"""
EXP-BUCKET2-DISSECTION-01: ECS=2 지뢰핵 서브셀 해부
====================================================
목표: 100% collapse인 Bucket2의 원인을 찾아 하드 차단 룰로 승격

가설: ECS=2는 "ZPOC alive + HTF alive" 과결속 조합

룰 후보:
  R1: htf_alive==1 AND alive_count>=5 → KILL
  R2: zpoc_alive==1 AND htf_alive==1 AND recovery_contradiction==1 → KILL
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

RESULT_FILE = "v7-grammar-system/results/exp_bucket2_dissection_01.json"

WEIGHTS = {
    'zpoc_alive': 2.0,
    'htf_alive': -1.5,
    'range_alive': 1.0,
    'depth_alive': 0.8,
    'tau_alive': 0.5,
    'er_alive': 0.3
}

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
    return (df['close'] - rolling_low) / (rolling_high - rolling_low + 0.001)

def calc_zpoc(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    vol = df['range'].replace(0, 1)
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * vol).rolling(lookback, min_periods=1).sum() / vol.rolling(lookback, min_periods=1).sum()

def resample_to_htf(df: pd.DataFrame, period: int) -> pd.DataFrame:
    htf = []
    for i in range(len(df) // period):
        start, end = i * period, (i + 1) * period
        window = df.iloc[start:end]
        htf.append({
            'open': window['open'].iloc[0],
            'high': window['high'].max(),
            'low': window['low'].min(),
            'close': window['close'].iloc[-1],
            'bar_start': start,
            'bar_end': end - 1
        })
    return pd.DataFrame(htf)

def find_ignition_events(df: pd.DataFrame, er_threshold: float = 0.7) -> List[int]:
    return [i for i in range(1, len(df)) 
            if df['er'].iloc[i] > er_threshold and df['er'].iloc[i-1] < er_threshold]

def check_strict_retouch(df: pd.DataFrame, ignition_idx: int, lookforward: int = 20) -> Tuple[bool, int, Dict]:
    if ignition_idx + lookforward >= len(df):
        return False, 0, {}
    
    pre_idx = max(0, ignition_idx - 5)
    baseline_er = df['er'].iloc[pre_idx:ignition_idx].mean()
    baseline_depth = df['depth'].iloc[pre_idx:ignition_idx].mean()
    ignition_price = df['close'].iloc[ignition_idx]
    price_band = df['range'].iloc[ignition_idx] * 2
    
    for i in range(1, lookforward + 1):
        idx = ignition_idx + i
        price_ok = abs(df['close'].iloc[idx] - ignition_price) < price_band
        depth_ok = abs(df['depth'].iloc[idx] - baseline_depth) < 0.15
        er_ok = df['er'].iloc[idx] > baseline_er * 0.7
        
        if price_ok and depth_ok and er_ok:
            return True, i, {'price': True, 'depth': True, 'er': True}
        
        if price_ok and not depth_ok:
            return True, i, {'price': True, 'depth': False, 'er': er_ok}
    
    return False, 0, {}

def check_hard_collapse(df: pd.DataFrame, dwell_end: int, ignition_price: float, lookforward: int = 30) -> bool:
    if dwell_end + lookforward >= len(df):
        return False
    
    future = df.iloc[dwell_end:dwell_end + lookforward + 1]
    
    c1 = future['er'].min() < 0.20
    c2 = (future['er'].iloc[0] - future['er'].min()) > 0.40
    
    band = df['range'].iloc[dwell_end] * 3
    no_recovery = sum(1 for i in range(len(future)) if abs(future['close'].iloc[i] - ignition_price) > band)
    c3 = no_recovery >= lookforward * 0.8
    
    return sum([c1, c2, c3]) >= 2

def compute_full_state(df: pd.DataFrame, bar_idx: int, 
                       htf_5m_ign: List[Tuple], htf_15m_ign: List[Tuple],
                       er_base: float, depth_base: float,
                       range_q25: float, range_q75: float,
                       tau_q25: float, tau_q75: float,
                       dwell: int, retouch_info: Dict) -> Dict:
    
    htf_5m = any(s - 5 <= bar_idx <= e + 5 for s, e in htf_5m_ign)
    htf_15m = any(s - 15 <= bar_idx <= e + 15 for s, e in htf_15m_ign)
    htf_alive = 1 if (htf_5m or htf_15m) else 0
    
    ign_price = df['close'].iloc[bar_idx - dwell] if bar_idx >= dwell else df['close'].iloc[bar_idx]
    zpoc_dist = abs(df['zpoc'].iloc[bar_idx] - ign_price)
    price_range = max(df['range'].iloc[bar_idx], 1)
    zpoc_alive = 1 if zpoc_dist < price_range * 3 else 0
    
    depth_alive = 1 if abs(df['depth'].iloc[bar_idx] - depth_base) < 0.2 else 0
    er_alive = 1 if df['er'].iloc[bar_idx] > er_base * 0.6 else 0
    range_alive = 1 if range_q25 <= df['range'].iloc[bar_idx] <= range_q75 * 1.5 else 0
    tau_alive = 1 if tau_q25 <= dwell <= tau_q75 * 1.5 else 0
    
    nodes = {
        'htf_alive': htf_alive, 'zpoc_alive': zpoc_alive, 'depth_alive': depth_alive,
        'er_alive': er_alive, 'range_alive': range_alive, 'tau_alive': tau_alive
    }
    
    alive_count = sum(nodes.values())
    ecs = sum(WEIGHTS[k] * v for k, v in nodes.items())
    
    penalty = 0
    if alive_count >= 5 and htf_alive == 1:
        penalty = 1.5
    elif alive_count >= 6:
        penalty = 1.0
    
    recovery_contradiction = 0
    if retouch_info.get('price', False) and not retouch_info.get('depth', True):
        recovery_contradiction = 1
    
    return {
        'alive_count': alive_count,
        'ecs': round(ecs, 2),
        'ecs_penalized': round(ecs - penalty, 2),
        'ecs_bucket': int(ecs - penalty),
        'recovery_contradiction': recovery_contradiction,
        **nodes
    }

def test_rule(events: List[Dict], rule_fn, rule_name: str) -> Dict:
    """룰을 테스트하고 성능 측정"""
    
    bucket2 = [e for e in events if e['ecs_bucket'] == 2]
    bucket2_killed = sum(1 for e in bucket2 if rule_fn(e))
    bucket2_coverage = bucket2_killed / len(bucket2) if bucket2 else 0
    
    all_collapsed = sum(1 for e in events if e['collapsed'])
    all_suspended = len(events) - all_collapsed
    
    killed_collapsed = sum(1 for e in events if rule_fn(e) and e['collapsed'])
    killed_suspended = sum(1 for e in events if rule_fn(e) and not e['collapsed'])
    
    fp_rate = killed_suspended / all_suspended if all_suspended > 0 else 0
    
    passed = [e for e in events if not rule_fn(e)]
    passed_collapsed = sum(1 for e in passed if e['collapsed'])
    new_cr = passed_collapsed / len(passed) if passed else 0
    
    original_cr = all_collapsed / len(events) if events else 0
    
    return {
        'rule_name': rule_name,
        'bucket2_total': len(bucket2),
        'bucket2_killed': bucket2_killed,
        'bucket2_coverage': round(bucket2_coverage, 3),
        'total_killed': bucket2_killed + sum(1 for e in events if e['ecs_bucket'] != 2 and rule_fn(e)),
        'killed_collapsed': killed_collapsed,
        'killed_suspended': killed_suspended,
        'fp_rate': round(fp_rate, 3),
        'original_cr': round(original_cr, 3),
        'new_cr': round(new_cr, 3),
        'improvement': round(original_cr - new_cr, 3)
    }

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-BUCKET2-DISSECTION-01")
    print("ECS=2 지뢰핵 서브셀 해부")
    print("=" * 70)
    
    print("\n[1] Computing metrics...")
    df['range'] = df['high'] - df['low']
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['zpoc'] = calc_zpoc(df)
    
    range_q25, range_q75 = df['range'].quantile(0.25), df['range'].quantile(0.75)
    
    print("\n[2] Computing HTF...")
    htf_5m = resample_to_htf(df, 5)
    htf_15m = resample_to_htf(df, 15)
    htf_5m['er'] = calc_er(htf_5m['close'])
    htf_15m['er'] = calc_er(htf_15m['close'])
    
    ign_5m = [(int(htf_5m.iloc[i]['bar_start']), int(htf_5m.iloc[i]['bar_end'])) 
              for i in find_ignition_events(htf_5m) if i < len(htf_5m)]
    ign_15m = [(int(htf_15m.iloc[i]['bar_start']), int(htf_15m.iloc[i]['bar_end'])) 
               for i in find_ignition_events(htf_15m) if i < len(htf_15m)]
    
    print("\n[3] Collecting events...")
    ignitions = find_ignition_events(df)
    
    strict_events = []
    for idx in ignitions:
        ok, dwell, info = check_strict_retouch(df, idx)
        if ok:
            strict_events.append((idx, dwell, info))
    
    dwells = [d for _, d, _ in strict_events]
    tau_q25 = np.percentile(dwells, 25) if dwells else 1
    tau_q75 = np.percentile(dwells, 75) if dwells else 10
    
    events = []
    for ign_idx, dwell, retouch_info in strict_events:
        dwell_end = ign_idx + dwell
        if dwell_end >= len(df):
            continue
        
        ign_price = df['close'].iloc[ign_idx]
        pre_idx = max(0, ign_idx - 5)
        er_base = df['er'].iloc[pre_idx:ign_idx].mean()
        depth_base = df['depth'].iloc[pre_idx:ign_idx].mean()
        
        state = compute_full_state(
            df, dwell_end, ign_5m, ign_15m,
            er_base, depth_base, range_q25, range_q75, tau_q25, tau_q75, dwell, retouch_info
        )
        
        is_collapse = check_hard_collapse(df, dwell_end, ign_price)
        events.append({'ignition_idx': ign_idx, 'collapsed': is_collapse, **state})
    
    total = len(events)
    collapsed = sum(1 for e in events if e['collapsed'])
    print(f"  Total: {total}, Collapsed: {collapsed} ({collapsed/total:.1%})")
    
    bucket2 = [e for e in events if e['ecs_bucket'] == 2]
    print(f"\n[4] Bucket2 분석 (N={len(bucket2)})...")
    
    print("\n" + "=" * 70)
    print("TABLE A: Bucket2 구성표")
    print("=" * 70)
    
    table_a = {}
    for e in bucket2:
        key = (e['zpoc_alive'], e['htf_alive'], e['alive_count'])
        if key not in table_a:
            table_a[key] = {'N': 0, 'collapsed': 0}
        table_a[key]['N'] += 1
        if e['collapsed']:
            table_a[key]['collapsed'] += 1
    
    print(f"\n{'(zpoc, htf, alive)':<25} {'N':>6} {'CR':>8}")
    print("-" * 45)
    for key in sorted(table_a.keys()):
        data = table_a[key]
        cr = data['collapsed'] / data['N'] if data['N'] > 0 else 0
        print(f"{str(key):<25} {data['N']:>6} {cr:>7.1%}")
    
    print("\n" + "=" * 70)
    print("TABLE B: alive_count별 보조노드 분포")
    print("=" * 70)
    
    table_b = {}
    for e in bucket2:
        ac = e['alive_count']
        if ac not in table_b:
            table_b[ac] = {'N': 0, 'range': 0, 'tau': 0, 'depth': 0, 'recovery_c': 0}
        table_b[ac]['N'] += 1
        table_b[ac]['range'] += e['range_alive']
        table_b[ac]['tau'] += e['tau_alive']
        table_b[ac]['depth'] += e['depth_alive']
        table_b[ac]['recovery_c'] += e['recovery_contradiction']
    
    print(f"\n{'alive':<8} {'N':>5} {'range%':>8} {'tau%':>8} {'depth%':>8} {'recov_c%':>10}")
    print("-" * 55)
    for ac in sorted(table_b.keys()):
        d = table_b[ac]
        print(f"{ac:<8} {d['N']:>5} {d['range']/d['N']:>7.1%} {d['tau']/d['N']:>7.1%} "
              f"{d['depth']/d['N']:>7.1%} {d['recovery_c']/d['N']:>9.1%}")
    
    print("\n[5] 룰 테스트...")
    
    def rule_R1(e):
        return e['htf_alive'] == 1 and e['alive_count'] >= 5
    
    def rule_R2(e):
        return e['zpoc_alive'] == 1 and e['htf_alive'] == 1 and e['recovery_contradiction'] == 1
    
    def rule_R3(e):
        return e['htf_alive'] == 1 and e['alive_count'] >= 4
    
    def rule_R4(e):
        return e['ecs_bucket'] == 2
    
    def rule_R5(e):
        return e['zpoc_alive'] == 0 and e['alive_count'] >= 4
    
    def rule_R6(e):
        return e['zpoc_alive'] == 0
    
    def rule_R7(e):
        return e['zpoc_alive'] == 0 and e['alive_count'] >= 3
    
    rules = [
        (rule_R1, "R1: htf=1 & alive>=5"),
        (rule_R2, "R2: zpoc=1 & htf=1 & recovery_c=1"),
        (rule_R3, "R3: htf=1 & alive>=4"),
        (rule_R4, "R4: ECS_bucket==2 (hard kill)"),
        (rule_R5, "R5: zpoc=0 & alive>=4"),
        (rule_R6, "R6: zpoc=0 (all)"),
        (rule_R7, "R7: zpoc=0 & alive>=3")
    ]
    
    print("\n" + "=" * 70)
    print("TABLE C: 룰 평가")
    print("=" * 70)
    
    rule_results = []
    print(f"\n{'Rule':<35} {'B2_cov':>8} {'FP':>8} {'Impr':>8}")
    print("-" * 65)
    
    for fn, name in rules:
        result = test_rule(events, fn, name)
        rule_results.append(result)
        print(f"{name:<35} {result['bucket2_coverage']:>7.1%} {result['fp_rate']:>7.1%} {result['improvement']:>+7.1%}")
    
    print("\n" + "=" * 70)
    print("VERDICT & 채택")
    print("=" * 70)
    
    best_rule = None
    for r in rule_results:
        if r['bucket2_coverage'] >= 0.70 and r['fp_rate'] <= 0.15 and r['improvement'] >= 0.05:
            if best_rule is None or r['improvement'] > best_rule['improvement']:
                best_rule = r
    
    if best_rule:
        print(f"\n  ✓ 채택: {best_rule['rule_name']}")
        print(f"    - Bucket2 커버리지: {best_rule['bucket2_coverage']:.1%}")
        print(f"    - False Positive: {best_rule['fp_rate']:.1%}")
        print(f"    - 붕괴율 개선: {best_rule['improvement']:+.1%}")
        verdict = f"ADOPT_{best_rule['rule_name'].split(':')[0]}"
    else:
        print("\n  ⚠ 기준 충족 룰 없음 - 임계값 완화 또는 추가 분석 필요")
        best_result = max(rule_results, key=lambda x: x['improvement'])
        print(f"  → 최선: {best_result['rule_name']} (개선 {best_result['improvement']:+.1%})")
        verdict = "NO_CLEAR_WINNER"
    
    print("\n" + "=" * 70)
    
    return {
        'experiment': 'EXP-BUCKET2-DISSECTION-01',
        'timestamp': datetime.now().isoformat(),
        'total_events': total,
        'bucket2_count': len(bucket2),
        'table_a': {str(k): v for k, v in table_a.items()},
        'table_b': table_b,
        'rule_results': rule_results,
        'verdict': verdict,
        'best_rule': best_rule
    }

def main():
    for path in ["data/mnq_december_2025.csv", "data/mnq_with_ratio.csv"]:
        if os.path.exists(path):
            print(f"Loading: {path}")
            df = pd.read_csv(path)
            break
    else:
        print("ERROR: No data")
        return
    
    df.columns = df.columns.str.lower()
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    print(f"Loaded {len(df)} bars")
    
    results = run_experiment(df)
    
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
