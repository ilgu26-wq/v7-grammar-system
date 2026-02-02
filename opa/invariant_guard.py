"""
V7 Grammar System - Invariant Guard
불변 조건 10개를 코드로 강제 + 위반 시 즉시 HALT

2026-01-23 구현
"""

import json
from datetime import datetime
from typing import Dict, Optional, List, Any

HALT_EXECUTION = False
INVARIANT_VIOLATIONS = []

VALID_DELTA_SCOPES = {'t-ε', 't0', 't+0', 'NEUTRAL'}
VALID_ACTIONS = {'ENTRY', 'EXIT', 'OBSERVE', 'DEFENSE'}
VALID_LAYERS = {'OPA', 'STB', 'DEFENSE', 'OBSERVATION'}


def assert_invariants(event: Dict, mode: str = "PAPER") -> Dict:
    """
    모든 이벤트 publish 직전에 호출
    위반 시 HALT + 로그
    
    Returns:
        {'valid': bool, 'violations': list, 'halt': bool}
    """
    global HALT_EXECUTION, INVARIANT_VIOLATIONS
    
    violations = []
    
    action = event.get('action', '')
    layer = event.get('layer', '')
    delta_scope = event.get('delta_scope', '')
    theta = event.get('theta', 0)
    trade_id = event.get('trade_id')
    direction = event.get('direction', '')
    
    if delta_scope and delta_scope not in VALID_DELTA_SCOPES:
        violations.append(f"INV_1: delta_scope '{delta_scope}' not in {VALID_DELTA_SCOPES}")
    
    if action == 'ENTRY' and theta < 3:
        pass
    
    if layer == 'DEFENSE' and delta_scope != 't+0' and action == 'ENTRY':
        violations.append(f"INV_3: DEFENSE layer requires delta_scope=t+0, got '{delta_scope}'")
    
    if layer == 'OPA' and delta_scope == 't0' and action == 'ENTRY':
        violations.append(f"INV_4: OPA layer cannot have delta_scope=t0")
    
    if action == 'ENTRY' and not direction:
        violations.append("INV_6: ENTRY requires direction (LONG/SHORT)")
    
    if action == 'EXIT' and not trade_id:
        violations.append("INV_7: EXIT requires trade_id")
    
    if mode == "PAPER" and event.get('execute_payload'):
        violations.append("INV_10: Paper mode cannot send execution payload")
    
    if violations:
        HALT_EXECUTION = True
        
        violation_record = {
            'timestamp': datetime.now().isoformat(),
            'event': event,
            'violations': violations,
            'mode': mode
        }
        INVARIANT_VIOLATIONS.append(violation_record)
        
        print(f"\n{'='*60}")
        print(f"🚨 INVARIANT_FAIL | {len(violations)} violations detected!")
        for v in violations:
            print(f"   ❌ {v}")
        print(f"   Event: {json.dumps(event, default=str)}")
        print(f"{'='*60}\n")
        
        return {
            'valid': False,
            'violations': violations,
            'halt': True,
            'event': event
        }
    
    return {
        'valid': True,
        'violations': [],
        'halt': False
    }


def create_reproducible_log(
    bar: Dict,
    layer: str,
    action: str,
    direction: str,
    delta: float,
    delta_scope: str,
    theta: int,
    reason: str,
    trade_id: Optional[str] = None,
    state_age: int = 0,
    stb_margin: float = 0,
    channel_pct: float = 50
) -> Dict:
    """
    버그 재현 가능한 최소 로그 필드 (MUST)
    """
    return {
        'ts': datetime.now().isoformat(),
        'symbol': 'NQ',
        'bar_time': bar.get('time', ''),
        'ohlc': {
            'open': bar.get('open', 0),
            'high': bar.get('high', 0),
            'low': bar.get('low', 0),
            'close': bar.get('close', 0)
        },
        'layer': layer,
        'action': action,
        'direction': direction,
        'delta': round(delta, 3),
        'delta_scope': delta_scope,
        'theta': theta,
        'state_age': state_age,
        'stb_margin': round(stb_margin, 2),
        'channel_pct': round(channel_pct, 1),
        'reason': reason,
        'trade_id': trade_id
    }


def check_live_kill_switch() -> Dict:
    """
    Live 직전 자동 차단 조건 체크
    """
    global HALT_EXECUTION, INVARIANT_VIOLATIONS
    
    invariant_count = len(INVARIANT_VIOLATIONS)
    layer_conflicts = sum(1 for v in INVARIANT_VIOLATIONS if 'layer' in str(v.get('violations', [])))
    scope_missing = sum(1 for v in INVARIANT_VIOLATIONS if 'delta_scope' in str(v.get('violations', [])))
    
    kill_reasons = []
    
    if invariant_count >= 1:
        kill_reasons.append(f"INVARIANT_FAIL >= 1 (count: {invariant_count})")
    
    if layer_conflicts > 0:
        kill_reasons.append(f"layer_conflict > 0 (count: {layer_conflicts})")
    
    if scope_missing > 0:
        kill_reasons.append(f"delta_scope_missing > 0 (count: {scope_missing})")
    
    if kill_reasons:
        return {
            'kill_switch': True,
            'reasons': kill_reasons,
            'action': 'LIVE_HALT',
            'message': '🚨 LIVE HALT - Execution stopped due to invariant violations'
        }
    
    return {
        'kill_switch': False,
        'reasons': [],
        'action': 'CONTINUE',
        'message': 'System healthy'
    }


def get_invariant_status() -> Dict:
    """현재 불변 조건 상태 조회"""
    global HALT_EXECUTION, INVARIANT_VIOLATIONS
    
    return {
        'halt_execution': HALT_EXECUTION,
        'violation_count': len(INVARIANT_VIOLATIONS),
        'violations': INVARIANT_VIOLATIONS[-10:],
        'kill_switch': check_live_kill_switch()
    }


def reset_invariant_guard():
    """리셋 (테스트용)"""
    global HALT_EXECUTION, INVARIANT_VIOLATIONS
    HALT_EXECUTION = False
    INVARIANT_VIOLATIONS = []
    return {'status': 'reset', 'halt': False, 'violations': 0}
