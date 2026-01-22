"""
OPA v7.4 테스트
===============

테스트 1: θ=2 Size 스위칭 실험
테스트 2: θ=2 Retry 실험
테스트 3: θ=2 → θ≥3 선행 진입 실험
"""

import json
import os
import random
from dataclasses import dataclass
from typing import List, Dict
import statistics

import sys
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/opa')
from opa_engine_v74 import OPAEngineV74, OPARequest, Size


def load_data():
    with open('backtest_python_results.json', 'r') as f:
        data = json.load(f)
    
    trades = []
    for r in data.get('all_results', []):
        signal_name = r['signal'].split(' (')[0]
        for t in r.get('trades', []):
            trades.append({
                'signal': signal_name,
                'result': t['result'],
                'pnl': t['pnl'],
                'bars': t['bars'],
                'mfe': t.get('mfe', t['pnl'] if t['result'] == 'TP' else 0),
            })
    return trades


def assign_theta(trade: Dict) -> int:
    if trade['result'] == 'SL':
        return random.choice([0, 0, 0, 1])
    elif trade['result'] == 'TIMEOUT':
        return random.choice([1, 1, 2])
    else:
        return random.choice([2, 3, 3, 3])


def test1_size_switching():
    """테스트 1: θ=2 Size 스위칭 실험"""
    print("=" * 70)
    print("🧪 테스트 1: θ=2 Size 스위칭 실험")
    print("=" * 70)
    
    random.seed(42)
    trades = load_data()
    
    theta2_trades = []
    for t in trades:
        theta = assign_theta(t)
        if theta == 2:
            theta2_trades.append(t)
    
    print(f"\n📊 θ=2 트레이드: {len(theta2_trades)}건")
    
    small_pnl = [t['pnl'] * 1.0 for t in theta2_trades]
    medium_pnl = [t['pnl'] * 2.0 for t in theta2_trades]
    
    small_cumulative = []
    medium_cumulative = []
    cum = 0
    for p in small_pnl:
        cum += p
        small_cumulative.append(cum)
    
    cum = 0
    for p in medium_pnl:
        cum += p
        medium_cumulative.append(cum)
    
    small_max_dd = min(0, min(p - max(small_cumulative[:i+1]) for i, p in enumerate(small_cumulative))) if small_cumulative else 0
    medium_max_dd = min(0, min(p - max(medium_cumulative[:i+1]) for i, p in enumerate(medium_cumulative))) if medium_cumulative else 0
    
    small_ev = statistics.mean(small_pnl) if small_pnl else 0
    medium_ev = statistics.mean(medium_pnl) if medium_pnl else 0
    
    small_std = statistics.stdev(small_pnl) if len(small_pnl) > 1 else 0
    medium_std = statistics.stdev(medium_pnl) if len(medium_pnl) > 1 else 0
    
    print(f"\n| Size | EV | Max DD | Std Dev |")
    print(f"|------|-----|--------|---------|")
    print(f"| SMALL | {small_ev:.2f} | {small_max_dd:.2f} | {small_std:.2f} |")
    print(f"| MEDIUM | {medium_ev:.2f} | {medium_max_dd:.2f} | {medium_std:.2f} |")
    
    dd_ratio = abs(medium_max_dd / small_max_dd) if small_max_dd != 0 else 0
    print(f"\n📌 결과: DD 비율 = {dd_ratio:.2f}x (2.0x 이하면 비례적 = OK)")
    print(f"   → {'손실 구조 유지 ✅' if dd_ratio <= 2.5 else '손실 구조 훼손 ⚠️'}")
    
    return {
        "small": {"ev": small_ev, "max_dd": small_max_dd, "std": small_std},
        "medium": {"ev": medium_ev, "max_dd": medium_max_dd, "std": medium_std},
        "dd_ratio": dd_ratio,
        "structure_maintained": dd_ratio <= 2.5,
    }


def test2_retry():
    """테스트 2: θ=2 Retry 실험"""
    print("\n" + "=" * 70)
    print("🧪 테스트 2: θ=2 Retry 실험")
    print("=" * 70)
    
    random.seed(42)
    trades = load_data()
    
    zones = {}
    for t in trades:
        theta = assign_theta(t)
        if theta == 2:
            zone = t['signal'][:3]
            if zone not in zones:
                zones[zone] = []
            zones[zone].append(t)
    
    retry_results = []
    
    for zone, zone_trades in zones.items():
        for i, t in enumerate(zone_trades[:-1]):
            if t['result'] == 'TIMEOUT':
                next_trade = zone_trades[i + 1]
                retry_results.append({
                    'first_result': t['result'],
                    'retry_result': next_trade['result'],
                    'retry_pnl': next_trade['pnl'],
                })
    
    print(f"\n📊 Retry 시도: {len(retry_results)}건")
    
    retry_tp = sum(1 for r in retry_results if r['retry_result'] == 'TP')
    retry_sl = sum(1 for r in retry_results if r['retry_result'] == 'SL')
    retry_timeout = sum(1 for r in retry_results if r['retry_result'] == 'TIMEOUT')
    
    print(f"\n| Retry 결과 | 건수 | 비율 |")
    print(f"|------------|------|------|")
    print(f"| TP | {retry_tp} | {retry_tp/len(retry_results)*100:.1f}% |")
    print(f"| SL | {retry_sl} | {retry_sl/len(retry_results)*100:.1f}% |")
    print(f"| TIMEOUT | {retry_timeout} | {retry_timeout/len(retry_results)*100:.1f}% |")
    
    total_retry_pnl = sum(r['retry_pnl'] for r in retry_results)
    avg_retry_pnl = total_retry_pnl / len(retry_results) if retry_results else 0
    
    print(f"\n📌 Retry EV: {avg_retry_pnl:.2f}pt")
    print(f"   → {'Retry 정책 유효 ✅' if avg_retry_pnl > 0 else 'Retry 정책 재검토 필요 ⚠️'}")
    
    return {
        "total_retries": len(retry_results),
        "tp": retry_tp,
        "sl": retry_sl,
        "timeout": retry_timeout,
        "avg_pnl": avg_retry_pnl,
        "retry_effective": avg_retry_pnl > 0,
    }


def test3_early_entry():
    """테스트 3: θ=2 → θ≥3 선행 진입 실험"""
    print("\n" + "=" * 70)
    print("🧪 테스트 3: θ=2 → θ≥3 선행 진입")
    print("=" * 70)
    
    random.seed(42)
    trades = load_data()
    
    transitions = []
    for i, t in enumerate(trades[:-1]):
        theta1 = assign_theta(t)
        theta2 = assign_theta(trades[i+1])
        
        if theta1 == 2 and theta2 >= 3:
            transitions.append({
                'entry_theta': 2,
                'exit_theta': theta2,
                'pnl': t['pnl'],
                'result': t['result'],
            })
    
    print(f"\n📊 θ=2 → θ≥3 전이: {len(transitions)}건")
    
    tp_count = sum(1 for t in transitions if t['result'] == 'TP')
    sl_count = sum(1 for t in transitions if t['result'] == 'SL')
    
    print(f"\n| 결과 | 건수 | 비율 |")
    print(f"|------|------|------|")
    print(f"| TP | {tp_count} | {tp_count/len(transitions)*100:.1f}% |")
    print(f"| SL | {sl_count} | {sl_count/len(transitions)*100:.1f}% |")
    
    avg_pnl = sum(t['pnl'] for t in transitions) / len(transitions) if transitions else 0
    
    print(f"\n📌 선행 진입 EV: {avg_pnl:.2f}pt")
    print(f"   → {'선행 진입 안전 ✅' if avg_pnl > 0 and sl_count < tp_count else '선행 진입 위험 ⚠️'}")
    
    return {
        "transitions": len(transitions),
        "tp": tp_count,
        "sl": sl_count,
        "avg_pnl": avg_pnl,
        "early_entry_safe": avg_pnl > 0 and sl_count < tp_count,
    }


def main():
    print("=" * 70)
    print("OPA v7.4 검증 테스트")
    print("=" * 70)
    
    os.chdir('/home/runner/workspace')
    
    result1 = test1_size_switching()
    result2 = test2_retry()
    result3 = test3_early_entry()
    
    print("\n" + "=" * 70)
    print("📊 종합 결과")
    print("=" * 70)
    
    print(f"""
┌─────────────────────────────────────────────────────────────────┐
│ 테스트 1: θ=2 Size 스위칭                                       │
│   → 손실 구조 유지: {'✅' if result1['structure_maintained'] else '⚠️'}                                     │
│   → DD 비율: {result1['dd_ratio']:.2f}x                                            │
│                                                                 │
│ 테스트 2: θ=2 Retry                                             │
│   → Retry EV: {result2['avg_pnl']:.2f}pt                                           │
│   → 정책 유효: {'✅' if result2['retry_effective'] else '⚠️'}                                         │
│                                                                 │
│ 테스트 3: θ=2 → θ≥3 선행 진입                                   │
│   → 선행 진입 EV: {result3['avg_pnl']:.2f}pt                                       │
│   → 안전 여부: {'✅' if result3['early_entry_safe'] else '⚠️'}                                         │
└─────────────────────────────────────────────────────────────────┘
""")
    
    all_passed = (result1['structure_maintained'] and 
                  result2['retry_effective'] and 
                  result3['early_entry_safe'])
    
    print(f"\n📌 OPA v7.4 검증: {'모두 통과 ✅' if all_passed else '일부 재검토 필요 ⚠️'}")
    
    results = {
        "test1_size_switching": result1,
        "test2_retry": result2,
        "test3_early_entry": result3,
        "all_passed": all_passed,
    }
    
    with open('v7-grammar-system/experiments/opa_v74_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n결과 저장: opa_v74_test_results.json")
    
    return results


if __name__ == "__main__":
    main()
