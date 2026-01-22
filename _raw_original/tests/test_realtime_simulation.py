"""
실시간 시뮬레이션 테스트 - 웹훅 환경 시뮬레이션

파이프라인:
Webhook → AI 판단 → check_signal_verified() → OPA → Telegram/Silence
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opa.main_integration import (
    opa_gate, 
    opa_record_result, 
    opa_get_status,
    opa_reset_daily,
    opa_set_conservative,
    opa_set_normal,
    get_opa_instance
)
from datetime import datetime
import json
import random


def simulate_webhook_payload(signal_name, direction, price, theta, state):
    """웹훅 페이로드 시뮬레이션"""
    return {
        "signal_name": signal_name,
        "direction": direction,
        "price": price,
        "theta": theta,
        "state": state,
        "timestamp": datetime.now().isoformat(),
        "spread": random.uniform(0.5, 1.5),  # 실시간 스프레드
    }


def simulate_check_signal_verified(signal_name):
    """기존 check_signal_verified 시뮬레이션"""
    VERIFIED = ["STB숏", "STB롱", "SCALP_A", "HUNT_1", "숏-정체", "숏 교집합 스팟"]
    return signal_name in VERIFIED


def simulate_telegram_send(msg):
    """텔레그램 발송 시뮬레이션 (90% 성공률)"""
    success = random.random() < 0.9
    return success


def process_webhook(payload):
    """
    전체 파이프라인 시뮬레이션
    
    Webhook → check_signal_verified → OPA → Telegram
    """
    signal_name = payload["signal_name"]
    direction = payload["direction"]
    price = payload["price"]
    theta = payload["theta"]
    state = payload["state"]
    spread = payload["spread"]
    
    # Step 1: check_signal_verified (과거 검증)
    if not simulate_check_signal_verified(signal_name):
        return {
            "status": "BLOCKED",
            "stage": "signal_verified",
            "reason": f"미검증 신호: {signal_name}"
        }
    
    # Step 2: OPA 권한 체크 (현재 상태)
    opa_allowed, opa_reason = opa_gate(
        signal_type=signal_name,
        direction=direction,
        current_price=price,
        theta=theta,
        state=state,
        spread=spread,
    )
    
    if not opa_allowed:
        return {
            "status": "BLOCKED",
            "stage": "opa",
            "reason": opa_reason
        }
    
    # Step 3: 텔레그램 발송
    telegram_success = simulate_telegram_send(f"{signal_name} @ {price}")
    
    if telegram_success:
        return {
            "status": "SENT",
            "stage": "telegram",
            "reason": f"OPA ALLOW + Telegram SUCCESS"
        }
    else:
        # ⚠️ 텔레그램 실패는 OPA 상태에 영향 없음!
        return {
            "status": "TELEGRAM_FAILED",
            "stage": "telegram",
            "reason": "Network error (OPA unaffected)"
        }


def run_realtime_simulation():
    """실시간 시뮬레이션 실행"""
    print("=" * 70)
    print("실시간 웹훅 시뮬레이션 테스트")
    print("=" * 70)
    
    # 리셋
    opa_reset_daily()
    
    # 시뮬레이션 시나리오
    scenarios = [
        # 정상 케이스
        {"signal_name": "STB숏", "direction": "SHORT", "price": 21550, "theta": 3, "state": "OVERBOUGHT"},
        {"signal_name": "STB롱", "direction": "LONG", "price": 21400, "theta": 2, "state": "OVERSOLD"},
        {"signal_name": "SCALP_A", "direction": "SHORT", "price": 21600, "theta": 1, "state": "OVERBOUGHT"},
        
        # 미인증 상태 (theta=0)
        {"signal_name": "STB숏", "direction": "SHORT", "price": 21550, "theta": 0, "state": "UNKNOWN"},
        
        # 미검증 신호
        {"signal_name": "UNKNOWN_SIGNAL", "direction": "SHORT", "price": 21550, "theta": 5, "state": "OVERBOUGHT"},
        
        # 연속 손실 시나리오
        {"signal_name": "숏-정체", "direction": "SHORT", "price": 21550, "theta": 3, "state": "OVERBOUGHT"},
    ]
    
    results = {"sent": 0, "blocked_verified": 0, "blocked_opa": 0, "telegram_failed": 0}
    
    print("\n[Phase 1: 초기 신호들]\n")
    
    for i, scenario in enumerate(scenarios[:5]):
        payload = simulate_webhook_payload(**scenario)
        result = process_webhook(payload)
        
        print(f"{i+1}. {scenario['signal_name']} (θ={scenario['theta']})")
        print(f"   → {result['status']} at {result['stage']}: {result['reason']}")
        
        if result["status"] == "SENT":
            results["sent"] += 1
        elif result["stage"] == "signal_verified":
            results["blocked_verified"] += 1
        elif result["stage"] == "opa":
            results["blocked_opa"] += 1
        elif result["status"] == "TELEGRAM_FAILED":
            results["telegram_failed"] += 1
    
    # 연속 손실 시뮬레이션
    print("\n[Phase 2: 연속 손실 발생 (같은 Zone)]\n")
    
    # 첫 손실
    opa_record_result("SHORT", 21550, is_win=False, state="OVERBOUGHT")
    print("손실 1 기록: SHORT @ 21550, OVERBOUGHT")
    
    # 두 번째 손실
    opa_record_result("SHORT", 21550, is_win=False, state="OVERBOUGHT")
    print("손실 2 기록: SHORT @ 21550, OVERBOUGHT")
    
    # 권한 박탈 확인
    payload = simulate_webhook_payload(**scenarios[5])  # 숏-정체
    result = process_webhook(payload)
    
    print(f"\n동일 Zone 재진입 시도:")
    print(f"   → {result['status']} at {result['stage']}: {result['reason']}")
    
    if result["status"] == "BLOCKED" and result["stage"] == "opa":
        results["blocked_opa"] += 1
        print("   ✅ 연속 손실 권한 박탈 작동!")
    
    # 다른 Zone은 정상
    print("\n[Phase 3: 다른 Zone 진입 시도]\n")
    
    different_zone = {"signal_name": "STB롱", "direction": "LONG", "price": 21400, "theta": 3, "state": "OVERSOLD"}
    payload = simulate_webhook_payload(**different_zone)
    result = process_webhook(payload)
    
    print(f"다른 Zone (LONG @ 21400, OVERSOLD):")
    print(f"   → {result['status']} at {result['stage']}: {result['reason']}")
    
    if result["status"] == "SENT":
        results["sent"] += 1
        print("   ✅ 다른 Zone은 정상 허용!")
    
    # CONSERVATIVE 모드 테스트
    print("\n[Phase 4: CONSERVATIVE 모드 전환]\n")
    
    opa_set_conservative("시뮬레이션 테스트")
    
    # non-Tier1 차단 확인
    non_tier1 = {"signal_name": "SCALP_A", "direction": "SHORT", "price": 21600, "theta": 5, "state": "OVERBOUGHT"}
    payload = simulate_webhook_payload(**non_tier1)
    result = process_webhook(payload)
    
    print(f"non-Tier1 (SCALP_A) in CONSERVATIVE:")
    print(f"   → {result['status']} at {result['stage']}: {result['reason']}")
    
    # 복원
    opa_set_normal()
    
    # 최종 통계
    print("\n" + "=" * 70)
    print("시뮬레이션 결과")
    print("=" * 70)
    
    status = opa_get_status()
    print(f"\n📊 처리 결과:")
    print(f"   발송 성공: {results['sent']}")
    print(f"   검증 차단: {results['blocked_verified']}")
    print(f"   OPA 차단: {results['blocked_opa']}")
    print(f"   텔레그램 실패: {results['telegram_failed']}")
    
    print(f"\n🛡️ OPA 상태:")
    print(f"   Mode: {status['mode']}")
    print(f"   Total requests: {status['opa_stats']['total_requests']}")
    print(f"   Allowed: {status['opa_stats']['allowed']}")
    print(f"   Denied: {status['opa_stats']['denied']}")
    print(f"   Zones with losses: {status['zones_with_losses']}")
    
    # 검증
    print("\n" + "=" * 70)
    print("✅ 실시간 파이프라인 시뮬레이션 완료!")
    print("=" * 70)
    
    return {
        "results": results,
        "opa_status": status,
    }


if __name__ == "__main__":
    random.seed(42)  # 재현성
    result = run_realtime_simulation()
    
    # JSON 저장
    with open("opa_realtime_simulation.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    
    print("\n결과 저장: opa_realtime_simulation.json")
