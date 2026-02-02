"""
EXP-FORCE-RUPTURE-INDEX-01: Force Engine × Connectivity × IE 결합
==================================================================
혈류 모델: "피가 어디서 터지는지" 찾기

핵심 변수:
  - FF (Force Flux): 에너지 유량
  - PG (Pressure Gradient): 압력차 = FF / ECS
  - R (Resistance): 저항 = f(zpoc_dead, htf, recovery)
  - RI (Rupture Index): 파열 지표 = PG × R

논리:
  IE 범위 밖 → 세계 사망
  RI > θ → 혈관 파열
  그 외 → 정상 순환
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_force_rupture_index_01.json"

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
    
    df['state'] = 'NEUTRAL'
    df.loc[df['er'] > 0.7, 'state'] = 'TRENDING'
    df.loc[df['er'] < 0.3, 'state'] = 'CHOPPY'
    df['state_stable'] = (df['state'] == df['state'].shift(1)).astype(int)
    
    df['price_change'] = df['close'].diff().abs()
    df['delta'] = np.sign(df['close'] - df['open'])
    
    if 'volume' in df.columns:
        df['force_flux'] = df['price_change'] * df['volume'] * df['delta'].abs()
    else:
        df['force_flux'] = df['price_change'] * df['range']
    
    df['force_flux'] = df['force_flux'].rolling(5, min_periods=1).mean()
    
    return df

def compute_ie(df: pd.DataFrame, idx: int) -> float:
    start = max(0, idx - WINDOW_PRE)
    end = min(len(df), idx + WINDOW_POST + 1)
    window = df.iloc[start:end]
    
    if len(window) < 3:
        return 0.0
    
    fields = {
        'zpoc': window['zpoc_alive'].mean(),
        'htf': window['htf_alive'].mean(),
        'er': window['er'].mean() * (1 - window['er'].std()),
        'depth': 1.0 - min(1.0, window['depth'].std() * 3),
        'tau': window['tau_alive'].mean(),
        'range': max(0, 1.0 - window['range'].std() / max(window['range'].mean(), 0.01)),
        'recovery': min(1.0, window['recovery'].sum()),
        'state': window['state_stable'].mean()
    }
    
    field_values = list(fields.values())
    ie = sum(field_values) - np.var(field_values)
    
    if fields['zpoc'] < 0.3 and fields['er'] > 0.6:
        ie -= 1.0
    if fields['zpoc'] < 0.3 and sum(field_values) > 4.0:
        ie -= 1.5
    
    return ie

def compute_ecs_v2(row: pd.Series) -> float:
    ecs = (
        ECS_WEIGHTS['zpoc_alive'] * row['zpoc_alive'] +
        ECS_WEIGHTS['htf_alive'] * row['htf_alive'] +
        ECS_WEIGHTS['tau_alive'] * row['tau_alive'] +
        ECS_WEIGHTS['state_stable'] * row['state_stable'] +
        ECS_WEIGHTS['range_alive'] * row['range_alive'] +
        ECS_WEIGHTS['recovery'] * row['recovery'] +
        ECS_WEIGHTS['er_alive'] * row['er_alive'] +
        ECS_WEIGHTS['depth_alive'] * row['depth_alive']
    )
    return ecs

def compute_rupture_index(force_flux: float, ecs: float, zpoc_dead: int, 
                          htf_alive: int, recovery: int) -> Tuple[float, float, float]:
    pg = force_flux / max(ecs + 2.0, 0.1)
    
    r = 1.0
    if zpoc_dead:
        r += 2.0
    if htf_alive:
        r += 0.5
    if recovery:
        r += 1.0
    
    ri = pg * r
    
    return ri, pg, r

def compute_collapse_label(df: pd.DataFrame, idx: int, lookforward: int = 30) -> int:
    if idx + lookforward >= len(df):
        return 0
    
    future = df.iloc[idx:idx + lookforward + 1]
    er_min = future['er'].min()
    er_drop = df['er'].iloc[idx] - er_min
    price_drop = (df['close'].iloc[idx] - future['low'].min()) / max(df['range'].iloc[idx], 0.01)
    
    conditions_met = sum([er_min < 0.15, er_drop > 0.50, price_drop > 5.0])
    return 1 if conditions_met >= 2 else 0

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-FORCE-RUPTURE-INDEX-01")
    print("Force Engine × Connectivity × IE: 혈류 파열 모델")
    print("=" * 70)
    
    print("\n[1] Computing all indicators...")
    df = compute_all_indicators(df)
    
    print("\n[2] Computing IE, ECS, RI for each sample...")
    
    results_list = []
    sample_indices = range(WINDOW_PRE + 30, len(df) - 30, 3)
    
    for idx in sample_indices:
        row = df.iloc[idx]
        
        ie = compute_ie(df, idx)
        ecs = compute_ecs_v2(row)
        ri, pg, r = compute_rupture_index(
            row['force_flux'], ecs,
            1 - row['zpoc_alive'], row['htf_alive'], row['recovery']
        )
        collapse = compute_collapse_label(df, idx)
        
        results_list.append({
            'idx': idx,
            'ie': ie,
            'ecs': ecs,
            'ri': ri,
            'pg': pg,
            'resistance': r,
            'force_flux': row['force_flux'],
            'zpoc_alive': row['zpoc_alive'],
            'htf_alive': row['htf_alive'],
            'recovery': row['recovery'],
            'collapse': collapse
        })
    
    results_df = pd.DataFrame(results_list)
    print(f"  Computed {len(results_df)} samples")
    
    print("\n[3] RI Distribution Analysis...")
    
    ri_q50 = results_df['ri'].quantile(0.50)
    ri_q75 = results_df['ri'].quantile(0.75)
    ri_q90 = results_df['ri'].quantile(0.90)
    ri_q95 = results_df['ri'].quantile(0.95)
    
    print(f"\n  RI Quantiles:")
    print(f"    50%: {ri_q50:.2f}")
    print(f"    75%: {ri_q75:.2f}")
    print(f"    90%: {ri_q90:.2f}")
    print(f"    95%: {ri_q95:.2f}")
    
    print("\n[4] RI by ZPOC status...")
    
    zpoc_alive = results_df[results_df['zpoc_alive'] == 1]
    zpoc_dead = results_df[results_df['zpoc_alive'] == 0]
    
    print(f"\n  ZPOC ALIVE (n={len(zpoc_alive)}):")
    print(f"    RI mean: {zpoc_alive['ri'].mean():.2f}")
    print(f"    RI std: {zpoc_alive['ri'].std():.2f}")
    print(f"    Collapse rate: {zpoc_alive['collapse'].mean():.1%}")
    
    print(f"\n  ZPOC DEAD (n={len(zpoc_dead)}):")
    print(f"    RI mean: {zpoc_dead['ri'].mean():.2f}")
    print(f"    RI std: {zpoc_dead['ri'].std():.2f}")
    print(f"    Collapse rate: {zpoc_dead['collapse'].mean():.1%}")
    
    print("\n[5] RI Threshold Analysis...")
    
    thresholds = [ri_q50, ri_q75, ri_q90, ri_q95]
    threshold_labels = ['50%', '75%', '90%', '95%']
    
    print("\n  RI > Threshold → Collapse Rate:")
    for thresh, label in zip(thresholds, threshold_labels):
        high_ri = results_df[results_df['ri'] > thresh]
        low_ri = results_df[results_df['ri'] <= thresh]
        if len(high_ri) > 0 and len(low_ri) > 0:
            print(f"    RI > {label} ({thresh:.2f}): {high_ri['collapse'].mean():.1%} (n={len(high_ri)}) vs {low_ri['collapse'].mean():.1%} (n={len(low_ri)})")
    
    print("\n[6] Combined IE + RI Analysis...")
    
    ie_valid = results_df[(results_df['ie'] >= 2.0) & (results_df['ie'] <= 4.5)]
    ie_invalid = results_df[(results_df['ie'] < 2.0) | (results_df['ie'] > 4.5)]
    
    print(f"\n  IE 2.0-4.5 (Valid World): {len(ie_valid)} samples, Collapse {ie_valid['collapse'].mean():.1%}")
    print(f"  IE outside (Invalid): {len(ie_invalid)} samples, Collapse {ie_invalid['collapse'].mean():.1%}")
    
    ri_thresh = ri_q75
    
    safe_zone = ie_valid[ie_valid['ri'] <= ri_thresh]
    danger_zone = ie_valid[ie_valid['ri'] > ri_thresh]
    
    print(f"\n  Within Valid IE:")
    print(f"    RI ≤ {ri_thresh:.2f}: Collapse {safe_zone['collapse'].mean():.1%} (n={len(safe_zone)})")
    print(f"    RI > {ri_thresh:.2f}: Collapse {danger_zone['collapse'].mean():.1%} (n={len(danger_zone)})")
    
    print("\n" + "=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)
    
    total_safe = len(safe_zone)
    total = len(results_df)
    safe_collapse = safe_zone['collapse'].mean() if len(safe_zone) > 0 else 0
    all_collapse = results_df['collapse'].mean()
    
    print(f"\n  전체 → Safe Zone: {total} → {total_safe} ({total_safe/total*100:.1f}%)")
    print(f"  Collapse Rate: {all_collapse:.1%} → {safe_collapse:.1%}")
    print(f"  → Collapse 감소: {(all_collapse - safe_collapse)*100:.1f}%p")
    
    return {
        'experiment': 'EXP-FORCE-RUPTURE-INDEX-01',
        'timestamp': datetime.now().isoformat(),
        'ri_quantiles': {
            'q50': ri_q50, 'q75': ri_q75, 'q90': ri_q90, 'q95': ri_q95
        },
        'zpoc_analysis': {
            'alive_ri_mean': zpoc_alive['ri'].mean(),
            'dead_ri_mean': zpoc_dead['ri'].mean(),
            'alive_collapse': zpoc_alive['collapse'].mean(),
            'dead_collapse': zpoc_dead['collapse'].mean()
        },
        'safe_zone': {
            'count': len(safe_zone),
            'collapse_rate': safe_collapse,
            'ie_range': '2.0-4.5',
            'ri_threshold': ri_thresh
        }
    }, results_df

def create_rupture_visualizations(results_df: pd.DataFrame, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    zpoc_alive = results_df[results_df['zpoc_alive'] == 1]['ri']
    zpoc_dead = results_df[results_df['zpoc_alive'] == 0]['ri']
    ax1.hist(zpoc_alive, bins=50, alpha=0.6, label=f'ZPOC Alive (n={len(zpoc_alive)})', color='green')
    ax1.hist(zpoc_dead, bins=50, alpha=0.6, label=f'ZPOC Dead (n={len(zpoc_dead)})', color='red')
    ax1.set_xlabel('Rupture Index (RI)')
    ax1.set_ylabel('Frequency')
    ax1.set_title('RI Distribution by ZPOC Status')
    ax1.legend()
    ax1.axvline(x=results_df['ri'].quantile(0.75), color='black', linestyle='--', alpha=0.5)
    
    ax2 = axes[0, 1]
    sample = results_df.sample(min(800, len(results_df)), random_state=42)
    scatter = ax2.scatter(sample['ie'], sample['ri'], 
                         c=sample['collapse'], cmap='RdYlGn_r', alpha=0.5, s=20)
    ax2.set_xlabel('Intersection Energy (IE)')
    ax2.set_ylabel('Rupture Index (RI)')
    ax2.set_title('IE vs RI Phase Map (color = Collapse)')
    ax2.axvline(x=2.0, color='blue', linestyle='--', alpha=0.5)
    ax2.axvline(x=4.5, color='blue', linestyle='--', alpha=0.5)
    ax2.axhline(y=results_df['ri'].quantile(0.75), color='red', linestyle='--', alpha=0.5)
    plt.colorbar(scatter, ax=ax2, label='Collapse')
    
    ax3 = axes[1, 0]
    ri_bins = np.percentile(results_df['ri'], [0, 25, 50, 75, 90, 100])
    ri_labels = ['0-25%', '25-50%', '50-75%', '75-90%', '90-100%']
    results_df['ri_bucket'] = pd.cut(results_df['ri'], bins=ri_bins, labels=ri_labels, duplicates='drop')
    
    bucket_stats = results_df.groupby('ri_bucket', observed=True)['collapse'].agg(['mean', 'count'])
    
    colors = plt.cm.RdYlGn_r(bucket_stats['mean'].values)
    bars = ax3.bar(range(len(bucket_stats)), bucket_stats['mean'], color=colors, alpha=0.8)
    ax3.set_xticks(range(len(bucket_stats)))
    ax3.set_xticklabels(bucket_stats.index)
    ax3.set_xlabel('RI Percentile Bucket')
    ax3.set_ylabel('Collapse Rate')
    ax3.set_title('Collapse Rate by RI Bucket')
    ax3.set_ylim(0, 1)
    
    for bar, (_, row) in zip(bars, bucket_stats.iterrows()):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{row["mean"]:.0%}\n({int(row["count"])})', ha='center', fontsize=8)
    
    ax4 = axes[1, 1]
    
    ie_valid = results_df[(results_df['ie'] >= 2.0) & (results_df['ie'] <= 4.5)]
    ie_invalid = results_df[(results_df['ie'] < 2.0) | (results_df['ie'] > 4.5)]
    ri_thresh = results_df['ri'].quantile(0.75)
    safe = ie_valid[ie_valid['ri'] <= ri_thresh]
    danger = ie_valid[ie_valid['ri'] > ri_thresh]
    
    zones = ['All', 'IE Invalid', 'IE Valid\n+ RI High', 'IE Valid\n+ RI Low\n(SAFE)']
    collapse_rates = [
        results_df['collapse'].mean(),
        ie_invalid['collapse'].mean() if len(ie_invalid) > 0 else 0,
        danger['collapse'].mean() if len(danger) > 0 else 0,
        safe['collapse'].mean() if len(safe) > 0 else 0
    ]
    counts = [len(results_df), len(ie_invalid), len(danger), len(safe)]
    colors = ['gray', 'red', 'orange', 'green']
    
    bars = ax4.bar(zones, collapse_rates, color=colors, alpha=0.7)
    ax4.set_ylabel('Collapse Rate')
    ax4.set_title('Zone Filtering: IE + RI')
    ax4.set_ylim(0, 1)
    
    for bar, rate, count in zip(bars, collapse_rates, counts):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{rate:.1%}\n(n={count})', ha='center', fontsize=9)
    
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
    
    results, results_df = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[7] Creating visualizations...")
    create_rupture_visualizations(results_df, f"{OUTPUT_DIR}/rupture_index_analysis.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
