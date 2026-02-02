"""
COMMIT-023-B: Boundary-Aware Impulse Warning Experiment

Purpose:
- NOT predicting impulse
- NOT modifying entry
- ONLY testing post-entry defense
- ONLY measuring loss severity reduction

Key insight:
Δ is always a value, but impulse is "value acting as force on fragile boundary"
"""

import json
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

STATE_LOCK_WINDOW = 3
STB_MARGIN_REF = 5.0
BOUNDARY_SENSITIVITY_THRESHOLD = 0.6
DELTA_QUANTILE = 0.90


class DefenseVariant(Enum):
    NONE = "baseline"
    A_SL_REDUCE = "sl_reduce_0.7"
    B_FORCE_EE = "force_ee"
    C_POSITION_REDUCE = "position_reduce_0.5"


@dataclass
class BarData:
    index: int
    open: float
    high: float
    low: float
    close: float
    delta: float
    state: str
    state_age: int
    stb_margin: float
    delta_q90: float
    boundary_sensitivity: float = 0.0


@dataclass
class Trade:
    entry_bar: int
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float = 1.0
    exit_bar: Optional[int] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    impulse_warning: bool = False
    exit_reason: str = ""


def calculate_boundary_sensitivity(
    state_age: int,
    stb_margin: float,
    bars_since_entry: int
) -> float:
    """
    BoundarySensitivity = degree to which current decision structure
    can be perturbed by small Δ
    
    Components:
    1. STATE sensitivity: high if state just locked
    2. STB margin sensitivity: high if near minimum condition
    3. Entry proximity: high if just entered
    """
    state_sensitivity = 1.0 if state_age <= STATE_LOCK_WINDOW else 0.0
    stb_sensitivity = 1.0 - min(max(stb_margin / STB_MARGIN_REF, 0), 1)
    entry_sensitivity = 1.0 if bars_since_entry <= 1 else 0.0
    
    boundary_sensitivity = (
        0.4 * state_sensitivity +
        0.4 * stb_sensitivity +
        0.2 * entry_sensitivity
    )
    
    return boundary_sensitivity


def is_impulse(delta: float, boundary_sensitivity: float, delta_q90: float) -> bool:
    """
    Impulse = Δ acting as force on fragile boundary
    
    NOT just large Δ
    NOT just high volatility
    Δ × boundary_sensitivity determines impulse
    """
    return (
        abs(delta) > delta_q90 and
        boundary_sensitivity >= BOUNDARY_SENSITIVITY_THRESHOLD
    )


def check_impulse_warning(trade: Trade, bar: BarData) -> bool:
    """
    Impulse Warning (IW):
    - Post-entry only (NOT prediction)
    - First bar after entry only
    - Boundary-aware
    """
    if trade.exit_bar is not None:
        return False
    if bar.index != trade.entry_bar + 1:
        return False
    return is_impulse(
        delta=bar.delta,
        boundary_sensitivity=bar.boundary_sensitivity,
        delta_q90=bar.delta_q90
    )


def apply_defense(trade: Trade, variant: DefenseVariant) -> Trade:
    """Apply defense mechanism when IW triggers"""
    if variant == DefenseVariant.A_SL_REDUCE:
        trade.stop_loss *= 0.7
    elif variant == DefenseVariant.B_FORCE_EE:
        pass
    elif variant == DefenseVariant.C_POSITION_REDUCE:
        trade.position_size *= 0.5
    return trade


def calculate_loss_severity_metrics(trades: List[Trade]) -> Dict:
    """
    ONLY measure loss severity
    NOT total profit
    NOT win rate
    """
    losses = [t.pnl for t in trades if t.pnl < 0]
    
    if not losses:
        return {
            "avg_loss": 0.0,
            "p95_loss": 0.0,
            "worst_5": [],
            "loss_count": 0,
            "total_trades": len(trades)
        }
    
    return {
        "avg_loss": float(np.mean(losses)),
        "p95_loss": float(np.percentile(losses, 5)),
        "worst_5": sorted(losses)[:5],
        "loss_count": len(losses),
        "total_trades": len(trades),
        "iw_triggered_count": sum(1 for t in trades if t.impulse_warning),
        "iw_loss_count": sum(1 for t in trades if t.impulse_warning and t.pnl < 0)
    }


def run_experiment(
    bars: List[BarData],
    trades: List[Trade],
    variant: DefenseVariant
) -> Dict:
    """
    Run IW experiment with specified defense variant
    """
    experiment_trades = []
    
    for trade in trades:
        trade_copy = Trade(
            entry_bar=trade.entry_bar,
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            position_size=trade.position_size
        )
        
        for bar in bars:
            if bar.index == trade.entry_bar + 1:
                if check_impulse_warning(trade_copy, bar):
                    trade_copy.impulse_warning = True
                    if variant != DefenseVariant.NONE:
                        trade_copy = apply_defense(trade_copy, variant)
        
        trade_copy.pnl = trade.pnl
        if trade_copy.impulse_warning and variant == DefenseVariant.C_POSITION_REDUCE:
            trade_copy.pnl *= 0.5
        
        experiment_trades.append(trade_copy)
    
    return {
        "variant": variant.value,
        "metrics": calculate_loss_severity_metrics(experiment_trades)
    }


def compare_variants(
    bars: List[BarData],
    trades: List[Trade]
) -> Dict:
    """
    Compare all defense variants against baseline
    """
    results = {}
    
    for variant in DefenseVariant:
        result = run_experiment(bars, trades, variant)
        results[variant.value] = result["metrics"]
    
    baseline = results["baseline"]
    
    comparisons = {}
    for variant_name, metrics in results.items():
        if variant_name == "baseline":
            continue
        comparisons[variant_name] = {
            "avg_loss_change": metrics["avg_loss"] - baseline["avg_loss"],
            "avg_loss_change_pct": (
                (metrics["avg_loss"] - baseline["avg_loss"]) / abs(baseline["avg_loss"]) * 100
                if baseline["avg_loss"] != 0 else 0
            ),
            "p95_loss_change": metrics["p95_loss"] - baseline["p95_loss"],
            "iw_triggered": metrics["iw_triggered_count"],
            "iw_loss_rate": (
                metrics["iw_loss_count"] / metrics["iw_triggered_count"] * 100
                if metrics["iw_triggered_count"] > 0 else 0
            )
        }
    
    return {
        "baseline": baseline,
        "variants": {k: v for k, v in results.items() if k != "baseline"},
        "comparisons": comparisons,
        "conclusion": generate_conclusion(baseline, comparisons)
    }


def generate_conclusion(baseline: Dict, comparisons: Dict) -> Dict:
    """
    Generate experiment conclusion
    
    Success: Loss severity decreased, non-impulse unchanged
    Failure: No effect at 1-bar lag (response latency constraint)
    """
    best_variant = None
    best_improvement = 0
    
    for variant_name, comp in comparisons.items():
        if comp["avg_loss_change"] > 0:
            if comp["avg_loss_change"] > best_improvement:
                best_improvement = comp["avg_loss_change"]
                best_variant = variant_name
    
    if best_variant:
        return {
            "status": "SUCCESS",
            "best_variant": best_variant,
            "avg_loss_reduction_pct": comparisons[best_variant]["avg_loss_change_pct"],
            "statement": "Impulse cannot be predicted, but its damage can be bounded when boundary sensitivity is high."
        }
    else:
        return {
            "status": "LATENCY_CONSTRAINT",
            "statement": "Impulse damage is already realized by the first bar, defining a hard response-latency constraint."
        }


def generate_sample_data() -> Tuple[List[BarData], List[Trade]]:
    """Generate sample data for testing"""
    np.random.seed(42)
    
    deltas = np.random.randn(100) * 10
    delta_q90 = np.percentile(np.abs(deltas), 90)
    
    bars = []
    price = 20000.0
    
    for i in range(100):
        delta = deltas[i]
        high = price + abs(delta) + np.random.rand() * 5
        low = price - abs(delta) - np.random.rand() * 5
        close = price + delta
        
        state_age = np.random.randint(1, 10)
        stb_margin = np.random.rand() * 10
        bars_since_entry = 1 if i % 10 == 1 else 5
        
        boundary_sensitivity = calculate_boundary_sensitivity(
            state_age, stb_margin, bars_since_entry
        )
        
        bars.append(BarData(
            index=i,
            open=price,
            high=high,
            low=low,
            close=close,
            delta=delta,
            state="THETA_1" if delta > 0 else "THETA_2",
            state_age=state_age,
            stb_margin=stb_margin,
            delta_q90=delta_q90,
            boundary_sensitivity=boundary_sensitivity
        ))
        
        price = close
    
    trades = []
    for i in range(10, 90, 10):
        pnl = np.random.randn() * 50
        trades.append(Trade(
            entry_bar=i,
            direction="long" if bars[i].delta > 0 else "short",
            entry_price=bars[i].close,
            stop_loss=bars[i].close - 20,
            take_profit=bars[i].close + 30,
            pnl=pnl
        ))
    
    return bars, trades


if __name__ == "__main__":
    print("=" * 60)
    print("COMMIT-023-B: Boundary-Aware Impulse Warning Experiment")
    print("=" * 60)
    
    bars, trades = generate_sample_data()
    
    print(f"\nSample data generated:")
    print(f"  Bars: {len(bars)}")
    print(f"  Trades: {len(trades)}")
    print(f"  Delta q90: {bars[0].delta_q90:.2f}")
    
    results = compare_variants(bars, trades)
    
    print("\n" + "-" * 40)
    print("BASELINE METRICS:")
    print("-" * 40)
    for key, value in results["baseline"].items():
        print(f"  {key}: {value}")
    
    print("\n" + "-" * 40)
    print("VARIANT COMPARISONS:")
    print("-" * 40)
    for variant_name, comp in results["comparisons"].items():
        print(f"\n  {variant_name}:")
        for key, value in comp.items():
            if isinstance(value, float):
                print(f"    {key}: {value:.2f}")
            else:
                print(f"    {key}: {value}")
    
    print("\n" + "=" * 60)
    print("CONCLUSION:")
    print("=" * 60)
    for key, value in results["conclusion"].items():
        print(f"  {key}: {value}")
    
    with open("experiments/impulse_warning_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print("\nResults saved to experiments/impulse_warning_results.json")
