"""
EXP-HYPOTHESIS-INVERSION-MAP-01: 가설 비틀기 + 분포도 맵핑
==========================================================
비틀린 가설:
  "ZPOC=0 구간에서 연결성이 안정 분포를 잃고 난류 분포로 이동한다"
  
출력:
  - map_connectivity_phase_zpoc1.png (ZPOC alive)
  - map_connectivity_phase_zpoc0.png (ZPOC dead)  
  - map_actionmask_overlay.png (ACTION_MASK 효과)
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from typing import Dict, List
import os

OUTPUT_DIR = "v7-grammar-system/images"

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

def compute_bar_level_labels(df: pd.DataFrame, lookforward: int = 30) -> pd.DataFrame:
    """전체 bar에 대해 라벨링"""
    
    print("  Computing base metrics...")
    df = df.copy()
    df['range'] = df['high'] - df['low']
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['zpoc'] = calc_zpoc(df)
    
    range_q25 = df['range'].quantile(0.25)
    range_q75 = df['range'].quantile(0.75)
    er_median = df['er'].median()
    depth_median = df['depth'].median()
    
    print("  Computing node states...")
    
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
        htf_high = (htf_er > 0.6).astype(int)
        df['htf_alive'] = df['htf_alive'] | htf_high
    
    df['alive_count'] = (df['zpoc_alive'] + df['htf_alive'] + df['depth_alive'] + 
                         df['er_alive'] + df['range_alive'] + df['tau_alive'])
    
    print("  Computing ECS...")
    df['ecs'] = (WEIGHTS['zpoc_alive'] * df['zpoc_alive'] +
                 WEIGHTS['htf_alive'] * df['htf_alive'] +
                 WEIGHTS['range_alive'] * df['range_alive'] +
                 WEIGHTS['depth_alive'] * df['depth_alive'] +
                 WEIGHTS['tau_alive'] * df['tau_alive'] +
                 WEIGHTS['er_alive'] * df['er_alive'])
    
    penalty = ((df['alive_count'] >= 5) & (df['htf_alive'] == 1)).astype(float) * 1.5
    penalty += (df['alive_count'] >= 6).astype(float) * 1.0
    df['ecs_penalized'] = df['ecs'] - penalty
    
    print("  Computing ACTION_MASK v3...")
    df['action_mask'] = 1.0
    df.loc[df['zpoc_alive'] == 0, 'action_mask'] = 0.0
    df.loc[(df['htf_alive'] == 1) & (df['alive_count'] >= 4), 'action_mask'] = 0.0
    df.loc[df['ecs_penalized'] < 1.0, 'action_mask'] = 0.0
    df.loc[(df['ecs_penalized'] >= 1.0) & (df['ecs_penalized'] < 2.0), 'action_mask'] = 0.5
    
    print("  Computing future collapse (STRICT)...")
    df['future_collapse'] = 0
    
    for i in range(len(df) - lookforward):
        future = df.iloc[i:i + lookforward + 1]
        er_min = future['er'].min()
        er_drop = df['er'].iloc[i] - er_min
        price_drop = (df['close'].iloc[i] - future['low'].min()) / max(df['range'].iloc[i], 0.01)
        
        conditions_met = 0
        if er_min < 0.15:
            conditions_met += 1
        if er_drop > 0.50:
            conditions_met += 1
        if price_drop > 5.0:
            conditions_met += 1
        
        if conditions_met >= 2:
            df.iloc[i, df.columns.get_loc('future_collapse')] = 1
    
    return df

def create_connectivity_phase_map(df: pd.DataFrame, zpoc_value: int, filename: str):
    """Connectivity Phase Map 생성"""
    
    subset = df[df['zpoc_alive'] == zpoc_value].copy()
    
    if len(subset) == 0:
        print(f"  Warning: No data for zpoc_alive={zpoc_value}")
        return
    
    alive_bins = range(0, 8)
    ecs_bins = np.arange(-3, 6, 1)
    
    heatmap = np.zeros((len(ecs_bins) - 1, len(alive_bins) - 1))
    counts = np.zeros_like(heatmap)
    
    for _, row in subset.iterrows():
        alive = int(row['alive_count'])
        ecs = row['ecs_penalized']
        collapse = row['future_collapse']
        
        alive_idx = min(alive, 6)
        ecs_idx = np.digitize(ecs, ecs_bins) - 1
        ecs_idx = max(0, min(ecs_idx, len(ecs_bins) - 2))
        
        if 0 <= alive_idx < heatmap.shape[1] and 0 <= ecs_idx < heatmap.shape[0]:
            heatmap[ecs_idx, alive_idx] += collapse
            counts[ecs_idx, alive_idx] += 1
    
    with np.errstate(divide='ignore', invalid='ignore'):
        collapse_rate = np.where(counts > 0, heatmap / counts, np.nan)
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    im = ax.imshow(collapse_rate, cmap='RdYlGn_r', aspect='auto', 
                   vmin=0, vmax=1, origin='lower')
    
    ax.set_xticks(range(len(alive_bins) - 1))
    ax.set_xticklabels([str(i) for i in alive_bins[:-1]])
    ax.set_yticks(range(len(ecs_bins) - 1))
    ax.set_yticklabels([f"{ecs_bins[i]:.0f}" for i in range(len(ecs_bins) - 1)])
    
    ax.set_xlabel('alive_count', fontsize=12)
    ax.set_ylabel('ECS (penalized)', fontsize=12)
    
    zpoc_label = "ZPOC ALIVE" if zpoc_value == 1 else "ZPOC DEAD"
    ax.set_title(f'Connectivity Phase Map ({zpoc_label})\nCollapse Rate by State', fontsize=14)
    
    for i in range(heatmap.shape[0]):
        for j in range(heatmap.shape[1]):
            if counts[i, j] > 0:
                rate = collapse_rate[i, j]
                n = int(counts[i, j])
                color = 'white' if rate > 0.5 else 'black'
                ax.text(j, i, f'{rate:.0%}\n({n})', ha='center', va='center', 
                       fontsize=8, color=color)
    
    cbar = plt.colorbar(im, ax=ax, label='Collapse Rate')
    
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {filename}")

def create_actionmask_overlay_map(df: pd.DataFrame, filename: str):
    """ACTION_MASK Effectiveness Map"""
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    
    for idx, (zpoc_val, title) in enumerate([(1, 'ZPOC ALIVE'), (0, 'ZPOC DEAD')]):
        ax = axes[idx]
        subset = df[df['zpoc_alive'] == zpoc_val]
        
        if len(subset) == 0:
            continue
        
        masked = subset[subset['action_mask'] == 0]
        half = subset[subset['action_mask'] == 0.5]
        passed = subset[subset['action_mask'] == 1.0]
        
        for data, color, label, alpha in [
            (masked[masked['future_collapse'] == 1], 'red', 'Blocked + Collapsed', 0.3),
            (masked[masked['future_collapse'] == 0], 'orange', 'Blocked + Survived', 0.5),
            (passed[passed['future_collapse'] == 1], 'darkred', 'Passed + Collapsed', 0.6),
            (passed[passed['future_collapse'] == 0], 'green', 'Passed + Survived', 0.8),
        ]:
            if len(data) > 0:
                sample = data.sample(min(len(data), 500), random_state=42)
                ax.scatter(sample['alive_count'] + np.random.normal(0, 0.1, len(sample)),
                          sample['ecs_penalized'] + np.random.normal(0, 0.1, len(sample)),
                          c=color, alpha=alpha, s=20, label=f'{label} ({len(data)})')
        
        ax.set_xlabel('alive_count', fontsize=11)
        ax.set_ylabel('ECS (penalized)', fontsize=11)
        ax.set_title(f'{title}', fontsize=13)
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(-0.5, 6.5)
        ax.set_ylim(-4, 6)
    
    plt.suptitle('ACTION_MASK v3 Effectiveness\n(Green=Safe Pass, Red=Dangerous Pass)', fontsize=14)
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {filename}")

def create_summary_stats(df: pd.DataFrame):
    """요약 통계 출력"""
    
    print("\n" + "=" * 70)
    print("DISTRIBUTION SUMMARY")
    print("=" * 70)
    
    total = len(df)
    collapsed = df['future_collapse'].sum()
    
    print(f"\nTotal bars: {total}")
    print(f"Future collapse: {collapsed} ({collapsed/total:.1%})")
    
    print("\n[By ZPOC status]")
    for zpoc in [1, 0]:
        subset = df[df['zpoc_alive'] == zpoc]
        n = len(subset)
        c = subset['future_collapse'].sum()
        label = "ALIVE" if zpoc == 1 else "DEAD"
        print(f"  ZPOC {label}: {n} bars, collapse {c/n:.1%}")
    
    print("\n[By ACTION_MASK]")
    for mask in [0.0, 0.5, 1.0]:
        subset = df[df['action_mask'] == mask]
        n = len(subset)
        c = subset['future_collapse'].sum()
        print(f"  MASK={mask}: {n} bars ({n/total:.1%}), collapse {c/n:.1%}" if n > 0 else f"  MASK={mask}: 0 bars")
    
    print("\n[ACTION_MASK Effectiveness]")
    blocked = df[df['action_mask'] == 0]
    passed = df[df['action_mask'] >= 0.5]
    
    blocked_collapse = blocked['future_collapse'].sum() / len(blocked) if len(blocked) > 0 else 0
    passed_collapse = passed['future_collapse'].sum() / len(passed) if len(passed) > 0 else 0
    
    print(f"  Blocked area collapse rate: {blocked_collapse:.1%}")
    print(f"  Passed area collapse rate: {passed_collapse:.1%}")
    print(f"  Improvement: {blocked_collapse - passed_collapse:+.1%}")

def run_experiment():
    print("=" * 70)
    print("EXP-HYPOTHESIS-INVERSION-MAP-01")
    print("가설 비틀기 + 분포도 맵핑")
    print("=" * 70)
    
    for path in ["data/mnq_december_2025.csv", "data/mnq_with_ratio.csv"]:
        if os.path.exists(path):
            print(f"\nLoading: {path}")
            df = pd.read_csv(path)
            break
    else:
        print("ERROR: No data")
        return
    
    df.columns = df.columns.str.lower()
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    print(f"Loaded {len(df)} bars")
    
    print("\n[1] Computing bar-level labels...")
    labeled = compute_bar_level_labels(df)
    
    create_summary_stats(labeled)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("\n[2] Creating Connectivity Phase Maps...")
    create_connectivity_phase_map(labeled, 1, f"{OUTPUT_DIR}/map_connectivity_phase_zpoc1.png")
    create_connectivity_phase_map(labeled, 0, f"{OUTPUT_DIR}/map_connectivity_phase_zpoc0.png")
    
    print("\n[3] Creating ACTION_MASK Overlay Map...")
    create_actionmask_overlay_map(labeled, f"{OUTPUT_DIR}/map_actionmask_overlay.png")
    
    print("\n" + "=" * 70)
    print("COMPLETE")
    print("=" * 70)
    print(f"\nOutput files:")
    print(f"  {OUTPUT_DIR}/map_connectivity_phase_zpoc1.png")
    print(f"  {OUTPUT_DIR}/map_connectivity_phase_zpoc0.png")
    print(f"  {OUTPUT_DIR}/map_actionmask_overlay.png")

if __name__ == "__main__":
    run_experiment()
