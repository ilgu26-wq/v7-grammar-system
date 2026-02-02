"""
EXP-RI-RUPTURE-PATTERN-01: RI 파열 패턴 분석
=============================================
파열 형태 3종:
  1. SPIKE: RI > q95 단발
  2. PLATEAU: RI > θ가 k bars 연속 (k≥3)
  3. CASCADE: RI > θ 스파이크 m회 이상 (window 10 bars)

규칙 승격 판정 기준:
  - 정밀도: Collapse rate ≥ 80%
  - 희소성: 전체 bar 중 < 30%
  - 재현성: 다른 구간에서도 유지
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_ri_rupture_pattern_01.json"

WINDOW_PRE = 5
WINDOW_POST = 5
PLATEAU_K = 3
CASCADE_M = 2
CASCADE_WINDOW = 10

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

def detect_rupture_patterns(df: pd.DataFrame, theta_75: float, theta_90: float, theta_95: float) -> pd.DataFrame:
    df = df.copy()
    
    df['spike_95'] = (df['ri'] > theta_95).astype(int)
    
    df['above_75'] = (df['ri'] > theta_75).astype(int)
    df['above_90'] = (df['ri'] > theta_90).astype(int)
    
    plateau_75 = []
    plateau_90 = []
    for i in range(len(df)):
        if i < PLATEAU_K - 1:
            plateau_75.append(0)
            plateau_90.append(0)
        else:
            p75 = int(df['above_75'].iloc[i-PLATEAU_K+1:i+1].sum() >= PLATEAU_K)
            p90 = int(df['above_90'].iloc[i-PLATEAU_K+1:i+1].sum() >= PLATEAU_K)
            plateau_75.append(p75)
            plateau_90.append(p90)
    
    df['plateau_75'] = plateau_75
    df['plateau_90'] = plateau_90
    
    cascade_75 = []
    cascade_90 = []
    for i in range(len(df)):
        if i < CASCADE_WINDOW:
            cascade_75.append(0)
            cascade_90.append(0)
        else:
            spikes_75 = sum(1 for j in range(i-CASCADE_WINDOW+1, i+1) 
                          if df['above_75'].iloc[j] == 1 and 
                             (j == 0 or df['above_75'].iloc[j-1] == 0))
            spikes_90 = sum(1 for j in range(i-CASCADE_WINDOW+1, i+1) 
                          if df['above_90'].iloc[j] == 1 and 
                             (j == 0 or df['above_90'].iloc[j-1] == 0))
            cascade_75.append(int(spikes_75 >= CASCADE_M))
            cascade_90.append(int(spikes_90 >= CASCADE_M))
    
    df['cascade_75'] = cascade_75
    df['cascade_90'] = cascade_90
    
    return df

def analyze_pattern(df: pd.DataFrame, pattern_col: str, name: str) -> Dict:
    triggered = df[df[pattern_col] == 1]
    not_triggered = df[df[pattern_col] == 0]
    
    if len(triggered) == 0:
        return {'name': name, 'count': 0, 'coverage': 0, 'precision': 0, 'fp_rate': 0}
    
    collapse_rate = triggered['collapse'].mean()
    coverage = len(triggered) / len(df)
    
    true_positives = len(triggered[triggered['collapse'] == 1])
    false_positives = len(triggered[triggered['collapse'] == 0])
    fp_rate = false_positives / len(triggered) if len(triggered) > 0 else 0
    
    non_collapse_triggered = len(not_triggered[not_triggered['collapse'] == 0])
    non_collapse_not_triggered = len(not_triggered[not_triggered['collapse'] == 0])
    
    return {
        'name': name,
        'count': len(triggered),
        'coverage': coverage,
        'precision': collapse_rate,
        'fp_rate': fp_rate,
        'baseline_collapse': df['collapse'].mean()
    }

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-RI-RUPTURE-PATTERN-01")
    print("RI 파열 패턴 분석: SPIKE / PLATEAU / CASCADE")
    print("=" * 70)
    
    print("\n[1] Computing all indicators...")
    df = compute_all_indicators(df)
    
    theta_75 = df['ri'].quantile(0.75)
    theta_90 = df['ri'].quantile(0.90)
    theta_95 = df['ri'].quantile(0.95)
    
    print(f"\n  Thresholds:")
    print(f"    θ75: {theta_75:.2f}")
    print(f"    θ90: {theta_90:.2f}")
    print(f"    θ95: {theta_95:.2f}")
    
    print("\n[2] Computing IE and collapse labels...")
    
    ie_list = []
    collapse_list = []
    indices = list(range(WINDOW_PRE + 30, len(df) - 30))
    
    for idx in indices:
        ie_list.append(compute_ie(df, idx))
        collapse_list.append(compute_collapse_label(df, idx))
    
    analysis_df = df.iloc[indices].copy()
    analysis_df['ie'] = ie_list
    analysis_df['collapse'] = collapse_list
    
    print("\n[3] Detecting rupture patterns...")
    analysis_df = detect_rupture_patterns(analysis_df, theta_75, theta_90, theta_95)
    
    print("\n[4] Analyzing each pattern...")
    
    patterns = [
        ('spike_95', 'SPIKE (RI > q95)'),
        ('plateau_75', 'PLATEAU_75 (RI > q75, 3+ bars)'),
        ('plateau_90', 'PLATEAU_90 (RI > q90, 3+ bars)'),
        ('cascade_75', 'CASCADE_75 (2+ spikes in 10 bars)'),
        ('cascade_90', 'CASCADE_90 (2+ spikes in 10 bars)')
    ]
    
    pattern_results = []
    
    print("\n  Pattern Analysis:")
    print("  " + "-" * 70)
    print(f"  {'Pattern':<35} {'Count':<10} {'Coverage':<12} {'Precision':<12} {'Baseline':<10}")
    print("  " + "-" * 70)
    
    baseline = analysis_df['collapse'].mean()
    
    for col, name in patterns:
        result = analyze_pattern(analysis_df, col, name)
        pattern_results.append(result)
        print(f"  {name:<35} {result['count']:<10} {result['coverage']*100:<10.1f}% {result['precision']*100:<10.1f}% {baseline*100:<10.1f}%")
    
    print("\n[5] Rule Qualification Check...")
    
    qualified_rules = []
    for result in pattern_results:
        passes_precision = result['precision'] >= 0.50
        passes_coverage = result['coverage'] <= 0.30
        passes_lift = result['precision'] > result['baseline_collapse'] * 1.3
        
        status = "QUALIFIED" if (passes_precision and passes_coverage and passes_lift) else "FAIL"
        
        if passes_precision and passes_coverage and passes_lift:
            qualified_rules.append(result['name'])
        
        print(f"\n  {result['name']}:")
        print(f"    Precision ≥ 50%: {'✓' if passes_precision else '✗'} ({result['precision']*100:.1f}%)")
        print(f"    Coverage ≤ 30%: {'✓' if passes_coverage else '✗'} ({result['coverage']*100:.1f}%)")
        print(f"    Lift > 1.3x: {'✓' if passes_lift else '✗'} ({result['precision']/result['baseline_collapse']:.2f}x)")
        print(f"    → {status}")
    
    print("\n[6] IE + Pattern Combined Analysis...")
    
    ie_valid = analysis_df[(analysis_df['ie'] >= 2.0) & (analysis_df['ie'] <= 4.5)]
    
    print(f"\n  Within IE Valid (2.0-4.5): {len(ie_valid)} samples")
    
    for col, name in patterns:
        triggered = ie_valid[ie_valid[col] == 1]
        not_triggered = ie_valid[ie_valid[col] == 0]
        
        if len(triggered) > 0 and len(not_triggered) > 0:
            print(f"\n  {name}:")
            print(f"    Triggered: {triggered['collapse'].mean()*100:.1f}% collapse (n={len(triggered)})")
            print(f"    Not Triggered: {not_triggered['collapse'].mean()*100:.1f}% collapse (n={len(not_triggered)})")
    
    print("\n" + "=" * 70)
    print("RULE CANDIDATES FOR PROMOTION")
    print("=" * 70)
    
    if qualified_rules:
        print(f"\n  QUALIFIED: {', '.join(qualified_rules)}")
    else:
        print("\n  No patterns qualified for rule promotion")
        print("  (Lower thresholds or combine with IE filtering)")
    
    return {
        'experiment': 'EXP-RI-RUPTURE-PATTERN-01',
        'timestamp': datetime.now().isoformat(),
        'thresholds': {'theta_75': theta_75, 'theta_90': theta_90, 'theta_95': theta_95},
        'pattern_results': pattern_results,
        'qualified_rules': qualified_rules,
        'settings': {'plateau_k': PLATEAU_K, 'cascade_m': CASCADE_M, 'cascade_window': CASCADE_WINDOW}
    }, analysis_df

def create_pattern_visualizations(analysis_df: pd.DataFrame, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    patterns = ['spike_95', 'plateau_75', 'plateau_90', 'cascade_75', 'cascade_90']
    pattern_names = ['SPIKE\n(q95)', 'PLATEAU\n(q75)', 'PLATEAU\n(q90)', 'CASCADE\n(q75)', 'CASCADE\n(q90)']
    
    collapse_rates = []
    counts = []
    for p in patterns:
        triggered = analysis_df[analysis_df[p] == 1]
        if len(triggered) > 0:
            collapse_rates.append(triggered['collapse'].mean())
            counts.append(len(triggered))
        else:
            collapse_rates.append(0)
            counts.append(0)
    
    baseline = analysis_df['collapse'].mean()
    colors = ['red' if r > 0.5 else 'orange' if r > baseline else 'green' for r in collapse_rates]
    
    bars = ax1.bar(range(len(patterns)), collapse_rates, color=colors, alpha=0.7)
    ax1.axhline(y=baseline, color='black', linestyle='--', label=f'Baseline ({baseline:.1%})')
    ax1.axhline(y=0.5, color='red', linestyle=':', alpha=0.5, label='50% threshold')
    ax1.set_xticks(range(len(patterns)))
    ax1.set_xticklabels(pattern_names)
    ax1.set_ylabel('Collapse Rate')
    ax1.set_title('Collapse Rate by Rupture Pattern')
    ax1.set_ylim(0, 1)
    ax1.legend()
    
    for bar, rate, count in zip(bars, collapse_rates, counts):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{rate:.0%}\n(n={count})', ha='center', fontsize=8)
    
    ax2 = axes[0, 1]
    coverages = [analysis_df[p].mean() for p in patterns]
    lifts = [collapse_rates[i] / baseline if baseline > 0 else 0 for i in range(len(patterns))]
    
    x = np.arange(len(patterns))
    width = 0.35
    ax2.bar(x - width/2, [c*100 for c in coverages], width, label='Coverage %', color='blue', alpha=0.6)
    ax2.bar(x + width/2, lifts, width, label='Lift (vs baseline)', color='purple', alpha=0.6)
    ax2.set_xticks(x)
    ax2.set_xticklabels(pattern_names)
    ax2.set_title('Coverage & Lift by Pattern')
    ax2.legend()
    ax2.axhline(y=1.0, color='black', linestyle='--', alpha=0.3)
    
    ax3 = axes[1, 0]
    ie_valid = analysis_df[(analysis_df['ie'] >= 2.0) & (analysis_df['ie'] <= 4.5)]
    
    collapse_within_ie = []
    for p in patterns:
        triggered = ie_valid[ie_valid[p] == 1]
        if len(triggered) > 0:
            collapse_within_ie.append(triggered['collapse'].mean())
        else:
            collapse_within_ie.append(0)
    
    colors = ['darkred' if r > 0.6 else 'red' if r > 0.5 else 'orange' for r in collapse_within_ie]
    bars = ax3.bar(range(len(patterns)), collapse_within_ie, color=colors, alpha=0.7)
    ax3.axhline(y=ie_valid['collapse'].mean(), color='black', linestyle='--', 
               label=f'IE Valid baseline ({ie_valid["collapse"].mean():.1%})')
    ax3.set_xticks(range(len(patterns)))
    ax3.set_xticklabels(pattern_names)
    ax3.set_ylabel('Collapse Rate')
    ax3.set_title('Collapse within IE Valid (2.0-4.5)')
    ax3.set_ylim(0, 1)
    ax3.legend()
    
    for bar, rate in zip(bars, collapse_within_ie):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{rate:.0%}', ha='center', fontsize=9)
    
    ax4 = axes[1, 1]
    sample = analysis_df.sample(min(500, len(analysis_df)), random_state=42)
    
    any_rupture = (sample['plateau_75'] | sample['cascade_75']).astype(int)
    scatter = ax4.scatter(sample['ie'], sample['ri'].clip(upper=sample['ri'].quantile(0.95)), 
                         c=any_rupture, cmap='RdYlGn_r', alpha=0.5, s=20)
    ax4.set_xlabel('IE')
    ax4.set_ylabel('RI (clipped)')
    ax4.set_title('IE vs RI with Rupture Pattern (color = any pattern)')
    ax4.axvline(x=2.0, color='blue', linestyle='--', alpha=0.5)
    ax4.axvline(x=4.5, color='blue', linestyle='--', alpha=0.5)
    plt.colorbar(scatter, ax=ax4, label='Rupture Pattern')
    
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
    
    results, analysis_df = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[7] Creating visualizations...")
    create_pattern_visualizations(analysis_df, f"{OUTPUT_DIR}/rupture_pattern_analysis.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
