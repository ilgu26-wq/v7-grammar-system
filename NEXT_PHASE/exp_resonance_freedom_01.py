"""
EXP-RESONANCE-FREEDOM-01: 자유도 붕괴 → 공명 → 파열 인과 사슬
================================================================
핵심 가설:
  "비가역성 경계 = 에너지 소멸이 아니라 자유도 붕괴"
  "자유도 ↓ → 공명 ↑ → RI_SPIKE ↑"

봉인 문장:
  "공명은 안정의 신호가 아니라, 자유도 상실의 부산물이다."
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from collections import deque
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/resonance_freedom_v1.json"

def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['range'] = df['high'] - df['low']
    
    er_list = []
    for i in range(len(df)):
        start = max(0, i - 9)
        window = df['close'].iloc[start:i+1]
        if len(window) < 2:
            er_list.append(0.5)
        else:
            change = abs(window.iloc[-1] - window.iloc[0])
            total = abs(window.diff().dropna()).sum()
            er_list.append(min(1.0, change / max(total, 0.01)))
    df['er'] = er_list
    
    rolling_high = df['high'].rolling(20, min_periods=1).max()
    rolling_low = df['low'].rolling(20, min_periods=1).min()
    df['depth'] = (df['close'] - rolling_low) / (rolling_high - rolling_low + 0.001)
    
    vol = df['range'].replace(0, 1)
    typical = (df['high'] + df['low'] + df['close']) / 3
    df['zpoc'] = (typical * vol).rolling(20, min_periods=1).sum() / vol.rolling(20, min_periods=1).sum()
    
    range_q25, range_q75 = df['range'].quantile(0.25), df['range'].quantile(0.75)
    er_median = df['er'].median()
    
    zpoc_dist = abs(df['zpoc'] - df['close'])
    zpoc_thresh = df['range'].rolling(20, min_periods=1).mean() * 3
    df['zpoc_alive'] = (zpoc_dist < zpoc_thresh).astype(int)
    df['er_alive'] = (df['er'] > er_median * 0.5).astype(int)
    df['range_alive'] = ((df['range'] >= range_q25) & (df['range'] <= range_q75 * 2)).astype(int)
    df['tau_alive'] = (df['er'].diff(5).abs().fillna(0) < 0.3).astype(int)
    
    df['htf_alive'] = 0
    for p in [5, 15]:
        htf = df['er'].rolling(p, min_periods=1).mean()
        df['htf_alive'] = df['htf_alive'] | (htf > 0.6).astype(int)
    
    df['recovery'] = ((df['er'].shift(3) < 0.3) & (df['er'] > 0.5)).astype(int).fillna(0)
    df['state_stable'] = (df['er'].diff().abs().fillna(0) < 0.1).astype(int)
    
    df['force_flux'] = (df['close'].diff().abs() * df['range']).rolling(5, min_periods=1).mean()
    
    ecs_weights = {'zpoc_alive': 2.0, 'htf_alive': -1.5, 'tau_alive': 0.6,
                   'state_stable': 0.5, 'range_alive': 0.3, 'recovery': -0.8,
                   'er_alive': -0.5}
    df['ecs'] = sum(ecs_weights[k] * df[k] for k in ecs_weights if k in df.columns)
    
    resistance = 1.0 + 2.0 * (1 - df['zpoc_alive']) + 0.5 * df['htf_alive'] + 1.0 * df['recovery']
    pg = df['force_flux'] / (df['ecs'] + 2.0).clip(lower=0.1)
    df['ri'] = pg * resistance
    
    window_pre, window_post = 5, 5
    ie_list = []
    for i in range(len(df)):
        start = max(0, i - window_pre)
        end = min(len(df), i + window_post + 1)
        w = df.iloc[start:end]
        if len(w) < 3:
            ie_list.append(0.0)
            continue
        fields = [
            w['zpoc_alive'].mean(), w['htf_alive'].mean(),
            w['er'].mean() * (1 - w['er'].std()),
            1.0 - min(1.0, w['depth'].std() * 3),
            w['tau_alive'].mean(),
            max(0, 1.0 - w['range'].std() / max(w['range'].mean(), 0.01)),
            min(1.0, w['recovery'].sum()), w['state_stable'].mean()
        ]
        ie = sum(fields) - np.var(fields)
        if fields[0] < 0.3 and fields[2] > 0.6:
            ie -= 1.0
        if fields[0] < 0.3 and sum(fields) > 4.0:
            ie -= 1.5
        ie_list.append(ie)
    df['ie'] = ie_list
    
    return df

def assign_planet(ie: float, zpoc: int, recovery: int, htf: int, ri: float, ri_q90: float) -> str:
    if not zpoc or ri > ri_q90:
        return "OUTSIDE"
    if ie < 2.3 or ie > 3.8:
        return "OUTSIDE"
    
    stressed = (recovery == 1) or (htf == 1)
    if ie < 2.75:
        return "P1"
    elif ie < 2.85:
        return "P2"
    elif stressed:
        return "P3_S"
    else:
        return "P3_C"

def compute_freedom(row: pd.Series, df: pd.DataFrame, idx: int, lookback: int = 10) -> Dict:
    start = max(0, idx - lookback)
    window = df.iloc[start:idx+1]
    
    ecs_sum = window['ecs'].sum()
    ecs_var = window['ecs'].var() if len(window) > 1 else 0
    
    alive_fields = ['zpoc_alive', 'er_alive', 'range_alive', 'tau_alive', 'state_stable']
    alive_sum = sum(window[f].sum() for f in alive_fields if f in window.columns)
    
    connection_density = alive_sum / (len(window) * len(alive_fields))
    
    zpoc_dist = window['zpoc_alive'].diff().abs().sum() if len(window) > 1 else 0
    
    freedom_index = connection_density * (1 + ecs_sum / (1 + ecs_var))
    
    return {
        'connection_density': connection_density,
        'ecs_stability': ecs_sum / (1 + ecs_var),
        'zpoc_fluctuation': zpoc_dist,
        'freedom_index': freedom_index
    }

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-RESONANCE-FREEDOM-01")
    print("자유도 붕괴 → 공명 → 파열 인과 사슬")
    print("=" * 70)
    
    print("\n[1] Computing indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q90 = df['ri'].quantile(0.90)
    ri_q95 = df['ri'].quantile(0.95)
    
    print("\n[2] Building trajectory with freedom measurements...")
    
    RESONANCE_WINDOW = 10
    RESONANCE_THRESHOLD = 3
    SPIKE_HORIZON = 5
    
    trajectory = []
    planet_history = deque(maxlen=RESONANCE_WINDOW)
    
    for idx in range(50, len(df) - 20):
        row = df.iloc[idx]
        
        planet = assign_planet(
            row['ie'], row['zpoc_alive'], row['recovery'],
            row['htf_alive'], row['ri'], ri_q90
        )
        planet_history.append(planet)
        
        transitions = 0
        if len(planet_history) >= RESONANCE_WINDOW:
            prev = planet_history[0]
            for p in list(planet_history)[1:]:
                if p != prev:
                    transitions += 1
                prev = p
        
        resonance = transitions >= RESONANCE_THRESHOLD
        
        unique_planets = len(set(planet_history))
        
        freedom = compute_freedom(row, df, idx, lookback=10)
        
        spike = False
        for k in range(1, SPIKE_HORIZON + 1):
            if idx + k < len(df) and df.iloc[idx + k]['ri'] > ri_q95:
                spike = True
                break
        
        ri_increase = 0
        if idx + 3 < len(df):
            ri_now = row['ri']
            ri_future = df.iloc[idx + 3]['ri']
            ri_increase = (ri_future - ri_now) / max(ri_now, 0.01)
        
        trajectory.append({
            'idx': idx,
            'planet': planet,
            'transitions': transitions,
            'unique_planets': unique_planets,
            'resonance': resonance,
            'freedom_index': freedom['freedom_index'],
            'connection_density': freedom['connection_density'],
            'ri': row['ri'],
            'ri_increase': ri_increase,
            'spike': spike
        })
    
    df_traj = pd.DataFrame(trajectory)
    print(f"  Trajectory: {len(df_traj)} bars")
    
    print("\n[3] Testing: Freedom ↓ → Resonance ↑ → RI_SPIKE ↑")
    
    freedom_bins = [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.0)]
    
    freedom_results = {}
    print("\n  Freedom vs Resonance vs SPIKE:")
    print("-" * 60)
    for low, high in freedom_bins:
        mask = (df_traj['freedom_index'] >= low) & (df_traj['freedom_index'] < high)
        bin_df = df_traj[mask]
        
        if len(bin_df) >= 50:
            resonance_rate = bin_df['resonance'].mean()
            spike_rate = bin_df['spike'].mean()
            avg_transitions = bin_df['transitions'].mean()
            avg_ri_increase = bin_df['ri_increase'].mean()
            
            bin_name = f"{low:.1f}-{high:.1f}"
            freedom_results[bin_name] = {
                'n': len(bin_df),
                'resonance_rate': resonance_rate,
                'spike_rate': spike_rate,
                'avg_transitions': avg_transitions,
                'avg_ri_increase': avg_ri_increase
            }
            
            print(f"  Freedom {bin_name}: res={resonance_rate:.1%}, spike={spike_rate:.1%}, "
                  f"trans={avg_transitions:.1f}, ri_inc={avg_ri_increase:.1%} (n={len(bin_df)})")
    
    print("\n[4] Testing: Resonance under low freedom → Guaranteed SPIKE")
    
    low_freedom = df_traj[df_traj['freedom_index'] < 0.4]
    high_freedom = df_traj[df_traj['freedom_index'] >= 0.6]
    
    resonance_results = {}
    
    if len(low_freedom) >= 100:
        low_res = low_freedom[low_freedom['resonance'] == True]
        low_no_res = low_freedom[low_freedom['resonance'] == False]
        
        if len(low_res) >= 20:
            resonance_results['low_freedom_resonance'] = {
                'n': len(low_res),
                'spike_rate': low_res['spike'].mean(),
                'avg_ri_increase': low_res['ri_increase'].mean()
            }
            print(f"\n  LOW freedom + RESONANCE: spike={low_res['spike'].mean():.1%}, "
                  f"ri_inc={low_res['ri_increase'].mean():.1%} (n={len(low_res)})")
        
        if len(low_no_res) >= 20:
            resonance_results['low_freedom_no_resonance'] = {
                'n': len(low_no_res),
                'spike_rate': low_no_res['spike'].mean(),
                'avg_ri_increase': low_no_res['ri_increase'].mean()
            }
            print(f"  LOW freedom + NO resonance: spike={low_no_res['spike'].mean():.1%}, "
                  f"ri_inc={low_no_res['ri_increase'].mean():.1%} (n={len(low_no_res)})")
    
    if len(high_freedom) >= 100:
        high_res = high_freedom[high_freedom['resonance'] == True]
        high_no_res = high_freedom[high_freedom['resonance'] == False]
        
        if len(high_res) >= 20:
            resonance_results['high_freedom_resonance'] = {
                'n': len(high_res),
                'spike_rate': high_res['spike'].mean(),
                'avg_ri_increase': high_res['ri_increase'].mean()
            }
            print(f"\n  HIGH freedom + RESONANCE: spike={high_res['spike'].mean():.1%}, "
                  f"ri_inc={high_res['ri_increase'].mean():.1%} (n={len(high_res)})")
        
        if len(high_no_res) >= 20:
            resonance_results['high_freedom_no_resonance'] = {
                'n': len(high_no_res),
                'spike_rate': high_no_res['spike'].mean(),
                'avg_ri_increase': high_no_res['ri_increase'].mean()
            }
            print(f"  HIGH freedom + NO resonance: spike={high_no_res['spike'].mean():.1%}, "
                  f"ri_inc={high_no_res['ri_increase'].mean():.1%} (n={len(high_no_res)})")
    
    print("\n[5] Causality chain test:")
    
    if freedom_results:
        first_bin = list(freedom_results.values())[0]
        last_bin = list(freedom_results.values())[-1]
        
        resonance_gradient = first_bin['resonance_rate'] - last_bin['resonance_rate']
        spike_gradient = first_bin['spike_rate'] - last_bin['spike_rate']
        
        print(f"\n  Freedom ↓ → Resonance: {'+' if resonance_gradient > 0 else ''}{resonance_gradient:.1%}")
        print(f"  Freedom ↓ → SPIKE: {'+' if spike_gradient > 0 else ''}{spike_gradient:.1%}")
        
        causality_confirmed = (resonance_gradient > 0.02 and spike_gradient > 0.02)
    else:
        causality_confirmed = False
    
    amplification = 1.0
    if 'low_freedom_resonance' in resonance_results and 'high_freedom_no_resonance' in resonance_results:
        low_spike = resonance_results['low_freedom_resonance']['spike_rate']
        high_spike = resonance_results['high_freedom_no_resonance']['spike_rate']
        if high_spike > 0:
            amplification = low_spike / high_spike
            print(f"\n  Amplification (low freedom + resonance vs high freedom): x{amplification:.1f}")
    
    print("\n" + "=" * 70)
    print("CAUSALITY CHAIN SUMMARY")
    print("=" * 70)
    
    success = causality_confirmed or amplification > 1.5
    
    if success:
        print("\n  CAUSALITY CHAIN CONFIRMED!")
        print("  자유도 ↓ → 공명 ↑ → RI_SPIKE ↑")
        print("\n  봉인 문장:")
        print("  '공명은 안정의 신호가 아니라,")
        print("   자유도 상실의 부산물이다.'")
    else:
        print("\n  Causality chain: PARTIAL")
    
    return {
        'experiment': 'EXP-RESONANCE-FREEDOM-01',
        'timestamp': datetime.now().isoformat(),
        'freedom_bins': freedom_results,
        'resonance_conditions': resonance_results,
        'causality_confirmed': causality_confirmed,
        'amplification': amplification,
        'success': success
    }, df_traj

def create_visualizations(results: Dict, df_traj: pd.DataFrame, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    freedom_bins = results['freedom_bins']
    if freedom_bins:
        bins = list(freedom_bins.keys())
        resonance_rates = [freedom_bins[b]['resonance_rate'] for b in bins]
        spike_rates = [freedom_bins[b]['spike_rate'] for b in bins]
        
        x = range(len(bins))
        width = 0.35
        ax1.bar([i - width/2 for i in x], resonance_rates, width, label='Resonance Rate', color='orange')
        ax1.bar([i + width/2 for i in x], spike_rates, width, label='SPIKE Rate', color='red')
        ax1.set_xticks(x)
        ax1.set_xticklabels([f'F:{b}' for b in bins])
        ax1.set_ylabel('Rate')
        ax1.set_title('Freedom vs Resonance/SPIKE')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
    
    ax2 = axes[0, 1]
    res_cond = results['resonance_conditions']
    if res_cond:
        conditions = list(res_cond.keys())
        spike_rates = [res_cond[c]['spike_rate'] for c in conditions]
        colors = ['red' if 'low' in c and 'resonance' in c and 'no' not in c else 'orange' if 'resonance' in c and 'no' not in c else 'green' for c in conditions]
        
        bars = ax2.bar(range(len(conditions)), spike_rates, color=colors, alpha=0.7)
        ax2.set_xticks(range(len(conditions)))
        ax2.set_xticklabels([c.replace('_', '\n') for c in conditions], fontsize=8)
        ax2.set_ylabel('SPIKE Rate')
        ax2.set_title('Freedom + Resonance → SPIKE')
        
        for bar, rate in zip(bars, spike_rates):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f'{rate:.0%}', ha='center', fontsize=10)
    
    ax3 = axes[1, 0]
    sample = df_traj.sample(min(2000, len(df_traj)))
    colors = ['red' if s else 'green' for s in sample['spike']]
    ax3.scatter(sample['freedom_index'], sample['transitions'], 
               alpha=0.3, c=colors, s=20)
    ax3.set_xlabel('Freedom Index')
    ax3.set_ylabel('Transitions (10 bars)')
    ax3.set_title('Freedom vs Transitions (red=SPIKE)')
    ax3.axhline(y=3, color='orange', linestyle='--', label='Resonance threshold')
    ax3.legend()
    
    ax4 = axes[1, 1]
    resonance_df = df_traj[df_traj['resonance'] == True]
    if len(resonance_df) > 50:
        freedom_q = pd.qcut(resonance_df['freedom_index'], q=4, labels=['Low', 'Med-Low', 'Med-High', 'High'])
        spike_by_freedom = resonance_df.groupby(freedom_q)['spike'].mean()
        
        colors = ['red', 'orange', 'yellow', 'green']
        ax4.bar(spike_by_freedom.index, spike_by_freedom.values, color=colors, alpha=0.7)
        ax4.set_ylabel('SPIKE Rate')
        ax4.set_xlabel('Freedom Level')
        ax4.set_title('SPIKE Rate by Freedom (Resonance only)')
        
        for i, (idx, val) in enumerate(spike_by_freedom.items()):
            ax4.text(i, val + 0.01, f'{val:.0%}', ha='center', fontsize=10)
    
    status = "CONFIRMED" if results['success'] else "PARTIAL"
    amp = results.get('amplification', 1.0)
    plt.suptitle(f'Causality Chain: Freedom -> Resonance -> SPIKE ({status}, x{amp:.1f})', 
                fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"\n  Saved: {filename}")

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
    
    results, df_traj = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[6] Creating visualizations...")
    create_visualizations(results, df_traj, f"{OUTPUT_DIR}/resonance_freedom.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
