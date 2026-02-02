"""
EXP-DEPTH-CLUSTER-ALIGN-01: DEPTH 누적 ↔ SPS/IVPOC 클러스터 교차 검증
=====================================================================
질문:
  DEPTH 누적이 큰 구간과 SPS/IVPOC 클러스터가
  같은 시간·같은 가격에 겹치는가?

기대:
  클러스터 구간: DEPTH 누적↑, DEPTH 분산↓, ER 붕괴↑
  비클러스터 구간: DEPTH 누적 없음, ER 정상

검증:
  DEPTH = SPS/IVPOC의 시간적 일반화
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List

RESULT_FILE = "v7-grammar-system/results/exp_depth_cluster_align_01.json"

def calc_er(df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 0.5
    price_change = abs(window.iloc[-1]['close'] - window.iloc[0]['close'])
    bar_changes = abs(window['close'].diff().dropna()).sum()
    if bar_changes < 0.01:
        return 1.0
    return min(1.0, price_change / bar_changes)

def calc_depth(df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 0.5
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    range_20 = high_20 - low_20
    if range_20 < 0.01:
        return 0.5
    close = df.iloc[idx]['close']
    return (high_20 - close) / range_20

def calc_sps_zscore(df: pd.DataFrame) -> pd.Series:
    """SPS Z-score 계산 (네 기존 로직)"""
    body = abs(df['close'] - df['open'])
    range_hl = df['high'] - df['low']
    body_ratio = body / range_hl.replace(0, np.nan)
    
    sps_raw = body_ratio * range_hl
    sps_mean = sps_raw.rolling(20).mean()
    sps_std = sps_raw.rolling(20).std()
    zscore = (sps_raw - sps_mean) / sps_std.replace(0, np.nan)
    
    return zscore.fillna(0)

def detect_sps_clusters(df: pd.DataFrame, zscore_threshold: float = 1.5, cluster_window: int = 10) -> List[Dict]:
    """SPS 클러스터 탐지 (연속 강한 SPS 발생 구간)"""
    df['sps_zscore'] = calc_sps_zscore(df)
    df['strong_sps'] = df['sps_zscore'] >= zscore_threshold
    
    clusters = []
    cluster_start = None
    cluster_count = 0
    
    for idx in range(len(df)):
        if df.iloc[idx]['strong_sps']:
            if cluster_start is None:
                cluster_start = idx
            cluster_count += 1
        else:
            if cluster_start is not None and cluster_count >= 3:
                clusters.append({
                    'start': cluster_start,
                    'end': idx - 1,
                    'count': cluster_count,
                    'duration': idx - 1 - cluster_start
                })
            cluster_start = None
            cluster_count = 0
    
    return clusters

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-DEPTH-CLUSTER-ALIGN-01: DEPTH ↔ SPS 클러스터 교차 검증")
    print("=" * 70)
    
    print("\n[1] Computing time series...")
    er_series = []
    depth_series = []
    for idx in range(len(df)):
        er_series.append(calc_er(df, idx))
        depth_series.append(calc_depth(df, idx))
    
    df['er'] = er_series
    df['depth'] = depth_series
    
    depth_change = [0] + [abs(depth_series[i] - depth_series[i-1]) for i in range(1, len(depth_series))]
    df['depth_change'] = depth_change
    
    depth_energy = pd.Series(depth_change).rolling(10).sum().fillna(0)
    df['depth_energy'] = depth_energy
    
    depth_var = pd.Series(depth_series).rolling(10).std().fillna(0)
    df['depth_var'] = depth_var
    
    df['zpoc'] = df['er'] < 0.25
    
    print(f"  Total bars: {len(df)}")
    
    print("\n[2] Detecting SPS clusters...")
    clusters = detect_sps_clusters(df, zscore_threshold=1.5, cluster_window=10)
    print(f"  SPS clusters found: {len(clusters)}")
    
    cluster_bars = set()
    for c in clusters:
        for i in range(c['start'], c['end'] + 1):
            cluster_bars.add(i)
    
    total_cluster_bars = len(cluster_bars)
    print(f"  Total cluster bars: {total_cluster_bars} ({100*total_cluster_bars/len(df):.1f}%)")
    
    print("\n[3] Comparing DEPTH metrics: Cluster vs Non-Cluster...")
    
    df['in_cluster'] = df.index.isin(cluster_bars)
    
    cluster_df = df[df['in_cluster']]
    non_cluster_df = df[~df['in_cluster']]
    
    metrics = ['depth_energy', 'depth_var', 'depth_change', 'er', 'zpoc']
    comparison = {}
    
    print(f"\n{'Metric':<15} | {'Cluster':>12} | {'Non-Cluster':>12} | {'Ratio':>8}")
    print("-" * 55)
    
    for metric in metrics:
        cluster_mean = cluster_df[metric].mean()
        non_cluster_mean = non_cluster_df[metric].mean()
        ratio = cluster_mean / non_cluster_mean if non_cluster_mean > 0 else 0
        
        comparison[metric] = {
            'cluster': float(cluster_mean),
            'non_cluster': float(non_cluster_mean),
            'ratio': float(ratio)
        }
        
        print(f"{metric:<15} | {cluster_mean:>12.4f} | {non_cluster_mean:>12.4f} | {ratio:>8.2f}")
    
    print("\n[4] ZPOC rate in clusters...")
    
    cluster_zpoc_rate = cluster_df['zpoc'].mean()
    non_cluster_zpoc_rate = non_cluster_df['zpoc'].mean()
    zpoc_lift = cluster_zpoc_rate / non_cluster_zpoc_rate if non_cluster_zpoc_rate > 0 else 0
    
    print(f"\n  Cluster ZPOC rate: {100*cluster_zpoc_rate:.1f}%")
    print(f"  Non-Cluster ZPOC rate: {100*non_cluster_zpoc_rate:.1f}%")
    print(f"  ZPOC Lift: {zpoc_lift:.2f}")
    
    print("\n[5] Depth energy distribution...")
    
    depth_energy_q75 = df['depth_energy'].quantile(0.75)
    high_energy = df['depth_energy'] >= depth_energy_q75
    
    high_energy_in_cluster = (high_energy & df['in_cluster']).sum()
    high_energy_total = high_energy.sum()
    high_energy_cluster_rate = high_energy_in_cluster / high_energy_total if high_energy_total > 0 else 0
    
    print(f"\n  High depth_energy (Q75+) bars: {high_energy_total}")
    print(f"  Of which in clusters: {high_energy_in_cluster} ({100*high_energy_cluster_rate:.1f}%)")
    
    cluster_rate_baseline = len(cluster_bars) / len(df)
    enrichment = high_energy_cluster_rate / cluster_rate_baseline if cluster_rate_baseline > 0 else 0
    
    print(f"  Enrichment vs baseline: {enrichment:.2f}x")
    
    print("\n[6] Temporal alignment check...")
    
    alignment_count = 0
    for c in clusters:
        cluster_mid = (c['start'] + c['end']) // 2
        
        lookback = 10
        pre_cluster = df.iloc[max(0, c['start']-lookback):c['start']]
        
        if len(pre_cluster) > 0:
            pre_depth_energy = pre_cluster['depth_energy'].mean()
            cluster_depth_energy = df.iloc[c['start']:c['end']+1]['depth_energy'].mean()
            
            if cluster_depth_energy > pre_depth_energy * 1.2:
                alignment_count += 1
    
    alignment_rate = alignment_count / len(clusters) if clusters else 0
    
    print(f"\n  Clusters with preceding depth energy buildup: {alignment_count}/{len(clusters)} ({100*alignment_rate:.1f}%)")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    depth_energy_elevated = comparison['depth_energy']['ratio'] > 1.1
    depth_var_reduced = comparison['depth_var']['ratio'] < 0.95
    zpoc_elevated = zpoc_lift > 1.1
    high_enrichment = enrichment > 1.3
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "n_clusters": len(clusters),
            "cluster_bars": total_cluster_bars,
            "cluster_coverage": float(total_cluster_bars / len(df))
        },
        "comparison": comparison,
        "zpoc_analysis": {
            "cluster_zpoc_rate": float(cluster_zpoc_rate),
            "non_cluster_zpoc_rate": float(non_cluster_zpoc_rate),
            "zpoc_lift": float(zpoc_lift)
        },
        "energy_distribution": {
            "high_energy_total": int(high_energy_total),
            "high_energy_in_cluster": int(high_energy_in_cluster),
            "enrichment": float(enrichment)
        },
        "temporal_alignment": {
            "aligned_clusters": int(alignment_count),
            "alignment_rate": float(alignment_rate)
        },
        "validation": {
            "depth_energy_elevated_in_cluster": bool(depth_energy_elevated),
            "depth_var_reduced_in_cluster": bool(depth_var_reduced),
            "zpoc_elevated_in_cluster": bool(zpoc_elevated),
            "high_energy_enriched": bool(high_enrichment),
            "DEPTH_SPS_ALIGNED": bool((depth_energy_elevated or zpoc_elevated) and high_enrichment)
        }
    }
    
    print(f"\n  Depth energy elevated in cluster: {depth_energy_elevated} (ratio: {comparison['depth_energy']['ratio']:.2f})")
    print(f"  Depth variance reduced in cluster: {depth_var_reduced} (ratio: {comparison['depth_var']['ratio']:.2f})")
    print(f"  ZPOC elevated in cluster: {zpoc_elevated} (lift: {zpoc_lift:.2f})")
    print(f"  High energy enriched in cluster: {high_enrichment} ({enrichment:.2f}x)")
    print(f"\n  DEPTH ↔ SPS CLUSTER ALIGNED: {results['validation']['DEPTH_SPS_ALIGNED']}")
    
    if results['validation']['DEPTH_SPS_ALIGNED']:
        print("\n  → SPS 클러스터 = DEPTH 누적 구간의 다른 표현")
    else:
        print("\n  → SPS 클러스터와 DEPTH는 독립적 현상")
    
    return results

def main():
    data_paths = [
        "data/chart_combined_full.csv",
        "v7-grammar-system/data/chart_combined_full.csv"
    ]
    
    df = None
    for path in data_paths:
        if os.path.exists(path):
            df = pd.read_csv(path)
            print(f"Loaded: {path}")
            break
    
    if df is None:
        print("No data file found.")
        return
    
    results = run_experiment(df)
    
    os.makedirs(os.path.dirname(RESULT_FILE), exist_ok=True)
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {RESULT_FILE}")
    
    return results

if __name__ == "__main__":
    main()
