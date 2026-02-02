"""
DC_LOW Necessity Test (세계 강제성 테스트)
==========================================

Experiment ID: DC_LOW_NECESSITY_V1
One-liner: "DC_LOW는 반드시 존재할 수밖에 없는 자리인가?"

Question:
비가역 + Storm-IN 세계에서
DC_LOW라는 자리는
다른 조건이 무너져도
여전히 덜 위험한가?

Method:
- DC_LOW 단독 고정
- 다른 축 하나씩 붕괴시키기
  1. Force 무시 (1.0 이상 전부 허용)
  2. τ 무시 (τ 조건 제거)
  3. Frame 무시 (dir_count 조건 제거)
  4. VOL 무시 (레짐 구분 없이)
- 각 붕괴 상태에서 DC_LOW vs DC_MID/HIGH 차이 유지되는지 확인

Verdict:
- 모든 붕괴에서 차이 유지 → DC_LOW는 세계가 강제한 자리
- 특정 붕괴에서 차이 사라짐 → DC_LOW는 해당 조건에 의존
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import (
    load_signals,
    classify_storm_coordinate,
    estimate_tau,
    estimate_dir_count,
    WindmillState,
    simulate_outcome
)


def get_loss_rate(signals: List[Dict], dc_filter: str) -> Tuple[float, int]:
    """Get loss rate for DC category in Storm-IN"""
    losses = []
    for s in signals:
        if classify_storm_coordinate(s) != "STORM_IN":
            continue
        
        dc = s.get('dc_pre', 0.5)
        if dc_filter == 'LOW' and dc > 0.2:
            continue
        if dc_filter == 'HIGH' and dc < 0.8:
            continue
        if dc_filter == 'MID' and (dc <= 0.2 or dc >= 0.8):
            continue
        if dc_filter == 'NOT_LOW' and dc <= 0.2:
            continue
        
        _, is_loss = simulate_outcome(s, WindmillState.ON)
        losses.append(is_loss)
    
    if not losses:
        return 0, 0
    return sum(losses) / len(losses), len(losses)


def run_necessity_test():
    """DC_LOW Necessity Test"""
    print("="*70)
    print("DC_LOW NECESSITY TEST (세계 강제성 테스트)")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nQuestion: DC_LOW는 반드시 존재할 수밖에 없는 자리인가?")
    print("-"*70)
    
    signals = load_signals()
    print(f"\nTotal signals: {len(signals)}")
    
    results = {}
    
    # ============================================================
    # BASELINE: Current condition (Force >= 1.3)
    # ============================================================
    print("\n" + "="*70)
    print("BASELINE: Force >= 1.3 (현재 조건)")
    print("="*70)
    
    baseline = [s for s in signals 
                if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.3]
    
    low_loss, low_n = get_loss_rate(baseline, 'LOW')
    not_low_loss, not_low_n = get_loss_rate(baseline, 'NOT_LOW')
    diff = not_low_loss - low_loss
    
    print(f"DC_LOW loss:     {low_loss*100:.1f}% (N={low_n})")
    print(f"DC_NOT_LOW loss: {not_low_loss*100:.1f}% (N={not_low_n})")
    print(f"Difference: {diff*100:.1f}pp")
    
    results['baseline'] = {
        'condition': 'Force >= 1.3',
        'dc_low_loss': low_loss,
        'dc_not_low_loss': not_low_loss,
        'diff_pp': diff * 100,
        'n_low': low_n,
        'n_not_low': not_low_n
    }
    
    # ============================================================
    # COLLAPSE 1: Force 무시 (1.0 이상 전부)
    # ============================================================
    print("\n" + "="*70)
    print("COLLAPSE 1: Force 무시 (>= 1.0)")
    print("="*70)
    
    collapse1 = [s for s in signals 
                 if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.0]
    
    low_loss, low_n = get_loss_rate(collapse1, 'LOW')
    not_low_loss, not_low_n = get_loss_rate(collapse1, 'NOT_LOW')
    diff = not_low_loss - low_loss
    
    print(f"DC_LOW loss:     {low_loss*100:.1f}% (N={low_n})")
    print(f"DC_NOT_LOW loss: {not_low_loss*100:.1f}% (N={not_low_n})")
    print(f"Difference: {diff*100:.1f}pp")
    survived = diff >= 0.10
    print(f"Survived (diff >= 10pp): {survived}")
    
    results['collapse_force'] = {
        'condition': 'Force >= 1.0 (lowered)',
        'dc_low_loss': low_loss,
        'dc_not_low_loss': not_low_loss,
        'diff_pp': diff * 100,
        'survived': survived
    }
    
    # ============================================================
    # COLLAPSE 2: τ 무시 (τ 조건 없이 Storm-IN만)
    # ============================================================
    print("\n" + "="*70)
    print("COLLAPSE 2: τ 무시 (Storm-IN 조건만 사용)")
    print("="*70)
    
    # Storm-IN은 이미 τ를 포함하므로, 여기서는 τ 없이 재정의
    def is_storm_in_no_tau(s):
        """Storm-IN without τ requirement"""
        force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
        return force >= 1.3  # Only force, no τ
    
    collapse2_losses_low = []
    collapse2_losses_not_low = []
    
    for s in baseline:  # Use baseline (Force >= 1.3)
        dc = s.get('dc_pre', 0.5)
        _, is_loss = simulate_outcome(s, WindmillState.ON)
        
        if dc <= 0.2:
            collapse2_losses_low.append(is_loss)
        else:
            collapse2_losses_not_low.append(is_loss)
    
    low_loss = sum(collapse2_losses_low) / len(collapse2_losses_low) if collapse2_losses_low else 0
    not_low_loss = sum(collapse2_losses_not_low) / len(collapse2_losses_not_low) if collapse2_losses_not_low else 0
    diff = not_low_loss - low_loss
    
    print(f"DC_LOW loss:     {low_loss*100:.1f}% (N={len(collapse2_losses_low)})")
    print(f"DC_NOT_LOW loss: {not_low_loss*100:.1f}% (N={len(collapse2_losses_not_low)})")
    print(f"Difference: {diff*100:.1f}pp")
    survived = diff >= 0.10
    print(f"Survived (diff >= 10pp): {survived}")
    
    results['collapse_tau'] = {
        'condition': 'τ ignored (Force only)',
        'dc_low_loss': low_loss,
        'dc_not_low_loss': not_low_loss,
        'diff_pp': diff * 100,
        'survived': survived
    }
    
    # ============================================================
    # COLLAPSE 3: Frame 무시 (dir_count 조건 제거)
    # ============================================================
    print("\n" + "="*70)
    print("COLLAPSE 3: Frame 무시 (dir_count 무시)")
    print("="*70)
    
    # Already collapsed in baseline since we don't filter by frame
    # Just confirming the same result
    
    low_loss, low_n = get_loss_rate(baseline, 'LOW')
    not_low_loss, not_low_n = get_loss_rate(baseline, 'NOT_LOW')
    diff = not_low_loss - low_loss
    
    print(f"DC_LOW loss:     {low_loss*100:.1f}% (N={low_n})")
    print(f"DC_NOT_LOW loss: {not_low_loss*100:.1f}% (N={not_low_n})")
    print(f"Difference: {diff*100:.1f}pp")
    survived = diff >= 0.10
    print(f"Survived (diff >= 10pp): {survived}")
    
    results['collapse_frame'] = {
        'condition': 'Frame ignored',
        'dc_low_loss': low_loss,
        'dc_not_low_loss': not_low_loss,
        'diff_pp': diff * 100,
        'survived': survived
    }
    
    # ============================================================
    # COLLAPSE 4: VOL 무시 (레짐 구분 없이)
    # ============================================================
    print("\n" + "="*70)
    print("COLLAPSE 4: VOL 무시 (Force 레벨 무관)")
    print("="*70)
    
    # Already VOL-agnostic in baseline
    # Split by force level to verify
    
    low_force = [s for s in baseline 
                 if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) < 1.5]
    high_force = [s for s in baseline 
                  if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.5]
    
    # Low force regime
    lf_low_loss, lf_low_n = get_loss_rate(low_force, 'LOW')
    lf_not_low_loss, lf_not_low_n = get_loss_rate(low_force, 'NOT_LOW')
    lf_diff = lf_not_low_loss - lf_low_loss
    
    # High force regime
    hf_low_loss, hf_low_n = get_loss_rate(high_force, 'LOW')
    hf_not_low_loss, hf_not_low_n = get_loss_rate(high_force, 'NOT_LOW')
    hf_diff = hf_not_low_loss - hf_low_loss
    
    print("Low Force (<1.5):")
    print(f"  DC_LOW: {lf_low_loss*100:.1f}% vs NOT_LOW: {lf_not_low_loss*100:.1f}% → diff={lf_diff*100:.1f}pp")
    print("High Force (>=1.5):")
    print(f"  DC_LOW: {hf_low_loss*100:.1f}% vs NOT_LOW: {hf_not_low_loss*100:.1f}% → diff={hf_diff*100:.1f}pp")
    
    survived = lf_diff >= 0.10 and hf_diff >= 0.10
    print(f"Both regimes survived: {survived}")
    
    results['collapse_vol'] = {
        'condition': 'VOL regime ignored',
        'low_force_diff_pp': lf_diff * 100,
        'high_force_diff_pp': hf_diff * 100,
        'survived': survived
    }
    
    # ============================================================
    # COLLAPSE 5: 전체 붕괴 (Force >= 1.0만)
    # ============================================================
    print("\n" + "="*70)
    print("COLLAPSE 5: 전체 붕괴 (Force >= 1.0만, 나머지 전부 무시)")
    print("="*70)
    
    total_collapse = [s for s in signals 
                      if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.0]
    
    tc_low_losses = []
    tc_not_low_losses = []
    
    for s in total_collapse:
        dc = s.get('dc_pre', 0.5)
        _, is_loss = simulate_outcome(s, WindmillState.ON)
        
        if dc <= 0.2:
            tc_low_losses.append(is_loss)
        else:
            tc_not_low_losses.append(is_loss)
    
    low_loss = sum(tc_low_losses) / len(tc_low_losses) if tc_low_losses else 0
    not_low_loss = sum(tc_not_low_losses) / len(tc_not_low_losses) if tc_not_low_losses else 0
    diff = not_low_loss - low_loss
    
    print(f"DC_LOW loss:     {low_loss*100:.1f}% (N={len(tc_low_losses)})")
    print(f"DC_NOT_LOW loss: {not_low_loss*100:.1f}% (N={len(tc_not_low_losses)})")
    print(f"Difference: {diff*100:.1f}pp")
    survived = diff >= 0.10
    print(f"Survived (diff >= 10pp): {survived}")
    
    results['collapse_total'] = {
        'condition': 'Total collapse (Force >= 1.0 only)',
        'dc_low_loss': low_loss,
        'dc_not_low_loss': not_low_loss,
        'diff_pp': diff * 100,
        'survived': survived
    }
    
    # ============================================================
    # FINAL VERDICT
    # ============================================================
    print("\n" + "="*70)
    print("FINAL VERDICT")
    print("="*70)
    
    collapse_results = [
        ('Force 무시', results['collapse_force']['survived']),
        ('τ 무시', results['collapse_tau']['survived']),
        ('Frame 무시', results['collapse_frame']['survived']),
        ('VOL 무시', results['collapse_vol']['survived']),
        ('전체 붕괴', results['collapse_total']['survived'])
    ]
    
    survived_count = sum(1 for _, s in collapse_results if s)
    
    print("\nCollapse Test Results:")
    for name, survived in collapse_results:
        status = "✅ SURVIVED" if survived else "❌ COLLAPSED"
        print(f"  {name}: {status}")
    
    print(f"\nSurvival Score: {survived_count}/5")
    
    if survived_count == 5:
        verdict = "WORLD_FORCED"
        interpretation = """
DC_LOW는 세계가 강제한 자리다.
다른 조건이 모두 무너져도
DC_LOW의 안전성은 유지된다.
→ WIND-2 설계 허용
"""
    elif survived_count >= 3:
        verdict = "CONDITIONALLY_FORCED"
        interpretation = """
DC_LOW는 대부분의 붕괴에서 살아남았다.
일부 조건에 의존하지만 구조적 강건함이 있다.
→ 조건부 WIND-2 허용
"""
    else:
        verdict = "NOT_FORCED"
        interpretation = """
DC_LOW는 다른 조건에 의존한다.
세계가 강제한 자리가 아니다.
→ WIND-2 설계 금지
"""
    
    print(f"\nVerdict: {verdict}")
    print(interpretation)
    
    results['verdict'] = verdict
    results['survival_score'] = survived_count
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'DC_LOW_NECESSITY_V1',
        'question': 'DC_LOW는 반드시 존재할 수밖에 없는 자리인가?',
        'tests': results,
        'verdict': verdict,
        'survival_score': survived_count
    }
    
    output_path = 'v7-grammar-system/analysis/windmill/dc_low_necessity_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_necessity_test()
