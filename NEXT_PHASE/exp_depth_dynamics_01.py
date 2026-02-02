"""
EXP-DEPTH-DYNAMICS-01: Depth 형성/소산/전이 동역학 분석
=======================================================
목적: "수렴 가능 조건이 언제 성립하는가?"에 답한다

핵심 질문:
- Depth가 형성(FORM)되는 선행 조건은 무엇인가?
- Depth가 소산(DISSIPATE)되는 선행 조건은 무엇인가?
- FAST↔SLOW 전이(TRANSITION)의 선행 조건은 무엇인가?

방법론:
1. 전 구간에서 depth_t 시계열 생성
2. FORM/DISSIPATE/TRANSITION 이벤트 타임스탬프 생성
3. 각 이벤트의 직전 윈도우(-30bar ~ -1bar)에서 조건 피처 집계
4. 이벤트 없는 구간(랜덤 샘플)과 비교
5. 리프트/우도비로 판정

판정 기준:
- event 대비 non-event에서 LR >= 3
- OOS 5-fold 중 4/5 이상 재현
"""

import json
import os
import numpy as np
import pandas as pd
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

RESULT_FILE = "v7-grammar-system/results/exp_depth_dynamics_01.json"

def calc_depth(df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    """Depth = (high_20 - close) / range_20"""
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 0.5
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    range_20 = high_20 - low_20
    if range_20 < 0.01:
        return 0.5
    close = df.iloc[idx]['close']
    return (high_20 - close) / range_20

def calc_depth_slope(depths: List[float], k: int = 5) -> float:
    """최근 k바 depth 변화율"""
    if len(depths) < k + 1:
        return 0.0
    recent = depths[-k:]
    if len(recent) < 2:
        return 0.0
    return (recent[-1] - recent[0]) / k

def calc_dc_pre(df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    """DC_pre = 직전 N봉 종가 표준편차 / ATR"""
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 1.0
    close_std = window['close'].std()
    atr = (window['high'] - window['low']).mean()
    if atr < 0.01:
        return 1.0
    return close_std / atr

def calc_er(df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    """Efficiency Ratio = |price_change| / sum(|bar_changes|)"""
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 0.5
    price_change = abs(window.iloc[-1]['close'] - window.iloc[0]['close'])
    bar_changes = abs(window['close'].diff().dropna()).sum()
    if bar_changes < 0.01:
        return 1.0
    return min(1.0, price_change / bar_changes)

def calc_delta(df: pd.DataFrame, idx: int) -> float:
    """Delta = volume * (close - open) / range"""
    row = df.iloc[idx]
    rng = row['high'] - row['low']
    if rng < 0.01:
        return 0.0
    vol = row.get('volume', 1.0)
    return vol * (row['close'] - row['open']) / rng

def calc_channel_pct(df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    """Channel % = (close - low_20) / (high_20 - low_20) * 100"""
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 50.0
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    rng = high_20 - low_20
    if rng < 0.01:
        return 50.0
    close = df.iloc[idx]['close']
    return (close - low_20) / rng * 100

def calc_session_range(df: pd.DataFrame, idx: int, session_len: int = 100) -> float:
    """세션 범위 (terminal normalization용)"""
    start = max(0, idx - session_len + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 1.0
    return window['high'].max() - window['low'].min()

def classify_terminal(terminal_time_r: float) -> str:
    """FAST vs SLOW terminal 분류 (Terminal_Time_R 기준)"""
    return "FAST" if terminal_time_r < 0.3 else "SLOW"

def detect_events(depth_series: List[float], threshold_form: float = 0.15, threshold_diss: float = -0.15) -> Dict[str, List[int]]:
    """
    FORM/DISSIPATE/TRANSITION 이벤트 감지
    
    FORM: depth 상승 추세 시작 (slope > threshold_form, 이전 depth < 0.3)
    DISSIPATE: depth 하락 추세 시작 (slope < threshold_diss, 이전 depth > 0.7)
    TRANSITION: depth가 0.5 경계를 넘는 순간
    """
    events = {"FORM": [], "DISSIPATE": [], "TRANSITION": []}
    
    if len(depth_series) < 10:
        return events
    
    prev_side = "LOW" if depth_series[5] < 0.5 else "HIGH"
    
    for i in range(10, len(depth_series)):
        slope = calc_depth_slope(depth_series[:i+1], k=5)
        current_depth = depth_series[i]
        prev_depth = depth_series[i-1]
        
        # FORM: 낮은 상태에서 상승 시작
        if prev_depth < 0.3 and slope > threshold_form:
            events["FORM"].append(i)
        
        # DISSIPATE: 높은 상태에서 하락 시작
        if prev_depth > 0.7 and slope < threshold_diss:
            events["DISSIPATE"].append(i)
        
        # TRANSITION: 0.5 경계 교차
        curr_side = "LOW" if current_depth < 0.5 else "HIGH"
        if curr_side != prev_side:
            events["TRANSITION"].append(i)
            prev_side = curr_side
    
    return events

def extract_precondition_features(df: pd.DataFrame, event_idx: int, depth_series: List[float], 
                                   lookback: int = 30) -> Dict:
    """이벤트 직전 윈도우의 조건 피처 추출"""
    if event_idx < lookback:
        return None
    
    features = {}
    
    # 직전 윈도우 통계
    window_start = event_idx - lookback
    window_depths = depth_series[window_start:event_idx]
    
    features['depth_mean'] = np.mean(window_depths)
    features['depth_std'] = np.std(window_depths)
    features['depth_trend'] = calc_depth_slope(window_depths, k=min(10, len(window_depths)-1))
    features['depth_at_event'] = depth_series[event_idx]
    
    # 조건 피처 (이벤트 직전 바)
    pre_idx = event_idx - 1
    features['dc_pre'] = calc_dc_pre(df, pre_idx)
    features['er'] = calc_er(df, pre_idx)
    features['delta'] = abs(calc_delta(df, pre_idx))
    features['channel'] = calc_channel_pct(df, pre_idx)
    
    # 세션 컨텍스트
    features['session_range'] = calc_session_range(df, pre_idx)
    
    return features

def run_depth_dynamics_analysis(df: pd.DataFrame, sample_step: int = 10) -> Dict:
    """전체 데이터셋에서 Depth 동역학 분석 실행"""
    
    print("=" * 70)
    print("EXP-DEPTH-DYNAMICS-01: Depth 형성/소산/전이 동역학 분석")
    print("=" * 70)
    print(f"Total bars: {len(df)}")
    print(f"Sample step: {sample_step}")
    
    # 1. 전체 depth 시계열 생성
    print("\n[STEP 1] Generating depth time series...")
    depth_series = []
    for idx in range(len(df)):
        depth_series.append(calc_depth(df, idx))
    
    print(f"  Depth series length: {len(depth_series)}")
    print(f"  Depth range: [{min(depth_series):.3f}, {max(depth_series):.3f}]")
    print(f"  Depth mean: {np.mean(depth_series):.3f}")
    
    # 2. 이벤트 감지
    print("\n[STEP 2] Detecting FORM/DISSIPATE/TRANSITION events...")
    events = detect_events(depth_series)
    
    for event_type, indices in events.items():
        print(f"  {event_type}: {len(indices)} events")
    
    # 3. 이벤트별 선행 조건 추출
    print("\n[STEP 3] Extracting precondition features...")
    
    event_features = defaultdict(list)
    for event_type, indices in events.items():
        for idx in indices:
            features = extract_precondition_features(df, idx, depth_series)
            if features:
                features['event_type'] = event_type
                features['event_idx'] = idx
                event_features[event_type].append(features)
    
    # 4. 비이벤트 구간 랜덤 샘플링 (비교용)
    print("\n[STEP 4] Sampling non-event baseline...")
    all_event_indices = set()
    for indices in events.values():
        all_event_indices.update(indices)
        # 이벤트 주변 ±10바도 제외
        for idx in indices:
            all_event_indices.update(range(max(0, idx-10), min(len(df), idx+11)))
    
    non_event_candidates = [i for i in range(50, len(df)-50) 
                            if i not in all_event_indices]
    
    np.random.seed(42)
    n_samples = min(len(non_event_candidates), sum(len(v) for v in events.values()) * 2)
    sampled_non_events = np.random.choice(non_event_candidates, size=n_samples, replace=False)
    
    baseline_features = []
    for idx in sampled_non_events:
        features = extract_precondition_features(df, idx, depth_series)
        if features:
            features['event_type'] = 'NONE'
            features['event_idx'] = idx
            baseline_features.append(features)
    
    print(f"  Non-event samples: {len(baseline_features)}")
    
    # 5. 리프트/우도비 분석
    print("\n[STEP 5] Computing likelihood ratios...")
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "depth_stats": {
                "min": float(min(depth_series)),
                "max": float(max(depth_series)),
                "mean": float(np.mean(depth_series)),
                "std": float(np.std(depth_series))
            }
        },
        "event_counts": {k: len(v) for k, v in events.items()},
        "precondition_analysis": {}
    }
    
    feature_names = ['dc_pre', 'er', 'delta', 'channel', 'depth_mean', 'depth_std', 'depth_trend']
    
    for event_type in ['FORM', 'DISSIPATE', 'TRANSITION']:
        if not event_features[event_type]:
            continue
            
        print(f"\n  [{event_type}] Analysis (N={len(event_features[event_type])})")
        
        event_df = pd.DataFrame(event_features[event_type])
        baseline_df = pd.DataFrame(baseline_features)
        
        analysis = {"n_events": len(event_df), "features": {}}
        
        for feat in feature_names:
            if feat not in event_df.columns or feat not in baseline_df.columns:
                continue
                
            event_mean = event_df[feat].mean()
            baseline_mean = baseline_df[feat].mean()
            
            # 간단한 리프트 계산
            if baseline_mean != 0:
                lift = event_mean / baseline_mean
            else:
                lift = 1.0
            
            # 분포 비교 (percentile)
            event_median = event_df[feat].median()
            baseline_median = baseline_df[feat].median()
            
            analysis["features"][feat] = {
                "event_mean": float(event_mean),
                "baseline_mean": float(baseline_mean),
                "lift": float(lift),
                "event_median": float(event_median),
                "baseline_median": float(baseline_median),
                "significant": bool(abs(lift - 1.0) > 0.3)  # 30% 이상 차이
            }
            
            sig_marker = "***" if analysis["features"][feat]["significant"] else ""
            print(f"    {feat}: event={event_mean:.3f} vs baseline={baseline_mean:.3f} (lift={lift:.2f}) {sig_marker}")
        
        results["precondition_analysis"][event_type] = analysis
    
    # 6. 핵심 발견 요약
    print("\n" + "=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)
    
    key_findings = []
    
    for event_type, analysis in results["precondition_analysis"].items():
        significant_features = [
            (feat, data) for feat, data in analysis["features"].items() 
            if data.get("significant", False)
        ]
        
        if significant_features:
            finding = f"{event_type}: "
            finding += ", ".join([f"{f}(lift={d['lift']:.2f})" for f, d in significant_features])
            key_findings.append(finding)
            print(f"  {finding}")
    
    results["key_findings"] = key_findings
    
    return results

def main():
    # 데이터 로드
    data_paths = [
        "v7-grammar-system/data/chart_combined_full.csv",
        "data/chart_combined_full.csv",
        "attached_assets/chart_combined_full.csv"
    ]
    
    df = None
    for path in data_paths:
        if os.path.exists(path):
            df = pd.read_csv(path)
            print(f"Loaded data from: {path}")
            break
    
    if df is None:
        # 시뮬레이션 데이터 생성
        print("No data file found. Generating simulated data...")
        np.random.seed(42)
        n = 5000
        
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        high = close + np.abs(np.random.randn(n) * 0.3)
        low = close - np.abs(np.random.randn(n) * 0.3)
        
        df = pd.DataFrame({
            'open': close - np.random.randn(n) * 0.1,
            'high': high,
            'low': low,
            'close': close,
            'volume': np.random.randint(100, 1000, n)
        })
        print(f"Generated {n} simulated bars")
    
    # 분석 실행
    results = run_depth_dynamics_analysis(df, sample_step=10)
    
    # 결과 저장
    os.makedirs(os.path.dirname(RESULT_FILE), exist_ok=True)
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {RESULT_FILE}")
    
    return results

if __name__ == "__main__":
    main()
