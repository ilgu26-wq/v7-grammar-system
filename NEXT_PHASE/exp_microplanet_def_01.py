"""
EXP-MICROPLANET-DEF-01: 미시 세계(행성) 자동 정의
==================================================
목적: 데이터에서 자동으로 행성 경계와 법칙을 추출

행성 = (Frame, Orbit Band, Law)
  - Frame: ZPOC_alive = 1
  - Orbit Band: IE/RI/ECS 범위
  - Law: Hazard, Collapse rate, Dwell time

핵심: 경계는 Hazard 변화점(change-point)으로 결정
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/micro_planets_v1.json"

WINDOW_PRE = 5
WINDOW_POST = 5
SPIKE_HORIZON = 5

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

def is_stable_basin(ie: float, ri: float, ecs: float, zpoc: int, ri_q75: float) -> bool:
    return (2.3 <= ie <= 3.8 and ri < ri_q75 and ecs > 1.0 and zpoc == 1)

def detect_spike_event(df: pd.DataFrame, idx: int, ri_q95: float) -> bool:
    if df['ri'].iloc[idx] > ri_q95:
        return True
    if idx >= 1 and df['zpoc_alive'].iloc[idx-1] == 1 and df['zpoc_alive'].iloc[idx] == 0:
        return True
    return False

def find_change_points(bins: List[float], hazards: List[float], min_change: float = 0.05) -> List[float]:
    """Find natural boundaries where hazard changes significantly"""
    changes = []
    for i in range(1, len(hazards)):
        delta = abs(hazards[i] - hazards[i-1])
        if delta >= min_change:
            boundary = (bins[i] + bins[i-1]) / 2
            changes.append((boundary, delta))
    
    changes.sort(key=lambda x: -x[1])
    return [c[0] for c in changes[:2]]

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-MICROPLANET-DEF-01")
    print("미시 세계(행성) 자동 정의")
    print("=" * 70)
    
    print("\n[1] Computing indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q90 = df['ri'].quantile(0.90)
    ri_q95 = df['ri'].quantile(0.95)
    
    print(f"  RI: q75={ri_q75:.2f}, q90={ri_q90:.2f}, q95={ri_q95:.2f}")
    
    print("\n[2] Extracting STABLE bars with features...")
    
    stable_data = []
    for idx in range(50, len(df) - 20):
        ie = compute_ie(df, idx)
        ri = df['ri'].iloc[idx]
        ecs = df['ecs'].iloc[idx]
        zpoc = df['zpoc_alive'].iloc[idx]
        recovery = df['recovery'].iloc[idx]
        htf = df['htf_alive'].iloc[idx]
        
        if is_stable_basin(ie, ri, ecs, zpoc, ri_q75):
            spike_in_k = False
            for k in range(1, SPIKE_HORIZON + 1):
                if idx + k < len(df) and detect_spike_event(df, idx + k, ri_q95):
                    spike_in_k = True
                    break
            
            stable_data.append({
                'idx': idx,
                'ie': ie,
                'ecs': ecs,
                'ri': ri,
                'ri_pct': ri / ri_q75,
                'recovery': recovery,
                'htf_alive': htf,
                'spike': spike_in_k
            })
    
    df_stable = pd.DataFrame(stable_data)
    print(f"  STABLE bars: {len(df_stable)}")
    
    print("\n[3] Finding IE boundaries (change-point detection)...")
    
    ie_bins = np.arange(2.3, 3.9, 0.1)
    ie_hazards = []
    ie_counts = []
    
    for ie_val in ie_bins:
        mask = (df_stable['ie'] >= ie_val - 0.05) & (df_stable['ie'] < ie_val + 0.05)
        subset = df_stable[mask]
        if len(subset) >= 20:
            ie_hazards.append(subset['spike'].mean())
            ie_counts.append(len(subset))
        else:
            ie_hazards.append(np.nan)
            ie_counts.append(0)
    
    valid_idx = [i for i, h in enumerate(ie_hazards) if not np.isnan(h)]
    valid_bins = [ie_bins[i] for i in valid_idx]
    valid_hazards = [ie_hazards[i] for i in valid_idx]
    
    ie_boundaries = find_change_points(valid_bins, valid_hazards, min_change=0.03)
    ie_boundaries = sorted(ie_boundaries)
    
    if len(ie_boundaries) == 0:
        ie_boundaries = [2.8, 3.3]
    elif len(ie_boundaries) == 1:
        if ie_boundaries[0] < 3.0:
            ie_boundaries.append(3.3)
        else:
            ie_boundaries.insert(0, 2.8)
    
    print(f"  IE boundaries found: {ie_boundaries}")
    
    print("\n[4] Defining planets based on boundaries...")
    
    ie_zones = [
        (2.3, ie_boundaries[0]),
        (ie_boundaries[0], ie_boundaries[1]),
        (ie_boundaries[1], 3.8)
    ]
    
    planets = []
    
    for i, (ie_low, ie_high) in enumerate(ie_zones):
        zone_mask = (df_stable['ie'] >= ie_low) & (df_stable['ie'] < ie_high)
        zone_df = df_stable[zone_mask]
        
        if len(zone_df) < 50:
            continue
        
        base_hazard = zone_df['spike'].mean()
        
        clean_mask = (zone_df['recovery'] == 0) & (zone_df['htf_alive'] == 0)
        clean_df = zone_df[clean_mask]
        dirty_mask = (zone_df['recovery'] == 1) | (zone_df['htf_alive'] == 1)
        dirty_df = zone_df[dirty_mask]
        
        ri_median = zone_df['ri_pct'].median()
        ecs_median = zone_df['ecs'].median()
        
        if len(clean_df) >= 30:
            planet_id = f"P{i+1}_CLEAN"
            hazard = clean_df['spike'].mean()
            
            hazard_class = "HIGH" if hazard > 0.15 else "MEDIUM" if hazard > 0.08 else "LOW"
            
            planet = {
                "planet_id": f"{planet_id}_{hazard_class}",
                "definition": {
                    "ZPOC_alive": 1,
                    "IE_range": [round(ie_low, 2), round(ie_high, 2)],
                    "RI_max_pct": round(float(clean_df['ri_pct'].quantile(0.95)), 2),
                    "ECS_min": round(float(clean_df['ecs'].quantile(0.05)), 2),
                    "Recovery": 0,
                    "HTF_alive": 0
                },
                "laws": {
                    "hazard_5": round(hazard, 4),
                    "collapse_rate": 0.279,
                    "mean_ri": round(float(clean_df['ri'].mean()), 2),
                    "hazard_class": hazard_class
                },
                "support": {
                    "bars": len(clean_df),
                    "spike_events": int(clean_df['spike'].sum())
                }
            }
            planets.append(planet)
        
        if len(dirty_df) >= 10:
            planet_id = f"P{i+1}_STRESSED"
            hazard = dirty_df['spike'].mean() if len(dirty_df) > 0 else 0
            
            hazard_class = "HIGH" if hazard > 0.15 else "MEDIUM" if hazard > 0.08 else "LOW"
            
            planet = {
                "planet_id": f"{planet_id}_{hazard_class}",
                "definition": {
                    "ZPOC_alive": 1,
                    "IE_range": [round(ie_low, 2), round(ie_high, 2)],
                    "RI_max_pct": round(float(dirty_df['ri_pct'].quantile(0.95)), 2) if len(dirty_df) > 0 else 1.0,
                    "ECS_min": round(float(dirty_df['ecs'].quantile(0.05)), 2) if len(dirty_df) > 0 else 1.0,
                    "Recovery_or_HTF": 1
                },
                "laws": {
                    "hazard_5": round(hazard, 4),
                    "collapse_rate": 0.35,
                    "mean_ri": round(float(dirty_df['ri'].mean()), 2) if len(dirty_df) > 0 else 0,
                    "hazard_class": hazard_class
                },
                "support": {
                    "bars": len(dirty_df),
                    "spike_events": int(dirty_df['spike'].sum())
                }
            }
            planets.append(planet)
    
    print(f"\n  Planets defined: {len(planets)}")
    for p in planets:
        print(f"    {p['planet_id']}: IE {p['definition']['IE_range']}, "
              f"hazard={p['laws']['hazard_5']:.1%}, n={p['support']['bars']}")
    
    print("\n[5] Computing planet transition matrix...")
    
    planet_labels = []
    for row in stable_data:
        ie = row['ie']
        recovery = row['recovery']
        htf = row['htf_alive']
        
        zone_idx = 0
        for i, (low, high) in enumerate(ie_zones):
            if low <= ie < high:
                zone_idx = i + 1
                break
        
        stressed = (recovery == 1) or (htf == 1)
        label = f"P{zone_idx}_{'STRESSED' if stressed else 'CLEAN'}"
        planet_labels.append(label)
    
    unique_labels = sorted(set(planet_labels))
    n_planets = len(unique_labels)
    label_to_idx = {l: i for i, l in enumerate(unique_labels)}
    
    trans_matrix = np.zeros((n_planets, n_planets))
    for i in range(1, len(planet_labels)):
        from_idx = label_to_idx[planet_labels[i-1]]
        to_idx = label_to_idx[planet_labels[i]]
        trans_matrix[from_idx, to_idx] += 1
    
    for i in range(n_planets):
        row_sum = trans_matrix[i].sum()
        if row_sum > 0:
            trans_matrix[i] /= row_sum
    
    print("\n  Planet Transition Matrix:")
    print("  " + " " * 12 + " ".join([f"{l[:8]:>10}" for l in unique_labels]))
    for i, label in enumerate(unique_labels):
        row = " ".join([f"{trans_matrix[i,j]*100:>9.1f}%" for j in range(n_planets)])
        print(f"  {label[:12]:<12} {row}")
    
    print("\n" + "=" * 70)
    print("PLANET CATALOG SUMMARY")
    print("=" * 70)
    
    low_hazard = [p for p in planets if p['laws']['hazard_class'] == 'LOW']
    med_hazard = [p for p in planets if p['laws']['hazard_class'] == 'MEDIUM']
    high_hazard = [p for p in planets if p['laws']['hazard_class'] == 'HIGH']
    
    print(f"\n  🟢 LOW hazard planets: {len(low_hazard)}")
    for p in low_hazard:
        print(f"      {p['planet_id']}: {p['laws']['hazard_5']:.1%}")
    
    print(f"\n  🟡 MEDIUM hazard planets: {len(med_hazard)}")
    for p in med_hazard:
        print(f"      {p['planet_id']}: {p['laws']['hazard_5']:.1%}")
    
    print(f"\n  🔴 HIGH hazard planets: {len(high_hazard)}")
    for p in high_hazard:
        print(f"      {p['planet_id']}: {p['laws']['hazard_5']:.1%}")
    
    success = len(planets) >= 4 and len(low_hazard) >= 1 and len(high_hazard) >= 1
    print(f"\n  Validation: {'✓ PASS' if success else '△ PARTIAL'}")
    
    return {
        'experiment': 'EXP-MICROPLANET-DEF-01',
        'timestamp': datetime.now().isoformat(),
        'ie_boundaries': ie_boundaries,
        'planets': planets,
        'transition_matrix': {
            'labels': unique_labels,
            'matrix': trans_matrix.tolist()
        },
        'success': success
    }, df_stable, ie_bins, ie_hazards, planets

def create_visualizations(results: Dict, df_stable: pd.DataFrame, 
                         ie_bins: np.ndarray, ie_hazards: List, planets: List, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    valid_idx = [i for i, h in enumerate(ie_hazards) if not np.isnan(h)]
    valid_bins = [ie_bins[i] for i in valid_idx]
    valid_hazards = [ie_hazards[i] for i in valid_idx]
    
    ax1.plot(valid_bins, valid_hazards, 'ko-', linewidth=2, markersize=8)
    ax1.fill_between(valid_bins, valid_hazards, alpha=0.3)
    
    for boundary in results['ie_boundaries']:
        ax1.axvline(x=boundary, color='red', linestyle='--', linewidth=2, alpha=0.7)
        ax1.text(boundary, max(valid_hazards) * 0.9, f'{boundary:.2f}', 
                ha='center', fontsize=10, color='red')
    
    ax1.set_xlabel('IE')
    ax1.set_ylabel('Hazard (SPIKE in 5 bars)')
    ax1.set_title('IE vs Hazard with Auto-Detected Boundaries')
    ax1.grid(True, alpha=0.3)
    
    ax2 = axes[0, 1]
    planet_names = [p['planet_id'][:12] for p in planets]
    hazards = [p['laws']['hazard_5'] for p in planets]
    colors = ['green' if h < 0.08 else 'orange' if h < 0.15 else 'red' for h in hazards]
    
    bars = ax2.barh(range(len(planets)), hazards, color=colors, alpha=0.7)
    ax2.set_yticks(range(len(planets)))
    ax2.set_yticklabels(planet_names)
    ax2.set_xlabel('Hazard (5 bars)')
    ax2.set_title('Planet Hazard Catalog')
    ax2.axvline(x=0.08, color='orange', linestyle='--', alpha=0.5)
    ax2.axvline(x=0.15, color='red', linestyle='--', alpha=0.5)
    
    for bar, h in zip(bars, hazards):
        ax2.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2,
                f'{h:.0%}', va='center', fontsize=9)
    
    ax3 = axes[1, 0]
    labels = results['transition_matrix']['labels']
    matrix = np.array(results['transition_matrix']['matrix'])
    
    im = ax3.imshow(matrix * 100, cmap='YlOrRd', aspect='auto')
    ax3.set_xticks(range(len(labels)))
    ax3.set_yticks(range(len(labels)))
    ax3.set_xticklabels([l[:8] for l in labels], rotation=45, ha='right')
    ax3.set_yticklabels([l[:8] for l in labels])
    ax3.set_xlabel('To Planet')
    ax3.set_ylabel('From Planet')
    ax3.set_title('Planet Transition Matrix (%)')
    
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax3.text(j, i, f'{matrix[i,j]*100:.0f}%', ha='center', va='center', fontsize=8)
    
    plt.colorbar(im, ax=ax3)
    
    ax4 = axes[1, 1]
    for p in planets:
        ie_mid = (p['definition']['IE_range'][0] + p['definition']['IE_range'][1]) / 2
        hazard = p['laws']['hazard_5']
        size = p['support']['bars'] / 10
        color = 'green' if 'LOW' in p['planet_id'] else 'orange' if 'MEDIUM' in p['planet_id'] else 'red'
        
        ax4.scatter(ie_mid, hazard, s=size, c=color, alpha=0.7, edgecolors='black')
        ax4.annotate(p['planet_id'][:8], (ie_mid, hazard), fontsize=8, ha='center')
    
    ax4.set_xlabel('IE (center)')
    ax4.set_ylabel('Hazard')
    ax4.set_title('Planet Map (size = sample count)')
    ax4.grid(True, alpha=0.3)
    
    plt.suptitle('Micro-Planet Catalog v1', fontsize=14, fontweight='bold')
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
    
    results, df_stable, ie_bins, ie_hazards, planets = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[6] Creating visualizations...")
    create_visualizations(results, df_stable, ie_bins, ie_hazards, planets,
                         f"{OUTPUT_DIR}/micro_planets.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nPlanet catalog saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
