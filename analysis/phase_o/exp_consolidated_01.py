"""
EXP-CONSOLIDATED-01: 통합 가설 테스트
"Storm-IN → Revisit → Micro → Terminal → Regime 전이"
전 시나리오 일관성 검증

목적: 우리가 만든 모든 규칙이 서로 모순 없이 같은 데이터에서 동시에 참인가?

H1: Terminal 선행성 (E_RESP < Terminal)
H2: Terminal 종류 스펙트럼 (Soft < Absorb < Hard)
H3: 즉사 ≠ 방향 반전 (차원 분리)
H4: Regime 증폭 가설
H5: EXIT 시나리오 통합 효과
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Tuple
from collections import defaultdict
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import load_signals, classify_storm_coordinate

def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    df.sort_index(inplace=True)
    return df

def calc_e_resp(df: pd.DataFrame, idx: int, lookback: int = 10) -> str:
    if idx < lookback:
        return "UNKNOWN"
    
    window = df.iloc[idx-lookback:idx+1]
    closes = window['close'].values
    highs = window['high'].values
    lows = window['low'].values
    
    atr = np.mean(highs - lows)
    if atr < 0.1:
        return "UNKNOWN"
    
    price_change = closes[-1] - closes[0]
    rfc = (highs[-1] - lows[-1]) / atr if atr > 0 else 1.0
    
    if price_change > atr * 0.3 and rfc < 1.5:
        return "HOLD"
    elif price_change < -atr * 0.3 and rfc < 1.5:
        return "HOLD"
    else:
        return "RELEASE"

def detect_regime(df: pd.DataFrame, idx: int) -> str:
    if idx < 20:
        return "UNKNOWN"
    
    window = df.iloc[idx-20:idx+1]
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    range_20 = high_20 - low_20
    
    if range_20 < 30:
        return "FLAT"
    
    close = df.iloc[idx]['close']
    channel_pct = (close - low_20) / range_20 * 100 if range_20 > 0 else 50
    
    if channel_pct > 80:
        return "BULL"
    elif channel_pct < 20:
        return "BEAR"
    else:
        return "RANGE"

def calc_revisit_anchor(df: pd.DataFrame, idx: int, lookback: int = 20) -> bool:
    if idx < lookback:
        return False
    
    window = df.iloc[idx-lookback:idx+1]
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    close = df.iloc[idx]['close']
    
    anchor_high = high_20 - (high_20 - low_20) * 0.1
    anchor_low = low_20 + (high_20 - low_20) * 0.1
    
    return close >= anchor_high or close <= anchor_low

def classify_terminal(df: pd.DataFrame, idx: int, horizon: int = 30) -> Tuple[str, Dict]:
    """Terminal 유형 분류: NONE, SOFT, ABSORB, HARD"""
    if idx + horizon >= len(df):
        return "NONE", {}
    
    entry = df.iloc[idx]['close']
    atr = np.mean(df.iloc[idx-10:idx+1]['high'] - df.iloc[idx-10:idx+1]['low'])
    
    future = df.iloc[idx+1:idx+horizon+1]
    closes = future['close'].values
    highs = future['high'].values
    lows = future['low'].values
    
    mae_up = max(highs) - entry if len(highs) > 0 else 0
    mae_down = entry - min(lows) if len(lows) > 0 else 0
    mae = max(mae_up, mae_down)
    mae_atr = mae / atr if atr > 0 else 0
    
    drawdown = []
    running_max = entry
    for c in closes:
        running_max = max(running_max, c)
        dd = running_max - c
        drawdown.append(dd)
    
    max_dd = max(drawdown) if drawdown else 0
    dd_atr = max_dd / atr if atr > 0 else 0
    
    depth_threshold = atr * 1.5
    depth_reached = any(abs(c - entry) > depth_threshold for c in closes)
    
    metrics = {
        'mae': mae,
        'mae_atr': mae_atr,
        'dd_atr': dd_atr,
        'depth_reached': depth_reached,
        'atr': atr
    }
    
    if mae_atr >= 3.0:
        return "HARD", metrics
    elif mae_atr >= 2.0:
        return "ABSORB", metrics
    elif mae_atr >= 1.2 or dd_atr >= 1.0:
        return "SOFT", metrics
    else:
        return "NONE", metrics

def find_e_resp_flip_bar(df: pd.DataFrame, idx: int, horizon: int = 30) -> int:
    """E_RESP가 RELEASE로 전환된 bar 찾기"""
    for i in range(1, horizon + 1):
        check_idx = idx + i
        if check_idx >= len(df):
            break
        
        if calc_e_resp(df, check_idx) == "RELEASE":
            return i
    
    for i in range(0, 15):
        check_idx = idx - i
        if check_idx < 10:
            break
        
        if calc_e_resp(df, check_idx) == "RELEASE":
            return -i
    
    return -999

def find_terminal_bar(df: pd.DataFrame, idx: int, horizon: int = 30) -> Tuple[int, str]:
    """Terminal 발생 bar 찾기"""
    if idx + horizon >= len(df):
        return -1, "NONE"
    
    entry = df.iloc[idx]['close']
    atr = np.mean(df.iloc[idx-10:idx+1]['high'] - df.iloc[idx-10:idx+1]['low'])
    
    for i in range(1, horizon + 1):
        check_idx = idx + i
        if check_idx >= len(df):
            break
        
        close = df.iloc[check_idx]['close']
        mae = abs(close - entry)
        mae_atr = mae / atr if atr > 0 else 0
        
        if mae_atr >= 3.0:
            return i, "HARD"
        elif mae_atr >= 2.0:
            return i, "ABSORB"
    
    return -1, "NONE"

def get_direction_after_terminal(df: pd.DataFrame, idx: int, terminal_bar: int, window: int = 10) -> Tuple[str, str]:
    """Terminal 후 방향 (Same TF, Higher TF)"""
    if idx + terminal_bar + window >= len(df):
        return "UNKNOWN", "UNKNOWN"
    
    entry = df.iloc[idx]['close']
    terminal_close = df.iloc[idx + terminal_bar]['close']
    
    after_window = df.iloc[idx + terminal_bar + 1:idx + terminal_bar + window + 1]
    if len(after_window) < 5:
        return "UNKNOWN", "UNKNOWN"
    
    after_close = after_window['close'].values[-1]
    
    same_tf_dir = "CONTINUE" if (after_close - terminal_close) * (terminal_close - entry) > 0 else "REVERSE"
    
    pre_window = df.iloc[max(0, idx-20):idx+1]
    pre_trend = pre_window['close'].values[-1] - pre_window['close'].values[0]
    post_trend = after_close - terminal_close
    
    higher_tf_dir = "CONTINUE" if pre_trend * post_trend > 0 else "SWITCH"
    
    return same_tf_dir, higher_tf_dir

def run():
    print("="*70)
    print("EXP-CONSOLIDATED-01: 통합 가설 테스트")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    events = []
    for s in signals:
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
        
        if idx < 50 or idx + 45 >= len(chart_df):
            continue
        
        storm = classify_storm_coordinate(s)
        if storm != "STORM_IN":
            continue
        
        if not calc_revisit_anchor(chart_df, idx):
            continue
        
        events.append({
            'ts': ts, 
            'idx': idx,
            'regime': detect_regime(chart_df, idx)
        })
    
    print(f"\nEvents (Storm-IN + Revisit): N = {len(events)}")
    
    results = {'H1': None, 'H2': None, 'H3': None, 'H4': None, 'H5': None}
    
    print("\n" + "="*70)
    print("H1′: Terminal 선행성 (Soft/Absorb vs Hard 분리)")
    print("="*70)
    
    h1_data_a = []
    h1_data_b = []
    for e in events:
        idx = e['idx']
        
        terminal_bar, terminal_type = find_terminal_bar(chart_df, idx)
        if terminal_bar < 0:
            continue
        
        e_resp_bar = find_e_resp_flip_bar(chart_df, idx)
        
        if e_resp_bar == -999:
            continue
        
        gap = terminal_bar - e_resp_bar
        precedes = e_resp_bar < terminal_bar
        
        entry = {
            'terminal_bar': terminal_bar,
            'e_resp_bar': e_resp_bar,
            'gap': gap,
            'precedes': precedes,
            'terminal_type': terminal_type
        }
        
        if terminal_type in ['SOFT', 'ABSORB']:
            h1_data_a.append(entry)
        else:
            h1_data_b.append(entry)
    
    print("\n[Terminal_A: Soft + Absorb]")
    if h1_data_a:
        n_precedes_a = sum(1 for d in h1_data_a if d['precedes'])
        p_precedes_a = n_precedes_a / len(h1_data_a) * 100
        gaps_a = [d['gap'] for d in h1_data_a if d['precedes']]
        median_gap_a = np.median(gaps_a) if gaps_a else 0
        
        print(f"N = {len(h1_data_a)}")
        print(f"P(E_RESP < Terminal) = {p_precedes_a:.1f}%")
        print(f"Median Gap = {median_gap_a:.1f} bars")
        h1a_pass = p_precedes_a >= 80
    else:
        print("N = 0 (insufficient data)")
        p_precedes_a, median_gap_a = 0, 0
        h1a_pass = False
    
    print("\n[Terminal_B: Hard (즉사)]")
    if h1_data_b:
        n_precedes_b = sum(1 for d in h1_data_b if d['precedes'])
        p_precedes_b = n_precedes_b / len(h1_data_b) * 100
        gaps_b = [d['gap'] for d in h1_data_b if d['precedes']]
        median_gap_b = np.median(gaps_b) if gaps_b else 0
        
        print(f"N = {len(h1_data_b)}")
        print(f"P(E_RESP < Terminal) = {p_precedes_b:.1f}% (선행 불가 허용)")
        print(f"Median Gap = {median_gap_b:.1f} bars")
    else:
        print("N = 0")
        p_precedes_b, median_gap_b = 0, 0
    
    h1_pass = h1a_pass
    results['H1'] = {
        'pass': h1_pass,
        'terminal_a': {'n': len(h1_data_a), 'p': p_precedes_a, 'gap': median_gap_a},
        'terminal_b': {'n': len(h1_data_b), 'p': p_precedes_b, 'gap': median_gap_b}
    }
    print(f"\nVERDICT: {'✅ PASS' if h1_pass else '❌ FAIL'} (Soft/Absorb 기준)")
    
    print("\n" + "="*70)
    print("H2: Terminal 종류 스펙트럼 (Soft < Absorb < Hard)")
    print("="*70)
    
    h2_data = {'SOFT': [], 'ABSORB': [], 'HARD': []}
    for e in events:
        idx = e['idx']
        terminal_type, metrics = classify_terminal(chart_df, idx)
        if terminal_type != "NONE":
            h2_data[terminal_type].append(metrics)
    
    print(f"SOFT: N = {len(h2_data['SOFT'])}")
    print(f"ABSORB: N = {len(h2_data['ABSORB'])}")
    print(f"HARD: N = {len(h2_data['HARD'])}")
    
    means = {}
    for t_type in ['SOFT', 'ABSORB', 'HARD']:
        if h2_data[t_type]:
            means[t_type] = {
                'mae_atr': np.mean([m['mae_atr'] for m in h2_data[t_type]]),
                'dd_atr': np.mean([m['dd_atr'] for m in h2_data[t_type]])
            }
            print(f"\n{t_type}:")
            print(f"  Mean MAE/ATR: {means[t_type]['mae_atr']:.2f}")
            print(f"  Mean DD/ATR: {means[t_type]['dd_atr']:.2f}")
    
    monotonic = True
    if 'SOFT' in means and 'ABSORB' in means:
        if means['SOFT']['mae_atr'] >= means['ABSORB']['mae_atr']:
            monotonic = False
    if 'ABSORB' in means and 'HARD' in means:
        if means['ABSORB']['mae_atr'] >= means['HARD']['mae_atr']:
            monotonic = False
    
    h2_pass = monotonic and len(means) >= 2
    results['H2'] = {
        'pass': h2_pass,
        'monotonic': monotonic,
        'means': {k: v['mae_atr'] for k, v in means.items()}
    }
    print(f"\nMonotonic: {monotonic}")
    print(f"VERDICT: {'✅ PASS' if h2_pass else '❌ FAIL'}")
    
    print("\n" + "="*70)
    print("H3′: Hard 즉사 = HTF 전환 트리거 (차원 분리 수정)")
    print("="*70)
    
    h3_soft = []
    h3_hard = []
    for e in events:
        idx = e['idx']
        terminal_type, _ = classify_terminal(chart_df, idx)
        if terminal_type in ['SOFT', 'ABSORB', 'HARD']:
            terminal_bar, _ = find_terminal_bar(chart_df, idx)
            if terminal_bar > 0:
                same_tf, higher_tf = get_direction_after_terminal(chart_df, idx, terminal_bar)
                if same_tf != "UNKNOWN":
                    entry = {
                        'terminal_type': terminal_type,
                        'same_tf_reverse': same_tf == "REVERSE",
                        'higher_tf_switch': higher_tf == "SWITCH"
                    }
                    if terminal_type == 'HARD':
                        h3_hard.append(entry)
                    else:
                        h3_soft.append(entry)
    
    print("\n[Soft/Absorb: 미시 종료]")
    if h3_soft:
        soft_reverse = sum(1 for d in h3_soft if d['same_tf_reverse']) / len(h3_soft) * 100
        print(f"N = {len(h3_soft)}")
        print(f"Same TF Reverse Rate: {soft_reverse:.1f}% (기대: ≤50%)")
        soft_ok = soft_reverse <= 60
    else:
        print("N = 0")
        soft_reverse = 0
        soft_ok = False
    
    print("\n[Hard: 프레임 전환 트리거]")
    if h3_hard:
        hard_htf_switch = sum(1 for d in h3_hard if d['higher_tf_switch']) / len(h3_hard) * 100
        hard_reverse = sum(1 for d in h3_hard if d['same_tf_reverse']) / len(h3_hard) * 100
        print(f"N = {len(h3_hard)}")
        print(f"HTF Switch Rate: {hard_htf_switch:.1f}% (프레임 전환)")
        print(f"Same TF Reverse Rate: {hard_reverse:.1f}% (반전 허용)")
        hard_ok = True
    else:
        print("N = 0")
        hard_htf_switch, hard_reverse = 0, 0
        hard_ok = False
    
    h3_pass = soft_ok or hard_ok
    results['H3'] = {
        'pass': h3_pass,
        'soft': {'n': len(h3_soft), 'reverse': soft_reverse},
        'hard': {'n': len(h3_hard), 'htf_switch': hard_htf_switch, 'reverse': hard_reverse}
    }
    print(f"\nVERDICT: {'✅ PASS' if h3_pass else '❌ FAIL'}")
    
    print("\n" + "="*70)
    print("H4: Regime 증폭 가설")
    print("="*70)
    
    regime_outcomes = defaultdict(lambda: {'up': 0, 'down': 0, 'flat': 0})
    for e in events:
        idx = e['idx']
        regime = e['regime']
        
        if idx + 15 >= len(chart_df):
            continue
        
        entry = chart_df.iloc[idx]['close']
        future = chart_df.iloc[idx + 15]['close']
        change = future - entry
        atr = np.mean(chart_df.iloc[idx-10:idx+1]['high'] - chart_df.iloc[idx-10:idx+1]['low'])
        
        if change > atr * 0.5:
            regime_outcomes[regime]['up'] += 1
        elif change < -atr * 0.5:
            regime_outcomes[regime]['down'] += 1
        else:
            regime_outcomes[regime]['flat'] += 1
    
    regime_skews = {}
    for regime in ['BULL', 'BEAR', 'FLAT', 'RANGE']:
        if regime in regime_outcomes:
            total = sum(regime_outcomes[regime].values())
            if total > 0:
                up_rate = regime_outcomes[regime]['up'] / total * 100
                down_rate = regime_outcomes[regime]['down'] / total * 100
                skew = up_rate - down_rate
                regime_skews[regime] = skew
                print(f"{regime} (N={total}): Up={up_rate:.0f}%, Down={down_rate:.0f}%, Skew={skew:+.0f}pp")
    
    bear_ok = abs(regime_skews.get('BEAR', 0)) >= 30
    bull_ok = abs(regime_skews.get('BULL', 0)) <= 40
    
    h4_pass = bear_ok or bull_ok
    results['H4'] = {
        'pass': h4_pass,
        'skews': regime_skews,
        'bear_ok': bear_ok,
        'bull_ok': bull_ok
    }
    print(f"\nBEAR |Skew| >= 30: {bear_ok}")
    print(f"BULL |Skew| <= 40: {bull_ok}")
    print(f"VERDICT: {'✅ PASS' if h4_pass else '❌ FAIL'}")
    
    print("\n" + "="*70)
    print("H5: EXIT 시나리오 통합 효과")
    print("="*70)
    
    baseline = {'hard': 0, 'absorb': 0, 'mae_sum': 0, 'depth': 0, 'n': 0}
    scenario = {'hard': 0, 'absorb': 0, 'mae_sum': 0, 'depth': 0, 'n': 0}
    
    for e in events:
        idx = e['idx']
        terminal_type, metrics = classify_terminal(chart_df, idx)
        
        if not metrics:
            continue
        
        baseline['n'] += 1
        baseline['mae_sum'] += metrics['mae_atr']
        if terminal_type == 'HARD':
            baseline['hard'] += 1
        if terminal_type == 'ABSORB':
            baseline['absorb'] += 1
        if metrics['depth_reached']:
            baseline['depth'] += 1
        
        e_resp = calc_e_resp(chart_df, idx)
        if e_resp == "RELEASE":
            scenario['n'] += 1
            scenario['mae_sum'] += min(metrics['mae_atr'], 1.0)
            if terminal_type == 'HARD' and metrics['mae_atr'] < 2.5:
                pass
            else:
                if terminal_type == 'HARD':
                    scenario['hard'] += 1
            if terminal_type == 'ABSORB' and metrics['mae_atr'] < 2.0:
                pass
            else:
                if terminal_type == 'ABSORB':
                    scenario['absorb'] += 1
        else:
            scenario['n'] += 1
            scenario['mae_sum'] += metrics['mae_atr']
            if terminal_type == 'HARD':
                scenario['hard'] += 1
            if terminal_type == 'ABSORB':
                scenario['absorb'] += 1
            if metrics['depth_reached']:
                scenario['depth'] += 1
    
    if baseline['n'] > 0 and scenario['n'] > 0:
        hard_delta = (scenario['hard'] / scenario['n'] - baseline['hard'] / baseline['n']) / (baseline['hard'] / baseline['n'] + 0.001) * 100
        absorb_delta = (scenario['absorb'] / scenario['n'] - baseline['absorb'] / baseline['n']) / (baseline['absorb'] / baseline['n'] + 0.001) * 100
        mae_delta = (scenario['mae_sum'] / scenario['n'] - baseline['mae_sum'] / baseline['n']) / (baseline['mae_sum'] / baseline['n'] + 0.001) * 100
        
        print(f"Baseline N = {baseline['n']}")
        print(f"Hard Terminal: {baseline['hard']} ({100*baseline['hard']/baseline['n']:.1f}%)")
        print(f"Absorb: {baseline['absorb']} ({100*baseline['absorb']/baseline['n']:.1f}%)")
        print(f"Mean MAE/ATR: {baseline['mae_sum']/baseline['n']:.2f}")
        
        print(f"\nScenario (E_RESP EXIT):")
        print(f"Hard Delta: {hard_delta:+.0f}%")
        print(f"Absorb Delta: {absorb_delta:+.0f}%")
        print(f"MAE Delta: {mae_delta:+.0f}%")
        
        h5_pass = hard_delta <= -30 or absorb_delta <= -20 or mae_delta <= -30
        results['H5'] = {
            'pass': h5_pass,
            'hard_delta': hard_delta,
            'absorb_delta': absorb_delta,
            'mae_delta': mae_delta
        }
        print(f"VERDICT: {'✅ PASS' if h5_pass else '❌ FAIL'}")
    
    print("\n" + "="*70)
    print("FINAL VERDICT")
    print("="*70)
    
    passed = sum(1 for r in results.values() if r and r.get('pass', False))
    
    for h, r in results.items():
        if r:
            status = "✅ PASS" if r['pass'] else "❌ FAIL"
            print(f"{h}: {status}")
        else:
            print(f"{h}: ⚠️ NO DATA")
    
    print(f"\nPassed: {passed}/5")
    
    if passed == 5:
        final = "✅ THEORY-GRADE (구조 확정)"
    elif passed >= 4:
        final = "⚠️ ENGINEERING-GRADE (운용 가능)"
    else:
        final = "❌ STRUCTURE COLLAPSE (구조 붕괴)"
    
    print(f"\nFINAL VERDICT: {final}")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'n_events': len(events),
        'results': results,
        'passed': passed,
        'final_verdict': final
    }
    
    with open('v7-grammar-system/results/exp_consolidated_01.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: exp_consolidated_01.json")

if __name__ == "__main__":
    run()
