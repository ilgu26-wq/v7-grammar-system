"""
Phase I — FINAL REPORT
======================

Phase I 성공 조건:
1. ENTER → WAIT 100% 붕괴
2. 세션 평균 길이 유의미 증가
3. Force 누적이 '세션 내부 변수'로 작동
4. HOLD가 코드 분기 없이 자연 발생
5. FAIL_REASON이 구조적으로 설명 가능

한 줄 결론:
Phase I은 시스템을 고치는 단계가 아니라
"시스템이 왜 안 벌었는지 증명하는 마지막 단계"다.
"""

import json
from datetime import datetime
from typing import Dict

from apply_session_orchestrator import PhaseIAnalyzer, load_force_data
from compare_phase_h_vs_i import (
    load_phase_h_sessions, 
    calculate_metrics, 
    compare_phases
)
from session_orchestrator import PHASE_I_HYPOTHESES, PHASE_I_SUCCESS_CRITERIA


def run_phase_i_analysis() -> Dict:
    """Phase I 전체 분석 실행"""
    print("=" * 70)
    print("PHASE I — SESSION ORCHESTRATOR EXPERIMENT")
    print("=" * 70)
    print(f"\nAnalysis Time: {datetime.now().isoformat()}")
    print("\n목적: ENTER 이후 세션이 '왜 유지되거나 끊기는지'를")
    print("      엔진이 아닌 규칙으로 설명 가능하게 만드는 것")
    
    print("\n📘 Hypotheses Under Test:")
    for h_id, h_data in PHASE_I_HYPOTHESES.items():
        print(f"\n  {h_id}: {h_data['name']}")
        print(f"    Statement: {h_data['statement']}")
        print(f"    Test: {h_data['test']}")
    
    print("\n" + "=" * 70)
    print("STEP 1: APPLY SESSION ORCHESTRATOR")
    print("=" * 70)
    
    candles = load_force_data()
    analyzer = PhaseIAnalyzer()
    phase_i_sessions = analyzer.analyze(candles)
    
    sessions_path = '/tmp/phase_i_sessions.json'
    with open(sessions_path, 'w') as f:
        json.dump([s.to_dict() for s in phase_i_sessions], f, indent=2, default=str)
    
    print("\n" + "=" * 70)
    print("STEP 2: COMPARE PHASE H vs I")
    print("=" * 70)
    
    phase_h_sessions = load_phase_h_sessions()
    
    phase_h_metrics = calculate_metrics(phase_h_sessions, "H")
    phase_i_metrics = calculate_metrics([s.to_dict() for s in phase_i_sessions], "I")
    
    comparison = compare_phases(phase_h_metrics, phase_i_metrics)
    
    print("\n" + "=" * 70)
    print("STEP 3: HYPOTHESIS VALIDATION")
    print("=" * 70)
    
    hypothesis_results = validate_hypotheses(phase_h_metrics, phase_i_metrics, analyzer)
    
    final_report = {
        "analysis_time": datetime.now().isoformat(),
        "phase": "I",
        "purpose": "SESSION ORCHESTRATOR EXPERIMENT",
        "hypotheses": PHASE_I_HYPOTHESES,
        "hypothesis_results": hypothesis_results,
        "comparison": comparison,
        "orchestrator_stats": analyzer.orchestrator.get_statistics(),
        "success_criteria": PHASE_I_SUCCESS_CRITERIA,
        "passed_criteria": comparison['passed_count'],
        "total_criteria": comparison['total_criteria'],
        "phase_i_passed": comparison['passed_count'] >= 4,
        "next_steps": generate_next_steps(comparison, hypothesis_results)
    }
    
    print_final_summary(final_report)
    
    report_path = '/tmp/phase_i_final_report.json'
    with open(report_path, 'w') as f:
        json.dump(final_report, f, indent=2, default=str)
    
    md_path = '/tmp/phase_i_report.md'
    with open(md_path, 'w') as f:
        f.write(generate_markdown_report(final_report))
    
    print(f"\n📄 Reports saved:")
    print(f"  - JSON: {report_path}")
    print(f"  - Markdown: {md_path}")
    
    return final_report


def validate_hypotheses(phase_h, phase_i, analyzer) -> Dict:
    """가설 검증"""
    results = {}
    
    results["H-I1"] = {
        "name": "Session Persistence Hypothesis",
        "validated": phase_i.hold_bars_total > phase_h.hold_bars_total,
        "evidence": f"HOLD bars increased: {phase_h.hold_bars_total} → {phase_i.hold_bars_total}",
        "conclusion": "ENTER 직후 즉시 종료 감소 → 구조적 단절 해소 중"
    }
    
    results["H-I2"] = {
        "name": "Force Accumulation Hypothesis",
        "validated": phase_i.avg_force_accumulated > 0,
        "evidence": f"Avg Force Accumulated: {phase_i.avg_force_accumulated:.1f}",
        "conclusion": "Force가 세션 내부 누적 변수로 작동 중"
    }
    
    results["H-I3"] = {
        "name": "HOLD Reinterpretation Hypothesis",
        "validated": phase_i.hold_bars_total > 0 and phase_i.observation_blocks > 0,
        "evidence": f"Observation blocks: {phase_i.observation_blocks}",
        "conclusion": "HOLD가 규칙 기반으로 자연 발생"
    }
    
    print("\n📋 Hypothesis Validation:")
    for h_id, result in results.items():
        status = "✅" if result['validated'] else "❌"
        print(f"\n  {status} {h_id}: {result['name']}")
        print(f"    Evidence: {result['evidence']}")
        print(f"    Conclusion: {result['conclusion']}")
    
    return results


def generate_next_steps(comparison: Dict, hypotheses: Dict) -> list:
    """다음 단계 도출"""
    steps = []
    
    all_passed = all(h['validated'] for h in hypotheses.values())
    
    if all_passed and comparison['passed_count'] >= 4:
        steps.append("Phase I 완료 → 알파 레이어 설계 가능")
        steps.append("Session Orchestrator 규칙을 프로덕션에 적용")
        steps.append("ML/알파를 Entry→Force 핸드오프에 추가")
    else:
        if not hypotheses.get("H-I1", {}).get("validated"):
            steps.append("Observation Window 조정 (N bars 증가)")
        if not hypotheses.get("H-I2", {}).get("validated"):
            steps.append("Force 누적 게이트 조정")
        if not hypotheses.get("H-I3", {}).get("validated"):
            steps.append("HOLD 규칙 재검토")
    
    return steps


def print_final_summary(report: Dict):
    """최종 요약 출력"""
    print("\n" + "=" * 70)
    print("PHASE I — FINAL SUMMARY")
    print("=" * 70)
    
    print(f"\n🎯 Criteria Passed: {report['passed_criteria']}/{report['total_criteria']}")
    
    status = "✅ PASSED" if report['phase_i_passed'] else "❌ FAILED"
    print(f"Phase I Status: {status}")
    
    print("\n📌 Next Steps:")
    for i, step in enumerate(report['next_steps'], 1):
        print(f"  {i}. {step}")
    
    if report['phase_i_passed']:
        print("\n" + "=" * 70)
        print("🎉 PHASE I SUCCESS!")
        print("=" * 70)
        print("""
이제 명확해진 것:
✔ 알파를 어디에 붙일지 → Entry→Force 핸드오프
✔ 스몰/익스텐드가 왜 안 나왔는지 → 세션 유지 규칙 부재
✔ ML이 어디에 들어가야 하는지 → Session Orchestrator 레이어

다음: 알파 레이어 설계
""")


def generate_markdown_report(report: Dict) -> str:
    """마크다운 리포트 생성"""
    md = f"""# Phase I — SESSION ORCHESTRATOR EXPERIMENT

**Analysis Time:** {report['analysis_time']}

## Purpose

ENTER 이후 세션이 "왜 유지되거나 끊기는지"를
엔진이 아닌 규칙으로 설명 가능하게 만드는 것

## Hypotheses

| ID | Hypothesis | Validated | Evidence |
|----|------------|-----------|----------|
"""
    
    for h_id, result in report['hypothesis_results'].items():
        status = "✅" if result['validated'] else "❌"
        md += f"| {h_id} | {result['name']} | {status} | {result['evidence']} |\n"
    
    md += f"""
## Results

**Criteria Passed:** {report['passed_criteria']}/{report['total_criteria']}

**Phase I Status:** {'✅ PASSED' if report['phase_i_passed'] else '❌ FAILED'}

## Comparison (Phase H vs I)

| Metric | Phase H | Phase I |
|--------|---------|---------|
| Sessions | {report['comparison']['phase_h']['total_sessions']} | {report['comparison']['phase_i']['total_sessions']} |
| Avg Duration | {report['comparison']['phase_h']['avg_duration']:.1f} | {report['comparison']['phase_i']['avg_duration']:.1f} |
| Win Rate | {report['comparison']['phase_h']['win_rate']:.1f}% | {report['comparison']['phase_i']['win_rate']:.1f}% |

## Next Steps

"""
    for i, step in enumerate(report['next_steps'], 1):
        md += f"{i}. {step}\n"
    
    return md


def main():
    return run_phase_i_analysis()


if __name__ == "__main__":
    main()
