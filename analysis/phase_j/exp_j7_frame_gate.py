"""
EXPERIMENT J7: Frame Gate Injection
====================================

Question:
"When frame_alive = FALSE, is Storm-IN still dangerous?"

This validates that the Multi-Dimensional Force Meter
works ONLY as a GATE, not as a VALUE.

ALLOWED:
✅ frame_alive = TRUE / FALSE (Boolean only)
✅ Gate injection before Storm judgment

FORBIDDEN:
❌ Continuous value injection
❌ Weight injection
❌ Condition relaxation/strengthening
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import (
    load_signals,
    classify_storm_coordinate,
    estimate_tau,
    estimate_dir_count,
    WindmillState,
    simulate_outcome
)


def observe_frame_alive(signal: Dict) -> bool:
    """
    Multi-Dimensional Force Meter observation.
    Output: Boolean ONLY.
    
    frame_alive = TRUE when:
    - τ ≥ 4 AND dir ≥ 3 (Frame preserved)
    
    No scores. No weights. No continuous values.
    """
    tau = estimate_tau(signal)
    dir_count = estimate_dir_count(signal)
    
    return tau >= 4 and dir_count >= 3


def run_exp_j7():
    """
    EXP-J7: Frame Gate Injection
    
    Question: frame_alive = FALSE → Storm-IN still dangerous?
    
    If YES → Frame gate is necessary
    If NO → Frame gate is redundant
    """
    print("="*50)
    print("EXPERIMENT J7")
    print("Frame Gate Injection")
    print("="*50)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nQuestion: frame_alive=FALSE → Storm-IN dangerous?")
    print("-"*50)
    
    signals = load_signals()
    print(f"\nRaw signals: {len(signals)}")
    
    # Filter Force-qualified signals
    F_THRESHOLD = 1.3
    force_qualified = [s for s in signals 
                       if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= F_THRESHOLD]
    
    print(f"Force-qualified: {len(force_qualified)}")
    
    # Label and categorize
    results = {
        'frame_alive_storm_in': [],
        'frame_dead_storm_in': [],
        'frame_alive_storm_out': [],
        'frame_dead_storm_out': []
    }
    
    for s in force_qualified:
        frame_alive = observe_frame_alive(s)
        storm_state = classify_storm_coordinate(s)
        _, is_loss = simulate_outcome(s, 
                                       WindmillState.ON if storm_state == "STORM_IN" else WindmillState.OFF)
        
        if frame_alive and storm_state == "STORM_IN":
            results['frame_alive_storm_in'].append(is_loss)
        elif not frame_alive and storm_state == "STORM_IN":
            results['frame_dead_storm_in'].append(is_loss)
        elif frame_alive and storm_state == "STORM_OUT":
            results['frame_alive_storm_out'].append(is_loss)
        else:
            results['frame_dead_storm_out'].append(is_loss)
    
    # Calculate loss rates
    print("\n" + "="*50)
    print("EXPERIMENT J7 RESULT")
    print("="*50)
    
    output_data = {}
    
    for category, losses in results.items():
        if len(losses) >= 10:
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
    
    # Key comparison: Storm-IN with frame_alive vs frame_dead
    print("\n" + "-"*50)
    print("KEY COMPARISON")
    print("-"*50)
    
    fa_in = output_data.get('frame_alive_storm_in', {})
    fd_in = output_data.get('frame_dead_storm_in', {})
    
    if fa_in.get('loss_rate') is not None and fd_in.get('loss_rate') is not None:
        fa_loss = fa_in['loss_rate']
        fd_loss = fd_in['loss_rate']
        diff = fd_loss - fa_loss
        
        print(f"\nStorm-IN with frame_alive=TRUE:  loss={fa_loss*100:.1f}%")
        print(f"Storm-IN with frame_alive=FALSE: loss={fd_loss*100:.1f}%")
        print(f"Difference: {diff*100:.1f}pp")
        
        # PASS: frame_dead is MORE dangerous even in Storm-IN
        verdict = "PASS" if diff > 0.10 else "FAIL"
        print(f"\nVerdict: {verdict}")
        
        if verdict == "PASS":
            print("\n'Even Storm-IN becomes dangerous when frame is dead.'")
            print("→ Frame gate is NECESSARY.")
        else:
            print("\n'Frame gate does not add value.'")
    else:
        print("Insufficient data for comparison")
        verdict = "SKIP"
    
    # Also compare Storm-OUT
    print("\n" + "-"*50)
    print("STORM-OUT COMPARISON")
    print("-"*50)
    
    fa_out = output_data.get('frame_alive_storm_out', {})
    fd_out = output_data.get('frame_dead_storm_out', {})
    
    if fa_out.get('loss_rate') is not None and fd_out.get('loss_rate') is not None:
        print(f"\nStorm-OUT with frame_alive=TRUE:  loss={fa_out['loss_rate']*100:.1f}%")
        print(f"Storm-OUT with frame_alive=FALSE: loss={fd_out['loss_rate']*100:.1f}%")
        out_diff = fd_out['loss_rate'] - fa_out['loss_rate']
        print(f"Difference: {out_diff*100:.1f}pp")
    
    print("\n" + "="*50)
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'J7',
        'question': 'frame_alive=FALSE → Storm-IN dangerous?',
        'results': output_data,
        'verdict': verdict
    }
    
    output_path = 'v7-grammar-system/analysis/phase_j/exp_j7_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_j7()
