"""
시도 밀도 vs 손실 관리 분석
============================

질문: OPA가 너무 보수적인가?
- 유지 확률이 낮지만 0이 아닌 구간이 있는가?
- 그 구간에서 제한된 리스크로 시도할 가치가 있는가?
"""

import json
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Trade:
    signal: str
    result: str
    pnl: float
    bars: int
    theta_est: int  # 0, 1, 2, 3


def estimate_theta(result: str, bars: int) -> int:
    """θ 추정"""
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
            trade = Trade(
                signal=signal_name,
                result=t['result'],
                pnl=t['pnl'],
                bars=t['bars'],
                theta_est=estimate_theta(t['result'], t['bars']),
            )
            trades.append(trade)
    
    return trades


def analyze_by_theta(trades: List[Trade]) -> Dict:
    """θ별 성과 분석"""
    by_theta = defaultdict(list)
    for t in trades:
        by_theta[t.theta_est].append(t)
    
    results = {}
    for theta, group in sorted(by_theta.items()):
        tp = sum(1 for t in group if t.result == 'TP')
        sl = sum(1 for t in group if t.result == 'SL')
        timeout = sum(1 for t in group if t.result == 'TIMEOUT')
        
        decisive = tp + sl
        winrate = (tp / decisive * 100) if decisive > 0 else None
        
        total_pnl = sum(t.pnl for t in group)
        avg_pnl = total_pnl / len(group) if group else 0
        
        results[theta] = {
            "count": len(group),
            "tp": tp,
            "sl": sl,
            "timeout": timeout,
            "winrate": winrate,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(avg_pnl, 2),
        }
    
    return results


def main():
    print("=" * 70)
    print("시도 밀도 vs 손실 관리 분석")
    print("=" * 70)
    
    trades = load_data()
    total = len(trades)
    
    print(f"\n📊 총 거래: {total}건")
    
    # θ별 분석
    theta_results = analyze_by_theta(trades)
    
    print("\n" + "=" * 70)
    print("📌 θ별 성과 분포")
    print("=" * 70)
    
    print(f"\n| θ | 거래수 | TP | SL | Timeout | 승률 | Avg PnL |")
    print(f"|---|--------|----|----|---------|------|---------|")
    
    for theta in sorted(theta_results.keys()):
        r = theta_results[theta]
        wr = f"{r['winrate']:.1f}%" if r['winrate'] is not None else "N/A"
        pct = r['count'] / total * 100
        print(f"| {theta} | {r['count']} ({pct:.1f}%) | {r['tp']} | {r['sl']} | {r['timeout']} | {wr} | {r['avg_pnl']}pt |")
    
    # 핵심 질문: θ=0 구간에서 TP는 있는가?
    print("\n" + "=" * 70)
    print("🔍 핵심 질문: θ=0 구간에서 TP가 있는가?")
    print("=" * 70)
    
    theta_0 = theta_results.get(0, {})
    theta_0_tp = theta_0.get('tp', 0)
    theta_0_sl = theta_0.get('sl', 0)
    theta_0_count = theta_0.get('count', 0)
    
    print(f"\nθ=0 구간:")
    print(f"  총 {theta_0_count}건 중:")
    print(f"  - TP: {theta_0_tp}건 (있다면 OPA가 놓친 기회)")
    print(f"  - SL: {theta_0_sl}건 (OPA가 차단한 손실)")
    
    if theta_0_sl > 0 and theta_0_tp == 0:
        print(f"\n  ✅ θ=0 구간에서 TP=0, SL={theta_0_sl}")
        print(f"     → OPA는 정확했다. 놓친 기회 없음.")
    elif theta_0_tp > 0:
        print(f"\n  ⚠️ θ=0 구간에서도 TP {theta_0_tp}건 있음")
        print(f"     → 시도 밀도 관점에서 검토 필요")
    
    # 시도 밀도 분석
    print("\n" + "=" * 70)
    print("📊 시도 밀도 분석")
    print("=" * 70)
    
    # OPA 현재 (θ≥1)
    opa_trades = [t for t in trades if t.theta_est >= 1]
    opa_tp = sum(1 for t in opa_trades if t.result == 'TP')
    opa_sl = sum(1 for t in opa_trades if t.result == 'SL')
    
    # 전체 시도
    all_tp = sum(1 for t in trades if t.result == 'TP')
    all_sl = sum(1 for t in trades if t.result == 'SL')
    
    print(f"\n| 구간 | 시도 | TP | SL | 승률 | 비고 |")
    print(f"|------|------|----|----|------|------|")
    print(f"| OPA (θ≥1) | {len(opa_trades)} | {opa_tp} | {opa_sl} | {opa_tp/(opa_tp+opa_sl)*100 if (opa_tp+opa_sl)>0 else 0:.1f}% | 현재 |")
    print(f"| 전체 (θ≥0) | {total} | {all_tp} | {all_sl} | {all_tp/(all_tp+all_sl)*100 if (all_tp+all_sl)>0 else 0:.1f}% | 최대 시도 |")
    
    # 놓친 기회 비용 vs 차단한 손실
    missed_opportunity = theta_0_tp
    blocked_loss = theta_0_sl
    
    print("\n" + "=" * 70)
    print("⚖️ 트레이드오프 분석")
    print("=" * 70)
    
    print(f"\n📌 OPA가 θ=0 차단으로:")
    print(f"   - 차단한 손실 (SL): {blocked_loss}건")
    print(f"   - 놓친 기회 (TP): {missed_opportunity}건")
    
    if blocked_loss > 0 and missed_opportunity == 0:
        ratio = "∞ (완벽)"
    elif blocked_loss > 0:
        ratio = f"{blocked_loss/missed_opportunity:.1f}:1"
    else:
        ratio = "N/A"
    
    print(f"   - 손실:기회 비율: {ratio}")
    
    # Exploration Channel 제안
    print("\n" + "=" * 70)
    print("💡 이중 채널 운용 제안")
    print("=" * 70)
    
    print("""
┌──────────────────────────────────────────────────────────┐
│ 🛡️ Channel 1: OPA Execution (메인)                      │
│    조건: θ ≥ 1                                           │
│    목적: 손실 최소화, 계좌 보호                          │
│    리스크: 정상                                          │
├──────────────────────────────────────────────────────────┤
│ 🧪 Channel 2: Exploration (탐색, 선택적)                 │
│    조건: θ = 0 허용, 단 리스크 캡 필수                   │
│    목적: 데이터 수집, 미래 알파 탐색                     │
│    리스크: 하루 -0.25R 캡 / 1 SL = 즉시 종료            │
└──────────────────────────────────────────────────────────┘
""")
    
    # 결론
    print("=" * 70)
    print("🎯 결론")
    print("=" * 70)
    
    if missed_opportunity == 0:
        print(f"""
✅ OPA는 정확하다:
   - θ=0에서 TP 0건 → 놓친 기회 없음
   - θ=0에서 SL {blocked_loss}건 → 차단 성공
   
📌 현재 상태에서 Exploration은 불필요:
   - 데이터상 θ=0은 순수 노이즈
   - 시도해도 SL만 늘어남
   
🔒 권장: OPA 단독 운용 유지
""")
    else:
        exp_winrate = missed_opportunity / (missed_opportunity + blocked_loss) * 100 if (missed_opportunity + blocked_loss) > 0 else 0
        print(f"""
⚠️ θ=0에서도 기회 존재:
   - TP {missed_opportunity}건 / SL {blocked_loss}건
   - 승률: {exp_winrate:.1f}%
   
📌 Exploration Channel 검토 가치:
   - 리스크 캡: 하루 -0.25R
   - 연속 손실 1회 = 종료
   - 목적: 성과 ❌, 데이터 수집 ⭕
""")
    
    # 결과 저장
    results = {
        "total_trades": total,
        "theta_distribution": theta_results,
        "opa_coverage": {
            "count": len(opa_trades),
            "tp": opa_tp,
            "sl": opa_sl,
        },
        "theta_0_analysis": {
            "count": theta_0_count,
            "tp": theta_0_tp,
            "sl": theta_0_sl,
            "missed_opportunity": missed_opportunity,
            "blocked_loss": blocked_loss,
        },
        "conclusion": "OPA 단독 운용" if missed_opportunity == 0 else "이중 채널 검토",
    }
    
    with open('v7-grammar-system/experiments/exploration_density_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n결과 저장: exploration_density_results.json")
    
    return results


if __name__ == "__main__":
    os.chdir('/home/runner/workspace')
    main()
