"""
EXP-PE-DUAL-FRAME-01: 미시 PE + 거시 PE 방향 비대칭 최종 검증
=============================================================
핵심 가설:
  거시 PE = "터질지" 결정
  미시 PE = "어느 쪽으로 터질지" 결정

조건: 공명 + MEDIUM freedom 구간에서만 방향 힌트 존재

봉인 문장:
  "방향은 예측 대상이 아니다.
   방향은 붕괴 직전에만 드러나는 구조적 비대칭이다."
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
RESULT_FILE = "v7-grammar-system/results/pe_dual_frame_v1.json"

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
    
    df['force_up'] = (df['close'].diff().clip(lower=0) * df['range']).rolling(5, min_periods=1).sum()
    df['force_down'] = (-df['close'].diff().clip(upper=0) * df['range']).rolling(5, min_periods=1).sum()
    
    df['zpoc_drift'] = df['zpoc'].diff(5)
    
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

def compute_freedom_index(ecs: float, zpoc: bool, recovery: bool, 
                          htf: bool, transitions: int) -> float:
    ecs_stability = np.tanh(ecs / 3.0)
    zpoc_score = 1.0 if zpoc else 0.0
    transition_penalty = min(1.0, transitions / 5.0)
    stress_penalty = 0.3 * int(recovery) + 0.2 * int(htf)
    
    freedom = (
        0.35 * ecs_stability +
        0.30 * zpoc_score +
        0.20 * (1.0 - transition_penalty) +
        0.15 * (1.0 - stress_penalty)
    )
    return max(0.0, min(1.0, freedom))

def classify_freedom(idx: float) -> str:
    if idx >= 0.65:
        return "HIGH"
    elif idx >= 0.45:
        return "MEDIUM"
    elif idx >= 0.25:
        return "LOW"
    else:
        return "COLLAPSED"

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-PE-DUAL-FRAME-01")
    print("미시 PE + 거시 PE 방향 비대칭 최종 검증")
    print("=" * 70)
    
    print("\n[1] Computing indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q90 = df['ri'].quantile(0.90)
    ri_q95 = df['ri'].quantile(0.95)
    
    print(f"  RI thresholds: q75={ri_q75:.2f}, q90={ri_q90:.2f}, q95={ri_q95:.2f}")
    
    RESONANCE_WINDOW = 10
    RESONANCE_THRESHOLD = 3
    RUPTURE_HORIZON = 10
    
    print("\n[2] Building trajectory with PE measurements...")
    
    trajectory = []
    planet_history = deque(maxlen=RESONANCE_WINDOW)
    
    for idx in range(50, len(df) - RUPTURE_HORIZON - 5):
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
        
        freedom_idx = compute_freedom_index(
            row['ecs'], bool(row['zpoc_alive']), bool(row['recovery']),
            bool(row['htf_alive']), transitions
        )
        freedom = classify_freedom(freedom_idx)
        
        force_up = row['force_up']
        force_down = row['force_down']
        micro_pe = (force_up - force_down) / (abs(force_up) + abs(force_down) + 0.001)
        
        zpoc_drift = row['zpoc_drift']
        zpoc_drift_sign = 1 if zpoc_drift > 0 else (-1 if zpoc_drift < 0 else 0)
        
        macro_pe = (row['ri'] / ri_q90) + (row['ie'] / 3.0)
        
        future = df.iloc[idx+1:idx+RUPTURE_HORIZON+1]
        max_up = (future['high'].max() - row['close'])
        max_down = (row['close'] - future['low'].min())
        
        if max_up > max_down * 1.3:
            rupture_dir = "UP"
        elif max_down > max_up * 1.3:
            rupture_dir = "DOWN"
        else:
            rupture_dir = "NEUTRAL"
        
        trajectory.append({
            'idx': idx,
            'planet': planet,
            'resonance': resonance,
            'freedom': freedom,
            'freedom_idx': freedom_idx,
            'micro_pe': micro_pe,
            'macro_pe': macro_pe,
            'zpoc_drift_sign': zpoc_drift_sign,
            'rupture_dir': rupture_dir,
            'ri': row['ri'],
            'ri_spike': row['ri'] > ri_q95
        })
    
    df_traj = pd.DataFrame(trajectory)
    print(f"  Trajectory: {len(df_traj)} bars")
    
    print("\n[3] Filtering TARGET ZONE: P3_CLEAN + Resonance + MEDIUM freedom + no SPIKE...")
    
    target_mask = (
        (df_traj['planet'] == 'P3_C') &
        (df_traj['resonance'] == True) &
        (df_traj['freedom'] == 'MEDIUM') &
        (df_traj['ri_spike'] == False)
    )
    target_df = df_traj[target_mask]
    print(f"  Target zone bars: {len(target_df)} ({len(target_df)/len(df_traj):.1%})")
    
    if len(target_df) < 50:
        print("\n  ⚠️ Insufficient target bars, expanding to include HIGH freedom...")
        target_mask = (
            (df_traj['planet'] == 'P3_C') &
            (df_traj['resonance'] == True) &
            (df_traj['ri_spike'] == False)
        )
        target_df = df_traj[target_mask]
        print(f"  Expanded target: {len(target_df)} bars")
    
    print("\n[4] Testing H1: MicroPE sign → Rupture direction...")
    
    results = {}
    
    if len(target_df) >= 30:
        up_ruptures = target_df[target_df['rupture_dir'] == 'UP']
        down_ruptures = target_df[target_df['rupture_dir'] == 'DOWN']
        
        micro_pe_up_correct = (up_ruptures['micro_pe'] > 0).sum()
        micro_pe_down_correct = (down_ruptures['micro_pe'] < 0).sum()
        
        total_directional = len(up_ruptures) + len(down_ruptures)
        if total_directional > 0:
            direction_accuracy = (micro_pe_up_correct + micro_pe_down_correct) / total_directional
        else:
            direction_accuracy = 0.5
        
        results['h1_direction_accuracy'] = direction_accuracy
        results['h1_n_samples'] = total_directional
        results['h1_up_correct'] = micro_pe_up_correct
        results['h1_down_correct'] = micro_pe_down_correct
        
        print(f"\n  Direction hint accuracy: {direction_accuracy:.1%}")
        print(f"  UP ruptures predicted: {micro_pe_up_correct}/{len(up_ruptures)}")
        print(f"  DOWN ruptures predicted: {micro_pe_down_correct}/{len(down_ruptures)}")
        
        if direction_accuracy > 0.55:
            print(f"  ✓ H1 PASS: Direction hint exists!")
        else:
            print(f"  △ H1 PARTIAL: Weak or no direction hint")
    else:
        results['h1_direction_accuracy'] = None
        print("  Insufficient samples for H1")
    
    print("\n[5] Testing H2: MacroPE amplifies direction alignment...")
    
    if len(target_df) >= 50:
        macro_pe_q = pd.qcut(target_df['macro_pe'], q=4, labels=['Q1', 'Q2', 'Q3', 'Q4'], duplicates='drop')
        
        h2_results = {}
        for q in ['Q1', 'Q2', 'Q3', 'Q4']:
            q_mask = macro_pe_q == q
            q_df = target_df[q_mask]
            
            if len(q_df) >= 10:
                q_up = q_df[q_df['rupture_dir'] == 'UP']
                q_down = q_df[q_df['rupture_dir'] == 'DOWN']
                
                q_correct = (q_up['micro_pe'] > 0).sum() + (q_down['micro_pe'] < 0).sum()
                q_total = len(q_up) + len(q_down)
                
                if q_total > 0:
                    q_accuracy = q_correct / q_total
                    h2_results[q] = {'accuracy': q_accuracy, 'n': q_total}
                    print(f"  MacroPE {q}: accuracy={q_accuracy:.1%} (n={q_total})")
        
        results['h2_macro_pe_results'] = h2_results
        
        if 'Q1' in h2_results and 'Q4' in h2_results:
            amplification = h2_results['Q4']['accuracy'] - h2_results['Q1']['accuracy']
            results['h2_amplification'] = amplification
            print(f"\n  MacroPE amplification (Q4-Q1): {amplification:+.1%}")
            
            if amplification > 0.05:
                print(f"  ✓ H2 PASS: Macro PE amplifies direction signal!")
            else:
                print(f"  △ H2 PARTIAL: Weak amplification")
    else:
        results['h2_macro_pe_results'] = {}
        print("  Insufficient samples for H2")
    
    print("\n[6] Control test: HIGH freedom should show ~50% (symmetric)...")
    
    high_freedom_mask = (
        (df_traj['planet'] == 'P3_C') &
        (df_traj['freedom'] == 'HIGH') &
        (df_traj['ri_spike'] == False)
    )
    high_df = df_traj[high_freedom_mask]
    
    if len(high_df) >= 50:
        h_up = high_df[high_df['rupture_dir'] == 'UP']
        h_down = high_df[high_df['rupture_dir'] == 'DOWN']
        h_correct = (h_up['micro_pe'] > 0).sum() + (h_down['micro_pe'] < 0).sum()
        h_total = len(h_up) + len(h_down)
        
        if h_total > 0:
            high_accuracy = h_correct / h_total
            results['control_high_freedom_accuracy'] = high_accuracy
            print(f"\n  HIGH freedom accuracy: {high_accuracy:.1%} (should be ~50%)")
            
            if abs(high_accuracy - 0.5) < 0.08:
                print(f"  ✓ Control PASS: HIGH freedom is symmetric as expected")
            else:
                print(f"  ⚠️ Control unexpected: HIGH freedom shows asymmetry")
    
    print("\n" + "=" * 70)
    print("PE DUAL FRAME SUMMARY")
    print("=" * 70)
    
    h1_pass = results.get('h1_direction_accuracy', 0) and results['h1_direction_accuracy'] > 0.55
    h2_pass = results.get('h2_amplification', 0) and results['h2_amplification'] > 0.05
    control_pass = results.get('control_high_freedom_accuracy') and abs(results['control_high_freedom_accuracy'] - 0.5) < 0.08
    
    success = h1_pass or h2_pass
    
    if success:
        print("\n  ✓ DIRECTION ASYMMETRY DETECTED!")
        print("\n  봉인 문장:")
        print("  '방향은 예측 대상이 아니다.")
        print("   방향은 붕괴 직전에만 드러나는 구조적 비대칭이다.'")
        print("\n  '거시 PE는 터질지를,")
        print("   미시 PE는 어느 쪽으로 터질지를 결정한다.'")
    else:
        print("\n  △ Direction asymmetry: WEAK or NOT DETECTED")
    
    return {
        'experiment': 'EXP-PE-DUAL-FRAME-01',
        'timestamp': datetime.now().isoformat(),
        'target_zone_bars': len(target_df),
        'results': results,
        'h1_pass': h1_pass,
        'h2_pass': h2_pass,
        'control_pass': control_pass,
        'success': success
    }, df_traj

def create_visualizations(results: Dict, df_traj: pd.DataFrame, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    res = results['results']
    if res.get('h1_direction_accuracy'):
        categories = ['MicroPE\nDirection', 'Random\nBaseline']
        values = [res['h1_direction_accuracy'], 0.5]
        colors = ['green' if res['h1_direction_accuracy'] > 0.55 else 'orange', 'gray']
        
        bars = ax1.bar(categories, values, color=colors, alpha=0.7)
        ax1.axhline(y=0.55, color='red', linestyle='--', label='55% threshold')
        ax1.set_ylabel('Accuracy')
        ax1.set_title(f'H1: Direction Hint Accuracy (n={res.get("h1_n_samples", 0)})')
        ax1.legend()
        
        for bar, val in zip(bars, values):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                    f'{val:.1%}', ha='center', fontsize=12, fontweight='bold')
    
    ax2 = axes[0, 1]
    h2 = res.get('h2_macro_pe_results', {})
    if h2:
        quartiles = list(h2.keys())
        accuracies = [h2[q]['accuracy'] for q in quartiles]
        colors = ['green' if a > 0.55 else 'orange' if a > 0.5 else 'red' for a in accuracies]
        
        bars = ax2.bar(quartiles, accuracies, color=colors, alpha=0.7)
        ax2.axhline(y=0.5, color='gray', linestyle='--')
        ax2.set_ylabel('Direction Accuracy')
        ax2.set_xlabel('MacroPE Quartile')
        ax2.set_title('H2: MacroPE Amplification Effect')
        
        for bar, val in zip(bars, accuracies):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                    f'{val:.0%}', ha='center', fontsize=10)
    
    ax3 = axes[1, 0]
    target_mask = (df_traj['planet'] == 'P3_C') & (df_traj['resonance'] == True)
    target_df = df_traj[target_mask]
    if len(target_df) > 0:
        colors = {'UP': 'green', 'DOWN': 'red', 'NEUTRAL': 'gray'}
        for direction in ['UP', 'DOWN', 'NEUTRAL']:
            subset = target_df[target_df['rupture_dir'] == direction]
            if len(subset) > 0:
                ax3.scatter(subset['micro_pe'], subset['macro_pe'], 
                           alpha=0.5, label=direction, c=colors[direction], s=20)
        ax3.axvline(x=0, color='black', linestyle='--', alpha=0.5)
        ax3.set_xlabel('MicroPE (Force Imbalance)')
        ax3.set_ylabel('MacroPE')
        ax3.set_title('MicroPE vs MacroPE (Target Zone)')
        ax3.legend()
    
    ax4 = axes[1, 1]
    control_acc = res.get('control_high_freedom_accuracy')
    target_acc = res.get('h1_direction_accuracy')
    
    if control_acc and target_acc:
        categories = ['Target Zone\n(Resonance+Medium)', 'Control\n(High Freedom)']
        values = [target_acc, control_acc]
        colors = ['green', 'blue']
        
        bars = ax4.bar(categories, values, color=colors, alpha=0.7)
        ax4.axhline(y=0.5, color='gray', linestyle='--', label='Random baseline')
        ax4.set_ylabel('Direction Accuracy')
        ax4.set_title('Target vs Control Comparison')
        
        for bar, val in zip(bars, values):
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                    f'{val:.1%}', ha='center', fontsize=12, fontweight='bold')
    
    status = "DETECTED" if results['success'] else "PARTIAL"
    plt.suptitle(f'PE Dual Frame: Direction Asymmetry {status}', fontsize=14, fontweight='bold')
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
    
    print("\n[7] Creating visualizations...")
    create_visualizations(results, df_traj, f"{OUTPUT_DIR}/pe_dual_frame.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
