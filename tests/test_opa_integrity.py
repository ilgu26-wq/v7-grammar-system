"""
OPA 정합성 테스트
=================

확인 항목:
1. θ=0에서 어떤 경로로도 execution.enter가 호출되지 않음
2. θ=2에서 retry 조건이 만족되지 않으면 재진입 불가
3. θ>=3에서 size가 반드시 LARGE로 설정됨
4. experiments/ 코드가 실운용 경로에서 import되지 않음
"""

import sys
import os

sys.path.insert(0, '/home/runner/workspace/v7-grammar-system')


def test_theta0_deny():
    """테스트 1: θ=0에서 절대 ALLOW 안 됨"""
    from opa.authority_engine import AuthorityEngine, AuthorityRequest, Authority
    
    engine = AuthorityEngine()
    
    request = AuthorityRequest(
        signal_name="STB숏",
        theta=0,
    )
    
    response = engine.evaluate(request)
    
    assert response.authority == Authority.DENY, "θ=0 must be DENY"
    print("✅ Test 1 PASS: θ=0 → DENY")
    return True


def test_theta2_retry_conditions():
    """테스트 2: θ=2에서 retry 조건 검증"""
    from opa.policy_v74 import can_retry
    
    assert can_retry(theta=2, impulse_count=3, recovery_time=3) == True, \
        "θ=2 with good conditions should allow retry"
    
    assert can_retry(theta=2, impulse_count=1, recovery_time=5) == False, \
        "θ=2 with bad conditions should deny retry"
    
    assert can_retry(theta=1, impulse_count=3, recovery_time=3) == False, \
        "θ=1 should never allow retry"
    
    print("✅ Test 2 PASS: θ=2 retry conditions enforced")
    return True


def test_theta3_large_size():
    """테스트 3: θ>=3에서 LARGE size"""
    from opa.policy_v74 import get_size
    
    assert get_size(3) == "LARGE", "θ=3 must be LARGE"
    assert get_size(4) == "LARGE", "θ=4 must be LARGE"
    assert get_size(10) == "LARGE", "θ=10 must be LARGE"
    
    print("✅ Test 3 PASS: θ≥3 → LARGE")
    return True


def test_no_experiments_import():
    """테스트 4: experiments 코드가 운용 코드에서 import 안 됨"""
    core_files = [
        '/home/runner/workspace/v7-grammar-system/core/theta_state.py',
        '/home/runner/workspace/v7-grammar-system/core/stb_sensor.py',
        '/home/runner/workspace/v7-grammar-system/core/transition_sensor.py',
        '/home/runner/workspace/v7-grammar-system/opa/policy_v74.py',
        '/home/runner/workspace/v7-grammar-system/opa/authority_engine.py',
        '/home/runner/workspace/v7-grammar-system/opa/size_manager.py',
    ]
    
    for filepath in core_files:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                content = f.read()
                assert 'experiments' not in content, \
                    f"{filepath} must not import from experiments"
    
    print("✅ Test 4 PASS: No experiments import in production code")
    return True


def run_all_tests():
    """모든 테스트 실행"""
    print("=" * 70)
    print("OPA 정합성 테스트")
    print("=" * 70)
    
    tests = [
        test_theta0_deny,
        test_theta2_retry_conditions,
        test_theta3_large_size,
        test_no_experiments_import,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except AssertionError as e:
            print(f"❌ FAIL: {e}")
            results.append(False)
        except Exception as e:
            print(f"❌ ERROR: {e}")
            results.append(False)
    
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"📊 결과: {passed}/{total} 테스트 통과")
    
    if passed == total:
        print("✅ OPA 정합성 검증 완료")
    else:
        print("⚠️ 일부 테스트 실패")
    
    return passed == total


if __name__ == "__main__":
    run_all_tests()
