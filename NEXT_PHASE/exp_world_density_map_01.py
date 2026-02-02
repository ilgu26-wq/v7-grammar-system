"""
EXP-WORLD-DENSITY-MAP-01: 세계 구조 패턴 분포화
==============================================
4D 좌표계: (IE, RI, ECS, ZPOC)
→ 2D 슬라이스로 투영하여 세계 패턴 발견

예상 패턴:
  - Pattern A: Stable Basin (안정 분지) - 미시 가능
  - Pattern B: Rupture Ridge (파열 능선) - 금지
  - Pattern C: Noise Field (노이즈 장) - 무의미
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_world_density_map_01.json"

WINDOW_PRE = 5
WINDOW_POST = 5

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

def compute_collapse_label(df: pd.DataFrame, idx: int, lookforward: int = 30) -> int:
    if idx + lookforward >= len(df):
        return 0
    
    future = df.iloc[idx:idx + lookforward + 1]
    er_min = future['er'].min()
    er_drop = df['er'].iloc[idx] - er_min
    price_drop = (df['close'].iloc[idx] - future['low'].min()) / max(df['range'].iloc[idx], 0.01)
    
    conditions_met = sum([er_min < 0.15, er_drop > 0.50, price_drop > 5.0])
    return 1 if conditions_met >= 2 else 0

def classify_world_pattern(ie: float, ri: float, ecs: float, zpoc: int, ri_q75: float, ri_q90: float) -> str:
    if zpoc == 0 or ri > ri_q90:
        return 'RUPTURE_RIDGE'
    
    if ie < 2.0 or ie > 4.5 or ecs < 0:
        return 'NOISE_FIELD'
    
    if 2.3 <= ie <= 3.8 and ri < ri_q75 and ecs > 1.0 and zpoc == 1:
        return 'STABLE_BASIN'
    
    if 2.0 <= ie <= 4.5 and ri < ri_q90:
        return 'TRANSITION_ZONE'
    
    return 'NOISE_FIELD'

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-WORLD-DENSITY-MAP-01")
    print("세계 구조 패턴 분포화 매핑")
    print("=" * 70)
    
    print("\n[1] Computing all indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q90 = df['ri'].quantile(0.90)
    ri_q95 = df['ri'].quantile(0.95)
    
    print(f"  RI Quantiles: q75={ri_q75:.2f}, q90={ri_q90:.2f}, q95={ri_q95:.2f}")
    
    print("\n[2] Computing 4D coordinates for each bar...")
    
    results = []
    sample_indices = range(WINDOW_PRE + 30, len(df) - 30, 2)
    
    for idx in sample_indices:
        ie = compute_ie(df, idx)
        ri = df['ri'].iloc[idx]
        ecs = df['ecs'].iloc[idx]
        zpoc = df['zpoc_alive'].iloc[idx]
        collapse = compute_collapse_label(df, idx)
        
        pattern = classify_world_pattern(ie, ri, ecs, zpoc, ri_q75, ri_q90)
        
        results.append({
            'ie': ie,
            'ri': ri,
            'ecs': ecs,
            'zpoc': zpoc,
            'collapse': collapse,
            'pattern': pattern
        })
    
    world_df = pd.DataFrame(results)
    print(f"  Computed {len(world_df)} samples")
    
    print("\n[3] Pattern Distribution...")
    
    pattern_stats = world_df.groupby('pattern').agg({
        'collapse': ['mean', 'count']
    }).round(3)
    pattern_stats.columns = ['collapse_rate', 'count']
    pattern_stats['pct'] = pattern_stats['count'] / len(world_df) * 100
    
    print("\n  Pattern Statistics:")
    print("  " + "-" * 60)
    for pattern in ['STABLE_BASIN', 'TRANSITION_ZONE', 'RUPTURE_RIDGE', 'NOISE_FIELD']:
        if pattern in pattern_stats.index:
            row = pattern_stats.loc[pattern]
            print(f"  {pattern:<20}: {row['collapse_rate']:.1%} collapse, {row['count']:.0f} bars ({row['pct']:.1f}%)")
    
    print("\n[4] Micro-Scalping Eligibility...")
    
    stable = world_df[world_df['pattern'] == 'STABLE_BASIN']
    transition = world_df[world_df['pattern'] == 'TRANSITION_ZONE']
    rupture = world_df[world_df['pattern'] == 'RUPTURE_RIDGE']
    noise = world_df[world_df['pattern'] == 'NOISE_FIELD']
    
    print(f"\n  STABLE_BASIN (미시 가능): {len(stable)} bars ({len(stable)/len(world_df)*100:.1f}%)")
    print(f"    Collapse Rate: {stable['collapse'].mean():.1%}")
    print(f"    IE Range: {stable['ie'].min():.2f} - {stable['ie'].max():.2f}")
    print(f"    RI Range: {stable['ri'].min():.2f} - {stable['ri'].max():.2f}")
    
    if len(rupture) > 0:
        print(f"\n  RUPTURE_RIDGE (금지): {len(rupture)} bars ({len(rupture)/len(world_df)*100:.1f}%)")
        print(f"    Collapse Rate: {rupture['collapse'].mean():.1%}")
    
    print("\n" + "=" * 70)
    print("WORLD STRUCTURE SUMMARY")
    print("=" * 70)
    
    baseline = world_df['collapse'].mean()
    stable_cr = stable['collapse'].mean() if len(stable) > 0 else 0
    rupture_cr = rupture['collapse'].mean() if len(rupture) > 0 else 0
    
    print(f"\n  Baseline Collapse: {baseline:.1%}")
    print(f"  STABLE_BASIN: {stable_cr:.1%} (Δ={stable_cr - baseline:+.1%}p)")
    print(f"  RUPTURE_RIDGE: {rupture_cr:.1%} (Δ={rupture_cr - baseline:+.1%}p)")
    print(f"\n  분리력: {(rupture_cr - stable_cr)*100:.1f}%p")
    
    return {
        'experiment': 'EXP-WORLD-DENSITY-MAP-01',
        'timestamp': datetime.now().isoformat(),
        'pattern_stats': pattern_stats.to_dict(),
        'thresholds': {'ri_q75': ri_q75, 'ri_q90': ri_q90, 'ri_q95': ri_q95},
        'summary': {
            'baseline_collapse': baseline,
            'stable_basin_collapse': stable_cr,
            'rupture_ridge_collapse': rupture_cr,
            'separation': rupture_cr - stable_cr
        }
    }, world_df

def create_density_maps(world_df: pd.DataFrame, filename: str):
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    
    ax1 = axes[0, 0]
    sample = world_df.sample(min(1000, len(world_df)), random_state=42)
    scatter = ax1.scatter(sample['ie'], sample['ri'].clip(upper=sample['ri'].quantile(0.95)),
                         c=sample['collapse'], cmap='RdYlGn_r', alpha=0.5, s=15)
    ax1.set_xlabel('IE (World Energy)')
    ax1.set_ylabel('RI (Rupture Index)')
    ax1.set_title('Slice 1: World Survival Plane\nIE vs RI')
    ax1.axvline(x=2.0, color='blue', linestyle='--', alpha=0.5)
    ax1.axvline(x=4.5, color='blue', linestyle='--', alpha=0.5)
    ax1.axhline(y=world_df['ri'].quantile(0.90), color='red', linestyle='--', alpha=0.5)
    plt.colorbar(scatter, ax=ax1, label='Collapse')
    
    ax2 = axes[0, 1]
    scatter2 = ax2.scatter(sample['ecs'], sample['ri'].clip(upper=sample['ri'].quantile(0.95)),
                          c=sample['collapse'], cmap='RdYlGn_r', alpha=0.5, s=15)
    ax2.set_xlabel('ECS (Connectivity Quality)')
    ax2.set_ylabel('RI (Rupture Index)')
    ax2.set_title('Slice 2: Structure Quality Plane\nECS vs RI')
    ax2.axvline(x=1.0, color='green', linestyle='--', alpha=0.5)
    plt.colorbar(scatter2, ax=ax2, label='Collapse')
    
    ax3 = axes[0, 2]
    scatter3 = ax3.scatter(sample['ie'], sample['ecs'],
                          c=sample['collapse'], cmap='RdYlGn_r', alpha=0.5, s=15)
    ax3.set_xlabel('IE (World Energy)')
    ax3.set_ylabel('ECS (Connectivity Quality)')
    ax3.set_title('Slice 3: World Depth Plane\nIE vs ECS')
    ax3.axvline(x=2.0, color='blue', linestyle='--', alpha=0.5)
    ax3.axvline(x=4.5, color='blue', linestyle='--', alpha=0.5)
    ax3.axhline(y=1.0, color='green', linestyle='--', alpha=0.5)
    plt.colorbar(scatter3, ax=ax3, label='Collapse')
    
    ax4 = axes[1, 0]
    patterns = ['STABLE_BASIN', 'TRANSITION_ZONE', 'RUPTURE_RIDGE', 'NOISE_FIELD']
    collapse_rates = []
    counts = []
    for p in patterns:
        subset = world_df[world_df['pattern'] == p]
        collapse_rates.append(subset['collapse'].mean() if len(subset) > 0 else 0)
        counts.append(len(subset))
    
    colors = ['green', 'yellow', 'red', 'gray']
    bars = ax4.bar(range(len(patterns)), collapse_rates, color=colors, alpha=0.7)
    ax4.set_xticks(range(len(patterns)))
    ax4.set_xticklabels(['STABLE\nBASIN', 'TRANSITION\nZONE', 'RUPTURE\nRIDGE', 'NOISE\nFIELD'])
    ax4.set_ylabel('Collapse Rate')
    ax4.set_title('World Pattern Classification')
    ax4.set_ylim(0, 1)
    ax4.axhline(y=world_df['collapse'].mean(), color='black', linestyle='--', alpha=0.5)
    
    for bar, rate, count in zip(bars, collapse_rates, counts):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{rate:.0%}\n(n={count})', ha='center', fontsize=8)
    
    ax5 = axes[1, 1]
    pattern_colors = {'STABLE_BASIN': 'green', 'TRANSITION_ZONE': 'yellow', 
                     'RUPTURE_RIDGE': 'red', 'NOISE_FIELD': 'gray'}
    for pattern, color in pattern_colors.items():
        subset = sample[sample['pattern'] == pattern]
        if len(subset) > 0:
            ax5.scatter(subset['ie'], subset['ri'].clip(upper=sample['ri'].quantile(0.95)),
                       c=color, alpha=0.5, s=15, label=pattern)
    ax5.set_xlabel('IE')
    ax5.set_ylabel('RI')
    ax5.set_title('Pattern Distribution in IE-RI Space')
    ax5.legend(loc='upper right', fontsize=8)
    
    ax6 = axes[1, 2]
    ie_bins = [0, 2.0, 2.3, 3.0, 3.8, 4.5, 10]
    ie_labels = ['<2.0', '2.0-2.3', '2.3-3.0', '3.0-3.8', '3.8-4.5', '>4.5']
    world_df['ie_bucket'] = pd.cut(world_df['ie'], bins=ie_bins, labels=ie_labels)
    
    ie_stats = world_df.groupby('ie_bucket', observed=True)['collapse'].agg(['mean', 'count'])
    
    colors = plt.cm.RdYlGn_r(ie_stats['mean'].values)
    bars = ax6.bar(range(len(ie_stats)), ie_stats['mean'], color=colors, alpha=0.8)
    ax6.set_xticks(range(len(ie_stats)))
    ax6.set_xticklabels(ie_stats.index)
    ax6.set_xlabel('IE Range')
    ax6.set_ylabel('Collapse Rate')
    ax6.set_title('IE U-Curve (Optimal: 2.3-3.8)')
    ax6.set_ylim(0, 1)
    
    for bar, (_, row) in zip(bars, ie_stats.iterrows()):
        ax6.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{row["mean"]:.0%}', ha='center', fontsize=8)
    
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
    
    results, world_df = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[5] Creating density maps...")
    create_density_maps(world_df, f"{OUTPUT_DIR}/world_density_map.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
