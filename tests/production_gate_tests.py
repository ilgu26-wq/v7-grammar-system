"""
V7 Grammar System - Production Gate Tests
AI 판단 검증 시스템

5가지 실험:
1. EXP-V7-1: Edge Case 스트레스
2. EXP-AI-1: Blind Audit Test
3. EXP-AI-2: Fault Injection
4. EXP-TG-1: 텔레그램 메시지 테스트
5. EXP-WH-1: Webhook Replay Test
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'opa'))
from paper_mode_engine import PaperModeEngine


FINAL_AUDIT_RULES = {
    'RULE_1': 'OPA(t-ε)와 STB(t0)는 동시에 실행될 수 없다. OPA 우선.',
    'RULE_2': 't0에서 Δ로 진입 판단 금지.',
    'RULE_3': 'θ≥3은 확정 레이블, 실행 트리거 아님.',
    'RULE_4': '0-bar 방어는 진입과 같은 봉에서만 발동.',
    'RULE_5': 'exit_reason은 TP/SL/TIMEOUT 중 하나.',
    'RULE_6': 'layer_triggered는 OPA/STB/DEFENSE 중 하나.',
    'RULE_7': 'delta_scope는 t-ε/t0/t+0 중 하나.'
}


def exp_v7_1_edge_case_stress() -> Dict:
    """EXP-V7-1: Edge Case 스트레스 테스트"""
    print("\n" + "="*60)
    print("EXP-V7-1: Edge Case Stress Test")
    print("="*60)
    
    engine = PaperModeEngine()
    test_cases = []
    
    for i in range(20):
        engine.state['bars'].append({
            'time': f'2026-01-23 00:{i:02d}:00',
            'open': 21000,
            'high': 21010,
            'low': 20990,
            'close': 21000
        })
        engine.state['delta_history'].append(1.0)
    
    case1 = {
        'time': '2026-01-23 00:20:00',
        'open': 21000,
        'high': 21100,
        'low': 20850,
        'close': 21080
    }
    engine.on_bar(case1)
    
    opa_triggered = len([e for e in engine.events if 'OPA' in e.get('event_type', '')])
    stb_triggered = len([e for e in engine.events if 'STB' in e.get('event_type', '')])
    
    test_cases.append({
        'case': 'OPA_STB_SIMULTANEOUS',
        'description': 'OPA와 STB 동시 발생 가능 봉',
        'opa_triggered': opa_triggered,
        'stb_triggered': stb_triggered,
        'passed': not (opa_triggered > 0 and stb_triggered > 0),
        'rule': 'RULE_1'
    })
    
    engine2 = PaperModeEngine()
    for i in range(25):
        bar = {
            'time': f'2026-01-23 00:{i:02d}:00',
            'open': 21000 + i*5,
            'high': 21010 + i*5,
            'low': 20990 + i*5,
            'close': 21000 + i*5
        }
        engine2.state['bars'].append(bar)
        engine2.state['delta_history'].append(1.5 + i*0.1)
    
    threshold_bar = {
        'time': '2026-01-23 00:25:00',
        'open': 21125,
        'high': 21200,
        'low': 21100,
        'close': 21180
    }
    engine2.on_bar(threshold_bar)
    
    test_cases.append({
        'case': 'IMPULSE_THRESHOLD_EDGE',
        'description': 'Impulse threshold 경계값',
        'events': len(engine2.events),
        'passed': engine2.audit_checks['engine_errors'] == 0,
        'rule': 'RULE_4'
    })
    
    engine3 = PaperModeEngine()
    for i in range(20):
        bar = {
            'time': f'2026-01-23 00:{i:02d}:00',
            'open': 21000,
            'high': 21050,
            'low': 20950,
            'close': 21000
        }
        engine3.on_bar(bar)
    
    tpsl_bar = {
        'time': '2026-01-23 00:20:00',
        'open': 21000,
        'high': 21025,
        'low': 20980,
        'close': 21010
    }
    engine3.on_bar(tpsl_bar)
    
    test_cases.append({
        'case': 'TP_SL_SAME_BAR',
        'description': 'TP/SL 동시 가능 봉',
        'engine_errors': engine3.audit_checks['engine_errors'],
        'passed': engine3.audit_checks['engine_errors'] == 0,
        'rule': 'RULE_5'
    })
    
    all_passed = all(tc['passed'] for tc in test_cases)
    
    result = {
        'experiment': 'EXP-V7-1',
        'test_cases': test_cases,
        'all_passed': all_passed,
        'timestamp': datetime.now().isoformat()
    }
    
    for tc in test_cases:
        status = "✅" if tc['passed'] else "❌"
        print(f"  {status} {tc['case']}: {tc['description']}")
    
    return result


def exp_ai_1_blind_audit(logs: List[Dict]) -> Dict:
    """EXP-AI-1: Blind Audit Test - AI가 판단해야 할 로그"""
    print("\n" + "="*60)
    print("EXP-AI-1: Blind Audit Test")
    print("="*60)
    
    results = []
    
    for log in logs:
        violations = []
        
        layer = log.get('layer')
        if layer not in ['OPA', 'STB', 'DEFENSE', None]:
            violations.append('RULE_6')
        
        delta_scope = log.get('delta_scope')
        if delta_scope not in ['t-ε', 't0', 't+0', None]:
            violations.append('RULE_7')
        
        if layer == 'STB' and delta_scope == 't-ε':
            violations.append('RULE_2')
        
        if layer == 'OPA' and delta_scope == 't0':
            violations.append('RULE_2')
        
        theta = log.get('theta', 0)
        action = log.get('action')
        if theta >= 3 and action == 'ENTER':
            violations.append('RULE_3')
        
        if layer == 'DEFENSE' and delta_scope != 't+0':
            violations.append('RULE_4')
        
        result = {
            'log': log,
            'violated': len(violations) > 0,
            'violations': violations,
            'verdict': 'VIOLATION' if violations else 'PASS'
        }
        results.append(result)
        
        status = "❌ VIOLATION" if violations else "✅ PASS"
        print(f"  {status}: layer={layer}, scope={delta_scope}, theta={theta}")
        if violations:
            print(f"    Rules: {violations}")
    
    return {
        'experiment': 'EXP-AI-1',
        'results': results,
        'total_logs': len(logs),
        'violations': sum(1 for r in results if r['violated']),
        'timestamp': datetime.now().isoformat()
    }


def exp_ai_2_fault_injection() -> Dict:
    """EXP-AI-2: Fault Injection - 의도적으로 잘못된 로그"""
    print("\n" + "="*60)
    print("EXP-AI-2: Fault Injection Test")
    print("="*60)
    
    faulty_logs = [
        {
            'id': 'FAULT_1',
            'description': 't0에서 Δ로 진입 (위반)',
            'layer': 'OPA',
            'delta_scope': 't0',
            'theta': 1,
            'action': 'ENTER',
            'expected_violation': 'RULE_2'
        },
        {
            'id': 'FAULT_2',
            'description': 'θ≥3 실행 (위반)',
            'layer': 'STB',
            'delta_scope': 't0',
            'theta': 3,
            'action': 'ENTER',
            'expected_violation': 'RULE_3'
        },
        {
            'id': 'FAULT_3',
            'description': '0-bar 방어가 다른 scope (위반)',
            'layer': 'DEFENSE',
            'delta_scope': 't0',
            'theta': 0,
            'action': 'TIGHT_SL',
            'expected_violation': 'RULE_4'
        },
        {
            'id': 'VALID_1',
            'description': '정상 STB 진입',
            'layer': 'STB',
            'delta_scope': 't0',
            'theta': 1,
            'action': 'ENTER',
            'expected_violation': None
        },
        {
            'id': 'VALID_2',
            'description': '정상 OPA 진입',
            'layer': 'OPA',
            'delta_scope': 't-ε',
            'theta': 0,
            'action': 'ENTER',
            'expected_violation': None
        },
        {
            'id': 'VALID_3',
            'description': '정상 0-bar 방어',
            'layer': 'DEFENSE',
            'delta_scope': 't+0',
            'theta': 0,
            'action': 'TIGHT_SL',
            'expected_violation': None
        }
    ]
    
    results = []
    
    for fault in faulty_logs:
        audit_result = exp_ai_1_blind_audit([fault])['results'][0]
        
        expected = fault['expected_violation']
        actual_violations = audit_result['violations']
        
        if expected is None:
            detected_correctly = len(actual_violations) == 0
        else:
            detected_correctly = expected in actual_violations
        
        results.append({
            'id': fault['id'],
            'description': fault['description'],
            'expected': expected,
            'actual': actual_violations,
            'detected_correctly': detected_correctly
        })
        
        status = "✅" if detected_correctly else "❌"
        print(f"  {status} {fault['id']}: {fault['description']}")
        if not detected_correctly:
            print(f"    Expected: {expected}, Got: {actual_violations}")
    
    all_correct = all(r['detected_correctly'] for r in results)
    
    return {
        'experiment': 'EXP-AI-2',
        'results': results,
        'all_correct': all_correct,
        'detection_rate': sum(1 for r in results if r['detected_correctly']) / len(results) * 100,
        'timestamp': datetime.now().isoformat()
    }


def exp_tg_1_telegram_clarity() -> Dict:
    """EXP-TG-1: 텔레그램 메시지 명확성 테스트"""
    print("\n" + "="*60)
    print("EXP-TG-1: Telegram Message Clarity Test")
    print("="*60)
    
    def format_telegram_message(event: Dict) -> str:
        """FINAL_AUDIT 준수 텔레그램 메시지"""
        layer = event.get('layer', 'UNKNOWN')
        scope = event.get('delta_scope', 'UNKNOWN')
        direction = event.get('direction', '')
        action = event.get('action', '')
        delta = event.get('delta', 0)
        impulse = event.get('impulse', False)
        
        lines = [
            f"[V7] {layer} | {action}",
            f"Direction: {direction}",
            f"Scope: {scope}",
            f"Delta: {delta:.2f}",
        ]
        
        if impulse:
            lines.append("⚠️ Impulse: 0-bar Defense Active")
        
        return "\n".join(lines)
    
    test_events = [
        {
            'layer': 'STB',
            'delta_scope': 't0',
            'direction': 'SHORT',
            'action': 'ENTER',
            'delta': 1.85,
            'impulse': False
        },
        {
            'layer': 'OPA',
            'delta_scope': 't-ε',
            'direction': 'LONG',
            'action': 'ENTER',
            'delta': 0.65,
            'impulse': False
        },
        {
            'layer': 'STB',
            'delta_scope': 't0',
            'direction': 'SHORT',
            'action': 'ENTER',
            'delta': 2.10,
            'impulse': True
        }
    ]
    
    messages = []
    for event in test_events:
        msg = format_telegram_message(event)
        messages.append({
            'event': event,
            'message': msg,
            'has_layer': event['layer'] in msg,
            'has_scope': event['delta_scope'] in msg,
            'has_direction': event['direction'] in msg,
            'no_emotion': not any(word in msg.lower() for word in ['좋은', 'good', '확률', 'probability'])
        })
        
        print(f"\n  --- Message ---")
        print(f"  {msg.replace(chr(10), chr(10) + '  ')}")
    
    all_clear = all(
        m['has_layer'] and m['has_scope'] and m['has_direction'] and m['no_emotion']
        for m in messages
    )
    
    return {
        'experiment': 'EXP-TG-1',
        'messages': messages,
        'all_clear': all_clear,
        'timestamp': datetime.now().isoformat()
    }


def exp_wh_1_webhook_replay() -> Dict:
    """EXP-WH-1: Webhook Stateless Replay Test"""
    print("\n" + "="*60)
    print("EXP-WH-1: Webhook Stateless Replay Test")
    print("="*60)
    
    webhook_payloads = [
        {
            'trade_id': 1,
            'layer': 'STB',
            'delta_scope': 't0',
            'direction': 'SHORT',
            'entry_price': 21050.5,
            'tp_price': 21030.5,
            'sl_price': 21065.5,
            'delta_at_entry': 1.85,
            '0bar_defense_applied': False,
            'theta_label': 1,
            'bar': {
                'time': '2026-01-23 10:15:00',
                'open': 21045,
                'high': 21055,
                'low': 21040,
                'close': 21050.5
            }
        },
        {
            'trade_id': 2,
            'layer': 'OPA',
            'delta_scope': 't-ε',
            'direction': 'LONG',
            'entry_price': 20980.0,
            'tp_price': 21000.0,
            'sl_price': 20965.0,
            'delta_at_entry': 0.55,
            '0bar_defense_applied': False,
            'theta_label': 0,
            'bar': {
                'time': '2026-01-23 10:30:00',
                'open': 20985,
                'high': 20990,
                'low': 20975,
                'close': 20980
            }
        }
    ]
    
    results = []
    
    for payload in webhook_payloads:
        can_determine_layer = payload.get('layer') in ['OPA', 'STB', 'DEFENSE']
        can_determine_scope = payload.get('delta_scope') in ['t-ε', 't0', 't+0']
        can_determine_direction = payload.get('direction') in ['LONG', 'SHORT']
        has_bar_data = 'bar' in payload
        
        audit_log = {
            'layer': payload.get('layer'),
            'delta_scope': payload.get('delta_scope'),
            'theta': payload.get('theta_label', 0),
            'action': 'ENTER'
        }
        audit_result = exp_ai_1_blind_audit([audit_log])['results'][0]
        
        results.append({
            'trade_id': payload['trade_id'],
            'can_determine_layer': can_determine_layer,
            'can_determine_scope': can_determine_scope,
            'can_determine_direction': can_determine_direction,
            'has_bar_data': has_bar_data,
            'audit_pass': not audit_result['violated'],
            'fully_reproducible': all([
                can_determine_layer,
                can_determine_scope,
                can_determine_direction,
                has_bar_data
            ])
        })
        
        status = "✅" if results[-1]['fully_reproducible'] else "❌"
        print(f"  {status} Trade {payload['trade_id']}: layer={payload['layer']}, scope={payload['delta_scope']}")
    
    all_reproducible = all(r['fully_reproducible'] for r in results)
    
    return {
        'experiment': 'EXP-WH-1',
        'results': results,
        'all_reproducible': all_reproducible,
        'timestamp': datetime.now().isoformat()
    }


def run_all_production_gate_tests() -> Dict:
    """모든 Production Gate 테스트 실행"""
    print("\n" + "="*60)
    print("V7 GRAMMAR SYSTEM - PRODUCTION GATE TESTS")
    print("="*60)
    
    results = {}
    
    results['EXP-V7-1'] = exp_v7_1_edge_case_stress()
    
    sample_logs = [
        {'layer': 'STB', 'delta_scope': 't0', 'theta': 1, 'action': 'ENTER'},
        {'layer': 'OPA', 'delta_scope': 't-ε', 'theta': 0, 'action': 'ENTER'},
        {'layer': 'DEFENSE', 'delta_scope': 't+0', 'theta': 0, 'action': 'TIGHT_SL'}
    ]
    results['EXP-AI-1'] = exp_ai_1_blind_audit(sample_logs)
    
    results['EXP-AI-2'] = exp_ai_2_fault_injection()
    
    results['EXP-TG-1'] = exp_tg_1_telegram_clarity()
    
    results['EXP-WH-1'] = exp_wh_1_webhook_replay()
    
    gate_status = {
        'EXP-V7-1': results['EXP-V7-1']['all_passed'],
        'EXP-AI-1': results['EXP-AI-1']['violations'] == 0,
        'EXP-AI-2': results['EXP-AI-2']['all_correct'],
        'EXP-TG-1': results['EXP-TG-1']['all_clear'],
        'EXP-WH-1': results['EXP-WH-1']['all_reproducible']
    }
    
    all_passed = all(gate_status.values())
    
    print("\n" + "="*60)
    print("PRODUCTION GATE SUMMARY")
    print("="*60)
    
    for exp, passed in gate_status.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {exp}")
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL GATES PASSED - Ready for Production")
    else:
        failed = [k for k, v in gate_status.items() if not v]
        print(f"❌ FAILED: {failed}")
    print("="*60)
    
    final_result = {
        'timestamp': datetime.now().isoformat(),
        'experiments': results,
        'gate_status': gate_status,
        'all_passed': all_passed,
        'ready_for_production': all_passed
    }
    
    output_path = os.path.join(os.path.dirname(__file__), 'production_gate_results.json')
    with open(output_path, 'w') as f:
        json.dump(final_result, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return final_result


if __name__ == "__main__":
    run_all_production_gate_tests()
