"""
EXP-TYPEC-RESOLUTION-01: Type C 분해 실험

목표: Type C(거짓 경보)를 두 종류로 분해

C1: Safe False - 진짜 아무 일 없음 (EXIT해도 손해만)
C2: Soft Terminal - Absorb는 아니지만 DAA/MAE tail 커짐 (EXIT가 맞음)

방법:
- Type C 케이스에서:
  - DAA 접근률
  - MAE tail
  - 세션 duration 붕괴 여부
- 를 비교해서 C1/C2 분리
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Tuple
from collections import defaultdict
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import load_signals

def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    df.sort_index(inplace=True)
    return df

def calc_e_resp(df: pd.DataFrame, idx: int, lookback: int = 10) -> str:
    if idx < lookback:
        return "UNKNOWN"
    
    window = df.iloc[idx-lookback:idx+1]
    closes = window['close'].values
    highs = window['high'].values
    lows = window['low'].values
    
    atr = np.mean(highs - lows)
    if atr < 0.1:
        return "UNKNOWN"
    
    price_change = closes[-1] - closes[0]
    rfc = (highs[-1] - lows[-1]) / atr if atr > 0 else 1.0
    
    if price_change > atr * 0.3 and rfc < 1.5:
        return "HOLD"
    elif price_change < -atr * 0.3 and rfc < 1.5:
        return "HOLD"
    else:
        return "RELEASE"

def detect_absorb(df: pd.DataFrame, idx: int, horizon: int = 30) -> Tuple[bool, int]:
    """Absorb 발생 여부 및 시점"""
    if idx + horizon >= len(df):
        return False, -1
    
    entry = df.iloc[idx]['close']
    atr = np.mean(df.iloc[idx-10:idx+1]['high'] - df.iloc[idx-10:idx+1]['low'])
    
    threshold = atr * 2.5
    
    for i in range(1, horizon + 1):
        if idx + i >= len(df):
            break
        
        future_close = df.iloc[idx + i]['close']
        mae = abs(future_close - entry)
        
        if mae > threshold:
            return True, i
    
    return False, -1

def calc_session_metrics(df: pd.DataFrame, idx: int, horizon: int = 30) -> Dict:
    """세션 메트릭 계산"""
    if idx + horizon >= len(df):
        return None
    
    entry = df.iloc[idx]['close']
    atr = np.mean(df.iloc[idx-10:idx+1]['high'] - df.iloc[idx-10:idx+1]['low'])
    
    future = df.iloc[idx+1:idx+horizon+1]
    
    closes = future['close'].values
    highs = future['high'].values
    lows = future['low'].values
    
    mae_up = max(highs) - entry
    mae_down = entry - min(lows)
    mae = max(mae_up, mae_down)
    
    daa = entry + (atr * 1.5)
    daa_reached = any(closes >= daa)
    
    daa_down = entry - (atr * 1.5)
    daa_down_reached = any(closes <= daa_down)
    
    drawdown = []
    running_max = entry
    for c in closes:
        running_max = max(running_max, c)
        dd = running_max - c
        drawdown.append(dd)
    
    max_drawdown = max(drawdown) if drawdown else 0
    
    volatility_burst = 0
    for i, (h, l) in enumerate(zip(highs, lows)):
        if h - l > atr * 1.8:
            volatility_burst += 1
    
    reversal_count = 0
    for i in range(1, len(closes)):
        if (closes[i] - closes[i-1]) * (closes[i-1] - closes[i-2] if i > 1 else 0) < 0:
            reversal_count += 1
    
    return {
        'entry': entry,
        'atr': atr,
        'mae': mae,
        'mae_atr': mae / atr if atr > 0 else 0,
        'daa_up_reached': daa_reached,
        'daa_down_reached': daa_down_reached,
        'max_drawdown': max_drawdown,
        'max_drawdown_atr': max_drawdown / atr if atr > 0 else 0,
        'volatility_bursts': volatility_burst,
        'reversal_count': reversal_count
    }

def classify_type_c(metrics: Dict) -> str:
    """Type C를 C1(Safe) vs C2(Soft Terminal)로 분류"""
    if metrics is None:
        return "UNKNOWN"
    
    mae_atr = metrics['mae_atr']
    dd_atr = metrics['max_drawdown_atr']
    vol_bursts = metrics['volatility_bursts']
    daa_any = metrics['daa_up_reached'] or metrics['daa_down_reached']
    
    danger_score = 0
    
    if mae_atr > 1.5:
        danger_score += 1
    if mae_atr > 2.0:
        danger_score += 1
    
    if dd_atr > 1.0:
        danger_score += 1
    if dd_atr > 1.5:
        danger_score += 1
    
    if vol_bursts >= 2:
        danger_score += 1
    
    if daa_any:
        danger_score += 1
    
    if danger_score >= 2:
        return "C2_SOFT_TERMINAL"
    else:
        return "C1_SAFE_FALSE"

def run():
    print("="*70)
    print("EXP-TYPEC-RESOLUTION-01: Type C 분해 실험")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    events = []
    for s in signals:
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
        
        if idx < 50 or idx + 35 >= len(chart_df):
            continue
        
        events.append({'ts': ts, 'idx': idx})
    
    events = events[:500]
    print(f"\nEvents: N = {len(events)}")
    
    type_c_cases = []
    type_a_cases = []
    type_b_cases = []
    success_cases = []
    
    for e in events:
        idx = e['idx']
        
        e_resp = calc_e_resp(chart_df, idx)
        
        absorb_occurred, absorb_bar = detect_absorb(chart_df, idx)
        
        if absorb_occurred:
            if e_resp == "RELEASE":
                type_b_cases.append(e) if absorb_bar <= 3 else success_cases.append(e)
            else:
                type_a_cases.append(e)
        else:
            if e_resp == "RELEASE":
                type_c_cases.append(e)
            else:
                pass
    
    print(f"\nType A (Miss): {len(type_a_cases)}")
    print(f"Type B (Late): {len(type_b_cases)}")
    print(f"Type C (False): {len(type_c_cases)}")
    print(f"SUCCESS: {len(success_cases)}")
    
    print("\n" + "="*70)
    print("TYPE C RESOLUTION")
    print("="*70)
    
    c1_cases = []
    c2_cases = []
    c1_metrics = []
    c2_metrics = []
    
    for e in type_c_cases:
        idx = e['idx']
        metrics = calc_session_metrics(chart_df, idx)
        
        if metrics is None:
            continue
        
        classification = classify_type_c(metrics)
        
        if classification == "C1_SAFE_FALSE":
            c1_cases.append(e)
            c1_metrics.append(metrics)
        elif classification == "C2_SOFT_TERMINAL":
            c2_cases.append(e)
            c2_metrics.append(metrics)
    
    print(f"\nC1 (Safe False): {len(c1_cases)} ({100*len(c1_cases)/len(type_c_cases):.1f}%)")
    print(f"C2 (Soft Terminal): {len(c2_cases)} ({100*len(c2_cases)/len(type_c_cases):.1f}%)")
    
    print("\n" + "-"*50)
    print("C1 vs C2 COMPARISON")
    print("-"*50)
    
    if c1_metrics:
        c1_mae = np.mean([m['mae_atr'] for m in c1_metrics])
        c1_dd = np.mean([m['max_drawdown_atr'] for m in c1_metrics])
        c1_daa = np.mean([1 if m['daa_up_reached'] or m['daa_down_reached'] else 0 for m in c1_metrics])
        c1_vol = np.mean([m['volatility_bursts'] for m in c1_metrics])
        
        print(f"\nC1 (Safe False) N={len(c1_cases)}:")
        print(f"  Mean MAE/ATR: {c1_mae:.2f}")
        print(f"  Mean Drawdown/ATR: {c1_dd:.2f}")
        print(f"  DAA Reach Rate: {c1_daa*100:.1f}%")
        print(f"  Volatility Bursts: {c1_vol:.2f}")
    
    if c2_metrics:
        c2_mae = np.mean([m['mae_atr'] for m in c2_metrics])
        c2_dd = np.mean([m['max_drawdown_atr'] for m in c2_metrics])
        c2_daa = np.mean([1 if m['daa_up_reached'] or m['daa_down_reached'] else 0 for m in c2_metrics])
        c2_vol = np.mean([m['volatility_bursts'] for m in c2_metrics])
        
        print(f"\nC2 (Soft Terminal) N={len(c2_cases)}:")
        print(f"  Mean MAE/ATR: {c2_mae:.2f}")
        print(f"  Mean Drawdown/ATR: {c2_dd:.2f}")
        print(f"  DAA Reach Rate: {c2_daa*100:.1f}%")
        print(f"  Volatility Bursts: {c2_vol:.2f}")
    
    print("\n" + "-"*50)
    print("INTERPRETATION")
    print("-"*50)
    
    if c2_metrics and c1_metrics:
        c2_ratio = len(c2_cases) / len(type_c_cases) * 100
        
        if c2_ratio > 50:
            print(f"\n⚠️  Type C의 {c2_ratio:.0f}%가 Soft Terminal")
            print("   → E_RESP 경고가 대부분 의미 있음")
            print("   → Absorb 정의가 너무 '좁았을' 가능성")
            print("   → EXIT 정책은 정당화됨")
        else:
            print(f"\n✅ Type C의 {100-c2_ratio:.0f}%가 Safe False")
            print("   → E_RESP 센서가 실제로 보수적")
            print("   → 거짓 경보 필터링 필요")
    
    print("\n" + "-"*50)
    print("OPERATIONAL IMPLICATION")
    print("-"*50)
    
    if c2_metrics:
        effective_precision = (len(success_cases) + len(c2_cases)) / (len(success_cases) + len(type_c_cases)) * 100
        print(f"\nOriginal Precision: {len(success_cases)/(len(success_cases)+len(type_c_cases))*100:.1f}%")
        print(f"Adjusted Precision (C2 = true positive): {effective_precision:.1f}%")
        print(f"\n→ C2를 '유효 경고'로 보면 정밀도 {effective_precision:.0f}%로 상승")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'n_events': len(events),
        'type_c_total': len(type_c_cases),
        'c1_safe_false': len(c1_cases),
        'c2_soft_terminal': len(c2_cases),
        'c1_ratio': len(c1_cases) / len(type_c_cases) if type_c_cases else 0,
        'c2_ratio': len(c2_cases) / len(type_c_cases) if type_c_cases else 0,
        'c1_avg_mae_atr': np.mean([m['mae_atr'] for m in c1_metrics]) if c1_metrics else 0,
        'c2_avg_mae_atr': np.mean([m['mae_atr'] for m in c2_metrics]) if c2_metrics else 0
    }
    
    with open('v7-grammar-system/results/exp_typec_resolution_01.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: exp_typec_resolution_01.json")

if __name__ == "__main__":
    run()
