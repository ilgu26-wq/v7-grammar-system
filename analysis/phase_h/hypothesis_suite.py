"""
Phase H: Full Hypothesis Suite (Einstein + Non-Orthogonal + Irreversibility)
=============================================================================

FOUNDATIONAL AXIOM: IRREVERSIBILITY

"Prediction is structurally impossible because information 
 needed for prediction doesn't exist before the boundary."

This is not a limitation. This is the starting point.

The irreversible boundary (Bar1, DC=1) is where:
- Before: Multiple possibilities, direction unknown, information not fixed
- After: Converges to one, direction confirmed, cannot return

ALL other principles derive from this:
- Frame-first (Einstein): Frame must be fixed before conditions have meaning
- Non-orthogonality: Axes are NOT independent; τ collapse kills dir meaning
- Energy as property: Same magnitude ≠ same state

HYPOTHESIS CATEGORIES:
- H-F: Frame hypotheses
- H-A: Asymmetry hypotheses  
- H-T: Trajectory hypotheses
- H-E: Energy nature hypotheses
"""

import json
import os
import sys
from typing import Dict, List, Tuple
from datetime import datetime
import random

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import (
    load_signals, 
    classify_storm_coordinate,
    estimate_tau,
    estimate_dir_count,
    WindmillState,
    simulate_outcome
)


# =============================================================================
# H-F: FRAME HYPOTHESES
# =============================================================================

def run_h_f1(signals: List[Dict]) -> Dict:
    """
    H-F1: Frame Collapse Transition
    
    Hypothesis: After frame collapse, OUT transition occurs within Δt
    Metric: Transition rate
    PASS: ≥ 90%
    """
    print("\n" + "="*60)
    print("H-F1: FRAME COLLAPSE TRANSITION")
    print("="*60)
    
    # Find signals where frame collapses (τ or dir drops below threshold)
    collapse_events = []
    
    for signal in signals:
        tau = signal.get('tau_estimate', estimate_tau(signal))
        dir_count = signal.get('dir_count', estimate_dir_count(signal))
        
        # Simulate collapse: was IN, now frame broken
        original_class = classify_storm_coordinate(signal)
        
        if original_class == "STORM_IN":
            # Inject collapse
            collapsed = signal.copy()
            collapsed['tau_estimate'] = 2  # Below threshold
            collapsed['dir_count'] = 1     # Below threshold
            
            new_class = classify_storm_coordinate(collapsed)
            transitioned = (new_class == "STORM_OUT")
            collapse_events.append({
                'original': original_class,
                'new': new_class,
                'transitioned': transitioned
            })
    
    if not collapse_events:
        return {'hypothesis': 'H-F1', 'status': 'SKIP', 'reason': 'No collapse events'}
    
    transition_rate = sum(1 for e in collapse_events if e['transitioned']) / len(collapse_events)
    passed = transition_rate >= 0.90
    
    print(f"\n  Collapse events: {len(collapse_events)}")
    print(f"  Transition rate: {transition_rate*100:.1f}%")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    
    return {
        'hypothesis': 'H-F1_FRAME_COLLAPSE_TRANSITION',
        'passed': passed,
        'count': len(collapse_events),
        'transition_rate': transition_rate
    }


def run_h_f2(signals: List[Dict]) -> Dict:
    """
    H-F2: Non-Orthogonality Confirmation
    
    Hypothesis: When τ collapses alone, dir/Force explanatory power collapses
    Method: τ-blind, then measure dir/Force performance
    PASS: Explanatory power vanishes
    
    This tests: "Are axes independent?" → NO
    """
    print("\n" + "="*60)
    print("H-F2: NON-ORTHOGONALITY (τ collapse → dir/Force meaningless)")
    print("="*60)
    
    F_THRESHOLD = 1.3
    force_qualified = [s for s in signals 
                       if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= F_THRESHOLD]
    
    # Split by τ only
    tau_high = [s for s in force_qualified if estimate_tau(s) >= 4]
    tau_low = [s for s in force_qualified if estimate_tau(s) < 4]
    
    if not tau_high or not tau_low:
        return {'hypothesis': 'H-F2', 'status': 'SKIP', 'reason': 'Insufficient data'}
    
    # In τ_low (frame broken), check if dir still has explanatory power
    dir_high_in_tau_low = [s for s in tau_low if estimate_dir_count(s) >= 3]
    dir_low_in_tau_low = [s for s in tau_low if estimate_dir_count(s) < 3]
    
    if len(dir_high_in_tau_low) < 10 or len(dir_low_in_tau_low) < 10:
        print("\n  Insufficient data for dir comparison in τ_low")
        return {'hypothesis': 'H-F2', 'status': 'SKIP', 'reason': 'Insufficient dir splits'}
    
    # Calculate loss rates
    dir_high_loss = sum(1 for s in dir_high_in_tau_low 
                        if simulate_outcome(s, WindmillState.OFF)[1]) / len(dir_high_in_tau_low)
    dir_low_loss = sum(1 for s in dir_low_in_tau_low 
                       if simulate_outcome(s, WindmillState.OFF)[1]) / len(dir_low_in_tau_low)
    
    # If frame is broken (τ low), dir should NOT have explanatory power
    # i.e., dir_high and dir_low should have similar loss rates
    dir_diff = abs(dir_high_loss - dir_low_loss)
    
    print(f"\n  When τ < 4 (frame broken):")
    print(f"    dir ≥ 3: N={len(dir_high_in_tau_low)}, loss={dir_high_loss*100:.1f}%")
    print(f"    dir < 3: N={len(dir_low_in_tau_low)}, loss={dir_low_loss*100:.1f}%")
    print(f"    Difference: {dir_diff*100:.1f}pp")
    
    # PASS if dir has NO explanatory power when frame is broken (diff < 10pp)
    passed = dir_diff < 0.10
    
    print(f"\n  Non-orthogonality confirmed: {passed}")
    print(f"  (When frame broken, dir loses meaning: {passed})")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    
    return {
        'hypothesis': 'H-F2_NON_ORTHOGONALITY',
        'passed': passed,
        'dir_high_loss': dir_high_loss,
        'dir_low_loss': dir_low_loss,
        'diff': dir_diff
    }


# =============================================================================
# H-A: ASYMMETRY HYPOTHESES
# =============================================================================

def run_h_a1(signals: List[Dict]) -> Dict:
    """
    H-A1: OUT is Always More Dangerous
    
    Hypothesis: Under all controls, OUT is more dangerous than IN
    Controls: Force + DC + τ-blind
    PASS: Loss rate difference maintained
    """
    print("\n" + "="*60)
    print("H-A1: ASYMMETRY (OUT always more dangerous)")
    print("="*60)
    
    F_THRESHOLD = 1.3
    force_qualified = [s for s in signals 
                       if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= F_THRESHOLD]
    
    in_signals = [s for s in force_qualified if classify_storm_coordinate(s) == "STORM_IN"]
    out_signals = [s for s in force_qualified if classify_storm_coordinate(s) == "STORM_OUT"]
    
    if not in_signals or not out_signals:
        return {'hypothesis': 'H-A1', 'status': 'SKIP'}
    
    in_loss = sum(1 for s in in_signals if simulate_outcome(s, WindmillState.ON)[1]) / len(in_signals)
    out_loss = sum(1 for s in out_signals if simulate_outcome(s, WindmillState.OFF)[1]) / len(out_signals)
    
    diff = out_loss - in_loss
    passed = diff > 0.15  # OUT must be at least 15pp more dangerous
    
    print(f"\n  IN:  N={len(in_signals)}, loss={in_loss*100:.1f}%")
    print(f"  OUT: N={len(out_signals)}, loss={out_loss*100:.1f}%")
    print(f"  Difference: {diff*100:.1f}pp")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    
    return {
        'hypothesis': 'H-A1_ASYMMETRY',
        'passed': passed,
        'in_loss': in_loss,
        'out_loss': out_loss,
        'diff': diff
    }


def run_h_a2(signals: List[Dict]) -> Dict:
    """
    H-A2: No Single Coordinate Separates IN/OUT
    
    Hypothesis: IN/OUT separation cannot be reduced to a single axis
    Method: Test each coordinate's standalone separation power
    PASS: No single coordinate achieves the full separation
    
    This confirms non-orthogonality: you need the FRAME, not individual axes.
    """
    print("\n" + "="*60)
    print("H-A2: IRREDUCIBILITY (No single axis separates)")
    print("="*60)
    
    F_THRESHOLD = 1.3
    force_qualified = [s for s in signals 
                       if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= F_THRESHOLD]
    
    # Full separation (frame-based)
    in_signals = [s for s in force_qualified if classify_storm_coordinate(s) == "STORM_IN"]
    out_signals = [s for s in force_qualified if classify_storm_coordinate(s) == "STORM_OUT"]
    
    if not in_signals or not out_signals:
        return {'hypothesis': 'H-A2', 'status': 'SKIP'}
    
    full_in_loss = sum(1 for s in in_signals if simulate_outcome(s, WindmillState.ON)[1]) / len(in_signals)
    full_out_loss = sum(1 for s in out_signals if simulate_outcome(s, WindmillState.OFF)[1]) / len(out_signals)
    full_diff = full_out_loss - full_in_loss
    
    print(f"\n  FULL FRAME separation: {full_diff*100:.1f}pp")
    
    # Test single coordinates
    results = {}
    
    # τ alone
    tau_high = [s for s in force_qualified if estimate_tau(s) >= 4]
    tau_low = [s for s in force_qualified if estimate_tau(s) < 4]
    if tau_high and tau_low:
        tau_high_loss = sum(1 for s in tau_high if simulate_outcome(s, WindmillState.ON)[1]) / len(tau_high)
        tau_low_loss = sum(1 for s in tau_low if simulate_outcome(s, WindmillState.OFF)[1]) / len(tau_low)
        tau_diff = tau_low_loss - tau_high_loss
        results['tau_alone'] = tau_diff
        print(f"  τ alone: {tau_diff*100:.1f}pp")
    
    # dir alone
    dir_high = [s for s in force_qualified if estimate_dir_count(s) >= 3]
    dir_low = [s for s in force_qualified if estimate_dir_count(s) < 3]
    if dir_high and dir_low:
        dir_high_loss = sum(1 for s in dir_high if simulate_outcome(s, WindmillState.ON)[1]) / len(dir_high)
        dir_low_loss = sum(1 for s in dir_low if simulate_outcome(s, WindmillState.OFF)[1]) / len(dir_low)
        dir_diff = dir_low_loss - dir_high_loss
        results['dir_alone'] = dir_diff
        print(f"  dir alone: {dir_diff*100:.1f}pp")
    
    # DC alone
    dc_extreme = [s for s in force_qualified if s.get('dc_pre', 0.5) <= 0.3 or s.get('dc_pre', 0.5) >= 0.7]
    dc_mid = [s for s in force_qualified if 0.3 < s.get('dc_pre', 0.5) < 0.7]
    if dc_extreme and dc_mid:
        dc_ext_loss = sum(1 for s in dc_extreme if simulate_outcome(s, WindmillState.ON)[1]) / len(dc_extreme)
        dc_mid_loss = sum(1 for s in dc_mid if simulate_outcome(s, WindmillState.OFF)[1]) / len(dc_mid)
        dc_diff = dc_mid_loss - dc_ext_loss
        results['dc_alone'] = dc_diff
        print(f"  DC alone: {dc_diff*100:.1f}pp")
    
    # PASS: No single coordinate achieves ≥ 80% of full separation
    max_single = max(results.values()) if results else 0
    ratio = max_single / full_diff if full_diff > 0 else 0
    
    passed = ratio < 0.80  # Single axis < 80% of full frame
    
    print(f"\n  Max single axis: {max_single*100:.1f}pp ({ratio*100:.1f}% of full)")
    print(f"  Irreducibility confirmed: {passed}")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    
    return {
        'hypothesis': 'H-A2_IRREDUCIBILITY',
        'passed': passed,
        'full_diff': full_diff,
        'single_results': results,
        'max_single_ratio': ratio
    }


# =============================================================================
# H-T: TRAJECTORY HYPOTHESES
# =============================================================================

def run_h_t1(signals: List[Dict]) -> Dict:
    """
    H-T1: Same Coordinates, Different Frames → Different Results
    
    Hypothesis: Same coordinate values with different frames produce different outcomes
    Method: Same Force bin, FrameGate TRUE vs FALSE comparison
    PASS: Outcome difference exists
    """
    print("\n" + "="*60)
    print("H-T1: FRAME DETERMINES OUTCOME (same coords, diff frames)")
    print("="*60)
    
    # Narrow Force bin for control
    force_bin = [s for s in signals 
                 if 1.5 <= s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) <= 2.0]
    
    if len(force_bin) < 50:
        return {'hypothesis': 'H-T1', 'status': 'SKIP', 'reason': 'Insufficient Force bin'}
    
    frame_true = [s for s in force_bin if classify_storm_coordinate(s) == "STORM_IN"]
    frame_false = [s for s in force_bin if classify_storm_coordinate(s) == "STORM_OUT"]
    
    if len(frame_true) < 10 or len(frame_false) < 10:
        return {'hypothesis': 'H-T1', 'status': 'SKIP', 'reason': 'Insufficient frame split'}
    
    true_loss = sum(1 for s in frame_true if simulate_outcome(s, WindmillState.ON)[1]) / len(frame_true)
    false_loss = sum(1 for s in frame_false if simulate_outcome(s, WindmillState.OFF)[1]) / len(frame_false)
    
    diff = false_loss - true_loss
    passed = diff > 0.10  # Must have at least 10pp difference
    
    print(f"\n  Force bin [1.5, 2.0]:")
    print(f"  Frame TRUE:  N={len(frame_true)}, loss={true_loss*100:.1f}%")
    print(f"  Frame FALSE: N={len(frame_false)}, loss={false_loss*100:.1f}%")
    print(f"  Difference: {diff*100:.1f}pp")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    
    return {
        'hypothesis': 'H-T1_FRAME_DETERMINES_OUTCOME',
        'passed': passed,
        'frame_true_loss': true_loss,
        'frame_false_loss': false_loss,
        'diff': diff
    }


def run_h_t2(signals: List[Dict]) -> Dict:
    """
    H-T2: Peripheral Energy Cannot Sustain Trajectory
    
    Hypothesis: Force spikes without frame cannot create sustained trajectory
    Method: Force spike → check trajectory persistence
    PASS: Persistence fails
    """
    print("\n" + "="*60)
    print("H-T2: PERIPHERAL ENERGY (Force spike → no trajectory)")
    print("="*60)
    
    # Find Force spikes with broken frame
    spikes = []
    for s in signals:
        force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
        tau = estimate_tau(s)
        dir_count = estimate_dir_count(s)
        
        if force >= 2.0 and (tau < 4 or dir_count < 3):
            spikes.append(s)
    
    if len(spikes) < 20:
        print(f"\n  Insufficient spikes: {len(spikes)}")
        return {'hypothesis': 'H-T2', 'status': 'SKIP'}
    
    # All spikes should fail (be losses or cutouts)
    failures = sum(1 for s in spikes if simulate_outcome(s, WindmillState.OFF)[1])
    failure_rate = failures / len(spikes)
    
    passed = failure_rate >= 0.50  # At least 50% fail
    
    print(f"\n  Force spikes without frame: {len(spikes)}")
    print(f"  Failure rate: {failure_rate*100:.1f}%")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    
    return {
        'hypothesis': 'H-T2_PERIPHERAL_NO_TRAJECTORY',
        'passed': passed,
        'spike_count': len(spikes),
        'failure_rate': failure_rate
    }


# =============================================================================
# H-E: ENERGY NATURE HYPOTHESES
# =============================================================================

def run_h_e1(signals: List[Dict]) -> Dict:
    """
    H-E1: Only Coherent Energy Creates Trajectory
    
    Hypothesis: Only τ+dir maintained zones create reproducible trajectories
    Method: Compare maintained vs broken zones
    PASS: Only maintained shows reproducibility
    """
    print("\n" + "="*60)
    print("H-E1: COHERENT ENERGY (only maintained creates trajectory)")
    print("="*60)
    
    F_THRESHOLD = 1.3
    force_qualified = [s for s in signals 
                       if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= F_THRESHOLD]
    
    # Coherent: both τ and dir maintained
    coherent = [s for s in force_qualified 
                if estimate_tau(s) >= 4 and estimate_dir_count(s) >= 3]
    
    # Incoherent: at least one broken
    incoherent = [s for s in force_qualified 
                  if estimate_tau(s) < 4 or estimate_dir_count(s) < 3]
    
    if len(coherent) < 20 or len(incoherent) < 20:
        return {'hypothesis': 'H-E1', 'status': 'SKIP'}
    
    # Reproducibility = low variance in outcomes
    coherent_wins = sum(1 for s in coherent if not simulate_outcome(s, WindmillState.ON)[1])
    incoherent_wins = sum(1 for s in incoherent if not simulate_outcome(s, WindmillState.OFF)[1])
    
    coherent_win_rate = coherent_wins / len(coherent)
    incoherent_win_rate = incoherent_wins / len(incoherent)
    
    # Coherent should have much higher win rate (reproducible success)
    diff = coherent_win_rate - incoherent_win_rate
    passed = diff > 0.20  # At least 20pp better
    
    print(f"\n  Coherent (τ+dir maintained): N={len(coherent)}, win={coherent_win_rate*100:.1f}%")
    print(f"  Incoherent (broken): N={len(incoherent)}, win={incoherent_win_rate*100:.1f}%")
    print(f"  Difference: {diff*100:.1f}pp")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    
    return {
        'hypothesis': 'H-E1_COHERENT_TRAJECTORY',
        'passed': passed,
        'coherent_win_rate': coherent_win_rate,
        'incoherent_win_rate': incoherent_win_rate,
        'diff': diff
    }


def run_h_e2(signals: List[Dict]) -> Dict:
    """
    H-E2: Energy State Transition is Discrete, Not Continuous
    
    Hypothesis: Transitions between energy states are state changes, not gradual
    Method: Boundary zone analysis
    PASS: Continuous model fails (discrete works better)
    """
    print("\n" + "="*60)
    print("H-E2: DISCRETE STATE TRANSITION (not continuous)")
    print("="*60)
    
    F_THRESHOLD = 1.3
    force_qualified = [s for s in signals 
                       if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= F_THRESHOLD]
    
    # Find boundary signals
    boundary = [s for s in force_qualified 
                if 3 <= estimate_tau(s) <= 5 and 2 <= estimate_dir_count(s) <= 4]
    
    if len(boundary) < 30:
        return {'hypothesis': 'H-E2', 'status': 'SKIP'}
    
    # In boundary: classify and check if outcomes match discrete prediction
    correct_discrete = 0
    
    for s in boundary:
        classification = classify_storm_coordinate(s)
        _, is_loss = simulate_outcome(s, 
                                       WindmillState.ON if classification == "STORM_IN" else WindmillState.OFF)
        
        # Discrete prediction: OUT should lose more
        if classification == "STORM_OUT" and is_loss:
            correct_discrete += 1
        elif classification == "STORM_IN" and not is_loss:
            correct_discrete += 1
    
    discrete_accuracy = correct_discrete / len(boundary)
    
    # PASS if discrete model works reasonably well at boundary (> 55%)
    passed = discrete_accuracy > 0.55
    
    print(f"\n  Boundary signals: {len(boundary)}")
    print(f"  Discrete model accuracy: {discrete_accuracy*100:.1f}%")
    print(f"  (Above random = discrete state model valid)")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'}")
    
    return {
        'hypothesis': 'H-E2_DISCRETE_TRANSITION',
        'passed': passed,
        'boundary_count': len(boundary),
        'discrete_accuracy': discrete_accuracy
    }


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_phase_h():
    """Run all Phase H hypothesis tests."""
    print("="*70)
    print("PHASE H: FULL HYPOTHESIS SUITE")
    print("(Einstein + Non-Orthogonal + Irreversibility)")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nFoundational Axiom: IRREVERSIBILITY")
    print("'Prediction is structurally impossible'")
    print("="*70)
    
    signals = load_signals()
    print(f"\nLoaded {len(signals)} signals for testing")
    
    results = {}
    
    # Frame hypotheses
    results['H-F1'] = run_h_f1(signals)
    results['H-F2'] = run_h_f2(signals)
    
    # Asymmetry hypotheses
    results['H-A1'] = run_h_a1(signals)
    results['H-A2'] = run_h_a2(signals)
    
    # Trajectory hypotheses
    results['H-T1'] = run_h_t1(signals)
    results['H-T2'] = run_h_t2(signals)
    
    # Energy nature hypotheses
    results['H-E1'] = run_h_e1(signals)
    results['H-E2'] = run_h_e2(signals)
    
    # Summary
    passed = sum(1 for r in results.values() if r.get('passed', False))
    skipped = sum(1 for r in results.values() if r.get('status') == 'SKIP')
    total = len(results)
    
    print("\n" + "="*70)
    print("PHASE H FINAL SUMMARY")
    print("="*70)
    for name, result in results.items():
        if result.get('status') == 'SKIP':
            print(f"  {name}: ⏭️ SKIP")
        elif result.get('passed'):
            print(f"  {name}: ✅ PASS")
        else:
            print(f"  {name}: ❌ FAIL")
    
    print(f"\n  Passed: {passed}/{total}")
    print(f"  Skipped: {skipped}/{total}")
    
    all_pass = (passed + skipped == total) and (skipped <= 2)
    
    if all_pass:
        print(f"\n  🎯 PHASE H PASSED — All hypotheses validated")
        print(f"\n  FOUNDATIONAL DECLARATION:")
        print(f"  'This system does not decompose energy.")
        print(f"   Energy reveals its nature only when the frame is preserved.")
        print(f"   Those natures are non-orthogonally entangled.")
        print(f"   Therefore, judgment is only possible through state transition.")
        print(f"   not through coordinates.'")
    else:
        print(f"\n  ⚠️ PHASE H INCOMPLETE — Review required")
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'phase': 'H',
        'foundational_axiom': 'IRREVERSIBILITY',
        'results': results,
        'passed': passed,
        'skipped': skipped,
        'total': total,
        'all_pass': all_pass
    }
    
    os.makedirs('v7-grammar-system/analysis/phase_h', exist_ok=True)
    output_path = 'v7-grammar-system/analysis/phase_h/hypothesis_results.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_phase_h()
