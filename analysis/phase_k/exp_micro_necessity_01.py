"""
EXP-MICRO-NECESSITY-01: 필수 미시법칙 탐색
==========================================

목적:
  Ridge(풍차 초입)에서 전이 구조를 유지시키는 최소 미시법칙을 찾는다.

후보 Micro-Laws:
  M1: Revisit Anchor (재도달 구조)
  M2: Recovery Failure Count (RFC)
  M3: Branch Collapse (BCR)
  M4: Energy Dissipation (EDA)
  M5: DC Extreme Gate
  M6: Volatility Regime Gate
  M7: STB Sequencing Rule (3-bar window)

붕괴 지표:
  S-1: Ridge 유지율 붕괴 (≥20% 상대변화)
  S-2: 전이 언어 붕괴 (방향 분포 KL-divergence)
  S-3: 구조 붕괴 (Win rate 급변 ≥15pp)

판정:
  Mi 제거 후 2개 이상 붕괴 → 필수
  3개 다 안정 → 비필수
"""

import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Callable
from collections import defaultdict

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
    """X축: Global Coherence"""
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
    """Y축: Local Irreversibility"""
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


def is_ridge(x: float, y: float) -> bool:
    """Ridge 영역 판정: X<0.5 AND Y>0.5"""
    return x < 0.5 and y > 0.5


def calc_m1_revisit_anchor(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> bool:
    """M1: Revisit Anchor - 이전 고점/저점 재도달"""
    if idx < lookback:
        return False
    window = chart_df.iloc[idx-lookback:idx]
    current = chart_df.iloc[idx]
    
    prev_high = window['high'].max()
    prev_low = window['low'].min()
    
    revisit_high = current['high'] >= prev_high * 0.99
    revisit_low = current['low'] <= prev_low * 1.01
    
    return revisit_high or revisit_low


def calc_m2_rfc(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> bool:
    """M2: Recovery Failure Count ≥ 1"""
    if idx < lookback:
        return False
    
    window = chart_df.iloc[idx-lookback:idx]
    consecutive_fails = 0
    
    for i in range(1, len(window)):
        prev_range = window['high'].iloc[i-1] - window['low'].iloc[i-1]
        if prev_range < 1:
            continue
        current_close = window['close'].iloc[i]
        prev_low = window['low'].iloc[i-1]
        recovery_threshold = prev_low + prev_range * 0.4
        if current_close < recovery_threshold:
            consecutive_fails += 1
        else:
            consecutive_fails = 0
    
    return consecutive_fails >= 1


def calc_m3_bcr(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> bool:
    """M3: Branch Collapse Ratio ≤ 0.8"""
    if idx < lookback:
        return False
    
    recent = chart_df.iloc[idx-lookback//2:idx]
    past = chart_df.iloc[idx-lookback:idx-lookback//2]
    
    recent_range = recent['high'].max() - recent['low'].min()
    past_range = past['high'].max() - past['low'].min()
    
    bcr = recent_range / past_range if past_range > 0.5 else 1.0
    return bcr <= 0.8


def calc_m4_eda(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> bool:
    """M4: Energy Dissipation Asymmetry ≤ 0.85"""
    if idx < lookback:
        return False
    
    window = chart_df.iloc[idx-lookback:idx]
    
    recent_avg = (window['high'].iloc[-lookback//2:] - window['low'].iloc[-lookback//2:]).mean()
    past_avg = (window['high'].iloc[:lookback//2] - window['low'].iloc[:lookback//2]).mean()
    
    eda = recent_avg / past_avg if past_avg > 0.1 else 1.0
    return eda <= 0.85


def calc_m5_dc_extreme(chart_df: pd.DataFrame, idx: int, lookback: int = 20) -> bool:
    """M5: DC Extreme Gate - 채널 극단"""
    if idx < lookback:
        return False
    
    window = chart_df.iloc[idx-lookback:idx]
    current = chart_df.iloc[idx]
    
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    range_20 = high_20 - low_20
    
    if range_20 < 1:
        return False
    
    channel_pct = (current['close'] - low_20) / range_20 * 100
    
    return channel_pct >= 80 or channel_pct <= 20


def calc_m6_vol_regime(chart_df: pd.DataFrame, idx: int, lookback: int = 20) -> bool:
    """M6: Volatility Regime Gate - 변동성 급변"""
    if idx < lookback * 2:
        return False
    
    recent = chart_df.iloc[idx-lookback//2:idx]
    past = chart_df.iloc[idx-lookback:idx-lookback//2]
    
    recent_vol = (recent['high'] - recent['low']).std()
    past_vol = (past['high'] - past['low']).std()
    
    vol_ratio = recent_vol / past_vol if past_vol > 0.1 else 1.0
    
    return vol_ratio >= 1.3 or vol_ratio <= 0.7


def calc_m7_stb_window(chart_df: pd.DataFrame, idx: int, window_size: int = 3) -> bool:
    """M7: STB Sequencing Rule - 3-bar window 패턴"""
    if idx < window_size:
        return False
    
    window = chart_df.iloc[idx-window_size:idx]
    
    closes = window['close'].values
    
    all_down = all(closes[i] < closes[i-1] for i in range(1, len(closes)))
    all_up = all(closes[i] > closes[i-1] for i in range(1, len(closes)))
    
    return all_down or all_up


def get_direction_outcome(chart_df: pd.DataFrame, idx: int, lookahead: int = 20) -> str:
    """방향 결과"""
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


def get_win_loss(chart_df: pd.DataFrame, idx: int, lookahead: int = 30) -> bool:
    """승패 판정 (SHORT 기준)"""
    if idx + lookahead >= len(chart_df):
        return None
    
    entry = chart_df.iloc[idx]['close']
    future = chart_df.iloc[idx+1:idx+1+lookahead]
    
    for _, bar in future.iterrows():
        if bar['low'] <= entry - 20:
            return True
        if bar['high'] >= entry + 10:
            return False
    
    return False


def calc_kl_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
    """KL Divergence 계산"""
    kl = 0
    for key in p:
        if p[key] > 0 and q.get(key, 0) > 0:
            kl += p[key] * np.log(p[key] / q[key])
    return kl


def run_ablation_test(data_points: List[Dict], micro_law_name: str, 
                      micro_law_fn: Callable, chart_df: pd.DataFrame) -> Dict:
    """단일 미시법칙 제거 테스트"""
    
    baseline_ridge = [d for d in data_points if d['is_ridge']]
    baseline_n = len(baseline_ridge)
    
    if baseline_n == 0:
        return {'status': 'NO_DATA'}
    
    baseline_dir = {'UP': 0, 'DOWN': 0, 'NEUTRAL': 0}
    baseline_wins = 0
    
    for d in baseline_ridge:
        baseline_dir[d['direction']] += 1
        if d['win']:
            baseline_wins += 1
    
    baseline_dir_dist = {k: v/baseline_n for k, v in baseline_dir.items()}
    baseline_win_rate = baseline_wins / baseline_n
    
    ablated_ridge = []
    for d in data_points:
        if not d['is_ridge']:
            continue
        
        idx = d['idx']
        law_active = micro_law_fn(chart_df, idx)
        
        if not law_active:
            ablated_ridge.append(d)
    
    ablated_n = len(ablated_ridge)
    
    if ablated_n == 0:
        return {
            'status': 'ALL_FILTERED',
            'interpretation': f'{micro_law_name}이 모든 Ridge 샘플에서 활성화됨 → 필수 후보'
        }
    
    ablated_dir = {'UP': 0, 'DOWN': 0, 'NEUTRAL': 0}
    ablated_wins = 0
    
    for d in ablated_ridge:
        ablated_dir[d['direction']] += 1
        if d['win']:
            ablated_wins += 1
    
    ablated_dir_dist = {k: v/ablated_n for k, v in ablated_dir.items()}
    ablated_win_rate = ablated_wins / ablated_n
    
    ridge_rate_change = abs(ablated_n - baseline_n) / baseline_n * 100
    
    kl_div = calc_kl_divergence(baseline_dir_dist, ablated_dir_dist)
    
    win_rate_change = abs(ablated_win_rate - baseline_win_rate) * 100
    
    s1_collapse = ridge_rate_change >= 20
    s2_collapse = kl_div >= 0.1
    s3_collapse = win_rate_change >= 15
    
    collapse_count = sum([s1_collapse, s2_collapse, s3_collapse])
    
    return {
        'status': 'TESTED',
        'baseline_n': baseline_n,
        'ablated_n': ablated_n,
        'ridge_rate_change': ridge_rate_change,
        'kl_divergence': kl_div,
        'baseline_win_rate': baseline_win_rate * 100,
        'ablated_win_rate': ablated_win_rate * 100,
        'win_rate_change': win_rate_change,
        's1_collapse': s1_collapse,
        's2_collapse': s2_collapse,
        's3_collapse': s3_collapse,
        'collapse_count': collapse_count,
        'is_necessary': collapse_count >= 2
    }


def run_exp_micro_necessity_01():
    """EXP-MICRO-NECESSITY-01 실행"""
    print("="*70)
    print("EXP-MICRO-NECESSITY-01: 필수 미시법칙 탐색")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\n목적: Ridge 전이 구조를 유지시키는 최소 미시법칙 찾기")
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
        ridge = is_ridge(x, y)
        
        direction = get_direction_outcome(chart_df, idx)
        win = get_win_loss(chart_df, idx)
        
        if direction is None or win is None:
            continue
        
        data_points.append({
            'ts': ts,
            'idx': idx,
            'x': x,
            'y': y,
            'is_ridge': ridge,
            'direction': direction,
            'win': win
        })
    
    print(f"Valid data points: {len(data_points)}")
    
    ridge_count = sum(1 for d in data_points if d['is_ridge'])
    print(f"Ridge samples: {ridge_count}")
    
    micro_laws = {
        'M1_Revisit_Anchor': calc_m1_revisit_anchor,
        'M2_RFC': calc_m2_rfc,
        'M3_BCR': calc_m3_bcr,
        'M4_EDA': calc_m4_eda,
        'M5_DC_Extreme': calc_m5_dc_extreme,
        'M6_Vol_Regime': calc_m6_vol_regime,
        'M7_STB_Window': calc_m7_stb_window
    }
    
    print("\n" + "="*70)
    print("ABLATION TESTS")
    print("="*70)
    
    results = {}
    
    for law_name, law_fn in micro_laws.items():
        print(f"\n--- {law_name} ---")
        result = run_ablation_test(data_points, law_name, law_fn, chart_df)
        results[law_name] = result
        
        if result['status'] == 'ALL_FILTERED':
            print(f"  Status: ALL_FILTERED")
            print(f"  → {law_name}이 모든 Ridge에서 활성화 = 필수 후보")
        elif result['status'] == 'TESTED':
            print(f"  Baseline N: {result['baseline_n']}")
            print(f"  Ablated N: {result['ablated_n']}")
            print(f"  Ridge Rate Change: {result['ridge_rate_change']:.1f}% {'⚠️' if result['s1_collapse'] else ''}")
            print(f"  KL Divergence: {result['kl_divergence']:.3f} {'⚠️' if result['s2_collapse'] else ''}")
            print(f"  Win Rate: {result['baseline_win_rate']:.1f}% → {result['ablated_win_rate']:.1f}% ({result['win_rate_change']:+.1f}pp) {'⚠️' if result['s3_collapse'] else ''}")
            print(f"  Collapse Count: {result['collapse_count']}/3")
            print(f"  → {'🔴 NECESSARY' if result['is_necessary'] else '⚪ Not Necessary'}")
    
    print("\n" + "="*70)
    print("MICRO LAW REGISTRY")
    print("="*70)
    
    necessary_laws = []
    non_necessary_laws = []
    
    for law_name, result in results.items():
        if result['status'] == 'ALL_FILTERED' or (result['status'] == 'TESTED' and result.get('is_necessary', False)):
            necessary_laws.append(law_name)
        else:
            non_necessary_laws.append(law_name)
    
    print(f"\n🔴 NECESSARY LAWS ({len(necessary_laws)}):")
    for law in necessary_laws:
        print(f"  - {law}")
    
    print(f"\n⚪ Non-Necessary Laws ({len(non_necessary_laws)}):")
    for law in non_necessary_laws:
        print(f"  - {law}")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_MICRO_NECESSITY_01',
        'total_points': len(data_points),
        'ridge_count': ridge_count,
        'results': results,
        'necessary_laws': necessary_laws,
        'non_necessary_laws': non_necessary_laws
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/exp_micro_necessity_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_micro_necessity_01()
