"""
EXP-RATIO-VS-CONNECTIVITY-COMPARE-01: 통합배율 vs Connectivity 비교
====================================================================
통합배율 철학:
  배율 = (close - low) / (high - close) = buyer / seller
  → 1.5+ = 과매수 (하락 예상)
  → 0.7- = 과매도 (상승 예상)

비교:
  1. 배율 기반 분포도
  2. Connectivity 기반 분포도
  3. 두 시스템 중첩 맵
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict
import os

OUTPUT_DIR = "v7-grammar-system/images"

WEIGHTS = {
    'zpoc_alive': 2.0, 'htf_alive': -1.5, 'range_alive': 1.0,
    'depth_alive': 0.8, 'tau_alive': 0.5, 'er_alive': 0.3
}

def calc_ratio(df: pd.DataFrame) -> pd.Series:
    """통합배율: (close - low) / (high - close)"""
    buyer = df['close'] - df['low']
    seller = df['high'] - df['close']
    seller = seller.replace(0, 0.01)
    ratio = (buyer / seller).clip(0, 10)
    return ratio

def calc_cumulative_ratio(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """누적배율: sum(buyer_N봉) / sum(seller_N봉)"""
    buyer = df['close'] - df['low']
    seller = df['high'] - df['close']
    cum_buyer = buyer.rolling(lookback, min_periods=1).sum()
    cum_seller = seller.rolling(lookback, min_periods=1).sum().replace(0, 0.01)
    return (cum_buyer / cum_seller).clip(0, 10)

def calc_channel_pct(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """채널%: (close - 20봉저점) / (20봉고점 - 20봉저점) * 100"""
    rolling_low = df['low'].rolling(lookback, min_periods=1).min()
    rolling_high = df['high'].rolling(lookback, min_periods=1).max()
    channel_range = rolling_high - rolling_low
    channel_range = channel_range.replace(0, 0.01)
    return ((df['close'] - rolling_low) / channel_range * 100).clip(0, 100)

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

def compute_all_labels(df: pd.DataFrame, lookforward: int = 30) -> pd.DataFrame:
    df = df.copy()
    df['range'] = df['high'] - df['low']
    
    df['ratio'] = calc_ratio(df)
    df['cum_ratio'] = calc_cumulative_ratio(df)
    df['channel_pct'] = calc_channel_pct(df)
    
    df['ratio_zone'] = 'NEUTRAL'
    df.loc[df['ratio'] > 1.5, 'ratio_zone'] = 'OVERBOUGHT'
    df.loc[df['ratio'] < 0.7, 'ratio_zone'] = 'OVERSOLD'
    
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
    
    df['alive_count'] = (df['zpoc_alive'] + df['htf_alive'] + df['depth_alive'] + 
                         df['er_alive'] + df['range_alive'] + df['tau_alive'])
    
    df['ecs'] = sum(WEIGHTS[k] * df[k] for k in WEIGHTS)
    penalty = ((df['alive_count'] >= 5) & (df['htf_alive'] == 1)).astype(float) * 1.5
    df['ecs_penalized'] = df['ecs'] - penalty
    
    df['future_collapse'] = 0
    for i in range(len(df) - lookforward):
        future = df.iloc[i:i + lookforward + 1]
        er_min = future['er'].min()
        er_drop = df['er'].iloc[i] - er_min
        price_drop = (df['close'].iloc[i] - future['low'].min()) / max(df['range'].iloc[i], 0.01)
        
        conditions_met = sum([er_min < 0.15, er_drop > 0.50, price_drop > 5.0])
        if conditions_met >= 2:
            df.iloc[i, df.columns.get_loc('future_collapse')] = 1
    
    return df

def create_ratio_phase_map(df: pd.DataFrame, filename: str):
    """배율 기반 Phase Map"""
    
    ratio_bins = [0, 0.5, 0.7, 1.0, 1.3, 1.5, 2.0, 3.0, 10.0]
    channel_bins = [0, 10, 20, 30, 50, 70, 80, 90, 100]
    
    heatmap = np.zeros((len(channel_bins) - 1, len(ratio_bins) - 1))
    counts = np.zeros_like(heatmap)
    
    for _, row in df.iterrows():
        ratio_idx = np.digitize(row['ratio'], ratio_bins) - 1
        channel_idx = np.digitize(row['channel_pct'], channel_bins) - 1
        ratio_idx = max(0, min(ratio_idx, len(ratio_bins) - 2))
        channel_idx = max(0, min(channel_idx, len(channel_bins) - 2))
        
        heatmap[channel_idx, ratio_idx] += row['future_collapse']
        counts[channel_idx, ratio_idx] += 1
    
    with np.errstate(divide='ignore', invalid='ignore'):
        collapse_rate = np.where(counts > 0, heatmap / counts, np.nan)
    
    fig, ax = plt.subplots(figsize=(12, 8))
    im = ax.imshow(collapse_rate, cmap='RdYlGn_r', aspect='auto', vmin=0, vmax=1, origin='lower')
    
    ratio_labels = ['<0.5', '0.5-0.7', '0.7-1.0', '1.0-1.3', '1.3-1.5', '1.5-2.0', '2.0-3.0', '>3.0']
    channel_labels = ['0-10', '10-20', '20-30', '30-50', '50-70', '70-80', '80-90', '90-100']
    
    ax.set_xticks(range(len(ratio_labels)))
    ax.set_xticklabels(ratio_labels, rotation=45, ha='right')
    ax.set_yticks(range(len(channel_labels)))
    ax.set_yticklabels(channel_labels)
    
    ax.set_xlabel('배율 (Ratio = buyer/seller)', fontsize=12)
    ax.set_ylabel('채널% (Channel Position)', fontsize=12)
    ax.set_title('통합배율 철학: Ratio x Channel Phase Map\nCollapse Rate by State', fontsize=14)
    
    for i in range(heatmap.shape[0]):
        for j in range(heatmap.shape[1]):
            if counts[i, j] > 10:
                rate = collapse_rate[i, j]
                n = int(counts[i, j])
                color = 'white' if rate > 0.5 else 'black'
                ax.text(j, i, f'{rate:.0%}\n({n})', ha='center', va='center', fontsize=7, color=color)
    
    plt.colorbar(im, ax=ax, label='Collapse Rate')
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {filename}")

def create_comparison_map(df: pd.DataFrame, filename: str):
    """배율 vs Connectivity 비교 맵"""
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    
    ax1 = axes[0]
    for zone, color, label in [('OVERBOUGHT', 'red', '배율>1.5'), 
                                ('OVERSOLD', 'blue', '배율<0.7'),
                                ('NEUTRAL', 'gray', '중립')]:
        subset = df[df['ratio_zone'] == zone]
        if len(subset) > 0:
            sample = subset.sample(min(len(subset), 500), random_state=42)
            collapsed = sample[sample['future_collapse'] == 1]
            survived = sample[sample['future_collapse'] == 0]
            ax1.scatter(survived['ratio'], survived['channel_pct'], c=color, alpha=0.3, s=10, label=f'{label} 생존')
            ax1.scatter(collapsed['ratio'], collapsed['channel_pct'], c=color, alpha=0.7, s=20, marker='x', label=f'{label} 붕괴')
    
    ax1.axvline(x=1.5, color='red', linestyle='--', alpha=0.5, label='과매수 경계')
    ax1.axvline(x=0.7, color='blue', linestyle='--', alpha=0.5, label='과매도 경계')
    ax1.axhline(y=80, color='orange', linestyle='--', alpha=0.5)
    ax1.axhline(y=20, color='green', linestyle='--', alpha=0.5)
    ax1.set_xlabel('배율')
    ax1.set_ylabel('채널%')
    ax1.set_title('통합배율 철학')
    ax1.set_xlim(0, 5)
    ax1.legend(loc='upper right', fontsize=6)
    
    ax2 = axes[1]
    for zpoc, color, label in [(1, 'green', 'ZPOC alive'), (0, 'red', 'ZPOC dead')]:
        subset = df[df['zpoc_alive'] == zpoc]
        if len(subset) > 0:
            sample = subset.sample(min(len(subset), 500), random_state=42)
            ax2.scatter(sample['alive_count'] + np.random.normal(0, 0.1, len(sample)),
                       sample['ecs_penalized'] + np.random.normal(0, 0.1, len(sample)),
                       c=color, alpha=0.4, s=10, label=f'{label} ({len(subset)})')
    ax2.set_xlabel('alive_count')
    ax2.set_ylabel('ECS (penalized)')
    ax2.set_title('Connectivity 시스템')
    ax2.legend(loc='upper right', fontsize=8)
    
    ax3 = axes[2]
    
    ratio_zone_collapse = df.groupby('ratio_zone')['future_collapse'].agg(['mean', 'count'])
    zpoc_collapse = df.groupby('zpoc_alive')['future_collapse'].agg(['mean', 'count'])
    
    labels = ['배율>1.5', '배율<0.7', '중립', 'ZPOC alive', 'ZPOC dead']
    rates = [
        ratio_zone_collapse.loc['OVERBOUGHT', 'mean'] if 'OVERBOUGHT' in ratio_zone_collapse.index else 0,
        ratio_zone_collapse.loc['OVERSOLD', 'mean'] if 'OVERSOLD' in ratio_zone_collapse.index else 0,
        ratio_zone_collapse.loc['NEUTRAL', 'mean'] if 'NEUTRAL' in ratio_zone_collapse.index else 0,
        zpoc_collapse.loc[1, 'mean'] if 1 in zpoc_collapse.index else 0,
        zpoc_collapse.loc[0, 'mean'] if 0 in zpoc_collapse.index else 0,
    ]
    colors = ['red', 'blue', 'gray', 'green', 'darkred']
    
    bars = ax3.bar(labels, rates, color=colors, alpha=0.7)
    ax3.set_ylabel('Collapse Rate')
    ax3.set_title('시스템 비교: Collapse Rate')
    ax3.set_ylim(0, 1)
    
    for bar, rate in zip(bars, rates):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02, 
                f'{rate:.1%}', ha='center', fontsize=9)
    
    plt.suptitle('통합배율 철학 vs Connectivity 시스템 비교', fontsize=14)
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {filename}")

def create_combined_signal_map(df: pd.DataFrame, filename: str):
    """배율 + Connectivity 결합 신호 맵"""
    
    df['ratio_signal'] = 0
    df.loc[(df['ratio'] > 1.5) & (df['channel_pct'] > 80), 'ratio_signal'] = -1
    df.loc[(df['ratio'] < 0.7) & (df['channel_pct'] < 20), 'ratio_signal'] = 1
    
    df['conn_signal'] = 0
    df.loc[df['zpoc_alive'] == 0, 'conn_signal'] = -1
    df.loc[(df['zpoc_alive'] == 1) & (df['ecs_penalized'] >= 3), 'conn_signal'] = 1
    
    df['combined'] = 'NEUTRAL'
    df.loc[(df['ratio_signal'] == -1) & (df['conn_signal'] == -1), 'combined'] = 'STRONG_BEAR'
    df.loc[(df['ratio_signal'] == 1) & (df['conn_signal'] == 1), 'combined'] = 'STRONG_BULL'
    df.loc[(df['ratio_signal'] == -1) | (df['conn_signal'] == -1), 'combined'] = df.loc[(df['ratio_signal'] == -1) | (df['conn_signal'] == -1), 'combined'].replace('NEUTRAL', 'WEAK_BEAR')
    df.loc[(df['ratio_signal'] == 1) | (df['conn_signal'] == 1), 'combined'] = df.loc[(df['ratio_signal'] == 1) | (df['conn_signal'] == 1), 'combined'].replace('NEUTRAL', 'WEAK_BULL')
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    combined_stats = df.groupby('combined').agg({
        'future_collapse': ['mean', 'count']
    }).round(3)
    combined_stats.columns = ['collapse_rate', 'count']
    combined_stats = combined_stats.sort_values('collapse_rate')
    
    colors = {'STRONG_BULL': 'darkgreen', 'WEAK_BULL': 'lightgreen', 
              'NEUTRAL': 'gray', 'WEAK_BEAR': 'salmon', 'STRONG_BEAR': 'darkred'}
    
    bars = ax.barh(combined_stats.index, combined_stats['collapse_rate'], 
                   color=[colors.get(x, 'gray') for x in combined_stats.index], alpha=0.8)
    
    for bar, (idx, row) in zip(bars, combined_stats.iterrows()):
        ax.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height()/2, 
               f'{row["collapse_rate"]:.1%} (n={int(row["count"])})', va='center', fontsize=10)
    
    ax.set_xlabel('Collapse Rate')
    ax.set_title('통합 신호 (배율 + Connectivity)\n결합 시 Collapse Rate', fontsize=13)
    ax.set_xlim(0, 1.1)
    ax.axvline(x=0.5, color='black', linestyle='--', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {filename}")

def print_summary(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("통합배율 철학 vs Connectivity 비교 요약")
    print("=" * 70)
    
    print("\n[통합배율 철학]")
    for zone in ['OVERBOUGHT', 'OVERSOLD', 'NEUTRAL']:
        subset = df[df['ratio_zone'] == zone]
        if len(subset) > 0:
            cr = subset['future_collapse'].mean()
            print(f"  {zone}: {len(subset)} bars, collapse {cr:.1%}")
    
    print("\n[Connectivity 시스템]")
    for zpoc in [1, 0]:
        subset = df[df['zpoc_alive'] == zpoc]
        label = "ALIVE" if zpoc == 1 else "DEAD"
        cr = subset['future_collapse'].mean()
        print(f"  ZPOC {label}: {len(subset)} bars, collapse {cr:.1%}")
    
    ratio_over = df[df['ratio_zone'] == 'OVERBOUGHT']['future_collapse'].mean()
    zpoc_dead = df[df['zpoc_alive'] == 0]['future_collapse'].mean()
    
    print("\n[핵심 비교]")
    print(f"  배율>1.5 (과매수) collapse: {ratio_over:.1%}")
    print(f"  ZPOC dead collapse: {zpoc_dead:.1%}")
    print(f"  → ZPOC dead가 {(zpoc_dead - ratio_over)*100:+.1f}%p 더 위험")

def run_experiment():
    print("=" * 70)
    print("EXP-RATIO-VS-CONNECTIVITY-COMPARE-01")
    print("통합배율 철학 vs Connectivity 비교")
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
    
    print("\n[1] Computing all labels...")
    labeled = compute_all_labels(df)
    
    print_summary(labeled)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("\n[2] Creating Ratio Phase Map...")
    create_ratio_phase_map(labeled, f"{OUTPUT_DIR}/map_ratio_phase.png")
    
    print("\n[3] Creating Comparison Map...")
    create_comparison_map(labeled, f"{OUTPUT_DIR}/map_ratio_vs_connectivity.png")
    
    print("\n[4] Creating Combined Signal Map...")
    create_combined_signal_map(labeled, f"{OUTPUT_DIR}/map_combined_signal.png")
    
    print("\n" + "=" * 70)
    print("COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    run_experiment()
