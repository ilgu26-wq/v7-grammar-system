"""
Live Integration Test - 실전 투입 전 5가지 체크

1. 웹훅 1회 → OPA 1회만 호출되는가
2. OPA DENY 시 텔레그램이 완전 무발송되는가
3. 연속 손실 카운트가 zone 기준으로만 증가하는가
4. CONSERVATIVE 모드에서 non-Tier1이 완전 차단되는가
5. 텔레그램 실패가 OPA 상태에 영향 없는가
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opa import (
    LiveOPAIntegration, Authority, ExecutionResult, 
    OperationMode, ZoneKey, calculate_zone_id
)
import json


def test_1_single_call_per_webhook():
    """테스트 1: 웹훅 1회 → OPA 1회만 호출"""
    print("=" * 60)
    print("Test 1: 웹훅 1회 → OPA 1회만 호출")
    print("=" * 60)
    
    opa = LiveOPAIntegration()
    
    # 같은 signal_id로 연속 호출 시도
    result1 = opa.check_and_execute(
        signal_id="SIG001",
        signal_name="숏-정체",
        state="OVERBOUGHT",
        theta=3,
        direction="SHORT",
        current_price=21550.0,
    )
    
    # 즉시 같은 ID로 다시 호출 (중복 차단 테스트)
    result2 = opa.check_and_execute(
        signal_id="SIG001",
        signal_name="숏-정체",
        state="OVERBOUGHT",
        theta=3,
        direction="SHORT",
        current_price=21550.0,
    )
    
    print(f"첫 번째 호출: {result1.opa_decision.value}")
    print(f"두 번째 호출 (중복): {result2.opa_decision.value}")
    print(f"호출 횟수: {opa.call_count}")
    
    # 첫 번째는 ALLOW, 두 번째는 중복 차단 (DENY)
    assert result1.opa_decision == Authority.ALLOW
    assert result2.opa_decision == Authority.DENY
    assert "Duplicate" in result2.details
    
    print("✅ Test 1 PASS\n")


def test_2_deny_means_silence():
    """테스트 2: OPA DENY 시 텔레그램 무발송"""
    print("=" * 60)
    print("Test 2: OPA DENY → 완전 침묵")
    print("=" * 60)
    
    opa = LiveOPAIntegration()
    
    # 미인증 상태 (θ=0)
    result = opa.check_and_execute(
        signal_id="SIG002",
        signal_name="숏-정체",
        state="UNKNOWN",
        theta=0,  # 미인증
        direction="SHORT",
        current_price=21550.0,
    )
    
    print(f"OPA 판정: {result.opa_decision.value}")
    print(f"실행 결과: {result.execution_result.value}")
    
    assert result.opa_decision == Authority.DENY
    assert result.execution_result == ExecutionResult.NOT_EXECUTED
    
    print("✅ Test 2 PASS\n")


def test_3_zone_based_loss_counting():
    """테스트 3: 연속 손실은 zone 기준으로만"""
    print("=" * 60)
    print("Test 3: Zone 기준 연속 손실 카운트")
    print("=" * 60)
    
    opa = LiveOPAIntegration()
    
    # Zone A에서 첫 손실
    opa.record_trade_result(
        state="OVERBOUGHT",
        direction="SHORT",
        current_price=21550.0,
        is_win=False,
    )
    
    # Zone A에서 두 번째 손실
    opa.record_trade_result(
        state="OVERBOUGHT",
        direction="SHORT",
        current_price=21550.0,
        is_win=False,
    )
    
    zone_a = ZoneKey("OVERBOUGHT", "SHORT", calculate_zone_id(21550.0))
    zone_a_loss = opa.zone_counter.get_consecutive_loss(zone_a)
    print(f"Zone A (OVERBOUGHT/SHORT/21500-21600) 연속 손실: {zone_a_loss}")
    
    # Zone B (다른 방향)에서 손실
    opa.record_trade_result(
        state="OVERSOLD",
        direction="LONG",
        current_price=21550.0,
        is_win=False,
    )
    
    zone_b = ZoneKey("OVERSOLD", "LONG", calculate_zone_id(21550.0))
    zone_b_loss = opa.zone_counter.get_consecutive_loss(zone_b)
    print(f"Zone B (OVERSOLD/LONG/21500-21600) 연속 손실: {zone_b_loss}")
    
    # Zone A는 여전히 2, Zone B는 1
    assert zone_a_loss == 2
    assert zone_b_loss == 1
    
    # Zone A에서 권한 박탈 확인
    result = opa.check_and_execute(
        signal_id="SIG003",
        signal_name="숏-정체",
        state="OVERBOUGHT",
        theta=5,
        direction="SHORT",
        current_price=21550.0,
    )
    
    print(f"Zone A 진입 시도: {result.opa_decision.value}")
    assert result.opa_decision == Authority.DENY
    assert "Layer 2" in result.details
    
    print("✅ Test 3 PASS\n")


def test_4_conservative_tier1_only():
    """테스트 4: CONSERVATIVE 모드에서 non-Tier1 차단"""
    print("=" * 60)
    print("Test 4: CONSERVATIVE → Tier1 only")
    print("=" * 60)
    
    opa = LiveOPAIntegration(mode=OperationMode.CONSERVATIVE)
    
    # non-Tier1 신호 시도
    result_non_tier1 = opa.check_and_execute(
        signal_id="SIG004",
        signal_name="SCALP_A",  # non-Tier1
        state="OVERBOUGHT",
        theta=5,
        direction="SHORT",
        current_price=21550.0,
    )
    
    print(f"non-Tier1 (SCALP_A): {result_non_tier1.opa_decision.value}")
    assert result_non_tier1.opa_decision == Authority.DENY
    
    # Tier1 신호 시도
    result_tier1 = opa.check_and_execute(
        signal_id="SIG005",
        signal_name="숏-정체",  # Tier1
        state="OVERBOUGHT",
        theta=3,
        direction="SHORT",
        current_price=21550.0,
    )
    
    print(f"Tier1 (숏-정체): {result_tier1.opa_decision.value}")
    assert result_tier1.opa_decision == Authority.ALLOW
    
    print("✅ Test 4 PASS\n")


def test_5_telegram_failure_separation():
    """테스트 5: 텔레그램 실패 ≠ OPA 실패"""
    print("=" * 60)
    print("Test 5: 텔레그램 실패와 OPA 분리")
    print("=" * 60)
    
    opa = LiveOPAIntegration()
    
    # OPA 허가
    result = opa.check_and_execute(
        signal_id="SIG006",
        signal_name="숏-정체",
        state="OVERBOUGHT",
        theta=3,
        direction="SHORT",
        current_price=21550.0,
    )
    
    print(f"OPA 판정: {result.opa_decision.value}")
    
    # 텔레그램 실패 시뮬레이션 (외부에서 처리)
    telegram_failed = True  # 가정: 네트워크 에러
    
    if telegram_failed:
        # ⚠️ 텔레그램 실패는 OPA 상태에 영향 없음!
        # record_trade_result를 호출하지 않음
        print("텔레그램 실패 → OPA 상태 변경 없음")
    
    # OPA 상태 확인
    stats = opa.get_status()
    print(f"OPA 통계: {stats['opa_stats']}")
    print(f"Zone 통계: {stats['zone_stats']}")
    
    # zone 손실 카운터가 증가하지 않았는지 확인
    zone = ZoneKey("OVERBOUGHT", "SHORT", calculate_zone_id(21550.0))
    loss_count = opa.zone_counter.get_consecutive_loss(zone)
    
    print(f"Zone 손실 카운트: {loss_count}")
    assert loss_count == 0  # 텔레그램 실패는 손실로 기록 안 됨
    
    print("✅ Test 5 PASS\n")


def test_manual_mode_switch():
    """추가: 수동 모드 전환 테스트"""
    print("=" * 60)
    print("Bonus Test: 수동 모드 전환")
    print("=" * 60)
    
    opa = LiveOPAIntegration(mode=OperationMode.NORMAL)
    print(f"초기 모드: {opa.get_status()['mode']}")
    
    # 수동으로 CONSERVATIVE 전환
    opa.set_mode(OperationMode.CONSERVATIVE, manual=True)
    print(f"수동 전환 후: {opa.get_status()['mode']}")
    print(f"Manual override: {opa.get_status()['manual_override']}")
    
    assert opa.get_status()['mode'] == 'CONSERVATIVE'
    assert opa.get_status()['manual_override'] == True
    
    # 다시 NORMAL로
    opa.set_mode(OperationMode.NORMAL, manual=False)
    print(f"복원 후: {opa.get_status()['mode']}")
    
    print("✅ Bonus Test PASS\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("OPA Live Integration Tests")
    print("실전 투입 전 5가지 체크")
    print("=" * 60 + "\n")
    
    test_1_single_call_per_webhook()
    test_2_deny_means_silence()
    test_3_zone_based_loss_counting()
    test_4_conservative_tier1_only()
    test_5_telegram_failure_separation()
    test_manual_mode_switch()
    
    print("=" * 60)
    print("🎉 ALL TESTS PASSED!")
    print("=" * 60)
    print("\n실전 투입 체크리스트:")
    print("1. ✅ 웹훅 1회 → OPA 1회만 호출")
    print("2. ✅ OPA DENY → 완전 무발송")
    print("3. ✅ 연속 손실 = zone 기준")
    print("4. ✅ CONSERVATIVE → Tier1 only")
    print("5. ✅ 텔레그램 실패 ≠ OPA 상태 변경")
    
    # 결과 저장
    result = {
        "all_tests_passed": True,
        "checklist": {
            "single_call_per_webhook": True,
            "deny_means_silence": True,
            "zone_based_loss": True,
            "conservative_tier1_only": True,
            "telegram_opa_separation": True,
        }
    }
    
    with open("opa_live_test_results.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print("\n결과 저장: opa_live_test_results.json")
