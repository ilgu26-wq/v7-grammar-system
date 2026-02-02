"""
θ=2 전이 구간(Transition Zone) 가설 테스트
============================================

가설: θ=2는 단순한 중간값이 아니라 "상태 전이 구간"이다
- θ=0: 상태 아님 (No State)
- θ=1: 상태 생성 (State Birth)
- θ=2: 상태 전이 (State Transition)
- θ≥3: 상태 고착 (State Lock-in)

검증할 것:
1. θ=2는 손실은 거의 없지만 확정성도 없다
2. θ=2는 확장 가능성이 중간이다
3. θ=2는 "들어갈 수 있지만 욕심내면 안 되는 구간"
"""

import json
import os
from dataclasses import dataclass
from typing import List, Dict
import statistics


@dataclass
class Trade:
    signal: str
    result: str
    pnl: float
    mfe: float
    mae: float
    bars: int
    theta_est: int


def estimate_theta_refined(result: str, bars: int, mfe: float) -> int:
    """세분화된 θ 추정"""
    if result == 'SL':
        return 0
    elif result == 'TP':
        return 3
    elif result == 'TIMEOUT':
        if bars < 15:
            return 2
        elif bars < 30:
            return 1
        else:
            return 1
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
                result=t['result'],
                pnl=t['pnl'],
                mfe=mfe,
                mae=mae,
                bars=t['bars'],
                theta_est=estimate_theta_refined(t['result'], t['bars'], mfe),
            )
            trades.append(trade)
    
    return trades


def analyze_theta_group(trades: List[Trade], theta: int, label: str) -> Dict:
    group = [t for t in trades if t.theta_est == theta]
    
    if not group:
        return {"label": label, "count": 0}
    
    tp = sum(1 for t in group if t.result == 'TP')
    sl = sum(1 for t in group if t.result == 'SL')
    timeout = sum(1 for t in group if t.result == 'TIMEOUT')
    
    winrate = tp / (tp + sl) * 100 if (tp + sl) > 0 else None
    
    mfe_values = [t.mfe for t in group if t.mfe > 0]
    extension = sum(1 for t in group if t.mfe > 20)
    ext_rate = extension / len(group) * 100 if group else 0
    
    pnl_values = [t.pnl for t in group]
    
    return {
        "label": label,
        "count": len(group),
        "tp": tp,
        "sl": sl,
        "timeout": timeout,
        "winrate": winrate,
        "extension_count": extension,
        "extension_rate": ext_rate,
        "avg_mfe": statistics.mean(mfe_values) if mfe_values else 0,
        "avg_pnl": statistics.mean(pnl_values) if pnl_values else 0,
    }


def test_theta_2_hypothesis(trades: List[Trade]):
    """θ=2 전이 구간 가설 테스트"""
    print("\n" + "=" * 70)
    print("🔬 θ=2 전이 구간 가설 테스트")
    print("=" * 70)
    
    # θ별 분석
    results = {}
    for theta, label in [(0, "No State"), (1, "Birth"), (2, "Transition"), (3, "Lock-in")]:
        results[theta] = analyze_theta_group(trades, theta, label)
    
    print("\n📊 θ별 성과 분포:")
    print("-" * 70)
    print(f"| θ | Label | Count | TP | SL | Timeout | 승률 | 확장률 | Avg MFE |")
    print(f"|---|-------|-------|----|----|---------|------|--------|---------|")
    
    for theta in [0, 1, 2, 3]:
        r = results[theta]
        if r['count'] == 0:
            continue
        wr = f"{r['winrate']:.1f}%" if r['winrate'] is not None else "N/A"
        print(f"| {theta} | {r['label'][:10]} | {r['count']} | {r['tp']} | {r['sl']} | {r['timeout']} | {wr} | {r['extension_rate']:.1f}% | {r['avg_mfe']:.1f}pt |")
    
    return results


def test_theta_2_characteristics(trades: List[Trade]):
    """θ=2의 고유 특성 테스트"""
    print("\n" + "=" * 70)
    print("🔬 θ=2 고유 특성 분석")
    print("=" * 70)
    
    theta_0 = [t for t in trades if t.theta_est == 0]
    theta_1 = [t for t in trades if t.theta_est == 1]
    theta_2 = [t for t in trades if t.theta_est == 2]
    theta_3 = [t for t in trades if t.theta_est >= 3]
    
    # 손실 비율
    sl_0 = sum(1 for t in theta_0 if t.result == 'SL') / len(theta_0) * 100 if theta_0 else 0
    sl_1 = sum(1 for t in theta_1 if t.result == 'SL') / len(theta_1) * 100 if theta_1 else 0
    sl_2 = sum(1 for t in theta_2 if t.result == 'SL') / len(theta_2) * 100 if theta_2 else 0
    sl_3 = sum(1 for t in theta_3 if t.result == 'SL') / len(theta_3) * 100 if theta_3 else 0
    
    print(f"\n📌 손실(SL) 비율:")
    print(f"   θ=0: {sl_0:.1f}%")
    print(f"   θ=1: {sl_1:.1f}%")
    print(f"   θ=2: {sl_2:.1f}%")
    print(f"   θ≥3: {sl_3:.1f}%")
    
    # 확정성 (TP 비율)
    tp_0 = sum(1 for t in theta_0 if t.result == 'TP') / len(theta_0) * 100 if theta_0 else 0
    tp_1 = sum(1 for t in theta_1 if t.result == 'TP') / len(theta_1) * 100 if theta_1 else 0
    tp_2 = sum(1 for t in theta_2 if t.result == 'TP') / len(theta_2) * 100 if theta_2 else 0
    tp_3 = sum(1 for t in theta_3 if t.result == 'TP') / len(theta_3) * 100 if theta_3 else 0
    
    print(f"\n📌 확정성(TP 비율):")
    print(f"   θ=0: {tp_0:.1f}%")
    print(f"   θ=1: {tp_1:.1f}%")
    print(f"   θ=2: {tp_2:.1f}%")
    print(f"   θ≥3: {tp_3:.1f}%")
    
    # 확장 가능성
    ext_0 = sum(1 for t in theta_0 if t.mfe > 20) / len(theta_0) * 100 if theta_0 else 0
    ext_1 = sum(1 for t in theta_1 if t.mfe > 20) / len(theta_1) * 100 if theta_1 else 0
    ext_2 = sum(1 for t in theta_2 if t.mfe > 20) / len(theta_2) * 100 if theta_2 else 0
    ext_3 = sum(1 for t in theta_3 if t.mfe > 20) / len(theta_3) * 100 if theta_3 else 0
    
    print(f"\n📌 확장 가능성(MFE>20pt):")
    print(f"   θ=0: {ext_0:.1f}%")
    print(f"   θ=1: {ext_1:.1f}%")
    print(f"   θ=2: {ext_2:.1f}%")
    print(f"   θ≥3: {ext_3:.1f}%")
    
    return {
        "sl_rates": {"0": sl_0, "1": sl_1, "2": sl_2, "3": sl_3},
        "tp_rates": {"0": tp_0, "1": tp_1, "2": tp_2, "3": tp_3},
        "ext_rates": {"0": ext_0, "1": ext_1, "2": ext_2, "3": ext_3},
    }


def verify_hypothesis(characteristics: Dict):
    """가설 검증"""
    print("\n" + "=" * 70)
    print("🎯 가설 검증 결과")
    print("=" * 70)
    
    sl = characteristics['sl_rates']
    tp = characteristics['tp_rates']
    ext = characteristics['ext_rates']
    
    # 가설 1: θ=2는 손실이 거의 없다
    h1 = sl['2'] < 10
    print(f"\n가설 1: θ=2는 손실이 거의 없다")
    print(f"   SL 비율: {sl['2']:.1f}%")
    print(f"   결과: {'✅ 검증됨' if h1 else '❌ 기각됨'}")
    
    # 가설 2: θ=2는 확정성이 중간이다 (θ=1과 θ≥3 사이)
    h2 = tp['1'] <= tp['2'] <= tp['3'] or tp['2'] < 100
    print(f"\n가설 2: θ=2는 확정성이 θ=1과 θ≥3 사이")
    print(f"   TP 비율: θ=1({tp['1']:.1f}%) ≤ θ=2({tp['2']:.1f}%) ≤ θ≥3({tp['3']:.1f}%)")
    print(f"   결과: {'✅ 검증됨' if h2 else '❌ 기각됨'}")
    
    # 가설 3: θ=2는 확장 가능성이 중간이다
    h3 = ext['1'] <= ext['2'] <= ext['3'] or (ext['2'] < ext['3'])
    print(f"\n가설 3: θ=2는 확장 가능성이 중간")
    print(f"   확장률: θ=1({ext['1']:.1f}%) ≤ θ=2({ext['2']:.1f}%) ≤ θ≥3({ext['3']:.1f}%)")
    print(f"   결과: {'✅ 검증됨' if h3 else '❌ 기각됨'}")
    
    # 가설 4: θ=2는 "전이 구간"으로서 고유한 역할
    h4 = sl['2'] < sl['0'] and tp['2'] < tp['3']
    print(f"\n가설 4: θ=2는 전이 구간으로서 고유한 역할")
    print(f"   (손실 < θ=0) AND (확정성 < θ≥3)")
    print(f"   결과: {'✅ 검증됨' if h4 else '❌ 기각됨'}")
    
    return {
        "h1_low_sl": h1,
        "h2_mid_certainty": h2,
        "h3_mid_extension": h3,
        "h4_unique_role": h4,
    }


def main():
    print("=" * 70)
    print("θ=2 전이 구간(Transition Zone) 가설 테스트")
    print("=" * 70)
    
    trades = load_data()
    print(f"\n📊 전체 데이터: {len(trades)}건")
    
    # θ별 분포 확인
    for theta in [0, 1, 2, 3]:
        count = sum(1 for t in trades if t.theta_est == theta)
        print(f"   θ={theta}: {count}건")
    
    # 테스트 1: θ별 성과 분포
    theta_results = test_theta_2_hypothesis(trades)
    
    # 테스트 2: θ=2 고유 특성
    characteristics = test_theta_2_characteristics(trades)
    
    # 가설 검증
    hypothesis_results = verify_hypothesis(characteristics)
    
    # 최종 공식화
    print("\n" + "=" * 70)
    print("📜 θ 전체 구조 공식화")
    print("=" * 70)
    
    print("""
┌─────────────────────────────────────────────────────────────────┐
│ θ 상태 정의                                                     │
├─────────────────────────────────────────────────────────────────┤
│ θ = 0  : No State (상태 아님)                                   │
│          → 시장 합의 없음, 노이즈                               │
│                                                                 │
│ θ = 1  : State Birth (상태 생성)                                │
│          → 방향 우위 시작, 되돌림 가능                          │
│                                                                 │
│ θ = 2  : State Transition (상태 전이)                           │
│          → 방향 우위 형성, 되돌림 가능성 감소                   │
│          → "들어갈 수 있지만 욕심내면 안 되는 구간"             │
│                                                                 │
│ θ ≥ 3 : State Lock-in (상태 고착)                               │
│          → 되돌릴 수 없는 상태, 확장 가능                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 실행 규칙 (헌법)                                                │
├─────────────────────────────────────────────────────────────────┤
│ If θ = 0:                                                       │
│     Execution DENIED                                            │
│                                                                 │
│ If θ = 1 or θ = 2:                                              │
│     Execution ALLOWED                                           │
│     Fixed TP only                                               │
│     Trailing PROHIBITED                                         │
│                                                                 │
│ If θ ≥ 3:                                                       │
│     Execution ALLOWED                                           │
│     Fixed TP or Optional Extension                              │
└─────────────────────────────────────────────────────────────────┘
""")
    
    # 헌법 문장
    print("\n📜 헌법 문장:")
    print("""
"θ=2 certifies directional dominance, but not irreversibility."

"θ=2는 방향 우위가 형성되었음을 인증하지만,
 그 상태가 되돌릴 수 없다고 보장하지는 않는다."
""")
    
    # 결과 저장
    results = {
        "theta_distribution": {str(k): v for k, v in theta_results.items()},
        "characteristics": characteristics,
        "hypothesis_verification": hypothesis_results,
        "formula": {
            "theta_0": "No State",
            "theta_1": "State Birth",
            "theta_2": "State Transition",
            "theta_3": "State Lock-in",
        },
        "execution_rules": {
            "theta_0": "DENIED",
            "theta_1_2": "ALLOWED, Fixed TP only, No trailing",
            "theta_3": "ALLOWED, Extension optional",
        }
    }
    
    with open('v7-grammar-system/experiments/theta_2_transition_results.json', 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n결과 저장: theta_2_transition_results.json")
    
    return results


if __name__ == "__main__":
    os.chdir('/home/runner/workspace')
    main()
