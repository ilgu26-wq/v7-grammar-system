"""
WIND-3D FRAMEWORK
=================

3차원 상태 공간에서 미시 알파 관측

X축: 상태 깊이 (State Depth)
  - D0: Bar1
  - D1: Storm-IN Early
  - D2: Storm-IN Mid  
  - D3: Storm-Core

Y축: 에너지 반응 (Force bin)
  - LOW: force < 1.3
  - MID: 1.3 <= force < 2.0
  - HIGH: force >= 2.0

Z축: 결과 반응 (Direction)
  - UP / DOWN / NEUTRAL

목적: Micro Alpha = 특정 3D 셀에서 결과 분포 비대칭 발견
"""

import json
import os
import sys
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import (
    load_signals,
    classify_storm_coordinate,
)


def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df = df.drop_duplicates(subset=['time'], keep='first')
    df = df.set_index('time').sort_index()
    return df


def get_state_depth(s: Dict) -> str:
    """X축: 상태 깊이 분류"""
    storm = classify_storm_coordinate(s)
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    dc = s.get('dc_pre', 0.5)
    
    if storm != 'STORM_IN':
        return 'D0_BAR1'  # 아직 Storm 밖
    
    # Storm-IN 내부 깊이
    if force < 1.5:
        return 'D1_EARLY'
    elif force < 2.5:
        return 'D2_MID'
    else:
        return 'D3_CORE'


def get_force_bin(s: Dict) -> str:
    """Y축: 에너지 반응"""
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    
    if force < 1.3:
        return 'F_LOW'
    elif force < 2.0:
        return 'F_MID'
    else:
        return 'F_HIGH'


def get_delta_bin(s: Dict) -> str:
    """Y축 보조: 델타 반응"""
    delta = s.get('avg_delta', 0)
    
    if not delta:
        return 'Δ_ZERO'
    elif delta > 20:
        return 'Δ_POS_HIGH'
    elif delta > 0:
        return 'Δ_POS_LOW'
    elif delta > -20:
        return 'Δ_NEG_LOW'
    else:
        return 'Δ_NEG_HIGH'


def get_direction_from_chart(chart_df: pd.DataFrame, 
                              entry_ts: str, 
                              entry_price: float,
                              lookahead: int = 5) -> Optional[str]:
    """Z축: 결과 방향"""
    try:
        ts = pd.to_datetime(entry_ts)
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        
        idx = chart_df.index.get_indexer([ts], method='nearest')[0]
        
        if idx < 0 or idx + lookahead >= len(chart_df):
            return None
        
        future = chart_df.iloc[idx+1:idx+1+lookahead]
        
        if len(future) < lookahead:
            return None
        
        max_up = future['high'].max() - entry_price
        max_down = entry_price - future['low'].min()
        
        if max_up > max_down and max_up > 5:
            return 'UP'
        elif max_down > max_up and max_down > 5:
            return 'DOWN'
        else:
            return 'NEUTRAL'
    except:
        return None


def calc_skew(directions: List[str]) -> float:
    up = sum(1 for d in directions if d == 'UP')
    down = sum(1 for d in directions if d == 'DOWN')
    total = up + down
    if total == 0:
        return 0
    return (up / total - 0.5) * 200


def run_wind_3d():
    """WIND-3D Framework 실행"""
    print("="*70)
    print("WIND-3D FRAMEWORK: Micro Alpha State Space")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\n3차원 상태 공간에서 미시 알파 밀도 관측")
    print("-"*70)
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    print(f"Total signals: {len(signals)}")
    print(f"Chart range: {chart_start} to {chart_end}")
    
    # 3D 셀 데이터 수집
    cells = defaultdict(list)
    
    for s in signals:
        ts = s.get('ts')
        entry_price = s.get('entry_price')
        
        if not ts or not entry_price:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        direction = get_direction_from_chart(chart_df, ts, entry_price)
        if not direction:
            continue
        
        # 3D 좌표
        x = get_state_depth(s)
        y = get_force_bin(s)
        delta = get_delta_bin(s)
        
        cell_key = (x, y)
        cells[cell_key].append({
            'direction': direction,
            'delta': delta,
            'force': s.get('force_ratio_30', s.get('force_ratio_20', 1.0)),
            'ts': ts
        })
    
    print(f"\n3D Cells populated: {len(cells)}")
    
    # 결과 분석
    print("\n" + "="*70)
    print("3D STATE CELL ANALYSIS")
    print("="*70)
    
    print("\n" + "-"*70)
    print("| Depth | Force | N | UP | DOWN | Skew | Alpha? |")
    print("-"*70)
    
    alpha_cells = []
    
    for (x, y), data in sorted(cells.items()):
        n = len(data)
        dirs = [d['direction'] for d in data if d['direction'] != 'NEUTRAL']
        
        if len(dirs) < 5:
            continue
        
        up = sum(1 for d in dirs if d == 'UP')
        down = sum(1 for d in dirs if d == 'DOWN')
        skew = calc_skew(dirs)
        
        is_alpha = abs(skew) >= 30 and len(dirs) >= 10
        alpha_mark = "⭐" if is_alpha else ""
        
        print(f"| {x:12} | {y:6} | {n:3} | {up:3} | {down:4} | {skew:+6.1f}pp | {alpha_mark:6} |")
        
        if is_alpha:
            alpha_cells.append({
                'depth': x,
                'force': y,
                'n': n,
                'up': up,
                'down': down,
                'skew': skew,
                'direction_bias': 'UP' if skew > 0 else 'DOWN'
            })
    
    print("-"*70)
    
    # Delta 분석
    print("\n" + "="*70)
    print("DELTA BREAKDOWN (Storm-IN Only)")
    print("="*70)
    
    storm_cells = {k: v for k, v in cells.items() if 'D1' in k[0] or 'D2' in k[0] or 'D3' in k[0]}
    
    delta_groups = defaultdict(list)
    for (x, y), data in storm_cells.items():
        for d in data:
            delta_groups[d['delta']].append(d['direction'])
    
    print("\n| Delta Bin | N | UP | DOWN | Skew |")
    print("-"*50)
    
    for delta_bin in ['Δ_POS_HIGH', 'Δ_POS_LOW', 'Δ_ZERO', 'Δ_NEG_LOW', 'Δ_NEG_HIGH']:
        dirs = [d for d in delta_groups.get(delta_bin, []) if d != 'NEUTRAL']
        if len(dirs) < 3:
            continue
        
        up = sum(1 for d in dirs if d == 'UP')
        down = sum(1 for d in dirs if d == 'DOWN')
        skew = calc_skew(dirs)
        
        print(f"| {delta_bin:12} | {len(dirs):3} | {up:3} | {down:4} | {skew:+6.1f}pp |")
    
    # 풍차 초입 분석
    print("\n" + "="*70)
    print("WINDMILL ENTRY ZONE (D1_EARLY)")
    print("="*70)
    
    d1_data = []
    for (x, y), data in cells.items():
        if x == 'D1_EARLY':
            d1_data.extend(data)
    
    if d1_data:
        dirs = [d['direction'] for d in d1_data if d['direction'] != 'NEUTRAL']
        skew = calc_skew(dirs)
        up = sum(1 for d in dirs if d == 'UP')
        down = sum(1 for d in dirs if d == 'DOWN')
        
        print(f"\n풍차 초입 (D1_EARLY):")
        print(f"  N = {len(dirs)}")
        print(f"  UP: {up}, DOWN: {down}")
        print(f"  Skew: {skew:+.1f}pp")
        print(f"\n  → {'방향 불확실 (풍차 역할 확인)' if abs(skew) < 20 else '방향 편향 존재'}")
    
    # 결과 요약
    print("\n" + "="*70)
    print("MICRO ALPHA CANDIDATES")
    print("="*70)
    
    if alpha_cells:
        print("\n발견된 Alpha Cells:")
        for ac in alpha_cells:
            print(f"  [{ac['depth']} × {ac['force']}]")
            print(f"    N={ac['n']}, Skew={ac['skew']:+.1f}pp → {ac['direction_bias']}")
    else:
        print("\n⚠️ |Skew| ≥ 30pp인 셀 없음")
    
    # 구조 해석
    print("\n" + "="*70)
    print("STRUCTURE INTERPRETATION")
    print("="*70)
    
    print("""
[고차원 상태 공간]
       ↓ (투영)
[풍차 초입 D1_EARLY]  ← World-Forced 관리자
       ↓
[3D Micro-State: Depth × Force × Direction]
       ↓
[Alpha Cell]  ← 비대칭 분포 봉우리
""")
    
    # 저장
    result = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'WIND_3D_FRAMEWORK',
        'total_cells': len(cells),
        'alpha_cells': alpha_cells,
        'cell_summary': {
            str(k): {
                'n': len(v),
                'skew': calc_skew([d['direction'] for d in v if d['direction'] != 'NEUTRAL'])
            }
            for k, v in cells.items() if len(v) >= 5
        }
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/wind_3d_result.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return result


if __name__ == "__main__":
    run_wind_3d()
