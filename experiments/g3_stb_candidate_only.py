"""
G3: STB → candidate-only 구조 테스트 (EXP-A)

설계:
- STB 발생 → 실행 X, 기록만
- OPA 충족 시만 실행
- 비교: 전량 실행 vs 조건부 실행

목표:
- 50.6% → 70~80%로 갈 수 있는지 확인
- 실행률/품질 트레이드오프 측정

G1 발견 적용:
- BUYER: 즉시 실행 가능 (95.1% 일관성)
- SELLER: 추가 필터 필요 (69.5% 일관성)
"""

import pandas as pd
import numpy as np
import json
from typing import List, Dict

DATA_PATH = "data/nq1_full_combined.csv"

CHANNEL_PERIOD = 20
PRE_TRANSITION_WINDOW = 5
TP_POINTS = 20
SL_POINTS = 15


def load_data():
    df = pd.read_csv(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]
    return df


def calculate_ratio(high, low, close):
    if high == low:
        return 1.0
    buyer = close - low
    seller = high - close
    if seller == 0:
        return 10.0
    return buyer / seller


def prepare_data(df):
    n = len(df)
    
    highs = df['high'].rolling(CHANNEL_PERIOD).max()
    lows = df['low'].rolling(CHANNEL_PERIOD).min()
    
    ratios = []
    channels = []
    
    for i in range(n):
        bar = df.iloc[i]
        
        ratio = calculate_ratio(bar['high'], bar['low'], bar['close'])
        ratios.append(ratio)
        
        period_high = highs.iloc[i]
        period_low = lows.iloc[i]
        if pd.isna(period_high) or period_high == period_low:
            channel = 50.0
        else:
            channel = (bar['close'] - period_low) / (period_high - period_low) * 100
        channels.append(channel)
    
    df['ratio'] = ratios
    df['channel'] = channels
    
    return df


def is_stb_long(ratio, channel):
    return ratio < 0.7 and channel < 30


def is_stb_short(ratio, channel):
    return ratio > 1.5 and channel > 70


def is_opa_transition(df, idx, direction):
    """
    OPA 전환 감지: pre-transition 윈도우에서 Δ 일관성 확인
    
    BUYER: Δ < 0 (하락 후 반등)
    SELLER: Δ > 0 (상승 후 반전)
    """
    if idx < PRE_TRANSITION_WINDOW + 1:
        return False
    
    pre_deltas = [df.iloc[j]['ratio'] for j in range(idx - PRE_TRANSITION_WINDOW, idx)]
    avg_delta = sum(pre_deltas) / len(pre_deltas)
    current_delta = df.iloc[idx]['ratio']
    delta_change = current_delta - avg_delta
    
    if direction == "long":
        return delta_change < -0.3
    else:
        return delta_change > 0.3


def is_strong_opa_transition(df, idx, direction):
    """
    강화된 OPA: 더 엄격한 조건
    
    BUYER: Δ < -0.5 (명확한 하락)
    SELLER: Δ > 0.5 + 채널 확인
    """
    if idx < PRE_TRANSITION_WINDOW + 1:
        return False
    
    pre_deltas = [df.iloc[j]['ratio'] for j in range(idx - PRE_TRANSITION_WINDOW, idx)]
    avg_delta = sum(pre_deltas) / len(pre_deltas)
    current_delta = df.iloc[idx]['ratio']
    delta_change = current_delta - avg_delta
    
    channel = df.iloc[idx]['channel']
    
    if direction == "long":
        return delta_change < -0.5 and channel < 25
    else:
        return delta_change > 0.5 and channel > 75


def is_buyer_only(df, idx, direction):
    """
    G1 발견 적용: BUYER만 실행, SELLER 제외
    """
    if direction == "long":
        return is_opa_transition(df, idx, direction)
    else:
        return False


def simulate_trade(df, entry_idx, direction, entry_price):
    tp = entry_price + TP_POINTS if direction == "long" else entry_price - TP_POINTS
    sl = entry_price - SL_POINTS if direction == "long" else entry_price + SL_POINTS
    
    for i in range(entry_idx + 1, min(entry_idx + 50, len(df))):
        bar = df.iloc[i]
        
        if direction == "long":
            if bar['high'] >= tp:
                return {'pnl': TP_POINTS, 'result': 'WIN'}
            elif bar['low'] <= sl:
                return {'pnl': -SL_POINTS, 'result': 'LOSS'}
        else:
            if bar['low'] <= tp:
                return {'pnl': TP_POINTS, 'result': 'WIN'}
            elif bar['high'] >= sl:
                return {'pnl': -SL_POINTS, 'result': 'LOSS'}
    
    final = df.iloc[min(entry_idx + 49, len(df) - 1)]
    if direction == "long":
        pnl = final['close'] - entry_price
    else:
        pnl = entry_price - final['close']
    
    return {'pnl': pnl, 'result': 'WIN' if pnl > 0 else 'LOSS'}


def run_experiment():
    print("="*70)
    print("G3: STB → candidate-only 구조 테스트 (EXP-A)")
    print("="*70)
    
    df = load_data()
    df = prepare_data(df)
    print(f"Loaded {len(df)} bars")
    
    strategies = {
        'STB_ALL': {'filter': lambda df, idx, dir: True, 'trades': []},
        'STB_OPA': {'filter': is_opa_transition, 'trades': []},
        'STB_STRONG_OPA': {'filter': is_strong_opa_transition, 'trades': []},
        'STB_BUYER_ONLY': {'filter': is_buyer_only, 'trades': []},
    }
    
    stb_candidates = []
    last_trade_idx = -20
    
    for i in range(CHANNEL_PERIOD, len(df) - 50):
        bar = df.iloc[i]
        ratio = bar['ratio']
        channel = bar['channel']
        
        if i - last_trade_idx < 10:
            continue
        
        stb_long = is_stb_long(ratio, channel)
        stb_short = is_stb_short(ratio, channel)
        
        if stb_long or stb_short:
            direction = "long" if stb_long else "short"
            entry_price = bar['close']
            
            stb_candidates.append({
                'bar_idx': i,
                'direction': direction,
                'entry_price': entry_price
            })
            
            for name, strategy in strategies.items():
                if strategy['filter'](df, i, direction):
                    trade = simulate_trade(df, i, direction, entry_price)
                    strategy['trades'].append({
                        'bar_idx': i,
                        'direction': direction,
                        **trade
                    })
            
            last_trade_idx = i
    
    print(f"\nTotal STB candidates: {len(stb_candidates)}")
    
    print("\n" + "="*70)
    print("[RESULTS] 전략별 성과 비교")
    print("="*70)
    
    results = {}
    
    for name, strategy in strategies.items():
        trades = strategy['trades']
        if not trades:
            continue
        
        wins = sum(1 for t in trades if t['result'] == 'WIN')
        total_pnl = sum(t['pnl'] for t in trades)
        
        win_rate = wins / len(trades) * 100
        exec_rate = len(trades) / len(stb_candidates) * 100 if stb_candidates else 0
        avg_pnl = total_pnl / len(trades)
        
        long_trades = [t for t in trades if t['direction'] == 'long']
        short_trades = [t for t in trades if t['direction'] == 'short']
        
        long_wr = sum(1 for t in long_trades if t['result'] == 'WIN') / len(long_trades) * 100 if long_trades else 0
        short_wr = sum(1 for t in short_trades if t['result'] == 'WIN') / len(short_trades) * 100 if short_trades else 0
        
        print(f"\n  {name}:")
        print(f"    Trades: {len(trades)} (실행률: {exec_rate:.1f}%)")
        print(f"    Win Rate: {win_rate:.1f}%")
        print(f"    Avg PnL: {avg_pnl:.2f}")
        print(f"    LONG: {long_wr:.1f}% (n={len(long_trades)})")
        print(f"    SHORT: {short_wr:.1f}% (n={len(short_trades)})")
        
        results[name] = {
            'trades': len(trades),
            'execution_rate': round(exec_rate, 1),
            'win_rate': round(win_rate, 1),
            'avg_pnl': round(avg_pnl, 2),
            'long_wr': round(long_wr, 1),
            'short_wr': round(short_wr, 1),
            'long_n': len(long_trades),
            'short_n': len(short_trades)
        }
    
    print("\n" + "="*70)
    print("[ANALYSIS] 트레이드오프 분석")
    print("="*70)
    
    if 'STB_ALL' in results and 'STB_OPA' in results:
        all_wr = results['STB_ALL']['win_rate']
        opa_wr = results['STB_OPA']['win_rate']
        opa_exec = results['STB_OPA']['execution_rate']
        
        print(f"\n  STB_ALL → STB_OPA:")
        print(f"    승률: {all_wr:.1f}% → {opa_wr:.1f}% ({opa_wr - all_wr:+.1f}%)")
        print(f"    실행률: 100% → {opa_exec:.1f}%")
        print(f"    품질/빈도 트레이드오프: {(opa_wr - all_wr) / (100 - opa_exec) * 10:.2f}% per 10% execution drop")
    
    if 'STB_STRONG_OPA' in results:
        strong_wr = results['STB_STRONG_OPA']['win_rate']
        strong_exec = results['STB_STRONG_OPA']['execution_rate']
        
        print(f"\n  STB_STRONG_OPA:")
        print(f"    승률: {strong_wr:.1f}%")
        print(f"    실행률: {strong_exec:.1f}%")
    
    if 'STB_BUYER_ONLY' in results:
        buyer_wr = results['STB_BUYER_ONLY']['win_rate']
        buyer_exec = results['STB_BUYER_ONLY']['execution_rate']
        
        print(f"\n  STB_BUYER_ONLY (G1 발견 적용):")
        print(f"    승률: {buyer_wr:.1f}%")
        print(f"    실행률: {buyer_exec:.1f}%")
    
    print("\n" + "="*70)
    print("[CONCLUSION] 최적 구조 판정")
    print("="*70)
    
    best_strategy = max(results.items(), key=lambda x: x[1]['win_rate'])
    best_quality = max(results.items(), key=lambda x: x[1]['avg_pnl'])
    
    print(f"\n  최고 승률: {best_strategy[0]} ({best_strategy[1]['win_rate']}%)")
    print(f"  최고 품질: {best_quality[0]} (Avg PnL: {best_quality[1]['avg_pnl']})")
    
    target_70 = [k for k, v in results.items() if v['win_rate'] >= 70]
    target_80 = [k for k, v in results.items() if v['win_rate'] >= 80]
    
    print(f"\n  70%+ 달성: {target_70 if target_70 else 'None'}")
    print(f"  80%+ 달성: {target_80 if target_80 else 'None'}")
    
    output = {
        'timestamp': '2026-01-23',
        'total_stb_candidates': len(stb_candidates),
        'strategies': results,
        'best_win_rate': best_strategy[0],
        'best_avg_pnl': best_quality[0],
        'target_70_achieved': target_70,
        'target_80_achieved': target_80
    }
    
    output_path = "v7-grammar-system/experiments/g3_stb_candidate_results.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_experiment()
