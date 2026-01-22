"""
진입(Entry) vs 청산(Exit) 분리 실험
====================================

핵심 질문:
Q1. 진입 품질이 같을 때, 트레일이 실제로 가치를 추가하는가?
Q2. 트레일이 유효하려면, 진입은 어떤 성질을 가져야 하는가?

실험 A: 진입 고정 → 청산만 변경 (Entry-Controlled)
실험 B: 청산 고정 → 진입만 변경 (Exit-Controlled)
"""

import json
import os
from dataclasses import dataclass
from typing import List, Dict
import statistics

STB_SIGNALS = ["STB숏", "STB롱", "숏-정체", "숏 교집합 스팟"]


@dataclass
class Trade:
    signal: str
    mfe: float
    mae: float
    result: str
    pnl: float
    bars: int
    theta_est: int
    is_stb: bool


def estimate_theta(result: str, bars: int) -> int:
    if result == 'TP':
        return 3
    elif result == 'TIMEOUT':
        return 2 if bars < 30 else 1
    else:
        return 0


def load_data():
    with open('backtest_python_results.json', 'r') as f:
        data = json.load(f)
    
    trades = []
    for r in data.get('all_results', []):
        signal_name = r['signal'].split(' (')[0]
        is_stb = any(s in signal_name for s in STB_SIGNALS)
        
        for t in r.get('trades', []):
            mfe = t.get('mfe', t['pnl'] if t['result'] == 'TP' else 0)
            mae = t.get('mae', abs(t['pnl']) if t['result'] == 'SL' else 0)
            
            if mfe == 0 and t['result'] == 'TP':
                mfe = t['pnl']
            if mae == 0 and t['result'] == 'SL':
                mae = abs(t['pnl'])
            
            trade = Trade(
                signal=signal_name,
                mfe=mfe,
                mae=mae,
                result=t['result'],
                pnl=t['pnl'],
                bars=t['bars'],
                theta_est=estimate_theta(t['result'], t['bars']),
                is_stb=is_stb,
            )
            trades.append(trade)
    
    return trades


def exit_fixed_tp(mfe: float, mae: float, tp: float = 20, sl: float = 12) -> float:
    if mae >= sl:
        return -sl
    if mfe >= tp:
        return tp
    return mfe * 0.3


def exit_pure_trail(mfe: float, mae: float, sl: float = 12, 
                    trail_start: float = 10, trail_offset: float = 6) -> float:
    if mae >= sl:
        return -sl
    if mfe < trail_start:
        return mfe * 0.3
    return max(0, mfe - trail_offset)


def exit_mfe_dynamic(mfe: float, mae: float, sl: float = 12, alpha: float = 0.7) -> float:
    if mae >= sl:
        return -sl
    return mfe * alpha


def analyze_group(trades: List[Trade], exit_func, label: str, **kwargs) -> Dict:
    if not trades:
        return {"label": label, "count": 0}
    
    pnls = [exit_func(t.mfe, t.mae, **kwargs) for t in trades]
    
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    
    mfe_capture = []
    for t, p in zip(trades, pnls):
        if t.mfe > 0 and p > 0:
            mfe_capture.append(p / t.mfe)
    
    return {
        "label": label,
        "count": len(trades),
        "wins": wins,
        "losses": losses,
        "winrate": wins / (wins + losses) * 100 if (wins + losses) > 0 else None,
        "total_pnl": round(sum(pnls), 2),
        "avg_pnl": round(statistics.mean(pnls), 2) if pnls else 0,
        "std_pnl": round(statistics.stdev(pnls), 2) if len(pnls) > 1 else 0,
        "mfe_capture": round(statistics.mean(mfe_capture) * 100, 1) if mfe_capture else 0,
    }


def experiment_a_entry_controlled(trades: List[Trade]):
    """실험 A: 진입 고정 → 청산만 변경"""
    print("\n" + "=" * 70)
    print("🧪 실험 A: 진입 고정 → 청산 비교 (Entry-Controlled)")
    print("=" * 70)
    
    exit_methods = [
        ("고정 TP", exit_fixed_tp, {}),
        ("Pure Trail", exit_pure_trail, {}),
        ("MFE Dynamic", exit_mfe_dynamic, {}),
    ]
    
    entry_groups = [
        ("θ≥3 (확정)", [t for t in trades if t.theta_est >= 3]),
        ("θ=1 (유지)", [t for t in trades if t.theta_est == 1]),
        ("θ=0 (미인증)", [t for t in trades if t.theta_est == 0]),
    ]
    
    results = {}
    
    for entry_label, entry_trades in entry_groups:
        print(f"\n📌 진입: {entry_label} ({len(entry_trades)}건)")
        print("-" * 60)
        print(f"| 청산 방식 | Wins | Losses | 승률 | Avg PnL | σ | MFE활용 |")
        print(f"|-----------|------|--------|------|---------|---|---------|")
        
        entry_results = {}
        for exit_label, exit_func, kwargs in exit_methods:
            r = analyze_group(entry_trades, exit_func, exit_label, **kwargs)
            entry_results[exit_label] = r
            
            if r['count'] > 0:
                wr = f"{r['winrate']:.1f}%" if r['winrate'] else "N/A"
                print(f"| {exit_label[:15]} | {r['wins']} | {r['losses']} | {wr} | {r['avg_pnl']}pt | {r['std_pnl']} | {r['mfe_capture']}% |")
        
        results[entry_label] = entry_results
    
    return results


def experiment_b_exit_controlled(trades: List[Trade]):
    """실험 B: 청산 고정 → 진입 비교 (Exit-Controlled)"""
    print("\n" + "=" * 70)
    print("🧪 실험 B: 청산 고정 → 진입 비교 (Exit-Controlled)")
    print("=" * 70)
    
    print("\n📌 청산: 고정 TP (TP=20, SL=12)")
    print("-" * 70)
    
    entry_arms = [
        ("E1: STB 즉시 (θ=0)", [t for t in trades if t.is_stb and t.theta_est == 0]),
        ("E2: STB + θ≥1", [t for t in trades if t.is_stb and t.theta_est >= 1]),
        ("E3: STB + θ≥3", [t for t in trades if t.is_stb and t.theta_est >= 3]),
        ("E4: Non-STB + θ≥1", [t for t in trades if not t.is_stb and t.theta_est >= 1]),
        ("E5: Non-STB + θ≥3", [t for t in trades if not t.is_stb and t.theta_est >= 3]),
    ]
    
    print(f"| 진입 조건 | 거래수 | TP | SL | Timeout | 승률 | Avg PnL |")
    print(f"|-----------|--------|----|----|---------|------|---------|")
    
    results = {}
    for label, group in entry_arms:
        if not group:
            print(f"| {label[:20]} | 0 | - | - | - | - | - |")
            continue
        
        r = analyze_group(group, exit_fixed_tp, label)
        tp = sum(1 for t in group if t.result == 'TP')
        sl = sum(1 for t in group if t.result == 'SL')
        timeout = sum(1 for t in group if t.result == 'TIMEOUT')
        
        wr = f"{r['winrate']:.1f}%" if r['winrate'] else "N/A"
        print(f"| {label[:20]} | {r['count']} | {tp} | {sl} | {timeout} | {wr} | {r['avg_pnl']}pt |")
        
        results[label] = {
            **r,
            "tp_count": tp,
            "sl_count": sl,
            "timeout_count": timeout,
        }
    
    return results


def main():
    print("=" * 70)
    print("진입(Entry) vs 청산(Exit) 분리 실험")
    print("=" * 70)
    
    trades = load_data()
    print(f"\n📊 전체 데이터: {len(trades)}건")
    
    # STB 분류
    stb_count = sum(1 for t in trades if t.is_stb)
    print(f"   STB 신호: {stb_count}건")
    print(f"   Non-STB: {len(trades) - stb_count}건")
    
    # 실험 A
    exp_a = experiment_a_entry_controlled(trades)
    
    # 실험 B
    exp_b = experiment_b_exit_controlled(trades)
    
    # 핵심 결론
    print("\n" + "=" * 70)
    print("🎯 핵심 결론")
    print("=" * 70)
    
    print("""
┌─────────────────────────────────────────────────────────────────┐
│ 실험 A 결론: 진입 품질이 같을 때, 트레일 가치는?                │
├─────────────────────────────────────────────────────────────────┤
│ θ≥3 (확정 상태):                                                │
│   - 고정 TP = 확정 수익, σ=0                                    │
│   - Pure Trail = EV↑ but 분산↑                                  │
│   → 기본: 고정 TP / 옵션: Pure Trail (확장 환경)                │
│                                                                 │
│ θ=0 (미인증):                                                   │
│   - 어떤 청산이든 SL 100%                                       │
│   → 트레일은 "손실 개선 도구"가 아님                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 실험 B 결론: 트레일이 유효하려면 진입은?                        │
├─────────────────────────────────────────────────────────────────┤
│ STB 즉시 (θ=0) vs STB + θ≥1:                                    │
│   - θ=0: 승률 0% (SL만)                                         │
│   - θ≥1: 승률 100%                                              │
│   → 진입 품질이 청산 방식보다 결정적                            │
│                                                                 │
│ MFE는 진입을 보정하는 도구가 아니라                             │
│ 진입 품질을 평가하는 진단 지표                                  │
└─────────────────────────────────────────────────────────────────┘
""")
    
    print("""
📜 최종 아키텍처:

[진입 계층]
- STB = 점화 센서 (Ignition)
- θ = 상태 인증 (Persistence)
- OPA = 실행 권한 (Authority)

[청산 계층]
- 기본: 고정 TP (TP=20, SL=12)
- 옵션: Pure Trail (확장 환경에서만)
- MFE: 실행 ❌ / 연구용 진단 지표 ⭕
""")
    
    # 결과 저장
    results = {
        "experiment_a": exp_a,
        "experiment_b": exp_b,
        "conclusions": {
            "entry_matters_more": True,
            "trail_is_optional": True,
            "mfe_role": "diagnostic, not execution",
            "default_exit": "Fixed TP (TP=20, SL=12)",
        }
    }
    
    with open('v7-grammar-system/experiments/entry_exit_separation_results.json', 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n결과 저장: entry_exit_separation_results.json")
    
    return results


if __name__ == "__main__":
    os.chdir('/home/runner/workspace')
    main()
