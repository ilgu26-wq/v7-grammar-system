"""
WIND-1: Local Compression Windmill
===================================

World Axioms (LOCKED):
- Irreversibility ON (Bar1)
- Storm-IN only
- No continuous values
- State judgment only

Micro Rule:
IF volatility_short < volatility_long
AND condition holds >= τ_min
THEN windmill_pass = TRUE
ELSE windmill_pass = FALSE

Question:
"Within Storm-IN, is the 'compressed position' less dangerous?"

Design Philosophy:
- Position first, not direction
- "Can it stay?" is the core question
- No force magnitude
- No prediction
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
    estimate_dir_count,
    WindmillState,
    simulate_outcome
)


def calculate_dc_stability(signals: List[Dict], idx: int, window: int) -> float:
    """
    Calculate DC channel stability using variance of dc_pre.
    Low variance = position maintained.
    High variance = position unstable.
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
    
    mean_dc = sum(dc_values) / len(dc_values)
    variance = sum((dc - mean_dc) ** 2 for dc in dc_values) / len(dc_values)
    return variance


def observe_local_compression(signals: List[Dict], idx: int, 
                               short_window: int = 3, 
                               long_window: int = 10) -> bool:
    """
    Local Compression = DC position quietly maintained.
    
    Rule: dc_variance_short < dc_variance_long
    (Recent position more stable than historical)
    
    Output: Boolean ONLY
    """
    var_short = calculate_dc_stability(signals, idx, short_window)
    var_long = calculate_dc_stability(signals, idx, long_window)
    
    return var_short < var_long


def check_compression_persistence(signals: List[Dict], idx: int, 
                                   tau_min: int = 4,
                                   short_window: int = 3,
                                   long_window: int = 10) -> bool:
    """
    Check if compression holds for majority of τ_min bars.
    
    This is the "position persistence" check.
    Relaxed: requires >= 75% of bars to show compression (not 100%).
    """
    if idx < tau_min + long_window:
        return False
    
    compression_count = 0
    for i in range(tau_min):
        check_idx = idx - i
        if observe_local_compression(signals, check_idx, short_window, long_window):
            compression_count += 1
    
    return compression_count >= (tau_min * 0.75)


def windmill_pass(signals: List[Dict], idx: int,
                  tau_min: int = 4,
                  short_window: int = 3,
                  long_window: int = 10) -> bool:
    """
    WIND-1 Micro Rule:
    
    IF volatility_short < volatility_long
    AND condition holds >= τ_min
    THEN TRUE
    ELSE FALSE
    """
    compression_now = observe_local_compression(signals, idx, short_window, long_window)
    persistence = check_compression_persistence(signals, idx, tau_min, short_window, long_window)
    
    return compression_now and persistence


def run_wind_1():
    """
    WIND-1 Experiment: Local Compression Windmill
    
    Question: Within Storm-IN, is compressed position less dangerous?
    
    Pass criterion: LossRate(reject) - LossRate(pass) >= 15pp
    """
    print("="*60)
    print("WIND-1: Local Compression Windmill")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nWorld Axioms: Irreversibility ON, Storm-IN only")
    print("-"*60)
    
    signals = load_signals()
    print(f"\nRaw signals: {len(signals)}")
    
    # Sort signals by timestamp for sequential analysis
    signals_sorted = sorted(signals, key=lambda x: x.get('timestamp', ''))
    
    # Filter Force-qualified and Storm-IN only
    F_THRESHOLD = 1.3
    
    results = {
        'storm_in_pass': [],      # Storm-IN AND windmill_pass=TRUE
        'storm_in_reject': [],    # Storm-IN AND windmill_pass=FALSE
        'storm_out_pass': [],     # For reference only
        'storm_out_reject': []    # For reference only
    }
    
    tau_min = 4
    short_window = 3
    long_window = 10
    
    print(f"\nParameters:")
    print(f"  τ_min = {tau_min}")
    print(f"  short_window = {short_window}")
    print(f"  long_window = {long_window}")
    
    for idx, s in enumerate(signals_sorted):
        # Skip if not enough history
        if idx < long_window + tau_min:
            continue
        
        # Force qualification
        force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
        if force < F_THRESHOLD:
            continue
        
        # Storm state
        storm_state = classify_storm_coordinate(s)
        
        # Windmill judgment
        wm_pass = windmill_pass(signals_sorted, idx, tau_min, short_window, long_window)
        
        # Outcome
        _, is_loss = simulate_outcome(s, 
                                       WindmillState.ON if storm_state == "STORM_IN" else WindmillState.OFF)
        
        # Categorize
        if storm_state == "STORM_IN":
            if wm_pass:
                results['storm_in_pass'].append(is_loss)
            else:
                results['storm_in_reject'].append(is_loss)
        else:
            if wm_pass:
                results['storm_out_pass'].append(is_loss)
            else:
                results['storm_out_reject'].append(is_loss)
    
    # Calculate and display results
    print("\n" + "="*60)
    print("WIND-1 RESULT")
    print("="*60)
    
    output_data = {}
    
    for category, losses in results.items():
        if len(losses) >= 20:
            loss_rate = sum(losses) / len(losses)
            print(f"\n{category}:")
            print(f"  N={len(losses)}, loss={loss_rate*100:.1f}%")
            output_data[category] = {
                'n': len(losses),
                'loss_rate': loss_rate
            }
        else:
            print(f"\n{category}: SKIP (N={len(losses)})")
            output_data[category] = {'status': 'SKIP', 'n': len(losses)}
    
    # Key comparison: Storm-IN pass vs reject
    print("\n" + "-"*60)
    print("KEY COMPARISON (Storm-IN only)")
    print("-"*60)
    
    si_pass = output_data.get('storm_in_pass', {})
    si_reject = output_data.get('storm_in_reject', {})
    
    verdict = "SKIP"
    diff = 0
    
    if si_pass.get('loss_rate') is not None and si_reject.get('loss_rate') is not None:
        pass_loss = si_pass['loss_rate']
        reject_loss = si_reject['loss_rate']
        diff = reject_loss - pass_loss
        
        print(f"\nwindmill_pass=TRUE:  N={si_pass['n']}, loss={pass_loss*100:.1f}%")
        print(f"windmill_pass=FALSE: N={si_reject['n']}, loss={reject_loss*100:.1f}%")
        print(f"Difference: {diff*100:.1f}pp")
        
        # PASS: reject more dangerous than pass by >= 15pp
        if diff >= 0.15:
            verdict = "PASS"
            print(f"\nVerdict: {verdict}")
            print("\n'Compressed position is less dangerous.'")
            print("→ WIND-1 rule SURVIVES.")
        elif diff >= 0.05:
            verdict = "WEAK"
            print(f"\nVerdict: {verdict}")
            print("\n'Some signal, but not strong enough.'")
            print("→ WIND-1 rule needs refinement.")
        else:
            verdict = "FAIL"
            print(f"\nVerdict: {verdict}")
            print("\n'No meaningful difference.'")
            print("→ WIND-1 rule REJECTED.")
    else:
        print("\nInsufficient data for comparison")
    
    # Storm-OUT reference (not for judgment)
    print("\n" + "-"*60)
    print("REFERENCE: Storm-OUT (not for rule judgment)")
    print("-"*60)
    
    so_pass = output_data.get('storm_out_pass', {})
    so_reject = output_data.get('storm_out_reject', {})
    
    if so_pass.get('loss_rate') is not None and so_reject.get('loss_rate') is not None:
        print(f"\nwindmill_pass=TRUE:  N={so_pass['n']}, loss={so_pass['loss_rate']*100:.1f}%")
        print(f"windmill_pass=FALSE: N={so_reject['n']}, loss={so_reject['loss_rate']*100:.1f}%")
    
    print("\n" + "="*60)
    print("INTERPRETATION")
    print("="*60)
    
    if verdict == "PASS":
        print("""
'Within Storm-IN, the position where energy is quietly maintained
 is indeed less dangerous than the position where it is not.'

This validates that "position persistence" is a valid micro rule.
""")
    elif verdict == "WEAK":
        print("""
'There is a signal, but the effect is not strong enough.
 Consider: shorter τ_min, different volatility measure, or other position definition.'
""")
    else:
        print("""
'Local compression does not distinguish danger within Storm-IN.
 This micro rule should be rejected or fundamentally redesigned.'
""")
    
    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'WIND-1',
        'question': 'Is compressed position less dangerous within Storm-IN?',
        'parameters': {
            'tau_min': tau_min,
            'short_window': short_window,
            'long_window': long_window,
            'force_threshold': F_THRESHOLD
        },
        'results': output_data,
        'difference_pp': diff * 100,
        'verdict': verdict
    }
    
    os.makedirs('v7-grammar-system/analysis/windmill', exist_ok=True)
    output_path = 'v7-grammar-system/analysis/windmill/wind_1_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_wind_1()
