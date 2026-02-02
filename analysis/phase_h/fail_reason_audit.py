"""
Phase H — FAIL_REASON AUDIT (무결성 핵심)
=========================================

역할: FAIL_REASON enum 완전성 검증

핵심 원칙:
- FAIL_REASON은 결과가 아니라 관측치다
- FAIL_REASON := "이 엔진이 다음 엔진으로 상태를 넘기지 못한 이유"
- 미정의 값 발견 시 → 즉시 FAIL

Integrity Rules:
- H-4: FAIL_REASON은 enum 외 값 불가
- H-5: 엔진별 성공률 합계는 100%
"""

import json
from typing import List, Dict, Set
from collections import defaultdict

import sys
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')
from state_session import HandoffFailReason, ExitType


KNOWN_FAIL_REASONS: Set[str] = {fr.value for fr in HandoffFailReason}

KNOWN_EXIT_TYPES: Set[str] = {et.value for et in ExitType}


class FailReasonAuditor:
    """FAIL_REASON 무결성 감사"""
    
    def __init__(self):
        self.unknown_fail_reasons: List[str] = []
        self.unknown_exit_types: List[str] = []
        self.fail_reason_dist: Dict[str, int] = defaultdict(int)
        self.exit_type_dist: Dict[str, int] = defaultdict(int)
        self.audit_passed = True
        self.errors: List[str] = []
    
    def audit_sessions(self, sessions: List[Dict]) -> Dict:
        """세션 데이터 감사"""
        print("\n" + "=" * 60)
        print("FAIL_REASON AUDIT — Phase H Integrity Check")
        print("=" * 60)
        
        for session in sessions:
            self._audit_session(session)
        
        self._validate_enum_completeness()
        
        return self._generate_report()
    
    def _audit_session(self, session: Dict):
        """단일 세션 감사"""
        exit_reason = session.get('exit_reason', '')
        
        if exit_reason:
            self.exit_type_dist[exit_reason] += 1
            
            if exit_reason not in KNOWN_EXIT_TYPES:
                self.unknown_exit_types.append(exit_reason)
                self.audit_passed = False
                self.errors.append(f"H-4 violation: Unknown exit_type '{exit_reason}'")
        
        handoffs = session.get('handoffs', [])
        for handoff in handoffs:
            fail_reason = handoff.get('fail_reason')
            if fail_reason:
                self.fail_reason_dist[fail_reason] += 1
                
                if fail_reason not in KNOWN_FAIL_REASONS:
                    self.unknown_fail_reasons.append(fail_reason)
                    self.audit_passed = False
                    self.errors.append(f"H-4 violation: Unknown fail_reason '{fail_reason}'")
    
    def _validate_enum_completeness(self):
        """Enum 완전성 검증"""
        print("\n📋 Known FAIL_REASON enum values:")
        for fr in sorted(KNOWN_FAIL_REASONS):
            observed = self.fail_reason_dist.get(fr, 0)
            status = "✅" if observed > 0 else "⚪"
            print(f"  {status} {fr}: {observed}")
        
        print("\n📋 Known EXIT_TYPE enum values:")
        for et in sorted(KNOWN_EXIT_TYPES):
            observed = self.exit_type_dist.get(et, 0)
            status = "✅" if observed > 0 else "⚪"
            print(f"  {status} {et}: {observed}")
    
    def _generate_report(self) -> Dict:
        """감사 리포트 생성"""
        print("\n" + "-" * 40)
        
        if self.audit_passed:
            print("✅ AUDIT PASSED — All values are within known enums")
        else:
            print(f"❌ AUDIT FAILED — {len(self.errors)} violations found")
            for err in self.errors[:10]:
                print(f"  - {err}")
        
        report = {
            "audit_passed": self.audit_passed,
            "errors": self.errors,
            "unknown_fail_reasons": list(set(self.unknown_fail_reasons)),
            "unknown_exit_types": list(set(self.unknown_exit_types)),
            "fail_reason_distribution": dict(self.fail_reason_dist),
            "exit_type_distribution": dict(self.exit_type_dist),
            "known_fail_reasons": list(KNOWN_FAIL_REASONS),
            "known_exit_types": list(KNOWN_EXIT_TYPES)
        }
        
        return report


def audit_handoff_stats(handoff_stats: Dict) -> bool:
    """핸드오프 통계 감사"""
    print("\n" + "=" * 60)
    print("HANDOFF STATS AUDIT")
    print("=" * 60)
    
    errors = []
    
    for handoff_name, stats in handoff_stats.get('handoff_matrix', {}).items():
        fail_reasons = stats.get('fail_reasons', {})
        for reason in fail_reasons:
            if reason not in KNOWN_FAIL_REASONS:
                errors.append(f"Unknown fail_reason in {handoff_name}: {reason}")
    
    if errors:
        print(f"❌ {len(errors)} violations found")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("✅ All handoff fail_reasons are valid")
        return True


def main():
    sessions_path = '/tmp/phase_h_sessions.json'
    handoff_path = '/tmp/phase_h_handoff_stats.json'
    
    try:
        with open(sessions_path, 'r') as f:
            sessions = json.load(f)
    except FileNotFoundError:
        print("❌ Sessions file not found. Run extract_sessions.py first.")
        return
    
    auditor = FailReasonAuditor()
    session_report = auditor.audit_sessions(sessions)
    
    try:
        with open(handoff_path, 'r') as f:
            handoff_stats = json.load(f)
        handoff_valid = audit_handoff_stats(handoff_stats)
        session_report['handoff_audit_passed'] = handoff_valid
    except FileNotFoundError:
        print("\n⚠️ Handoff stats not found. Run engine_handoff_stats.py first.")
        session_report['handoff_audit_passed'] = None
    
    output_path = '/tmp/phase_h_audit_report.json'
    with open(output_path, 'w') as f:
        json.dump(session_report, f, indent=2)
    
    print(f"\n\nAudit report saved to: {output_path}")
    
    return session_report


if __name__ == "__main__":
    main()
