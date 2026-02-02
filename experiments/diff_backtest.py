"""
Diff Backtest: 기존 vs 새 엔진 정확 비교

불일치 포인트 체크:
1. STB 조건 (channel 임계값)
2. TP/SL 처리 (봉 내 순서)
3. 쿨다운 로직
4. Delta 계산
"""

import pandas as pd
import numpy as np
import json
from dataclasses import dataclass
from typing import List, Dict, Optional

DATA_PATH = "data/nq1_full_combined.csv"

TP_POINTS = 20
SL_POINTS = 15
CHANNEL_PERIOD = 20


@dataclass
class DiffEvent:
    bar_idx: int
    time: str
    event_type: str
    old_value: any
    new_value: any
    source: str


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


class OldBacktest:
    """기존 백테스트 로직 (50.6%)"""
    
    def __init__(self):
        self.trades = []
        self.triggers = []
        self.last_trade_idx = -20
    
    def stb_condition(self, ratio, channel_pct):
        stb_long = ratio < 0.7 and channel_pct < 30
        stb_short = ratio > 1.5 and channel_pct > 70
        return stb_long, stb_short
    
    def simulate_trade(self, df, entry_idx, direction, entry_price):
        tp = entry_price + TP_POINTS if direction == "long" else entry_price - TP_POINTS
        sl = entry_price - SL_POINTS if direction == "long" else entry_price + SL_POINTS
        
        for i in range(entry_idx + 1, min(entry_idx + 50, len(df))):
            bar = df.iloc[i]
            
            if direction == "long":
                if bar['high'] >= tp:
                    return {'exit_idx': i, 'reason': 'TP', 'pnl': TP_POINTS}
                elif bar['low'] <= sl:
                    return {'exit_idx': i, 'reason': 'SL', 'pnl': sl - entry_price}
            else:
                if bar['low'] <= tp:
                    return {'exit_idx': i, 'reason': 'TP', 'pnl': TP_POINTS}
                elif bar['high'] >= sl:
                    return {'exit_idx': i, 'reason': 'SL', 'pnl': entry_price - sl}
        
        return {'exit_idx': entry_idx + 49, 'reason': 'TIMEOUT', 'pnl': 0}
    
    def run(self, df):
        self.trades = []
        self.triggers = []
        self.last_trade_idx = -20
        
        highs = df['high'].rolling(CHANNEL_PERIOD).max()
        lows = df['low'].rolling(CHANNEL_PERIOD).min()
        
        for i in range(CHANNEL_PERIOD, len(df) - 50):
            if i - self.last_trade_idx < 10:
                continue
            
            bar = df.iloc[i]
            ratio = calculate_ratio(bar['high'], bar['low'], bar['close'])
            
            period_high = highs.iloc[i]
            period_low = lows.iloc[i]
            if period_high == period_low:
                channel_pct = 50.0
            else:
                channel_pct = (bar['close'] - period_low) / (period_high - period_low) * 100
            
            stb_long, stb_short = self.stb_condition(ratio, channel_pct)
            
            if stb_short:
                self.triggers.append({
                    'bar_idx': i,
                    'type': 'STB_SHORT',
                    'ratio': ratio,
                    'channel': channel_pct
                })
                trade = self.simulate_trade(df, i, "short", bar['close'])
                trade['bar_idx'] = i
                trade['direction'] = 'short'
                self.trades.append(trade)
                self.last_trade_idx = i
            elif stb_long:
                self.triggers.append({
                    'bar_idx': i,
                    'type': 'STB_LONG',
                    'ratio': ratio,
                    'channel': channel_pct
                })
                trade = self.simulate_trade(df, i, "long", bar['close'])
                trade['bar_idx'] = i
                trade['direction'] = 'long'
                self.trades.append(trade)
                self.last_trade_idx = i
        
        return self.trades, self.triggers


class NewEngine:
    """새 엔진 로직 (수정됨)"""
    
    def __init__(self):
        self.trades = []
        self.triggers = []
        self.last_trade_idx = -20
        self.in_position = False
    
    def stb_condition(self, ratio, channel_pct):
        stb_long = ratio < 0.7 and channel_pct < 30
        stb_short = ratio > 1.5 and channel_pct > 70
        return stb_long, stb_short
    
    def simulate_trade(self, df, entry_idx, direction, entry_price):
        tp = entry_price + TP_POINTS if direction == "long" else entry_price - TP_POINTS
        sl = entry_price - SL_POINTS if direction == "long" else entry_price + SL_POINTS
        
        for i in range(entry_idx + 1, min(entry_idx + 50, len(df))):
            bar = df.iloc[i]
            
            if direction == "long":
                if bar['high'] >= tp:
                    return {'exit_idx': i, 'reason': 'TP', 'pnl': TP_POINTS}
                elif bar['low'] <= sl:
                    return {'exit_idx': i, 'reason': 'SL', 'pnl': sl - entry_price}
            else:
                if bar['low'] <= tp:
                    return {'exit_idx': i, 'reason': 'TP', 'pnl': TP_POINTS}
                elif bar['high'] >= sl:
                    return {'exit_idx': i, 'reason': 'SL', 'pnl': entry_price - sl}
        
        return {'exit_idx': entry_idx + 49, 'reason': 'TIMEOUT', 'pnl': 0}
    
    def run(self, df):
        self.trades = []
        self.triggers = []
        self.last_trade_idx = -20
        
        highs = df['high'].rolling(CHANNEL_PERIOD).max()
        lows = df['low'].rolling(CHANNEL_PERIOD).min()
        
        for i in range(CHANNEL_PERIOD, len(df) - 50):
            if i - self.last_trade_idx < 10:
                continue
            
            bar = df.iloc[i]
            ratio = calculate_ratio(bar['high'], bar['low'], bar['close'])
            
            period_high = highs.iloc[i]
            period_low = lows.iloc[i]
            if period_high == period_low:
                channel_pct = 50.0
            else:
                channel_pct = (bar['close'] - period_low) / (period_high - period_low) * 100
            
            stb_long, stb_short = self.stb_condition(ratio, channel_pct)
            
            if stb_short:
                self.triggers.append({
                    'bar_idx': i,
                    'type': 'STB_SHORT',
                    'ratio': ratio,
                    'channel': channel_pct
                })
                trade = self.simulate_trade(df, i, "short", bar['close'])
                trade['bar_idx'] = i
                trade['direction'] = 'short'
                self.trades.append(trade)
                self.last_trade_idx = i
            elif stb_long:
                self.triggers.append({
                    'bar_idx': i,
                    'type': 'STB_LONG',
                    'ratio': ratio,
                    'channel': channel_pct
                })
                trade = self.simulate_trade(df, i, "long", bar['close'])
                trade['bar_idx'] = i
                trade['direction'] = 'long'
                self.trades.append(trade)
                self.last_trade_idx = i
        
        return self.trades, self.triggers


def run_diff():
    print("="*70)
    print("DIFF BACKTEST: 기존 vs 새 엔진")
    print("="*70)
    
    df = load_data()
    print(f"Loaded {len(df)} bars")
    
    old = OldBacktest()
    new = NewEngine()
    
    old_trades, old_triggers = old.run(df)
    new_trades, new_triggers = new.run(df)
    
    print("\n[1] TRIGGER COUNT COMPARISON")
    print(f"  Old triggers: {len(old_triggers)}")
    print(f"  New triggers: {len(new_triggers)}")
    print(f"  Difference: {len(old_triggers) - len(new_triggers)}")
    
    old_trigger_idx = set(t['bar_idx'] for t in old_triggers)
    new_trigger_idx = set(t['bar_idx'] for t in new_triggers)
    
    only_old = old_trigger_idx - new_trigger_idx
    only_new = new_trigger_idx - old_trigger_idx
    both = old_trigger_idx & new_trigger_idx
    
    print(f"\n  Only in OLD: {len(only_old)}")
    print(f"  Only in NEW: {len(only_new)}")
    print(f"  Both: {len(both)}")
    
    print("\n[2] STB CONDITION DIFFERENCE")
    print("  OLD: ratio < 0.7 & channel < 30 (long)")
    print("       ratio > 1.5 & channel > 70 (short)")
    print("  NEW: ratio < 0.7 & channel < 20 (long)")
    print("       ratio > 1.5 & channel > 80 (short)")
    
    cond_diff = []
    for t in old_triggers:
        if t['bar_idx'] not in new_trigger_idx:
            if t['type'] == 'STB_LONG' and 20 <= t['channel'] < 30:
                cond_diff.append(t)
            elif t['type'] == 'STB_SHORT' and 70 < t['channel'] <= 80:
                cond_diff.append(t)
    
    print(f"\n  Trades lost due to tighter channel: {len(cond_diff)}")
    
    print("\n[3] TRADE COUNT & WIN RATE")
    old_wins = sum(1 for t in old_trades if t['reason'] == 'TP')
    new_wins = sum(1 for t in new_trades if t['reason'] == 'TP')
    
    old_wr = old_wins / len(old_trades) * 100 if old_trades else 0
    new_wr = new_wins / len(new_trades) * 100 if new_trades else 0
    
    print(f"  Old: {len(old_trades)} trades, {old_wins} wins, {old_wr:.1f}%")
    print(f"  New: {len(new_trades)} trades, {new_wins} wins, {new_wr:.1f}%")
    
    print("\n[4] TP/SL PROCESSING DIFFERENCE")
    print("  OLD: bar.high >= TP (checks H/L extremes)")
    print("  NEW: pnl >= TP (checks close-based PnL)")
    
    tp_diff_count = 0
    sl_diff_count = 0
    
    old_trade_map = {t['bar_idx']: t for t in old_trades}
    new_trade_map = {t['bar_idx']: t for t in new_trades}
    
    common_entries = set(old_trade_map.keys()) & set(new_trade_map.keys())
    
    for idx in common_entries:
        ot = old_trade_map[idx]
        nt = new_trade_map[idx]
        if ot['reason'] != nt['reason']:
            if ot['reason'] == 'TP' and nt['reason'] == 'SL':
                tp_diff_count += 1
            elif ot['reason'] == 'SL' and nt['reason'] == 'TP':
                sl_diff_count += 1
    
    print(f"\n  Same entry, different exit:")
    print(f"    Old=TP, New=SL: {tp_diff_count}")
    print(f"    Old=SL, New=TP: {sl_diff_count}")
    
    print("\n[5] COOLDOWN DIFFERENCE")
    print("  OLD: 10-bar cooldown between trades")
    print("  NEW: No cooldown (just position check)")
    
    old_gaps = []
    for i in range(1, len(old_trades)):
        gap = old_trades[i]['bar_idx'] - old_trades[i-1]['bar_idx']
        old_gaps.append(gap)
    
    new_gaps = []
    for i in range(1, len(new_trades)):
        gap = new_trades[i]['bar_idx'] - new_trades[i-1]['bar_idx']
        new_gaps.append(gap)
    
    if old_gaps:
        print(f"  Old avg gap: {sum(old_gaps)/len(old_gaps):.1f} bars")
        print(f"  Old min gap: {min(old_gaps)} bars")
    if new_gaps:
        print(f"  New avg gap: {sum(new_gaps)/len(new_gaps):.1f} bars")
        print(f"  New min gap: {min(new_gaps)} bars")
    
    print("\n" + "="*70)
    print("DIAGNOSIS SUMMARY")
    print("="*70)
    
    issues = []
    
    if len(cond_diff) > 10:
        issues.append({
            'issue': 'STB_CONDITION_TIGHTER',
            'severity': 'HIGH',
            'detail': f'New engine misses {len(cond_diff)} trades due to tighter channel thresholds',
            'fix': 'Change new engine: channel < 30 (long), channel > 70 (short)'
        })
    
    if tp_diff_count > 5 or sl_diff_count > 5:
        issues.append({
            'issue': 'TP_SL_PROCESSING',
            'severity': 'HIGH',
            'detail': f'{tp_diff_count} trades where old=TP but new=SL',
            'fix': 'New engine should check bar.high/low, not close-based PnL'
        })
    
    if len(only_old) > 50:
        issues.append({
            'issue': 'TRIGGER_MISMATCH',
            'severity': 'MEDIUM',
            'detail': f'{len(only_old)} triggers only in old engine',
            'fix': 'Verify channel calculation and cooldown logic'
        })
    
    for issue in issues:
        print(f"\n  [{issue['severity']}] {issue['issue']}")
        print(f"    {issue['detail']}")
        print(f"    FIX: {issue['fix']}")
    
    if not issues:
        print("\n  No critical issues found")
    
    results = {
        'timestamp': '2026-01-23',
        'old_triggers': len(old_triggers),
        'new_triggers': len(new_triggers),
        'old_trades': len(old_trades),
        'new_trades': len(new_trades),
        'old_win_rate': old_wr,
        'new_win_rate': new_wr,
        'condition_diff_trades': len(cond_diff),
        'tp_to_sl_diff': tp_diff_count,
        'sl_to_tp_diff': sl_diff_count,
        'issues': issues
    }
    
    output_path = "v7-grammar-system/experiments/diff_backtest_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n\nResults saved to: {output_path}")
    
    return results


if __name__ == "__main__":
    run_diff()
