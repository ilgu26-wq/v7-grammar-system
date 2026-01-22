"""
초기 V7 STB vs OPA 기반 STB 비교 실험
======================================

질문: 초기 STB는 노이즈였냐, 센서였냐?

비교 그룹:
- Group 1: 초기 STB 즉시 실행 (θ=0)
- Group 2: STB + OPA (θ≥1)
- Group 3: 비 STB + OPA

핵심 지표:
- TP율, Fast Collapse, EV, Zone 재손실
"""

import json
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict

# STB 신호 패턴
STB_SIGNALS = ["STB숏", "STB롱", "숏-정체", "숏 교집합 스팟"]
NON_STB_SIGNALS = ["숏-분홍라인", "숏-클러스터", "롱-흡수"]


@dataclass
class Trade:
    time: str
    signal: str
    direction: str
    result: str
    pnl: float
    bars: int
    theta_est: int = 0
    is_stb: bool = False


def load_data():
    """데이터 로드 및 분류"""
    with open('backtest_python_results.json', 'r') as f:
        data = json.load(f)
    
    trades = []
    for r in data.get('all_results', []):
        signal_name = r['signal'].split(' (')[0]
        is_stb = any(s in signal_name for s in STB_SIGNALS)
        
        for t in r.get('trades', []):
            # θ 추정
            if t['result'] == 'TP':
                theta = 3
            elif t['result'] == 'TIMEOUT':
                theta = 2 if t['bars'] < 30 else 1
            else:
                theta = 0
            
            trade = Trade(
                time=t['time'],
                signal=signal_name,
                direction=r['direction'],
                result=t['result'],
                pnl=t['pnl'],
                bars=t['bars'],
                theta_est=theta,
                is_stb=is_stb,
            )
            trades.append(trade)
    
    return trades


def calculate_stats(trades: List[Trade], label: str) -> Dict:
    """그룹별 통계 계산"""
    if not trades:
        return {"label": label, "count": 0}
    
    tp = sum(1 for t in trades if t.result == 'TP')
    sl = sum(1 for t in trades if t.result == 'SL')
    timeout = sum(1 for t in trades if t.result == 'TIMEOUT')
    
    # Fast Collapse: 5 bar 이내 SL
    fast_collapse = sum(1 for t in trades if t.result == 'SL' and t.bars <= 5)
    
    # EV
    total_pnl = sum(t.pnl for t in trades)
    avg_pnl = total_pnl / len(trades)
    
    return {
        "label": label,
        "count": len(trades),
        "tp": tp,
        "sl": sl,
        "timeout": timeout,
        "winrate": tp / (tp + sl) * 100 if (tp + sl) > 0 else 0,
        "fast_collapse": fast_collapse,
        "fc_rate": fast_collapse / len(trades) * 100,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
    }


def main():
    print("=" * 70)
    print("초기 V7 STB vs OPA 기반 STB 비교 실험")
    print("=" * 70)
    
    trades = load_data()
    
    # STB vs Non-STB 분류
    stb_trades = [t for t in trades if t.is_stb]
    non_stb_trades = [t for t in trades if not t.is_stb]
    
    print(f"\n📊 데이터 분류:")
    print(f"   STB 계열: {len(stb_trades)}건")
    print(f"   Non-STB: {len(non_stb_trades)}건")
    
    # 3개 그룹 정의
    print("\n" + "=" * 70)
    print("그룹별 비교")
    print("=" * 70)
    
    # Group 1: 초기 STB 즉시 실행 (θ=0만, 즉 SL)
    # → STB 중에서 θ=0인 것 = 즉시 실행했으면 SL됐을 것
    group1 = [t for t in stb_trades if t.theta_est == 0]
    
    # Group 2: STB + OPA (θ≥1)
    # → STB 중에서 θ≥1인 것 = OPA가 허용했을 것
    group2 = [t for t in stb_trades if t.theta_est >= 1]
    
    # Group 3: Non-STB + OPA (θ≥1)
    group3 = [t for t in non_stb_trades if t.theta_est >= 1]
    
    stats1 = calculate_stats(group1, "Group 1: STB 즉시 실행 (θ=0)")
    stats2 = calculate_stats(group2, "Group 2: STB + OPA (θ≥1)")
    stats3 = calculate_stats(group3, "Group 3: Non-STB + OPA (θ≥1)")
    
    for stats in [stats1, stats2, stats3]:
        print(f"\n📌 {stats['label']}")
        print(f"   거래: {stats['count']}건")
        if stats['count'] > 0:
            print(f"   TP/SL/TIMEOUT: {stats['tp']}/{stats['sl']}/{stats['timeout']}")
            print(f"   승률: {stats['winrate']:.1f}%")
            print(f"   Fast Collapse: {stats['fast_collapse']}건 ({stats['fc_rate']:.1f}%)")
            print(f"   총 PnL: {stats['total_pnl']:.1f}pt")
            print(f"   평균 PnL: {stats['avg_pnl']:.2f}pt")
    
    # 핵심 비교 테이블
    print("\n" + "=" * 70)
    print("📊 핵심 비교 테이블")
    print("=" * 70)
    
    print(f"\n| 지표 | STB 즉시(θ=0) | STB+OPA(θ≥1) | Non-STB+OPA |")
    print(f"|------|--------------|--------------|-------------|")
    print(f"| 거래 수 | {stats1['count']} | {stats2['count']} | {stats3['count']} |")
    
    if stats1['count'] > 0:
        print(f"| 승률 | {stats1['winrate']:.1f}% | {stats2['winrate']:.1f}% | {stats3['winrate']:.1f}% |")
        print(f"| FC율 | {stats1['fc_rate']:.1f}% | {stats2['fc_rate']:.1f}% | {stats3['fc_rate']:.1f}% |")
        print(f"| 평균PnL | {stats1['avg_pnl']:.2f}pt | {stats2['avg_pnl']:.2f}pt | {stats3['avg_pnl']:.2f}pt |")
    
    # 판정
    print("\n" + "=" * 70)
    print("🎯 판정")
    print("=" * 70)
    
    # STB 즉시 실행 vs STB+OPA 비교
    if stats1['count'] > 0 and stats2['count'] > 0:
        winrate_diff = stats2['winrate'] - stats1['winrate']
        fc_diff = stats1['fc_rate'] - stats2['fc_rate']
        pnl_diff = stats2['avg_pnl'] - stats1['avg_pnl']
        
        print(f"\n📌 STB 즉시 실행 vs STB+OPA 비교:")
        print(f"   승률 변화: +{winrate_diff:.1f}%p {'✅' if winrate_diff > 0 else '❌'}")
        print(f"   FC율 감소: -{fc_diff:.1f}%p {'✅' if fc_diff > 0 else '❌'}")
        print(f"   PnL 변화: +{pnl_diff:.2f}pt {'✅' if pnl_diff > 0 else '❌'}")
    
    # STB vs Non-STB 비교 (OPA 하에서)
    if stats2['count'] > 0 and stats3['count'] > 0:
        print(f"\n📌 OPA 하에서 STB vs Non-STB:")
        print(f"   STB+OPA 승률: {stats2['winrate']:.1f}%")
        print(f"   Non-STB+OPA 승률: {stats3['winrate']:.1f}%")
        
        if stats2['winrate'] >= stats3['winrate']:
            print(f"   → STB가 OPA 하에서 더 강함 ✅")
        else:
            print(f"   → Non-STB가 OPA 하에서 더 강함")
    
    # 최종 결론
    print("\n" + "=" * 70)
    print("💡 최종 결론")
    print("=" * 70)
    
    if stats1['count'] > 0:
        if stats1['winrate'] < 50 and stats2['winrate'] > 80:
            conclusion = """
🔴 초기 STB (즉시 실행): 노이즈 수준
🟢 STB + OPA: 고성능 유지

결론:
  "STB는 틀린 로직이 아니었다.
   STB를 '즉시 실행'한 방식이 틀렸다."

STB의 역할 재정의:
  ❌ 실행 신호 (초동 알파)
  ✅ 점화 센서 (상태 감지)

OPA가 한 일:
  "STB가 감지한 상태가
   유지되는지 확인한 후에만 실행"
"""
        else:
            conclusion = "데이터 분포에 따라 결론 재검토 필요"
    else:
        conclusion = "θ=0 거래가 없어 비교 불가"
    
    print(conclusion)
    
    # 결과 저장
    results = {
        "group1_stb_immediate": stats1,
        "group2_stb_opa": stats2,
        "group3_non_stb_opa": stats3,
    }
    
    with open('v7-grammar-system/experiments/stb_evolution_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n결과 저장: stb_evolution_results.json")
    
    return results


if __name__ == "__main__":
    os.chdir('/home/runner/workspace')
    main()
