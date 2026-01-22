"""
OPA Main Integration - main.py와 통합하기 위한 래퍼

파이프라인:
Webhook
 → AI 판단
 → check_signal_verified()      # 신호 자격 (과거 검증)
 → 🛡️ OPA.check_authority()     # 실행 권한 (현재 상태)
 → Telegram or Silence

⚠️ 중요: check_signal_verified()를 대체하는 게 아니라 추가 계층!
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import json

from opa import (
    LiveOPAIntegration, 
    Authority, 
    ExecutionResult,
    OperationMode,
    ZoneKey,
    calculate_zone_id
)


# 전역 OPA 인스턴스 (싱글톤)
_opa_instance: Optional[LiveOPAIntegration] = None


def get_opa_instance() -> LiveOPAIntegration:
    """OPA 싱글톤 인스턴스 반환"""
    global _opa_instance
    if _opa_instance is None:
        _opa_instance = LiveOPAIntegration(mode=OperationMode.NORMAL)
    return _opa_instance


def opa_check_authority(
    signal_name: str,
    direction: str,
    current_price: float,
    theta: int = 1,
    state: str = "UNKNOWN",
    spread: float = 1.0,
    signal_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    main.py에서 호출할 OPA 권한 체크 함수
    
    Args:
        signal_name: 신호 이름 (예: "STB숏", "SCALP_A")
        direction: "SHORT" or "LONG"
        current_price: 현재 가격
        theta: 상태 인증 레벨 (기본값 1)
        state: 시장 상태 (예: "OVERBOUGHT", "OVERSOLD")
        spread: 현재 스프레드
        signal_id: 신호 ID (없으면 자동 생성)
    
    Returns:
        (allowed: bool, reason: str)
    """
    opa = get_opa_instance()
    
    # 신호 ID 생성
    if not signal_id:
        signal_id = f"{signal_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    result = opa.check_and_execute(
        signal_id=signal_id,
        signal_name=signal_name,
        state=state,
        theta=theta,
        direction=direction,
        current_price=current_price,
        spread=spread,
    )
    
    allowed = result.opa_decision == Authority.ALLOW
    reason = result.details or "OK"
    
    return allowed, reason


def opa_record_result(
    direction: str,
    current_price: float,
    is_win: bool,
    state: str = "UNKNOWN",
):
    """
    거래 결과 기록 (Zone 기준 손실 추적)
    
    ⚠️ 텔레그램 실패는 여기서 기록하지 않음!
    """
    opa = get_opa_instance()
    opa.record_trade_result(
        state=state,
        direction=direction,
        current_price=current_price,
        is_win=is_win,
    )


def opa_set_conservative(reason: str = "Manual"):
    """CONSERVATIVE 모드로 전환 (긴급 상황)"""
    opa = get_opa_instance()
    opa.set_mode(OperationMode.CONSERVATIVE, manual=True)
    print(f"🛡️ OPA: CONSERVATIVE 모드 전환 - {reason}")


def opa_set_normal():
    """NORMAL 모드로 복원"""
    opa = get_opa_instance()
    opa.set_mode(OperationMode.NORMAL, manual=False)
    print("🛡️ OPA: NORMAL 모드 복원")


def opa_get_status() -> Dict[str, Any]:
    """OPA 상태 조회"""
    opa = get_opa_instance()
    return opa.get_status()


def opa_reset_daily():
    """일일 리셋"""
    opa = get_opa_instance()
    opa.reset_daily()
    print("🛡️ OPA: 일일 리셋 완료")


# ==========================================
# main.py send_telegram_alert 통합용 래퍼
# ==========================================

def opa_gate(
    signal_type: str,
    direction: str,
    current_price: float,
    theta: int = 1,
    state: str = "UNKNOWN",
    spread: float = 1.0,
) -> Tuple[bool, str]:
    """
    send_telegram_alert 직전에 호출하는 OPA 게이트
    
    사용법 (main.py에서):
    ```python
    from v7_grammar_system.opa.main_integration import opa_gate
    
    # 기존 check_signal_verified 후에 추가
    opa_allowed, opa_reason = opa_gate(
        signal_type=signal_type,
        direction="SHORT",  # 또는 "LONG"
        current_price=21550.0,
        theta=1,  # 또는 AI에서 계산된 값
        state="OVERBOUGHT",  # 또는 현재 상태
    )
    
    if not opa_allowed:
        print(f"🛡️ OPA 차단: {opa_reason}")
        return False
    
    # 여기서 텔레그램 발송
    return send_signal(...)
    ```
    """
    return opa_check_authority(
        signal_name=signal_type,
        direction=direction,
        current_price=current_price,
        theta=theta,
        state=state,
        spread=spread,
    )


# ==========================================
# 테스트 함수
# ==========================================

def test_integration():
    """통합 테스트"""
    print("=" * 60)
    print("OPA Main Integration Test")
    print("=" * 60)
    
    # 1. 정상 신호 테스트
    allowed, reason = opa_gate(
        signal_type="STB숏",
        direction="SHORT",
        current_price=21550.0,
        theta=3,
        state="OVERBOUGHT",
    )
    print(f"\n1. 정상 신호 (STB숏, θ=3): {allowed} - {reason}")
    assert allowed == True
    
    # 2. 미인증 상태 테스트
    allowed, reason = opa_gate(
        signal_type="SCALP_A",
        direction="SHORT",
        current_price=21550.0,
        theta=0,  # 미인증
        state="UNKNOWN",
    )
    print(f"2. 미인증 상태 (θ=0): {allowed} - {reason}")
    assert allowed == False
    
    # 3. 손실 기록 후 권한 박탈 테스트
    opa_record_result("SHORT", 21550.0, is_win=False, state="OVERBOUGHT")
    opa_record_result("SHORT", 21550.0, is_win=False, state="OVERBOUGHT")  # 연속 2회
    
    allowed, reason = opa_gate(
        signal_type="STB숏",
        direction="SHORT",
        current_price=21550.0,
        theta=5,
        state="OVERBOUGHT",
    )
    print(f"3. 연속 손실 후 (2회): {allowed} - {reason}")
    assert allowed == False
    assert "Layer 2" in reason
    
    # 4. 상태 확인
    status = opa_get_status()
    print(f"\n4. OPA 상태:")
    print(f"   Mode: {status['mode']}")
    print(f"   Zone stats: {status['zone_stats']}")
    
    # 5. 리셋 후 재시도
    opa_reset_daily()
    
    allowed, reason = opa_gate(
        signal_type="STB숏",
        direction="SHORT",
        current_price=21550.0,
        theta=3,
        state="OVERBOUGHT",
    )
    print(f"5. 리셋 후 재시도: {allowed} - {reason}")
    assert allowed == True
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    test_integration()
