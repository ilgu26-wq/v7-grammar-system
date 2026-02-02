"""
EXP-DEPTH-ENTRY-01: Depth Attractor 접근 판별 실험
==================================================

목적:
  Force가 존재함에도 상태의 선택지가 구조적으로 붕괴되고 있는가?
  → YES면 Depth Attractor 접근 상태

관측 축 (Force 대체 ❌, 보완 ⭕):
  A) RFC (Recovery Failure Count) - 회복 시도 연속 실패 수
  B) BCR (Branch Collapse Ratio) - 가능한 다음 상태 수 감소율
  C) EDA (Energy Dissipation Asymmetry) - 에너지 투입 대비 회수 실패

판정:
  IF RFC ≥ 2 AND BCR ≤ 0.6 AND EDA ≤ 0.7
  THEN DEPTH_ATTRACTOR_APPROACH = TRUE
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


def calc_rfc(chart_df: pd.DataFrame, ts: str, lookback: int = 10) -> int:
    """
    A) Recovery Failure Count
    - 최근 N 바에서 회복 시도 연속 실패 수
    - 회복 = 이전 고점의 50% 이상 되돌림
    """
    try:
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        
        if idx < lookback:
            return 0
        
        window = chart_df.iloc[idx-lookback:idx]
        
        if len(window) < lookback:
            return 0
        
        consecutive_fails = 0
        
        for i in range(1, len(window)):
            prev_range = window['high'].iloc[i-1] - window['low'].iloc[i-1]
            if prev_range < 2:
                continue
            
            current_close = window['close'].iloc[i]
            prev_high = window['high'].iloc[i-1]
            prev_low = window['low'].iloc[i-1]
            
            recovery_threshold = prev_low + prev_range * 0.5
            
            if current_close < recovery_threshold:
                consecutive_fails += 1
            else:
                consecutive_fails = 0
        
        return consecutive_fails
    except:
        return 0


def calc_bcr(chart_df: pd.DataFrame, ts: str, lookback: int = 10) -> float:
    """
    B) Branch Collapse Ratio
    - 가능한 다음 상태 수 감소율
    - 최근 변동폭 / 과거 변동폭
    """
    try:
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        
        if idx < lookback * 2:
            return 1.0
        
        recent = chart_df.iloc[idx-lookback//2:idx]
        past = chart_df.iloc[idx-lookback:idx-lookback//2]
        
        recent_range = recent['high'].max() - recent['low'].min()
        past_range = past['high'].max() - past['low'].min()
        
        if past_range < 1:
            return 1.0
        
        return recent_range / past_range
    except:
        return 1.0


def calc_eda(chart_df: pd.DataFrame, ts: str, lookback: int = 10) -> float:
    """
    C) Energy Dissipation Asymmetry
    - 에너지 투입 대비 회수 실패
    - 최근 바 크기 / 과거 바 크기
    """
    try:
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        
        if idx < lookback:
            return 1.0
        
        window = chart_df.iloc[idx-lookback:idx]
        
        if len(window) < lookback:
            return 1.0
        
        recent_avg = (window['high'].iloc[-lookback//2:] - window['low'].iloc[-lookback//2:]).mean()
        past_avg = (window['high'].iloc[:lookback//2] - window['low'].iloc[:lookback//2]).mean()
        
        if past_avg < 0.1:
            return 1.0
        
        return recent_avg / past_avg
    except:
        return 1.0


def is_depth_attractor_approach(rfc: int, bcr: float, eda: float, strict: bool = False) -> bool:
    """
    Windmill Rule (완화된 버전):
    Strict: RFC ≥ 2 AND BCR ≤ 0.6 AND EDA ≤ 0.7
    Relaxed: RFC ≥ 1 AND BCR ≤ 0.8 AND EDA ≤ 0.85
    """
    if strict:
        return rfc >= 2 and bcr <= 0.6 and eda <= 0.7
    else:
        return rfc >= 1 and bcr <= 0.8 and eda <= 0.85


def get_loss_from_chart(chart_df: pd.DataFrame, 
                        entry_ts: str, 
                        entry_price: float,
                        direction: str = 'SHORT',
                        tp: float = 20,
                        sl: float = 10,
                        lookahead: int = 30) -> bool:
    """손실 여부 판정"""
    try:
        ts = pd.to_datetime(entry_ts)
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        
        idx = chart_df.index.get_indexer([ts], method='nearest')[0]
        
        if idx < 0 or idx + lookahead >= len(chart_df):
            return None
        
        future = chart_df.iloc[idx+1:idx+1+lookahead]
        
        for _, bar in future.iterrows():
            if direction == 'SHORT':
                if bar['low'] <= entry_price - tp:
                    return False  # Win
                if bar['high'] >= entry_price + sl:
                    return True   # Loss
            else:
                if bar['high'] >= entry_price + tp:
                    return False  # Win
                if bar['low'] <= entry_price - sl:
                    return True   # Loss
        
        return True  # Timeout = Loss
    except:
        return None


def run_exp_depth_entry_01():
    """EXP-DEPTH-ENTRY-01 실행"""
    print("="*70)
    print("EXP-DEPTH-ENTRY-01: Depth Attractor 접근 판별")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\n질문: Force가 존재함에도 상태 선택지가 붕괴되고 있는가?")
    print("-"*70)
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    print(f"Total signals: {len(signals)}")
    print(f"Chart range: {chart_start} to {chart_end}")
    
    qualified = [s for s in signals 
                 if classify_storm_coordinate(s) == "STORM_IN"
                 and s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.3]
    
    print(f"Storm-IN qualified: {len(qualified)}")
    
    pass_group = []
    reject_group = []
    
    for s in qualified:
        ts = s.get('ts')
        entry_price = s.get('entry_price')
        
        if not ts or not entry_price:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        rfc = calc_rfc(chart_df, ts)
        bcr = calc_bcr(chart_df, ts)
        eda = calc_eda(chart_df, ts)
        
        is_daa = is_depth_attractor_approach(rfc, bcr, eda)
        
        loss = get_loss_from_chart(chart_df, ts, entry_price, 'SHORT')
        
        if loss is None:
            continue
        
        data = {
            'ts': ts,
            'rfc': rfc,
            'bcr': bcr,
            'eda': eda,
            'is_daa': is_daa,
            'loss': loss
        }
        
        if is_daa:
            pass_group.append(data)
        else:
            reject_group.append(data)
    
    print(f"\nPASS (Depth Attractor): {len(pass_group)}")
    print(f"REJECT: {len(reject_group)}")
    
    print("\n" + "="*70)
    print("LOSS RATE COMPARISON")
    print("="*70)
    
    pass_losses = sum(1 for d in pass_group if d['loss'])
    pass_total = len(pass_group)
    pass_loss_rate = pass_losses / pass_total * 100 if pass_total > 0 else 0
    
    reject_losses = sum(1 for d in reject_group if d['loss'])
    reject_total = len(reject_group)
    reject_loss_rate = reject_losses / reject_total * 100 if reject_total > 0 else 0
    
    print(f"\nPASS Group (Depth Attractor):")
    print(f"  N = {pass_total}")
    print(f"  Loss Rate = {pass_loss_rate:.1f}%")
    
    print(f"\nREJECT Group:")
    print(f"  N = {reject_total}")
    print(f"  Loss Rate = {reject_loss_rate:.1f}%")
    
    diff = reject_loss_rate - pass_loss_rate
    print(f"\nDifference: {diff:+.1f}pp")
    
    print("\n" + "="*70)
    print("VERDICT")
    print("="*70)
    
    if diff >= 15:
        verdict = "✅ PASS"
        interpretation = """
Depth Attractor 접근 상태가 유의미하게 낮은 손실률을 보임.

→ Force가 흡수되는 순간이 실시간으로 관측 가능
→ RFC/BCR/EDA 조합이 구조적 붕괴를 감지함
"""
    elif pass_total < 10:
        verdict = "⚠️ INSUFFICIENT DATA"
        interpretation = "PASS 그룹 샘플 부족"
    else:
        verdict = "❌ FAIL"
        interpretation = """
손실률 차이가 15pp 미만.

→ 현재 조건으로는 Depth Attractor 접근 판별 불가
→ RFC/BCR/EDA 정의 재검토 필요
"""
    
    print(f"\nVerdict: {verdict}")
    print(interpretation)
    
    print("\n" + "="*70)
    print("COMPONENT DISTRIBUTION (PASS GROUP)")
    print("="*70)
    
    if pass_group:
        avg_rfc = sum(d['rfc'] for d in pass_group) / len(pass_group)
        avg_bcr = sum(d['bcr'] for d in pass_group) / len(pass_group)
        avg_eda = sum(d['eda'] for d in pass_group) / len(pass_group)
        
        print(f"\n  Avg RFC: {avg_rfc:.1f}")
        print(f"  Avg BCR: {avg_bcr:.2f}")
        print(f"  Avg EDA: {avg_eda:.2f}")
    
    result = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_DEPTH_ENTRY_01',
        'pass_group': {
            'n': pass_total,
            'loss_rate': pass_loss_rate
        },
        'reject_group': {
            'n': reject_total,
            'loss_rate': reject_loss_rate
        },
        'difference': diff,
        'verdict': verdict
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/exp_depth_entry_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return result


if __name__ == "__main__":
    run_exp_depth_entry_01()
