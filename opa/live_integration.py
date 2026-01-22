"""
OPA Live Integration - 실시간 파이프라인 통합

파이프라인:
TradingView Webhook
   ↓
Raw Candle / Signal Payload
   ↓
AI 판단 (Signal Engine + Validation)
   ↓
🛡️ OPA (Authority Check) ← 여기!
   ↓
Telegram Signal Send (or Silence)

⚠️ 핵심 원칙:
1. OPA는 텔레그램 보내기 직전에 한 번만 호출
2. OPA DENY = 완전 침묵 (행동 변경 X)
3. 텔레그램 실패 ≠ OPA 실패 (분리!)
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

from .opa_engine import OPAEngine, OPARequest, OPAResponse, Authority
from .mode_switch import OperationMode
from .zone_loss_counter import ZoneLossCounter, ZoneKey, calculate_zone_id
from .authority_rules import estimate_slippage


class ExecutionResult(Enum):
    """실행 결과 (OPA와 분리!)"""
    SUCCESS = "success"
    TELEGRAM_FAILED = "telegram_failed"
    NETWORK_ERROR = "network_error"
    NOT_EXECUTED = "not_executed"  # OPA DENY


@dataclass
class LiveOPAResult:
    """실시간 OPA 결과"""
    opa_decision: Authority      # OPA 판정
    execution_result: ExecutionResult  # 실행 결과 (분리!)
    signal_id: str
    timestamp: datetime
    details: Optional[str] = None


class LiveOPAIntegration:
    """
    실시간 OPA 통합 클래스
    
    특징:
    - 웹훅당 OPA 1회만 호출
    - Zone 기준 손실 추적
    - 보수적 슬리피지 추정
    - 수동 모드 전환 지원
    - 텔레그램 실패와 OPA 분리
    """
    
    def __init__(self, mode: OperationMode = OperationMode.NORMAL):
        self.opa_engine = OPAEngine(mode=mode)
        self.zone_counter = ZoneLossCounter(auto_reset_hours=24)
        self.manual_override = False
        self.call_count = 0
        self.last_call_id: Optional[str] = None
    
    def check_and_execute(
        self,
        signal_id: str,
        signal_name: str,
        state: str,
        theta: int,
        direction: str,
        current_price: float,
        spread: float = 1.0,
        zone_size: float = 100.0,
    ) -> LiveOPAResult:
        """
        실시간 OPA 체크 및 실행 결정
        
        ⚠️ 이 함수는 텔레그램 직전에 한 번만 호출!
        """
        now = datetime.now()
        
        # 중복 호출 방지
        call_id = f"{signal_id}_{now.strftime('%Y%m%d%H%M%S')}"
        if call_id == self.last_call_id:
            return LiveOPAResult(
                opa_decision=Authority.DENY,
                execution_result=ExecutionResult.NOT_EXECUTED,
                signal_id=signal_id,
                timestamp=now,
                details="Duplicate call blocked"
            )
        self.last_call_id = call_id
        self.call_count += 1
        
        # Zone 계산
        zone_id = calculate_zone_id(current_price, zone_size)
        zone = ZoneKey(state=state, direction=direction, zone_id=zone_id)
        
        # 연속 손실 조회
        consecutive_loss = self.zone_counter.get_consecutive_loss(zone)
        
        # 슬리피지 추정 (보수적)
        slippage = estimate_slippage(spread)
        
        # OPA 요청 생성
        request = OPARequest(
            signal_name=signal_name,
            state_certified=theta >= 1,
            theta=theta,
            consecutive_loss_same_zone=consecutive_loss,
            slippage=slippage,
            spread=spread,
            timestamp=now,
        )
        
        # OPA 판정
        response = self.opa_engine.check_authority(request)
        
        if response.authority == Authority.ALLOW:
            return LiveOPAResult(
                opa_decision=Authority.ALLOW,
                execution_result=ExecutionResult.SUCCESS,  # 텔레그램 발송 예정
                signal_id=signal_id,
                timestamp=now,
                details=f"Allowed: θ={theta}, zone={zone_id}"
            )
        else:
            return LiveOPAResult(
                opa_decision=Authority.DENY,
                execution_result=ExecutionResult.NOT_EXECUTED,
                signal_id=signal_id,
                timestamp=now,
                details=f"Denied at Layer {response.layer_failed}: {response.reason.value}"
            )
    
    def record_trade_result(
        self,
        state: str,
        direction: str,
        current_price: float,
        is_win: bool,
        zone_size: float = 100.0,
    ):
        """
        거래 결과 기록
        
        ⚠️ 텔레그램 실패는 여기서 기록하지 않음!
        오직 실제 거래 결과만 기록
        """
        zone_id = calculate_zone_id(current_price, zone_size)
        zone = ZoneKey(state=state, direction=direction, zone_id=zone_id)
        
        if is_win:
            self.zone_counter.record_win(zone)
        else:
            self.zone_counter.record_loss(zone)
    
    def set_mode(self, mode: OperationMode, manual: bool = False):
        """
        모드 설정
        
        manual=True: 수동 override (긴급 상황)
        manual=False: 자동 전환
        """
        self.manual_override = manual
        
        if mode == OperationMode.CONSERVATIVE:
            self.opa_engine.mode_controller.force_conservative(
                "Manual override" if manual else "Auto switch"
            )
        else:
            self.opa_engine.mode_controller.force_normal()
    
    def get_status(self) -> Dict[str, Any]:
        """현재 상태 조회"""
        return {
            "mode": self.opa_engine.mode_controller.current_mode.value,
            "manual_override": self.manual_override,
            "call_count": self.call_count,
            "opa_stats": self.opa_engine.get_stats(),
            "zone_stats": self.zone_counter.get_stats(),
            "zones_with_losses": self.zone_counter.get_all_zones_with_losses(),
        }
    
    def reset_daily(self):
        """일일 리셋"""
        self.zone_counter.reset_all()
        self.opa_engine.reset_stats()
        self.opa_engine.mode_controller.reset_daily()
        self.call_count = 0
        self.last_call_id = None


# 실전 통합 테스트 체크리스트
INTEGRATION_CHECKLIST = """
실전 투입 전 체크리스트:

1. ✅ 웹훅 1회 → OPA 1회만 호출되는가
   - last_call_id로 중복 호출 차단됨

2. ✅ OPA DENY 시 텔레그램이 완전 무발송되는가
   - Authority.DENY → ExecutionResult.NOT_EXECUTED

3. ✅ 연속 손실 카운트가 zone 기준으로만 증가하는가
   - ZoneKey = (state, direction, zone_id)

4. ✅ CONSERVATIVE 모드에서 non-Tier1이 완전 차단되는가
   - tier1_only=True when CONSERVATIVE

5. ✅ 텔레그램 실패가 OPA 상태에 영향 없는가
   - ExecutionResult와 OPA 판정 완전 분리
"""
