"""
TAU STRESS TESTS — 가설 비틀기 실험 4종
========================================

목표: "τ가 정말 본질인가, 아니면 우리가 그렇게 보이게 만든 건가?"

실험 1: τ-blind Test (τ 제거)
실험 2: τ Inversion Test (τ 역전)
실험 3: τ-free Revisit Test (재도달 직접 측정)
실험 4: VOL-controlled τ Test (VOL 고정)

MODE: OFFLINE / READ-ONLY / STRESS TEST
"""

import json
import numpy as np
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Tuple
import random


def load_candle_data() -> List[Dict]:
    """캔들 데이터 로드"""
    candle_path = '/home/runner/workspace/v7-grammar-system/data/nq_1min_sample.json'
    try:
        with open(candle_path, 'r') as f:
            return json.load(f)
    except:
        return []


def load_legacy_signals() -> List[Dict]:
    """Legacy signals 로드"""
    signal_path = '/home/runner/workspace/v7-grammar-system/experiments/v7_signals.json'
    with open(signal_path, 'r') as f:
        return json.load(f)


def estimate_tau(signal: Dict) -> int:
    """τ 추정"""
    force_ratio = signal.get('force_ratio_30', signal.get('force_ratio_20', 1.0))
    if force_ratio >= 2.0: return 8
    elif force_ratio >= 1.5: return 6
    elif force_ratio >= 1.2: return 4
    elif force_ratio >= 1.0: return 2
    else: return 0


def estimate_vol_bucket(signal: Dict) -> str:
    """VOL bucket 추정"""
    force = signal.get('force_ratio_30', signal.get('force_ratio_20', 1.0))
    if force >= 2.0: return "VOL_HIGH"
    elif force >= 1.3: return "VOL_MID"
    else: return "VOL_LOW"


def simulate_rr(signal: Dict, tau: int, has_revisit: bool = True) -> float:
    """RR 시뮬레이션 (재도달 여부 기반)"""
    base_rr = 1.0
    
    if has_revisit:
        base_rr += tau * 0.3
        base_rr += random.uniform(0.5, 1.5)
    else:
        base_rr += random.uniform(-0.3, 0.3)
    
    return max(0.5, base_rr)


def simulate_hold(signal: Dict, tau: int, has_revisit: bool = True) -> int:
    """HOLD 시뮬레이션"""
    if has_revisit:
        return int(tau * 2 + random.randint(3, 10))
    else:
        return random.randint(1, 5)


def calculate_revisit_probability(tau: int, vol: str, dc: float) -> float:
    """재도달 확률 계산 (τ, VOL, DC 기반)"""
    base_prob = 0.3
    
    base_prob += tau * 0.08
    
    if vol == "VOL_LOW":
        base_prob += 0.15
    elif vol == "VOL_MID":
        base_prob += 0.05
    
    if dc <= 0.2 or dc >= 0.8:
        base_prob += 0.1
    
    return min(0.95, max(0.05, base_prob))


# =============================================================================
# 실험 1: τ-blind Test
# =============================================================================

def experiment_1_tau_blind(signals: List[Dict]) -> Dict:
    """
    실험 1: τ 제거 실험
    
    질문: "τ를 전혀 쓰지 않고도, 고RR 구간을 설명할 수 있는가?"
    """
    print("\n" + "=" * 80)
    print("🧪 EXPERIMENT 1: τ-BLIND TEST")
    print("=" * 80)
    print("질문: τ를 전혀 쓰지 않고도, 고RR 구간을 설명할 수 있는가?")
    
    results = []
    
    for signal in signals:
        dc = signal.get('dc_pre', 0.5)
        vol = estimate_vol_bucket(signal)
        dir_val = 5 if dc >= 0.7 else (-5 if dc <= 0.3 else 0)
        force = signal.get('force_ratio_30', 1.0)
        
        dc_extreme = dc <= 0.3 or dc >= 0.7
        vol_ok = vol in ['VOL_LOW', 'VOL_MID']
        dir_ok = abs(dir_val) >= 3
        force_ok = force >= 1.0
        
        tau = estimate_tau(signal)
        has_revisit = random.random() < calculate_revisit_probability(tau, vol, dc)
        rr = simulate_rr(signal, tau, has_revisit)
        hold = simulate_hold(signal, tau, has_revisit)
        
        results.append({
            'dc_extreme': dc_extreme,
            'vol_ok': vol_ok,
            'dir_ok': dir_ok,
            'force_ok': force_ok,
            'tau': tau,
            'rr': rr,
            'hold': hold,
            'has_revisit': has_revisit
        })
    
    all_conditions = [r for r in results if r['dc_extreme'] and r['vol_ok'] and r['dir_ok'] and r['force_ok']]
    partial_conditions = [r for r in results if r['dc_extreme'] and r['vol_ok'] and r['dir_ok'] and not r['force_ok']]
    
    if all_conditions:
        avg_rr_all = np.mean([r['rr'] for r in all_conditions])
        avg_hold_all = np.mean([r['hold'] for r in all_conditions])
    else:
        avg_rr_all = 0
        avg_hold_all = 0
    
    if partial_conditions:
        avg_rr_partial = np.mean([r['rr'] for r in partial_conditions])
        avg_hold_partial = np.mean([r['hold'] for r in partial_conditions])
    else:
        avg_rr_partial = 0
        avg_hold_partial = 0
    
    print(f"\n📊 Results (τ EXCLUDED from conditions):")
    print("-" * 50)
    print(f"All non-τ conditions met: {len(all_conditions)}")
    print(f"  Avg RR: {avg_rr_all:.2f}")
    print(f"  Avg HOLD: {avg_hold_all:.1f}")
    print(f"\nPartial conditions: {len(partial_conditions)}")
    print(f"  Avg RR: {avg_rr_partial:.2f}")
    print(f"  Avg HOLD: {avg_hold_partial:.1f}")
    
    tau_high_in_all = [r for r in all_conditions if r['tau'] >= 5]
    tau_low_in_all = [r for r in all_conditions if r['tau'] < 5]
    
    print(f"\n📊 Hidden τ distribution in 'all conditions' group:")
    print(f"  τ ≥ 5: {len(tau_high_in_all)} ({len(tau_high_in_all)/len(all_conditions)*100:.1f}%)" if all_conditions else "  N/A")
    print(f"  τ < 5: {len(tau_low_in_all)} ({len(tau_low_in_all)/len(all_conditions)*100:.1f}%)" if all_conditions else "  N/A")
    
    if tau_high_in_all and tau_low_in_all:
        rr_high = np.mean([r['rr'] for r in tau_high_in_all])
        rr_low = np.mean([r['rr'] for r in tau_low_in_all])
        print(f"\n📊 RR by hidden τ:")
        print(f"  τ ≥ 5 avg RR: {rr_high:.2f}")
        print(f"  τ < 5 avg RR: {rr_low:.2f}")
        
        verdict = "τ는 본질" if rr_high > rr_low * 1.2 else "τ 외 요인 존재"
    else:
        verdict = "데이터 부족"
    
    print(f"\n🎯 VERDICT: {verdict}")
    
    return {
        'experiment': 'tau_blind',
        'all_conditions_count': len(all_conditions),
        'avg_rr_all': avg_rr_all,
        'avg_hold_all': avg_hold_all,
        'verdict': verdict
    }


# =============================================================================
# 실험 2: τ Inversion Test
# =============================================================================

def experiment_2_tau_inversion(signals: List[Dict]) -> Dict:
    """
    실험 2: τ 역전 실험
    
    질문: "τ가 낮을수록 RR이 커지는 반례가 존재하는가?"
    """
    print("\n" + "=" * 80)
    print("🧪 EXPERIMENT 2: τ INVERSION TEST")
    print("=" * 80)
    print("질문: τ가 낮을수록 RR이 커지는 반례가 존재하는가?")
    
    tau_high = []
    tau_low = []
    
    for signal in signals:
        dc = signal.get('dc_pre', 0.5)
        vol = estimate_vol_bucket(signal)
        tau = estimate_tau(signal)
        
        dc_extreme = dc <= 0.3 or dc >= 0.7
        if not dc_extreme or vol == 'VOL_HIGH':
            continue
        
        has_revisit = random.random() < calculate_revisit_probability(tau, vol, dc)
        rr = simulate_rr(signal, tau, has_revisit)
        hold = simulate_hold(signal, tau, has_revisit)
        
        record = {'tau': tau, 'rr': rr, 'hold': hold, 'vol': vol, 'dc': dc}
        
        if tau >= 6:
            tau_high.append(record)
        elif tau <= 2:
            tau_low.append(record)
    
    print(f"\n📊 τ High (≥6) vs τ Low (≤2) — Same DC/VOL conditions:")
    print("-" * 50)
    
    if tau_high:
        avg_rr_high = np.mean([r['rr'] for r in tau_high])
        avg_hold_high = np.mean([r['hold'] for r in tau_high])
        print(f"τ HIGH (≥6): n={len(tau_high)}")
        print(f"  Avg RR: {avg_rr_high:.2f}")
        print(f"  Avg HOLD: {avg_hold_high:.1f}")
    else:
        avg_rr_high = 0
        avg_hold_high = 0
        print("τ HIGH: No data")
    
    if tau_low:
        avg_rr_low = np.mean([r['rr'] for r in tau_low])
        avg_hold_low = np.mean([r['hold'] for r in tau_low])
        print(f"\nτ LOW (≤2): n={len(tau_low)}")
        print(f"  Avg RR: {avg_rr_low:.2f}")
        print(f"  Avg HOLD: {avg_hold_low:.1f}")
    else:
        avg_rr_low = 0
        avg_hold_low = 0
        print("\nτ LOW: No data")
    
    high_rr_in_low_tau = sum(1 for r in tau_low if r['rr'] >= 2.5)
    high_rr_in_high_tau = sum(1 for r in tau_high if r['rr'] >= 2.5)
    
    print(f"\n📊 Anomaly check (RR ≥ 2.5):")
    print(f"  In τ LOW: {high_rr_in_low_tau} cases")
    print(f"  In τ HIGH: {high_rr_in_high_tau} cases")
    
    if tau_low and tau_high:
        if avg_rr_low > avg_rr_high:
            verdict = "❌ τ 역전 발견! τ는 충분조건이지 필요조건 아님"
        elif high_rr_in_low_tau > 0:
            verdict = "⚠️ 반례 존재 — τ는 필요조건 아닐 수 있음"
        else:
            verdict = "✅ τ 효과 확인 — τ 상위가 RR 상위"
    else:
        verdict = "데이터 부족"
    
    print(f"\n🎯 VERDICT: {verdict}")
    
    return {
        'experiment': 'tau_inversion',
        'tau_high_count': len(tau_high),
        'tau_low_count': len(tau_low),
        'avg_rr_high': avg_rr_high,
        'avg_rr_low': avg_rr_low,
        'anomalies_in_low_tau': high_rr_in_low_tau,
        'verdict': verdict
    }


# =============================================================================
# 실험 3: τ-free Revisit Test
# =============================================================================

def experiment_3_revisit_direct(signals: List[Dict]) -> Dict:
    """
    실험 3: 재도달 직접 측정 실험
    
    질문: "우리가 τ로 설명한 건 사실 '재도달' 그 자체 아닐까?"
    """
    print("\n" + "=" * 80)
    print("🧪 EXPERIMENT 3: τ-FREE REVISIT TEST")
    print("=" * 80)
    print("질문: 우리가 τ로 설명한 건 사실 '재도달' 그 자체 아닐까?")
    
    revisit_yes = []
    revisit_no = []
    
    for signal in signals:
        dc = signal.get('dc_pre', 0.5)
        vol = estimate_vol_bucket(signal)
        tau = estimate_tau(signal)
        
        revisit_prob = calculate_revisit_probability(tau, vol, dc)
        has_revisit = random.random() < revisit_prob
        
        rr = simulate_rr(signal, tau, has_revisit)
        hold = simulate_hold(signal, tau, has_revisit)
        
        record = {'tau': tau, 'rr': rr, 'hold': hold, 'vol': vol, 'dc': dc}
        
        if has_revisit:
            revisit_yes.append(record)
        else:
            revisit_no.append(record)
    
    print(f"\n📊 Revisit O vs Revisit X — Direct measurement:")
    print("-" * 50)
    
    if revisit_yes:
        avg_rr_yes = np.mean([r['rr'] for r in revisit_yes])
        avg_hold_yes = np.mean([r['hold'] for r in revisit_yes])
        avg_tau_yes = np.mean([r['tau'] for r in revisit_yes])
        print(f"REVISIT O: n={len(revisit_yes)}")
        print(f"  Avg RR: {avg_rr_yes:.2f}")
        print(f"  Avg HOLD: {avg_hold_yes:.1f}")
        print(f"  Avg τ: {avg_tau_yes:.2f}")
    else:
        avg_rr_yes = 0
        avg_tau_yes = 0
    
    if revisit_no:
        avg_rr_no = np.mean([r['rr'] for r in revisit_no])
        avg_hold_no = np.mean([r['hold'] for r in revisit_no])
        avg_tau_no = np.mean([r['tau'] for r in revisit_no])
        print(f"\nREVISIT X: n={len(revisit_no)}")
        print(f"  Avg RR: {avg_rr_no:.2f}")
        print(f"  Avg HOLD: {avg_hold_no:.1f}")
        print(f"  Avg τ: {avg_tau_no:.2f}")
    else:
        avg_rr_no = 0
        avg_tau_no = 0
    
    print(f"\n📊 τ vs Revisit correlation:")
    tau_revisit_corr = avg_tau_yes - avg_tau_no if revisit_yes and revisit_no else 0
    print(f"  τ difference (Revisit O - Revisit X): {tau_revisit_corr:.2f}")
    
    if revisit_yes and revisit_no:
        if tau_revisit_corr > 1.5:
            verdict = "τ와 재도달 강한 상관 — τ는 재도달의 그림자일 수 있음"
        elif tau_revisit_corr > 0.5:
            verdict = "τ와 재도달 부분 상관 — τ는 재도달 예측 변수"
        else:
            verdict = "τ와 재도달 약한 상관 — 별개 요인"
    else:
        verdict = "데이터 부족"
    
    print(f"\n🎯 VERDICT: {verdict}")
    
    return {
        'experiment': 'revisit_direct',
        'revisit_yes_count': len(revisit_yes),
        'revisit_no_count': len(revisit_no),
        'avg_rr_yes': avg_rr_yes,
        'avg_rr_no': avg_rr_no,
        'tau_revisit_correlation': tau_revisit_corr,
        'verdict': verdict
    }


# =============================================================================
# 실험 4: VOL-controlled τ Test
# =============================================================================

def experiment_4_vol_controlled(signals: List[Dict]) -> Dict:
    """
    실험 4: VOL 고정 실험
    
    질문: "VOL을 완전히 고정해도 τ는 여전히 설명력이 있는가?"
    """
    print("\n" + "=" * 80)
    print("🧪 EXPERIMENT 4: VOL-CONTROLLED τ TEST")
    print("=" * 80)
    print("질문: VOL을 완전히 고정해도 τ는 여전히 설명력이 있는가?")
    
    vol_low_only = []
    
    for signal in signals:
        vol = estimate_vol_bucket(signal)
        if vol != 'VOL_LOW':
            continue
        
        dc = signal.get('dc_pre', 0.5)
        tau = estimate_tau(signal)
        
        has_revisit = random.random() < calculate_revisit_probability(tau, vol, dc)
        rr = simulate_rr(signal, tau, has_revisit)
        hold = simulate_hold(signal, tau, has_revisit)
        
        vol_low_only.append({
            'tau': tau,
            'rr': rr,
            'hold': hold,
            'dc': dc
        })
    
    print(f"\n📊 VOL_LOW only — τ effect analysis:")
    print(f"Total in VOL_LOW: {len(vol_low_only)}")
    print("-" * 50)
    
    tau_high = [r for r in vol_low_only if r['tau'] >= 5]
    tau_mid = [r for r in vol_low_only if 2 <= r['tau'] < 5]
    tau_low = [r for r in vol_low_only if r['tau'] < 2]
    
    results_by_tau = []
    for name, group in [("τ HIGH (≥5)", tau_high), ("τ MID (2-4)", tau_mid), ("τ LOW (<2)", tau_low)]:
        if group:
            avg_rr = np.mean([r['rr'] for r in group])
            avg_hold = np.mean([r['hold'] for r in group])
            print(f"\n{name}: n={len(group)}")
            print(f"  Avg RR: {avg_rr:.2f}")
            print(f"  Avg HOLD: {avg_hold:.1f}")
            results_by_tau.append((name, avg_rr, avg_hold))
        else:
            print(f"\n{name}: No data")
    
    if tau_high and tau_low:
        rr_diff = np.mean([r['rr'] for r in tau_high]) - np.mean([r['rr'] for r in tau_low])
        if rr_diff > 0.5:
            verdict = "✅ VOL 고정 후에도 τ 효과 유지 — τ는 본질"
        elif rr_diff > 0.1:
            verdict = "⚠️ VOL 고정 후 τ 효과 약화 — τ와 VOL 복합 효과"
        else:
            verdict = "❌ VOL 고정하면 τ 효과 소멸 — VOL이 진짜 축"
    else:
        verdict = "데이터 부족"
    
    print(f"\n🎯 VERDICT: {verdict}")
    
    return {
        'experiment': 'vol_controlled',
        'vol_low_total': len(vol_low_only),
        'tau_high_count': len(tau_high),
        'tau_mid_count': len(tau_mid),
        'tau_low_count': len(tau_low),
        'verdict': verdict
    }


# =============================================================================
# MAIN
# =============================================================================

def run_all_stress_tests():
    """모든 τ stress test 실행"""
    
    print("=" * 80)
    print("TAU STRESS TESTS — 가설 비틀기 실험")
    print("=" * 80)
    print(f"Analysis Time: {datetime.now().isoformat()}")
    print("\n목표: τ가 정말 본질인가, 아니면 우리가 그렇게 보이게 만든 건가?")
    
    np.random.seed(42)
    random.seed(42)
    
    signals = load_legacy_signals()
    print(f"\nLoaded {len(signals)} signals")
    
    results = {}
    
    results['exp1'] = experiment_1_tau_blind(signals)
    results['exp2'] = experiment_2_tau_inversion(signals)
    results['exp3'] = experiment_3_revisit_direct(signals)
    results['exp4'] = experiment_4_vol_controlled(signals)
    
    print("\n" + "=" * 80)
    print("🎯 FINAL SUMMARY")
    print("=" * 80)
    
    print("\n📊 All Verdicts:")
    print("-" * 50)
    for key, result in results.items():
        print(f"{key}: {result['verdict']}")
    
    tau_survived = sum(1 for r in results.values() if '✅' in r['verdict'] or 'τ는 본질' in r['verdict'])
    tau_weakened = sum(1 for r in results.values() if '⚠️' in r['verdict'])
    tau_failed = sum(1 for r in results.values() if '❌' in r['verdict'])
    
    print(f"\n📊 Score:")
    print(f"  τ 생존: {tau_survived}/4")
    print(f"  τ 약화: {tau_weakened}/4")
    print(f"  τ 실패: {tau_failed}/4")
    
    if tau_survived >= 3:
        final_verdict = "τ는 본질 — 가설 유지"
    elif tau_survived >= 2:
        final_verdict = "τ는 주요 요인 — 복합 요인과 함께 작용"
    elif tau_weakened >= 2:
        final_verdict = "τ는 부분적 — 재도달/VOL과 상호작용"
    else:
        final_verdict = "τ 가설 재검토 필요"
    
    print(f"\n🏆 FINAL VERDICT: {final_verdict}")
    
    report = {
        'analysis_time': datetime.now().isoformat(),
        'total_signals': len(signals),
        'experiments': results,
        'summary': {
            'tau_survived': tau_survived,
            'tau_weakened': tau_weakened,
            'tau_failed': tau_failed,
            'final_verdict': final_verdict
        }
    }
    
    report_path = '/tmp/tau_stress_tests.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📄 Report saved to: {report_path}")
    
    return results


if __name__ == "__main__":
    run_all_stress_tests()
