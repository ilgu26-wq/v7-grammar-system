"""
StateSession — 상태 기반 실패 관리 시스템의 핵심 구조

핵심 철학:
- 실패 = "틀림"이 아니라 "명명된 종료"
- 4차원 메트릭스 = 실패 흡수 장치
- 질문 변화: "왜 졌지?" → "어떤 궤적에서 종료됐지?"

StateSession = ENTER 이후 하나의 상태 생애주기
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime
import json


class ExitType(Enum):
    """
    EXIT를 "실패"가 아닌 종료 타입으로 분해
    모든 실패는 이름을 가진다
    """
    FORCE_DECAY = "EXIT_FORCE_DECAY"
    TAU_COLLAPSE = "EXIT_TAU_COLLAPSE"
    TIME_EXHAUST = "EXIT_TIME_EXHAUST"
    OPA_BLOCK = "EXIT_OPA_BLOCK"
    ALPHA_REVERSAL = "EXIT_ALPHA_REVERSAL"
    PROFIT_TAKE = "EXIT_PROFIT_TAKE"
    INVALIDATION = "EXIT_INVALIDATION"
    MAE_EXCESS = "EXIT_MAE_EXCESS"
    END_OF_DATA = "EXIT_END_OF_DATA"
    MAX_BARS = "EXIT_MAX_BARS"
    HANDOFF_MISSING = "EXIT_HANDOFF_MISSING"


class HandoffFailReason(Enum):
    """
    ENGINE_HANDOFF_FAIL_REASON 표준 정의 v1.0
    
    우선순위 (가장 구조적인 실패 하나만 기록):
    1. OPA_BLOCK
    2. ENERGY_EXHAUST
    3. TAU_DROP
    4. FORCE_RESET
    5. FORCE_NOT_READY
    6. ENTRY_ORPHAN
    
    핵심 원칙: "우리는 HOLD를 만들려는 게 아니라 EXIT를 설명하려고 한다"
    """
    OPA_BLOCK = "OPA_BLOCK"
    ENERGY_EXHAUST = "ENERGY_EXHAUST"
    TAU_DROP = "TAU_DROP"
    FORCE_RESET = "FORCE_RESET"
    FORCE_NOT_READY = "FORCE_NOT_READY"
    ENTRY_ORPHAN = "ENTRY_ORPHAN"
    NONE = "NONE"


@dataclass
class HandoffRecord:
    """엔진 핸드오프 기록"""
    from_engine: str
    to_engine: str
    success: bool
    fail_reason: HandoffFailReason = HandoffFailReason.NONE
    bar_index: int = 0
    force_at_handoff: float = 0.0
    tau_at_handoff: int = 0
    
    def to_dict(self) -> dict:
        return {
            "from": self.from_engine,
            "to": self.to_engine,
            "success": self.success,
            "fail_reason": self.fail_reason.value if not self.success else None,
            "bar_index": self.bar_index,
            "force": self.force_at_handoff,
            "tau": self.tau_at_handoff
        }


class ActionLayer(Enum):
    """Action 전이 상태"""
    WAIT = "WAIT"
    OBSERVE = "OBSERVE"
    ENTER = "ENTER"
    HOLD = "HOLD"
    HOLD_SMALL = "HOLD_SMALL"
    HOLD_EXTEND = "HOLD_EXTEND"
    EXIT = "EXIT"


@dataclass
class EntrySnapshot:
    """ENTER 시점 스냅샷"""
    bar_idx: int
    timestamp: str
    price: float
    tau: int
    dc: float
    delta: float
    force: float
    direction: str
    alpha_flags: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "bar_idx": self.bar_idx,
            "timestamp": self.timestamp,
            "price": self.price,
            "tau": self.tau,
            "dc": self.dc,
            "delta": self.delta,
            "force": self.force,
            "direction": self.direction,
            "alpha_flags": self.alpha_flags
        }


@dataclass
class TrajectoryPoint:
    """궤적 내 단일 포인트 (4차원)"""
    bar_idx: int
    tau: int
    force: float
    action: str
    price: float
    mfe: float = 0.0
    mae: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "bar_idx": self.bar_idx,
            "tau": self.tau,
            "force": self.force,
            "action": self.action,
            "price": self.price,
            "mfe": round(self.mfe, 2),
            "mae": round(self.mae, 2)
        }


@dataclass
class ExitSnapshot:
    """EXIT 시점 스냅샷"""
    bar_idx: int
    timestamp: str
    exit_type: ExitType
    price: float
    tau: int
    force: float
    pnl: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "bar_idx": self.bar_idx,
            "timestamp": self.timestamp,
            "exit_type": self.exit_type.value,
            "price": self.price,
            "tau": self.tau,
            "force": self.force,
            "pnl": round(self.pnl, 2)
        }


@dataclass
class StateSession:
    """
    ENTER 이후 하나의 상태 생애주기
    
    4차원 메트릭스:
    - τ (State Maturity): time-series
    - Force (물리 에너지): integral + slope
    - Time (세션 지속): duration
    - Action (의사결정): transition graph
    """
    session_id: int
    entry: EntrySnapshot
    trajectory: List[TrajectoryPoint] = field(default_factory=list)
    exit: Optional[ExitSnapshot] = None
    
    engine_contributions: Dict = field(default_factory=dict)
    
    def duration(self) -> int:
        return len(self.trajectory)
    
    def max_tau(self) -> int:
        if not self.trajectory:
            return self.entry.tau
        return max(p.tau for p in self.trajectory)
    
    def integrated_energy(self) -> float:
        return sum(p.force for p in self.trajectory)
    
    def avg_force(self) -> float:
        if not self.trajectory:
            return 0
        return sum(p.force for p in self.trajectory) / len(self.trajectory)
    
    def force_slope(self) -> float:
        if len(self.trajectory) < 2:
            return 0
        first = self.trajectory[0].force
        last = self.trajectory[-1].force
        return (last - first) / len(self.trajectory)
    
    def mfe(self) -> float:
        if not self.trajectory:
            return 0
        return max(p.mfe for p in self.trajectory)
    
    def mae(self) -> float:
        if not self.trajectory:
            return 0
        return max(p.mae for p in self.trajectory)
    
    def action_sequence(self) -> List[str]:
        return [p.action for p in self.trajectory]
    
    def action_transitions(self) -> Dict[str, int]:
        transitions = {}
        seq = self.action_sequence()
        for i in range(len(seq) - 1):
            key = f"{seq[i]}→{seq[i+1]}"
            transitions[key] = transitions.get(key, 0) + 1
        return transitions
    
    def has_extend(self) -> bool:
        return any(p.action == "HOLD_EXTEND" for p in self.trajectory)
    
    def has_small(self) -> bool:
        return any(p.action == "HOLD_SMALL" for p in self.trajectory)
    
    def session_ev(self) -> float:
        if self.exit is None:
            return 0
        return self.exit.pnl
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "duration": self.duration(),
            "entry": self.entry.to_dict(),
            "trajectory_summary": {
                "length": len(self.trajectory),
                "max_tau": self.max_tau(),
                "integrated_energy": round(self.integrated_energy(), 2),
                "avg_force": round(self.avg_force(), 2),
                "force_slope": round(self.force_slope(), 4),
                "mfe": round(self.mfe(), 2),
                "mae": round(self.mae(), 2),
                "has_extend": self.has_extend(),
                "has_small": self.has_small()
            },
            "action_sequence": self.action_sequence()[:10],
            "action_transitions": self.action_transitions(),
            "exit": self.exit.to_dict() if self.exit else None,
            "session_ev": round(self.session_ev(), 2),
            "engine_contributions": self.engine_contributions
        }


class EngineRole(Enum):
    """엔진 역할 분류"""
    STATE_JUDGMENT = "상태 판정"
    DIRECTION = "방향성"
    PERSISTENCE = "지속 조건"
    PERMISSION = "권한 봉인"
    TIME_TRACKING = "시간 추적"


@dataclass
class EngineAnalysis:
    """
    엔진별 분석 템플릿
    
    질문: 어떤 엔진 조합에서 EXIT_PROFIT이 구조적으로 나오는가
    """
    engine_name: str
    role: EngineRole
    dimension: str
    
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    failure_types: List[ExitType] = field(default_factory=list)
    required_partners: List[str] = field(default_factory=list)
    
    sessions_involved: int = 0
    win_rate: float = 0.0
    avg_ev: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "engine_name": self.engine_name,
            "role": self.role.value,
            "dimension": self.dimension,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "failure_types": [f.value for f in self.failure_types],
            "required_partners": self.required_partners,
            "sessions_involved": self.sessions_involved,
            "win_rate": f"{self.win_rate:.1f}%",
            "avg_ev": round(self.avg_ev, 2)
        }


ENGINE_PROFILES = {
    "V7_Grammar": EngineAnalysis(
        engine_name="V7_Grammar",
        role=EngineRole.STATE_JUDGMENT,
        dimension="τ (State Maturity)",
        strengths=["τ 기반 상태 판별 정확", "진입 타이밍 75% 정확"],
        weaknesses=["시간 지속 개념 없음", "HOLD 판단 불가"],
        failure_types=[ExitType.TIME_EXHAUST, ExitType.TAU_COLLAPSE],
        required_partners=["Phase_Tracker", "Force_Engine"]
    ),
    "Entry_Alpha": EngineAnalysis(
        engine_name="Entry_Alpha",
        role=EngineRole.DIRECTION,
        dimension="Direction",
        strengths=["방향성 순간 정확도 높음"],
        weaknesses=["지속력 없음", "반전 취약"],
        failure_types=[ExitType.ALPHA_REVERSAL],
        required_partners=["Force_Engine", "OPA"]
    ),
    "Force_Engine": EngineAnalysis(
        engine_name="Force_Engine",
        role=EngineRole.PERSISTENCE,
        dimension="Force (물리 에너지)",
        strengths=["HOLD/EXTEND의 필요조건 제공", "에너지 측정"],
        weaknesses=["진입 판단 불가", "단독 무의미"],
        failure_types=[ExitType.FORCE_DECAY],
        required_partners=["Entry_Alpha", "V7_Grammar"]
    ),
    "OPA": EngineAnalysis(
        engine_name="OPA",
        role=EngineRole.PERMISSION,
        dimension="Permission Gate",
        strengths=["실패 봉인", "리스크 차단"],
        weaknesses=["수익 창출 불가", "기회 비용"],
        failure_types=[ExitType.OPA_BLOCK],
        required_partners=["All Engines"]
    ),
    "Phase_Tracker": EngineAnalysis(
        engine_name="Phase_Tracker",
        role=EngineRole.TIME_TRACKING,
        dimension="Time (세션 지속)",
        strengths=["세션 궤적 추적", "Duration 관리"],
        weaknesses=["판단 불가", "수동적"],
        failure_types=[ExitType.TIME_EXHAUST, ExitType.MAX_BARS],
        required_partners=["V7_Grammar", "Force_Engine"]
    )
}


def create_session_from_enter(
    session_id: int,
    bar_idx: int,
    timestamp: str,
    price: float,
    tau: int,
    dc: float,
    delta: float,
    force: float,
    direction: str,
    alpha_flags: Dict = None
) -> StateSession:
    """ENTER 시점에 세션 생성"""
    entry = EntrySnapshot(
        bar_idx=bar_idx,
        timestamp=timestamp,
        price=price,
        tau=tau,
        dc=dc,
        delta=delta,
        force=force,
        direction=direction,
        alpha_flags=alpha_flags or {}
    )
    return StateSession(session_id=session_id, entry=entry)


def add_trajectory_point(
    session: StateSession,
    bar_idx: int,
    tau: int,
    force: float,
    action: str,
    price: float
) -> None:
    """세션에 궤적 포인트 추가"""
    entry_price = session.entry.price
    direction = session.entry.direction
    
    if direction == "HIGH":
        mfe = max(0, price - entry_price)
        mae = max(0, entry_price - price)
    else:
        mfe = max(0, entry_price - price)
        mae = max(0, price - entry_price)
    
    point = TrajectoryPoint(
        bar_idx=bar_idx,
        tau=tau,
        force=force,
        action=action,
        price=price,
        mfe=mfe,
        mae=mae
    )
    session.trajectory.append(point)


def close_session(
    session: StateSession,
    bar_idx: int,
    timestamp: str,
    exit_type: ExitType,
    price: float,
    tau: int,
    force: float
) -> None:
    """세션 종료"""
    entry_price = session.entry.price
    direction = session.entry.direction
    
    if direction == "HIGH":
        pnl = price - entry_price
    else:
        pnl = entry_price - price
    
    session.exit = ExitSnapshot(
        bar_idx=bar_idx,
        timestamp=timestamp,
        exit_type=exit_type,
        price=price,
        tau=tau,
        force=force,
        pnl=pnl
    )


class SessionAnalyzer:
    """세션 집합 분석기"""
    
    def __init__(self):
        self.sessions: List[StateSession] = []
    
    def add_session(self, session: StateSession):
        self.sessions.append(session)
    
    def exit_type_distribution(self) -> Dict[str, int]:
        dist = {}
        for s in self.sessions:
            if s.exit:
                et = s.exit.exit_type.value
                dist[et] = dist.get(et, 0) + 1
        return dist
    
    def avg_metrics(self) -> Dict:
        if not self.sessions:
            return {}
        
        durations = [s.duration() for s in self.sessions]
        taus = [s.max_tau() for s in self.sessions]
        energies = [s.integrated_energy() for s in self.sessions]
        evs = [s.session_ev() for s in self.sessions if s.exit]
        
        winners = [s for s in self.sessions if s.exit and s.exit.pnl > 0]
        
        return {
            "total_sessions": len(self.sessions),
            "avg_duration": round(sum(durations) / len(durations), 1),
            "avg_max_tau": round(sum(taus) / len(taus), 1),
            "avg_integrated_energy": round(sum(energies) / len(energies), 1),
            "avg_session_ev": round(sum(evs) / len(evs), 2) if evs else 0,
            "total_ev": round(sum(evs), 2) if evs else 0,
            "win_rate": f"{len(winners) / len(self.sessions) * 100:.1f}%",
            "has_extend_pct": f"{len([s for s in self.sessions if s.has_extend()]) / len(self.sessions) * 100:.1f}%",
            "has_small_pct": f"{len([s for s in self.sessions if s.has_small()]) / len(self.sessions) * 100:.1f}%"
        }
    
    def engine_contribution_analysis(self) -> Dict:
        """엔진별 기여도 분석"""
        results = {}
        
        for name, profile in ENGINE_PROFILES.items():
            profile.sessions_involved = len(self.sessions)
            
            relevant_exits = [
                s for s in self.sessions 
                if s.exit and s.exit.exit_type in profile.failure_types
            ]
            
            profile.win_rate = len([s for s in self.sessions if s.exit and s.exit.pnl > 0]) / len(self.sessions) * 100 if self.sessions else 0
            profile.avg_ev = sum(s.session_ev() for s in self.sessions) / len(self.sessions) if self.sessions else 0
            
            results[name] = {
                **profile.to_dict(),
                "exits_caused": len(relevant_exits)
            }
        
        return results
    
    def generate_report(self) -> Dict:
        return {
            "timestamp": datetime.now().isoformat(),
            "metrics": self.avg_metrics(),
            "exit_distribution": self.exit_type_distribution(),
            "engine_analysis": self.engine_contribution_analysis(),
            "sessions": [s.to_dict() for s in self.sessions[:20]]
        }


if __name__ == "__main__":
    print("=" * 70)
    print("STATE SESSION SCHEMA — 실패 관리 시스템")
    print("=" * 70)
    
    print("\n📋 EXIT Types (명명된 종료):")
    for et in ExitType:
        print(f"  - {et.value}")
    
    print("\n🔧 Engine Profiles:")
    for name, profile in ENGINE_PROFILES.items():
        print(f"\n  {name}:")
        print(f"    Role: {profile.role.value}")
        print(f"    Dimension: {profile.dimension}")
        print(f"    Strengths: {profile.strengths[:2]}")
        print(f"    Failure Types: {[f.value for f in profile.failure_types]}")
        print(f"    Partners: {profile.required_partners}")
    
    print("\n" + "=" * 70)
    print("Schema ready for integration")
    print("=" * 70)
