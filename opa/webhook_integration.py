"""
V7 Grammar System - Webhook Integration
main.py의 process_candle()과 연결

사용법:
from opa.webhook_integration import v7_paper_engine, process_v7_bar, get_v7_paper_stats

process_candle() 내부에서:
    v7_result = process_v7_bar(candle_data)
"""

from datetime import datetime
from typing import Dict, Optional, Any
from .paper_mode_engine import PaperModeEngine
from .invariant_guard import (
    assert_invariants, 
    create_reproducible_log,
    check_live_kill_switch,
    get_invariant_status,
    HALT_EXECUTION
)

v7_paper_engine = PaperModeEngine()


def process_v7_bar(candle: Dict) -> Dict:
    """
    main.py process_candle()에서 호출
    
    Args:
        candle: {'time', 'open', 'high', 'low', 'close', ...}
    
    Returns:
        action dict (항상 반환 - 관찰 상태 포함)
    """
    bar = {
        'time': candle.get('time', datetime.now().isoformat()),
        'open': float(candle.get('open', 0)),
        'high': float(candle.get('high', 0)),
        'low': float(candle.get('low', 0)),
        'close': float(candle.get('close', 0))
    }
    
    position_before = v7_paper_engine.state['in_position']
    trade_count_before = len(v7_paper_engine.trades)
    
    v7_paper_engine.on_bar(bar)
    
    position_after = v7_paper_engine.state['in_position']
    trade_count_after = len(v7_paper_engine.trades)
    
    delta = v7_paper_engine.calculate_delta(bar)
    channel_pct = v7_paper_engine.calculate_channel_pct()
    
    if not position_before and position_after:
        trade = v7_paper_engine.state['active_trade']
        return {
            'action': 'ENTRY',
            'layer': trade['layer'],
            'delta_scope': trade['delta_scope'],
            'direction': trade['direction'],
            'theta': trade.get('theta', 0),
            'entry_price': trade['entry_price'],
            'tp_price': trade['tp_price'],
            'sl_price': trade['sl_price'],
            '0bar_defense': trade['0bar_defense_applied'],
            'reason': 'EXECUTION'
        }
    
    elif position_before and not position_after:
        if trade_count_after > trade_count_before or v7_paper_engine.trades:
            last_trade = v7_paper_engine.trades[-1]
            if last_trade.get('exit_reason'):
                return {
                    'action': 'EXIT',
                    'layer': last_trade['layer'],
                    'delta_scope': 't0',
                    'direction': last_trade['direction'],
                    'theta': 0,
                    'exit_reason': last_trade['exit_reason'],
                    'pnl': last_trade['pnl'],
                    'result': last_trade['result'],
                    'reason': last_trade['exit_reason']
                }
    
    if delta >= 1.5:
        scope = 't-ε'
        direction = 'SHORT'
        layer = 'OPA'
    elif delta <= 0.7:
        scope = 't-ε'
        direction = 'LONG'
        layer = 'OPA'
    elif channel_pct >= 80:
        scope = 't0'
        direction = 'SHORT'
        layer = 'STB'
    elif channel_pct <= 20:
        scope = 't0'
        direction = 'LONG'
        layer = 'STB'
    else:
        scope = 'NEUTRAL'
        direction = 'NONE'
        layer = 'OBSERVATION'
    
    result = {
        'action': 'OBSERVE',
        'layer': layer,
        'delta_scope': scope,
        'direction': direction,
        'theta': 0,
        'delta': round(delta, 2),
        'channel_pct': round(channel_pct, 1),
        'in_position': position_after,
        'reason': 'NO_SIGNAL' if layer == 'OBSERVATION' else 'CONDITION_NOT_MET'
    }
    
    inv_check = assert_invariants(result, mode="PAPER")
    if not inv_check['valid']:
        result['invariant_fail'] = True
        result['violations'] = inv_check['violations']
        print(f"[V7_INVARIANT_FAIL] {inv_check['violations']}")
    
    return result


def get_v7_paper_stats() -> Dict:
    """통계 조회"""
    return v7_paper_engine.get_stats()


def get_v7_audit_status() -> Dict:
    """FINAL_AUDIT 7가지 체크 상태"""
    return v7_paper_engine.validate_audit()


def save_v7_logs():
    """로그 저장"""
    return v7_paper_engine.save_logs()


def reset_v7_engine():
    """엔진 리셋"""
    global v7_paper_engine
    v7_paper_engine = PaperModeEngine()
    return {"status": "reset", "mode": "PAPER"}
