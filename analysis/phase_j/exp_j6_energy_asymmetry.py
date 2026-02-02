"""
EXPERIMENT J6: Energy Asymmetry via Irreversibility
=====================================================

Question (FIXED):
"In the same Force condition, is the state that passed 
 the irreversible boundary always more dangerous?"

This question alone. Nothing else.

FORBIDDEN:
❌ Up/Down direction labels
❌ Energy quantification
❌ Coordinate values
❌ Continuous regression
❌ ML usage
❌ "Explanation" additions

ALLOWED:
✅ State separation necessity only
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


def extract_force_bin(signal: Dict) -> str:
    """Extract Force bin for control. No smoothing, no normalization."""
    force = signal.get('force_ratio_30', signal.get('force_ratio_20', 1.0))
    
    if force < 1.0:
        return "LOW"
    elif force < 1.5:
        return "MID"
    elif force < 2.0:
        return "HIGH"
    else:
        return "EXTREME"


def label_storm_state(signal: Dict) -> str:
    """Label Storm-IN / Storm-OUT. Nothing else."""
    return classify_storm_coordinate(signal)


def calculate_post_bar1_loss(signal: Dict, state: str) -> bool:
    """Calculate post-Bar1 loss. Binary only."""
    windmill = WindmillState.ON if state == "STORM_IN" else WindmillState.OFF
    _, is_loss = simulate_outcome(signal, windmill)
    return is_loss


def run_exp_j6():
    """
    EXP-J6: Energy Asymmetry via Irreversibility
    
    Step A: Force control
    Step B: State separation (Storm-IN / Storm-OUT)
    Step C: Result comparison (Post-Bar1 Loss Rate only)
    
    PASS: LossRate(Storm-OUT) - LossRate(Storm-IN) ≥ 20pp
    """
    print("="*50)
    print("EXPERIMENT J6")
    print("Energy Asymmetry via Irreversibility")
    print("="*50)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nQuestion: Same Force → Is post-Bar1 state more dangerous?")
    print("-"*50)
    
    # Load raw data
    signals = load_signals()
    print(f"\nRaw signals: {len(signals)}")
    
    # Step A: Label and bin
    labeled = []
    for s in signals:
        force_bin = extract_force_bin(s)
        storm_state = label_storm_state(s)
        is_loss = calculate_post_bar1_loss(s, storm_state)
        
        labeled.append({
            'force_bin': force_bin,
            'storm_state': storm_state,
            'post_bar1_loss': is_loss
        })
    
    # Step B & C: Compare by Force bin
    results = {}
    
    for force_bin in ["LOW", "MID", "HIGH", "EXTREME"]:
        bin_data = [l for l in labeled if l['force_bin'] == force_bin]
        
        storm_in = [l for l in bin_data if l['storm_state'] == "STORM_IN"]
        storm_out = [l for l in bin_data if l['storm_state'] == "STORM_OUT"]
        
        if len(storm_in) < 10 or len(storm_out) < 10:
            results[force_bin] = {'status': 'SKIP', 'reason': 'Insufficient data'}
            continue
        
        in_loss = sum(1 for l in storm_in if l['post_bar1_loss']) / len(storm_in)
        out_loss = sum(1 for l in storm_out if l['post_bar1_loss']) / len(storm_out)
        diff = out_loss - in_loss
        
        verdict = "PASS" if diff >= 0.20 else "FAIL"
        
        results[force_bin] = {
            'storm_in_n': len(storm_in),
            'storm_out_n': len(storm_out),
            'storm_in_loss': in_loss,
            'storm_out_loss': out_loss,
            'diff': diff,
            'verdict': verdict
        }
    
    # Output (FIXED FORMAT)
    print("\n" + "="*50)
    print("EXPERIMENT J6 RESULT")
    print("="*50)
    
    all_pass = True
    total_in_loss = 0
    total_out_loss = 0
    total_in_n = 0
    total_out_n = 0
    
    for force_bin, r in results.items():
        print("-"*50)
        print(f"Force bin: {force_bin}")
        
        if r.get('status') == 'SKIP':
            print(f"  Verdict: SKIP ({r['reason']})")
            continue
        
        print(f"  Storm-IN:  N={r['storm_in_n']}, loss={r['storm_in_loss']*100:.1f}%")
        print(f"  Storm-OUT: N={r['storm_out_n']}, loss={r['storm_out_loss']*100:.1f}%")
        print(f"  Diff: {r['diff']*100:.1f}pp")
        print(f"  Verdict: {r['verdict']}")
        
        if r['verdict'] != "PASS":
            all_pass = False
        
        total_in_n += r['storm_in_n']
        total_out_n += r['storm_out_n']
        total_in_loss += r['storm_in_loss'] * r['storm_in_n']
        total_out_loss += r['storm_out_loss'] * r['storm_out_n']
    
    # Aggregate
    print("-"*50)
    print("AGGREGATE")
    
    agg_in_loss = 0
    agg_out_loss = 0
    agg_diff = 0
    agg_verdict = "SKIP"
    
    if total_in_n > 0 and total_out_n > 0:
        agg_in_loss = total_in_loss / total_in_n
        agg_out_loss = total_out_loss / total_out_n
        agg_diff = agg_out_loss - agg_in_loss
        agg_verdict = "PASS" if agg_diff >= 0.20 else "FAIL"
        
        print(f"  Storm-IN:  N={total_in_n}, loss={agg_in_loss*100:.1f}%")
        print(f"  Storm-OUT: N={total_out_n}, loss={agg_out_loss*100:.1f}%")
        print(f"  Diff: {agg_diff*100:.1f}pp")
        print(f"  Verdict: {agg_verdict}")
    
    print("-"*50)
    
    # Final declaration (ALLOWED INTERPRETATION ONLY)
    print("\n" + "="*50)
    print("INTERPRETATION (SEALED)")
    print("="*50)
    
    if agg_diff >= 0.20:
        print("\n'The state that passed the irreversible boundary")
        print(" is always more dangerous,")
        print(" regardless of energy properties.'")
    else:
        print("\n'Asymmetry not confirmed at 20pp threshold.'")
    
    print("\n" + "="*50)
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'J6',
        'question': 'Same Force → Is post-Bar1 state more dangerous?',
        'results_by_bin': results,
        'aggregate': {
            'storm_in_n': total_in_n,
            'storm_out_n': total_out_n,
            'storm_in_loss': agg_in_loss if total_in_n > 0 else None,
            'storm_out_loss': agg_out_loss if total_out_n > 0 else None,
            'diff': agg_diff if total_in_n > 0 and total_out_n > 0 else None,
            'verdict': agg_verdict if total_in_n > 0 and total_out_n > 0 else 'SKIP'
        }
    }
    
    output_path = 'v7-grammar-system/analysis/phase_j/exp_j6_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_j6()
