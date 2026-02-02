"""
EXP-WORLD-CLUSTER-AUTO-01: HDBSCAN 자동 세계 경계 검증
=======================================================
목적: 사람이 만든 4개 세계가 기계적으로도 동일하게 재현되는가

입력: (IE, RI, ECS, ZPOC)
방법: HDBSCAN 밀도 기반 클러스터링
성공: 클러스터 ≈ 세계 패턴
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
import json
from datetime import datetime
import os

try:
    import hdbscan
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False
    from sklearn.cluster import DBSCAN

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_world_cluster_auto_01.json"

WINDOW_PRE = 5
WINDOW_POST = 5

ECS_WEIGHTS = {
    'zpoc_alive': 2.0, 'htf_alive': -1.5, 'tau_alive': 0.6,
    'state_stable': 0.5, 'range_alive': 0.3,
    'recovery': -0.8, 'er_alive': -0.5, 'depth_alive': -0.3
}

STATES = ['STABLE_BASIN', 'TRANSITION_ZONE', 'RUPTURE_RIDGE', 'NOISE_FIELD']

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

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-WORLD-CLUSTER-AUTO-01")
    print("HDBSCAN 자동 세계 경계 검증")
    print("=" * 70)
    
    print(f"\n  HDBSCAN available: {HAS_HDBSCAN}")
    
    print("\n[1] Computing indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q90 = df['ri'].quantile(0.90)
    
    print("\n[2] Preparing 4D feature space...")
    
    sample_indices = list(range(WINDOW_PRE + 30, len(df) - 30, 3))
    
    features = []
    human_labels = []
    
    for idx in sample_indices:
        ie = compute_ie(df, idx)
        ri = df['ri'].iloc[idx]
        ecs = df['ecs'].iloc[idx]
        zpoc = df['zpoc_alive'].iloc[idx]
        
        features.append([ie, ri, ecs, zpoc])
        
        state = classify_world_state(ie, ri, ecs, zpoc, ri_q75, ri_q90)
        human_labels.append(state)
    
    X = np.array(features)
    print(f"  Samples: {len(X)}")
    print(f"  Feature shape: {X.shape}")
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    print("\n[3] Running clustering...")
    
    if HAS_HDBSCAN:
        min_cluster_size = max(50, int(len(X) * 0.02))
        clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, 
                                    metric='euclidean',
                                    cluster_selection_method='eom')
        cluster_labels = clusterer.fit_predict(X_scaled)
    else:
        clusterer = DBSCAN(eps=0.5, min_samples=50)
        cluster_labels = clusterer.fit_predict(X_scaled)
    
    n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
    noise_ratio = (cluster_labels == -1).sum() / len(cluster_labels)
    
    print(f"\n  Clusters found: {n_clusters}")
    print(f"  Noise ratio: {noise_ratio:.1%}")
    
    print("\n[4] Comparing with human labels...")
    
    human_numeric = np.array([STATES.index(s) for s in human_labels])
    
    valid_mask = cluster_labels != -1
    if valid_mask.sum() > 100:
        ari = adjusted_rand_score(human_numeric[valid_mask], cluster_labels[valid_mask])
        nmi = normalized_mutual_info_score(human_numeric[valid_mask], cluster_labels[valid_mask])
    else:
        ari = 0
        nmi = 0
    
    print(f"\n  Adjusted Rand Index: {ari:.3f}")
    print(f"  Normalized Mutual Info: {nmi:.3f}")
    
    print("\n[5] Cluster-to-State mapping...")
    
    cluster_state_matrix = {}
    for c in sorted(set(cluster_labels)):
        if c == -1:
            continue
        mask = cluster_labels == c
        states_in_cluster = [human_labels[i] for i in range(len(human_labels)) if mask[i]]
        state_counts = pd.Series(states_in_cluster).value_counts()
        dominant_state = state_counts.index[0]
        purity = state_counts.iloc[0] / len(states_in_cluster)
        cluster_state_matrix[c] = {
            'dominant_state': dominant_state,
            'purity': purity,
            'size': mask.sum(),
            'distribution': state_counts.to_dict()
        }
        print(f"  Cluster {c}: {dominant_state} ({purity:.0%} purity, n={mask.sum()})")
    
    print("\n" + "=" * 70)
    print("CLUSTERING VALIDATION SUMMARY")
    print("=" * 70)
    
    avg_purity = np.mean([v['purity'] for v in cluster_state_matrix.values()]) if cluster_state_matrix else 0
    
    unique_states_found = len(set(v['dominant_state'] for v in cluster_state_matrix.values()))
    
    print(f"\n  Clusters found: {n_clusters}")
    print(f"  Unique states recovered: {unique_states_found}/4")
    print(f"  Average cluster purity: {avg_purity:.1%}")
    print(f"  ARI: {ari:.3f}")
    print(f"  NMI: {nmi:.3f}")
    
    success = (n_clusters >= 2 and avg_purity > 0.5) or unique_states_found >= 3
    
    interpretation = ""
    if n_clusters >= 3 and avg_purity > 0.6:
        interpretation = "STRONG: 세계는 밀도적으로 분리된 구조"
    elif n_clusters >= 2 and avg_purity > 0.4:
        interpretation = "MODERATE: 부분적 구조 존재"
    else:
        interpretation = "CONTINUOUS: 세계는 연속체 (경계 불명확)"
    
    print(f"\n  Interpretation: {interpretation}")
    print(f"  Validation: {'✓ PASS' if success else '△ PARTIAL'}")
    
    return {
        'experiment': 'EXP-WORLD-CLUSTER-AUTO-01',
        'timestamp': datetime.now().isoformat(),
        'n_clusters': n_clusters,
        'noise_ratio': noise_ratio,
        'ari': ari,
        'nmi': nmi,
        'avg_purity': avg_purity,
        'unique_states_found': unique_states_found,
        'cluster_mapping': {str(k): v for k, v in cluster_state_matrix.items()},
        'interpretation': interpretation,
        'success': success
    }, X, cluster_labels, human_labels

def create_visualizations(results: Dict, X: np.ndarray, cluster_labels: np.ndarray, 
                         human_labels: List[str], filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    
    ax1 = axes[0, 0]
    state_colors = {'STABLE_BASIN': 'green', 'TRANSITION_ZONE': 'yellow',
                   'RUPTURE_RIDGE': 'red', 'NOISE_FIELD': 'gray'}
    colors = [state_colors[s] for s in human_labels]
    ri_clipped = np.clip(X[:, 1], 0, np.percentile(X[:, 1], 95))
    ax1.scatter(X[:, 0], ri_clipped, c=colors, alpha=0.4, s=10)
    ax1.set_xlabel('IE')
    ax1.set_ylabel('RI (clipped)')
    ax1.set_title('Human-Labeled World States')
    ax1.axvline(x=2.0, color='blue', linestyle='--', alpha=0.3)
    ax1.axvline(x=4.5, color='blue', linestyle='--', alpha=0.3)
    
    ax2 = axes[0, 1]
    unique_clusters = sorted(set(cluster_labels))
    cmap = plt.cm.get_cmap('tab10', len(unique_clusters))
    cluster_colors = [cmap(c % 10) if c != -1 else 'black' for c in cluster_labels]
    ax2.scatter(X[:, 0], ri_clipped, c=cluster_colors, alpha=0.4, s=10)
    ax2.set_xlabel('IE')
    ax2.set_ylabel('RI (clipped)')
    ax2.set_title(f'Auto-Clustered ({results["n_clusters"]} clusters)')
    ax2.axvline(x=2.0, color='blue', linestyle='--', alpha=0.3)
    ax2.axvline(x=4.5, color='blue', linestyle='--', alpha=0.3)
    
    ax3 = axes[1, 0]
    ax3.scatter(X[:, 0], X[:, 2], c=colors, alpha=0.4, s=10)
    ax3.set_xlabel('IE')
    ax3.set_ylabel('ECS')
    ax3.set_title('Human Labels: IE vs ECS')
    ax3.axhline(y=1.0, color='green', linestyle='--', alpha=0.3)
    
    ax4 = axes[1, 1]
    metrics = ['n_clusters', 'unique_states_found', 'avg_purity', 'ari', 'nmi']
    values = [results.get(m, 0) for m in metrics]
    
    if values[0] > 0:
        values[0] = values[0] / 10
    if values[1] > 0:
        values[1] = values[1] / 4
    
    bars = ax4.bar(range(len(metrics)), values, color=['blue', 'green', 'orange', 'purple', 'red'], alpha=0.7)
    ax4.set_xticks(range(len(metrics)))
    ax4.set_xticklabels(['Clusters/10', 'States/4', 'Purity', 'ARI', 'NMI'], rotation=45, ha='right')
    ax4.set_ylabel('Score')
    ax4.set_title('Clustering Quality Metrics')
    ax4.set_ylim(0, 1.2)
    
    for bar, val, metric in zip(bars, values, metrics):
        if metric == 'n_clusters':
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                    f'{results["n_clusters"]}', ha='center', fontsize=9)
        elif metric == 'unique_states_found':
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                    f'{results["unique_states_found"]}/4', ha='center', fontsize=9)
        else:
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                    f'{val:.2f}', ha='center', fontsize=9)
    
    plt.suptitle(f'Interpretation: {results["interpretation"]}', fontsize=12, fontweight='bold')
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
    
    results, X, cluster_labels, human_labels = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[6] Creating visualizations...")
    create_visualizations(results, X, cluster_labels, human_labels, 
                         f"{OUTPUT_DIR}/world_cluster_auto.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
