"""
EXP-MICRO-TRANSITION-COORD-01: 미시 상태 전이 좌표 분석
=======================================================

목적:
  Revisit 이후 미시단위들이 어떤 좌표 조건에서 전이되는지 규칙 추출

좌표 축:
  X - E_DIR: {POS, NEG} (에너지 방향)
  Y - E_RESP: {ABSORB, RELEASE} (에너지 응답)
  Z - T_COMMIT: {FAST, DELAYED} (시간 확정)
  W - PATH: {V, STAIR} (경로 형태)

상태 문법:
  STATE = ⟨MicroUnit | E_DIR | E_RESP | T_COMMIT | PATH⟩

판정:
  Transition Purity ≥ +25pp AND N ≥ 10 → PASS
"""

import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from itertools import combinations

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
    revisit_high = current['high'] >= prev_high * 0.99
    revisit_low = current['low'] <= prev_low * 1.01
    return revisit_high or revisit_low


def calc_e_dir(chart_df: pd.DataFrame, idx: int) -> str:
    """X축: Energy Direction"""
    if idx < 1:
        return 'NEG'
    current = chart_df.iloc[idx]
    delta = current['close'] - current['open']
    return 'POS' if delta > 0 else 'NEG'


def calc_e_resp(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> str:
    """Y축: Energy Response (ABSORB/RELEASE)"""
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


def calc_t_commit(chart_df: pd.DataFrame, idx: int, threshold: float = 15) -> str:
    """Z축: Temporal Commitment (FAST/DELAYED)"""
    if idx + 15 >= len(chart_df):
        return 'DELAYED'
    
    entry = chart_df.iloc[idx]['close']
    
    for i in range(1, 16):
        bar = chart_df.iloc[idx + i]
        if abs(bar['high'] - entry) >= threshold or abs(entry - bar['low']) >= threshold:
            return 'FAST' if i <= 5 else 'DELAYED'
    
    return 'DELAYED'


def calc_path(chart_df: pd.DataFrame, idx: int, window: int = 10) -> str:
    """W축: Path Geometry (V/STAIR)"""
    if idx + window >= len(chart_df):
        return 'STAIR'
    
    entry = chart_df.iloc[idx]['close']
    bars = chart_df.iloc[idx+1:idx+1+window]
    
    prices = [bars.iloc[i]['close'] - entry for i in range(len(bars))]
    
    max_drawdown = 0
    peak = prices[0]
    for p in prices:
        if p > peak:
            peak = p
        drawdown = abs(peak - p)
        max_drawdown = max(max_drawdown, drawdown)
    
    return 'V' if max_drawdown >= 10 else 'STAIR'


def classify_micro_unit(chart_df: pd.DataFrame, idx: int) -> Optional[str]:
    """미시단위 분류"""
    if idx + 15 >= len(chart_df):
        return None
    
    entry = chart_df.iloc[idx]['close']
    future = chart_df.iloc[idx+1:idx+16]
    
    max_up = future['high'].max() - entry
    max_down = entry - future['low'].min()
    
    closes = future['close'].values
    returns = np.diff(closes)
    
    if max_up >= 15 and max_up > max_down * 1.5:
        direction = 'UP'
        consistency = sum(1 for r in returns if r > 0) / len(returns)
    elif max_down >= 15 and max_down > max_up * 1.5:
        direction = 'DOWN'
        consistency = sum(1 for r in returns if r < 0) / len(returns)
    else:
        direction = 'MIXED'
        consistency = 0.5
    
    tp_hit = max_up >= 20 or max_down >= 20
    sl_hit = (max_down >= 10 and direction == 'UP') or (max_up >= 10 and direction == 'DOWN')
    
    if tp_hit and not sl_hit:
        outcome = 'WIN'
    elif sl_hit:
        outcome = 'LOSS'
    else:
        outcome = 'NEUTRAL'
    
    if outcome == 'WIN' and direction == 'MIXED':
        return 'Absorb'
    
    if direction == 'MIXED' or consistency < 0.5:
        return 'Chaos'
    
    t_commit = calc_t_commit(chart_df, idx)
    path = calc_path(chart_df, idx)
    
    if direction == 'DOWN':
        return f"FAST-DOWN-{path}" if t_commit == 'FAST' else f"DELAYED-DOWN-{path}"
    else:
        return f"FAST-UP-{path}" if t_commit == 'FAST' else f"DELAYED-UP-{path}"


def build_state_label(micro_unit: str, e_dir: str, e_resp: str, 
                       t_commit: str, path: str) -> str:
    """상태 라벨 생성"""
    return f"⟨{micro_unit}|{e_dir}|{e_resp}|{t_commit}|{path}⟩"


def calc_transition_purity(transitions: List[Tuple[str, str]], 
                            from_state: str, to_state: str) -> Tuple[float, int]:
    """전이 순도 계산"""
    from_transitions = [t for t in transitions if t[0] == from_state]
    if len(from_transitions) == 0:
        return 0, 0
    
    to_count = sum(1 for t in from_transitions if t[1] == to_state)
    not_to_count = len(from_transitions) - to_count
    
    p_to = to_count / len(from_transitions)
    p_not_to = not_to_count / len(from_transitions)
    
    purity = (p_to - p_not_to) * 100
    return purity, to_count


def run_exp_micro_transition_coord_01():
    """EXP-MICRO-TRANSITION-COORD-01 실행"""
    print("="*70)
    print("EXP-MICRO-TRANSITION-COORD-01: 미시 상태 전이 좌표 분석")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("-"*70)
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    storm_in_signals = [s for s in signals if classify_storm_coordinate(s) == "STORM_IN"]
    print(f"Storm-IN signals: {len(storm_in_signals)}")
    
    samples = []
    
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
        
        if idx < 20 or idx + 20 >= len(chart_df):
            continue
        
        if not calc_revisit_anchor(chart_df, idx):
            continue
        
        micro_unit = classify_micro_unit(chart_df, idx)
        if micro_unit is None or micro_unit == 'Chaos':
            continue
        
        e_dir = calc_e_dir(chart_df, idx)
        e_resp = calc_e_resp(chart_df, idx)
        t_commit = calc_t_commit(chart_df, idx)
        path = calc_path(chart_df, idx)
        
        state_label = build_state_label(micro_unit, e_dir, e_resp, t_commit, path)
        
        samples.append({
            'ts': ts,
            'idx': idx,
            'micro_unit': micro_unit,
            'e_dir': e_dir,
            'e_resp': e_resp,
            't_commit': t_commit,
            'path': path,
            'state_label': state_label
        })
    
    samples.sort(key=lambda x: x['idx'])
    print(f"Labeled samples: {len(samples)}")
    
    print("\n" + "="*70)
    print("COORDINATE DISTRIBUTION")
    print("="*70)
    
    for axis, key in [('E_DIR', 'e_dir'), ('E_RESP', 'e_resp'), 
                       ('T_COMMIT', 't_commit'), ('PATH', 'path')]:
        dist = defaultdict(int)
        for s in samples:
            dist[s[key]] += 1
        print(f"\n{axis}:")
        for val, count in sorted(dist.items()):
            print(f"  {val}: {count} ({count/len(samples)*100:.1f}%)")
    
    print("\n" + "="*70)
    print("MICRO-UNIT DISTRIBUTION")
    print("="*70)
    
    unit_dist = defaultdict(int)
    for s in samples:
        unit_dist[s['micro_unit']] += 1
    
    for unit, count in sorted(unit_dist.items(), key=lambda x: -x[1]):
        print(f"  {unit}: {count}")
    
    print("\n" + "="*70)
    print("TRANSITION EXTRACTION")
    print("="*70)
    
    transitions = []
    min_gap = 3
    max_gap = 20
    
    for i in range(len(samples) - 1):
        for j in range(i + 1, len(samples)):
            gap = samples[j]['idx'] - samples[i]['idx']
            if gap < min_gap:
                continue
            if gap > max_gap:
                break
            
            if samples[i]['micro_unit'] == samples[j]['micro_unit']:
                continue
            
            transitions.append({
                'from': samples[i],
                'to': samples[j],
                'gap': gap
            })
    
    print(f"Total transitions: {len(transitions)}")
    
    print("\n" + "="*70)
    print("TRANSITION PURITY ANALYSIS")
    print("="*70)
    
    coord_axes = ['e_dir', 'e_resp', 't_commit', 'path']
    
    transition_rules = []
    
    unit_pairs = set()
    for t in transitions:
        unit_pairs.add((t['from']['micro_unit'], t['to']['micro_unit']))
    
    for from_unit, to_unit in unit_pairs:
        pair_transitions = [t for t in transitions 
                           if t['from']['micro_unit'] == from_unit 
                           and t['to']['micro_unit'] == to_unit]
        
        if len(pair_transitions) < 3:
            continue
        
        for axis in coord_axes:
            for value in set(t['from'][axis] for t in pair_transitions):
                filtered = [t for t in transitions 
                           if t['from']['micro_unit'] == from_unit
                           and t['from'][axis] == value]
                
                if len(filtered) < 5:
                    continue
                
                to_count = sum(1 for t in filtered if t['to']['micro_unit'] == to_unit)
                not_to_count = len(filtered) - to_count
                
                p_to = to_count / len(filtered) * 100
                p_not = not_to_count / len(filtered) * 100
                purity = p_to - p_not
                
                if purity >= 20 and to_count >= 3:
                    transition_rules.append({
                        'from': from_unit,
                        'to': to_unit,
                        'coord': f"{axis}={value}",
                        'n': to_count,
                        'total': len(filtered),
                        'purity': purity,
                        'pass': purity >= 25 and to_count >= 10
                    })
    
    transition_rules.sort(key=lambda x: -x['purity'])
    
    print("\n| From | To | Coord | N | Purity | Verdict |")
    print("|------|-----|-------|---|--------|---------|")
    
    for rule in transition_rules[:20]:
        verdict = '✅' if rule['pass'] else '⚠️'
        print(f"| {rule['from'][:12]:12} | {rule['to'][:12]:12} | {rule['coord']:15} | {rule['n']:2} | {rule['purity']:+.0f}pp | {verdict} |")
    
    passed_rules = [r for r in transition_rules if r['pass']]
    
    print("\n" + "="*70)
    print("VALIDATED TRANSITION RULES")
    print("="*70)
    
    print(f"\nPassed Rules (Purity≥25pp, N≥10): {len(passed_rules)}")
    for rule in passed_rules:
        print(f"  {rule['from']} → {rule['to']} | {rule['coord']} | N={rule['n']} | +{rule['purity']:.0f}pp")
    
    print("\n" + "="*70)
    print("STATE MACHINE SUMMARY")
    print("="*70)
    
    allowed_transitions = defaultdict(list)
    for rule in passed_rules:
        allowed_transitions[rule['from']].append({
            'to': rule['to'],
            'condition': rule['coord'],
            'purity': rule['purity']
        })
    
    print("\nAllowed Transitions:")
    for from_unit, to_list in sorted(allowed_transitions.items()):
        print(f"\n  {from_unit}:")
        for t in to_list:
            print(f"    → {t['to']} (IF {t['condition']}, +{t['purity']:.0f}pp)")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_MICRO_TRANSITION_COORD_01',
        'total_samples': len(samples),
        'total_transitions': len(transitions),
        'transition_rules': transition_rules,
        'passed_rules': passed_rules,
        'allowed_transitions': dict(allowed_transitions)
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/exp_micro_transition_coord_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_micro_transition_coord_01()
