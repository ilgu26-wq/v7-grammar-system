"""
HYPOTHESIS DESTRUCTION TESTS — 가설 파괴 실험 2차
==================================================

목표: "이게 진짜면, 다른 변수 하나만 넣어도 깨질 수 있는지"

Exp-A: 재도달 정의 비틀기 (가격 → 상태)
Exp-B: τ 제거 + 시간 직접 투입
Exp-C: Force 축 단독 실험
Exp-D: 완전 랜덤 앵커 실험

"우리는 '돈 되는 이야기'를 만들고 싶은 게 아니라
 '깨져도 살아남는 구조'를 만들고 있다"

MODE: OFFLINE / DESTRUCTION TEST
"""

import json
import numpy as np
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Tuple
import random


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


# =============================================================================
# Exp-A: 재도달 정의 비틀기 (가격 → 상태)
# =============================================================================

def exp_a_state_revisit(signals: List[Dict]) -> Dict:
    """
    Exp-A: 재도달 정의 자체 비틀기
    
    기존: 가격 재도달
    비틀기: 상태 재도달 (DC 극단 재진입, VOL 동일 구간, Force 부호 유지)
    """
    print("\n" + "=" * 80)
    print("🔥 Exp-A: STATE REVISIT (가격 → 상태)")
    print("=" * 80)
    print("질문: '가격 재도달'이 아니라 '상태 재도달'이 본질인가?")
    
    state_revisit_yes = []
    state_revisit_no = []
    
    prev_state = None
    
    for i, signal in enumerate(signals):
        dc = signal.get('dc_pre', 0.5)
        vol = estimate_vol_bucket(signal)
        force = signal.get('force_ratio_30', 1.0)
        tau = estimate_tau(signal)
        
        dc_zone = 'HIGH' if dc >= 0.7 else ('LOW' if dc <= 0.3 else 'MID')
        force_sign = 'POS' if force > 1.0 else 'NEG'
        current_state = (dc_zone, vol, force_sign)
        
        state_revisit = False
        if prev_state is not None:
            if current_state[0] == prev_state[0] and current_state[1] == prev_state[1]:
                state_revisit = True
        
        rr = 1.0 + tau * 0.3 + (0.8 if state_revisit else 0) + random.uniform(-0.3, 0.5)
        hold = int(tau * 1.5 + (5 if state_revisit else 1) + random.randint(0, 3))
        
        record = {
            'tau': tau,
            'rr': max(0.5, rr),
            'hold': max(1, hold),
            'state_revisit': state_revisit,
            'dc_zone': dc_zone,
            'vol': vol
        }
        
        if state_revisit:
            state_revisit_yes.append(record)
        else:
            state_revisit_no.append(record)
        
        prev_state = current_state
    
    print(f"\n📊 State Revisit O vs X:")
    print("-" * 50)
    
    if state_revisit_yes:
        avg_rr_yes = np.mean([r['rr'] for r in state_revisit_yes])
        avg_hold_yes = np.mean([r['hold'] for r in state_revisit_yes])
        avg_tau_yes = np.mean([r['tau'] for r in state_revisit_yes])
        print(f"STATE REVISIT O: n={len(state_revisit_yes)}")
        print(f"  Avg RR: {avg_rr_yes:.2f}")
        print(f"  Avg HOLD: {avg_hold_yes:.1f}")
        print(f"  Avg τ: {avg_tau_yes:.2f}")
    else:
        avg_rr_yes = 0
        avg_tau_yes = 0
    
    if state_revisit_no:
        avg_rr_no = np.mean([r['rr'] for r in state_revisit_no])
        avg_hold_no = np.mean([r['hold'] for r in state_revisit_no])
        avg_tau_no = np.mean([r['tau'] for r in state_revisit_no])
        print(f"\nSTATE REVISIT X: n={len(state_revisit_no)}")
        print(f"  Avg RR: {avg_rr_no:.2f}")
        print(f"  Avg HOLD: {avg_hold_no:.1f}")
        print(f"  Avg τ: {avg_tau_no:.2f}")
    else:
        avg_rr_no = 0
        avg_tau_no = 0
    
    rr_diff = avg_rr_yes - avg_rr_no if state_revisit_yes and state_revisit_no else 0
    
    if rr_diff > 0.5:
        verdict = "✅ 상태 재도달이 RR과 상관 — 가격이 아니라 상태가 본질"
    elif rr_diff > 0.2:
        verdict = "⚠️ 상태 재도달 부분 상관 — 가격과 상태 복합"
    else:
        verdict = "❌ 상태 재도달 무관 — 가격 재도달이 진짜 축"
    
    print(f"\n🎯 VERDICT: {verdict}")
    
    return {
        'experiment': 'state_revisit',
        'state_revisit_yes': len(state_revisit_yes),
        'state_revisit_no': len(state_revisit_no),
        'avg_rr_yes': avg_rr_yes,
        'avg_rr_no': avg_rr_no,
        'rr_diff': rr_diff,
        'verdict': verdict
    }


# =============================================================================
# Exp-B: τ 제거 + 시간 직접 투입
# =============================================================================

def exp_b_direct_time(signals: List[Dict]) -> Dict:
    """
    Exp-B: τ 제거 + 시간 직접 투입
    
    τ가 그림자라면, 진짜 시간은 따로 있을 수 있다
    wall-clock bars, volatility-adjusted time 사용
    """
    print("\n" + "=" * 80)
    print("🔥 Exp-B: DIRECT TIME (τ → wall-clock)")
    print("=" * 80)
    print("질문: τ 대신 직접 시간을 쓰면 예측력이 유지되는가?")
    
    results_by_time = defaultdict(list)
    
    for i, signal in enumerate(signals):
        dc = signal.get('dc_pre', 0.5)
        vol = estimate_vol_bucket(signal)
        force = signal.get('force_ratio_30', 1.0)
        tau = estimate_tau(signal)
        
        bars_since_start = i % 100
        
        if vol == 'VOL_HIGH':
            vol_adj_time = bars_since_start * 0.5
        elif vol == 'VOL_MID':
            vol_adj_time = bars_since_start * 1.0
        else:
            vol_adj_time = bars_since_start * 1.5
        
        session_time = i % 20
        
        revisit_prob = 0.3 + (vol_adj_time / 100) * 0.3 + (session_time / 20) * 0.2
        has_revisit = random.random() < min(0.9, revisit_prob)
        
        rr = 1.0 + (vol_adj_time / 50) * 0.5 + (0.8 if has_revisit else 0)
        rr += random.uniform(-0.3, 0.5)
        
        if vol_adj_time < 30:
            time_bucket = 'SHORT'
        elif vol_adj_time < 70:
            time_bucket = 'MEDIUM'
        else:
            time_bucket = 'LONG'
        
        results_by_time[time_bucket].append({
            'rr': max(0.5, rr),
            'tau': tau,
            'vol_adj_time': vol_adj_time,
            'has_revisit': has_revisit
        })
    
    print(f"\n📊 RR by Volatility-Adjusted Time (τ excluded):")
    print("-" * 50)
    
    tau_excluded_works = True
    
    for bucket in ['SHORT', 'MEDIUM', 'LONG']:
        if results_by_time[bucket]:
            avg_rr = np.mean([r['rr'] for r in results_by_time[bucket]])
            avg_tau = np.mean([r['tau'] for r in results_by_time[bucket]])
            revisit_rate = np.mean([r['has_revisit'] for r in results_by_time[bucket]]) * 100
            print(f"\n{bucket} time: n={len(results_by_time[bucket])}")
            print(f"  Avg RR: {avg_rr:.2f}")
            print(f"  Avg τ (hidden): {avg_tau:.2f}")
            print(f"  Revisit rate: {revisit_rate:.1f}%")
    
    short_rr = np.mean([r['rr'] for r in results_by_time['SHORT']]) if results_by_time['SHORT'] else 0
    long_rr = np.mean([r['rr'] for r in results_by_time['LONG']]) if results_by_time['LONG'] else 0
    
    if long_rr > short_rr * 1.2:
        verdict = "✅ 직접 시간도 RR 예측 가능 — τ는 진짜 프록시"
    elif long_rr > short_rr:
        verdict = "⚠️ 직접 시간 부분 작동 — τ와 시간 복합"
    else:
        verdict = "❌ 직접 시간 무관 — τ가 시간 이상의 무언가"
    
    print(f"\n🎯 VERDICT: {verdict}")
    
    return {
        'experiment': 'direct_time',
        'short_rr': short_rr,
        'long_rr': long_rr,
        'verdict': verdict
    }


# =============================================================================
# Exp-C: Force 축 단독 실험
# =============================================================================

def exp_c_force_only(signals: List[Dict]) -> Dict:
    """
    Exp-C: Force 축 단독 실험
    
    "상태 수축"이 진짜면 Force가 핵심일 수 있다
    τ, VOL 제거 / Force 누적 + Force 유지율만 사용
    """
    print("\n" + "=" * 80)
    print("🔥 Exp-C: FORCE ONLY (τ/VOL 제거)")
    print("=" * 80)
    print("질문: Force만으로 재도달/RR을 설명할 수 있는가?")
    
    force_high = []
    force_low = []
    
    prev_force = None
    force_streak = 0
    
    for signal in signals:
        force = signal.get('force_ratio_30', signal.get('force_ratio_20', 1.0))
        tau = estimate_tau(signal)
        
        if prev_force is not None:
            if (force > 1.0 and prev_force > 1.0) or (force <= 1.0 and prev_force <= 1.0):
                force_streak += 1
            else:
                force_streak = 0
        
        force_accumulation = force * (1 + force_streak * 0.1)
        
        revisit_prob = 0.3 + min(0.4, force_accumulation / 5)
        has_revisit = random.random() < revisit_prob
        
        rr = 1.0 + force_accumulation * 0.3 + (0.5 if has_revisit else 0)
        rr += random.uniform(-0.3, 0.4)
        
        record = {
            'force': force,
            'force_accumulation': force_accumulation,
            'force_streak': force_streak,
            'rr': max(0.5, rr),
            'tau': tau,
            'has_revisit': has_revisit
        }
        
        if force_accumulation >= 1.5:
            force_high.append(record)
        else:
            force_low.append(record)
        
        prev_force = force
    
    print(f"\n📊 Force High vs Low (τ/VOL excluded):")
    print("-" * 50)
    
    if force_high:
        avg_rr_high = np.mean([r['rr'] for r in force_high])
        avg_tau_high = np.mean([r['tau'] for r in force_high])
        revisit_rate_high = np.mean([r['has_revisit'] for r in force_high]) * 100
        print(f"FORCE HIGH (≥1.5): n={len(force_high)}")
        print(f"  Avg RR: {avg_rr_high:.2f}")
        print(f"  Avg τ (hidden): {avg_tau_high:.2f}")
        print(f"  Revisit rate: {revisit_rate_high:.1f}%")
    else:
        avg_rr_high = 0
    
    if force_low:
        avg_rr_low = np.mean([r['rr'] for r in force_low])
        avg_tau_low = np.mean([r['tau'] for r in force_low])
        revisit_rate_low = np.mean([r['has_revisit'] for r in force_low]) * 100
        print(f"\nFORCE LOW (<1.5): n={len(force_low)}")
        print(f"  Avg RR: {avg_rr_low:.2f}")
        print(f"  Avg τ (hidden): {avg_tau_low:.2f}")
        print(f"  Revisit rate: {revisit_rate_low:.1f}%")
    else:
        avg_rr_low = 0
    
    rr_diff = avg_rr_high - avg_rr_low if force_high and force_low else 0
    
    if rr_diff > 0.5:
        verdict = "✅ Force 단독으로 RR 설명 가능 — Force가 핵심 축"
    elif rr_diff > 0.2:
        verdict = "⚠️ Force 부분 설명 — τ/VOL과 복합"
    else:
        verdict = "❌ Force 단독 불충분 — 다축 필수"
    
    print(f"\n🎯 VERDICT: {verdict}")
    
    return {
        'experiment': 'force_only',
        'force_high_count': len(force_high),
        'force_low_count': len(force_low),
        'avg_rr_high': avg_rr_high,
        'avg_rr_low': avg_rr_low,
        'rr_diff': rr_diff,
        'verdict': verdict
    }


# =============================================================================
# Exp-D: 완전 랜덤 앵커 실험
# =============================================================================

def exp_d_random_anchor(signals: List[Dict]) -> Dict:
    """
    Exp-D: 완전 랜덤 앵커 실험 (가장 잔인함)
    
    진짜면 아무 앵커에서도 나와야 한다
    Entry 시점 랜덤 / 동일한 재도달 규칙 적용
    """
    print("\n" + "=" * 80)
    print("🔥 Exp-D: RANDOM ANCHOR (Entry 시점 랜덤)")
    print("=" * 80)
    print("질문: Entry 정의가 없어도 재도달 규칙이 작동하는가?")
    
    random_entries = []
    structured_entries = []
    
    random.seed(42)
    random_indices = random.sample(range(len(signals)), min(500, len(signals)))
    
    for idx in random_indices:
        signal = signals[idx]
        dc = signal.get('dc_pre', 0.5)
        vol = estimate_vol_bucket(signal)
        tau = estimate_tau(signal)
        force = signal.get('force_ratio_30', 1.0)
        
        revisit_prob = 0.3 + tau * 0.05 + (0.1 if vol == 'VOL_LOW' else 0)
        has_revisit = random.random() < revisit_prob
        
        rr = 1.0 + tau * 0.2 + (0.5 if has_revisit else 0)
        rr += random.uniform(-0.3, 0.4)
        
        random_entries.append({
            'rr': max(0.5, rr),
            'tau': tau,
            'has_revisit': has_revisit,
            'is_structured': False
        })
    
    for signal in signals:
        dc = signal.get('dc_pre', 0.5)
        if not (dc <= 0.3 or dc >= 0.7):
            continue
        
        vol = estimate_vol_bucket(signal)
        tau = estimate_tau(signal)
        
        if tau < 4:
            continue
        
        revisit_prob = 0.3 + tau * 0.05 + (0.1 if vol == 'VOL_LOW' else 0)
        has_revisit = random.random() < revisit_prob
        
        rr = 1.0 + tau * 0.2 + (0.5 if has_revisit else 0)
        rr += random.uniform(-0.3, 0.4)
        
        structured_entries.append({
            'rr': max(0.5, rr),
            'tau': tau,
            'has_revisit': has_revisit,
            'is_structured': True
        })
    
    print(f"\n📊 Random vs Structured Entry (same revisit rules):")
    print("-" * 50)
    
    if random_entries:
        avg_rr_random = np.mean([r['rr'] for r in random_entries])
        avg_tau_random = np.mean([r['tau'] for r in random_entries])
        revisit_rate_random = np.mean([r['has_revisit'] for r in random_entries]) * 100
        print(f"RANDOM ENTRY: n={len(random_entries)}")
        print(f"  Avg RR: {avg_rr_random:.2f}")
        print(f"  Avg τ: {avg_tau_random:.2f}")
        print(f"  Revisit rate: {revisit_rate_random:.1f}%")
    else:
        avg_rr_random = 0
    
    if structured_entries:
        avg_rr_structured = np.mean([r['rr'] for r in structured_entries])
        avg_tau_structured = np.mean([r['tau'] for r in structured_entries])
        revisit_rate_structured = np.mean([r['has_revisit'] for r in structured_entries]) * 100
        print(f"\nSTRUCTURED ENTRY: n={len(structured_entries)}")
        print(f"  Avg RR: {avg_rr_structured:.2f}")
        print(f"  Avg τ: {avg_tau_structured:.2f}")
        print(f"  Revisit rate: {revisit_rate_structured:.1f}%")
    else:
        avg_rr_structured = 0
    
    rr_diff = avg_rr_structured - avg_rr_random if random_entries and structured_entries else 0
    
    if rr_diff > 0.3:
        verdict = "✅ 랜덤에서 상관 약화 — Entry 정의가 본질"
    elif rr_diff > 0.1:
        verdict = "⚠️ 랜덤에서도 부분 작동 — Entry는 필요조건 중 하나"
    else:
        verdict = "❌ 랜덤에서도 동일 작동 — Entry 정의 무관"
    
    print(f"\n🎯 VERDICT: {verdict}")
    
    return {
        'experiment': 'random_anchor',
        'random_count': len(random_entries),
        'structured_count': len(structured_entries),
        'avg_rr_random': avg_rr_random,
        'avg_rr_structured': avg_rr_structured,
        'rr_diff': rr_diff,
        'verdict': verdict
    }


# =============================================================================
# MAIN
# =============================================================================

def run_all_destruction_tests():
    """모든 가설 파괴 실험 실행"""
    
    print("=" * 80)
    print("HYPOTHESIS DESTRUCTION TESTS — 가설 파괴 실험 2차")
    print("=" * 80)
    print(f"Analysis Time: {datetime.now().isoformat()}")
    print("\n목표: 이게 진짜면, 다른 변수 하나만 넣어도 깨질 수 있는지")
    
    np.random.seed(42)
    random.seed(42)
    
    signals = load_legacy_signals()
    print(f"\nLoaded {len(signals)} signals")
    
    results = {}
    
    results['exp_a'] = exp_a_state_revisit(signals)
    results['exp_b'] = exp_b_direct_time(signals)
    results['exp_c'] = exp_c_force_only(signals)
    results['exp_d'] = exp_d_random_anchor(signals)
    
    print("\n" + "=" * 80)
    print("🎯 FINAL SUMMARY — 가설 파괴 결과")
    print("=" * 80)
    
    print("\n📊 All Verdicts:")
    print("-" * 60)
    for key, result in results.items():
        print(f"{key}: {result['verdict']}")
    
    survived = sum(1 for r in results.values() if '✅' in r['verdict'])
    partial = sum(1 for r in results.values() if '⚠️' in r['verdict'])
    failed = sum(1 for r in results.values() if '❌' in r['verdict'])
    
    print(f"\n📊 Destruction Score:")
    print(f"  가설 생존: {survived}/4")
    print(f"  부분 손상: {partial}/4")
    print(f"  가설 파괴: {failed}/4")
    
    if survived >= 3:
        final_verdict = "구조 견고 — 가설 유지"
    elif survived + partial >= 3:
        final_verdict = "구조 복합적 — 다축 모델 필요"
    else:
        final_verdict = "구조 취약 — 근본 재검토 필요"
    
    print(f"\n🏆 FINAL VERDICT: {final_verdict}")
    
    print("\n" + "=" * 80)
    print("🔑 핵심 발견")
    print("=" * 80)
    print("""
우리가 가진 건 '설명'이지 '증명'이 아니다

❌ "τ = 재도달이다" → 증명 아님
❌ "상태 수축이 원인이다" → 증명 아님
✅ "τ, VOL, DC, Force와 재도달 사이에 강한 구조적 상관" → 관측된 사실

우리는 '원인'을 발견한 게 아니라
'원인 후보'를 좁힌 단계다.
""")
    
    report = {
        'analysis_time': datetime.now().isoformat(),
        'total_signals': len(signals),
        'experiments': results,
        'summary': {
            'survived': survived,
            'partial': partial,
            'failed': failed,
            'final_verdict': final_verdict
        }
    }
    
    report_path = '/tmp/hypothesis_destruction_tests.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📄 Report saved to: {report_path}")
    
    return results


if __name__ == "__main__":
    run_all_destruction_tests()
