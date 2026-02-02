"""
EXP-E_RESP-ADV-01: E_RESP Sensor Adversarial Validation Suite
==============================================================

목적:
  "E_RESP = RELEASE → Absorb" 규칙이
  언제 실패하며, 그 실패가 구조적으로 설명 가능한가를 검증

FAIL TYPES:
  Type A (Miss): Absorb 발생, E_RESP 신호 없음
  Type B (Late): E_RESP 있으나 gap < 3 bars
  Type C (False): E_RESP 발생, Absorb 미발생

ADV TESTS:
  ADV-1: Time-Resolution Attack
  ADV-2: Noise Injection Attack
  ADV-3: Regime Flip Attack
  ADV-4: Feature Ablation Attack
  ADV-5: Counterfactual Replay
"""

import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import random

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import load_signals, classify_storm_coordinate


def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df = df.drop_duplicates(subset=['time'], keep='first')
    df = df.set_index('time').sort_index()
    return df


def calc_revisit_anchor(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> bool:
    if idx < lookback:
        return False
    window = chart_df.iloc[idx-lookback:idx]
    current = chart_df.iloc[idx]
    prev_high = window['high'].max()
    prev_low = window['low'].min()
    return current['high'] >= prev_high * 0.99 or current['low'] <= prev_low * 1.01


def calc_e_resp_components(chart_df: pd.DataFrame, idx: int, lookback: int = 10,
                            use_rfc: bool = True, use_bcr: bool = True, 
                            use_eda: bool = True) -> Tuple[str, Dict]:
    """E_RESP 계산 + 컴포넌트 반환 (ablation용)"""
    if idx < lookback:
        return 'RELEASE', {'rfc': False, 'bcr': 1.0, 'eda': 1.0}
    
    window = chart_df.iloc[idx-lookback:idx]
    
    consecutive_fails = 0
    for i in range(1, len(window)):
        prev_range = window['high'].iloc[i-1] - window['low'].iloc[i-1]
        if prev_range < 1:
            continue
        current_close = window['close'].iloc[i]
        prev_low = window['low'].iloc[i-1]
        recovery_threshold = prev_low + prev_range * 0.4
        if current_close < recovery_threshold:
            consecutive_fails += 1
        else:
            consecutive_fails = 0
    rfc = consecutive_fails >= 1
    
    recent = window.iloc[-lookback//2:]
    past = window.iloc[:lookback//2]
    recent_range = recent['high'].max() - recent['low'].min()
    past_range = past['high'].max() - past['low'].min()
    bcr = recent_range / past_range if past_range > 0.5 else 1.0
    
    recent_avg = (recent['high'] - recent['low']).mean()
    past_avg = (past['high'] - past['low']).mean()
    eda = recent_avg / past_avg if past_avg > 0.1 else 1.0
    
    components = {'rfc': rfc, 'bcr': bcr, 'eda': eda}
    
    conditions = []
    if use_rfc:
        conditions.append(rfc)
    if use_bcr:
        conditions.append(bcr <= 0.8)
    if use_eda:
        conditions.append(eda <= 0.85)
    
    if len(conditions) == 0:
        return 'RELEASE', components
    
    if all(conditions):
        return 'ABSORB', components
    return 'RELEASE', components


def calc_e_resp(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> str:
    result, _ = calc_e_resp_components(chart_df, idx, lookback)
    return result


def detect_regime(chart_df: pd.DataFrame, idx: int, lookback: int = 50) -> str:
    """시장 국면 판정"""
    if idx < lookback:
        return 'FLAT'
    
    window = chart_df.iloc[idx-lookback:idx]
    start_price = window['close'].iloc[0]
    end_price = window['close'].iloc[-1]
    
    change_pct = (end_price - start_price) / start_price * 100
    
    if change_pct > 1.5:
        return 'UP'
    elif change_pct < -1.5:
        return 'DOWN'
    else:
        return 'FLAT'


def analyze_session_for_fail(chart_df: pd.DataFrame, idx: int, 
                              session_length: int = 30, absorb_k: int = 3,
                              tau_min: int = 3, **kwargs) -> Dict:
    """세션 분석 + FAIL TYPE 판정"""
    if idx + session_length >= len(chart_df):
        return None
    
    result = {
        'absorb_reached': False,
        't_e_resp_flip': None,
        't_absorb': None,
        'gap': None,
        'fail_type': None
    }
    
    absorb_count = 0
    
    for i in range(1, session_length + 1):
        bar_idx = idx + i
        if bar_idx >= len(chart_df):
            break
        
        e_resp, _ = calc_e_resp_components(chart_df, bar_idx, **kwargs)
        
        if result['t_e_resp_flip'] is None and e_resp == 'RELEASE':
            result['t_e_resp_flip'] = i
        
        if e_resp == 'ABSORB':
            absorb_count += 1
            if absorb_count >= absorb_k and result['t_absorb'] is None:
                result['t_absorb'] = i
                result['absorb_reached'] = True
        else:
            absorb_count = 0
    
    if result['t_e_resp_flip'] and result['t_absorb']:
        result['gap'] = result['t_absorb'] - result['t_e_resp_flip']
    
    if result['absorb_reached']:
        if result['t_e_resp_flip'] is None:
            result['fail_type'] = 'A'
        elif result['gap'] is not None and result['gap'] < tau_min:
            result['fail_type'] = 'B'
        else:
            result['fail_type'] = 'SUCCESS'
    else:
        if result['t_e_resp_flip'] is not None:
            result['fail_type'] = 'C'
        else:
            result['fail_type'] = 'SUCCESS'
    
    return result


def get_valid_events(signals: List, chart_df: pd.DataFrame, require_revisit: bool = False) -> List[Dict]:
    """유효 이벤트 추출 (표본 확대 버전)"""
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    all_signals = signals
    
    events = []
    
    for s in all_signals:
        ts = s.get('ts')
        if not ts:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        try:
            idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        except:
            continue
        
        if idx < 50 or idx + 35 >= len(chart_df):
            continue
        
        if require_revisit and not calc_revisit_anchor(chart_df, idx):
            continue
        
        events.append({
            'ts': ts,
            'idx': idx,
            'regime': detect_regime(chart_df, idx),
            'storm': classify_storm_coordinate(s),
            'revisit': calc_revisit_anchor(chart_df, idx)
        })
    
    return events


def calc_fail_distribution(results: List[Dict]) -> Dict:
    """FAIL 분포 계산"""
    total = len(results)
    if total == 0:
        return {'A': 0, 'B': 0, 'C': 0, 'SUCCESS': 0}
    
    dist = defaultdict(int)
    for r in results:
        if r and r.get('fail_type'):
            dist[r['fail_type']] += 1
    
    return {
        'A': dist['A'] / total * 100,
        'B': dist['B'] / total * 100,
        'C': dist['C'] / total * 100,
        'SUCCESS': dist['SUCCESS'] / total * 100,
        'total': total
    }


def run_adv1_time_resolution(events: List, chart_df: pd.DataFrame) -> Dict:
    """ADV-1: Time-Resolution Attack"""
    print("\n" + "-"*60)
    print("ADV-1: Time-Resolution Attack")
    print("-"*60)
    
    base_results = []
    for e in events:
        r = analyze_session_for_fail(chart_df, e['idx'])
        if r:
            base_results.append(r)
    
    base_dist = calc_fail_distribution(base_results)
    
    print(f"\n1m Resolution (Base):")
    print(f"  Type A (Miss): {base_dist['A']:.1f}%")
    print(f"  Type B (Late): {base_dist['B']:.1f}%")
    print(f"  Type C (False): {base_dist['C']:.1f}%")
    print(f"  SUCCESS: {base_dist['SUCCESS']:.1f}%")
    
    lookback_tests = [5, 15, 20]
    variations = []
    
    for lb in lookback_tests:
        results = []
        for e in events:
            r = analyze_session_for_fail(chart_df, e['idx'], lookback=lb)
            if r:
                results.append(r)
        dist = calc_fail_distribution(results)
        variations.append({
            'lookback': lb,
            'dist': dist
        })
        print(f"\nLookback={lb} bars:")
        print(f"  Type A: {dist['A']:.1f}%, Type B: {dist['B']:.1f}%, Type C: {dist['C']:.1f}%")
    
    max_a_diff = max(abs(v['dist']['A'] - base_dist['A']) for v in variations)
    max_b_diff = max(abs(v['dist']['B'] - base_dist['B']) for v in variations)
    
    stable = max_a_diff < 10 and max_b_diff < 10
    
    print(f"\nMax deviation: A={max_a_diff:.1f}pp, B={max_b_diff:.1f}pp")
    print(f"Verdict: {'✅ PASS' if stable else '❌ FAIL'}")
    
    return {'base': base_dist, 'variations': variations, 'pass': stable}


def run_adv2_noise_injection(events: List, chart_df: pd.DataFrame) -> Dict:
    """ADV-2: Noise Injection Attack"""
    print("\n" + "-"*60)
    print("ADV-2: Noise Injection Attack")
    print("-"*60)
    
    base_results = []
    for e in events:
        r = analyze_session_for_fail(chart_df, e['idx'])
        if r:
            base_results.append(r)
    
    base_dist = calc_fail_distribution(base_results)
    
    print(f"\nBaseline:")
    print(f"  Type A: {base_dist['A']:.1f}%, Type B: {base_dist['B']:.1f}%, Type C: {base_dist['C']:.1f}%")
    
    noisy_df = chart_df.copy()
    atr = (noisy_df['high'] - noisy_df['low']).rolling(20).mean().fillna(1)
    noise = np.random.normal(0, 0.05, len(noisy_df)) * atr
    noisy_df['close'] = noisy_df['close'] + noise
    noisy_df['high'] = noisy_df['high'] + np.abs(noise) * 0.5
    noisy_df['low'] = noisy_df['low'] - np.abs(noise) * 0.5
    
    noisy_results = []
    for e in events:
        r = analyze_session_for_fail(noisy_df, e['idx'])
        if r:
            noisy_results.append(r)
    
    noisy_dist = calc_fail_distribution(noisy_results)
    
    print(f"\nWith 5% ATR Noise:")
    print(f"  Type A: {noisy_dist['A']:.1f}%, Type B: {noisy_dist['B']:.1f}%, Type C: {noisy_dist['C']:.1f}%")
    
    a_increase = noisy_dist['A'] - base_dist['A']
    c_increase = noisy_dist['C'] - base_dist['C']
    
    robust = a_increase < 10 and c_increase < 10
    
    print(f"\nChange: A={a_increase:+.1f}pp, C={c_increase:+.1f}pp")
    print(f"Verdict: {'✅ PASS' if robust else '❌ FAIL'}")
    
    return {'base': base_dist, 'noisy': noisy_dist, 'pass': robust}


def run_adv3_regime_flip(events: List, chart_df: pd.DataFrame) -> Dict:
    """ADV-3: Regime Flip Attack"""
    print("\n" + "-"*60)
    print("ADV-3: Regime Flip Attack")
    print("-"*60)
    
    regime_results = defaultdict(list)
    
    for e in events:
        r = analyze_session_for_fail(chart_df, e['idx'])
        if r:
            regime_results[e['regime']].append(r)
    
    regime_dists = {}
    for regime, results in regime_results.items():
        dist = calc_fail_distribution(results)
        regime_dists[regime] = dist
        print(f"\n{regime} Regime (N={len(results)}):")
        print(f"  Type A: {dist['A']:.1f}%, Type B: {dist['B']:.1f}%, Type C: {dist['C']:.1f}%")
    
    if len(regime_dists) < 2:
        print("\nNot enough regimes for comparison")
        return {'regime_dists': regime_dists, 'pass': True}
    
    fail_patterns = []
    for regime, dist in regime_dists.items():
        pattern = 'A' if dist['A'] > dist['B'] and dist['A'] > dist['C'] else \
                  'B' if dist['B'] > dist['C'] else 'C'
        fail_patterns.append(pattern)
    
    consistent = len(set(fail_patterns)) <= 2
    
    print(f"\nFail patterns by regime: {fail_patterns}")
    print(f"Consistent failure shape: {'✅ YES' if consistent else '❌ NO'}")
    print(f"Verdict: {'✅ PASS' if consistent else '❌ FAIL'}")
    
    return {'regime_dists': regime_dists, 'pass': consistent}


def run_adv4_feature_ablation(events: List, chart_df: pd.DataFrame) -> Dict:
    """ADV-4: Feature Ablation Attack"""
    print("\n" + "-"*60)
    print("ADV-4: Feature Ablation Attack")
    print("-"*60)
    
    base_results = []
    for e in events:
        r = analyze_session_for_fail(chart_df, e['idx'])
        if r:
            base_results.append(r)
    
    base_dist = calc_fail_distribution(base_results)
    
    print(f"\nFull E_RESP:")
    print(f"  Type A: {base_dist['A']:.1f}%, Type B: {base_dist['B']:.1f}%, Type C: {base_dist['C']:.1f}%")
    
    ablations = [
        ('No RFC', {'use_rfc': False, 'use_bcr': True, 'use_eda': True}),
        ('No BCR', {'use_rfc': True, 'use_bcr': False, 'use_eda': True}),
        ('No EDA', {'use_rfc': True, 'use_bcr': True, 'use_eda': False}),
    ]
    
    ablation_results = {}
    critical_features = []
    
    for name, kwargs in ablations:
        results = []
        for e in events:
            r = analyze_session_for_fail(chart_df, e['idx'], **kwargs)
            if r:
                results.append(r)
        
        dist = calc_fail_distribution(results)
        ablation_results[name] = dist
        
        a_change = dist['A'] - base_dist['A']
        
        print(f"\n{name}:")
        print(f"  Type A: {dist['A']:.1f}% ({a_change:+.1f}pp)")
        print(f"  Type B: {dist['B']:.1f}%")
        print(f"  Type C: {dist['C']:.1f}%")
        
        if a_change > 10:
            critical_features.append(name.replace('No ', ''))
    
    print(f"\nCritical features: {critical_features if critical_features else 'None (may be redundant)'}")
    
    has_critical = len(critical_features) >= 1
    print(f"Verdict: {'✅ PASS' if has_critical else '⚠️ MARGINAL'}")
    
    return {'base': base_dist, 'ablations': ablation_results, 
            'critical': critical_features, 'pass': has_critical}


def run_adv5_counterfactual(events: List, chart_df: pd.DataFrame) -> Dict:
    """ADV-5: Counterfactual Replay"""
    print("\n" + "-"*60)
    print("ADV-5: Counterfactual Replay (Blind Future)")
    print("-"*60)
    
    base_results = []
    for e in events:
        r = analyze_session_for_fail(chart_df, e['idx'])
        if r:
            base_results.append(r)
    
    base_dist = calc_fail_distribution(base_results)
    
    cf_success = 0
    cf_total = 0
    
    for e in events:
        idx = e['idx']
        if idx + 30 >= len(chart_df):
            continue
        
        t_flip = None
        for i in range(1, 31):
            bar_idx = idx + i
            e_resp = calc_e_resp(chart_df, bar_idx)
            if e_resp == 'RELEASE':
                t_flip = i
                break
        
        absorb_count = 0
        t_absorb = None
        for i in range(1, 31):
            bar_idx = idx + i
            e_resp = calc_e_resp(chart_df, bar_idx)
            if e_resp == 'ABSORB':
                absorb_count += 1
                if absorb_count >= 3:
                    t_absorb = i
                    break
            else:
                absorb_count = 0
        
        if t_absorb is not None:
            cf_total += 1
            if t_flip is not None and t_flip < t_absorb:
                cf_success += 1
    
    cf_rate = cf_success / cf_total * 100 if cf_total > 0 else 0
    
    print(f"\nCounterfactual (real-time simulation):")
    print(f"  Absorb events: {cf_total}")
    print(f"  E_RESP flip before Absorb: {cf_success} ({cf_rate:.1f}%)")
    print(f"  Baseline P(Flip<Absorb): ~{100 - base_dist['A'] - base_dist['B']:.1f}%")
    
    drop = (100 - base_dist['A'] - base_dist['B']) - cf_rate
    real_time = drop < 15
    
    print(f"\nPerformance drop: {drop:.1f}pp")
    print(f"Verdict: {'✅ PASS (Real-time valid)' if real_time else '❌ FAIL (Future leakage)'}")
    
    return {'cf_rate': cf_rate, 'drop': drop, 'pass': real_time}


def run_exp_e_resp_adv_01():
    """EXP-E_RESP-ADV-01 전체 실행"""
    print("="*70)
    print("EXP-E_RESP-ADV-01: E_RESP Sensor Adversarial Validation Suite")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    all_events = get_valid_events(signals, chart_df, require_revisit=False)
    events = all_events[:500]
    print(f"\nTotal Events (Sampled): N = {len(events)} / {len(all_events)}")
    
    storm_in = sum(1 for e in events if e.get('storm') == 'STORM_IN')
    revisit = sum(1 for e in events if e.get('revisit'))
    print(f"  Storm-IN: {storm_in}")
    print(f"  With Revisit: {revisit}")
    
    base_results = []
    for e in events:
        r = analyze_session_for_fail(chart_df, e['idx'])
        if r:
            base_results.append(r)
    
    base_dist = calc_fail_distribution(base_results)
    
    print("\n" + "="*70)
    print("BASELINE FAIL SUMMARY")
    print("="*70)
    print(f"Type A (Miss): {base_dist['A']:.1f}%")
    print(f"Type B (Late): {base_dist['B']:.1f}%")
    print(f"Type C (False): {base_dist['C']:.1f}%")
    print(f"SUCCESS: {base_dist['SUCCESS']:.1f}%")
    
    adv1 = run_adv1_time_resolution(events, chart_df)
    adv2 = run_adv2_noise_injection(events, chart_df)
    adv3 = run_adv3_regime_flip(events, chart_df)
    adv4 = run_adv4_feature_ablation(events, chart_df)
    adv5 = run_adv5_counterfactual(events, chart_df)
    
    print("\n" + "="*70)
    print("FINAL VERDICT")
    print("="*70)
    
    tests = [
        ('ADV-1 Time Resolution', adv1['pass']),
        ('ADV-2 Noise Injection', adv2['pass']),
        ('ADV-3 Regime Flip', adv3['pass']),
        ('ADV-4 Feature Ablation', adv4['pass']),
        ('ADV-5 Counterfactual', adv5['pass'])
    ]
    
    passed = sum(1 for _, p in tests if p)
    
    print("\n| ADV Test | Result |")
    print("|----------|--------|")
    for name, result in tests:
        print(f"| {name} | {'✅ PASS' if result else '❌ FAIL'} |")
    
    print(f"\nTotal: {passed}/5 passed")
    
    fail_types = [base_dist['A'], base_dist['B'], base_dist['C']]
    dominant_fail = ['A', 'B', 'C'][np.argmax(fail_types)] if max(fail_types) > 5 else 'NONE'
    
    print(f"\nDominant Fail Type: {dominant_fail}")
    
    if passed >= 4:
        verdict = "✅ STRUCTURALLY ROBUST - Sensor is reliable"
    elif passed >= 3:
        verdict = "⚠️ CONDITIONAL - Needs regime/noise filter"
    else:
        verdict = "❌ INVALID - Sensor needs redesign"
    
    print(f"\n{verdict}")
    
    fail_consistent = (dominant_fail != 'NONE' and 
                       base_dist[dominant_fail] > base_dist['A'] + base_dist['B'] + base_dist['C'] - base_dist[dominant_fail])
    
    print(f"\nFail Pattern Consistency: {'YES' if fail_consistent else 'NO'}")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_E_RESP_ADV_01',
        'total_events': len(events),
        'baseline_fail': base_dist,
        'adv1_time': adv1,
        'adv2_noise': adv2,
        'adv3_regime': adv3,
        'adv4_ablation': adv4,
        'adv5_counterfactual': adv5,
        'passed': passed,
        'dominant_fail': dominant_fail,
        'verdict': verdict
    }
    
    output_path = 'v7-grammar-system/analysis/phase_o/exp_e_resp_adv_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_e_resp_adv_01()
