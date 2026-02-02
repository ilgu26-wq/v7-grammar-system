"""
EXP-PLANET-HYPOTHESIS-01: 미시 행성별 규칙 존재성 검증
=======================================================
목적: 각 미시 행성이 서로 다른 '위험 법칙'을 가진 독립적 세계인지 검증

가설:
  H1. RI 상승 → SPIKE 위험 증가
  H2. Recovery=1 → 위험 신호
  H3. HTF_alive → 위험 증가
  H4. IE 미세 변화 → 위험도 영향

성공 기준:
  - 같은 변수라도 행성마다 효과 방향/크기가 다름
  - Permutation test로 효과 붕괴 확인
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
from scipy import stats
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/planet_laws_v1.json"

WINDOW_PRE = 5
WINDOW_POST = 5
SPIKE_HORIZON = 5
N_PERMUTATIONS = 100

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
    
    df['ecs'] = sum(ECS_WEIGHTS[k] * df[k] for k in ECS_WEIGHTS if k in df.columns)
    
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

def assign_planet(ie: float, recovery: int, htf: int) -> str:
    stressed = (recovery == 1) or (htf == 1)
    
    if ie < 2.75:
        return "P1_DANGER"
    elif ie < 2.85:
        return "P2_DANGER"
    elif stressed:
        return "P3_STRESSED"
    else:
        return "P3_CLEAN"

def test_hypothesis(df_planet: pd.DataFrame, var_name: str, split_type: str = 'median') -> Dict:
    if len(df_planet) < 20:
        return {'effect': 0, 'p_value': 1.0, 'n_high': 0, 'n_low': 0, 'significant': False}
    
    if split_type == 'binary':
        high_mask = df_planet[var_name] == 1
        low_mask = df_planet[var_name] == 0
    else:
        median_val = df_planet[var_name].median()
        high_mask = df_planet[var_name] > median_val
        low_mask = df_planet[var_name] <= median_val
    
    high_df = df_planet[high_mask]
    low_df = df_planet[low_mask]
    
    if len(high_df) < 5 or len(low_df) < 5:
        return {'effect': 0, 'p_value': 1.0, 'n_high': len(high_df), 'n_low': len(low_df), 'significant': False}
    
    hazard_high = high_df['spike'].mean()
    hazard_low = low_df['spike'].mean()
    effect = hazard_high - hazard_low
    
    contingency = np.array([
        [high_df['spike'].sum(), len(high_df) - high_df['spike'].sum()],
        [low_df['spike'].sum(), len(low_df) - low_df['spike'].sum()]
    ])
    
    if contingency.min() >= 5:
        _, p_value = stats.chi2_contingency(contingency)[:2]
    else:
        _, p_value = stats.fisher_exact(contingency)
    
    return {
        'effect': effect,
        'hazard_high': hazard_high,
        'hazard_low': hazard_low,
        'p_value': p_value,
        'n_high': len(high_df),
        'n_low': len(low_df),
        'significant': p_value < 0.05
    }

def permutation_test(df_planet: pd.DataFrame, var_name: str, observed_effect: float, 
                    split_type: str = 'median', n_perms: int = 100) -> float:
    if len(df_planet) < 30:
        return 1.0
    
    perm_effects = []
    spike_values = df_planet['spike'].values.copy()
    
    for _ in range(n_perms):
        np.random.shuffle(spike_values)
        df_perm = df_planet.copy()
        df_perm['spike'] = spike_values
        
        result = test_hypothesis(df_perm, var_name, split_type)
        perm_effects.append(abs(result['effect']))
    
    p_value = np.mean(np.array(perm_effects) >= abs(observed_effect))
    return p_value

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-PLANET-HYPOTHESIS-01")
    print("미시 행성별 규칙 존재성 검증")
    print("=" * 70)
    
    print("\n[1] Computing indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q95 = df['ri'].quantile(0.95)
    
    print("\n[2] Extracting STABLE bars and assigning planets...")
    
    stable_data = []
    for idx in range(50, len(df) - 20):
        ie = compute_ie(df, idx)
        ri = df['ri'].iloc[idx]
        ecs = df['ecs'].iloc[idx]
        zpoc = df['zpoc_alive'].iloc[idx]
        recovery = df['recovery'].iloc[idx]
        htf = df['htf_alive'].iloc[idx]
        
        if is_stable_basin(ie, ri, ecs, zpoc, ri_q75):
            spike = False
            for k in range(1, SPIKE_HORIZON + 1):
                if idx + k < len(df) and detect_spike_event(df, idx + k, ri_q95):
                    spike = True
                    break
            
            planet = assign_planet(ie, recovery, htf)
            
            stable_data.append({
                'ie': ie, 'ecs': ecs, 'ri': ri, 'ri_pct': ri / ri_q75,
                'recovery': recovery, 'htf_alive': htf,
                'planet': planet, 'spike': spike
            })
    
    df_stable = pd.DataFrame(stable_data)
    print(f"  STABLE bars: {len(df_stable)}")
    
    planet_counts = df_stable['planet'].value_counts()
    for planet, count in planet_counts.items():
        hazard = df_stable[df_stable['planet'] == planet]['spike'].mean()
        print(f"    {planet}: n={count}, hazard={hazard:.1%}")
    
    print("\n[3] Testing hypotheses per planet...")
    
    hypotheses = [
        ('H1_RI', 'ri_pct', 'median'),
        ('H2_Recovery', 'recovery', 'binary'),
        ('H3_HTF', 'htf_alive', 'binary'),
        ('H4_ECS', 'ecs', 'median')
    ]
    
    planets = ['P3_CLEAN', 'P3_STRESSED', 'P2_DANGER', 'P1_DANGER']
    
    results_table = {}
    planet_laws = {}
    
    for planet in planets:
        df_planet = df_stable[df_stable['planet'] == planet]
        baseline_hazard = df_planet['spike'].mean() if len(df_planet) > 0 else 0
        
        results_table[planet] = {'n': len(df_planet), 'baseline': baseline_hazard}
        planet_laws[planet] = {'baseline_hazard': round(baseline_hazard, 4)}
        
        for hyp_name, var_name, split_type in hypotheses:
            result = test_hypothesis(df_planet, var_name, split_type)
            results_table[planet][hyp_name] = result
            
            effect_class = 'strong' if abs(result['effect']) > 0.1 else 'moderate' if abs(result['effect']) > 0.05 else 'weak' if abs(result['effect']) > 0.02 else 'none'
            planet_laws[planet][f'{var_name}_effect'] = effect_class
            planet_laws[planet][f'{var_name}_delta'] = round(result['effect'], 4)
    
    print("\n[4] Planet-wise Effect Table:")
    print("-" * 90)
    header = f"{'Hypothesis':<15} | {'P3_CLEAN':>12} | {'P3_STRESSED':>12} | {'P2_DANGER':>12} | {'P1_DANGER':>12}"
    print(header)
    print("-" * 90)
    
    for hyp_name, _, _ in hypotheses:
        row = f"{hyp_name:<15}"
        for planet in planets:
            if planet in results_table and hyp_name in results_table[planet]:
                result = results_table[planet][hyp_name]
                effect = result['effect']
                sig = "🔴" if result['significant'] and effect > 0.05 else "🟡" if result['significant'] else ""
                row += f" | {effect:+.1%} {sig:>4}"
            else:
                row += f" | {'N/A':>12}"
        print(row)
    
    print("-" * 90)
    
    print("\n[5] Permutation tests (validating effects)...")
    
    perm_results = {}
    for planet in planets:
        df_planet = df_stable[df_stable['planet'] == planet]
        perm_results[planet] = {}
        
        if len(df_planet) < 50:
            continue
        
        for hyp_name, var_name, split_type in hypotheses:
            if planet in results_table and hyp_name in results_table[planet]:
                observed = results_table[planet][hyp_name]['effect']
                p_perm = permutation_test(df_planet, var_name, observed, split_type, N_PERMUTATIONS)
                perm_results[planet][hyp_name] = p_perm
                
                if abs(observed) > 0.03:
                    status = "✓ robust" if p_perm < 0.1 else "✗ spurious"
                    print(f"    {planet} | {hyp_name}: effect={observed:+.1%}, perm_p={p_perm:.3f} {status}")
    
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING SUMMARY")
    print("=" * 70)
    
    print("\n  [Planet Law Summary]")
    for planet in planets:
        laws = planet_laws.get(planet, {})
        effects = [f"{k}={v}" for k, v in laws.items() if '_effect' in k and v != 'none']
        print(f"    {planet}: baseline={laws.get('baseline_hazard', 0):.1%}, effects: {', '.join(effects) or 'none'}")
    
    different_effects = 0
    for hyp_name, _, _ in hypotheses:
        effects = []
        for planet in planets:
            if planet in results_table and hyp_name in results_table[planet]:
                effects.append(results_table[planet][hyp_name]['effect'])
        if len(effects) >= 2:
            effect_range = max(effects) - min(effects)
            if effect_range > 0.1:
                different_effects += 1
                print(f"\n  {hyp_name}: Effect range = {effect_range:.1%} → 행성별 차이 확인!")
    
    success = different_effects >= 2
    
    print(f"\n  Different effects across planets: {different_effects}/4")
    print(f"  Validation: {'✓ PASS - 행성별 법칙 존재' if success else '△ PARTIAL'}")
    
    return {
        'experiment': 'EXP-PLANET-HYPOTHESIS-01',
        'timestamp': datetime.now().isoformat(),
        'results_table': {p: {k: v if not isinstance(v, dict) else {kk: float(vv) if isinstance(vv, (np.floating, np.integer)) else vv for kk, vv in v.items()} for k, v in r.items()} for p, r in results_table.items()},
        'planet_laws': planet_laws,
        'perm_results': perm_results,
        'success': success
    }, df_stable, results_table

def create_visualizations(results: Dict, df_stable: pd.DataFrame, results_table: Dict, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    planets = ['P3_CLEAN', 'P3_STRESSED', 'P2_DANGER', 'P1_DANGER']
    baselines = [results_table.get(p, {}).get('baseline', 0) for p in planets]
    colors = ['green', 'orange', 'red', 'darkred']
    
    bars = ax1.bar(range(len(planets)), baselines, color=colors, alpha=0.7)
    ax1.set_xticks(range(len(planets)))
    ax1.set_xticklabels(planets, rotation=45, ha='right')
    ax1.set_ylabel('Baseline Hazard')
    ax1.set_title('Planet Baseline Hazard')
    
    for bar, h in zip(bars, baselines):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f'{h:.0%}', ha='center', fontsize=10)
    
    ax2 = axes[0, 1]
    hyp_names = ['H1_RI', 'H2_Recovery', 'H3_HTF', 'H4_ECS']
    x = np.arange(len(hyp_names))
    width = 0.2
    
    for i, planet in enumerate(planets):
        effects = []
        for hyp in hyp_names:
            if planet in results_table and hyp in results_table[planet]:
                effects.append(results_table[planet][hyp]['effect'])
            else:
                effects.append(0)
        ax2.bar(x + i*width, effects, width, label=planet, alpha=0.7)
    
    ax2.set_xticks(x + width * 1.5)
    ax2.set_xticklabels(hyp_names)
    ax2.set_ylabel('Effect (Hazard Delta)')
    ax2.set_title('Hypothesis Effects by Planet')
    ax2.legend()
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    
    ax3 = axes[1, 0]
    p3_clean = df_stable[df_stable['planet'] == 'P3_CLEAN']
    if len(p3_clean) > 100:
        ax3.scatter(p3_clean['ie'], p3_clean['ri_pct'], 
                   c=p3_clean['spike'].astype(int), cmap='RdYlGn_r',
                   alpha=0.5, s=10)
        ax3.set_xlabel('IE')
        ax3.set_ylabel('RI / q75')
        ax3.set_title('P3_CLEAN: SPIKE Distribution (Red=SPIKE)')
    
    ax4 = axes[1, 1]
    laws = results['planet_laws']
    planet_names = list(laws.keys())
    
    text_content = "PLANET LAWS\n" + "=" * 30 + "\n\n"
    for planet in planet_names:
        law = laws[planet]
        text_content += f"{planet}:\n"
        text_content += f"  baseline: {law['baseline_hazard']:.1%}\n"
        for k, v in law.items():
            if '_effect' in k:
                text_content += f"  {k}: {v}\n"
        text_content += "\n"
    
    ax4.text(0.1, 0.9, text_content, transform=ax4.transAxes, fontsize=9,
            verticalalignment='top', fontfamily='monospace')
    ax4.axis('off')
    ax4.set_title('Planet Laws Summary')
    
    status = "✓ PASS" if results['success'] else "△ PARTIAL"
    plt.suptitle(f'Planet Hypothesis Testing: {status}', fontsize=14, fontweight='bold')
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
    
    results, df_stable, results_table = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[6] Creating visualizations...")
    create_visualizations(results, df_stable, results_table,
                         f"{OUTPUT_DIR}/planet_hypothesis.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nPlanet laws saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
