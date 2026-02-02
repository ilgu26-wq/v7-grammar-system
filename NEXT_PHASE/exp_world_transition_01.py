"""
EXP-WORLD-TRANSITION-01: 세계 전이 법칙 (World Transition Law)
================================================================
목적: "STABLE_BASIN이 언제, 어떤 경로로 무너지는가"를
      확률이 아니라 구조 전이 규칙으로 고정

핵심:
  - 전이 행렬: P(next_state | current_state)
  - 원인 조건부: P(next_state | current_state, trigger)
  - 체류 시간 분포
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_world_transition_01.json"

WINDOW_PRE = 5
WINDOW_POST = 5

ECS_WEIGHTS = {
    'zpoc_alive': 2.0, 'htf_alive': -1.5, 'tau_alive': 0.6,
    'state_stable': 0.5, 'range_alive': 0.3,
    'recovery': -0.8, 'er_alive': -0.5, 'depth_alive': -0.3
}

STATES = ['STABLE_BASIN', 'TRANSITION_ZONE', 'RUPTURE_RIDGE', 'NOISE_FIELD']
STATE_IDX = {s: i for i, s in enumerate(STATES)}

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
        result.append(min(1.0, price_change / max(bar_changes, 0.01)))
    return pd.Series(result, index=close_series.index)

def calc_depth(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    rolling_high = df['high'].rolling(lookback, min_periods=1).max()
    rolling_low = df['low'].rolling(lookback, min_periods=1).min()
    return (df['close'] - rolling_low) / (rolling_high - rolling_low + 0.001)

def calc_zpoc(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    vol = df['range'].replace(0, 1)
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * vol).rolling(lookback, min_periods=1).sum() / vol.rolling(lookback, min_periods=1).sum()

def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['range'] = df['high'] - df['low']
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['zpoc'] = calc_zpoc(df)
    
    range_q25, range_q75 = df['range'].quantile(0.25), df['range'].quantile(0.75)
    er_median = df['er'].median()
    depth_median = df['depth'].median()
    
    zpoc_distance = abs(df['zpoc'] - df['close'])
    zpoc_threshold = df['range'].rolling(20, min_periods=1).mean() * 3
    df['zpoc_alive'] = (zpoc_distance < zpoc_threshold).astype(int)
    df['depth_alive'] = (abs(df['depth'] - depth_median) < 0.3).astype(int)
    df['er_alive'] = (df['er'] > er_median * 0.5).astype(int)
    df['range_alive'] = ((df['range'] >= range_q25) & (df['range'] <= range_q75 * 2)).astype(int)
    
    er_change = df['er'].diff(5).abs()
    df['tau_alive'] = (er_change < 0.3).astype(int)
    
    df['htf_alive'] = 0
    for period in [5, 15]:
        htf_er = df['er'].rolling(period, min_periods=1).mean()
        df['htf_alive'] = df['htf_alive'] | (htf_er > 0.6).astype(int)
    
    df['recovery'] = ((df['er'].shift(3) < 0.3) & (df['er'] > 0.5)).astype(int)
    df['state_stable'] = (df['er'].diff().abs() < 0.1).astype(int)
    
    df['price_change'] = df['close'].diff().abs()
    df['force_flux'] = df['price_change'] * df['range']
    df['force_flux'] = df['force_flux'].rolling(5, min_periods=1).mean()
    
    df['ecs'] = (
        ECS_WEIGHTS['zpoc_alive'] * df['zpoc_alive'] +
        ECS_WEIGHTS['htf_alive'] * df['htf_alive'] +
        ECS_WEIGHTS['tau_alive'] * df['tau_alive'] +
        ECS_WEIGHTS['state_stable'] * df['state_stable'] +
        ECS_WEIGHTS['range_alive'] * df['range_alive'] +
        ECS_WEIGHTS['recovery'] * df['recovery'] +
        ECS_WEIGHTS['er_alive'] * df['er_alive'] +
        ECS_WEIGHTS['depth_alive'] * df['depth_alive']
    )
    
    resistance = 1.0 + 2.0 * (1 - df['zpoc_alive']) + 0.5 * df['htf_alive'] + 1.0 * df['recovery']
    pg = df['force_flux'] / (df['ecs'] + 2.0).clip(lower=0.1)
    df['ri'] = pg * resistance
    
    return df

def compute_ie(df: pd.DataFrame, idx: int) -> float:
    start = max(0, idx - WINDOW_PRE)
    end = min(len(df), idx + WINDOW_POST + 1)
    window = df.iloc[start:end]
    
    if len(window) < 3:
        return 0.0
    
    fields = [
        window['zpoc_alive'].mean(),
        window['htf_alive'].mean(),
        window['er'].mean() * (1 - window['er'].std()),
        1.0 - min(1.0, window['depth'].std() * 3),
        window['tau_alive'].mean(),
        max(0, 1.0 - window['range'].std() / max(window['range'].mean(), 0.01)),
        min(1.0, window['recovery'].sum()),
        window['state_stable'].mean()
    ]
    
    ie = sum(fields) - np.var(fields)
    
    if fields[0] < 0.3 and fields[2] > 0.6:
        ie -= 1.0
    if fields[0] < 0.3 and sum(fields) > 4.0:
        ie -= 1.5
    
    return ie

def classify_world_state(ie: float, ri: float, ecs: float, zpoc: int, ri_q75: float, ri_q90: float) -> str:
    if zpoc == 0 or ri > ri_q90:
        return 'RUPTURE_RIDGE'
    
    if ie < 2.0 or ie > 4.5 or ecs < 0:
        return 'NOISE_FIELD'
    
    if 2.3 <= ie <= 3.8 and ri < ri_q75 and ecs > 1.0 and zpoc == 1:
        return 'STABLE_BASIN'
    
    if 2.0 <= ie <= 4.5 and ri < ri_q90:
        return 'TRANSITION_ZONE'
    
    return 'NOISE_FIELD'

def detect_triggers(df: pd.DataFrame, idx: int, ri_q90: float, ri_q95: float) -> List[str]:
    triggers = []
    
    if df['ri'].iloc[idx] > ri_q95:
        triggers.append('RI_SPIKE')
    
    if idx >= 2:
        if all(df['ri'].iloc[idx-2:idx+1] > ri_q90):
            triggers.append('RI_PLATEAU_90')
    
    if idx >= 1 and df['zpoc_alive'].iloc[idx-1] == 1 and df['zpoc_alive'].iloc[idx] == 0:
        triggers.append('ZPOC_DEATH')
    
    if idx >= 1:
        ie_prev = compute_ie(df, idx - 1)
        ie_curr = compute_ie(df, idx)
        if 2.3 <= ie_prev <= 3.8 and (ie_curr < 2.3 or ie_curr > 3.8):
            triggers.append('IE_EXIT')
    
    if idx >= 1:
        ecs_delta = df['ecs'].iloc[idx] - df['ecs'].iloc[idx-1]
        if ecs_delta < -1.0:
            triggers.append('ECS_DROP')
    
    return triggers if triggers else ['NONE']

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-WORLD-TRANSITION-01")
    print("세계 전이 법칙 (World Transition Law)")
    print("=" * 70)
    
    print("\n[1] Computing indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q90 = df['ri'].quantile(0.90)
    ri_q95 = df['ri'].quantile(0.95)
    
    print(f"  RI: q75={ri_q75:.2f}, q90={ri_q90:.2f}, q95={ri_q95:.2f}")
    
    print("\n[2] Assigning world states...")
    
    states = []
    ie_list = []
    for idx in range(len(df)):
        ie = compute_ie(df, idx)
        ie_list.append(ie)
        state = classify_world_state(ie, df['ri'].iloc[idx], df['ecs'].iloc[idx], 
                                    df['zpoc_alive'].iloc[idx], ri_q75, ri_q90)
        states.append(state)
    
    df['ie'] = ie_list
    df['world_state'] = states
    
    state_counts = pd.Series(states).value_counts()
    print("  State distribution:")
    for s in STATES:
        print(f"    {s}: {state_counts.get(s, 0)} ({state_counts.get(s, 0)/len(df)*100:.1f}%)")
    
    print("\n[3] Computing transition matrix...")
    
    trans_matrix = np.zeros((4, 4))
    trans_count = np.zeros((4, 4))
    
    for i in range(1, len(df)):
        prev_state = df['world_state'].iloc[i-1]
        curr_state = df['world_state'].iloc[i]
        
        prev_idx = STATE_IDX[prev_state]
        curr_idx = STATE_IDX[curr_state]
        
        trans_count[prev_idx, curr_idx] += 1
    
    for i in range(4):
        row_sum = trans_count[i].sum()
        if row_sum > 0:
            trans_matrix[i] = trans_count[i] / row_sum
    
    print("\n  Basic Transition Matrix P(next | current):")
    print("  " + " " * 20 + " ".join([f"{s[:8]:>10}" for s in STATES]))
    for i, s in enumerate(STATES):
        row = " ".join([f"{trans_matrix[i,j]*100:>9.1f}%" for j in range(4)])
        print(f"  {s:<20} {row}")
    
    print("\n[4] Computing trigger-conditional transitions...")
    
    trigger_trans = {}
    trigger_names = ['RI_SPIKE', 'RI_PLATEAU_90', 'ZPOC_DEATH', 'IE_EXIT', 'ECS_DROP', 'NONE']
    
    for trigger in trigger_names:
        trigger_trans[trigger] = {'STABLE→RUPTURE': 0, 'STABLE→TRANSITION': 0, 
                                  'total_from_stable': 0, 'instances': 0}
    
    for i in range(1, len(df)):
        prev_state = df['world_state'].iloc[i-1]
        curr_state = df['world_state'].iloc[i]
        
        triggers = detect_triggers(df, i, ri_q90, ri_q95)
        
        for trigger in triggers:
            trigger_trans[trigger]['instances'] += 1
            
            if prev_state == 'STABLE_BASIN':
                trigger_trans[trigger]['total_from_stable'] += 1
                
                if curr_state == 'RUPTURE_RIDGE':
                    trigger_trans[trigger]['STABLE→RUPTURE'] += 1
                elif curr_state == 'TRANSITION_ZONE':
                    trigger_trans[trigger]['STABLE→TRANSITION'] += 1
    
    print("\n  Trigger-Conditional: P(STABLE → X | trigger)")
    print("  " + "-" * 70)
    
    key_findings = {}
    for trigger in trigger_names:
        t = trigger_trans[trigger]
        total = t['total_from_stable']
        if total > 10:
            p_rupture = t['STABLE→RUPTURE'] / total
            p_trans = t['STABLE→TRANSITION'] / total
            print(f"  {trigger:<15}: →RUPTURE {p_rupture:5.1%}, →TRANSITION {p_trans:5.1%} (n={total})")
            key_findings[trigger] = {'p_rupture': p_rupture, 'p_transition': p_trans, 'n': total}
    
    print("\n[5] Computing dwell times...")
    
    dwell_times = {s: [] for s in STATES}
    current_state = df['world_state'].iloc[0]
    dwell_count = 1
    
    for i in range(1, len(df)):
        if df['world_state'].iloc[i] == current_state:
            dwell_count += 1
        else:
            dwell_times[current_state].append(dwell_count)
            current_state = df['world_state'].iloc[i]
            dwell_count = 1
    
    dwell_times[current_state].append(dwell_count)
    
    print("\n  Dwell Time Statistics (bars):")
    print("  " + "-" * 50)
    dwell_stats = {}
    for s in STATES:
        times = dwell_times[s]
        if times:
            mean_t = np.mean(times)
            std_t = np.std(times)
            median_t = np.median(times)
            max_t = np.max(times)
            print(f"  {s:<20}: mean={mean_t:5.1f}, median={median_t:4.0f}, max={max_t:4.0f}, std={std_t:5.1f}")
            dwell_stats[s] = {'mean': mean_t, 'median': median_t, 'max': max_t, 'std': std_t}
    
    print("\n" + "=" * 70)
    print("TRANSITION LAW DISCOVERY")
    print("=" * 70)
    
    base_rupture = trans_matrix[STATE_IDX['STABLE_BASIN'], STATE_IDX['RUPTURE_RIDGE']]
    
    print(f"\n  Baseline P(STABLE → RUPTURE): {base_rupture:.1%}")
    
    print("\n  Trigger Amplification (RI_SPIKE / ZPOC_DEATH):")
    if 'RI_SPIKE' in key_findings:
        spike_rupture = key_findings['RI_SPIKE']['p_rupture']
        amp = spike_rupture / max(base_rupture, 0.001)
        print(f"    RI_SPIKE: {spike_rupture:.1%} (×{amp:.1f} baseline)")
    
    if 'ZPOC_DEATH' in key_findings:
        zpoc_rupture = key_findings['ZPOC_DEATH']['p_rupture']
        amp = zpoc_rupture / max(base_rupture, 0.001)
        print(f"    ZPOC_DEATH: {zpoc_rupture:.1%} (×{amp:.1f} baseline)")
    
    none_trigger = key_findings.get('NONE', {})
    random_ratio = none_trigger.get('p_rupture', 0) if none_trigger else 0
    
    print(f"\n  Random (no trigger) → RUPTURE: {random_ratio:.1%}")
    print(f"  Non-random transition rate: {1 - random_ratio:.1%}")
    
    success = random_ratio < 0.20
    print(f"\n  Success criterion (random < 20%): {'✓ PASS' if success else '✗ FAIL'}")
    
    return {
        'experiment': 'EXP-WORLD-TRANSITION-01',
        'timestamp': datetime.now().isoformat(),
        'transition_matrix': trans_matrix.tolist(),
        'trigger_findings': key_findings,
        'dwell_stats': dwell_stats,
        'success': success
    }, df, trans_matrix

def create_visualizations(results: Dict, df: pd.DataFrame, trans_matrix: np.ndarray, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    
    ax1 = axes[0, 0]
    im = ax1.imshow(trans_matrix * 100, cmap='YlOrRd', aspect='auto')
    ax1.set_xticks(range(4))
    ax1.set_yticks(range(4))
    ax1.set_xticklabels([s[:8] for s in STATES], rotation=45, ha='right')
    ax1.set_yticklabels([s[:8] for s in STATES])
    ax1.set_xlabel('Next State')
    ax1.set_ylabel('Current State')
    ax1.set_title('Transition Matrix P(next | current) %')
    
    for i in range(4):
        for j in range(4):
            ax1.text(j, i, f'{trans_matrix[i,j]*100:.1f}%', ha='center', va='center', fontsize=9)
    
    plt.colorbar(im, ax=ax1)
    
    ax2 = axes[0, 1]
    findings = results['trigger_findings']
    triggers = [t for t in findings.keys() if findings[t].get('n', 0) > 10]
    rupture_probs = [findings[t]['p_rupture'] for t in triggers]
    colors = ['red' if t in ['RI_SPIKE', 'ZPOC_DEATH'] else 'gray' for t in triggers]
    
    bars = ax2.bar(range(len(triggers)), rupture_probs, color=colors, alpha=0.7)
    ax2.set_xticks(range(len(triggers)))
    ax2.set_xticklabels(triggers, rotation=45, ha='right')
    ax2.set_ylabel('P(STABLE → RUPTURE)')
    ax2.set_title('Trigger-Conditional Transition to RUPTURE')
    ax2.set_ylim(0, max(rupture_probs) * 1.3 if rupture_probs else 1)
    
    base = trans_matrix[STATE_IDX['STABLE_BASIN'], STATE_IDX['RUPTURE_RIDGE']]
    ax2.axhline(y=base, color='blue', linestyle='--', alpha=0.5, label=f'Baseline {base:.1%}')
    ax2.legend()
    
    for bar, prob in zip(bars, rupture_probs):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f'{prob:.0%}', ha='center', fontsize=9)
    
    ax3 = axes[1, 0]
    dwell = results['dwell_stats']
    states_with_data = [s for s in STATES if s in dwell]
    means = [dwell[s]['mean'] for s in states_with_data]
    stds = [dwell[s]['std'] for s in states_with_data]
    colors = ['green', 'yellow', 'red', 'gray'][:len(states_with_data)]
    
    bars = ax3.bar(range(len(states_with_data)), means, yerr=stds, 
                   color=colors, alpha=0.7, capsize=5)
    ax3.set_xticks(range(len(states_with_data)))
    ax3.set_xticklabels([s[:12] for s in states_with_data], rotation=45, ha='right')
    ax3.set_ylabel('Dwell Time (bars)')
    ax3.set_title('Average State Dwell Time')
    
    for bar, mean in zip(bars, means):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                f'{mean:.0f}', ha='center', fontsize=9)
    
    ax4 = axes[1, 1]
    sample = df.iloc[1000:2000].copy()
    state_colors = {'STABLE_BASIN': 0, 'TRANSITION_ZONE': 1, 'RUPTURE_RIDGE': 2, 'NOISE_FIELD': 3}
    state_nums = [state_colors.get(s, 3) for s in sample['world_state']]
    
    ax4.plot(range(len(sample)), sample['close'], 'k-', alpha=0.3, linewidth=0.5)
    ax4_twin = ax4.twinx()
    scatter = ax4_twin.scatter(range(len(sample)), state_nums, 
                               c=state_nums, cmap='RdYlGn_r', s=5, alpha=0.7)
    ax4_twin.set_yticks([0, 1, 2, 3])
    ax4_twin.set_yticklabels(['STABLE', 'TRANS', 'RUPTURE', 'NOISE'])
    ax4.set_xlabel('Bar')
    ax4.set_ylabel('Price', color='black')
    ax4_twin.set_ylabel('World State')
    ax4.set_title('World State Transitions Over Time (Sample)')
    
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {filename}")

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
    
    results, df, trans_matrix = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[6] Creating visualizations...")
    create_visualizations(results, df, trans_matrix, f"{OUTPUT_DIR}/world_transition.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
