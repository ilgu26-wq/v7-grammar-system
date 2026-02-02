"""
Phase N-0: Coordinate-ization Feasibility Test
================================================

Purpose: Evaluate if multi-dimensional force can be expressed as
         multi-dimensional coordinates (continuous values),
         WITHOUT violating the four prohibitions:
         - Center decomposition
         - Proxy-variable substitution
         - Optimization
         - Distance/angle games

Key Distinction:
- ✅ ALLOWED: "Coordinate-ization" (recording as continuous log)
- ❌ FORBIDDEN: "Coordinate system operation" (distance, clustering, optimization)

Comparison Models:
- M0 (Current): Storm-IN/OUT force meter (Binary)
- M1 (Candidate): Coordinate-log (Continuous)

Tests:
- N0-A: Early Detection Test
- N0-B: False Positive Reduction Test

INTERPRETATION LOCK (3 forbidden statements):
- "x₂ is the core"
- "In this coordinate space, the distance..."
- "The optimal boundary is..."

ONLY ALLOWED CONCLUSION:
"The coordinate-ized observation log showed/did not show
 additional value in (early detection / FP reduction)
 compared to the existing Storm-IN/OUT meter."
"""

import json
import os
import sys
from typing import Dict, List, Tuple
from datetime import datetime
from enum import Enum

# Add parent path for imports
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
# COORDINATE-IZATION (NOT COORDINATE SYSTEM OPERATION)
# =============================================================================

def coordinatize_signal(signal: Dict) -> Dict[str, float]:
    """
    Convert signal to coordinate log.
    
    This is RECORDING, not OPERATING.
    Each dimension is normalized to [0,1] for logging only.
    
    Dimensions:
    - x1: Force magnitude (normalized)
    - x2: Persistence proxy (τ-related)
    - x3: Alignment proxy (dir consistency)
    - x4: Stability proxy (dc_pre)
    """
    force = signal.get('force_ratio_30', signal.get('force_ratio_20', 1.0))
    tau = estimate_tau(signal)
    dir_count = estimate_dir_count(signal)
    dc = signal.get('dc_pre', 0.5)
    
    # Normalize to [0,1] - for LOGGING only, NOT for distance calculation
    x1 = min(force / 3.0, 1.0)  # Force: 0-3 → 0-1
    x2 = min(tau / 10.0, 1.0)   # τ: 0-10 → 0-1
    x3 = min(dir_count / 6.0, 1.0)  # Dir: 0-6 → 0-1
    x4 = dc  # DC: already 0-1
    
    return {
        'x1_force': x1,
        'x2_persistence': x2,
        'x3_alignment': x3,
        'x4_stability': x4,
        'raw_force': force,
        'raw_tau': tau,
        'raw_dir': dir_count,
        'raw_dc': dc
    }


# =============================================================================
# M0: EXISTING STORM-IN/OUT METER (BINARY)
# =============================================================================

def m0_classify(signal: Dict) -> Tuple[str, int]:
    """
    M0: Current Storm-IN/OUT binary classifier.
    Returns: (classification, detection_bar)
    
    detection_bar = 0 (instant detection at signal time)
    """
    classification = classify_storm_coordinate(signal)
    return classification, 0  # Instant detection


# =============================================================================
# M1: COORDINATE-LOG BASED DETECTOR
# =============================================================================

# PRE-FIXED THRESHOLDS (NO OPTIMIZATION ALLOWED)
# These are set ONCE before experiment, never tuned
M1_THRESHOLDS = {
    'x2_min': 0.4,  # τ >= 4 → x2 >= 0.4
    'x3_min': 0.5,  # dir >= 3 → x3 >= 0.5
}

def m1_classify(signal: Dict) -> Tuple[str, int]:
    """
    M1: Coordinate-log based detector.
    
    RULES (pre-fixed, single-dimension or 2D AND/OR only):
    - IN: x2 >= x2_min AND x3 >= x3_min
    - OUT: otherwise
    
    Returns: (classification, detection_bar)
    
    detection_bar = number of bars BEFORE the standard detection
    (positive = earlier warning, negative = later)
    """
    coords = coordinatize_signal(signal)
    
    # Pre-fixed rule (2D AND, NO optimization)
    if coords['x2_persistence'] >= M1_THRESHOLDS['x2_min'] and \
       coords['x3_alignment'] >= M1_THRESHOLDS['x3_min']:
        classification = "STORM_IN"
    else:
        classification = "STORM_OUT"
    
    # For early detection test: check if threshold was crossed earlier
    # In this simplified version, detection is instant (bar=0)
    detection_bar = 0
    
    return classification, detection_bar


# =============================================================================
# TEST N0-A: EARLY DETECTION TEST
# =============================================================================

def run_test_n0_a(signals: List[Dict]) -> Dict:
    """
    Test N0-A: Early Detection Test
    
    Question: Does M1 warn of danger earlier than M0,
              without increasing false alarms?
    
    Method:
    - Compare M0 and M1 classifications
    - Measure: When M1 says OUT but M0 says IN,
               was there actual danger?
    
    PASS Criteria:
    - M1 provides earlier warning (or same timing)
    - False positive rate does not increase
    """
    print("\n" + "="*60)
    print("TEST N0-A: EARLY DETECTION")
    print("="*60)
    print("\nQuestion: Does coordinate-log detect danger earlier?")
    
    F_THRESHOLD = 1.3
    force_qualified = [s for s in signals 
                       if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= F_THRESHOLD]
    
    # Compare M0 and M1 classifications
    m0_in_m1_out = []  # M0 says safe, M1 says danger
    m0_out_m1_in = []  # M0 says danger, M1 says safe
    both_in = []
    both_out = []
    
    for signal in force_qualified:
        m0_class, _ = m0_classify(signal)
        m1_class, _ = m1_classify(signal)
        
        rr, is_loss = simulate_outcome(signal, 
                                        WindmillState.ON if m0_class == "STORM_IN" else WindmillState.OFF)
        
        result = {
            'signal': signal,
            'm0': m0_class,
            'm1': m1_class,
            'rr': rr,
            'is_loss': is_loss,
            'coords': coordinatize_signal(signal)
        }
        
        if m0_class == "STORM_IN" and m1_class == "STORM_OUT":
            m0_in_m1_out.append(result)
        elif m0_class == "STORM_OUT" and m1_class == "STORM_IN":
            m0_out_m1_in.append(result)
        elif m0_class == "STORM_IN" and m1_class == "STORM_IN":
            both_in.append(result)
        else:
            both_out.append(result)
    
    print(f"\n--- CLASSIFICATION COMPARISON ---")
    print(f"  Both IN:         {len(both_in)}")
    print(f"  Both OUT:        {len(both_out)}")
    print(f"  M0=IN, M1=OUT:   {len(m0_in_m1_out)} (M1 more cautious)")
    print(f"  M0=OUT, M1=IN:   {len(m0_out_m1_in)} (M1 more permissive)")
    
    # Key question: When M1 says danger but M0 doesn't, was M1 right?
    if m0_in_m1_out:
        m1_early_correct = sum(1 for r in m0_in_m1_out if r['is_loss']) / len(m0_in_m1_out)
        m1_early_avg_rr = sum(r['rr'] for r in m0_in_m1_out) / len(m0_in_m1_out)
        print(f"\n--- M1 EARLY WARNING EVALUATION ---")
        print(f"  Cases where M1 warned but M0 didn't: {len(m0_in_m1_out)}")
        print(f"  Actual loss rate in these cases: {m1_early_correct*100:.1f}%")
        print(f"  Avg RR in these cases: {m1_early_avg_rr:.2f}")
        
        early_detection_value = m1_early_correct > 0.3  # More than 30% were actual losses
    else:
        m1_early_correct = 0
        early_detection_value = False
        print(f"\n--- M1 EARLY WARNING EVALUATION ---")
        print(f"  No cases where M1 warned earlier than M0")
    
    # Check false positive: When M1 says safe but M0 says danger
    if m0_out_m1_in:
        m1_fp_rate = sum(1 for r in m0_out_m1_in if r['is_loss']) / len(m0_out_m1_in)
        print(f"\n--- M1 FALSE SAFETY EVALUATION ---")
        print(f"  Cases where M1 said safe but M0 warned: {len(m0_out_m1_in)}")
        print(f"  Actual loss rate in these cases: {m1_fp_rate*100:.1f}%")
        
        no_fp_increase = m1_fp_rate < 0.5  # Less than 50% were actual losses
    else:
        m1_fp_rate = 0
        no_fp_increase = True
        print(f"\n--- M1 FALSE SAFETY EVALUATION ---")
        print(f"  No cases where M1 was more permissive than M0")
    
    passed = early_detection_value and no_fp_increase
    
    print(f"\n--- VERDICT ---")
    print(f"  Early detection value: {early_detection_value}")
    print(f"  No FP increase: {no_fp_increase}")
    
    if passed:
        print(f"\n  ✅ TEST N0-A PASSED")
        print(f"     Coordinate-log provides early detection value")
    else:
        print(f"\n  ❌ TEST N0-A FAILED")
        print(f"     Coordinate-log does NOT provide additional early detection")
    
    return {
        'test': 'N0-A_EARLY_DETECTION',
        'passed': passed,
        'both_in': len(both_in),
        'both_out': len(both_out),
        'm0_in_m1_out': len(m0_in_m1_out),
        'm0_out_m1_in': len(m0_out_m1_in),
        'm1_early_correct_rate': m1_early_correct if m0_in_m1_out else None,
        'm1_fp_rate': m1_fp_rate if m0_out_m1_in else None,
        'early_detection_value': early_detection_value,
        'no_fp_increase': no_fp_increase
    }


# =============================================================================
# TEST N0-B: FALSE POSITIVE REDUCTION TEST
# =============================================================================

def run_test_n0_b(signals: List[Dict]) -> Dict:
    """
    Test N0-B: False Positive Reduction Test
    
    Question: Can M1 reduce false positives from M0's OUT classification?
    
    Definition of FP:
    - M0 says OUT (dangerous)
    - But actual outcome was NOT a loss (RR >= 1.0)
    
    Method:
    - Among M0's OUT classifications, find FP cases
    - Check if M1 coordinates can separate these FP cases
    
    PASS Criteria:
    - FP reduction observed
    - TP (true dangerous OUT) maintained
    """
    print("\n" + "="*60)
    print("TEST N0-B: FALSE POSITIVE REDUCTION")
    print("="*60)
    print("\nQuestion: Can coordinate-log reduce false OUT warnings?")
    
    F_THRESHOLD = 1.3
    force_qualified = [s for s in signals 
                       if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= F_THRESHOLD]
    
    # Get all M0 OUT cases
    m0_out_cases = []
    for signal in force_qualified:
        m0_class, _ = m0_classify(signal)
        if m0_class == "STORM_OUT":
            rr, is_loss = simulate_outcome(signal, WindmillState.OFF)
            m0_out_cases.append({
                'signal': signal,
                'rr': rr,
                'is_loss': is_loss,
                'coords': coordinatize_signal(signal)
            })
    
    if not m0_out_cases:
        print("\n  No M0 OUT cases to analyze")
        return {
            'test': 'N0-B_FP_REDUCTION',
            'passed': False,
            'reason': 'No M0 OUT cases'
        }
    
    # Separate TP (true dangerous) and FP (false alarm)
    tp_cases = [c for c in m0_out_cases if c['is_loss']]
    fp_cases = [c for c in m0_out_cases if not c['is_loss']]
    
    print(f"\n--- M0 OUT ANALYSIS ---")
    print(f"  Total M0 OUT: {len(m0_out_cases)}")
    print(f"  True Positive (actual loss): {len(tp_cases)}")
    print(f"  False Positive (no loss): {len(fp_cases)}")
    print(f"  Original FP rate: {len(fp_cases)/len(m0_out_cases)*100:.1f}%")
    
    if not fp_cases:
        print("\n  No false positives to reduce")
        return {
            'test': 'N0-B_FP_REDUCTION',
            'passed': True,
            'reason': 'No FP to reduce - M0 already perfect',
            'original_fp_rate': 0
        }
    
    # Check if M1 can separate FP from TP using PRE-FIXED rule
    # Rule: Among M0 OUT, if M1 says IN, was it really less dangerous?
    
    m1_reclassify_in = []  # M0=OUT but M1 would say IN
    m1_keep_out = []       # Both M0 and M1 say OUT
    
    for case in m0_out_cases:
        m1_class, _ = m1_classify(case['signal'])
        if m1_class == "STORM_IN":
            m1_reclassify_in.append(case)
        else:
            m1_keep_out.append(case)
    
    print(f"\n--- M1 RECLASSIFICATION ---")
    print(f"  M1 would reclassify as IN: {len(m1_reclassify_in)}")
    print(f"  M1 would keep as OUT: {len(m1_keep_out)}")
    
    # Evaluate reclassification quality
    if m1_reclassify_in:
        reclass_loss_rate = sum(1 for c in m1_reclassify_in if c['is_loss']) / len(m1_reclassify_in)
        reclass_avg_rr = sum(c['rr'] for c in m1_reclassify_in) / len(m1_reclassify_in)
        print(f"\n  Among reclassified (M0=OUT→M1=IN):")
        print(f"    Loss rate: {reclass_loss_rate*100:.1f}%")
        print(f"    Avg RR: {reclass_avg_rr:.2f}")
    else:
        reclass_loss_rate = None
        reclass_avg_rr = None
    
    if m1_keep_out:
        keep_loss_rate = sum(1 for c in m1_keep_out if c['is_loss']) / len(m1_keep_out)
        keep_avg_rr = sum(c['rr'] for c in m1_keep_out) / len(m1_keep_out)
        print(f"\n  Among kept OUT (M0=OUT, M1=OUT):")
        print(f"    Loss rate: {keep_loss_rate*100:.1f}%")
        print(f"    Avg RR: {keep_avg_rr:.2f}")
    else:
        keep_loss_rate = None
        keep_avg_rr = None
    
    # PASS criteria:
    # 1. Reclassified cases have lower loss rate than original OUT
    # 2. Kept OUT cases have higher loss rate (concentrated danger)
    original_loss_rate = len(tp_cases) / len(m0_out_cases)
    
    fp_reduced = (m1_reclassify_in and reclass_loss_rate is not None and 
                  reclass_loss_rate < original_loss_rate * 0.8)
    tp_maintained = (m1_keep_out and keep_loss_rate is not None and 
                     keep_loss_rate >= original_loss_rate)
    
    passed = fp_reduced and tp_maintained
    
    print(f"\n--- VERDICT ---")
    print(f"  Original loss rate in OUT: {original_loss_rate*100:.1f}%")
    print(f"  FP reduced (reclass lower): {fp_reduced}")
    print(f"  TP maintained (kept higher): {tp_maintained}")
    
    if passed:
        print(f"\n  ✅ TEST N0-B PASSED")
        print(f"     Coordinate-log provides FP reduction value")
    else:
        print(f"\n  ❌ TEST N0-B FAILED")
        print(f"     Coordinate-log does NOT provide FP reduction")
    
    return {
        'test': 'N0-B_FP_REDUCTION',
        'passed': passed,
        'total_m0_out': len(m0_out_cases),
        'tp_count': len(tp_cases),
        'fp_count': len(fp_cases),
        'original_loss_rate': original_loss_rate,
        'm1_reclassify_count': len(m1_reclassify_in),
        'm1_keep_out_count': len(m1_keep_out),
        'reclass_loss_rate': reclass_loss_rate,
        'keep_loss_rate': keep_loss_rate,
        'fp_reduced': fp_reduced,
        'tp_maintained': tp_maintained
    }


# =============================================================================
# INTERPRETATION LOCK CHECK
# =============================================================================

def check_interpretation_lock() -> Dict:
    """
    Q2: Does coordinate-ization create forbidden temptations?
    
    FORBIDDEN STATEMENTS (if any appear in documentation, FAIL):
    - "x₂ is the core"
    - "In this coordinate space, the distance..."
    - "The optimal boundary is..."
    
    This is a documentation/design check, not a code check.
    """
    print("\n" + "="*60)
    print("INTERPRETATION LOCK CHECK")
    print("="*60)
    
    forbidden_patterns = [
        "is the core",
        "coordinate space, the distance",
        "optimal boundary",
        "center estimation",
        "axis interpretation",
        "clustering",
    ]
    
    print("\n  FORBIDDEN patterns in any Phase N documentation:")
    for pattern in forbidden_patterns:
        print(f"    ❌ '{pattern}'")
    
    print("\n  ALLOWED conclusion format only:")
    print("    'The coordinate-ized observation log showed/did not show")
    print("     additional value in (early detection / FP reduction)")
    print("     compared to the existing Storm-IN/OUT meter.'")
    
    print("\n  ⚠️ This check must be verified manually in documentation")
    
    return {
        'check': 'INTERPRETATION_LOCK',
        'forbidden_patterns': forbidden_patterns,
        'status': 'REQUIRES_MANUAL_REVIEW'
    }


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_phase_n0():
    """Run all Phase N-0 tests."""
    print("="*70)
    print("PHASE N-0: COORDINATE-IZATION FEASIBILITY TEST")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nPurpose: Evaluate if multi-dimensional force can be expressed")
    print("         as continuous coordinates WITHOUT violating prohibitions")
    print("="*70)
    
    signals = load_signals()
    print(f"\nLoaded {len(signals)} signals for testing")
    
    # Run tests
    result_a = run_test_n0_a(signals)
    result_b = run_test_n0_b(signals)
    lock_check = check_interpretation_lock()
    
    # Determine overall result
    # Note: EITHER A OR B passing is sufficient for coordinate-ization to have value
    has_value = result_a['passed'] or result_b['passed']
    
    print("\n" + "="*70)
    print("PHASE N-0 SUMMARY")
    print("="*70)
    print(f"  Test N0-A (Early Detection): {'✅ PASS' if result_a['passed'] else '❌ FAIL'}")
    print(f"  Test N0-B (FP Reduction):    {'✅ PASS' if result_b['passed'] else '❌ FAIL'}")
    print(f"  Interpretation Lock:         ⚠️ MANUAL REVIEW REQUIRED")
    
    if has_value:
        print(f"\n  🎯 COORDINATE-IZATION SHOWS VALUE")
        if result_a['passed'] and result_b['passed']:
            value_type = "BOTH early detection AND FP reduction"
        elif result_a['passed']:
            value_type = "early detection ONLY"
        else:
            value_type = "FP reduction ONLY"
        print(f"     Value type: {value_type}")
        print(f"\n  ALLOWED CONCLUSION:")
        print(f"  'The coordinate-ized observation log showed additional value in")
        print(f"   {value_type} compared to the existing Storm-IN/OUT meter.'")
    else:
        print(f"\n  ⚠️ COORDINATE-IZATION SHOWS NO ADDITIONAL VALUE")
        print(f"     The existing Storm-IN/OUT meter is sufficient.")
        print(f"\n  ALLOWED CONCLUSION:")
        print(f"  'The coordinate-ized observation log did not show additional value")
        print(f"   compared to the existing Storm-IN/OUT meter.'")
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'phase': 'N-0',
        'test_n0_a': result_a,
        'test_n0_b': result_b,
        'interpretation_lock': lock_check,
        'overall_has_value': has_value,
        'value_type': value_type if has_value else None
    }
    
    output_path = 'v7-grammar-system/analysis/phase_n/n0_results.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return results


if __name__ == "__main__":
    run_phase_n0()
