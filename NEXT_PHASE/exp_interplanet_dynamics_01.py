"""
EXP-INTERPLANET-DYNAMICS-01: 행성 간 중력 + 공명 법칙
======================================================
두 가지 핵심 실험:

1. GRAVITY: 체류 시간 증가 → 인접 행성 전이 확률 증가?
2. RESONANCE: 빠른 왕복 → SPIKE 확률 급증?

봉인 문장:
"시장은 중력과 공명을 가진 다중 세계계다.
 스톰은 가격 움직임이 아니라 세계 간 공명으로 발생한다."
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
from collections import defaultdict
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/interplanet_dynamics_v1.json"

WINDOW_PRE = 5
WINDOW_POST = 5
SPIKE_HORIZON = 5
RESONANCE_WINDOW = 10
MIN_TRANSITIONS_FOR_RESONANCE = 3

ECS_WEIGHTS = {
    'zpoc_alive': 2.0, 'htf_alive': -1.5, 'tau_alive': 0.6,
    'state_stable': 0.5, 'range_alive': 0.3,
    'recovery': -0.8, 'er_alive': -0.5, 'depth_alive': -0.3
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
        result.append(min(1.0, price_change / max(bar_changes, 0.01)))
    return pd.Series(result, index=close_series.index)

def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['range'] = df['high'] - df['low']
    df['er'] = calc_er(df['close'])
    
    rolling_high = df['high'].rolling(20, min_periods=1).max()
    rolling_low = df['low'].rolling(20, min_periods=1).min()
    df['depth'] = (df['close'] - rolling_low) / (rolling_high - rolling_low + 0.001)
    
    vol = df['range'].replace(0, 1)
    typical = (df['high'] + df['low'] + df['close']) / 3
    df['zpoc'] = (typical * vol).rolling(20, min_periods=1).sum() / vol.rolling(20, min_periods=1).sum()
    
    range_q25, range_q75 = df['range'].quantile(0.25), df['range'].quantile(0.75)
    er_median = df['er'].median()
    depth_median = df['depth'].median()
    
    zpoc_dist = abs(df['zpoc'] - df['close'])
    zpoc_thresh = df['range'].rolling(20, min_periods=1).mean() * 3
    df['zpoc_alive'] = (zpoc_dist < zpoc_thresh).astype(int)
    df['depth_alive'] = (abs(df['depth'] - depth_median) < 0.3).astype(int)
    df['er_alive'] = (df['er'] > er_median * 0.5).astype(int)
    df['range_alive'] = ((df['range'] >= range_q25) & (df['range'] <= range_q75 * 2)).astype(int)
    df['tau_alive'] = (df['er'].diff(5).abs() < 0.3).astype(int)
    
    df['htf_alive'] = 0
    for p in [5, 15]:
        htf = df['er'].rolling(p, min_periods=1).mean()
        df['htf_alive'] = df['htf_alive'] | (htf > 0.6).astype(int)
    
    df['recovery'] = ((df['er'].shift(3) < 0.3) & (df['er'] > 0.5)).astype(int)
    df['state_stable'] = (df['er'].diff().abs() < 0.1).astype(int)
    
    df['force_flux'] = (df['close'].diff().abs() * df['range']).rolling(5, min_periods=1).mean()
    df['ecs'] = sum(ECS_WEIGHTS[k] * df[k] for k in ECS_WEIGHTS if k in df.columns)
    
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
        window['zpoc_alive'].mean(), window['htf_alive'].mean(),
        window['er'].mean() * (1 - window['er'].std()),
        1.0 - min(1.0, window['depth'].std() * 3),
        window['tau_alive'].mean(),
        max(0, 1.0 - window['range'].std() / max(window['range'].mean(), 0.01)),
        min(1.0, window['recovery'].sum()), window['state_stable'].mean()
    ]
    
    ie = sum(fields) - np.var(fields)
    if fields[0] < 0.3 and fields[2] > 0.6:
        ie -= 1.0
    if fields[0] < 0.3 and sum(fields) > 4.0:
        ie -= 1.5
    return ie

def is_stable_basin(ie: float, ri: float, ecs: float, zpoc: int, ri_q75: float) -> bool:
    return (2.3 <= ie <= 3.8 and ri < ri_q75 and ecs > 1.0 and zpoc == 1)

def detect_spike_event(df: pd.DataFrame, idx: int, ri_q95: float) -> bool:
    if df['ri'].iloc[idx] > ri_q95:
        return True
    if idx >= 1 and df['zpoc_alive'].iloc[idx-1] == 1 and df['zpoc_alive'].iloc[idx] == 0:
        return True
    return False

def assign_planet(ie: float, recovery: int, htf: int) -> str:
    stressed = (recovery == 1) or (htf == 1)
    if ie < 2.75:
        return "P1"
    elif ie < 2.85:
        return "P2"
    elif stressed:
        return "P3_S"
    else:
        return "P3_C"

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-INTERPLANET-DYNAMICS-01")
    print("행성 간 중력 + 공명 법칙")
    print("=" * 70)
    
    print("\n[1] Computing indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q95 = df['ri'].quantile(0.95)
    
    print("\n[2] Building planet trajectory...")
    
    trajectory = []
    for idx in range(50, len(df) - 20):
        ie = compute_ie(df, idx)
        ri = df['ri'].iloc[idx]
        ecs = df['ecs'].iloc[idx]
        zpoc = df['zpoc_alive'].iloc[idx]
        recovery = df['recovery'].iloc[idx]
        htf = df['htf_alive'].iloc[idx]
        
        if is_stable_basin(ie, ri, ecs, zpoc, ri_q75):
            planet = assign_planet(ie, recovery, htf)
        else:
            planet = "OUTSIDE"
        
        spike = False
        for k in range(1, SPIKE_HORIZON + 1):
            if idx + k < len(df) and detect_spike_event(df, idx + k, ri_q95):
                spike = True
                break
        
        trajectory.append({
            'idx': idx, 'planet': planet, 'spike': spike,
            'ie': ie, 'ri': ri
        })
    
    df_traj = pd.DataFrame(trajectory)
    print(f"  Trajectory length: {len(df_traj)}")
    
    print("\n[3] GRAVITY TEST: Dwell time vs transition probability...")
    
    dwell_times = []
    current_planet = df_traj['planet'].iloc[0]
    dwell_start = 0
    
    for i in range(1, len(df_traj)):
        if df_traj['planet'].iloc[i] != current_planet:
            dwell = i - dwell_start
            next_planet = df_traj['planet'].iloc[i]
            spike_during = df_traj['spike'].iloc[dwell_start:i].any()
            
            dwell_times.append({
                'from_planet': current_planet,
                'to_planet': next_planet,
                'dwell_bars': dwell,
                'spike': spike_during
            })
            
            current_planet = next_planet
            dwell_start = i
    
    df_dwell = pd.DataFrame(dwell_times)
    
    p3c_dwells = df_dwell[df_dwell['from_planet'] == 'P3_C']
    
    gravity_results = {}
    dwell_bins = [(1, 3), (4, 6), (7, 10), (11, 20)]
    
    print("\n  P3_CLEAN dwell time → transition probability:")
    for low, high in dwell_bins:
        bin_mask = (p3c_dwells['dwell_bars'] >= low) & (p3c_dwells['dwell_bars'] <= high)
        bin_df = p3c_dwells[bin_mask]
        
        if len(bin_df) >= 10:
            p3c_stay = (bin_df['to_planet'] == 'P3_C').mean()
            p3s_trans = (bin_df['to_planet'] == 'P3_S').mean()
            p2_trans = (bin_df['to_planet'] == 'P2').mean()
            spike_rate = bin_df['spike'].mean()
            
            bin_name = f"{low}-{high}"
            gravity_results[bin_name] = {
                'n': len(bin_df),
                'stay_p3c': p3c_stay,
                'trans_p3s': p3s_trans,
                'trans_p2': p2_trans,
                'spike_rate': spike_rate
            }
            
            print(f"    {bin_name} bars: stay={p3c_stay:.0%}, →P3_S={p3s_trans:.1%}, →P2={p2_trans:.1%}, spike={spike_rate:.1%} (n={len(bin_df)})")
    
    print("\n[4] RESONANCE TEST: Fast oscillation → SPIKE probability...")
    
    resonance_events = []
    
    for i in range(RESONANCE_WINDOW, len(df_traj)):
        window = df_traj['planet'].iloc[i-RESONANCE_WINDOW:i]
        transitions = (window != window.shift(1)).sum() - 1
        
        if transitions >= MIN_TRANSITIONS_FOR_RESONANCE:
            unique_planets = window[window != 'OUTSIDE'].nunique()
            spike = df_traj['spike'].iloc[i]
            
            resonance_events.append({
                'idx': i,
                'transitions': transitions,
                'unique_planets': unique_planets,
                'spike': spike
            })
    
    df_resonance = pd.DataFrame(resonance_events) if resonance_events else pd.DataFrame()
    
    normal_mask = df_traj['planet'] == 'P3_C'
    normal_spike_rate = df_traj[normal_mask]['spike'].mean()
    
    resonance_results = {
        'normal_spike_rate': normal_spike_rate,
        'resonance_events': len(df_resonance)
    }
    
    if len(df_resonance) > 20:
        resonance_spike_rate = df_resonance['spike'].mean()
        resonance_results['resonance_spike_rate'] = resonance_spike_rate
        resonance_results['amplification'] = resonance_spike_rate / max(normal_spike_rate, 0.01)
        
        print(f"\n  Normal (P3_CLEAN): {normal_spike_rate:.1%}")
        print(f"  Resonance Zone: {resonance_spike_rate:.1%}")
        print(f"  Amplification: ×{resonance_results['amplification']:.1f}")
        
        for trans_threshold in [3, 4, 5]:
            high_res = df_resonance[df_resonance['transitions'] >= trans_threshold]
            if len(high_res) >= 10:
                spike_rate = high_res['spike'].mean()
                print(f"  Resonance ≥{trans_threshold} transitions: {spike_rate:.1%} (n={len(high_res)})")
                resonance_results[f'spike_rate_{trans_threshold}+'] = spike_rate
    else:
        print(f"\n  Insufficient resonance events: {len(df_resonance)}")
    
    print("\n" + "=" * 70)
    print("INTERPLANETARY DYNAMICS SUMMARY")
    print("=" * 70)
    
    gravity_detected = False
    if gravity_results:
        first_bin = list(gravity_results.values())[0]
        last_bin = list(gravity_results.values())[-1]
        stay_decrease = first_bin.get('stay_p3c', 1) - last_bin.get('stay_p3c', 1)
        if stay_decrease > 0.05:
            gravity_detected = True
            print(f"\n  🌍 GRAVITY DETECTED!")
            print(f"     Stay probability drops: {first_bin.get('stay_p3c', 0):.0%} → {last_bin.get('stay_p3c', 0):.0%}")
    
    resonance_detected = False
    if resonance_results.get('amplification', 0) > 1.5:
        resonance_detected = True
        print(f"\n  🌪️ RESONANCE DETECTED!")
        print(f"     SPIKE amplification: ×{resonance_results['amplification']:.1f}")
    
    success = gravity_detected or resonance_detected
    
    print(f"\n  Gravity Law: {'✓ CONFIRMED' if gravity_detected else '△ NOT CLEAR'}")
    print(f"  Resonance Law: {'✓ CONFIRMED' if resonance_detected else '△ NOT CLEAR'}")
    print(f"\n  Overall: {'✓ PASS' if success else '△ PARTIAL'}")
    
    return {
        'experiment': 'EXP-INTERPLANET-DYNAMICS-01',
        'timestamp': datetime.now().isoformat(),
        'gravity_results': gravity_results,
        'resonance_results': resonance_results,
        'gravity_detected': gravity_detected,
        'resonance_detected': resonance_detected,
        'success': success
    }, df_traj, df_dwell, df_resonance

def create_visualizations(results: Dict, df_traj, df_dwell, df_resonance, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    gravity = results['gravity_results']
    if gravity:
        bins = list(gravity.keys())
        stays = [gravity[b]['stay_p3c'] for b in bins]
        trans_p3s = [gravity[b].get('trans_p3s', 0) for b in bins]
        spikes = [gravity[b].get('spike_rate', 0) for b in bins]
        
        x = range(len(bins))
        ax1.plot(x, stays, 'go-', label='Stay in P3_C', linewidth=2, markersize=10)
        ax1.plot(x, trans_p3s, 'rs-', label='→ P3_S', linewidth=2, markersize=10)
        ax1.plot(x, spikes, 'b^-', label='SPIKE rate', linewidth=2, markersize=10)
        
        ax1.set_xticks(x)
        ax1.set_xticklabels([f'{b} bars' for b in bins])
        ax1.set_ylabel('Probability')
        ax1.set_title('GRAVITY: Dwell Time Effect on Transitions')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
    
    ax2 = axes[0, 1]
    res = results['resonance_results']
    if 'resonance_spike_rate' in res:
        categories = ['Normal\n(P3_CLEAN)', 'Resonance\nZone']
        rates = [res['normal_spike_rate'], res['resonance_spike_rate']]
        colors = ['green', 'red']
        
        bars = ax2.bar(categories, rates, color=colors, alpha=0.7)
        ax2.set_ylabel('SPIKE Rate')
        ax2.set_title(f'RESONANCE: SPIKE Amplification ×{res.get("amplification", 1):.1f}')
        
        for bar, rate in zip(bars, rates):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f'{rate:.0%}', ha='center', fontsize=12, fontweight='bold')
    
    ax3 = axes[1, 0]
    if len(df_dwell) > 0:
        p3c = df_dwell[df_dwell['from_planet'] == 'P3_C']
        if len(p3c) > 0:
            ax3.hist(p3c['dwell_bars'], bins=20, color='green', alpha=0.7, edgecolor='black')
            ax3.axvline(x=p3c['dwell_bars'].median(), color='red', linestyle='--', label=f'Median: {p3c["dwell_bars"].median():.0f}')
            ax3.set_xlabel('Dwell Time (bars)')
            ax3.set_ylabel('Frequency')
            ax3.set_title('P3_CLEAN Dwell Time Distribution')
            ax3.legend()
    
    ax4 = axes[1, 1]
    if len(df_resonance) > 0:
        ax4.scatter(df_resonance['transitions'], df_resonance['spike'].astype(int) + np.random.normal(0, 0.05, len(df_resonance)),
                   alpha=0.5, c=df_resonance['spike'].astype(int), cmap='RdYlGn_r')
        ax4.set_xlabel('Transitions in Window')
        ax4.set_ylabel('SPIKE (jittered)')
        ax4.set_title('Resonance: Transitions vs SPIKE')
    
    status = "✓ PASS" if results['success'] else "△ PARTIAL"
    gravity_status = "🌍 Gravity" if results['gravity_detected'] else ""
    resonance_status = "🌪️ Resonance" if results['resonance_detected'] else ""
    plt.suptitle(f'Interplanetary Dynamics: {status} {gravity_status} {resonance_status}', fontsize=14, fontweight='bold')
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
    
    results, df_traj, df_dwell, df_resonance = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[5] Creating visualizations...")
    create_visualizations(results, df_traj, df_dwell, df_resonance,
                         f"{OUTPUT_DIR}/interplanet_dynamics.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
