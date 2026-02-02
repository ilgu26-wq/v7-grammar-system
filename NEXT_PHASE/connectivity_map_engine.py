"""
CONNECTIVITY–MAP ACTION ENGINE (v0)
====================================
This engine does not predict collapse.
It maps state-space density and masks actions in high-collapse regions.

구조:
  [Raw Data] → [Feature Extraction] → [Connectivity State Vector]
            → [Probability Map Lookup] → [ACTION_MASK / SIZE_SCALE]

핵심 원리:
  - 확률 맵은 사후 고정 (freeze)
  - 실시간은 계산 ❌ / 조회 ⭕
  - 판단 없음, 학습 없음, 즉시 실행
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime
import os

RESULT_FILE = "v7-grammar-system/results/connectivity_map_engine_v0.json"
MAP_FILE = "v7-grammar-system/results/connectivity_probability_map_v0.json"

def calc_er(close_series: pd.Series, lookback: int = 10) -> pd.Series:
    result = []
    for i in range(len(close_series)):
        start = max(0, i - lookback + 1)
        window = close_series.iloc[start:i + 1]
        if len(window) < 2:
            result.append(0.5)
            continue
        price_change = abs(window.iloc[-1] - window.iloc[0])
        bar_changes = abs(window.diff().dropna()).sum()
        if bar_changes < 0.01:
            result.append(1.0)
        else:
            result.append(min(1.0, price_change / bar_changes))
    return pd.Series(result, index=close_series.index)

def calc_depth(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    rolling_high = df['high'].rolling(lookback, min_periods=1).max()
    rolling_low = df['low'].rolling(lookback, min_periods=1).min()
    depth = (df['close'] - rolling_low) / (rolling_high - rolling_low + 0.001)
    return depth

def calc_zpoc(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    vol = df['range'].replace(0, 1)
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    zpoc = (typical_price * vol).rolling(lookback, min_periods=1).sum() / vol.rolling(lookback, min_periods=1).sum()
    return zpoc

def resample_to_htf(df: pd.DataFrame, period: int) -> pd.DataFrame:
    htf = pd.DataFrame()
    groups = len(df) // period
    for i in range(groups):
        start = i * period
        end = start + period
        window = df.iloc[start:end]
        htf = pd.concat([htf, pd.DataFrame({
            'open': [window['open'].iloc[0]],
            'high': [window['high'].max()],
            'low': [window['low'].min()],
            'close': [window['close'].iloc[-1]],
            'bar_start': [start],
            'bar_end': [end - 1]
        })], ignore_index=True)
    return htf

def find_ignition_events(df: pd.DataFrame, er_threshold: float = 0.7) -> List[int]:
    events = []
    for i in range(1, len(df)):
        if df['er'].iloc[i] > er_threshold and df['er'].iloc[i-1] < er_threshold:
            events.append(i)
    return events

def check_retouch(df: pd.DataFrame, ignition_idx: int, lookforward: int = 20) -> Tuple[bool, int]:
    if ignition_idx + lookforward >= len(df):
        return False, 0
    entry_er = df['er'].iloc[ignition_idx]
    for i in range(1, lookforward + 1):
        future_idx = ignition_idx + i
        future_er = df['er'].iloc[future_idx]
        if future_er > entry_er * 0.8:
            return True, i
    return False, 0

def check_collapse(df: pd.DataFrame, dwell_end: int, lookforward: int = 10) -> Tuple[bool, str]:
    if dwell_end + lookforward >= len(df):
        return False, "insufficient_data"
    future_window = df.iloc[dwell_end:dwell_end + lookforward + 1]
    min_er = future_window['er'].min()
    if min_er < 0.25:
        return True, "er_collapse"
    er_drop = future_window['er'].iloc[0] - future_window['er'].iloc[-1]
    if er_drop > 0.3:
        return True, "er_degradation"
    return False, "stable"

def compute_connectivity_state(df: pd.DataFrame, bar_idx: int, 
                                htf_5m_ignitions: List[Tuple[int, int]], 
                                htf_15m_ignitions: List[Tuple[int, int]],
                                er_baseline: float, depth_baseline: float,
                                range_q25: float, range_q75: float,
                                tau_q25: float, tau_q75: float,
                                dwell_time: int) -> Dict:
    """Connectivity State Vector 계산"""
    
    htf_5m_alive = any(start - 5 <= bar_idx <= end + 5 for start, end in htf_5m_ignitions)
    htf_15m_alive = any(start - 15 <= bar_idx <= end + 15 for start, end in htf_15m_ignitions)
    htf_alive = 1 if (htf_5m_alive or htf_15m_alive) else 0
    
    current_zpoc = df['zpoc'].iloc[bar_idx]
    ignition_price = df['close'].iloc[bar_idx - dwell_time] if bar_idx >= dwell_time else df['close'].iloc[bar_idx]
    zpoc_distance = abs(current_zpoc - ignition_price)
    price_range = df['range'].iloc[bar_idx] if df['range'].iloc[bar_idx] > 0 else 1
    zpoc_alive = 1 if zpoc_distance < price_range * 3 else 0
    
    current_depth = df['depth'].iloc[bar_idx]
    depth_alive = 1 if abs(current_depth - depth_baseline) < 0.2 else 0
    
    current_er = df['er'].iloc[bar_idx]
    er_alive = 1 if current_er > er_baseline * 0.6 else 0
    
    current_range = df['range'].iloc[bar_idx]
    range_alive = 1 if range_q25 <= current_range <= range_q75 * 1.5 else 0
    
    tau_alive = 1 if tau_q25 <= dwell_time <= tau_q75 * 1.5 else 0
    
    alive_count = htf_alive + zpoc_alive + depth_alive + er_alive + range_alive + tau_alive
    
    return {
        'alive_count': alive_count,
        'zpoc_alive': zpoc_alive,
        'htf_alive': htf_alive
    }

def make_cell_key(state: Dict) -> str:
    """상태 → 셀 키 변환"""
    return f"(alive={state['alive_count']}, zpoc={state['zpoc_alive']}, htf={state['htf_alive']})"

def get_action_mask(collapse_rate: Optional[float]) -> float:
    """ACTION_MASK 규칙 (v0)"""
    if collapse_rate is None:
        return 0.0
    if collapse_rate >= 0.75:
        return 0.0
    elif collapse_rate >= 0.60:
        return 0.5
    else:
        return 1.0

def build_probability_map(events: List[Dict], min_samples: int = 10) -> Dict:
    """Connectivity Probability Map 생성"""
    cell_data = {}
    
    for event in events:
        key = make_cell_key(event)
        if key not in cell_data:
            cell_data[key] = {'N': 0, 'suspended': 0, 'collapsed': 0}
        
        cell_data[key]['N'] += 1
        if event['collapsed']:
            cell_data[key]['collapsed'] += 1
        else:
            cell_data[key]['suspended'] += 1
    
    probability_map = {}
    for key, data in cell_data.items():
        if data['N'] >= min_samples:
            probability_map[key] = {
                'N': data['N'],
                'suspended': data['suspended'],
                'collapsed': data['collapsed'],
                'collapse_rate': round(data['collapsed'] / data['N'], 3),
                'action_mask': get_action_mask(data['collapsed'] / data['N'])
            }
        else:
            probability_map[key] = {
                'N': data['N'],
                'suspended': data['suspended'],
                'collapsed': data['collapsed'],
                'collapse_rate': None,
                'action_mask': 0.0,
                'status': 'UNKNOWN (insufficient samples)'
            }
    
    return probability_map

def evaluate_mask_performance(events: List[Dict], probability_map: Dict) -> Dict:
    """ACTION_MASK 적용 전/후 성능 비교"""
    
    total = len(events)
    collapsed = sum(1 for e in events if e['collapsed'])
    suspended = total - collapsed
    
    blocked = 0
    blocked_collapsed = 0
    blocked_suspended = 0
    
    passed = 0
    passed_collapsed = 0
    passed_suspended = 0
    
    for event in events:
        key = make_cell_key(event)
        cell = probability_map.get(key, {})
        mask = cell.get('action_mask', 0.0)
        
        if mask == 0.0:
            blocked += 1
            if event['collapsed']:
                blocked_collapsed += 1
            else:
                blocked_suspended += 1
        else:
            passed += 1
            if event['collapsed']:
                passed_collapsed += 1
            else:
                passed_suspended += 1
    
    return {
        'before_mask': {
            'total': total,
            'collapsed': collapsed,
            'suspended': suspended,
            'collapse_rate': round(collapsed / total, 3) if total > 0 else 0
        },
        'after_mask': {
            'blocked': blocked,
            'blocked_collapsed': blocked_collapsed,
            'blocked_suspended': blocked_suspended,
            'passed': passed,
            'passed_collapsed': passed_collapsed,
            'passed_suspended': passed_suspended,
            'new_collapse_rate': round(passed_collapsed / passed, 3) if passed > 0 else 0
        },
        'mask_efficiency': {
            'collapse_blocked_rate': round(blocked_collapsed / collapsed, 3) if collapsed > 0 else 0,
            'suspended_blocked_rate': round(blocked_suspended / suspended, 3) if suspended > 0 else 0,
            'net_improvement': round((collapsed / total) - (passed_collapsed / passed), 3) if passed > 0 and total > 0 else 0
        }
    }

def run_engine(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("CONNECTIVITY–MAP ACTION ENGINE (v0)")
    print("=" * 70)
    
    print("\n[1] Computing base metrics...")
    df['range'] = df['high'] - df['low']
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['zpoc'] = calc_zpoc(df)
    
    range_q25 = df['range'].quantile(0.25)
    range_q75 = df['range'].quantile(0.75)
    
    print("\n[2] Computing HTF structure...")
    htf_5m = resample_to_htf(df, 5)
    htf_15m = resample_to_htf(df, 15)
    htf_5m['er'] = calc_er(htf_5m['close'])
    htf_15m['er'] = calc_er(htf_15m['close'])
    
    ignitions_5m_idx = find_ignition_events(htf_5m, er_threshold=0.7)
    ignitions_15m_idx = find_ignition_events(htf_15m, er_threshold=0.7)
    
    htf_5m_ignitions = [(int(htf_5m.iloc[i]['bar_start']), int(htf_5m.iloc[i]['bar_end'])) 
                        for i in ignitions_5m_idx if i < len(htf_5m)]
    htf_15m_ignitions = [(int(htf_15m.iloc[i]['bar_start']), int(htf_15m.iloc[i]['bar_end'])) 
                         for i in ignitions_15m_idx if i < len(htf_15m)]
    
    print("\n[3] Collecting events with connectivity states...")
    ignitions_1m = find_ignition_events(df, er_threshold=0.7)
    
    recoverable_events = []
    for idx in ignitions_1m:
        retouch, dwell = check_retouch(df, idx)
        if retouch:
            recoverable_events.append((idx, dwell))
    
    all_dwells = [d for _, d in recoverable_events]
    tau_q25 = np.percentile(all_dwells, 25) if all_dwells else 1
    tau_q75 = np.percentile(all_dwells, 75) if all_dwells else 10
    
    events = []
    
    for ignition_idx, dwell_time in recoverable_events:
        dwell_end = ignition_idx + dwell_time
        
        if dwell_end >= len(df):
            continue
        
        pre_ignition_idx = max(0, ignition_idx - 5)
        er_baseline = df['er'].iloc[pre_ignition_idx:ignition_idx].mean()
        depth_baseline = df['depth'].iloc[pre_ignition_idx:ignition_idx].mean()
        
        state = compute_connectivity_state(
            df, dwell_end, htf_5m_ignitions, htf_15m_ignitions,
            er_baseline, depth_baseline, range_q25, range_q75, tau_q25, tau_q75, dwell_time
        )
        
        did_collapse, _ = check_collapse(df, dwell_end)
        
        events.append({
            'ignition_idx': ignition_idx,
            'dwell_end': dwell_end,
            'collapsed': did_collapse,
            **state
        })
    
    print(f"  Total events: {len(events)}")
    print(f"  Collapsed: {sum(1 for e in events if e['collapsed'])}")
    print(f"  Suspended: {sum(1 for e in events if not e['collapsed'])}")
    
    print("\n[4] Building Connectivity Probability Map...")
    probability_map = build_probability_map(events, min_samples=10)
    
    print("\n" + "=" * 70)
    print("CONNECTIVITY PROBABILITY MAP")
    print("=" * 70)
    
    sorted_cells = sorted(probability_map.items(), 
                         key=lambda x: (x[1].get('collapse_rate') or 1.0), 
                         reverse=True)
    
    print(f"\n{'Cell':<35} {'N':>5} {'CR':>6} {'MASK':>5}")
    print("-" * 55)
    
    for key, data in sorted_cells:
        cr = data.get('collapse_rate')
        cr_str = f"{cr:.1%}" if cr is not None else "N/A"
        mask = data.get('action_mask', 0)
        print(f"{key:<35} {data['N']:>5} {cr_str:>6} {mask:>5.1f}")
    
    print("\n[5] Evaluating ACTION_MASK performance...")
    performance = evaluate_mask_performance(events, probability_map)
    
    print("\n" + "=" * 70)
    print("ACTION_MASK PERFORMANCE")
    print("=" * 70)
    
    before = performance['before_mask']
    after = performance['after_mask']
    eff = performance['mask_efficiency']
    
    print(f"\n[BEFORE MASK]")
    print(f"  Total events: {before['total']}")
    print(f"  Collapse rate: {before['collapse_rate']:.1%}")
    
    print(f"\n[AFTER MASK]")
    print(f"  Blocked: {after['blocked']} ({after['blocked_collapsed']} collapsed, {after['blocked_suspended']} suspended)")
    print(f"  Passed: {after['passed']} ({after['passed_collapsed']} collapsed, {after['passed_suspended']} suspended)")
    print(f"  New collapse rate: {after['new_collapse_rate']:.1%}")
    
    print(f"\n[MASK EFFICIENCY]")
    print(f"  Collapse blocked: {eff['collapse_blocked_rate']:.1%} of all collapses")
    print(f"  Suspended blocked: {eff['suspended_blocked_rate']:.1%} of all suspended (false positive)")
    print(f"  Net improvement: {eff['net_improvement']:+.1%}")
    
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    
    if eff['net_improvement'] >= 0.05:
        print("\n  ✓ ACTION_MASK 효과적")
        print(f"    붕괴율 {eff['net_improvement']:.1%} 감소")
        verdict = "EFFECTIVE"
    elif eff['net_improvement'] > 0:
        print("\n  ~ ACTION_MASK 약한 효과")
        verdict = "WEAK_EFFECT"
    else:
        print("\n  ✗ ACTION_MASK 효과 없음")
        verdict = "NO_EFFECT"
    
    print("\n" + "=" * 70)
    
    results = {
        'engine': 'CONNECTIVITY-MAP-ACTION-ENGINE-v0',
        'timestamp': datetime.now().isoformat(),
        'total_bars': len(df),
        'total_events': len(events),
        'probability_map': probability_map,
        'performance': performance,
        'verdict': verdict
    }
    
    return results

def main():
    data_files = [
        "data/mnq_december_2025.csv",
        "data/mnq_with_ratio.csv"
    ]
    
    df = None
    for path in data_files:
        if os.path.exists(path):
            print(f"Loading data from: {path}")
            df = pd.read_csv(path)
            break
    
    if df is None:
        print("ERROR: No data file found")
        return
    
    df.columns = df.columns.str.lower()
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    print(f"Loaded {len(df)} bars")
    
    results = run_engine(df)
    
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {RESULT_FILE}")
    
    with open(MAP_FILE, 'w') as f:
        json.dump(results['probability_map'], f, indent=2)
    print(f"Probability map saved to: {MAP_FILE}")

if __name__ == "__main__":
    main()
