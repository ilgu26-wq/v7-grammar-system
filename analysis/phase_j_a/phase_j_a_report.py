"""
Phase J-A — FINAL REPORT
========================

최종 판정 리포트

PASS 조건:
- H-1~H-5 모두 PASS
- FAIL_REASON 분포 차이 통계적으로 무의미
- 구조/전이 그래프 동형(isomorphic)

PASS 선언 문구:
"Alpha observation does not contaminate decision structure.
Alpha can be safely elevated from observer to gate."
"""

import json
from datetime import datetime
from typing import Dict

from inject_alpha_readonly import AlphaInjectionAnalyzer, load_force_data
from alpha_bucket_analysis import analyze_by_bucket, check_distribution_stability
from structure_diff_check import load_phase_i_sessions, compare_structures


def run_phase_j_a_analysis() -> Dict:
    """Phase J-A 전체 분석 실행"""
    print("=" * 70)
    print("PHASE J-A — ALPHA INJECTION DRY-RUN")
    print("=" * 70)
    print(f"\nAnalysis Time: {datetime.now().isoformat()}")
    print("\n목적: 알파를 관측 변수로만 삽입했을 때")
    print("      구조가 오염되지 않는지를 검증한다")
    
    print("\n" + "=" * 70)
    print("STEP 1: INJECT ALPHA (READ-ONLY)")
    print("=" * 70)
    
    candles = load_force_data()
    analyzer = AlphaInjectionAnalyzer()
    sessions = analyzer.analyze(candles)
    
    sessions_path = '/tmp/phase_j_a_sessions.json'
    with open(sessions_path, 'w') as f:
        json.dump([s.to_dict() for s in sessions], f, indent=2, default=str)
    
    print("\n" + "=" * 70)
    print("STEP 2: ALPHA BUCKET ANALYSIS")
    print("=" * 70)
    
    session_dicts = [s.to_dict() for s in sessions]
    bucket_analysis = analyze_by_bucket(session_dicts)
    stability = check_distribution_stability(session_dicts)
    
    print("\n" + "=" * 70)
    print("STEP 3: STRUCTURE DIFF CHECK")
    print("=" * 70)
    
    phase_i = load_phase_i_sessions()
    structure_diff = compare_structures(phase_i, session_dicts)
    
    print("\n" + "=" * 70)
    print("STEP 4: FINAL JUDGMENT")
    print("=" * 70)
    
    j_a_1 = structure_diff.get('all_pass', False)
    j_a_2 = stability.get('is_stable', False)
    j_a_3 = structure_diff.get('exit_reasons_match', False)
    j_a_4 = structure_diff.get('duration_match', False)
    
    all_pass = j_a_1 and j_a_2 and j_a_3 and j_a_4
    
    print("\n📋 Phase J-A Criteria:")
    print(f"  {'✅' if j_a_1 else '❌'} J-A-1: 구조 무결성 (H-1~H-5)")
    print(f"  {'✅' if j_a_2 else '❌'} J-A-2: FAIL_REASON 불변성")
    print(f"  {'✅' if j_a_3 else '❌'} J-A-3: 전이 언어 불변성")
    print(f"  {'✅' if j_a_4 else '❌'} J-A-4: 세션 통계 안정성")
    
    print(f"\n🎯 Phase J-A Status: {'✅ PASSED' if all_pass else '❌ FAILED'}")
    
    if all_pass:
        print("""
======================================================================
🎉 PHASE J-A PASSED
======================================================================

"Alpha observation does not contaminate decision structure.
 Alpha can be safely elevated from observer to gate."

→ Phase J-B (Alpha-Gated Force) 진행 가능
======================================================================
""")
    else:
        print("""
======================================================================
⚠️ PHASE J-A NEEDS REVIEW
======================================================================

Alpha 삽입이 구조에 영향을 미쳤습니다.
원인 분석 후 재시도가 필요합니다.
======================================================================
""")
    
    final_report = {
        "analysis_time": datetime.now().isoformat(),
        "phase": "J-A",
        "purpose": "ALPHA INJECTION DRY-RUN",
        "total_sessions": len(sessions),
        "bucket_analysis": bucket_analysis,
        "stability_check": stability,
        "structure_diff": structure_diff,
        "criteria": {
            "J-A-1_structure_integrity": j_a_1,
            "J-A-2_fail_reason_invariance": j_a_2,
            "J-A-3_transition_invariance": j_a_3,
            "J-A-4_session_stats_stability": j_a_4
        },
        "phase_j_a_passed": all_pass,
        "conclusion": "Alpha can be safely elevated from observer to gate" if all_pass else "Alpha injection needs review"
    }
    
    report_path = '/tmp/phase_j_a_final_report.json'
    with open(report_path, 'w') as f:
        json.dump(final_report, f, indent=2, default=str)
    
    print(f"\n📄 Report saved to: {report_path}")
    
    return final_report


def main():
    return run_phase_j_a_analysis()


if __name__ == "__main__":
    main()
