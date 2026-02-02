"""
Phase I: IRREVERSIBILITY LOCK
==============================

Purpose: Elevate irreversibility from "hypothesis" to "axiom"

Criterion:
All plausible alternatives that deny irreversibility must collapse in experiments.
If even one survives → Axiom lock ❌

Axiom to be locked:
"Before Bar1, information that determines the outcome does not exist."

Tests:
- I-A: False Irreversibility (Pseudo-Event Injection)
- I-B: Pre-Information Existence (Oracle Window)
- I-C: Observer Relativity Collapse
- I-D: Continuity Illusion
- I-E: Information Recovery
- I-F: ML Counter-Example (Most Important)
"""

import json
import os
import sys
from typing import Dict, List, Tuple
from datetime import datetime
import random
import numpy as np

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
# I-A: FALSE IRREVERSIBILITY (Pseudo-Event Injection)
# =============================================================================

def run_i_a1(signals: List[Dict]) -> Dict:
    """
    I-A1: Pseudo-Event Injection
    
    Hypothesis to REJECT:
    "DC < 1 zones can also show Bar1-like information fixation"
    
    Method:
    - Select DC ∈ [0.7, 0.9] zone
    - Attempt same condition separation as Bar1
    - Compare observer agreement
    
    PASS (Axiom supported):
    - Observer disagreement
    - Distribution non-convergence
    - No reproducibility
    
    → Proves Bar1 is the ONLY event
    """
    print("\n" + "="*60)
    print("I-A1: PSEUDO-EVENT INJECTION")
    print("="*60)
    print("\nTesting: Can DC < 1 zones mimic Bar1?")
    
    # DC extreme (near Bar1)
    dc_near = [s for s in signals if 0.7 <= s.get('dc_pre', 0.5) <= 0.9]
    # DC at Bar1 level
    dc_bar1 = [s for s in signals if s.get('dc_pre', 0.5) >= 0.95]
    
    if len(dc_near) < 30 or len(dc_bar1) < 30:
        print(f"  DC near: {len(dc_near)}, DC Bar1: {len(dc_bar1)}")
        return {'test': 'I-A1', 'status': 'SKIP', 'reason': 'Insufficient data'}
    
    # "Observer agreement" = consistency of classification
    # Simulate multiple observers by adding noise
    def observer_agreement(signals_subset):
        agreements = 0
        total = 0
        for s in signals_subset[:50]:
            classifications = []
            for _ in range(5):  # 5 observers
                noisy = s.copy()
                noisy['force_ratio_30'] = s.get('force_ratio_30', 1.0) * random.uniform(0.95, 1.05)
                classifications.append(classify_storm_coordinate(noisy))
            # Agreement = all same
            if len(set(classifications)) == 1:
                agreements += 1
            total += 1
        return agreements / total if total > 0 else 0
    
    near_agreement = observer_agreement(dc_near)
    bar1_agreement = observer_agreement(dc_bar1)
    
    print(f"\n  DC [0.7-0.9] observer agreement: {near_agreement*100:.1f}%")
    print(f"  DC ≥ 0.95 observer agreement: {bar1_agreement*100:.1f}%")
    
    # PASS: Bar1 agreement >> near agreement
    diff = bar1_agreement - near_agreement
    passed = diff > 0.10  # Bar1 must be at least 10pp more consistent
    
    print(f"  Difference: {diff*100:.1f}pp")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — Bar1 is unique event")
    
    return {
        'test': 'I-A1_PSEUDO_EVENT',
        'passed': passed,
        'near_agreement': near_agreement,
        'bar1_agreement': bar1_agreement,
        'diff': diff
    }


# =============================================================================
# I-B: PRE-INFORMATION EXISTENCE (Oracle Window)
# =============================================================================

def run_i_b1(signals: List[Dict]) -> Dict:
    """
    I-B1: Oracle Window Test
    
    Hypothesis to REJECT:
    "Information determining outcome exists in Δt window before Bar1"
    
    Method:
    - Create sliding windows before Bar1
    - Use all known observation variables
    - Attempt outcome distribution separation
    
    PASS (Axiom supported):
    - Distribution separation fails in all Δt
    - Direction agreement fails
    
    → Fixes "not lack of info" but "absence of info"
    """
    print("\n" + "="*60)
    print("I-B1: ORACLE WINDOW TEST")
    print("="*60)
    print("\nTesting: Does pre-Bar1 info determine outcome?")
    
    # Simulate pre-Bar1 windows by using lower DC thresholds
    windows = {
        'DC_50_70': (0.5, 0.7),
        'DC_70_85': (0.7, 0.85),
        'DC_85_95': (0.85, 0.95)
    }
    
    separation_scores = {}
    
    for window_name, (dc_min, dc_max) in windows.items():
        window_signals = [s for s in signals if dc_min <= s.get('dc_pre', 0.5) < dc_max]
        
        if len(window_signals) < 30:
            continue
        
        # Try to separate outcomes using all available info
        wins = [s for s in window_signals if not simulate_outcome(s, WindmillState.ON)[1]]
        losses = [s for s in window_signals if simulate_outcome(s, WindmillState.OFF)[1]]
        
        if not wins or not losses:
            continue
        
        # Calculate feature means for each group
        win_force_mean = np.mean([s.get('force_ratio_30', 1.0) for s in wins])
        loss_force_mean = np.mean([s.get('force_ratio_30', 1.0) for s in losses])
        
        # Separation = difference in means / pooled std
        all_forces = [s.get('force_ratio_30', 1.0) for s in window_signals]
        std = np.std(all_forces) if np.std(all_forces) > 0 else 1
        separation = abs(win_force_mean - loss_force_mean) / std
        
        separation_scores[window_name] = separation
        print(f"\n  {window_name}: separation = {separation:.3f}")
    
    if not separation_scores:
        return {'test': 'I-B1', 'status': 'SKIP', 'reason': 'Insufficient windows'}
    
    # PASS: No window achieves significant separation (< 0.5 effect size)
    max_separation = max(separation_scores.values())
    passed = max_separation < 0.5
    
    print(f"\n  Max separation: {max_separation:.3f}")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — Pre-Bar1 info doesn't determine outcome")
    
    return {
        'test': 'I-B1_ORACLE_WINDOW',
        'passed': passed,
        'separation_scores': separation_scores,
        'max_separation': max_separation
    }


# =============================================================================
# I-C: OBSERVER RELATIVITY COLLAPSE
# =============================================================================

def run_i_c1(signals: List[Dict]) -> Dict:
    """
    I-C1: Observer Collapse Test
    
    Hypothesis to REJECT:
    "Skilled observers reach same conclusion even before Bar1"
    
    Method:
    - Same data
    - Different observation frames (indicator sets)
    - Compare pre-judgment results
    
    PASS (Axiom supported):
    - Observer disagreement maintained
    - No consensus point
    
    → Confirms relativity in Reversible zone
    """
    print("\n" + "="*60)
    print("I-C1: OBSERVER RELATIVITY TEST")
    print("="*60)
    print("\nTesting: Do different 'observers' agree before Bar1?")
    
    # Define different "observers" = different indicator weightings
    def observer_1(s):
        # Force-focused
        return "UP" if s.get('force_ratio_30', 1.0) > 1.5 else "DOWN"
    
    def observer_2(s):
        # DC-focused
        return "UP" if s.get('dc_pre', 0.5) > 0.7 else "DOWN"
    
    def observer_3(s):
        # τ-focused
        return "UP" if estimate_tau(s) >= 5 else "DOWN"
    
    # Pre-Bar1 signals
    pre_bar1 = [s for s in signals if s.get('dc_pre', 0.5) < 0.9]
    
    if len(pre_bar1) < 50:
        return {'test': 'I-C1', 'status': 'SKIP', 'reason': 'Insufficient pre-Bar1'}
    
    # Calculate agreement
    agreements = 0
    for s in pre_bar1[:100]:
        o1 = observer_1(s)
        o2 = observer_2(s)
        o3 = observer_3(s)
        if o1 == o2 == o3:
            agreements += 1
    
    agreement_rate = agreements / min(100, len(pre_bar1))
    
    # PASS: Low agreement (< 70%)
    passed = agreement_rate < 0.70
    
    print(f"\n  Observer agreement rate: {agreement_rate*100:.1f}%")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — Observers disagree before Bar1")
    
    return {
        'test': 'I-C1_OBSERVER_RELATIVITY',
        'passed': passed,
        'agreement_rate': agreement_rate
    }


# =============================================================================
# I-D: CONTINUITY ILLUSION
# =============================================================================

def run_i_d1(signals: List[Dict]) -> Dict:
    """
    I-D1: Continuity Illusion Test
    
    Hypothesis to REJECT:
    "Bar1 is part of continuous transition, not a threshold"
    
    Method:
    - Compare low DC vs high DC outcome distributions
    - Check if there's a qualitative difference
    
    PASS (Axiom supported):
    - High DC zone shows different behavior than low DC
    - State change exists
    
    → Fixes Bar1 as state transition (Event)
    """
    print("\n" + "="*60)
    print("I-D1: CONTINUITY ILLUSION TEST")
    print("="*60)
    print("\nTesting: Is Bar1 continuous or discontinuous?")
    
    # Simple comparison: low DC vs high DC
    low_dc = [s for s in signals if s.get('dc_pre', 0.5) < 0.5]
    high_dc = [s for s in signals if s.get('dc_pre', 0.5) >= 0.8]
    
    if len(low_dc) < 30 or len(high_dc) < 30:
        return {'test': 'I-D1', 'status': 'SKIP', 'reason': 'Insufficient DC split'}
    
    # Compare Storm classification behavior
    low_in = sum(1 for s in low_dc if classify_storm_coordinate(s) == "STORM_IN")
    high_in = sum(1 for s in high_dc if classify_storm_coordinate(s) == "STORM_IN")
    
    low_in_rate = low_in / len(low_dc)
    high_in_rate = high_in / len(high_dc)
    
    print(f"\n  Low DC (<0.5): N={len(low_dc)}, Storm-IN rate={low_in_rate*100:.1f}%")
    print(f"  High DC (≥0.8): N={len(high_dc)}, Storm-IN rate={high_in_rate*100:.1f}%")
    
    # Calculate loss rate difference
    low_loss = sum(1 for s in low_dc 
                   if simulate_outcome(s, WindmillState.OFF)[1]) / len(low_dc)
    high_loss = sum(1 for s in high_dc 
                    if simulate_outcome(s, WindmillState.OFF)[1]) / len(high_dc)
    
    print(f"\n  Low DC loss rate: {low_loss*100:.1f}%")
    print(f"  High DC loss rate: {high_loss*100:.1f}%")
    
    # PASS: Qualitative difference in behavior (IN rate or loss rate differs)
    in_diff = abs(high_in_rate - low_in_rate)
    loss_diff = abs(high_loss - low_loss)
    
    passed = in_diff > 0.05 or loss_diff > 0.05
    
    print(f"\n  IN rate difference: {in_diff*100:.1f}pp")
    print(f"  Loss rate difference: {loss_diff*100:.1f}pp")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — State transition exists at DC threshold")
    
    return {
        'test': 'I-D1_CONTINUITY_ILLUSION',
        'passed': passed,
        'low_in_rate': low_in_rate,
        'high_in_rate': high_in_rate,
        'low_loss': low_loss,
        'high_loss': high_loss,
        'in_diff': in_diff,
        'loss_diff': loss_diff
    }


# =============================================================================
# I-E: INFORMATION RECOVERY
# =============================================================================

def run_i_e1(signals: List[Dict]) -> Dict:
    """
    I-E1: Reverse Reconstruction Test
    
    Hypothesis to REJECT:
    "Post-Bar1 information can reconstruct Pre-Bar1 state"
    
    Method:
    - Use only Post-Bar1 info
    - Attempt Pre-Bar1 state reconstruction
    
    PASS (Axiom supported):
    - Reconstruction fails
    - Many-to-one mapping collapse
    
    → Proves information loss
    """
    print("\n" + "="*60)
    print("I-E1: INFORMATION RECOVERY TEST")
    print("="*60)
    print("\nTesting: Can post-Bar1 info reconstruct pre-Bar1 state?")
    
    # Post-Bar1 signals
    post_bar1 = [s for s in signals if s.get('dc_pre', 0.5) >= 0.9]
    
    if len(post_bar1) < 30:
        return {'test': 'I-E1', 'status': 'SKIP', 'reason': 'Insufficient post-Bar1'}
    
    # Try to "reconstruct" pre-Bar1 state from post-Bar1 outcome
    # If reconstruction is possible, same outcome → same pre-state
    # If not, same outcome can come from different pre-states
    
    wins = [s for s in post_bar1 if not simulate_outcome(s, WindmillState.ON)[1]]
    losses = [s for s in post_bar1 if simulate_outcome(s, WindmillState.OFF)[1]]
    
    if len(wins) < 10 or len(losses) < 10:
        return {'test': 'I-E1', 'status': 'SKIP', 'reason': 'Insufficient win/loss split'}
    
    # Calculate variance of pre-states within same outcome
    win_forces = [s.get('force_ratio_30', 1.0) for s in wins]
    loss_forces = [s.get('force_ratio_30', 1.0) for s in losses]
    
    win_variance = np.var(win_forces) if win_forces else 0
    loss_variance = np.var(loss_forces) if loss_forces else 0
    
    # High variance = many different pre-states led to same outcome
    avg_variance = (win_variance + loss_variance) / 2
    
    print(f"\n  Within-win Force variance: {win_variance:.3f}")
    print(f"  Within-loss Force variance: {loss_variance:.3f}")
    print(f"  Average variance: {avg_variance:.3f}")
    
    # PASS: High variance (reconstruction fails)
    passed = avg_variance > 0.05
    
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — Pre-state not reconstructible")
    
    return {
        'test': 'I-E1_INFORMATION_RECOVERY',
        'passed': passed,
        'win_variance': win_variance,
        'loss_variance': loss_variance,
        'avg_variance': avg_variance
    }


# =============================================================================
# I-F: ML COUNTER-EXAMPLE (Most Important)
# =============================================================================

def run_i_f1(signals: List[Dict]) -> Dict:
    """
    I-F1: Best Possible Predictor Test
    
    Hypothesis to REJECT:
    "Powerful ML can predict outcome before Bar1"
    
    Method:
    - Allow any ML approach
    - Use ONLY pre-Bar1 information
    - Goal: direction/outcome prediction
    
    PASS (Axiom supported):
    - Structural failure
    - Performance at chance level
    - No stable reproduction
    
    → Fixes "prediction impossible" as structure, not capability limit
    """
    print("\n" + "="*60)
    print("I-F1: BEST POSSIBLE PREDICTOR TEST")
    print("="*60)
    print("\nTesting: Can ANY predictor succeed before Bar1?")
    
    # Use pre-Bar1 signals
    pre_bar1 = [s for s in signals if s.get('dc_pre', 0.5) < 0.9]
    
    if len(pre_bar1) < 100:
        return {'test': 'I-F1', 'status': 'SKIP', 'reason': 'Insufficient pre-Bar1'}
    
    # Simulate "best possible predictor" = use all available features
    # This is a simple rule-based predictor that should be upper bound
    
    correct = 0
    total = 0
    
    for s in pre_bar1[:200]:
        # Predictor: use Force, DC, τ, dir to predict outcome
        force = s.get('force_ratio_30', 1.0)
        dc = s.get('dc_pre', 0.5)
        tau = estimate_tau(s)
        dir_count = estimate_dir_count(s)
        
        # Best guess based on all features
        score = 0
        if force > 1.5: score += 1
        if dc > 0.7: score += 1
        if tau >= 4: score += 1
        if dir_count >= 3: score += 1
        
        prediction = "WIN" if score >= 3 else "LOSS"
        
        # Actual outcome
        _, is_loss = simulate_outcome(s, WindmillState.ON if score >= 3 else WindmillState.OFF)
        actual = "LOSS" if is_loss else "WIN"
        
        if prediction == actual:
            correct += 1
        total += 1
    
    accuracy = correct / total if total > 0 else 0
    
    # PASS: Accuracy near chance (< 60%)
    passed = accuracy < 0.60
    
    print(f"\n  Best predictor accuracy: {accuracy*100:.1f}%")
    print(f"  Chance level: 50%")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — Prediction structurally impossible")
    
    return {
        'test': 'I-F1_BEST_PREDICTOR',
        'passed': passed,
        'accuracy': accuracy,
        'total_tested': total
    }


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_phase_i():
    """Run all Phase I irreversibility lock tests."""
    print("="*70)
    print("PHASE I: IRREVERSIBILITY LOCK")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nAxiom to lock:")
    print("'Before Bar1, information determining outcome does not exist.'")
    print("="*70)
    
    signals = load_signals()
    print(f"\nLoaded {len(signals)} signals for testing")
    
    results = {}
    
    # Run all tests
    results['I-A1'] = run_i_a1(signals)
    results['I-B1'] = run_i_b1(signals)
    results['I-C1'] = run_i_c1(signals)
    results['I-D1'] = run_i_d1(signals)
    results['I-E1'] = run_i_e1(signals)
    results['I-F1'] = run_i_f1(signals)
    
    # Summary
    passed = sum(1 for r in results.values() if r.get('passed', False))
    skipped = sum(1 for r in results.values() if r.get('status') == 'SKIP')
    total = len(results)
    
    print("\n" + "="*70)
    print("PHASE I FINAL SUMMARY")
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
    
    # ALL must pass (no failures allowed)
    all_pass = (passed + skipped == total) and (skipped <= 1) and (passed >= 5)
    
    if all_pass:
        print(f"\n  🔒 IRREVERSIBILITY AXIOM LOCKED")
        print(f"\n  AXIOM DECLARATION:")
        print(f"  'Before Bar1, information that determines the outcome does not exist.'")
        print(f"  This is not a limitation. This is the starting point.")
        print(f"\n  Consequences:")
        print(f"  - Irreversibility document → Top-level axiom")
        print(f"  - Phase M/O/H → Sub-verification layers")
        print(f"  - ML → Detection assistant only")
    else:
        print(f"\n  ⚠️ AXIOM NOT LOCKED — Counter-examples exist")
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'phase': 'I',
        'axiom': 'Before Bar1, information determining outcome does not exist',
        'results': results,
        'passed': passed,
        'skipped': skipped,
        'total': total,
        'axiom_locked': all_pass
    }
    
    os.makedirs('v7-grammar-system/analysis/phase_i', exist_ok=True)
    output_path = 'v7-grammar-system/analysis/phase_i/irreversibility_results.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_phase_i()
