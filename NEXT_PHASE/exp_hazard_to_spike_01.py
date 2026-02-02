"""
EXP-HAZARD-TO-SPIKE-01: STABLE 내부 위험도 예측
================================================
목적: STABLE_BASIN에서 "다음 k bars 내 SPIKE 위험도(hazard)"를 추정

핵심 질문:
  "STABLE 안에서도 hazard가 계층화(낮음/중간/높음)로 나뉘는가?"

예측 대상: RI_SPIKE 또는 ZPOC_DEATH 발생까지의 시간
입력: (IE, ECS, RI, ZPOC, TAU, STATE, Recovery, HTF)
출력: P(SPIKE within next k bars | S) for k=1,3,5,10
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_hazard_to_spike_01.json"

WINDOW_PRE = 5
WINDOW_POST = 5
HORIZONS = [1, 3, 5, 10]

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

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-HAZARD-TO-SPIKE-01")
    print("STABLE 내부 위험도 예측")
    print("=" * 70)
    
    print("\n[1] Computing indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q90 = df['ri'].quantile(0.90)
    ri_q95 = df['ri'].quantile(0.95)
    
    print(f"  RI: q75={ri_q75:.2f}, q90={ri_q90:.2f}, q95={ri_q95:.2f}")
    
    print("\n[2] Finding STABLE bars and SPIKE events...")
    
    stable_bars = []
    for idx in range(50, len(df) - 20):
        ie = compute_ie(df, idx)
        ri = df['ri'].iloc[idx]
        ecs = df['ecs'].iloc[idx]
        zpoc = df['zpoc_alive'].iloc[idx]
        
        if is_stable_basin(ie, ri, ecs, zpoc, ri_q75):
            spike_times = {}
            for horizon in HORIZONS:
                found = False
                for k in range(1, horizon + 1):
                    if idx + k < len(df) and detect_spike_event(df, idx + k, ri_q95):
                        found = True
                        break
                spike_times[horizon] = found
            
            stable_bars.append({
                'idx': idx,
                'ie': ie,
                'ecs': ecs,
                'ri': ri,
                'ri_pct': df['ri'].iloc[idx] / ri_q75,
                'recovery': df['recovery'].iloc[idx],
                'htf_alive': df['htf_alive'].iloc[idx],
                'tau_alive': df['tau_alive'].iloc[idx],
                **{f'spike_in_{h}': spike_times[h] for h in HORIZONS}
            })
    
    print(f"  STABLE bars: {len(stable_bars)}")
    
    df_stable = pd.DataFrame(stable_bars)
    
    print("\n[3] Analyzing hazard by IE zone...")
    
    ie_zones = [(2.3, 2.8), (2.8, 3.3), (3.3, 3.8)]
    hazard_by_ie = {}
    
    for low, high in ie_zones:
        zone_df = df_stable[(df_stable['ie'] >= low) & (df_stable['ie'] < high)]
        zone_name = f"IE_{low:.1f}-{high:.1f}"
        
        hazard_by_ie[zone_name] = {
            'count': len(zone_df),
            **{f'hazard_{h}': zone_df[f'spike_in_{h}'].mean() if len(zone_df) > 0 else 0 for h in HORIZONS}
        }
        
        if len(zone_df) > 0:
            print(f"  {zone_name}: n={len(zone_df)}, hazard_5={hazard_by_ie[zone_name]['hazard_5']:.1%}")
    
    print("\n[4] Analyzing hazard by ECS level...")
    
    ecs_levels = [(-1, 1.5), (1.5, 2.5), (2.5, 4)]
    hazard_by_ecs = {}
    
    for low, high in ecs_levels:
        level_df = df_stable[(df_stable['ecs'] >= low) & (df_stable['ecs'] < high)]
        level_name = f"ECS_{low:.1f}-{high:.1f}"
        
        hazard_by_ecs[level_name] = {
            'count': len(level_df),
            **{f'hazard_{h}': level_df[f'spike_in_{h}'].mean() if len(level_df) > 0 else 0 for h in HORIZONS}
        }
        
        if len(level_df) > 0:
            print(f"  {level_name}: n={len(level_df)}, hazard_5={hazard_by_ecs[level_name]['hazard_5']:.1%}")
    
    print("\n[5] Analyzing hazard by RI percentile...")
    
    ri_levels = [(0, 0.3), (0.3, 0.6), (0.6, 1.0)]
    hazard_by_ri = {}
    
    for low, high in ri_levels:
        level_df = df_stable[(df_stable['ri_pct'] >= low) & (df_stable['ri_pct'] < high)]
        level_name = f"RI_{int(low*100)}-{int(high*100)}%"
        
        hazard_by_ri[level_name] = {
            'count': len(level_df),
            **{f'hazard_{h}': level_df[f'spike_in_{h}'].mean() if len(level_df) > 0 else 0 for h in HORIZONS}
        }
        
        if len(level_df) > 0:
            print(f"  {level_name}: n={len(level_df)}, hazard_5={hazard_by_ri[level_name]['hazard_5']:.1%}")
    
    print("\n[6] Analyzing hazard by Recovery/HTF presence...")
    
    with_recovery = df_stable[df_stable['recovery'] == 1]
    without_recovery = df_stable[df_stable['recovery'] == 0]
    
    recovery_hazard = {
        'with_recovery': {
            'count': len(with_recovery),
            **{f'hazard_{h}': with_recovery[f'spike_in_{h}'].mean() if len(with_recovery) > 0 else 0 for h in HORIZONS}
        },
        'without_recovery': {
            'count': len(without_recovery),
            **{f'hazard_{h}': without_recovery[f'spike_in_{h}'].mean() if len(without_recovery) > 0 else 0 for h in HORIZONS}
        }
    }
    
    print(f"  With Recovery: n={len(with_recovery)}, hazard_5={recovery_hazard['with_recovery'].get('hazard_5', 0):.1%}")
    print(f"  Without Recovery: n={len(without_recovery)}, hazard_5={recovery_hazard['without_recovery'].get('hazard_5', 0):.1%}")
    
    with_htf = df_stable[df_stable['htf_alive'] == 1]
    without_htf = df_stable[df_stable['htf_alive'] == 0]
    
    htf_hazard = {
        'with_htf': {
            'count': len(with_htf),
            **{f'hazard_{h}': with_htf[f'spike_in_{h}'].mean() if len(with_htf) > 0 else 0 for h in HORIZONS}
        },
        'without_htf': {
            'count': len(without_htf),
            **{f'hazard_{h}': without_htf[f'spike_in_{h}'].mean() if len(without_htf) > 0 else 0 for h in HORIZONS}
        }
    }
    
    print(f"  With HTF: n={len(with_htf)}, hazard_5={htf_hazard['with_htf'].get('hazard_5', 0):.1%}")
    print(f"  Without HTF: n={len(without_htf)}, hazard_5={htf_hazard['without_htf'].get('hazard_5', 0):.1%}")
    
    print("\n" + "=" * 70)
    print("HAZARD STRATIFICATION ANALYSIS")
    print("=" * 70)
    
    all_hazards = []
    for zone in hazard_by_ie.values():
        all_hazards.append(zone.get('hazard_5', 0))
    for level in hazard_by_ecs.values():
        all_hazards.append(level.get('hazard_5', 0))
    for level in hazard_by_ri.values():
        all_hazards.append(level.get('hazard_5', 0))
    
    hazard_range = max(all_hazards) - min(all_hazards) if all_hazards else 0
    
    print(f"\n  Overall hazard_5 range: {min(all_hazards):.1%} - {max(all_hazards):.1%} (spread: {hazard_range:.1%})")
    
    stratification = 'NONE'
    if hazard_range >= 0.15:
        stratification = 'STRONG'
    elif hazard_range >= 0.08:
        stratification = 'MODERATE'
    elif hazard_range >= 0.03:
        stratification = 'WEAK'
    
    print(f"  Stratification: {stratification}")
    
    success = stratification in ['STRONG', 'MODERATE']
    print(f"\n  Validation: {'✓ PASS' if success else '△ PARTIAL'}")
    
    return {
        'experiment': 'EXP-HAZARD-TO-SPIKE-01',
        'timestamp': datetime.now().isoformat(),
        'stable_bars': len(stable_bars),
        'hazard_by_ie': hazard_by_ie,
        'hazard_by_ecs': hazard_by_ecs,
        'hazard_by_ri': hazard_by_ri,
        'recovery_hazard': recovery_hazard,
        'htf_hazard': htf_hazard,
        'stratification': stratification,
        'hazard_range': hazard_range,
        'success': success
    }, df_stable

def create_visualizations(results: Dict, df_stable: pd.DataFrame, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    zones = list(results['hazard_by_ie'].keys())
    for h in HORIZONS:
        hazards = [results['hazard_by_ie'][z].get(f'hazard_{h}', 0) for z in zones]
        ax1.plot(range(len(zones)), hazards, 'o-', label=f'{h} bars', linewidth=2)
    ax1.set_xticks(range(len(zones)))
    ax1.set_xticklabels(zones, rotation=45, ha='right')
    ax1.set_ylabel('Hazard (SPIKE probability)')
    ax1.set_title('Hazard by IE Zone')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    ax2 = axes[0, 1]
    levels = list(results['hazard_by_ri'].keys())
    for h in HORIZONS:
        hazards = [results['hazard_by_ri'][l].get(f'hazard_{h}', 0) for l in levels]
        ax2.plot(range(len(levels)), hazards, 's-', label=f'{h} bars', linewidth=2)
    ax2.set_xticks(range(len(levels)))
    ax2.set_xticklabels(levels, rotation=45, ha='right')
    ax2.set_ylabel('Hazard (SPIKE probability)')
    ax2.set_title('Hazard by RI Percentile')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    ax3 = axes[1, 0]
    categories = ['Recovery', 'No Recovery', 'HTF', 'No HTF']
    hazard_5 = [
        results['recovery_hazard']['with_recovery'].get('hazard_5', 0),
        results['recovery_hazard']['without_recovery'].get('hazard_5', 0),
        results['htf_hazard']['with_htf'].get('hazard_5', 0),
        results['htf_hazard']['without_htf'].get('hazard_5', 0)
    ]
    colors = ['red', 'green', 'orange', 'blue']
    bars = ax3.bar(range(len(categories)), hazard_5, color=colors, alpha=0.7)
    ax3.set_xticks(range(len(categories)))
    ax3.set_xticklabels(categories)
    ax3.set_ylabel('Hazard (5 bars)')
    ax3.set_title('Hazard by Recovery/HTF Presence')
    
    for bar, val in zip(bars, hazard_5):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                f'{val:.0%}', ha='center', fontsize=10)
    
    ax4 = axes[1, 1]
    ax4.scatter(df_stable['ri_pct'], df_stable['ie'], 
               c=df_stable['spike_in_5'].astype(int), cmap='RdYlGn_r',
               alpha=0.5, s=10)
    ax4.set_xlabel('RI / q75')
    ax4.set_ylabel('IE')
    ax4.set_title('SPIKE in 5 bars (Red=SPIKE)')
    ax4.axhline(y=3.0, color='blue', linestyle='--', alpha=0.3)
    ax4.axvline(x=0.6, color='red', linestyle='--', alpha=0.3)
    
    strat = results['stratification']
    color = 'green' if strat in ['STRONG', 'MODERATE'] else 'orange'
    plt.suptitle(f'Hazard Stratification: {strat} (range: {results["hazard_range"]:.1%})', 
                fontsize=12, fontweight='bold', color=color)
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
    
    results, df_stable = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[7] Creating visualizations...")
    create_visualizations(results, df_stable, f"{OUTPUT_DIR}/hazard_to_spike.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
