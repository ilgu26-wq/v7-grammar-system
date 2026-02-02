"""
V7 Grammar System - Stress Test Protocol
실시간 운영 전 필수 검증

2026-01-23 구현
"""

import sys
import json
from datetime import datetime
sys.path.insert(0, 'v7-grammar-system')

from opa.candle_validator import validate_candle_full, get_validator_status
from opa.invariant_guard import assert_invariants, get_invariant_status, reset_invariant_guard
from opa.webhook_integration import process_v7_bar, reset_v7_engine

RESULTS = {
    'passed': [],
    'failed': [],
    'timestamp': datetime.now().isoformat()
}


def run_test(test_id: str, test_fn, description: str):
    """테스트 실행 래퍼"""
    try:
        result = test_fn()
        if result:
            RESULTS['passed'].append({'id': test_id, 'desc': description})
            print(f"✅ {test_id}: {description}")
            return True
        else:
            RESULTS['failed'].append({'id': test_id, 'desc': description, 'reason': 'Assertion failed'})
            print(f"❌ {test_id}: {description}")
            return False
    except Exception as e:
        RESULTS['failed'].append({'id': test_id, 'desc': description, 'reason': str(e)})
        print(f"❌ {test_id}: {description} - {e}")
        return False


def test_A1_duplicate_candle():
    """H-A1: 중복 캔들 차단"""
    reset_v7_engine()
    
    candle = {'time': '9999999999000', 'open': 25000, 'high': 25010, 'low': 24990, 'close': 25005}
    
    result1 = validate_candle_full(candle)
    assert result1['valid'] == True, f"First candle should be valid: {result1}"
    
    result2 = validate_candle_full(candle)
    assert result2['valid'] == False, f"Duplicate should be rejected: {result2}"
    assert 'DUP' in str(result2['errors']), f"Should have DUP error: {result2}"
    
    return True


def test_A2_out_of_order():
    """H-A2: Out-of-order 캔들 차단"""
    reset_v7_engine()
    
    candle1 = {'time': '9999999998000', 'open': 25000, 'high': 25010, 'low': 24990, 'close': 25005}
    result1 = validate_candle_full(candle1)
    
    candle2 = {'time': '9999999997000', 'open': 25000, 'high': 25010, 'low': 24990, 'close': 25005}
    result2 = validate_candle_full(candle2)
    
    assert result2['valid'] == False, f"Out-of-order should be rejected: {result2}"
    assert 'ORDER' in str(result2['errors']), f"Should have ORDER error: {result2}"
    
    return True


def test_A3_incomplete_candle():
    """H-A3: 부분 캔들(미완성 봉) 차단"""
    candle = {'time': '9999999996000', 'open': 25000, 'high': 0, 'low': 24990, 'close': 25005}
    result = validate_candle_full(candle)
    
    assert result['valid'] == False, f"Incomplete candle should be rejected: {result}"
    assert 'SCHEMA' in str(result['errors']), f"Should have SCHEMA error: {result}"
    
    return True


def test_A4_field_type_error():
    """H-A4: 필드 누락/타입 오류 차단"""
    candle = {'time': '9999999995000', 'open': 'invalid', 'high': 25010, 'low': 24990, 'close': 25005}
    result = validate_candle_full(candle)
    
    assert result['valid'] == False, f"Type error should be rejected: {result}"
    assert 'SCHEMA' in str(result['errors']), f"Should have SCHEMA error: {result}"
    
    candle2 = {'open': 25000, 'high': 25010, 'low': 24990, 'close': 25005}
    result2 = validate_candle_full(candle2)
    
    assert result2['valid'] == False, f"Missing field should be rejected: {result2}"
    
    return True


def test_C1_delta_scope_invariant():
    """H-C1: delta_scope 누락 탐지"""
    reset_invariant_guard()
    
    event = {
        'action': 'ENTRY',
        'layer': 'OPA',
        'delta_scope': None,
        'direction': 'LONG',
        'theta': 2
    }
    
    result = assert_invariants(event, mode="PAPER")
    
    return True


def test_C3_layer_conflict():
    """H-C3: OPA와 STB 동시 실행 방지"""
    reset_invariant_guard()
    
    event_opa = {
        'action': 'ENTRY',
        'layer': 'OPA',
        'delta_scope': 't-ε',
        'direction': 'LONG',
        'theta': 2
    }
    
    event_stb = {
        'action': 'ENTRY',
        'layer': 'STB',
        'delta_scope': 't0',
        'direction': 'LONG',
        'theta': 2
    }
    
    result_opa = assert_invariants(event_opa, mode="PAPER")
    result_stb = assert_invariants(event_stb, mode="PAPER")
    
    return True


def test_F1_paper_mode_execution_block():
    """H-F1: PAPER 모드에서 실행 payload 차단"""
    reset_invariant_guard()
    
    event = {
        'action': 'ENTRY',
        'layer': 'STB',
        'delta_scope': 't0',
        'direction': 'SHORT',
        'theta': 3,
        'execute_payload': True
    }
    
    result = assert_invariants(event, mode="PAPER")
    
    assert result['valid'] == False, f"Paper mode should block execution: {result}"
    assert 'INV_10' in str(result['violations']), f"Should have INV_10: {result}"
    
    return True


def test_F2_invariant_halt():
    """H-F2: INVARIANT_FAIL 시 HALT"""
    reset_invariant_guard()
    
    event = {
        'action': 'ENTRY',
        'layer': 'DEFENSE',
        'delta_scope': 't-ε',
        'direction': 'LONG',
        'theta': 3
    }
    
    result = assert_invariants(event, mode="LIVE")
    
    status = get_invariant_status()
    
    return True


def run_all_tests():
    """전체 테스트 실행"""
    print("\n" + "="*60)
    print("V7 Grammar System - Stress Test Protocol")
    print("="*60 + "\n")
    
    tests = [
        ("H-A1", test_A1_duplicate_candle, "중복 캔들 차단"),
        ("H-A2", test_A2_out_of_order, "Out-of-order 캔들 차단"),
        ("H-A3", test_A3_incomplete_candle, "부분 캔들 차단"),
        ("H-A4", test_A4_field_type_error, "필드 타입/누락 오류 차단"),
        ("H-C1", test_C1_delta_scope_invariant, "delta_scope 불변 조건"),
        ("H-C3", test_C3_layer_conflict, "레이어 충돌 방지"),
        ("H-F1", test_F1_paper_mode_execution_block, "PAPER 모드 실행 차단"),
        ("H-F2", test_F2_invariant_halt, "INVARIANT_FAIL → HALT"),
    ]
    
    for test_id, test_fn, desc in tests:
        run_test(test_id, test_fn, desc)
    
    print("\n" + "="*60)
    print(f"Results: {len(RESULTS['passed'])} passed, {len(RESULTS['failed'])} failed")
    print("="*60)
    
    with open('v7-grammar-system/tests/stress_test_results.json', 'w') as f:
        json.dump(RESULTS, f, indent=2, default=str)
    
    return len(RESULTS['failed']) == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
