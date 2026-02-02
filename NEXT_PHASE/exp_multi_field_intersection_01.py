"""
EXP-MULTI-FIELD-INTERSECTION-01: Intersection Energy (IE) 실험
===============================================================
목적: Storm의 "실체 강도"를 다차원 교집합에서 수치화

8차원 Field:
  1. ZPOC Field - 기준 필드
  2. HTF Field - 상위 파동 필드  
  3. ER Field - 에너지 필드
  4. Depth Field - 저항 필드
  5. τ Field - 시간 응력 필드
  6. Range Field - 압축/팽창 필드
  7. Recovery Field - 복원력 필드
  8. State Field - 국면 필드

IE = Σ Field_i - α·Var(Field_i) - β·ConflictPenalty
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_multi_field_intersection_01.json"

WINDOW_PRE = 5
WINDOW_POST = 5
ALPHA = 1.0
BETA = 1.0

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

def compute_base_indicators(df: pd.DataFrame) -> pd.DataFrame:
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
    df.loc[(df['er'] >= 0.3) & (df['er'] <= 0.7), 'state'] = 'NEUTRAL'
    
    return df

def compute_field_scores(df: pd.DataFrame, center_idx: int) -> Dict[str, float]:
    """Storm Window에서 8개 Field Score 계산"""
    
    start = max(0, center_idx - WINDOW_PRE)
    end = min(len(df), center_idx + WINDOW_POST + 1)
    window = df.iloc[start:end]
    
    if len(window) < 3:
        return {f: 0.0 for f in ['zpoc', 'htf', 'er', 'depth', 'tau', 'range', 'recovery', 'state']}
    
    fields = {}
    
    fields['zpoc'] = window['zpoc_alive'].mean()
    fields['htf'] = window['htf_alive'].mean()
    fields['er'] = window['er'].mean() * (1 - window['er'].std())
    
    depth_stability = 1.0 - min(1.0, window['depth'].std() * 3)
    fields['depth'] = depth_stability
    
    fields['tau'] = window['tau_alive'].mean()
    
    range_cv = window['range'].std() / max(window['range'].mean(), 0.01)
    fields['range'] = max(0, 1.0 - range_cv)
    
    fields['recovery'] = min(1.0, window['recovery'].sum())
    
    center_state = df['state'].iloc[center_idx]
    same_state = (window['state'] == center_state).mean()
    fields['state'] = same_state
    
    return fields

def compute_conflict_penalty(fields: Dict[str, float]) -> float:
    """충돌 패널티: "강한데 기준 없음" 상태"""
    penalty = 0.0
    
    if fields['zpoc'] < 0.3 and fields['er'] > 0.6:
        penalty += 1.0
    
    if fields['htf'] == 0 and fields['tau'] > 0.7:
        penalty += 0.5
    
    if fields['zpoc'] < 0.3 and sum(fields.values()) > 4.0:
        penalty += 1.5
    
    if fields['er'] > 0.7 and fields['depth'] < 0.3:
        penalty += 0.5
    
    return penalty

def compute_intersection_energy(fields: Dict[str, float], alpha: float = ALPHA, beta: float = BETA) -> float:
    """IE = Σ Field_i - α·Var(Field_i) - β·ConflictPenalty"""
    
    field_values = list(fields.values())
    field_sum = sum(field_values)
    field_var = np.var(field_values)
    conflict = compute_conflict_penalty(fields)
    
    ie = field_sum - alpha * field_var - beta * conflict
    
    return ie

def compute_collapse_label(df: pd.DataFrame, idx: int, lookforward: int = 30) -> int:
    """Strict collapse 라벨"""
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
    print("EXP-MULTI-FIELD-INTERSECTION-01")
    print("Intersection Energy (IE) 다차원 교집합 실험")
    print("=" * 70)
    
    print("\n[1] Computing base indicators...")
    df = compute_base_indicators(df)
    
    print("\n[2] Computing Field Scores & IE for each bar...")
    
    all_ie = []
    all_fields = []
    all_collapse = []
    
    sample_indices = range(WINDOW_PRE + 30, len(df) - 30, 3)
    
    for idx in sample_indices:
        fields = compute_field_scores(df, idx)
        ie = compute_intersection_energy(fields)
        collapse = compute_collapse_label(df, idx)
        
        all_ie.append(ie)
        all_fields.append(fields)
        all_collapse.append(collapse)
    
    print(f"  Computed {len(all_ie)} samples")
    
    ie_df = pd.DataFrame({
        'ie': all_ie,
        'collapse': all_collapse,
        **{f'field_{k}': [f[k] for f in all_fields] for k in all_fields[0].keys()}
    })
    
    print("\n[3] Analyzing IE distribution...")
    
    ie_bins = [-np.inf, 2.0, 3.0, 4.0, 5.0, 6.0, np.inf]
    ie_labels = ['<2', '2-3', '3-4', '4-5', '5-6', '>6']
    ie_df['ie_bucket'] = pd.cut(ie_df['ie'], bins=ie_bins, labels=ie_labels)
    
    bucket_stats = ie_df.groupby('ie_bucket', observed=True).agg({
        'collapse': ['mean', 'count']
    }).round(3)
    bucket_stats.columns = ['collapse_rate', 'count']
    
    print("\n  IE Bucket Analysis:")
    print("  " + "-" * 40)
    for bucket in ie_labels:
        if bucket in bucket_stats.index:
            row = bucket_stats.loc[bucket]
            print(f"  IE {bucket}: Collapse {row['collapse_rate']:.1%} (n={int(row['count'])})")
    
    print("\n[4] Field Importance Analysis...")
    
    collapse_1 = ie_df[ie_df['collapse'] == 1]
    collapse_0 = ie_df[ie_df['collapse'] == 0]
    
    field_names = ['zpoc', 'htf', 'er', 'depth', 'tau', 'range', 'recovery', 'state']
    field_importance = {}
    
    print("\n  Field Score Comparison (Collapse vs Non-Collapse):")
    print("  " + "-" * 50)
    for field in field_names:
        col = f'field_{field}'
        mean_collapse = collapse_1[col].mean()
        mean_non_collapse = collapse_0[col].mean()
        diff = mean_non_collapse - mean_collapse
        field_importance[field] = diff
        print(f"  {field.upper():12} | Collapse: {mean_collapse:.3f} | Non-Collapse: {mean_non_collapse:.3f} | Δ: {diff:+.3f}")
    
    sorted_importance = sorted(field_importance.items(), key=lambda x: abs(x[1]), reverse=True)
    print("\n  Field Importance Ranking:")
    for i, (field, diff) in enumerate(sorted_importance, 1):
        direction = "↑ (stabilizer)" if diff > 0 else "↓ (destabilizer)"
        print(f"  {i}. {field.upper()}: {diff:+.3f} {direction}")
    
    print("\n" + "=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)
    
    low_ie = ie_df[ie_df['ie'] < 3.0]['collapse'].mean()
    high_ie = ie_df[ie_df['ie'] >= 5.0]['collapse'].mean()
    
    print(f"\n  IE < 3.0: Collapse {low_ie:.1%}")
    print(f"  IE >= 5.0: Collapse {high_ie:.1%}")
    print(f"  → Separation: {(low_ie - high_ie)*100:.1f}%p")
    
    results = {
        'experiment': 'EXP-MULTI-FIELD-INTERSECTION-01',
        'timestamp': datetime.now().isoformat(),
        'settings': {
            'window_pre': WINDOW_PRE,
            'window_post': WINDOW_POST,
            'alpha': ALPHA,
            'beta': BETA
        },
        'bucket_stats': bucket_stats.to_dict(),
        'field_importance': field_importance,
        'key_findings': {
            'low_ie_collapse': low_ie,
            'high_ie_collapse': high_ie,
            'separation': low_ie - high_ie
        }
    }
    
    return results, ie_df

def create_ie_visualizations(ie_df: pd.DataFrame, filename: str):
    """IE 분포 시각화"""
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    collapse_0 = ie_df[ie_df['collapse'] == 0]['ie']
    collapse_1 = ie_df[ie_df['collapse'] == 1]['ie']
    ax1.hist(collapse_0, bins=30, alpha=0.6, label=f'Non-Collapse (n={len(collapse_0)})', color='green')
    ax1.hist(collapse_1, bins=30, alpha=0.6, label=f'Collapse (n={len(collapse_1)})', color='red')
    ax1.set_xlabel('Intersection Energy (IE)')
    ax1.set_ylabel('Frequency')
    ax1.set_title('IE Distribution by Collapse')
    ax1.legend()
    ax1.axvline(x=4.0, color='black', linestyle='--', alpha=0.5, label='Threshold')
    
    ax2 = axes[0, 1]
    ie_bins = [-np.inf, 2.0, 3.0, 4.0, 5.0, 6.0, np.inf]
    ie_labels = ['<2', '2-3', '3-4', '4-5', '5-6', '>6']
    ie_df['ie_bucket'] = pd.cut(ie_df['ie'], bins=ie_bins, labels=ie_labels)
    
    bucket_stats = ie_df.groupby('ie_bucket', observed=True)['collapse'].agg(['mean', 'count'])
    
    colors = plt.cm.RdYlGn_r(bucket_stats['mean'].values)
    bars = ax2.bar(range(len(bucket_stats)), bucket_stats['mean'], color=colors, alpha=0.8)
    ax2.set_xticks(range(len(bucket_stats)))
    ax2.set_xticklabels(bucket_stats.index)
    ax2.set_xlabel('IE Bucket')
    ax2.set_ylabel('Collapse Rate')
    ax2.set_title('Collapse Rate by IE Bucket')
    ax2.set_ylim(0, 1)
    ax2.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
    
    for bar, (_, row) in zip(bars, bucket_stats.iterrows()):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{row["mean"]:.0%}\n({int(row["count"])})', ha='center', fontsize=8)
    
    ax3 = axes[1, 0]
    field_names = ['zpoc', 'htf', 'er', 'depth', 'tau', 'range', 'recovery', 'state']
    
    collapse_means = [ie_df[ie_df['collapse'] == 1][f'field_{f}'].mean() for f in field_names]
    non_collapse_means = [ie_df[ie_df['collapse'] == 0][f'field_{f}'].mean() for f in field_names]
    
    x = np.arange(len(field_names))
    width = 0.35
    ax3.bar(x - width/2, collapse_means, width, label='Collapse', color='red', alpha=0.7)
    ax3.bar(x + width/2, non_collapse_means, width, label='Non-Collapse', color='green', alpha=0.7)
    ax3.set_xticks(x)
    ax3.set_xticklabels([f.upper() for f in field_names], rotation=45, ha='right')
    ax3.set_ylabel('Field Score')
    ax3.set_title('Field Scores: Collapse vs Non-Collapse')
    ax3.legend()
    
    ax4 = axes[1, 1]
    sample = ie_df.sample(min(500, len(ie_df)), random_state=42)
    scatter = ax4.scatter(sample['field_zpoc'], sample['ie'], 
                         c=sample['collapse'], cmap='RdYlGn_r', alpha=0.5, s=20)
    ax4.set_xlabel('ZPOC Field Score')
    ax4.set_ylabel('Intersection Energy (IE)')
    ax4.set_title('ZPOC vs IE (color = Collapse)')
    plt.colorbar(scatter, ax=ax4, label='Collapse')
    
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
    
    results, ie_df = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[5] Creating visualizations...")
    create_ie_visualizations(ie_df, f"{OUTPUT_DIR}/ie_distribution_analysis.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
