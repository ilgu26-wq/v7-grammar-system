"""
EXP-POC-MICRO-VALIDATION-01: POC 기준 미시 방향 생성 가설 종합 검증
====================================================================
H_POC_MICRO:
  Rolling POC 기준 상대 위치가 미시 방향 비대칭을 "생성"하며,
  그 비대칭은 랜덤화/반사실에서 무너지고 OOS에서도 유지된다.

검증 테스트:
  A. Random Shift (time permutation)
  B. Block Bootstrap (구조 보존 랜덤화)
  C. Placebo Anchor (가짜 기준점 대조군)
  D. State Filter Sensitivity (ZPOC 제거 효과)
  E. Out-of-Sample (시간 분할)

최종 판정:
  PASS: A, C, E 중 2개 이상 PASS AND D가 구조 일관성 만족
  FAIL: A, B에서 무의미 + placebo에서 동일 수준
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from scipy import stats

RESULT_FILE = "v7-grammar-system/results/exp_poc_micro_validation_01.json"

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

def calc_rolling_poc(df: pd.DataFrame, lookback: int = 50) -> pd.Series:
    result = []
    for i in range(len(df)):
        start = max(0, i - lookback + 1)
        window = df.iloc[start:i + 1]
        poc = (window['high'].max() + window['low'].min()) / 2
        result.append(poc)
    return pd.Series(result, index=df.index)

def calc_rolling_mid(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    high_roll = df['high'].rolling(lookback, min_periods=1).max()
    low_roll = df['low'].rolling(lookback, min_periods=1).min()
    return (high_roll + low_roll) / 2

def calc_rolling_mean(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    return df['close'].rolling(lookback, min_periods=1).mean()

def compute_bias_stats(df: pd.DataFrame, anchor_col: str, micro_col: str = 'micro_dir') -> Dict:
    above_mask = df['close'] > df[anchor_col]
    below_mask = ~above_mask
    
    above_df = df[above_mask]
    below_df = df[below_mask]
    
    above_bullish = (above_df[micro_col] > 0).mean() * 100 if len(above_df) > 0 else 50
    below_bearish = (below_df[micro_col] < 0).mean() * 100 if len(below_df) > 0 else 50
    
    return {
        'above_bullish_pct': float(above_bullish),
        'below_bearish_pct': float(below_bearish),
        'above_count': len(above_df),
        'below_count': len(below_df),
        'asymmetry': float(above_bullish + below_bearish - 100)
    }

def compute_forward_hits(df: pd.DataFrame, anchor_col: str, horizons: List[int] = [3, 5]) -> Dict:
    results = {}
    
    for h in horizons:
        df[f'fwd_{h}'] = df['close'].shift(-h) - df['close']
    
    above_bullish_mask = (df['close'] > df[anchor_col]) & (df['micro_dir'] > 0)
    below_bearish_mask = (df['close'] <= df[anchor_col]) & (df['micro_dir'] < 0)
    
    for h in horizons:
        above_fwd = df.loc[above_bullish_mask, f'fwd_{h}'].dropna()
        below_fwd = df.loc[below_bearish_mask, f'fwd_{h}'].dropna()
        
        results[f'above_long_+{h}'] = {
            'hit_rate': float((above_fwd > 0).mean() * 100) if len(above_fwd) > 0 else 50,
            'count': len(above_fwd)
        }
        results[f'below_short_+{h}'] = {
            'hit_rate': float((below_fwd < 0).mean() * 100) if len(below_fwd) > 0 else 50,
            'count': len(below_fwd)
        }
    
    return results

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-POC-MICRO-VALIDATION-01: POC 미시 방향 가설 종합 검증")
    print("=" * 70)
    
    print("\n[0] Base metrics...")
    
    df['range'] = df['high'] - df['low']
    df['buyer_power'] = df['close'] - df['low']
    df['seller_power'] = df['high'] - df['close']
    df['force_ratio'] = df['buyer_power'] / df['seller_power'].replace(0, 0.001)
    df['force_ratio'] = df['force_ratio'].clip(0.01, 100)
    df['micro_dir'] = np.sign(df['force_ratio'] - 1.0)
    
    df['er'] = calc_er(df['close'])
    df['zpoc'] = df['er'] < 0.20
    df['normal'] = df['er'] >= 0.35
    
    df['rolling_poc'] = calc_rolling_poc(df, lookback=50)
    df['rolling_mid'] = calc_rolling_mid(df, lookback=20)
    df['rolling_mean'] = calc_rolling_mean(df, lookback=20)
    
    normal_df = df[df['normal']].copy().reset_index(drop=True)
    
    print(f"  Total: {len(df)}, NORMAL: {len(normal_df)}")
    
    baseline = compute_bias_stats(normal_df, 'rolling_poc')
    baseline_fwd = compute_forward_hits(normal_df, 'rolling_poc')
    
    print(f"\n  Baseline POC bias:")
    print(f"    Above bullish: {baseline['above_bullish_pct']:.1f}%")
    print(f"    Below bearish: {baseline['below_bearish_pct']:.1f}%")
    
    results = {
        'baseline': baseline,
        'baseline_forward': baseline_fwd
    }
    
    print("\n[A] Random Shift Test...")
    
    np.random.seed(42)
    n_iter = 500
    
    shift_above = []
    shift_below = []
    
    for _ in range(n_iter):
        shuffled = normal_df['micro_dir'].sample(frac=1).reset_index(drop=True)
        temp_df = normal_df.copy()
        temp_df['micro_dir'] = shuffled.values
        
        stats_s = compute_bias_stats(temp_df, 'rolling_poc')
        shift_above.append(stats_s['above_bullish_pct'])
        shift_below.append(stats_s['below_bearish_pct'])
    
    above_p = (np.array(shift_above) >= baseline['above_bullish_pct']).mean()
    below_p = (np.array(shift_below) >= baseline['below_bearish_pct']).mean()
    
    test_a_pass = above_p < 0.05 and below_p < 0.05
    
    print(f"  Above: orig={baseline['above_bullish_pct']:.1f}%, shuffle_mean={np.mean(shift_above):.1f}%, p={above_p:.3f}")
    print(f"  Below: orig={baseline['below_bearish_pct']:.1f}%, shuffle_mean={np.mean(shift_below):.1f}%, p={below_p:.3f}")
    print(f"  TEST A: {'PASS' if test_a_pass else 'FAIL'}")
    
    results['test_a'] = {
        'above_p': float(above_p),
        'below_p': float(below_p),
        'shuffle_above_mean': float(np.mean(shift_above)),
        'shuffle_below_mean': float(np.mean(shift_below)),
        'pass': bool(test_a_pass)
    }
    
    print("\n[B] Block Bootstrap Test...")
    
    block_size = 100
    n_blocks = len(normal_df) // block_size
    
    block_above = []
    block_below = []
    
    for _ in range(300):
        blocks = [normal_df.iloc[i*block_size:(i+1)*block_size]['micro_dir'].values 
                  for i in range(n_blocks)]
        np.random.shuffle(blocks)
        shuffled = np.concatenate(blocks)
        
        temp_df = normal_df.iloc[:len(shuffled)].copy()
        temp_df['micro_dir'] = shuffled
        
        stats_b = compute_bias_stats(temp_df, 'rolling_poc')
        block_above.append(stats_b['above_bullish_pct'])
        block_below.append(stats_b['below_bearish_pct'])
    
    block_above_p = (np.array(block_above) >= baseline['above_bullish_pct']).mean()
    block_below_p = (np.array(block_below) >= baseline['below_bearish_pct']).mean()
    
    test_b_pass = block_above_p < 0.10 and block_below_p < 0.10
    
    print(f"  Block Above p={block_above_p:.3f}, Block Below p={block_below_p:.3f}")
    print(f"  TEST B: {'PASS' if test_b_pass else 'FAIL'}")
    
    results['test_b'] = {
        'block_above_p': float(block_above_p),
        'block_below_p': float(block_below_p),
        'pass': bool(test_b_pass)
    }
    
    print("\n[C] Placebo Anchor Test...")
    
    anchors = {
        'rolling_poc': 'rolling_poc',
        'rolling_mid': 'rolling_mid',
        'rolling_mean': 'rolling_mean'
    }
    
    placebo_results = {}
    for name, col in anchors.items():
        stats_p = compute_bias_stats(normal_df, col)
        fwd_p = compute_forward_hits(normal_df, col)
        placebo_results[name] = {
            'bias': stats_p,
            'forward': fwd_p
        }
        print(f"  {name}: above={stats_p['above_bullish_pct']:.1f}%, below={stats_p['below_bearish_pct']:.1f}%")
    
    poc_asymmetry = placebo_results['rolling_poc']['bias']['asymmetry']
    mid_asymmetry = placebo_results['rolling_mid']['bias']['asymmetry']
    mean_asymmetry = placebo_results['rolling_mean']['bias']['asymmetry']
    
    poc_advantage = poc_asymmetry - max(mid_asymmetry, mean_asymmetry)
    test_c_pass = poc_advantage >= 2.0
    
    print(f"  POC asymmetry advantage: {poc_advantage:.1f}%p")
    print(f"  TEST C: {'PASS' if test_c_pass else 'FAIL'}")
    
    results['test_c'] = {
        'placebo': placebo_results,
        'poc_advantage': float(poc_advantage),
        'pass': bool(test_c_pass)
    }
    
    print("\n[D] State Filter Sensitivity...")
    
    state_results = {}
    
    for state_name, mask in [
        ('all', pd.Series([True] * len(df), index=df.index)),
        ('normal', df['normal']),
        ('zpoc', df['zpoc'])
    ]:
        state_df = df[mask].copy()
        if len(state_df) > 100:
            stats_d = compute_bias_stats(state_df, 'rolling_poc')
            state_results[state_name] = stats_d
            print(f"  {state_name}: above={stats_d['above_bullish_pct']:.1f}%, below={stats_d['below_bearish_pct']:.1f}%")
    
    normal_asymmetry = state_results.get('normal', {}).get('asymmetry', 0)
    zpoc_asymmetry = state_results.get('zpoc', {}).get('asymmetry', 0)
    
    test_d_pass = normal_asymmetry > zpoc_asymmetry
    
    print(f"  NORMAL asymmetry: {normal_asymmetry:.1f}%, ZPOC asymmetry: {zpoc_asymmetry:.1f}%")
    print(f"  TEST D: {'PASS' if test_d_pass else 'FAIL'}")
    
    results['test_d'] = {
        'states': state_results,
        'normal_zpoc_diff': float(normal_asymmetry - zpoc_asymmetry),
        'pass': bool(test_d_pass)
    }
    
    print("\n[E] Out-of-Sample Test...")
    
    n = len(normal_df)
    train_end = int(n * 0.6)
    
    train_df = normal_df.iloc[:train_end].copy()
    test_df = normal_df.iloc[train_end:].copy()
    
    train_stats = compute_bias_stats(train_df, 'rolling_poc')
    test_stats = compute_bias_stats(test_df, 'rolling_poc')
    
    train_fwd = compute_forward_hits(train_df, 'rolling_poc')
    test_fwd = compute_forward_hits(test_df, 'rolling_poc')
    
    print(f"  Train ({len(train_df)}): above={train_stats['above_bullish_pct']:.1f}%, below={train_stats['below_bearish_pct']:.1f}%")
    print(f"  Test  ({len(test_df)}): above={test_stats['above_bullish_pct']:.1f}%, below={test_stats['below_bearish_pct']:.1f}%")
    
    test_e_criteria = [
        test_stats['above_bullish_pct'] >= 55,
        test_stats['below_bearish_pct'] >= 55,
        test_fwd.get('above_long_+5', {}).get('hit_rate', 0) >= 53,
        test_fwd.get('below_short_+3', {}).get('hit_rate', 0) >= 52
    ]
    
    test_e_pass = sum(test_e_criteria) >= 2
    
    print(f"  Criteria met: {sum(test_e_criteria)}/4")
    print(f"  TEST E: {'PASS' if test_e_pass else 'FAIL'}")
    
    results['test_e'] = {
        'train': train_stats,
        'test': test_stats,
        'train_forward': train_fwd,
        'test_forward': test_fwd,
        'criteria_met': sum(test_e_criteria),
        'pass': bool(test_e_pass)
    }
    
    print("\n" + "=" * 70)
    print("FINAL JUDGMENT")
    print("=" * 70)
    
    ace_passes = sum([test_a_pass, test_c_pass, test_e_pass])
    d_consistent = test_d_pass
    
    if ace_passes >= 2 and d_consistent:
        final_verdict = "VALIDATED"
    elif ace_passes >= 1:
        final_verdict = "PARTIAL"
    else:
        final_verdict = "REJECTED"
    
    print(f"\n  Test A (Random Shift): {'PASS' if test_a_pass else 'FAIL'}")
    print(f"  Test B (Block Bootstrap): {'PASS' if test_b_pass else 'FAIL'}")
    print(f"  Test C (Placebo Anchor): {'PASS' if test_c_pass else 'FAIL'}")
    print(f"  Test D (State Sensitivity): {'PASS' if test_d_pass else 'FAIL'}")
    print(f"  Test E (Out-of-Sample): {'PASS' if test_e_pass else 'FAIL'}")
    
    print(f"\n  A+C+E PASS count: {ace_passes}/3")
    print(f"  D consistent: {d_consistent}")
    print(f"\n  FINAL VERDICT: {final_verdict}")
    
    if final_verdict == "VALIDATED":
        print("\n  → POC가 미시 방향의 좌표계를 정의한다! (가설 확정)")
    elif final_verdict == "PARTIAL":
        print("\n  → 부분 검증. 추가 분석 필요")
    else:
        print("\n  → POC 특이성 없음. 가설 기각")
    
    results['final'] = {
        'test_a': bool(test_a_pass),
        'test_b': bool(test_b_pass),
        'test_c': bool(test_c_pass),
        'test_d': bool(test_d_pass),
        'test_e': bool(test_e_pass),
        'ace_passes': ace_passes,
        'd_consistent': bool(d_consistent),
        'verdict': final_verdict
    }
    
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
