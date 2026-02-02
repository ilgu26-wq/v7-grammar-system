"""
COMMIT-025: Impulse 0-Bar Experiment

COMMIT-024 showed that 1-bar IW is too late (0.3% effect).
This experiment tests 0-bar (entry moment) impulse detection.

Hypothesis:
If impulse is detected AT the entry bar (not +1),
risk clamp can prevent more damage.
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional

DATA_PATH = "data/nq1_full_combined.csv"
RESULTS_PATH = "v7-grammar-system/experiments/impulse_0bar_results.json"

TP_POINTS = 20
SL_POINTS = 15
CHANNEL_PERIOD = 20


@dataclass
class Bar:
    idx: int
    open: float
    high: float
    low: float
    close: float
    ratio: float = 0.0
    channel_pct: float = 50.0
    delta: float = 0.0
    delta_q90: float = 0.0
    stb_long: bool = False
    stb_short: bool = False


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
    impulse_0bar: bool = False
    variant: str = ""


def load_and_prepare() -> List[Bar]:
    df = pd.read_csv(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]
    
    bars = []
    deltas = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        bar = Bar(
            idx=i,
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close'])
        )
        
        if bar.high != bar.low:
            buyer = bar.close - bar.low
            seller = bar.high - bar.close
            bar.ratio = buyer / seller if seller > 0 else 10.0
        else:
            bar.ratio = 1.0
        
        bar.delta = bar.close - bar.open
        deltas.append(abs(bar.delta))
        
        if i >= CHANNEL_PERIOD:
            period_highs = [bars[j].high for j in range(i - CHANNEL_PERIOD, i)]
            period_lows = [bars[j].low for j in range(i - CHANNEL_PERIOD, i)]
            ph, pl = max(period_highs), min(period_lows)
            bar.channel_pct = (bar.close - pl) / (ph - pl) * 100 if ph != pl else 50.0
        
        if len(deltas) >= 100:
            bar.delta_q90 = np.percentile(deltas[-100:], 90)
        else:
            bar.delta_q90 = np.percentile(deltas, 90) if deltas else 10.0
        
        bar.stb_long = bar.ratio < 0.7 and bar.channel_pct < 30
        bar.stb_short = bar.ratio > 1.5 and bar.channel_pct > 70
        
        bars.append(bar)
    
    return bars


def is_0bar_impulse(bar: Bar) -> bool:
    """Check if entry bar itself has impulse characteristics"""
    return abs(bar.delta) > bar.delta_q90


def simulate_trade(bars: List[Bar], entry_idx: int, direction: str,
                   variant: str) -> Trade:
    entry_bar = bars[entry_idx]
    entry_price = entry_bar.close
    
    trade = Trade(
        entry_idx=entry_idx,
        direction=direction,
        entry_price=entry_price,
        tp=entry_price + TP_POINTS if direction == "long" else entry_price - TP_POINTS,
        sl=entry_price - SL_POINTS if direction == "long" else entry_price + SL_POINTS,
        variant=variant
    )
    
    if is_0bar_impulse(entry_bar):
        trade.impulse_0bar = True
        
        if variant == "0BAR_SL_REDUCE":
            if direction == "long":
                trade.sl = entry_price - SL_POINTS * 0.5
            else:
                trade.sl = entry_price + SL_POINTS * 0.5
        elif variant == "0BAR_SKIP":
            trade.exit_idx = entry_idx
            trade.exit_price = entry_price
            trade.pnl = 0
            trade.exit_reason = "SKIPPED"
            return trade
        elif variant == "0BAR_TIGHT_SL":
            if direction == "long":
                trade.sl = entry_price - SL_POINTS * 0.3
            else:
                trade.sl = entry_price + SL_POINTS * 0.3
    
    for i in range(entry_idx + 1, min(entry_idx + 50, len(bars))):
        bar = bars[i]
        
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


def calculate_metrics(trades: List[Trade]) -> Dict:
    if not trades:
        return {"count": 0}
    
    losses = [t for t in trades if t.pnl < 0]
    impulse_trades = [t for t in trades if t.impulse_0bar]
    impulse_losses = [t for t in impulse_trades if t.pnl < 0]
    non_impulse_losses = [t for t in trades if not t.impulse_0bar and t.pnl < 0]
    
    return {
        "count": len(trades),
        "wins": sum(1 for t in trades if t.pnl > 0),
        "losses": len(losses),
        "win_rate": round(sum(1 for t in trades if t.pnl > 0) / len(trades) * 100, 1),
        "avg_pnl": round(sum(t.pnl for t in trades) / len(trades), 2),
        "total_pnl": round(sum(t.pnl for t in trades), 2),
        "avg_loss": round(sum(t.pnl for t in losses) / len(losses), 2) if losses else 0,
        "worst_loss": round(min(t.pnl for t in trades), 2) if trades else 0,
        "impulse_0bar_count": len(impulse_trades),
        "impulse_0bar_pct": round(len(impulse_trades) / len(trades) * 100, 1),
        "impulse_loss_count": len(impulse_losses),
        "impulse_avg_loss": round(sum(t.pnl for t in impulse_losses) / len(impulse_losses), 2) if impulse_losses else 0,
        "non_impulse_avg_loss": round(sum(t.pnl for t in non_impulse_losses) / len(non_impulse_losses), 2) if non_impulse_losses else 0,
        "skipped": sum(1 for t in trades if t.exit_reason == "SKIPPED"),
    }


def run_experiment():
    print("=" * 70)
    print("COMMIT-025: Impulse 0-Bar Experiment")
    print("=" * 70)
    
    print("\nLoading data...")
    bars = load_and_prepare()
    print(f"Prepared {len(bars)} bars")
    
    variants = ["BASELINE", "0BAR_SL_REDUCE", "0BAR_SKIP", "0BAR_TIGHT_SL"]
    results = {}
    
    for variant in variants:
        trades = []
        last_trade_idx = -20
        
        for i in range(CHANNEL_PERIOD, len(bars) - 50):
            if i - last_trade_idx < 10:
                continue
            bar = bars[i]
            
            if bar.stb_short:
                trade = simulate_trade(bars, i, "short", variant)
                trades.append(trade)
                last_trade_idx = i
            elif bar.stb_long:
                trade = simulate_trade(bars, i, "long", variant)
                trades.append(trade)
                last_trade_idx = i
        
        metrics = calculate_metrics(trades)
        results[variant] = metrics
        
        print(f"\n{'-' * 50}")
        print(f"{variant}:")
        print(f"{'-' * 50}")
        print(f"  Trades: {metrics['count']}")
        print(f"  Win Rate: {metrics['win_rate']}%")
        print(f"  Avg PnL: {metrics['avg_pnl']}")
        print(f"  Avg Loss: {metrics['avg_loss']}")
        print(f"  0-Bar Impulse: {metrics['impulse_0bar_count']} ({metrics['impulse_0bar_pct']}%)")
        if variant != "BASELINE":
            print(f"  Impulse Avg Loss: {metrics['impulse_avg_loss']}")
            print(f"  Non-Impulse Avg Loss: {metrics['non_impulse_avg_loss']}")
        if metrics.get('skipped', 0) > 0:
            print(f"  Skipped: {metrics['skipped']}")
    
    print("\n" + "=" * 70)
    print("COMPARISON vs BASELINE")
    print("=" * 70)
    
    baseline = results["BASELINE"]
    for variant in ["0BAR_SL_REDUCE", "0BAR_SKIP", "0BAR_TIGHT_SL"]:
        v = results[variant]
        loss_change = v["avg_loss"] - baseline["avg_loss"]
        loss_change_pct = (loss_change / abs(baseline["avg_loss"])) * 100 if baseline["avg_loss"] != 0 else 0
        pnl_change = v["avg_pnl"] - baseline["avg_pnl"]
        
        print(f"\n{variant}:")
        print(f"  Avg Loss Change: {loss_change:+.2f} ({loss_change_pct:+.1f}%)")
        print(f"  Avg PnL Change: {pnl_change:+.2f}")
        print(f"  Win Rate: {v['win_rate']}% (baseline: {baseline['win_rate']}%)")
    
    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    
    best_variant = None
    best_improvement = 0
    for variant in ["0BAR_SL_REDUCE", "0BAR_SKIP", "0BAR_TIGHT_SL"]:
        v = results[variant]
        loss_improvement = v["avg_loss"] - baseline["avg_loss"]
        if loss_improvement > best_improvement:
            best_improvement = loss_improvement
            best_variant = variant
    
    if best_variant and best_improvement > 0:
        print(f"  BEST VARIANT: {best_variant}")
        print(f"  Loss Reduction: {best_improvement:.2f}")
        results["conclusion"] = {
            "status": "SUCCESS",
            "best_variant": best_variant,
            "loss_reduction": best_improvement,
            "statement": "0-bar impulse detection provides meaningful loss reduction"
        }
    else:
        print("  No significant improvement from 0-bar variants")
        results["conclusion"] = {
            "status": "NO_IMPROVEMENT",
            "statement": "0-bar detection does not significantly reduce losses"
        }
    
    results["metadata"] = {
        "data_file": DATA_PATH,
        "bars_count": len(bars),
        "test_date": datetime.now().isoformat()
    }
    
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to {RESULTS_PATH}")
    
    return results


if __name__ == "__main__":
    run_experiment()
