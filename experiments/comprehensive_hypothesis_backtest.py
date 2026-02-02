"""
Comprehensive Hypothesis Backtest
All V7 Grammar + OPA hypotheses tested on real NQ data

Hypotheses tested:
H1: 배율 단독 (ratio alone)
H2: 배율 + 채널% (ratio + channel)
H3: STATE persistence (θ states)
H4: STB ignition role
H5: Impulse Warning (IW)
H6: Boundary-Aware Impulse
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

DATA_PATH = "data/nq1_full_combined.csv"
RESULTS_PATH = "v7-grammar-system/experiments/comprehensive_backtest_results.json"

TP_POINTS = 20
SL_POINTS = 15
CHANNEL_PERIOD = 20
STATE_LOCK_BARS = 3


@dataclass
class Bar:
    idx: int
    time: str
    open: float
    high: float
    low: float
    close: float
    ratio: float = 0.0
    channel_pct: float = 50.0
    delta: float = 0.0
    state: str = "NEUTRAL"
    state_age: int = 0
    stb_long: bool = False
    stb_short: bool = False
    boundary_sensitivity: float = 0.0
    delta_q90: float = 0.0


@dataclass
class Trade:
    entry_idx: int
    direction: str
    entry_price: float
    tp: float
    sl: float
    exit_idx: Optional[int] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    exit_reason: str = ""
    impulse_warning: bool = False
    hypothesis: str = ""


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]
    return df


def calculate_ratio(high: float, low: float, close: float) -> float:
    if high == low:
        return 1.0
    buyer = close - low
    seller = high - close
    if seller == 0:
        return 10.0
    return buyer / seller


def calculate_channel_pct(close: float, period_high: float, period_low: float) -> float:
    if period_high == period_low:
        return 50.0
    return (close - period_low) / (period_high - period_low) * 100


def prepare_bars(df: pd.DataFrame) -> List[Bar]:
    bars = []
    deltas = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        bar = Bar(
            idx=i,
            time=str(row.get('time', '')),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close'])
        )
        
        bar.ratio = calculate_ratio(bar.high, bar.low, bar.close)
        bar.delta = bar.close - bar.open
        deltas.append(abs(bar.delta))
        
        if i >= CHANNEL_PERIOD:
            period_highs = [bars[j].high for j in range(i - CHANNEL_PERIOD, i)]
            period_lows = [bars[j].low for j in range(i - CHANNEL_PERIOD, i)]
            bar.channel_pct = calculate_channel_pct(
                bar.close,
                max(period_highs),
                min(period_lows)
            )
        
        if i > 0:
            prev = bars[-1]
            if bar.ratio > 1.5 and bar.channel_pct > 80:
                bar.state = "OVERBOUGHT"
            elif bar.ratio < 0.7 and bar.channel_pct < 20:
                bar.state = "OVERSOLD"
            elif bar.ratio > 1.3:
                bar.state = "THETA_1"
            elif bar.ratio < 0.77:
                bar.state = "THETA_2"
            else:
                bar.state = "NEUTRAL"
            
            if bar.state == prev.state:
                bar.state_age = prev.state_age + 1
            else:
                bar.state_age = 1
        
        bar.stb_long = bar.ratio < 0.7 and bar.channel_pct < 30
        bar.stb_short = bar.ratio > 1.5 and bar.channel_pct > 70
        
        if len(deltas) >= 100:
            bar.delta_q90 = np.percentile(deltas[-100:], 90)
        else:
            bar.delta_q90 = np.percentile(deltas, 90) if deltas else 10.0
        
        state_sens = 1.0 if bar.state_age <= STATE_LOCK_BARS else 0.0
        stb_margin = abs(bar.ratio - 1.0) * 5
        stb_sens = 1.0 - min(max(stb_margin / 5.0, 0), 1)
        bar.boundary_sensitivity = 0.5 * state_sens + 0.5 * stb_sens
        
        bars.append(bar)
    
    return bars


def simulate_trade(bars: List[Bar], entry_idx: int, direction: str, 
                   entry_price: float, hypothesis: str,
                   use_iw: bool = False) -> Trade:
    trade = Trade(
        entry_idx=entry_idx,
        direction=direction,
        entry_price=entry_price,
        tp=entry_price + TP_POINTS if direction == "long" else entry_price - TP_POINTS,
        sl=entry_price - SL_POINTS if direction == "long" else entry_price + SL_POINTS,
        hypothesis=hypothesis
    )
    
    for i in range(entry_idx + 1, min(entry_idx + 50, len(bars))):
        bar = bars[i]
        
        if i == entry_idx + 1 and use_iw:
            if abs(bar.delta) > bar.delta_q90 and bar.boundary_sensitivity >= 0.6:
                trade.impulse_warning = True
                if direction == "long":
                    trade.sl = entry_price - SL_POINTS * 0.7
                else:
                    trade.sl = entry_price + SL_POINTS * 0.7
        
        if direction == "long":
            if bar.high >= trade.tp:
                trade.exit_idx = i
                trade.exit_price = trade.tp
                trade.pnl = TP_POINTS
                trade.exit_reason = "TP"
                break
            elif bar.low <= trade.sl:
                trade.exit_idx = i
                trade.exit_price = trade.sl
                trade.pnl = trade.sl - entry_price
                trade.exit_reason = "SL"
                break
        else:
            if bar.low <= trade.tp:
                trade.exit_idx = i
                trade.exit_price = trade.tp
                trade.pnl = TP_POINTS
                trade.exit_reason = "TP"
                break
            elif bar.high >= trade.sl:
                trade.exit_idx = i
                trade.exit_price = trade.sl
                trade.pnl = entry_price - trade.sl
                trade.exit_reason = "SL"
                break
    
    if trade.exit_idx is None:
        trade.exit_idx = min(entry_idx + 49, len(bars) - 1)
        trade.exit_price = bars[trade.exit_idx].close
        trade.pnl = (trade.exit_price - entry_price) if direction == "long" else (entry_price - trade.exit_price)
        trade.exit_reason = "TIMEOUT"
    
    return trade


def test_h1_ratio_only(bars: List[Bar]) -> List[Trade]:
    """H1: 배율 단독"""
    trades = []
    last_trade_idx = -20
    
    for i in range(CHANNEL_PERIOD, len(bars) - 50):
        if i - last_trade_idx < 10:
            continue
        bar = bars[i]
        
        if bar.ratio > 1.5:
            trade = simulate_trade(bars, i, "short", bar.close, "H1_RATIO_SHORT")
            trades.append(trade)
            last_trade_idx = i
        elif bar.ratio < 0.7:
            trade = simulate_trade(bars, i, "long", bar.close, "H1_RATIO_LONG")
            trades.append(trade)
            last_trade_idx = i
    
    return trades


def test_h2_ratio_channel(bars: List[Bar]) -> List[Trade]:
    """H2: 배율 + 채널%"""
    trades = []
    last_trade_idx = -20
    
    for i in range(CHANNEL_PERIOD, len(bars) - 50):
        if i - last_trade_idx < 10:
            continue
        bar = bars[i]
        
        if bar.ratio > 1.5 and bar.channel_pct > 80:
            trade = simulate_trade(bars, i, "short", bar.close, "H2_RATIO_CHANNEL_SHORT")
            trades.append(trade)
            last_trade_idx = i
        elif bar.ratio < 0.7 and bar.channel_pct < 20:
            trade = simulate_trade(bars, i, "long", bar.close, "H2_RATIO_CHANNEL_LONG")
            trades.append(trade)
            last_trade_idx = i
    
    return trades


def test_h3_state_persistence(bars: List[Bar]) -> List[Trade]:
    """H3: STATE persistence (θ lock 후 진입)"""
    trades = []
    last_trade_idx = -20
    
    for i in range(CHANNEL_PERIOD, len(bars) - 50):
        if i - last_trade_idx < 10:
            continue
        bar = bars[i]
        
        if bar.state == "OVERBOUGHT" and bar.state_age >= STATE_LOCK_BARS:
            trade = simulate_trade(bars, i, "short", bar.close, "H3_STATE_SHORT")
            trades.append(trade)
            last_trade_idx = i
        elif bar.state == "OVERSOLD" and bar.state_age >= STATE_LOCK_BARS:
            trade = simulate_trade(bars, i, "long", bar.close, "H3_STATE_LONG")
            trades.append(trade)
            last_trade_idx = i
    
    return trades


def test_h4_stb_ignition(bars: List[Bar]) -> List[Trade]:
    """H4: STB ignition (STB 조건 충족 시 진입)"""
    trades = []
    last_trade_idx = -20
    
    for i in range(CHANNEL_PERIOD, len(bars) - 50):
        if i - last_trade_idx < 10:
            continue
        bar = bars[i]
        
        if bar.stb_short:
            trade = simulate_trade(bars, i, "short", bar.close, "H4_STB_SHORT")
            trades.append(trade)
            last_trade_idx = i
        elif bar.stb_long:
            trade = simulate_trade(bars, i, "long", bar.close, "H4_STB_LONG")
            trades.append(trade)
            last_trade_idx = i
    
    return trades


def test_h5_impulse_warning(bars: List[Bar]) -> Tuple[List[Trade], List[Trade]]:
    """H5: Impulse Warning (baseline vs IW defense)"""
    baseline_trades = []
    iw_trades = []
    last_trade_idx = -20
    
    for i in range(CHANNEL_PERIOD, len(bars) - 50):
        if i - last_trade_idx < 10:
            continue
        bar = bars[i]
        
        if bar.stb_short:
            baseline = simulate_trade(bars, i, "short", bar.close, "H5_BASELINE_SHORT", use_iw=False)
            iw = simulate_trade(bars, i, "short", bar.close, "H5_IW_SHORT", use_iw=True)
            baseline_trades.append(baseline)
            iw_trades.append(iw)
            last_trade_idx = i
        elif bar.stb_long:
            baseline = simulate_trade(bars, i, "long", bar.close, "H5_BASELINE_LONG", use_iw=False)
            iw = simulate_trade(bars, i, "long", bar.close, "H5_IW_LONG", use_iw=True)
            baseline_trades.append(baseline)
            iw_trades.append(iw)
            last_trade_idx = i
    
    return baseline_trades, iw_trades


def test_h6_boundary_aware(bars: List[Bar]) -> List[Trade]:
    """H6: Boundary-Aware (high sensitivity only)"""
    trades = []
    last_trade_idx = -20
    
    for i in range(CHANNEL_PERIOD, len(bars) - 50):
        if i - last_trade_idx < 10:
            continue
        bar = bars[i]
        
        if bar.boundary_sensitivity < 0.6:
            continue
        
        if bar.stb_short:
            trade = simulate_trade(bars, i, "short", bar.close, "H6_BOUNDARY_SHORT", use_iw=True)
            trades.append(trade)
            last_trade_idx = i
        elif bar.stb_long:
            trade = simulate_trade(bars, i, "long", bar.close, "H6_BOUNDARY_LONG", use_iw=True)
            trades.append(trade)
            last_trade_idx = i
    
    return trades


def calculate_metrics(trades: List[Trade]) -> Dict:
    if not trades:
        return {"count": 0, "win_rate": 0, "avg_pnl": 0, "total_pnl": 0}
    
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    
    return {
        "count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_pnl": round(sum(t.pnl for t in trades) / len(trades), 2),
        "total_pnl": round(sum(t.pnl for t in trades), 2),
        "avg_loss": round(sum(t.pnl for t in losses) / len(losses), 2) if losses else 0,
        "worst_loss": round(min(t.pnl for t in trades), 2),
        "best_win": round(max(t.pnl for t in trades), 2),
        "iw_triggered": sum(1 for t in trades if t.impulse_warning),
        "tp_exits": sum(1 for t in trades if t.exit_reason == "TP"),
        "sl_exits": sum(1 for t in trades if t.exit_reason == "SL"),
    }


def run_all_hypotheses():
    print("=" * 70)
    print("COMPREHENSIVE HYPOTHESIS BACKTEST")
    print("=" * 70)
    
    print("\nLoading data...")
    df = load_data()
    print(f"Loaded {len(df)} bars")
    
    print("\nPreparing bars with indicators...")
    bars = prepare_bars(df)
    print(f"Prepared {len(bars)} bars")
    
    results = {}
    
    print("\n" + "-" * 50)
    print("H1: 배율 단독 (Ratio Only)")
    print("-" * 50)
    h1_trades = test_h1_ratio_only(bars)
    results["H1_RATIO_ONLY"] = calculate_metrics(h1_trades)
    print(f"  Trades: {results['H1_RATIO_ONLY']['count']}")
    print(f"  Win Rate: {results['H1_RATIO_ONLY']['win_rate']}%")
    print(f"  Avg PnL: {results['H1_RATIO_ONLY']['avg_pnl']}")
    
    print("\n" + "-" * 50)
    print("H2: 배율 + 채널% (Ratio + Channel)")
    print("-" * 50)
    h2_trades = test_h2_ratio_channel(bars)
    results["H2_RATIO_CHANNEL"] = calculate_metrics(h2_trades)
    print(f"  Trades: {results['H2_RATIO_CHANNEL']['count']}")
    print(f"  Win Rate: {results['H2_RATIO_CHANNEL']['win_rate']}%")
    print(f"  Avg PnL: {results['H2_RATIO_CHANNEL']['avg_pnl']}")
    
    print("\n" + "-" * 50)
    print("H3: STATE Persistence (θ Lock)")
    print("-" * 50)
    h3_trades = test_h3_state_persistence(bars)
    results["H3_STATE_PERSISTENCE"] = calculate_metrics(h3_trades)
    print(f"  Trades: {results['H3_STATE_PERSISTENCE']['count']}")
    print(f"  Win Rate: {results['H3_STATE_PERSISTENCE']['win_rate']}%")
    print(f"  Avg PnL: {results['H3_STATE_PERSISTENCE']['avg_pnl']}")
    
    print("\n" + "-" * 50)
    print("H4: STB Ignition")
    print("-" * 50)
    h4_trades = test_h4_stb_ignition(bars)
    results["H4_STB_IGNITION"] = calculate_metrics(h4_trades)
    print(f"  Trades: {results['H4_STB_IGNITION']['count']}")
    print(f"  Win Rate: {results['H4_STB_IGNITION']['win_rate']}%")
    print(f"  Avg PnL: {results['H4_STB_IGNITION']['avg_pnl']}")
    
    print("\n" + "-" * 50)
    print("H5: Impulse Warning (Baseline vs Defense)")
    print("-" * 50)
    h5_baseline, h5_iw = test_h5_impulse_warning(bars)
    results["H5_BASELINE"] = calculate_metrics(h5_baseline)
    results["H5_IW_DEFENSE"] = calculate_metrics(h5_iw)
    print(f"  Baseline:")
    print(f"    Trades: {results['H5_BASELINE']['count']}")
    print(f"    Win Rate: {results['H5_BASELINE']['win_rate']}%")
    print(f"    Avg Loss: {results['H5_BASELINE']['avg_loss']}")
    print(f"  With IW Defense:")
    print(f"    Trades: {results['H5_IW_DEFENSE']['count']}")
    print(f"    Win Rate: {results['H5_IW_DEFENSE']['win_rate']}%")
    print(f"    Avg Loss: {results['H5_IW_DEFENSE']['avg_loss']}")
    print(f"    IW Triggered: {results['H5_IW_DEFENSE']['iw_triggered']}")
    
    print("\n" + "-" * 50)
    print("H6: Boundary-Aware Impulse")
    print("-" * 50)
    h6_trades = test_h6_boundary_aware(bars)
    results["H6_BOUNDARY_AWARE"] = calculate_metrics(h6_trades)
    print(f"  Trades: {results['H6_BOUNDARY_AWARE']['count']}")
    print(f"  Win Rate: {results['H6_BOUNDARY_AWARE']['win_rate']}%")
    print(f"  Avg PnL: {results['H6_BOUNDARY_AWARE']['avg_pnl']}")
    print(f"  IW Triggered: {results['H6_BOUNDARY_AWARE']['iw_triggered']}")
    
    print("\n" + "=" * 70)
    print("HYPOTHESIS RANKING (by Win Rate)")
    print("=" * 70)
    sorted_results = sorted(results.items(), key=lambda x: x[1].get('win_rate', 0), reverse=True)
    for i, (name, metrics) in enumerate(sorted_results, 1):
        if metrics['count'] > 0:
            print(f"{i}. {name}: {metrics['win_rate']}% ({metrics['count']} trades, avg={metrics['avg_pnl']})")
    
    print("\n" + "=" * 70)
    print("IMPULSE WARNING EFFECT ANALYSIS")
    print("=" * 70)
    if results['H5_BASELINE']['avg_loss'] != 0:
        loss_reduction = results['H5_IW_DEFENSE']['avg_loss'] - results['H5_BASELINE']['avg_loss']
        loss_reduction_pct = (loss_reduction / abs(results['H5_BASELINE']['avg_loss'])) * 100
        print(f"  Baseline Avg Loss: {results['H5_BASELINE']['avg_loss']}")
        print(f"  IW Defense Avg Loss: {results['H5_IW_DEFENSE']['avg_loss']}")
        print(f"  Loss Reduction: {loss_reduction:.2f} ({loss_reduction_pct:.1f}%)")
        
        if loss_reduction > 0:
            print("\n  CONCLUSION: Impulse Warning REDUCED loss severity!")
            results["IW_CONCLUSION"] = "SUCCESS: Loss severity reduced"
        else:
            print("\n  CONCLUSION: Impulse Warning had no effect or worsened losses")
            results["IW_CONCLUSION"] = "LATENCY_CONSTRAINT: 1-bar lag insufficient"
    
    results["metadata"] = {
        "data_file": DATA_PATH,
        "bars_count": len(bars),
        "test_date": datetime.now().isoformat(),
        "tp_points": TP_POINTS,
        "sl_points": SL_POINTS
    }
    
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to {RESULTS_PATH}")
    
    return results


if __name__ == "__main__":
    run_all_hypotheses()
