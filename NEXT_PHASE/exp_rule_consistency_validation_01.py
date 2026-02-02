"""
EXP-RULE-CONSISTENCY-VALIDATION-01: 규칙 승격 최종 검증
=======================================================
검증 목표: SPIKE/PLATEAU_90 규칙이 "세계 규칙"인지 확인

검증 4가지:
  1. 전체 차트 분리력 (SPIKE > PLATEAU > NONE)
  2. 위치별 일관성 (Session, Time block, ZPOC status)
  3. 시간적 일관성 (주간/월간)
  4. 무작위성 반증 (Permutation Test)

승격 기준: 4개 중 3개 이상 통과
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_rule_consistency_01.json"

PLATEAU_K = 3

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

def compute_collapse_label(df: pd.DataFrame, lookforward: int = 30) -> pd.Series:
    collapse = []
    for idx in range(len(df)):
        if idx + lookforward >= len(df):
            collapse.append(0)
            continue
        
        future = df.iloc[idx:idx + lookforward + 1]
        er_min = future['er'].min()
        er_drop = df['er'].iloc[idx] - er_min
        price_drop = (df['close'].iloc[idx] - future['low'].min()) / max(df['range'].iloc[idx], 0.01)
        
        conditions_met = sum([er_min < 0.15, er_drop > 0.50, price_drop > 5.0])
        collapse.append(1 if conditions_met >= 2 else 0)
    
    return pd.Series(collapse, index=df.index)

def tag_rupture_patterns(df: pd.DataFrame) -> pd.DataFrame:
    theta_95 = df['ri'].quantile(0.95)
    theta_90 = df['ri'].quantile(0.90)
    
    df['tag_SPIKE'] = (df['ri'] > theta_95).astype(int)
    
    above_90 = (df['ri'] > theta_90).astype(int)
    plateau_90 = []
    for i in range(len(df)):
        if i < PLATEAU_K - 1:
            plateau_90.append(0)
        else:
            p90 = int(above_90.iloc[i-PLATEAU_K+1:i+1].sum() >= PLATEAU_K)
            plateau_90.append(p90)
    df['tag_PLATEAU90'] = plateau_90
    
    df['tag'] = 'NONE'
    df.loc[df['tag_PLATEAU90'] == 1, 'tag'] = 'PLATEAU_90'
    df.loc[df['tag_SPIKE'] == 1, 'tag'] = 'SPIKE'
    
    return df

def test_1_global_separation(df: pd.DataFrame) -> Dict:
    print("\n" + "=" * 60)
    print("TEST 1: 전체 차트 분리력")
    print("=" * 60)
    
    results = {}
    for tag in ['SPIKE', 'PLATEAU_90', 'NONE']:
        subset = df[df['tag'] == tag]
        if len(subset) > 0:
            collapse_rate = subset['collapse'].mean()
            results[tag] = {'count': len(subset), 'collapse_rate': collapse_rate}
            print(f"  {tag:<15}: {len(subset):>6} bars, Collapse {collapse_rate:.1%}")
    
    order_correct = (
        results.get('SPIKE', {}).get('collapse_rate', 0) > 
        results.get('PLATEAU_90', {}).get('collapse_rate', 0) > 
        results.get('NONE', {}).get('collapse_rate', 0)
    )
    
    print(f"\n  Order Check (SPIKE > PLATEAU_90 > NONE): {'✓ PASS' if order_correct else '✗ FAIL'}")
    
    return {'results': results, 'passed': order_correct}

def test_2_location_independence(df: pd.DataFrame) -> Dict:
    print("\n" + "=" * 60)
    print("TEST 2: 위치별 일관성")
    print("=" * 60)
    
    df['bar_idx'] = range(len(df))
    df['position_block'] = pd.cut(df['bar_idx'], bins=4, labels=['Q1', 'Q2', 'Q3', 'Q4'])
    
    block_results = {}
    all_consistent = True
    
    print("\n  Position Block Analysis:")
    print("  " + "-" * 50)
    
    for block in ['Q1', 'Q2', 'Q3', 'Q4']:
        block_df = df[df['position_block'] == block]
        
        spike_collapse = block_df[block_df['tag'] == 'SPIKE']['collapse'].mean() if len(block_df[block_df['tag'] == 'SPIKE']) > 0 else 0
        none_collapse = block_df[block_df['tag'] == 'NONE']['collapse'].mean() if len(block_df[block_df['tag'] == 'NONE']) > 0 else 0
        
        consistent = spike_collapse > none_collapse
        if not consistent:
            all_consistent = False
        
        block_results[block] = {
            'spike_collapse': spike_collapse,
            'none_collapse': none_collapse,
            'consistent': consistent
        }
        
        print(f"  {block}: SPIKE={spike_collapse:.1%} vs NONE={none_collapse:.1%} {'✓' if consistent else '✗'}")
    
    zpoc_results = {}
    print("\n  ZPOC Status Analysis:")
    print("  " + "-" * 50)
    
    for zpoc_status in [0, 1]:
        label = "ALIVE" if zpoc_status == 1 else "DEAD"
        zpoc_df = df[df['zpoc_alive'] == zpoc_status]
        
        spike_collapse = zpoc_df[zpoc_df['tag'] == 'SPIKE']['collapse'].mean() if len(zpoc_df[zpoc_df['tag'] == 'SPIKE']) > 0 else 0
        none_collapse = zpoc_df[zpoc_df['tag'] == 'NONE']['collapse'].mean() if len(zpoc_df[zpoc_df['tag'] == 'NONE']) > 0 else 0
        
        consistent = spike_collapse >= none_collapse
        
        zpoc_results[label] = {
            'spike_collapse': spike_collapse,
            'none_collapse': none_collapse,
            'consistent': consistent
        }
        
        print(f"  ZPOC {label}: SPIKE={spike_collapse:.1%} vs NONE={none_collapse:.1%} {'✓' if consistent else '✗'}")
    
    passed = all_consistent and all(r['consistent'] for r in zpoc_results.values())
    print(f"\n  Location Independence: {'✓ PASS' if passed else '✗ FAIL'}")
    
    return {'block_results': block_results, 'zpoc_results': zpoc_results, 'passed': passed}

def test_3_temporal_consistency(df: pd.DataFrame) -> Dict:
    print("\n" + "=" * 60)
    print("TEST 3: 시간적 일관성")
    print("=" * 60)
    
    n_windows = 4
    window_size = len(df) // n_windows
    
    window_results = []
    precisions = []
    
    print("\n  Rolling Window Analysis:")
    print("  " + "-" * 50)
    
    for i in range(n_windows):
        start = i * window_size
        end = start + window_size if i < n_windows - 1 else len(df)
        
        window_df = df.iloc[start:end]
        spike_df = window_df[window_df['tag'] == 'SPIKE']
        
        if len(spike_df) > 0:
            precision = spike_df['collapse'].mean()
        else:
            precision = 0
        
        precisions.append(precision)
        window_results.append({
            'window': f'W{i+1}',
            'precision': precision,
            'count': len(spike_df)
        })
        
        print(f"  Window {i+1}: SPIKE Precision={precision:.1%} (n={len(spike_df)})")
    
    valid_precisions = [p for p in precisions if p > 0]
    if len(valid_precisions) >= 2:
        precision_range = max(valid_precisions) - min(valid_precisions)
        mean_precision = np.mean(valid_precisions)
        cv = precision_range / mean_precision if mean_precision > 0 else 1.0
        
        passed = cv < 0.30
    else:
        cv = 0
        passed = False
    
    print(f"\n  Precision Range: {precision_range*100:.1f}%p")
    print(f"  CV (Coefficient of Variation): {cv:.2f}")
    print(f"  Temporal Consistency (CV < 0.30): {'✓ PASS' if passed else '✗ FAIL'}")
    
    return {'window_results': window_results, 'cv': cv, 'passed': passed}

def test_4_permutation(df: pd.DataFrame, n_permutations: int = 20) -> Dict:
    print("\n" + "=" * 60)
    print("TEST 4: 무작위성 반증 (Permutation Test)")
    print("=" * 60)
    
    original_spike = df[df['tag'] == 'SPIKE']
    original_precision = original_spike['collapse'].mean() if len(original_spike) > 0 else 0
    
    print(f"\n  Original SPIKE Precision: {original_precision:.1%}")
    
    shuffled_precisions = []
    
    for i in range(n_permutations):
        shuffled_ri = df['ri'].sample(frac=1, random_state=i).reset_index(drop=True)
        theta_95 = shuffled_ri.quantile(0.95)
        
        shuffled_spike_mask = shuffled_ri > theta_95
        shuffled_spike_collapse = df.loc[shuffled_spike_mask, 'collapse'].mean() if shuffled_spike_mask.sum() > 0 else 0
        shuffled_precisions.append(shuffled_spike_collapse)
    
    mean_shuffled = np.mean(shuffled_precisions)
    std_shuffled = np.std(shuffled_precisions)
    
    baseline = df['collapse'].mean()
    
    degradation = original_precision - mean_shuffled
    passed = mean_shuffled < original_precision * 0.8
    
    print(f"  Shuffled Mean Precision: {mean_shuffled:.1%} (±{std_shuffled:.1%})")
    print(f"  Baseline Collapse: {baseline:.1%}")
    print(f"  Degradation: {degradation*100:+.1f}%p")
    print(f"  Permutation Test (shuffled < 80% original): {'✓ PASS' if passed else '✗ FAIL'}")
    
    return {
        'original_precision': original_precision,
        'shuffled_mean': mean_shuffled,
        'shuffled_std': std_shuffled,
        'degradation': degradation,
        'passed': passed
    }

def run_validation(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-RULE-CONSISTENCY-VALIDATION-01")
    print("규칙 승격 최종 검증: SPIKE / PLATEAU_90")
    print("=" * 70)
    
    print("\n[1] Computing all indicators...")
    df = compute_all_indicators(df)
    
    print("\n[2] Computing collapse labels...")
    df['collapse'] = compute_collapse_label(df)
    
    print("\n[3] Tagging rupture patterns...")
    df = tag_rupture_patterns(df)
    
    tag_counts = df['tag'].value_counts()
    print(f"\n  Tag Distribution:")
    for tag, count in tag_counts.items():
        print(f"    {tag}: {count} ({count/len(df)*100:.1f}%)")
    
    test1 = test_1_global_separation(df)
    test2 = test_2_location_independence(df)
    test3 = test_3_temporal_consistency(df)
    test4 = test_4_permutation(df)
    
    print("\n" + "=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)
    
    tests_passed = sum([test1['passed'], test2['passed'], test3['passed'], test4['passed']])
    
    print(f"\n  Tests Passed: {tests_passed}/4")
    print(f"    1. Global Separation: {'✓' if test1['passed'] else '✗'}")
    print(f"    2. Location Independence: {'✓' if test2['passed'] else '✗'}")
    print(f"    3. Temporal Consistency: {'✓' if test3['passed'] else '✗'}")
    print(f"    4. Permutation Test: {'✓' if test4['passed'] else '✗'}")
    
    if tests_passed >= 3:
        verdict = "RULE PROMOTED TO AXIOM"
        print(f"\n  🏆 {verdict}")
        print("  → SPIKE: Hard Kill Rule (Axiom Layer)")
        print("  → PLATEAU_90: Soft Kill Rule")
    elif tests_passed >= 2:
        verdict = "CONDITIONAL RULE"
        print(f"\n  ⚠️ {verdict}")
        print("  → Rules valid but context-dependent")
    else:
        verdict = "RULE REJECTED"
        print(f"\n  ✗ {verdict}")
        print("  → Rules show local patterns only")
    
    return {
        'experiment': 'EXP-RULE-CONSISTENCY-VALIDATION-01',
        'timestamp': datetime.now().isoformat(),
        'test_results': {
            'test1_global': test1,
            'test2_location': test2,
            'test3_temporal': test3,
            'test4_permutation': test4
        },
        'tests_passed': tests_passed,
        'verdict': verdict
    }, df

def create_validation_visualizations(df: pd.DataFrame, results: Dict, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    tags = ['SPIKE', 'PLATEAU_90', 'NONE']
    collapse_rates = []
    counts = []
    for tag in tags:
        subset = df[df['tag'] == tag]
        collapse_rates.append(subset['collapse'].mean() if len(subset) > 0 else 0)
        counts.append(len(subset))
    
    colors = ['darkred', 'orange', 'green']
    bars = ax1.bar(tags, collapse_rates, color=colors, alpha=0.7)
    ax1.set_ylabel('Collapse Rate')
    ax1.set_title('Test 1: Global Separation\n(SPIKE > PLATEAU_90 > NONE)')
    ax1.set_ylim(0, 1)
    
    for bar, rate, count in zip(bars, collapse_rates, counts):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{rate:.1%}\n(n={count})', ha='center', fontsize=9)
    
    passed = results['test_results']['test1_global']['passed']
    ax1.set_xlabel(f"{'✓ PASS' if passed else '✗ FAIL'}", fontsize=12, 
                   color='green' if passed else 'red')
    
    ax2 = axes[0, 1]
    blocks = ['Q1', 'Q2', 'Q3', 'Q4']
    block_data = results['test_results']['test2_location']['block_results']
    
    spike_rates = [block_data[b]['spike_collapse'] for b in blocks]
    none_rates = [block_data[b]['none_collapse'] for b in blocks]
    
    x = np.arange(len(blocks))
    width = 0.35
    ax2.bar(x - width/2, spike_rates, width, label='SPIKE', color='red', alpha=0.7)
    ax2.bar(x + width/2, none_rates, width, label='NONE', color='green', alpha=0.7)
    ax2.set_xticks(x)
    ax2.set_xticklabels(blocks)
    ax2.set_ylabel('Collapse Rate')
    ax2.set_title('Test 2: Location Independence')
    ax2.legend()
    
    passed = results['test_results']['test2_location']['passed']
    ax2.set_xlabel(f"{'✓ PASS' if passed else '✗ FAIL'}", fontsize=12,
                   color='green' if passed else 'red')
    
    ax3 = axes[1, 0]
    window_data = results['test_results']['test3_temporal']['window_results']
    windows = [w['window'] for w in window_data]
    precisions = [w['precision'] for w in window_data]
    
    ax3.bar(windows, precisions, color='purple', alpha=0.7)
    ax3.axhline(y=np.mean(precisions), color='black', linestyle='--', label='Mean')
    ax3.set_ylabel('SPIKE Precision')
    ax3.set_title(f'Test 3: Temporal Consistency\n(CV={results["test_results"]["test3_temporal"]["cv"]:.2f})')
    ax3.legend()
    ax3.set_ylim(0, 1)
    
    passed = results['test_results']['test3_temporal']['passed']
    ax3.set_xlabel(f"{'✓ PASS' if passed else '✗ FAIL'}", fontsize=12,
                   color='green' if passed else 'red')
    
    ax4 = axes[1, 1]
    perm_data = results['test_results']['test4_permutation']
    labels = ['Original\nSPIKE', 'Shuffled\nMean', 'Baseline']
    values = [perm_data['original_precision'], perm_data['shuffled_mean'], df['collapse'].mean()]
    colors = ['red', 'gray', 'blue']
    
    bars = ax4.bar(labels, values, color=colors, alpha=0.7)
    ax4.set_ylabel('Collapse Rate')
    ax4.set_title('Test 4: Permutation Test\n(Shuffled should drop)')
    ax4.set_ylim(0, 1)
    
    for bar, val in zip(bars, values):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{val:.1%}', ha='center', fontsize=10)
    
    passed = perm_data['passed']
    ax4.set_xlabel(f"{'✓ PASS' if passed else '✗ FAIL'}", fontsize=12,
                   color='green' if passed else 'red')
    
    plt.suptitle(f"Rule Consistency Validation: {results['verdict']}", fontsize=14, fontweight='bold')
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
    
    results, analysis_df = run_validation(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[5] Creating visualizations...")
    create_validation_visualizations(analysis_df, results, f"{OUTPUT_DIR}/rule_consistency_validation.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
