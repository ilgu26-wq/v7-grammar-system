"""
EXP-ABSORB-OPS-01: Absorb Terminal Operations
==============================================

목적:
  FAST-UP-V에서 Absorb 진입을 실시간 감지하고,
  탈출/축소가 Absorb(종착) 및 Depth 악화를 줄이는지 검증

타임라인:
  t0: FAST-UP-V 시작
  t1: E_RESP → RELEASE 전환 (조기 경보)
  t2: Absorb 확정 (K bars 지속)
  t3: Depth Attractor 접근 (DAA TRUE)

가설:
  H-OPS-1: t1이 t2/t3보다 앞선다 (실시간 감지 가능)
  H-OPS-2: t2 이후 t3 확률 증가 (Absorb → Depth 연결)
  H-OPS-3: 탈출/축소가 Absorb/Depth를 줄인다

평가 지표:
  P(Absorb reached), P(DAA approached), Absorb duration
"""

import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

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


def is_fast_up_v(chart_df: pd.DataFrame, idx: int) -> bool:
    """FAST-UP-V 판정"""
    if idx + 15 >= len(chart_df):
        return False
    
    entry = chart_df.iloc[idx]['close']
    future = chart_df.iloc[idx+1:idx+16]
    
    max_up = future['high'].max() - entry
    max_down = entry - future['low'].min()
    
    if max_up < 15 or max_up <= max_down * 1.5:
        return False
    
    for i in range(1, 6):
        bar = chart_df.iloc[idx + i]
        if bar['high'] - entry >= 15:
            prices = [chart_df.iloc[idx+j]['close'] - entry for j in range(1, min(11, len(future)+1))]
            max_dd = 0
            peak = prices[0]
            for p in prices:
                if p > peak:
                    peak = p
                max_dd = max(max_dd, peak - p)
            if max_dd >= 10:
                return True
            break
    return False


def calc_e_resp(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> str:
    """E_RESP 계산"""
    if idx < lookback:
        return 'RELEASE'
    
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
    recent_avg = (recent['high'] - recent['low']).mean()
    past_avg = (past['high'] - past['low']).mean()
    eda = recent_avg / past_avg if past_avg > 0.1 else 1.0
    
    if rfc and eda <= 0.85:
        return 'ABSORB'
    return 'RELEASE'


def calc_daa(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> bool:
    """Depth Attractor Approach (DAA) 판정"""
    if idx < lookback:
        return False
    
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
    bcr_ok = bcr <= 0.8
    
    recent_avg = (recent['high'] - recent['low']).mean()
    past_avg = (past['high'] - past['low']).mean()
    eda = recent_avg / past_avg if past_avg > 0.1 else 1.0
    eda_ok = eda <= 0.85
    
    return rfc and bcr_ok and eda_ok


def analyze_session_timeline(chart_df: pd.DataFrame, t0: int, 
                              session_length: int = 30, absorb_k: int = 3) -> Dict:
    """세션 타임라인 분석"""
    if t0 + session_length >= len(chart_df):
        return None
    
    timeline = {
        't0': t0,
        't1': None,
        't2': None,
        't3': None,
        'absorb_reached': False,
        'daa_approached': False,
        'absorb_duration': 0,
        'mae': 0
    }
    
    entry = chart_df.iloc[t0]['close']
    absorb_count = 0
    
    for i in range(1, session_length + 1):
        bar_idx = t0 + i
        if bar_idx >= len(chart_df):
            break
        
        bar = chart_df.iloc[bar_idx]
        mae = max(timeline['mae'], entry - bar['low'])
        timeline['mae'] = mae
        
        e_resp = calc_e_resp(chart_df, bar_idx)
        
        if timeline['t1'] is None and e_resp == 'RELEASE':
            timeline['t1'] = i
        
        if e_resp == 'ABSORB':
            absorb_count += 1
            if absorb_count >= absorb_k and timeline['t2'] is None:
                timeline['t2'] = i
                timeline['absorb_reached'] = True
        else:
            if timeline['t2'] is not None:
                timeline['absorb_duration'] += 1
            absorb_count = 0
        
        if timeline['t2'] is not None:
            timeline['absorb_duration'] += 1
        
        if calc_daa(chart_df, bar_idx):
            if timeline['t3'] is None:
                timeline['t3'] = i
                timeline['daa_approached'] = True
    
    return timeline


def simulate_policy(chart_df: pd.DataFrame, t0: int, 
                     policy: str, session_length: int = 30) -> Dict:
    """정책 시뮬레이션"""
    if t0 + session_length >= len(chart_df):
        return None
    
    result = {
        'policy': policy,
        'absorb_reached': False,
        'daa_approached': False,
        'absorb_duration': 0,
        'mae': 0,
        'exit_bar': None
    }
    
    entry = chart_df.iloc[t0]['close']
    absorb_count = 0
    
    for i in range(1, session_length + 1):
        bar_idx = t0 + i
        if bar_idx >= len(chart_df):
            break
        
        bar = chart_df.iloc[bar_idx]
        
        e_resp = calc_e_resp(chart_df, bar_idx)
        
        if policy == 'EXIT' and e_resp == 'RELEASE' and i >= 3:
            result['exit_bar'] = i
            break
        
        if policy == 'REDUCE' and e_resp == 'RELEASE' and i >= 3:
            mae_after = (entry - bar['low']) * 0.5
            result['mae'] = max(result['mae'], mae_after)
        else:
            result['mae'] = max(result['mae'], entry - bar['low'])
        
        if e_resp == 'ABSORB':
            absorb_count += 1
            if absorb_count >= 3:
                result['absorb_reached'] = True
                result['absorb_duration'] += 1
        else:
            absorb_count = 0
        
        if calc_daa(chart_df, bar_idx):
            result['daa_approached'] = True
    
    return result


def run_exp_absorb_ops_01():
    """EXP-ABSORB-OPS-01 실행"""
    print("="*70)
    print("EXP-ABSORB-OPS-01: Absorb Terminal Operations")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("-"*70)
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    storm_in_signals = [s for s in signals if classify_storm_coordinate(s) == "STORM_IN"]
    print(f"Storm-IN signals: {len(storm_in_signals)}")
    
    fast_up_v_sessions = []
    
    for s in storm_in_signals:
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
        
        if idx < 20 or idx + 35 >= len(chart_df):
            continue
        
        if not calc_revisit_anchor(chart_df, idx):
            continue
        
        if not is_fast_up_v(chart_df, idx):
            continue
        
        fast_up_v_sessions.append({
            'ts': ts,
            't0': idx
        })
    
    print(f"FAST-UP-V sessions: {len(fast_up_v_sessions)}")
    
    print("\n" + "="*70)
    print("TIMELINE ANALYSIS (H-OPS-1: Early Detection)")
    print("="*70)
    
    timelines = []
    for session in fast_up_v_sessions:
        tl = analyze_session_timeline(chart_df, session['t0'])
        if tl:
            timelines.append(tl)
    
    t1_before_t2 = 0
    t1_before_t3 = 0
    t2_before_t3 = 0
    
    t1_t2_gaps = []
    t2_t3_gaps = []
    
    for tl in timelines:
        if tl['t1'] is not None and tl['t2'] is not None:
            if tl['t1'] < tl['t2']:
                t1_before_t2 += 1
                t1_t2_gaps.append(tl['t2'] - tl['t1'])
        
        if tl['t1'] is not None and tl['t3'] is not None:
            if tl['t1'] < tl['t3']:
                t1_before_t3 += 1
        
        if tl['t2'] is not None and tl['t3'] is not None:
            if tl['t2'] < tl['t3']:
                t2_before_t3 += 1
                t2_t3_gaps.append(tl['t3'] - tl['t2'])
    
    sessions_with_t1_t2 = sum(1 for tl in timelines if tl['t1'] and tl['t2'])
    sessions_with_t2_t3 = sum(1 for tl in timelines if tl['t2'] and tl['t3'])
    
    print(f"\nH-OPS-1: t1 → t2 선행 검증")
    print(f"  t1 < t2: {t1_before_t2}/{sessions_with_t1_t2} ({t1_before_t2/max(1,sessions_with_t1_t2)*100:.1f}%)")
    if t1_t2_gaps:
        print(f"  Avg gap (t1→t2): {np.mean(t1_t2_gaps):.1f} bars")
    
    print(f"\nH-OPS-1: t1 → t3 선행 검증")
    sessions_with_t1_t3 = sum(1 for tl in timelines if tl['t1'] and tl['t3'])
    print(f"  t1 < t3: {t1_before_t3}/{sessions_with_t1_t3} ({t1_before_t3/max(1,sessions_with_t1_t3)*100:.1f}%)")
    
    print("\n" + "="*70)
    print("ABSORB → DEPTH CONNECTION (H-OPS-2)")
    print("="*70)
    
    absorb_reached = [tl for tl in timelines if tl['absorb_reached']]
    no_absorb = [tl for tl in timelines if not tl['absorb_reached']]
    
    daa_after_absorb = sum(1 for tl in absorb_reached if tl['daa_approached'])
    daa_no_absorb = sum(1 for tl in no_absorb if tl['daa_approached'])
    
    p_daa_given_absorb = daa_after_absorb / max(1, len(absorb_reached)) * 100
    p_daa_no_absorb = daa_no_absorb / max(1, len(no_absorb)) * 100
    
    print(f"\nP(DAA | Absorb): {p_daa_given_absorb:.1f}% ({daa_after_absorb}/{len(absorb_reached)})")
    print(f"P(DAA | No Absorb): {p_daa_no_absorb:.1f}% ({daa_no_absorb}/{len(no_absorb)})")
    print(f"Difference: {p_daa_given_absorb - p_daa_no_absorb:+.1f}pp")
    
    h2_pass = p_daa_given_absorb - p_daa_no_absorb >= 15
    print(f"H-OPS-2: {'✅ PASS' if h2_pass else '❌ FAIL'}")
    
    print("\n" + "="*70)
    print("POLICY SIMULATION (H-OPS-3)")
    print("="*70)
    
    baseline_results = []
    exit_results = []
    
    for session in fast_up_v_sessions:
        baseline = simulate_policy(chart_df, session['t0'], 'BASELINE')
        exit_pol = simulate_policy(chart_df, session['t0'], 'EXIT')
        
        if baseline and exit_pol:
            baseline_results.append(baseline)
            exit_results.append(exit_pol)
    
    print(f"\nSessions simulated: {len(baseline_results)}")
    
    baseline_absorb = sum(1 for r in baseline_results if r['absorb_reached']) / len(baseline_results) * 100
    exit_absorb = sum(1 for r in exit_results if r['absorb_reached']) / len(exit_results) * 100
    
    baseline_daa = sum(1 for r in baseline_results if r['daa_approached']) / len(baseline_results) * 100
    exit_daa = sum(1 for r in exit_results if r['daa_approached']) / len(exit_results) * 100
    
    baseline_duration = np.mean([r['absorb_duration'] for r in baseline_results])
    exit_duration = np.mean([r['absorb_duration'] for r in exit_results])
    
    baseline_mae = np.mean([r['mae'] for r in baseline_results])
    exit_mae = np.mean([r['mae'] for r in exit_results])
    
    print("\n| Metric | Baseline | EXIT Policy | Change |")
    print("|--------|----------|-------------|--------|")
    print(f"| P(Absorb) | {baseline_absorb:.1f}% | {exit_absorb:.1f}% | {exit_absorb - baseline_absorb:+.1f}pp |")
    print(f"| P(DAA) | {baseline_daa:.1f}% | {exit_daa:.1f}% | {exit_daa - baseline_daa:+.1f}pp |")
    print(f"| Absorb Duration | {baseline_duration:.1f} bars | {exit_duration:.1f} bars | {(exit_duration/max(1,baseline_duration)-1)*100:+.1f}% |")
    print(f"| Avg MAE | {baseline_mae:.1f}pt | {exit_mae:.1f}pt | {(exit_mae/max(1,baseline_mae)-1)*100:+.1f}% |")
    
    criteria_met = 0
    if baseline_absorb - exit_absorb >= 15:
        criteria_met += 1
        print("\n  ✅ P(Absorb) reduced by ≥15pp")
    if baseline_daa - exit_daa >= 15:
        criteria_met += 1
        print("  ✅ P(DAA) reduced by ≥15pp")
    if baseline_duration > 0 and (baseline_duration - exit_duration) / baseline_duration >= 0.3:
        criteria_met += 1
        print("  ✅ Absorb duration reduced by ≥30%")
    
    print(f"\nH-OPS-3: Criteria met: {criteria_met}/3")
    print(f"Policy Status: {'✅ VALID' if criteria_met >= 2 else '⚠️ MARGINAL' if criteria_met >= 1 else '❌ INVALID'}")
    
    print("\n" + "="*70)
    print("FINAL ALGORITHM")
    print("="*70)
    
    if criteria_met >= 1:
        print("""
Real-time Rule v0.1
-------------------
IF MicroUnit == FAST-UP-V
AND E_RESP flips to RELEASE (t1 detected)
THEN EXIT immediately

IF DAA (RFC≥1 + BCR≤0.8 + EDA≤0.85) approaches
THEN hard EXIT (terminal)
""")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_ABSORB_OPS_01',
        'fast_up_v_sessions': len(fast_up_v_sessions),
        'h_ops_1': {
            't1_before_t2_rate': t1_before_t2 / max(1, sessions_with_t1_t2),
            'avg_gap_t1_t2': np.mean(t1_t2_gaps) if t1_t2_gaps else None
        },
        'h_ops_2': {
            'p_daa_given_absorb': p_daa_given_absorb,
            'p_daa_no_absorb': p_daa_no_absorb,
            'pass': h2_pass
        },
        'h_ops_3': {
            'baseline_absorb': baseline_absorb,
            'exit_absorb': exit_absorb,
            'baseline_daa': baseline_daa,
            'exit_daa': exit_daa,
            'criteria_met': criteria_met
        }
    }
    
    os.makedirs('v7-grammar-system/analysis/phase_o', exist_ok=True)
    output_path = 'v7-grammar-system/analysis/phase_o/exp_absorb_ops_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_absorb_ops_01()
