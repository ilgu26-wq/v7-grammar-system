"""
OPA + MFE 기반 트레일링 vs 고정 TP 실험
=======================================

질문: OPA로 허가된 진입에서 트레일링이 실제로 추가 가치를 만드는가?

3-Arm 실험:
- Arm A: 고정 TP (TP=20, SL=12)
- Arm B: Partial + Trailing (TP1=20 50%, 나머지 트레일링)
- Arm C: Pure Trailing (TP 없음, 순수 추세 포획)
"""

import json
import os
from dataclasses import dataclass
from typing import List, Dict, Tuple
import statistics

@dataclass
class Trade:
    signal: str
    mfe: float  # Max Favorable Excursion
    mae: float  # Max Adverse Excursion
    result: str
    bars: int
    theta_est: int


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
                bars=t['bars'],
                theta_est=estimate_theta(t['result'], t['bars']),
            )
            trades.append(trade)
    
    return trades


def arm_a_fixed_tp(mfe: float, mae: float, tp: float = 20, sl: float = 12) -> float:
    """Arm A: 고정 TP/SL"""
    if mae >= sl:
        return -sl
    if mfe >= tp:
        return tp
    return mfe * 0.3


def arm_b_partial_trail(mfe: float, mae: float, tp1: float = 20, sl: float = 12, 
                        trail_start: float = 20, trail_offset: float = 6) -> float:
    """Arm B: Partial + Trailing (50% TP1, 50% 트레일링)"""
    if mae >= sl:
        return -sl
    
    pnl = 0
    
    if mfe >= tp1:
        pnl += tp1 * 0.5
        
        remaining_mfe = mfe - tp1
        if remaining_mfe > 0:
            trail_capture = max(0, remaining_mfe - trail_offset)
            pnl += trail_capture * 0.5
        
        return pnl
    
    return mfe * 0.3


def arm_c_pure_trail(mfe: float, mae: float, sl: float = 12,
                     trail_start: float = 10, trail_offset: float = 6) -> float:
    """Arm C: Pure Trailing (TP 없음)"""
    if mae >= sl:
        return -sl
    
    if mfe < trail_start:
        return mfe * 0.3
    
    captured = max(0, mfe - trail_offset)
    return captured


def analyze_arm(trades: List[Trade], arm_func, arm_name: str, **kwargs) -> Dict:
    """Arm 성과 분석"""
    pnls = []
    mfe_captured = []
    
    for t in trades:
        pnl = arm_func(t.mfe, t.mae, **kwargs)
        pnls.append(pnl)
        
        if t.mfe > 0:
            capture_rate = max(0, pnl) / t.mfe if t.mfe > 0 else 0
            mfe_captured.append(capture_rate)
    
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    
    return {
        "arm": arm_name,
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "winrate": wins / (wins + losses) * 100 if (wins + losses) > 0 else None,
        "total_pnl": round(sum(pnls), 2),
        "avg_pnl": round(statistics.mean(pnls), 2) if pnls else 0,
        "std_pnl": round(statistics.stdev(pnls), 2) if len(pnls) > 1 else 0,
        "avg_mfe_capture": round(statistics.mean(mfe_captured) * 100, 1) if mfe_captured else 0,
        "min_pnl": round(min(pnls), 2) if pnls else 0,
        "max_pnl": round(max(pnls), 2) if pnls else 0,
    }


def main():
    print("=" * 70)
    print("OPA + MFE 기반 트레일링 vs 고정 TP 실험")
    print("=" * 70)
    
    trades = load_data()
    
    # OPA 통과 거래만 (θ≥1)
    opa_trades = [t for t in trades if t.theta_est >= 1]
    theta_1_trades = [t for t in trades if t.theta_est == 1]
    theta_3_trades = [t for t in trades if t.theta_est >= 3]
    
    print(f"\n📊 데이터:")
    print(f"   전체: {len(trades)}건")
    print(f"   OPA 통과 (θ≥1): {len(opa_trades)}건")
    print(f"   θ=1: {len(theta_1_trades)}건")
    print(f"   θ≥3: {len(theta_3_trades)}건")
    
    # MFE 분포 확인
    mfe_values = [t.mfe for t in opa_trades if t.mfe > 0]
    if mfe_values:
        print(f"\n📊 MFE 분포 (θ≥1):")
        print(f"   평균: {statistics.mean(mfe_values):.1f}pt")
        print(f"   중앙값: {statistics.median(mfe_values):.1f}pt")
        print(f"   최대: {max(mfe_values):.1f}pt")
    
    # 3-Arm 실험
    print("\n" + "=" * 70)
    print("🧪 3-Arm 실험 결과")
    print("=" * 70)
    
    arms = [
        ("Arm A: 고정 TP", arm_a_fixed_tp, {}),
        ("Arm B: Partial+Trail", arm_b_partial_trail, {}),
        ("Arm C: Pure Trail", arm_c_pure_trail, {}),
    ]
    
    # 전체 OPA 결과
    print("\n📌 전체 OPA 통과 (θ≥1)")
    print("-" * 70)
    print(f"| Arm | Trades | Wins | Losses | Winrate | Avg PnL | Std | MFE활용 |")
    print(f"|-----|--------|------|--------|---------|---------|-----|---------|")
    
    all_results = {}
    for arm_name, arm_func, kwargs in arms:
        result = analyze_arm(opa_trades, arm_func, arm_name, **kwargs)
        all_results[arm_name] = result
        wr = f"{result['winrate']:.1f}%" if result['winrate'] else "N/A"
        print(f"| {arm_name[:20]} | {result['trades']} | {result['wins']} | {result['losses']} | {wr} | {result['avg_pnl']}pt | {result['std_pnl']} | {result['avg_mfe_capture']}% |")
    
    # θ=1 결과
    if theta_1_trades:
        print("\n📌 θ=1 (유지되지만 변동성 있음)")
        print("-" * 70)
        print(f"| Arm | Trades | Avg PnL | Std | MFE활용 |")
        print(f"|-----|--------|---------|-----|---------|")
        
        theta1_results = {}
        for arm_name, arm_func, kwargs in arms:
            result = analyze_arm(theta_1_trades, arm_func, arm_name, **kwargs)
            theta1_results[arm_name] = result
            print(f"| {arm_name[:20]} | {result['trades']} | {result['avg_pnl']}pt | {result['std_pnl']} | {result['avg_mfe_capture']}% |")
    
    # θ≥3 결과
    print("\n📌 θ≥3 (확정 상태)")
    print("-" * 70)
    print(f"| Arm | Trades | Avg PnL | Std | MFE활용 |")
    print(f"|-----|--------|---------|-----|---------|")
    
    theta3_results = {}
    for arm_name, arm_func, kwargs in arms:
        result = analyze_arm(theta_3_trades, arm_func, arm_name, **kwargs)
        theta3_results[arm_name] = result
        print(f"| {arm_name[:20]} | {result['trades']} | {result['avg_pnl']}pt | {result['std_pnl']} | {result['avg_mfe_capture']}% |")
    
    # 비교 분석
    print("\n" + "=" * 70)
    print("📊 비교 분석")
    print("=" * 70)
    
    arm_a = all_results["Arm A: 고정 TP"]
    arm_b = all_results["Arm B: Partial+Trail"]
    arm_c = all_results["Arm C: Pure Trail"]
    
    # EV 비교
    print(f"\n📈 EV (기대값) 비교:")
    print(f"   Arm A (고정): {arm_a['avg_pnl']}pt/trade")
    print(f"   Arm B (Partial): {arm_b['avg_pnl']}pt/trade")
    print(f"   Arm C (Pure): {arm_c['avg_pnl']}pt/trade")
    
    best_ev = max([(arm_a['avg_pnl'], 'A'), (arm_b['avg_pnl'], 'B'), (arm_c['avg_pnl'], 'C')])
    print(f"   → 최고 EV: Arm {best_ev[1]} ({best_ev[0]}pt)")
    
    # 분산 비교
    print(f"\n📉 분산 (리스크) 비교:")
    print(f"   Arm A (고정): σ={arm_a['std_pnl']}")
    print(f"   Arm B (Partial): σ={arm_b['std_pnl']}")
    print(f"   Arm C (Pure): σ={arm_c['std_pnl']}")
    
    # MFE 활용률 비교
    print(f"\n🎯 MFE 활용률:")
    print(f"   Arm A (고정): {arm_a['avg_mfe_capture']}%")
    print(f"   Arm B (Partial): {arm_b['avg_mfe_capture']}%")
    print(f"   Arm C (Pure): {arm_c['avg_mfe_capture']}%")
    
    # 결론
    print("\n" + "=" * 70)
    print("🎯 결론")
    print("=" * 70)
    
    # 판정 규칙
    ev_diff_ab = abs(arm_a['avg_pnl'] - arm_b['avg_pnl']) / arm_a['avg_pnl'] * 100 if arm_a['avg_pnl'] != 0 else 0
    std_increase_b = (arm_b['std_pnl'] - arm_a['std_pnl']) / arm_a['std_pnl'] * 100 if arm_a['std_pnl'] != 0 else 0
    
    print(f"\n📌 판정 기준:")
    print(f"   EV 차이 (A vs B): {ev_diff_ab:.1f}%")
    print(f"   분산 증가 (A → B): {std_increase_b:.1f}%")
    
    if ev_diff_ab < 5:
        conclusion = "EV 차이 < 5% → 단순한 쪽 (Arm A 고정 TP) 채택"
    elif std_increase_b > 20:
        conclusion = "분산 증가 > 20% → Arm B 폐기, Arm A 채택"
    elif arm_b['avg_pnl'] > arm_a['avg_pnl']:
        conclusion = "Arm B가 EV 우위 + 분산 허용 범위 → Arm B 채택"
    else:
        conclusion = "Arm A가 최적"
    
    print(f"\n✅ 결론: {conclusion}")
    
    # θ별 권장
    print("\n📌 θ별 권장:")
    if theta3_results:
        theta3_a = theta3_results["Arm A: 고정 TP"]
        theta3_b = theta3_results["Arm B: Partial+Trail"]
        if theta3_a['avg_pnl'] >= theta3_b['avg_pnl']:
            print(f"   θ≥3: 고정 TP 권장 (Arm A: {theta3_a['avg_pnl']}pt vs Arm B: {theta3_b['avg_pnl']}pt)")
        else:
            print(f"   θ≥3: Partial+Trail 고려 (Arm B: {theta3_b['avg_pnl']}pt > Arm A: {theta3_a['avg_pnl']}pt)")
    
    if theta1_results:
        theta1_a = theta1_results["Arm A: 고정 TP"]
        theta1_b = theta1_results["Arm B: Partial+Trail"]
        if theta1_b['avg_pnl'] > theta1_a['avg_pnl']:
            print(f"   θ=1: Partial+Trail 고려 (Arm B: {theta1_b['avg_pnl']}pt > Arm A: {theta1_a['avg_pnl']}pt)")
        else:
            print(f"   θ=1: 고정 TP 권장 (Arm A: {theta1_a['avg_pnl']}pt)")
    
    # 최종 권장
    print("\n" + "=" * 70)
    print("📜 최종 권장")
    print("=" * 70)
    
    print("""
┌─────────────────────────────────────────────────────────┐
│ OPA 이후 종료 규칙 권장                                  │
├─────────────────────────────────────────────────────────┤
│ 1. 기본: 고정 TP (TP=20pt, SL=12pt)                     │
│    - 단순, 예측 가능, OPA 철학과 일치                    │
│                                                         │
│ 2. 선택적: Partial + Trail (θ=1에서만)                  │
│    - 50% @ TP1, 50% 트레일링                            │
│    - 변동성 큰 날 추가 수익 포착                         │
│                                                         │
│ 3. 비권장: Pure Trailing                                │
│    - 분산 증가, 확정성 감소                             │
│    - OPA 철학과 충돌                                    │
└─────────────────────────────────────────────────────────┘
""")
    
    # 결과 저장
    results = {
        "experiment": "Trailing vs Fixed TP",
        "opa_all": all_results,
        "theta_1": theta1_results if theta_1_trades else {},
        "theta_3": theta3_results,
        "conclusion": conclusion,
        "recommendation": {
            "default": "Fixed TP (TP=20pt, SL=12pt)",
            "optional": "Partial + Trail for θ=1 only",
            "not_recommended": "Pure Trailing",
        }
    }
    
    with open('v7-grammar-system/experiments/trailing_experiment_results.json', 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n결과 저장: trailing_experiment_results.json")
    
    return results


if __name__ == "__main__":
    os.chdir('/home/runner/workspace')
    main()
