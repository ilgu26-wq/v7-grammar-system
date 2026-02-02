"""
Phase J: IRREVERSIBILITY-DRIVEN HYPOTHESIS EXPERIMENTS
=======================================================

NOT Validation. This is GENERATIVE hypothesis testing.

Question: "If irreversibility is true, what structures MUST exist?"

Template:
  If irreversibility is true, then [STRUCTURE] must exist.
  If [STRUCTURE] does not exist, irreversibility is violated.

  PASS = Structure is actually forced by data
  FAIL = Axiom is false or incomplete
"""

import json
import os
import sys
from typing import Dict, List
from datetime import datetime
import numpy as np
from collections import Counter

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
# J-1: STATE DENSITY INEQUALITY
# =============================================================================

def run_j1(signals: List[Dict]) -> Dict:
    """
    J-1: Irreversibility ⇒ State Density Inequality
    
    Hypothesis:
    Post-irreversible-boundary state space CANNOT be uniformly distributed.
    
    Method:
    - State frequency distribution after Bar1
    - Entropy comparison (before/after)
    
    PASS:
    - Concentration into specific states
    - Reverse restoration impossible
    
    → Events tear the state space
    """
    print("\n" + "="*60)
    print("J-1: STATE DENSITY INEQUALITY")
    print("="*60)
    print("\nIf irreversibility ⇒ post-Bar1 states are NOT uniform")
    
    # Split by DC (proxy for Bar1)
    pre_bar1 = [s for s in signals if s.get('dc_pre', 0.5) < 0.7]
    post_bar1 = [s for s in signals if s.get('dc_pre', 0.5) >= 0.9]
    
    if len(pre_bar1) < 50 or len(post_bar1) < 50:
        return {'test': 'J-1', 'status': 'SKIP', 'reason': 'Insufficient data'}
    
    def calculate_state_entropy(sigs):
        states = [classify_storm_coordinate(s) for s in sigs]
        counts = Counter(states)
        total = len(states)
        probs = [c/total for c in counts.values()]
        entropy = -sum(p * np.log2(p) for p in probs if p > 0)
        return entropy, counts
    
    pre_entropy, pre_counts = calculate_state_entropy(pre_bar1)
    post_entropy, post_counts = calculate_state_entropy(post_bar1)
    
    print(f"\n  Pre-Bar1 (DC < 0.7):")
    print(f"    States: {dict(pre_counts)}")
    print(f"    Entropy: {pre_entropy:.3f} bits")
    
    print(f"\n  Post-Bar1 (DC ≥ 0.9):")
    print(f"    States: {dict(post_counts)}")
    print(f"    Entropy: {post_entropy:.3f} bits")
    
    # Also check outcome concentration
    pre_outcomes = [simulate_outcome(s, WindmillState.ON)[1] for s in pre_bar1[:200]]
    post_outcomes = [simulate_outcome(s, WindmillState.ON)[1] for s in post_bar1[:200]]
    
    pre_loss_rate = sum(pre_outcomes) / len(pre_outcomes)
    post_loss_rate = sum(post_outcomes) / len(post_outcomes)
    
    print(f"\n  Outcome concentration:")
    print(f"    Pre-Bar1 loss rate: {pre_loss_rate*100:.1f}%")
    print(f"    Post-Bar1 loss rate: {post_loss_rate*100:.1f}%")
    
    # PASS: Post-Bar1 shows concentration (entropy lower or outcome skewed)
    entropy_drop = pre_entropy - post_entropy
    outcome_concentration = abs(post_loss_rate - 0.5)
    
    passed = entropy_drop > 0 or outcome_concentration > 0.10
    
    print(f"\n  Entropy change: {entropy_drop:+.3f} bits")
    print(f"  Outcome skew from 50%: {outcome_concentration*100:.1f}pp")
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — Events tear state space")
    
    return {
        'test': 'J-1_STATE_DENSITY',
        'passed': passed,
        'pre_entropy': pre_entropy,
        'post_entropy': post_entropy,
        'entropy_drop': entropy_drop,
        'outcome_concentration': outcome_concentration
    }


# =============================================================================
# J-2: BOUNDARY SENSITIVITY
# =============================================================================

def run_j2(signals: List[Dict]) -> Dict:
    """
    J-2: Irreversibility ⇒ Boundary Sensitivity
    
    Hypothesis:
    Near Bar1, micro-changes cause discontinuous outcome changes.
    
    Method:
    - Perturbation near DC ≈ 1
    - Check outcome distribution jump
    
    PASS:
    - Continuous model fails
    - Jump exists
    
    → Critical point (event) is real
    """
    print("\n" + "="*60)
    print("J-2: BOUNDARY SENSITIVITY")
    print("="*60)
    print("\nIf irreversibility ⇒ micro-changes at boundary cause jumps")
    
    # Find signals near boundary
    boundary = [s for s in signals if 0.85 <= s.get('dc_pre', 0.5) <= 0.95]
    
    if len(boundary) < 30:
        return {'test': 'J-2', 'status': 'SKIP', 'reason': 'Insufficient boundary data'}
    
    # Apply micro-perturbations and check if classification jumps
    jump_count = 0
    total_tests = 0
    
    for s in boundary[:100]:
        original_class = classify_storm_coordinate(s)
        
        # Small perturbation
        perturbed = s.copy()
        perturbed['force_ratio_30'] = s.get('force_ratio_30', 1.0) * 1.05
        perturbed_class = classify_storm_coordinate(perturbed)
        
        if original_class != perturbed_class:
            jump_count += 1
        total_tests += 1
    
    jump_rate = jump_count / total_tests if total_tests > 0 else 0
    
    print(f"\n  Boundary signals tested: {total_tests}")
    print(f"  Classification jumps: {jump_count}")
    print(f"  Jump rate: {jump_rate*100:.1f}%")
    
    # Also test outcome sensitivity
    outcome_jumps = 0
    for s in boundary[:100]:
        _, orig_loss = simulate_outcome(s, WindmillState.ON)
        
        perturbed = s.copy()
        perturbed['force_ratio_30'] = s.get('force_ratio_30', 1.0) * 1.05
        _, pert_loss = simulate_outcome(perturbed, WindmillState.ON)
        
        if orig_loss != pert_loss:
            outcome_jumps += 1
    
    outcome_jump_rate = outcome_jumps / min(100, len(boundary))
    
    print(f"  Outcome jumps: {outcome_jumps} ({outcome_jump_rate*100:.1f}%)")
    
    # PASS: Sensitivity exists (jumps > 5%)
    passed = jump_rate > 0.05 or outcome_jump_rate > 0.10
    
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — Critical point is real")
    
    return {
        'test': 'J-2_BOUNDARY_SENSITIVITY',
        'passed': passed,
        'classification_jump_rate': jump_rate,
        'outcome_jump_rate': outcome_jump_rate
    }


# =============================================================================
# J-3: OBSERVER NULLIFICATION
# =============================================================================

def run_j3(signals: List[Dict]) -> Dict:
    """
    J-3: Irreversibility ⇒ Observer Nullification
    
    Hypothesis:
    Before irreversible boundary, NO observation frame can be superior.
    
    Method:
    - Different indicator/frames
    - Pre-Bar1 prediction comparison
    
    PASS:
    - No superior frame
    - Consensus impossible
    
    → Data consequence of relativity
    """
    print("\n" + "="*60)
    print("J-3: OBSERVER NULLIFICATION")
    print("="*60)
    print("\nIf irreversibility ⇒ no frame is superior before Bar1")
    
    pre_bar1 = [s for s in signals if s.get('dc_pre', 0.5) < 0.8]
    
    if len(pre_bar1) < 100:
        return {'test': 'J-3', 'status': 'SKIP', 'reason': 'Insufficient pre-Bar1'}
    
    # Define different "observers" (prediction frames)
    def observer_force(s):
        return "UP" if s.get('force_ratio_30', 1.0) > 1.5 else "DOWN"
    
    def observer_tau(s):
        return "UP" if estimate_tau(s) >= 4 else "DOWN"
    
    def observer_dir(s):
        return "UP" if estimate_dir_count(s) >= 3 else "DOWN"
    
    def observer_combined(s):
        score = sum([
            s.get('force_ratio_30', 1.0) > 1.3,
            estimate_tau(s) >= 4,
            estimate_dir_count(s) >= 3
        ])
        return "UP" if score >= 2 else "DOWN"
    
    observers = {
        'Force': observer_force,
        'τ': observer_tau,
        'dir': observer_dir,
        'Combined': observer_combined
    }
    
    accuracies = {}
    
    for name, obs in observers.items():
        correct = 0
        for s in pre_bar1[:200]:
            prediction = obs(s)
            _, is_loss = simulate_outcome(s, WindmillState.ON)
            actual = "DOWN" if is_loss else "UP"
            if prediction == actual:
                correct += 1
        
        accuracy = correct / min(200, len(pre_bar1))
        accuracies[name] = accuracy
        print(f"  {name} observer: {accuracy*100:.1f}%")
    
    # PASS: All observers near chance (< 60%), no clear winner
    max_accuracy = max(accuracies.values())
    min_accuracy = min(accuracies.values())
    spread = max_accuracy - min_accuracy
    
    print(f"\n  Max accuracy: {max_accuracy*100:.1f}%")
    print(f"  Spread: {spread*100:.1f}pp")
    
    # No superior frame = all < 60% AND spread < 15pp
    passed = max_accuracy < 0.60 and spread < 0.15
    
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — No frame is superior")
    
    return {
        'test': 'J-3_OBSERVER_NULLIFICATION',
        'passed': passed,
        'accuracies': accuracies,
        'max_accuracy': max_accuracy,
        'spread': spread
    }


# =============================================================================
# J-4: PATH EXTINCTION
# =============================================================================

def run_j4(signals: List[Dict]) -> Dict:
    """
    J-4: Irreversibility ⇒ Path Extinction
    
    Hypothesis:
    After event, number of possible paths decreases sharply.
    
    Method:
    - Trajectory diversity comparison before/after Bar1
    
    PASS:
    - Trajectory collapse
    
    → "Extinction of possibilities" demonstrated
    """
    print("\n" + "="*60)
    print("J-4: PATH EXTINCTION")
    print("="*60)
    print("\nIf irreversibility ⇒ possible paths collapse after event")
    
    pre_bar1 = [s for s in signals if s.get('dc_pre', 0.5) < 0.7]
    post_bar1 = [s for s in signals if s.get('dc_pre', 0.5) >= 0.9]
    
    if len(pre_bar1) < 50 or len(post_bar1) < 50:
        return {'test': 'J-4', 'status': 'SKIP', 'reason': 'Insufficient data'}
    
    def calculate_trajectory_diversity(sigs):
        # Represent "trajectory" as (Force bin, τ bin, dir bin, outcome)
        trajectories = []
        for s in sigs[:200]:
            force_bin = int(s.get('force_ratio_30', 1.0) * 2)  # 0.5 bins
            tau_bin = estimate_tau(s) // 2
            dir_bin = estimate_dir_count(s) // 2
            _, is_loss = simulate_outcome(s, WindmillState.ON)
            outcome = 1 if is_loss else 0
            
            trajectories.append((force_bin, tau_bin, dir_bin, outcome))
        
        unique = len(set(trajectories))
        total = len(trajectories)
        diversity = unique / total if total > 0 else 0
        
        return diversity, unique, total
    
    pre_div, pre_unique, pre_total = calculate_trajectory_diversity(pre_bar1)
    post_div, post_unique, post_total = calculate_trajectory_diversity(post_bar1)
    
    print(f"\n  Pre-Bar1:")
    print(f"    Unique trajectories: {pre_unique}/{pre_total}")
    print(f"    Diversity: {pre_div*100:.1f}%")
    
    print(f"\n  Post-Bar1:")
    print(f"    Unique trajectories: {post_unique}/{post_total}")
    print(f"    Diversity: {post_div*100:.1f}%")
    
    diversity_drop = pre_div - post_div
    
    print(f"\n  Diversity drop: {diversity_drop*100:.1f}pp")
    
    # PASS: Diversity decreases after Bar1
    passed = diversity_drop > 0
    
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — Paths collapse after event")
    
    return {
        'test': 'J-4_PATH_EXTINCTION',
        'passed': passed,
        'pre_diversity': pre_div,
        'post_diversity': post_div,
        'diversity_drop': diversity_drop
    }


# =============================================================================
# J-5: INEXPLICABILITY
# =============================================================================

def run_j5(signals: List[Dict]) -> Dict:
    """
    J-5: Irreversibility ⇒ Inexplicability
    
    Hypothesis:
    Post-event data cannot reconstruct causes.
    
    Method:
    - Attempt post-Bar1 → pre-Bar1 classification
    
    PASS:
    - Performance at chance level
    
    → Explanation ≠ Observation
    """
    print("\n" + "="*60)
    print("J-5: INEXPLICABILITY")
    print("="*60)
    print("\nIf irreversibility ⇒ post-event cannot reconstruct pre-event")
    
    post_bar1 = [s for s in signals if s.get('dc_pre', 0.5) >= 0.9]
    
    if len(post_bar1) < 50:
        return {'test': 'J-5', 'status': 'SKIP', 'reason': 'Insufficient post-Bar1'}
    
    # Try to "reconstruct" pre-Bar1 state from post-Bar1 outcome
    # If reconstruction is possible: same outcome → predictable pre-state
    # If not: same outcome from different pre-states
    
    wins = [s for s in post_bar1 if not simulate_outcome(s, WindmillState.ON)[1]]
    losses = [s for s in post_bar1 if simulate_outcome(s, WindmillState.OFF)[1]]
    
    if len(wins) < 20 or len(losses) < 20:
        return {'test': 'J-5', 'status': 'SKIP', 'reason': 'Insufficient win/loss'}
    
    # Attempt to classify pre-state (Force level) from outcome
    # If explanation is possible, wins should have different Force distribution than losses
    
    win_forces = [s.get('force_ratio_30', 1.0) for s in wins]
    loss_forces = [s.get('force_ratio_30', 1.0) for s in losses]
    
    win_mean = np.mean(win_forces)
    loss_mean = np.mean(loss_forces)
    
    pooled_std = np.std(win_forces + loss_forces)
    separation = abs(win_mean - loss_mean) / pooled_std if pooled_std > 0 else 0
    
    print(f"\n  Win Force mean: {win_mean:.3f}")
    print(f"  Loss Force mean: {loss_mean:.3f}")
    print(f"  Separation (effect size): {separation:.3f}")
    
    # PASS: Low separation (< 0.3 = small effect)
    passed = separation < 0.3
    
    print(f"  {'✅ PASS' if passed else '❌ FAIL'} — Explanation ≠ Observation")
    
    return {
        'test': 'J-5_INEXPLICABILITY',
        'passed': passed,
        'win_mean': win_mean,
        'loss_mean': loss_mean,
        'separation': separation
    }


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_phase_j():
    """Run all Phase J generative hypothesis experiments."""
    print("="*70)
    print("PHASE J: IRREVERSIBILITY-DRIVEN HYPOTHESIS EXPERIMENTS")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nNOT Validation. This is GENERATIVE hypothesis testing.")
    print("\nQuestion: 'If irreversibility is true, what MUST exist?'")
    print("="*70)
    
    signals = load_signals()
    print(f"\nLoaded {len(signals)} signals for experiments")
    
    results = {}
    
    results['J-1'] = run_j1(signals)
    results['J-2'] = run_j2(signals)
    results['J-3'] = run_j3(signals)
    results['J-4'] = run_j4(signals)
    results['J-5'] = run_j5(signals)
    
    # Summary
    passed = sum(1 for r in results.values() if r.get('passed', False))
    skipped = sum(1 for r in results.values() if r.get('status') == 'SKIP')
    total = len(results)
    
    print("\n" + "="*70)
    print("PHASE J FINAL SUMMARY")
    print("="*70)
    print("\nGenerative Consequences of Irreversibility:")
    
    for name, result in results.items():
        if result.get('status') == 'SKIP':
            print(f"  {name}: ⏭️ SKIP")
        elif result.get('passed'):
            print(f"  {name}: ✅ FORCED (structure exists)")
        else:
            print(f"  {name}: ❌ NOT FORCED (axiom incomplete?)")
    
    print(f"\n  Structures forced: {passed}/{total}")
    print(f"  Skipped: {skipped}/{total}")
    
    if passed >= 4:
        print(f"\n  🌊 IRREVERSIBILITY GENERATES STRUCTURE")
        print(f"  The axiom produces necessary consequences:")
        for name, result in results.items():
            if result.get('passed'):
                structure = name.split('_', 1)[1] if '_' in name else name
                print(f"    → {structure}")
    else:
        print(f"\n  ⚠️ AXIOM MAY BE INCOMPLETE")
        print(f"  Some structures not forced by data")
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'phase': 'J',
        'type': 'GENERATIVE_HYPOTHESIS',
        'question': 'If irreversibility is true, what MUST exist?',
        'results': results,
        'structures_forced': passed,
        'skipped': skipped,
        'total': total
    }
    
    os.makedirs('v7-grammar-system/analysis/phase_j', exist_ok=True)
    output_path = 'v7-grammar-system/analysis/phase_j/generative_results.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_phase_j()
