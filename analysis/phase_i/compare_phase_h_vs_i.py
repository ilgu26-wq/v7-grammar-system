"""
Phase I — COMPARE PHASE H vs I
==============================

핵심 비교:
- 같은 데이터
- 같은 엔진
- 단 하나 다른 것: EXIT 허용 시점

측정 지표:
1. 세션 구조 지표: Avg Duration, ENTER→WAIT 비율, HOLD 발생률
2. 엔진 핸드오프 지표: Entry→Force, Force→EXIT
3. FAIL_REASON 분포 변화
"""

import json
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class ComparisonMetrics:
    """Phase H vs I 비교 지표"""
    phase: str
    total_sessions: int
    avg_duration: float
    avg_force_accumulated: float
    win_rate: float
    total_pnl: float
    hold_bars_total: int
    observation_blocks: int
    exit_reasons: Dict[str, int]


def load_phase_h_sessions() -> List[Dict]:
    """Phase H 세션 로드"""
    try:
        with open('/tmp/phase_h_sessions.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Phase H sessions not found. Run Phase H first.")
        return []


def load_phase_i_sessions() -> List[Dict]:
    """Phase I 세션 로드"""
    try:
        with open('/tmp/phase_i_sessions.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Phase I sessions not found. Run apply_session_orchestrator.py first.")
        return []


def calculate_metrics(sessions: List[Dict], phase: str) -> ComparisonMetrics:
    """지표 계산"""
    if not sessions:
        return ComparisonMetrics(phase, 0, 0, 0, 0, 0, 0, 0, {})
    
    total = len(sessions)
    
    if phase == "H":
        durations = [s.get('end_bar', 0) - s.get('start_bar', 0) for s in sessions]
        forces = [s.get('max_force_int', 0) for s in sessions]
        hold_bars = sum(len(s.get('bars', [])) - 1 for s in sessions)
        obs_blocks = 0
    else:
        durations = [s.get('duration_bars', 0) for s in sessions]
        forces = [s.get('force_accumulated', 0) for s in sessions]
        hold_bars = sum(s.get('hold_bars', 0) for s in sessions)
        obs_blocks = sum(s.get('observation_window_blocks', 0) for s in sessions)
    
    pnls = [s.get('pnl', 0) for s in sessions]
    wins = sum(1 for p in pnls if p > 0)
    
    exit_reasons = {}
    for s in sessions:
        reason = s.get('exit_reason', 'UNKNOWN')
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
    
    return ComparisonMetrics(
        phase=phase,
        total_sessions=total,
        avg_duration=sum(durations) / total if total else 0,
        avg_force_accumulated=sum(forces) / total if total else 0,
        win_rate=(wins / total * 100) if total else 0,
        total_pnl=sum(pnls),
        hold_bars_total=hold_bars,
        observation_blocks=obs_blocks,
        exit_reasons=exit_reasons
    )


def compare_phases(phase_h: ComparisonMetrics, phase_i: ComparisonMetrics) -> Dict:
    """Phase H vs I 비교"""
    print("\n" + "=" * 70)
    print("PHASE H vs PHASE I — COMPARISON")
    print("=" * 70)
    
    print("\n📊 Session Structure Metrics:")
    print("-" * 50)
    print(f"{'Metric':<30} {'Phase H':>15} {'Phase I':>15} {'Change':>10}")
    print("-" * 50)
    
    def delta(h, i):
        if h == 0:
            return "N/A"
        change = ((i - h) / h) * 100
        return f"{'+' if change > 0 else ''}{change:.1f}%"
    
    metrics = [
        ("Total Sessions", phase_h.total_sessions, phase_i.total_sessions),
        ("Avg Duration (bars)", phase_h.avg_duration, phase_i.avg_duration),
        ("Avg Force Accumulated", phase_h.avg_force_accumulated, phase_i.avg_force_accumulated),
        ("Win Rate (%)", phase_h.win_rate, phase_i.win_rate),
        ("Total PnL", phase_h.total_pnl, phase_i.total_pnl),
        ("Total HOLD bars", phase_h.hold_bars_total, phase_i.hold_bars_total),
    ]
    
    for name, h_val, i_val in metrics:
        print(f"{name:<30} {h_val:>15.1f} {i_val:>15.1f} {delta(h_val, i_val):>10}")
    
    print(f"\n📋 Observation Window Blocks (Phase I only): {phase_i.observation_blocks}")
    
    print("\n📊 EXIT Reason Distribution:")
    print("-" * 50)
    
    all_reasons = set(phase_h.exit_reasons.keys()) | set(phase_i.exit_reasons.keys())
    print(f"{'EXIT Reason':<30} {'Phase H':>15} {'Phase I':>15}")
    print("-" * 50)
    for reason in sorted(all_reasons):
        h_count = phase_h.exit_reasons.get(reason, 0)
        i_count = phase_i.exit_reasons.get(reason, 0)
        print(f"{reason:<30} {h_count:>15} {i_count:>15}")
    
    print("\n" + "=" * 70)
    print("SUCCESS CRITERIA CHECK")
    print("=" * 70)
    
    criteria = []
    
    enter_wait_broken = phase_i.hold_bars_total > phase_h.hold_bars_total
    criteria.append(("ENTER → WAIT 100% 붕괴", enter_wait_broken, 
                     f"HOLD bars: {phase_h.hold_bars_total} → {phase_i.hold_bars_total}"))
    
    duration_increased = phase_i.avg_duration > phase_h.avg_duration
    criteria.append(("세션 평균 길이 증가", duration_increased,
                     f"Duration: {phase_h.avg_duration:.1f} → {phase_i.avg_duration:.1f}"))
    
    force_works = phase_i.avg_force_accumulated > 0
    criteria.append(("Force 누적 작동", force_works,
                     f"Avg Force: {phase_i.avg_force_accumulated:.1f}"))
    
    hold_natural = phase_i.hold_bars_total > 0
    criteria.append(("HOLD 자연 발생", hold_natural,
                     f"Hold bars: {phase_i.hold_bars_total}"))
    
    fail_structural = len(phase_i.exit_reasons) <= 5
    criteria.append(("FAIL_REASON 구조적 설명 가능", fail_structural,
                     f"Exit types: {len(phase_i.exit_reasons)}"))
    
    print(f"\n{'Criterion':<40} {'Status':>10} {'Evidence':<30}")
    print("-" * 80)
    
    passed = 0
    for name, status, evidence in criteria:
        status_str = "✅ PASS" if status else "❌ FAIL"
        print(f"{name:<40} {status_str:>10} {evidence:<30}")
        if status:
            passed += 1
    
    print("-" * 80)
    print(f"\nPassed: {passed}/{len(criteria)}")
    
    if passed == len(criteria):
        print("\n🎉 PHASE I SUCCESS — All criteria met!")
    elif passed >= 3:
        print("\n⚠️ PHASE I PARTIAL — Most criteria met")
    else:
        print("\n❌ PHASE I NEEDS WORK — Review Orchestrator rules")
    
    return {
        "phase_h": {
            "total_sessions": phase_h.total_sessions,
            "avg_duration": phase_h.avg_duration,
            "avg_force": phase_h.avg_force_accumulated,
            "win_rate": phase_h.win_rate,
            "total_pnl": phase_h.total_pnl,
            "exit_reasons": phase_h.exit_reasons
        },
        "phase_i": {
            "total_sessions": phase_i.total_sessions,
            "avg_duration": phase_i.avg_duration,
            "avg_force": phase_i.avg_force_accumulated,
            "win_rate": phase_i.win_rate,
            "total_pnl": phase_i.total_pnl,
            "exit_reasons": phase_i.exit_reasons,
            "hold_bars": phase_i.hold_bars_total,
            "observation_blocks": phase_i.observation_blocks
        },
        "criteria_results": [
            {"name": name, "passed": status, "evidence": evidence}
            for name, status, evidence in criteria
        ],
        "passed_count": passed,
        "total_criteria": len(criteria)
    }


def main():
    phase_h_sessions = load_phase_h_sessions()
    phase_i_sessions = load_phase_i_sessions()
    
    phase_h_metrics = calculate_metrics(phase_h_sessions, "H")
    phase_i_metrics = calculate_metrics(phase_i_sessions, "I")
    
    comparison = compare_phases(phase_h_metrics, phase_i_metrics)
    
    output_path = '/tmp/phase_h_vs_i_comparison.json'
    with open(output_path, 'w') as f:
        json.dump(comparison, f, indent=2, default=str)
    
    print(f"\nComparison saved to: {output_path}")
    return comparison


if __name__ == "__main__":
    main()
