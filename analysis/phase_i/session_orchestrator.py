"""
Phase I — SESSION ORCHESTRATOR
==============================

목적: ENTER 이후 세션이 "왜 유지되거나 끊기는지"를
엔진이 아닌 규칙으로 설명 가능하게 만드는 것

❌ 목표 아님: 수익 극대화, 파라미터 튜닝, 알파 성능 비교
⭕ 목표: 세션 지속 논리의 정합성 검증

고정 조건 (Phase H와 동일):
- Entry 조건, Force 계산, OPA, 데이터, 엔진 코드 모두 동일
- 차이는 단 하나: "언제 EXIT를 허용하느냐"
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum


class OrchestratorRule(Enum):
    """Session Orchestrator 규칙"""
    OBSERVATION_WINDOW = "R1_OBSERVATION_WINDOW"
    FORCE_PERSISTENCE = "R2_FORCE_PERSISTENCE"
    STRUCTURAL_HOLD = "R3_STRUCTURAL_HOLD"
    FORCE_ACCUMULATION = "R4_FORCE_ACCUMULATION"
    UNIFIED_EXIT = "R5_UNIFIED_EXIT"


@dataclass
class OrchestratorConfig:
    """Phase I 실험 설정 (검증 대상 가설)"""
    observation_window_bars: int = 3
    force_min: float = 10.0
    tau_min: int = 5
    dir_threshold: int = 3
    force_accumulation_gate: float = 100.0
    
    def to_dict(self) -> dict:
        return {
            "R1_observation_window_bars": self.observation_window_bars,
            "R2_force_min": self.force_min,
            "R3_tau_min": self.tau_min,
            "R3_dir_threshold": self.dir_threshold,
            "R4_force_accumulation_gate": self.force_accumulation_gate
        }


@dataclass
class SessionState:
    """세션 상태 (HOLD는 상태가 아님!)"""
    session_id: int
    bars_since_enter: int = 0
    force_accumulated: float = 0.0
    last_tau: int = 0
    last_force: float = 0.0
    dir_streak: int = 0
    can_exit: bool = False
    hold_reason: str = ""
    
    rules_blocking_exit: List[str] = None
    
    def __post_init__(self):
        if self.rules_blocking_exit is None:
            self.rules_blocking_exit = []


class SessionOrchestrator:
    """
    세션 오케스트레이터
    
    핵심 가설:
    - H-I1: ENTER 직후 즉시 종료는 구조적 단절
    - H-I2: Force는 세션 내부에서만 의미 있는 누적 변수
    - H-I3: HOLD는 EXIT 조건 미충족의 결과
    """
    
    def __init__(self, config: OrchestratorConfig = None):
        self.config = config or OrchestratorConfig()
        self.rule_applications = {rule.value: 0 for rule in OrchestratorRule}
        self.rule_blocks = {rule.value: 0 for rule in OrchestratorRule}
    
    def check_exit_allowed(self, state: SessionState, tau: int, force: float, 
                           dir_count: int) -> Tuple[bool, List[str]]:
        """
        EXIT 허용 여부 확인
        
        Rule 5 (Unified EXIT): 모든 유지 조건이 동시에 깨질 때만 EXIT
        """
        blocking_rules = []
        
        if state.bars_since_enter < self.config.observation_window_bars:
            blocking_rules.append(OrchestratorRule.OBSERVATION_WINDOW.value)
            self.rule_blocks[OrchestratorRule.OBSERVATION_WINDOW.value] += 1
        
        if force >= self.config.force_min:
            blocking_rules.append(OrchestratorRule.FORCE_PERSISTENCE.value)
            self.rule_blocks[OrchestratorRule.FORCE_PERSISTENCE.value] += 1
        
        if tau >= self.config.tau_min and abs(dir_count) >= self.config.dir_threshold:
            blocking_rules.append(OrchestratorRule.STRUCTURAL_HOLD.value)
            self.rule_blocks[OrchestratorRule.STRUCTURAL_HOLD.value] += 1
        
        can_exit = len(blocking_rules) == 0
        
        self.rule_applications[OrchestratorRule.UNIFIED_EXIT.value] += 1
        
        return can_exit, blocking_rules
    
    def check_hold_extend(self, state: SessionState) -> bool:
        """
        HOLD_EXTEND 가능 여부 확인
        
        Rule 4: ΣForce ≥ 100 → HOLD_EXTEND 가능
        """
        can_extend = state.force_accumulated >= self.config.force_accumulation_gate
        
        if can_extend:
            self.rule_applications[OrchestratorRule.FORCE_ACCUMULATION.value] += 1
        
        return can_extend
    
    def update_state(self, state: SessionState, tau: int, force: float, 
                     dir_count: int) -> SessionState:
        """세션 상태 업데이트"""
        state.bars_since_enter += 1
        state.force_accumulated += force
        state.last_tau = tau
        state.last_force = force
        state.dir_streak = dir_count
        
        can_exit, blocking = self.check_exit_allowed(state, tau, force, dir_count)
        state.can_exit = can_exit
        state.rules_blocking_exit = blocking
        
        if not can_exit:
            if OrchestratorRule.OBSERVATION_WINDOW.value in blocking:
                state.hold_reason = "OBSERVATION_WINDOW"
            elif OrchestratorRule.STRUCTURAL_HOLD.value in blocking:
                state.hold_reason = "STRUCTURAL_HOLD"
            elif OrchestratorRule.FORCE_PERSISTENCE.value in blocking:
                state.hold_reason = "FORCE_PERSISTENCE"
            else:
                state.hold_reason = "ORCHESTRATOR_ACTIVE"
        else:
            state.hold_reason = ""
        
        return state
    
    def get_statistics(self) -> Dict:
        """규칙 적용 통계"""
        return {
            "rule_applications": self.rule_applications,
            "rule_blocks": self.rule_blocks,
            "config": self.config.to_dict()
        }


PHASE_I_HYPOTHESES = {
    "H-I1": {
        "name": "Session Persistence Hypothesis",
        "statement": "ENTER 직후 즉시 종료되는 세션은 '시장 실패'가 아니라 세션 유지 규칙 부재로 인한 구조적 단절이다",
        "test": "ENTER → WAIT 100% 현상 붕괴 여부"
    },
    "H-I2": {
        "name": "Force Accumulation Hypothesis", 
        "statement": "Force는 '진입 순간'이 아니라 세션 내부에서만 의미 있는 누적 변수다",
        "test": "Force 누적이 '세션 내부 변수'로 작동 여부"
    },
    "H-I3": {
        "name": "HOLD Reinterpretation Hypothesis",
        "statement": "HOLD는 상태가 아니라 EXIT 조건이 아직 충족되지 않았다는 사실의 결과다",
        "test": "HOLD가 코드 분기 없이 자연 발생 여부"
    }
}


PHASE_I_SUCCESS_CRITERIA = [
    "ENTER → WAIT 100% 붕괴",
    "세션 평균 길이 유의미 증가",
    "Force 누적이 '세션 내부 변수'로 작동",
    "HOLD가 코드 분기 없이 자연 발생",
    "FAIL_REASON이 구조적으로 설명 가능"
]
