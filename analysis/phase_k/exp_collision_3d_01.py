"""
EXP-COLLISION-3D-01: 규칙 충돌 3D 분포 시각화
==============================================

목적:
  규칙 충돌 밀도를 3D 분포로 시각화하고
  풍차 초입(Transition Band)을 객관적으로 식별

3D 좌표:
  X = Global Coherence (세계 규칙 설명력)
  Y = Local Irreversibility (미시 규칙 지배도)
  Z = Phase Depth (자유도 붕괴량)
"""

import json
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from datetime import datetime
from typing import Dict, List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import load_signals, classify_storm_coordinate


def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df = df.drop_duplicates(subset=['time'], keep='first')
    df = df.set_index('time').sort_index()
    return df


def calc_global_coherence(chart_df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    """
    X′축: Global Coherence (세계 규칙 설명력) - 재정의
    - 얼마나 버티고 있나 (붕괴 압력)
    - 목표 분포: 0.2~0.9
    """
    if idx < lookback * 2:
        return 0.5
    
    window = chart_df.iloc[idx-lookback:idx]
    past = chart_df.iloc[idx-lookback*2:idx-lookback]
    
    current_vol = (window['high'] - window['low']).std()
    past_vol = (past['high'] - past['low']).std()
    vol_divergence = abs(current_vol - past_vol) / (past_vol + 0.1)
    vol_score = min(vol_divergence / 0.5, 1.0)
    
    current_range = window['high'].max() - window['low'].min()
    past_range = past['high'].max() - past['low'].min()
    range_instability = abs(current_range - past_range) / (past_range + 1)
    frame_score = min(range_instability / 0.3, 1.0)
    
    price_trend = (window['close'].iloc[-1] - window['close'].iloc[0]) / (window['high'].max() - window['low'].min() + 1)
    trend_pressure = abs(price_trend)
    regime_score = min(trend_pressure / 0.3, 1.0)
    
    coherence = 1 - (vol_score * 0.4 + frame_score * 0.3 + regime_score * 0.3)
    return max(0.1, min(0.9, coherence))


def calc_local_irreversibility(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    """
    Y′축: Local Irreversibility (미시 규칙 지배도) - 재정의
    - sigmoid 기반 압력 누적 스칼라
    - 목표 분포: 0.1~0.9
    """
    if idx < lookback:
        return 0.1
    
    window = chart_df.iloc[idx-lookback:idx]
    
    consecutive_fails = 0
    max_fails = 0
    for i in range(1, len(window)):
        prev_range = window['high'].iloc[i-1] - window['low'].iloc[i-1]
        if prev_range < 1:
            continue
        current_close = window['close'].iloc[i]
        prev_low = window['low'].iloc[i-1]
        recovery_threshold = prev_low + prev_range * 0.4
        if current_close < recovery_threshold:
            consecutive_fails += 1
            max_fails = max(max_fails, consecutive_fails)
        else:
            consecutive_fails = 0
    rfc_raw = max_fails
    
    recent = chart_df.iloc[idx-lookback//2:idx]
    past = chart_df.iloc[idx-lookback:idx-lookback//2]
    recent_range = recent['high'].max() - recent['low'].min()
    past_range = past['high'].max() - past['low'].min()
    bcr_raw = 1 - (recent_range / past_range if past_range > 0.5 else 1.0)
    bcr_raw = max(0, bcr_raw)
    
    recent_avg = (window['high'].iloc[-lookback//2:] - window['low'].iloc[-lookback//2:]).mean()
    past_avg = (window['high'].iloc[:lookback//2] - window['low'].iloc[:lookback//2]).mean()
    eda_raw = 1 - (recent_avg / past_avg if past_avg > 0.1 else 1.0)
    eda_raw = max(0, eda_raw)
    
    pressure = 0.5 * rfc_raw + 0.3 * bcr_raw * 5 + 0.2 * eda_raw * 5
    
    irreversibility = 1 / (1 + np.exp(-pressure + 2))
    return max(0.1, min(0.9, irreversibility))


def calc_phase_depth(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    """
    Z축: Phase Depth (자유도 붕괴량)
    - 선택 분기 수 감소율
    - 값: 0.0 = 자유, 1.0 = 완전 붕괴
    """
    if idx < lookback * 2:
        return 0.0
    
    past = chart_df.iloc[idx-lookback*2:idx-lookback]
    recent = chart_df.iloc[idx-lookback:idx]
    
    past_vol = (past['high'] - past['low']).std()
    recent_vol = (recent['high'] - recent['low']).std()
    vol_collapse = 1 - (recent_vol / past_vol) if past_vol > 0.1 else 0
    
    past_range = past['high'].max() - past['low'].min()
    recent_range = recent['high'].max() - recent['low'].min()
    range_collapse = 1 - (recent_range / past_range) if past_range > 1 else 0
    
    price_movement = abs(recent['close'].iloc[-1] - recent['close'].iloc[0])
    avg_bar = (recent['high'] - recent['low']).mean()
    directional_commitment = min(price_movement / (avg_bar * lookback) * 2, 1.0) if avg_bar > 0 else 0
    
    depth = (vol_collapse + range_collapse + directional_commitment) / 3
    return max(0, min(1, depth))


def get_direction_outcome(chart_df: pd.DataFrame, idx: int, lookahead: int = 20) -> str:
    if idx + lookahead >= len(chart_df):
        return None
    
    entry = chart_df.iloc[idx]['close']
    future = chart_df.iloc[idx+1:idx+1+lookahead]
    
    max_up = future['high'].max() - entry
    max_down = entry - future['low'].min()
    
    if max_up >= 15 and max_up > max_down:
        return 'UP'
    elif max_down >= 15 and max_down > max_up:
        return 'DOWN'
    else:
        return 'NEUTRAL'


def get_loss_outcome(chart_df: pd.DataFrame, idx: int, lookahead: int = 30) -> bool:
    if idx + lookahead >= len(chart_df):
        return None
    
    entry = chart_df.iloc[idx]['close']
    future = chart_df.iloc[idx+1:idx+1+lookahead]
    
    for _, bar in future.iterrows():
        if bar['low'] <= entry - 20:
            return False
        if bar['high'] >= entry + 10:
            return True
    
    return True


def run_exp_collision_3d_01():
    """EXP-COLLISION-3D-01 실행"""
    print("="*70)
    print("EXP-COLLISION-3D-01: 규칙 충돌 3D 분포")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("-"*70)
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    storm_in_signals = [s for s in signals if classify_storm_coordinate(s) == "STORM_IN"]
    print(f"Storm-IN signals: {len(storm_in_signals)}")
    
    data_points = []
    
    for s in storm_in_signals:
        ts = s.get('ts')
        if not ts:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        try:
            idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        except:
            continue
        
        if idx < 40 or idx + 35 >= len(chart_df):
            continue
        
        x = calc_global_coherence(chart_df, idx)
        y = calc_local_irreversibility(chart_df, idx)
        z = calc_phase_depth(chart_df, idx)
        
        direction = get_direction_outcome(chart_df, idx)
        loss = get_loss_outcome(chart_df, idx)
        
        if direction is None or loss is None:
            continue
        
        data_points.append({
            'ts': ts,
            'x': x,
            'y': y,
            'z': z,
            'direction': direction,
            'loss': loss
        })
    
    print(f"Valid data points: {len(data_points)}")
    
    fig = plt.figure(figsize=(16, 12))
    
    ax1 = fig.add_subplot(221, projection='3d')
    
    colors = []
    for d in data_points:
        if d['direction'] == 'UP':
            colors.append('green')
        elif d['direction'] == 'DOWN':
            colors.append('red')
        else:
            colors.append('gray')
    
    xs = [d['x'] for d in data_points]
    ys = [d['y'] for d in data_points]
    zs = [d['z'] for d in data_points]
    
    ax1.scatter(xs, ys, zs, c=colors, alpha=0.6, s=30)
    ax1.set_xlabel('X: Global Coherence')
    ax1.set_ylabel('Y: Local Irreversibility')
    ax1.set_zlabel('Z: Phase Depth')
    ax1.set_title('3D Rule Collision Space\n(Green=UP, Red=DOWN, Gray=NEUTRAL)')
    
    ax2 = fig.add_subplot(222)
    
    alphas = [0.3 if d['loss'] else 0.8 for d in data_points]
    sizes = [100 if not d['loss'] else 30 for d in data_points]
    
    for i, d in enumerate(data_points):
        ax2.scatter(d['x'], d['y'], c=colors[i], alpha=alphas[i], s=sizes[i])
    
    ax2.set_xlabel('X: Global Coherence')
    ax2.set_ylabel('Y: Local Irreversibility')
    ax2.set_title('X-Y Plane (Coherence vs Irreversibility)\nLarge=Win, Small=Loss')
    ax2.grid(True, alpha=0.3)
    
    ax3 = fig.add_subplot(223)
    
    for i, d in enumerate(data_points):
        ax3.scatter(d['y'], d['z'], c=colors[i], alpha=alphas[i], s=sizes[i])
    
    ax3.set_xlabel('Y: Local Irreversibility')
    ax3.set_ylabel('Z: Phase Depth')
    ax3.set_title('Y-Z Plane (Irreversibility vs Depth)\nTransition Band = High Y, Mid Z')
    ax3.grid(True, alpha=0.3)
    
    ax4 = fig.add_subplot(224)
    
    x_bins = np.linspace(0, 1, 6)
    y_bins = np.linspace(0, 1, 6)
    
    heatmap_data = np.zeros((5, 5))
    count_data = np.zeros((5, 5))
    
    for d in data_points:
        x_idx = min(int(d['x'] * 5), 4)
        y_idx = min(int(d['y'] * 5), 4)
        
        skew = 1 if d['direction'] == 'DOWN' else (-1 if d['direction'] == 'UP' else 0)
        heatmap_data[y_idx, x_idx] += skew
        count_data[y_idx, x_idx] += 1
    
    count_data[count_data == 0] = 1
    heatmap_data = heatmap_data / count_data
    
    im = ax4.imshow(heatmap_data, cmap='RdYlGn_r', aspect='auto', 
                     extent=[0, 1, 0, 1], origin='lower', vmin=-1, vmax=1)
    ax4.set_xlabel('X: Global Coherence')
    ax4.set_ylabel('Y: Local Irreversibility')
    ax4.set_title('Direction Skew Heatmap\n(Red=DOWN bias, Green=UP bias)')
    plt.colorbar(im, ax=ax4, label='Skew')
    
    plt.tight_layout()
    
    output_path = 'v7-grammar-system/analysis/phase_k/collision_3d_visualization.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"\nVisualization saved to: {output_path}")
    
    print("\n" + "="*70)
    print("REGION ANALYSIS")
    print("="*70)
    
    regions = {
        'Flat (X>0.6, Y<0.4)': [],
        'Turbulent (X<0.4, Y<0.4)': [],
        'Ridge (X<0.5, Y>0.5)': [],
        'Core (X<0.3, Y>0.7)': []
    }
    
    for d in data_points:
        if d['x'] > 0.6 and d['y'] < 0.4:
            regions['Flat (X>0.6, Y<0.4)'].append(d)
        elif d['x'] < 0.4 and d['y'] < 0.4:
            regions['Turbulent (X<0.4, Y<0.4)'].append(d)
        elif d['x'] < 0.5 and d['y'] > 0.5:
            regions['Ridge (X<0.5, Y>0.5)'].append(d)
        if d['x'] < 0.3 and d['y'] > 0.7:
            regions['Core (X<0.3, Y>0.7)'].append(d)
    
    for region_name, region_data in regions.items():
        n = len(region_data)
        if n == 0:
            continue
        
        up = sum(1 for d in region_data if d['direction'] == 'UP')
        down = sum(1 for d in region_data if d['direction'] == 'DOWN')
        loss_rate = sum(1 for d in region_data if d['loss']) / n * 100
        skew = (down - up) / n * 100
        
        print(f"\n{region_name}:")
        print(f"  N = {n}")
        print(f"  UP: {up/n*100:.1f}%, DOWN: {down/n*100:.1f}%")
        print(f"  Skew: {skew:+.1f}pp")
        print(f"  Loss Rate: {loss_rate:.1f}%")
    
    result = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_COLLISION_3D_01',
        'total_points': len(data_points),
        'visualization': output_path
    }
    
    result_path = 'v7-grammar-system/analysis/phase_k/exp_collision_3d_01_result.json'
    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\nResults saved to: {result_path}")
    
    return result


if __name__ == "__main__":
    run_exp_collision_3d_01()
