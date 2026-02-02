"""
WIND-1 (RE-DESIGNED): Quiet Seat — Static Position Observation
===============================================================

Goal (one line):
"Within Storm-IN, pass only the 'originally quiet position'."
(becoming quiet ❌ / already quiet ⭕)

Design Philosophy:
- Position creates ❌
- Position 'fixes' and observes within it ⭕

Method: Distribution-based (Choice B)
- quiet_seat = volatility_long in lowest q% of Storm-IN distribution
- No dynamics, no time filter as cause
- τ used only as observation reliability mask
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple
import statistics

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import (
    load_signals,
    classify_storm_coordinate,
    estimate_tau,
    WindmillState,
    simulate_outcome
)


# Fixed percentile threshold (NOT tunable)
QUIET_PERCENTILE = 20  # lowest 20% = quiet seat


def calculate_dc_volatility(signals: List[Dict], idx: int, window: int = 10) -> float:
    """
    Calculate DC volatility using std of dc_pre over window.
    This is a static measure of position stability.
    """
    if idx < window:
        return float('inf')
    
    dc_values = []
    for i in range(idx - window, idx):
        s = signals[i]
        dc = s.get('dc_pre', 0.5)
        dc_values.append(dc)
    
    if len(dc_values) < 2:
        return float('inf')
    
    return statistics.stdev(dc_values)


def calculate_force_volatility(signals: List[Dict], idx: int, window: int = 10) -> float:
    """
    Alternative: Use force_ratio volatility as position stability.
    """
    if idx < window:
        return float('inf')
    
    force_values = []
    for i in range(idx - window, idx):
        s = signals[i]
        force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
        force_values.append(force)
    
    if len(force_values) < 2:
        return float('inf')
    
    return statistics.stdev(force_values)


def run_wind_1_quiet_seat():
    """
    WIND-1 (RE-DESIGNED): Quiet Seat
    
    Method: Distribution-based
    - quiet_seat = volatility in lowest 20% of Storm-IN distribution
    
    Question: Is the "originally quiet position" less dangerous?
    
    Pass criterion: LossRate(REJECT) - LossRate(PASS) >= 15pp
    """
    print("="*60)
    print("WIND-1 (RE-DESIGNED): Quiet Seat")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nGoal: 'Originally quiet position' only")
    print("Method: Distribution-based (lowest 20%)")
    print("-"*60)
    
    signals = load_signals()
    print(f"\nRaw signals: {len(signals)}")
    
    # Sort for sequential analysis
    signals_sorted = sorted(signals, key=lambda x: x.get('ts', x.get('timestamp', '')))
    
    # Filter: Force-qualified AND Storm-IN AND is_bar1
    F_THRESHOLD = 1.3
    TAU_RELIABILITY_MIN = 2  # τ < 2 = observation unreliable (mask only)
    WINDOW = 10
    
    # Step A: Collect Storm-IN samples with volatility
    storm_in_samples = []
    
    for idx, s in enumerate(signals_sorted):
        if idx < WINDOW:
            continue
        
        # Force qualification
        force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
        if force < F_THRESHOLD:
            continue
        
        # Storm-IN only
        storm_state = classify_storm_coordinate(s)
        if storm_state != "STORM_IN":
            continue
        
        # τ reliability mask (not filter, just exclude unreliable obs)
        tau = estimate_tau(s)
        if tau < TAU_RELIABILITY_MIN:
            continue  # Unreliable observation, skip
        
        # Calculate volatility (static, 1-shot)
        vol = calculate_dc_volatility(signals_sorted, idx, WINDOW)
        if vol == float('inf'):
            continue
        
        # Outcome
        _, is_loss = simulate_outcome(s, WindmillState.ON)
        
        storm_in_samples.append({
            'volatility': vol,
            'is_loss': is_loss
        })
    
    print(f"\nStorm-IN samples (after reliability mask): {len(storm_in_samples)}")
    
    if len(storm_in_samples) < 50:
        print("ERROR: Insufficient samples")
        return None
    
    # Step B: Calculate volatility distribution threshold
    volatilities = [s['volatility'] for s in storm_in_samples]
    volatilities_sorted = sorted(volatilities)
    threshold_idx = int(len(volatilities_sorted) * QUIET_PERCENTILE / 100)
    vol_threshold = volatilities_sorted[threshold_idx]
    
    print(f"\nVolatility distribution:")
    print(f"  Min: {min(volatilities):.4f}")
    print(f"  Max: {max(volatilities):.4f}")
    print(f"  20th percentile (threshold): {vol_threshold:.4f}")
    
    # Step B: Classify PASS/REJECT
    pass_samples = [s for s in storm_in_samples if s['volatility'] <= vol_threshold]
    reject_samples = [s for s in storm_in_samples if s['volatility'] > vol_threshold]
    
    print("\n" + "="*60)
    print("WIND-1 RESULT")
    print("="*60)
    
    # Step C: Calculate loss rates
    pass_losses = [s['is_loss'] for s in pass_samples]
    reject_losses = [s['is_loss'] for s in reject_samples]
    
    pass_loss_rate = sum(pass_losses) / len(pass_losses) if pass_losses else 0
    reject_loss_rate = sum(reject_losses) / len(reject_losses) if reject_losses else 0
    
    print(f"\nPASS (quiet_seat=TRUE, lowest {QUIET_PERCENTILE}%):")
    print(f"  N={len(pass_samples)}, loss={pass_loss_rate*100:.1f}%")
    
    print(f"\nREJECT (quiet_seat=FALSE):")
    print(f"  N={len(reject_samples)}, loss={reject_loss_rate*100:.1f}%")
    
    # Step D: Judgment
    diff = reject_loss_rate - pass_loss_rate
    
    print("\n" + "-"*60)
    print("JUDGMENT")
    print("-"*60)
    print(f"\nDifference: {diff*100:.1f}pp")
    
    if diff >= 0.15:
        verdict = "PASS"
        print(f"\nVerdict: {verdict}")
        print("\n'Quiet seat is less dangerous.'")
        print("→ WIND-1 rule SURVIVES.")
    elif diff >= 0.05:
        verdict = "WEAK"
        print(f"\nVerdict: {verdict}")
        print("\n'Signal exists but not strong enough.'")
    else:
        verdict = "FAIL"
        print(f"\nVerdict: {verdict}")
        print("\n'Quiet seat does not reduce danger.'")
        print("→ WIND-1 rule REJECTED.")
    
    print("\n" + "="*60)
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'WIND-1 (RE-DESIGNED)',
        'method': 'distribution-based quiet seat',
        'parameters': {
            'quiet_percentile': QUIET_PERCENTILE,
            'window': WINDOW,
            'tau_reliability_min': TAU_RELIABILITY_MIN,
            'force_threshold': F_THRESHOLD,
            'vol_threshold': vol_threshold
        },
        'results': {
            'pass': {'n': len(pass_samples), 'loss_rate': pass_loss_rate},
            'reject': {'n': len(reject_samples), 'loss_rate': reject_loss_rate}
        },
        'difference_pp': diff * 100,
        'verdict': verdict
    }
    
    output_path = 'v7-grammar-system/analysis/windmill/wind_1_quiet_seat_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_wind_1_quiet_seat()
