"""
EXP-BLACKLINE-RELATIVE-MICRO-01: 거시 기준점 기반 미시 방향 생성
================================================================
핵심 가설 (H_MACRO_ANCHOR):
  미시 방향은 '자체 생성'되지 않는다.
  항상 거시 기준점(POC/Blackline)에 의해 '강제 편향'된다.

  즉:
  - 기준점 위 → 미시 매수력 누적
  - 기준점 아래 → 미시 매도력 누적

이전 실험 실패 이유:
  - 기준점 없이 ZPOC 직후/직전에서 미시 방향을 찾음
  - 좌표계가 없는 곳에서 방향을 찾은 것

이번 실험:
  - NORMAL 상태에서만
  - POC/블랙라인 기준 상대 위치
  - 미시 비대칭 누적 측정
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List
import sys
sys.path.insert(0, '.')

RESULT_FILE = "v7-grammar-system/results/exp_blackline_relative_micro_01.json"

BLACK_LINES = [24451, 24961.5, 25512.5, 26109, 26651.25]

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

def get_nearest_blackline(price: float) -> float:
    return min(BLACK_LINES, key=lambda bl: abs(price - bl))

def calc_rolling_poc(df: pd.DataFrame, lookback: int = 50) -> pd.Series:
    """롤링 POC 계산 (가격 중심점)"""
    result = []
    for i in range(len(df)):
        start = max(0, i - lookback + 1)
        window = df.iloc[start:i + 1]
        poc = (window['high'].max() + window['low'].min()) / 2
        result.append(poc)
    return pd.Series(result, index=df.index)

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-BLACKLINE-RELATIVE-MICRO-01: 거시 기준점 기반 미시 방향")
    print("=" * 70)
    
    print("\n[1] Computing base metrics...")
    
    df['range'] = df['high'] - df['low']
    df['buyer_power'] = df['close'] - df['low']
    df['seller_power'] = df['high'] - df['close']
    df['force_ratio'] = df['buyer_power'] / df['seller_power'].replace(0, 0.001)
    df['force_ratio'] = df['force_ratio'].clip(0.01, 100)
    
    df['micro_dir'] = np.sign(df['force_ratio'] - 1.0)
    
    df['er'] = calc_er(df['close'])
    
    df['zpoc'] = df['er'] < 0.20
    df['normal'] = df['er'] >= 0.35
    
    print(f"  Total bars: {len(df)}")
    print(f"  ZPOC bars: {df['zpoc'].sum()}")
    print(f"  NORMAL bars: {df['normal'].sum()}")
    
    print("\n[2] Computing macro anchors...")
    
    df['nearest_blackline'] = df['close'].apply(get_nearest_blackline)
    df['dist_to_bl'] = df['close'] - df['nearest_blackline']
    df['above_bl'] = df['close'] > df['nearest_blackline']
    
    df['rolling_poc'] = calc_rolling_poc(df, lookback=50)
    df['dist_to_poc'] = df['close'] - df['rolling_poc']
    df['above_poc'] = df['close'] > df['rolling_poc']
    
    print(f"  Bars above BL: {df['above_bl'].sum()}")
    print(f"  Bars below BL: {(~df['above_bl']).sum()}")
    print(f"  Bars above POC: {df['above_poc'].sum()}")
    print(f"  Bars below POC: {(~df['above_poc']).sum()}")
    
    print("\n[3] Testing micro asymmetry by relative position...")
    
    results = {}
    
    for anchor_name, above_col in [('blackline', 'above_bl'), ('rolling_poc', 'above_poc')]:
        print(f"\n  === {anchor_name.upper()} ===")
        
        normal_df = df[df['normal']].copy()
        
        above_micro = normal_df[normal_df[above_col]]['micro_dir'].mean()
        below_micro = normal_df[~normal_df[above_col]]['micro_dir'].mean()
        
        above_count = normal_df[above_col].sum()
        below_count = (~normal_df[above_col]).sum()
        
        above_force = normal_df[normal_df[above_col]]['force_ratio'].mean()
        below_force = normal_df[~normal_df[above_col]]['force_ratio'].mean()
        
        above_bullish_pct = (normal_df[normal_df[above_col]]['micro_dir'] > 0).mean() * 100
        below_bearish_pct = (normal_df[~normal_df[above_col]]['micro_dir'] < 0).mean() * 100
        
        print(f"    Above: n={above_count}, avg_micro_dir={above_micro:.3f}, bullish%={above_bullish_pct:.1f}%")
        print(f"    Below: n={below_count}, avg_micro_dir={below_micro:.3f}, bearish%={below_bearish_pct:.1f}%")
        print(f"    Force ratio: above={above_force:.3f}, below={below_force:.3f}")
        
        results[anchor_name] = {
            'above': {
                'count': int(above_count),
                'avg_micro_dir': float(above_micro),
                'bullish_pct': float(above_bullish_pct),
                'avg_force_ratio': float(above_force)
            },
            'below': {
                'count': int(below_count),
                'avg_micro_dir': float(below_micro),
                'bearish_pct': float(below_bearish_pct),
                'avg_force_ratio': float(below_force)
            }
        }
    
    print("\n[4] Testing micro persistence by position...")
    
    persistence_results = {}
    
    for anchor_name, above_col in [('blackline', 'above_bl'), ('rolling_poc', 'above_poc')]:
        normal_df = df[df['normal']].copy()
        
        above_persistence = []
        below_persistence = []
        
        current_streak = 0
        current_side = None
        
        for idx in range(len(normal_df)):
            row = normal_df.iloc[idx]
            is_above = row[above_col]
            micro = row['micro_dir']
            
            if is_above and micro > 0:
                if current_side == 'above_bullish':
                    current_streak += 1
                else:
                    if current_side == 'above_bullish' and current_streak > 0:
                        above_persistence.append(current_streak)
                    current_streak = 1
                    current_side = 'above_bullish'
            elif not is_above and micro < 0:
                if current_side == 'below_bearish':
                    current_streak += 1
                else:
                    if current_side == 'below_bearish' and current_streak > 0:
                        below_persistence.append(current_streak)
                    current_streak = 1
                    current_side = 'below_bearish'
            else:
                if current_side == 'above_bullish' and current_streak > 0:
                    above_persistence.append(current_streak)
                elif current_side == 'below_bearish' and current_streak > 0:
                    below_persistence.append(current_streak)
                current_streak = 0
                current_side = None
        
        avg_above = np.mean(above_persistence) if above_persistence else 0
        avg_below = np.mean(below_persistence) if below_persistence else 0
        
        persistence_results[anchor_name] = {
            'above_bullish_persistence': float(avg_above),
            'below_bearish_persistence': float(avg_below),
            'above_streak_count': len(above_persistence),
            'below_streak_count': len(below_persistence)
        }
        
        print(f"\n  {anchor_name.upper()} Persistence:")
        print(f"    Above+Bullish avg streak: {avg_above:.2f} bars")
        print(f"    Below+Bearish avg streak: {avg_below:.2f} bars")
    
    print("\n[5] Testing forward price movement by position...")
    
    forward_results = {}
    
    for anchor_name, above_col in [('blackline', 'above_bl'), ('rolling_poc', 'above_poc')]:
        normal_df = df[df['normal']].copy()
        
        for forward in [3, 5, 10]:
            normal_df[f'fwd_{forward}'] = normal_df['close'].shift(-forward) - normal_df['close']
        
        above_fwd = {}
        below_fwd = {}
        
        for forward in [3, 5, 10]:
            above_mask = normal_df[above_col] & (normal_df['micro_dir'] > 0)
            below_mask = (~normal_df[above_col]) & (normal_df['micro_dir'] < 0)
            
            above_moves = normal_df.loc[above_mask, f'fwd_{forward}'].dropna()
            below_moves = normal_df.loc[below_mask, f'fwd_{forward}'].dropna()
            
            above_fwd[f'+{forward}'] = {
                'mean': float(above_moves.mean()) if len(above_moves) > 0 else 0,
                'hit_rate': float((above_moves > 0).mean() * 100) if len(above_moves) > 0 else 0,
                'count': len(above_moves)
            }
            below_fwd[f'+{forward}'] = {
                'mean': float(below_moves.mean()) if len(below_moves) > 0 else 0,
                'hit_rate': float((below_moves < 0).mean() * 100) if len(below_moves) > 0 else 0,
                'count': len(below_moves)
            }
        
        forward_results[anchor_name] = {
            'above_bullish': above_fwd,
            'below_bearish': below_fwd
        }
        
        print(f"\n  {anchor_name.upper()} Forward Returns:")
        print(f"    Above+Bullish → Long:")
        for k, v in above_fwd.items():
            print(f"      {k}: hit={v['hit_rate']:.1f}%, avg={v['mean']:.2f}, n={v['count']}")
        print(f"    Below+Bearish → Short:")
        for k, v in below_fwd.items():
            print(f"      {k}: hit={v['hit_rate']:.1f}%, avg={v['mean']:.2f}, n={v['count']}")
    
    print("\n[6] Random shift validation...")
    
    np.random.seed(42)
    
    best_hit = 0
    best_config = None
    
    for anchor_name in ['blackline', 'rolling_poc']:
        for side in ['above_bullish', 'below_bearish']:
            for fwd in ['+3', '+5', '+10']:
                hit = forward_results[anchor_name][side][fwd]['hit_rate']
                if hit > best_hit:
                    best_hit = hit
                    best_config = (anchor_name, side, fwd)
    
    shuffle_hits = []
    for _ in range(100):
        shuffled = df['close'].sample(frac=1).reset_index(drop=True)
        if best_config[0] == 'blackline':
            shuffled_above = shuffled > shuffled.apply(get_nearest_blackline)
        else:
            shuffled_above = shuffled > calc_rolling_poc(df, 50).sample(frac=1).reset_index(drop=True)
        
        fwd_num = int(best_config[2][1:])
        fwd_return = df['close'].shift(-fwd_num) - df['close']
        
        if best_config[1] == 'above_bullish':
            mask = shuffled_above & (df['micro_dir'] > 0) & df['normal']
            hits = (fwd_return[mask] > 0).mean() * 100
        else:
            mask = (~shuffled_above) & (df['micro_dir'] < 0) & df['normal']
            hits = (fwd_return[mask] < 0).mean() * 100
        
        if not np.isnan(hits):
            shuffle_hits.append(hits)
    
    shuffle_mean = np.mean(shuffle_hits) if shuffle_hits else 50
    shuffle_std = np.std(shuffle_hits) if shuffle_hits else 1
    z_score = (best_hit - shuffle_mean) / shuffle_std if shuffle_std > 0 else 0
    
    print(f"\n  Best config: {best_config}")
    print(f"  Original hit rate: {best_hit:.1f}%")
    print(f"  Shuffled mean: {shuffle_mean:.1f}%")
    print(f"  Z-score: {z_score:.2f}")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    macro_anchor_valid = best_hit >= 55
    statistically_valid = z_score >= 2.0
    strong_edge = best_hit >= 58
    
    if strong_edge and statistically_valid:
        verdict = "STRONG_EDGE"
    elif macro_anchor_valid and statistically_valid:
        verdict = "WEAK_EDGE"
    elif macro_anchor_valid:
        verdict = "POSSIBLE_BUT_NOISY"
    else:
        verdict = "NO_EDGE"
    
    final_results = {
        "metadata": {
            "total_bars": len(df),
            "normal_bars": int(df['normal'].sum()),
            "zpoc_bars": int(df['zpoc'].sum())
        },
        "asymmetry_by_position": results,
        "persistence": persistence_results,
        "forward_returns": forward_results,
        "validation": {
            "best_config": best_config,
            "best_hit_rate": float(best_hit),
            "shuffle_mean": float(shuffle_mean),
            "z_score": float(z_score),
            "macro_anchor_valid": bool(macro_anchor_valid),
            "statistically_valid": bool(statistically_valid),
            "verdict": verdict
        }
    }
    
    print(f"\n  Best hit rate: {best_hit:.1f}%")
    print(f"  Z-score: {z_score:.2f}")
    print(f"  Verdict: {verdict}")
    
    if verdict == "STRONG_EDGE":
        print("\n  → 거시 기준점이 미시 방향을 생성한다!")
        print("  → 기준점 위 = 롱 미시 누적, 기준점 아래 = 숏 미시 누적")
    elif verdict == "WEAK_EDGE":
        print("\n  → 약한 edge 존재. 조건부 사용 가능")
    elif verdict == "POSSIBLE_BUT_NOISY":
        print("\n  → 패턴 있으나 통계적 유의성 부족")
    else:
        print("\n  → 거시 기준점도 미시 방향을 결정하지 못함")
        print("  → 미시 방향은 구조적으로 예측 불가능")
    
    return final_results

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
