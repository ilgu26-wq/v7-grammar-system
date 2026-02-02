"""
Phase H — ENGINE HANDOFF STATISTICS
====================================

역할: 엔진 간 전이 성공/실패 계산

핵심 질문:
"엔진 A의 성공이 왜 엔진 B로 전달되지 않았는가?"

Engine Interaction Matrix:
| Case | Entry | Force | OPA | 결과        |
|------|-------|-------|-----|-------------|
| A    | 강    | 약    | 無  | 조기 종료   |
| B    | 강    | 강    | 無  | 확장 성공   |
| C    | 강    | 강    | 有  | 정상 차단   |
| D    | 약    | 강    | 無  | 진입 실패   |
"""

import json
from typing import List, Dict
from dataclasses import dataclass
from collections import defaultdict

import sys
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')
from state_session import HandoffFailReason


FORCE_MIN = 10.0
TAU_MIN = 5


@dataclass
class HandoffStats:
    """핸드오프 통계"""
    from_engine: str
    to_engine: str
    success: int = 0
    fail: int = 0
    fail_reasons: Dict[str, int] = None
    
    def __post_init__(self):
        if self.fail_reasons is None:
            self.fail_reasons = {}
    
    @property
    def total(self) -> int:
        return self.success + self.fail
    
    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total > 0 else 0
    
    def to_dict(self) -> dict:
        return {
            "from": self.from_engine,
            "to": self.to_engine,
            "success": self.success,
            "fail": self.fail,
            "total": self.total,
            "success_rate": f"{self.success_rate:.1f}%",
            "fail_reasons": self.fail_reasons
        }


class EngineHandoffAnalyzer:
    """엔진 핸드오프 분석기"""
    
    def __init__(self):
        self.stats = {
            "entry_to_force": HandoffStats("ENTRY", "FORCE"),
            "force_to_sustain": HandoffStats("FORCE", "SUSTAIN"),
            "sustain_to_exit": HandoffStats("SUSTAIN", "EXIT")
        }
        self.interaction_cases = []
    
    def analyze_sessions(self, sessions: List[Dict]) -> Dict:
        """세션별 핸드오프 분석"""
        
        for session in sessions:
            self._analyze_session(session)
        
        return self._generate_report()
    
    def _analyze_session(self, session: Dict):
        """단일 세션 분석"""
        bars = session.get('bars', [])
        if len(bars) < 2:
            return
        
        force_bars = session.get('force_bars', 0)
        avg_force = session.get('avg_force', 0)
        max_tau = session.get('max_tau', 0)
        exit_reason = session.get('exit_reason', '')
        pnl = session.get('pnl', 0)
        
        entry_strong = max_tau >= TAU_MIN
        force_strong = avg_force >= FORCE_MIN or force_bars >= 3
        opa_blocked = 'OPA' in exit_reason
        
        if entry_strong and force_strong:
            self.stats["entry_to_force"].success += 1
        elif entry_strong and not force_strong:
            self.stats["entry_to_force"].fail += 1
            fail_reason = self._determine_fail_reason(session, "entry_to_force")
            self.stats["entry_to_force"].fail_reasons[fail_reason] = \
                self.stats["entry_to_force"].fail_reasons.get(fail_reason, 0) + 1
        
        if force_strong:
            sustained = len(bars) >= 4
            if sustained:
                self.stats["force_to_sustain"].success += 1
            else:
                self.stats["force_to_sustain"].fail += 1
                fail_reason = self._determine_fail_reason(session, "force_to_sustain")
                self.stats["force_to_sustain"].fail_reasons[fail_reason] = \
                    self.stats["force_to_sustain"].fail_reasons.get(fail_reason, 0) + 1
        
        case = self._classify_interaction_case(entry_strong, force_strong, opa_blocked, pnl)
        self.interaction_cases.append({
            "session_id": session.get('session_id'),
            "case": case,
            "entry_strong": entry_strong,
            "force_strong": force_strong,
            "opa_blocked": opa_blocked,
            "pnl": pnl,
            "exit_reason": exit_reason
        })
    
    def _determine_fail_reason(self, session: Dict, handoff_type: str) -> str:
        """FAIL_REASON 결정"""
        exit_reason = session.get('exit_reason', '')
        avg_force = session.get('avg_force', 0)
        max_tau = session.get('max_tau', 0)
        
        if 'OPA' in exit_reason:
            return HandoffFailReason.OPA_BLOCK.value
        
        if 'TAU' in exit_reason:
            return HandoffFailReason.TAU_DROP.value
        
        if 'FORCE_DECAY' in exit_reason:
            return HandoffFailReason.FORCE_RESET.value
        
        if avg_force < FORCE_MIN:
            return HandoffFailReason.FORCE_NOT_READY.value
        
        return HandoffFailReason.ENTRY_ORPHAN.value
    
    def _classify_interaction_case(self, entry_strong: bool, force_strong: bool, 
                                   opa_blocked: bool, pnl: float) -> str:
        """Engine Interaction Case 분류"""
        if entry_strong and not force_strong and not opa_blocked:
            return "A"
        elif entry_strong and force_strong and not opa_blocked:
            return "B"
        elif entry_strong and force_strong and opa_blocked:
            return "C"
        elif not entry_strong and force_strong:
            return "D"
        else:
            return "E"
    
    def _generate_report(self) -> Dict:
        """핸드오프 리포트 생성"""
        case_dist = defaultdict(int)
        case_pnl = defaultdict(list)
        
        for ic in self.interaction_cases:
            case_dist[ic['case']] += 1
            case_pnl[ic['case']].append(ic['pnl'])
        
        case_summary = {}
        for case, count in case_dist.items():
            pnls = case_pnl[case]
            case_summary[case] = {
                "count": count,
                "avg_pnl": sum(pnls) / len(pnls) if pnls else 0,
                "interpretation": self._case_interpretation(case)
            }
        
        return {
            "handoff_matrix": {k: v.to_dict() for k, v in self.stats.items()},
            "interaction_cases": case_summary,
            "total_sessions": len(self.interaction_cases),
            "case_descriptions": {
                "A": "Entry 강 + Force 약 + OPA 無 → 조기 종료",
                "B": "Entry 강 + Force 강 + OPA 無 → 확장 성공",
                "C": "Entry 강 + Force 강 + OPA 有 → 정상 차단",
                "D": "Entry 약 + Force 강 → 진입 실패",
                "E": "기타"
            }
        }
    
    def _case_interpretation(self, case: str) -> str:
        interpretations = {
            "A": "Entry 정확, Force 연결 실패 → 핸드오프 규칙 필요",
            "B": "정상 세션 흐름 → 목표 패턴",
            "C": "OPA가 리스크 차단 → 의도된 종료",
            "D": "Entry 조건 미충족 → 진입 필터 검토",
            "E": "분류 불가 → 추가 분석 필요"
        }
        return interpretations.get(case, "Unknown")


def main():
    sessions_path = '/tmp/phase_h_sessions.json'
    try:
        with open(sessions_path, 'r') as f:
            sessions = json.load(f)
    except FileNotFoundError:
        print("❌ Sessions file not found. Run extract_sessions.py first.")
        return
    
    analyzer = EngineHandoffAnalyzer()
    report = analyzer.analyze_sessions(sessions)
    
    print("\n" + "=" * 60)
    print("ENGINE HANDOFF STATISTICS — Phase H")
    print("=" * 60)
    
    print("\n📊 Handoff Matrix:")
    for name, stats in report['handoff_matrix'].items():
        print(f"\n  {stats['from']} → {stats['to']}:")
        print(f"    Success: {stats['success']}, Fail: {stats['fail']}")
        print(f"    Success Rate: {stats['success_rate']}")
        if stats['fail_reasons']:
            print(f"    Fail Reasons: {stats['fail_reasons']}")
    
    print("\n📈 Interaction Cases:")
    for case, data in report['interaction_cases'].items():
        print(f"\n  Case {case}: {report['case_descriptions'].get(case, '')}")
        print(f"    Count: {data['count']}")
        print(f"    Avg PnL: {data['avg_pnl']:.2f}")
        print(f"    Interpretation: {data['interpretation']}")
    
    output_path = '/tmp/phase_h_handoff_stats.json'
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n\nReport saved to: {output_path}")
    return report


if __name__ == "__main__":
    main()
