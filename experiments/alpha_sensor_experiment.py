"""
초동 알파 + 섹터 동조 검증 실험
==================================

실험 목표:
H₁: 초동 상태 변화 + 섹터 동조 정보는 OPA의 실행 성능을 
    악화시키지 않으면서 실행 타이밍을 앞당기거나 안정화한다.

3-Arm 비교:
- Arm A: Baseline OPA (현재)
- Arm B: 초동 관측 (비실행, 상관관계 측정)
- Arm C: 섹터 동조 가중 OPA

핵심 지표:
1. 실행 타이밍 (Bars to Execution)
2. 성능 유지 (승률, EV, DD)
3. 위험 집중 (Fast Collapse, Zone Loss)
"""

import json
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

@dataclass
class Trade:
    time: str
    signal: str
    direction: str
    entry: float
    exit: float
    result: str  # TP, SL, TIMEOUT
    pnl: float
    bars: int
    theta_est: int = 0
    sector_aligned: bool = False
    early_signal: bool = False  # 초동 신호 여부


def load_backtest_data():
    """백테스트 데이터 로드"""
    with open('backtest_python_results.json', 'r') as f:
        return json.load(f)


def estimate_theta(trade: Trade) -> int:
    """θ 추정 (결과 기반)"""
    if trade.result == 'TP':
        return 3
    elif trade.result == 'TIMEOUT':
        if trade.bars < 30:
            return 2
        else:
            return 1
    else:
        return 0


def parse_time(time_str: str) -> datetime:
    """시간 파싱 헬퍼"""
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except:
        return datetime.strptime(time_str[:16], "%Y-%m-%d %H:%M")


def detect_early_signal(trade: Trade, all_trades: List[Trade]) -> bool:
    """
    초동 신호 감지:
    - 같은 시간대(±5분)에 같은 방향 신호가 3개 이상이면 초동
    """
    trade_time = parse_time(trade.time)
    same_direction = [
        t for t in all_trades
        if t.direction == trade.direction
        and abs((parse_time(t.time) - trade_time).total_seconds()) <= 300
    ]
    return len(same_direction) >= 3


def detect_sector_alignment(trade: Trade, all_trades: List[Trade]) -> bool:
    """
    섹터 동조 감지:
    - 같은 시간대(±10분)에 같은 방향 TP 비율이 70% 이상
    """
    trade_time = parse_time(trade.time)
    same_window = [
        t for t in all_trades
        if abs((parse_time(t.time) - trade_time).total_seconds()) <= 600
    ]
    if len(same_window) < 3:
        return False
    
    same_direction = [t for t in same_window if t.direction == trade.direction]
    if len(same_direction) < 2:
        return False
    
    tp_rate = sum(1 for t in same_direction if t.result == 'TP') / len(same_direction)
    return tp_rate >= 0.7


def run_arm_a_baseline(trades: List[Trade]) -> Dict:
    """Arm A: Baseline OPA (θ≥1 필터만)"""
    filtered = [t for t in trades if t.theta_est >= 1]
    
    tp = sum(1 for t in filtered if t.result == 'TP')
    sl = sum(1 for t in filtered if t.result == 'SL')
    
    return {
        "name": "Arm A: Baseline OPA",
        "total": len(filtered),
        "tp": tp,
        "sl": sl,
        "winrate": tp / (tp + sl) * 100 if (tp + sl) > 0 else 0,
        "avg_bars": sum(t.bars for t in filtered) / len(filtered) if filtered else 0,
        "pnl": sum(t.pnl for t in filtered),
    }


def run_arm_b_observation(trades: List[Trade]) -> Dict:
    """Arm B: 초동 관측 (비실행, 상관관계 측정)"""
    # 초동 신호 vs 미래 θ 상관관계 분석
    early_signals = [t for t in trades if t.early_signal]
    non_early = [t for t in trades if not t.early_signal]
    
    early_tp_rate = sum(1 for t in early_signals if t.result == 'TP') / len(early_signals) if early_signals else 0
    non_early_tp_rate = sum(1 for t in non_early if t.result == 'TP') / len(non_early) if non_early else 0
    
    # 초동 신호 후 θ≥1 도달 비율
    early_certified = [t for t in early_signals if t.theta_est >= 1]
    certification_rate = len(early_certified) / len(early_signals) if early_signals else 0
    
    return {
        "name": "Arm B: 초동 관측 (비실행)",
        "early_signal_count": len(early_signals),
        "early_tp_rate": early_tp_rate * 100,
        "non_early_tp_rate": non_early_tp_rate * 100,
        "certification_rate": certification_rate * 100,
        "correlation": "양의 상관" if early_tp_rate > non_early_tp_rate else "음의 상관",
    }


def run_arm_c_sector_weighted(trades: List[Trade]) -> Dict:
    """Arm C: 섹터 동조 가중 OPA"""
    results = []
    
    for t in trades:
        # 섹터 동조 시 effective_theta 증가
        base_theta = t.theta_est
        if t.sector_aligned:
            effective_theta = base_theta + 1
        else:
            effective_theta = base_theta
        
        # effective_theta ≥ 1이면 실행
        if effective_theta >= 1:
            results.append(t)
    
    tp = sum(1 for t in results if t.result == 'TP')
    sl = sum(1 for t in results if t.result == 'SL')
    
    # 섹터 동조로 앞당겨진 진입 수
    accelerated = [t for t in results if t.theta_est == 0 and t.sector_aligned]
    
    return {
        "name": "Arm C: 섹터 동조 가중 OPA",
        "total": len(results),
        "tp": tp,
        "sl": sl,
        "winrate": tp / (tp + sl) * 100 if (tp + sl) > 0 else 0,
        "avg_bars": sum(t.bars for t in results) / len(results) if results else 0,
        "pnl": sum(t.pnl for t in results),
        "accelerated_entries": len(accelerated),
        "accelerated_tp": sum(1 for t in accelerated if t.result == 'TP'),
    }


def calculate_risk_metrics(trades: List[Trade], label: str) -> Dict:
    """위험 집중 지표 계산"""
    # Fast Collapse: 5 bar 이내 SL
    fast_collapse = sum(1 for t in trades if t.result == 'SL' and t.bars <= 5)
    fast_collapse_rate = fast_collapse / len(trades) * 100 if trades else 0
    
    # Zone Loss: 연속 손실
    consecutive_losses = 0
    max_consecutive = 0
    for t in trades:
        if t.result == 'SL':
            consecutive_losses += 1
            max_consecutive = max(max_consecutive, consecutive_losses)
        else:
            consecutive_losses = 0
    
    return {
        "label": label,
        "fast_collapse_count": fast_collapse,
        "fast_collapse_rate": fast_collapse_rate,
        "max_consecutive_losses": max_consecutive,
    }


def main():
    print("=" * 70)
    print("초동 알파 + 섹터 동조 검증 실험")
    print("=" * 70)
    
    # 데이터 로드
    data = load_backtest_data()
    
    # Trade 객체로 변환
    all_trades = []
    for r in data.get('all_results', []):
        signal_name = r['signal'].split(' (')[0]
        for t in r.get('trades', []):
            trade = Trade(
                time=t['time'].split('-05:00')[0] if '-05:00' in t['time'] else t['time'],
                signal=signal_name,
                direction=r['direction'],
                entry=t['entry'],
                exit=t['entry'] + t['pnl'],  # exit 추정
                result=t['result'],
                pnl=t['pnl'],
                bars=t['bars'],
            )
            trade.theta_est = estimate_theta(trade)
            all_trades.append(trade)
    
    print(f"\n📊 데이터: {len(all_trades)} 거래")
    
    # 초동 신호 & 섹터 동조 감지
    print("\n🔍 초동 신호 & 섹터 동조 감지 중...")
    for trade in all_trades:
        trade.early_signal = detect_early_signal(trade, all_trades)
        trade.sector_aligned = detect_sector_alignment(trade, all_trades)
    
    early_count = sum(1 for t in all_trades if t.early_signal)
    sector_count = sum(1 for t in all_trades if t.sector_aligned)
    print(f"   초동 신호: {early_count} ({early_count/len(all_trades)*100:.1f}%)")
    print(f"   섹터 동조: {sector_count} ({sector_count/len(all_trades)*100:.1f}%)")
    
    # 3-Arm 실험 실행
    print("\n" + "=" * 70)
    print("실험 결과")
    print("=" * 70)
    
    # Arm A: Baseline
    arm_a = run_arm_a_baseline(all_trades)
    print(f"\n📌 {arm_a['name']}")
    print(f"   거래: {arm_a['total']}건")
    print(f"   승률: {arm_a['winrate']:.1f}%")
    print(f"   평균 bars: {arm_a['avg_bars']:.1f}")
    print(f"   PnL: {arm_a['pnl']:.1f}pt")
    
    # Arm B: 초동 관측
    arm_b = run_arm_b_observation(all_trades)
    print(f"\n📌 {arm_b['name']}")
    print(f"   초동 신호 수: {arm_b['early_signal_count']}건")
    print(f"   초동 TP율: {arm_b['early_tp_rate']:.1f}%")
    print(f"   비초동 TP율: {arm_b['non_early_tp_rate']:.1f}%")
    print(f"   인증 도달률: {arm_b['certification_rate']:.1f}%")
    print(f"   상관관계: {arm_b['correlation']}")
    
    # Arm C: 섹터 가중
    arm_c = run_arm_c_sector_weighted(all_trades)
    print(f"\n📌 {arm_c['name']}")
    print(f"   거래: {arm_c['total']}건")
    print(f"   승률: {arm_c['winrate']:.1f}%")
    print(f"   평균 bars: {arm_c['avg_bars']:.1f}")
    print(f"   PnL: {arm_c['pnl']:.1f}pt")
    print(f"   앞당겨진 진입: {arm_c['accelerated_entries']}건")
    print(f"   앞당겨진 TP: {arm_c['accelerated_tp']}건")
    
    # 위험 지표 비교
    print("\n" + "=" * 70)
    print("위험 집중 지표 비교")
    print("=" * 70)
    
    arm_a_trades = [t for t in all_trades if t.theta_est >= 1]
    arm_c_trades = [t for t in all_trades if (t.theta_est >= 1) or (t.theta_est == 0 and t.sector_aligned)]
    
    risk_a = calculate_risk_metrics(arm_a_trades, "Arm A")
    risk_c = calculate_risk_metrics(arm_c_trades, "Arm C")
    
    print(f"\n| 지표 | Arm A (Baseline) | Arm C (섹터가중) | 판정 |")
    print(f"|------|-----------------|-----------------|------|")
    print(f"| Fast Collapse | {risk_a['fast_collapse_rate']:.1f}% | {risk_c['fast_collapse_rate']:.1f}% | {'✅' if risk_c['fast_collapse_rate'] <= risk_a['fast_collapse_rate'] else '❌'} |")
    print(f"| 최대 연속 손실 | {risk_a['max_consecutive_losses']} | {risk_c['max_consecutive_losses']} | {'✅' if risk_c['max_consecutive_losses'] <= risk_a['max_consecutive_losses'] else '❌'} |")
    
    # 최종 판정
    print("\n" + "=" * 70)
    print("🎯 최종 판정")
    print("=" * 70)
    
    # 판정 조건
    winrate_ok = arm_c['winrate'] >= arm_a['winrate'] - 2  # 2% 허용
    pnl_ok = arm_c['pnl'] >= arm_a['pnl'] * 0.95  # 5% 감소 허용
    risk_ok = risk_c['fast_collapse_rate'] <= risk_a['fast_collapse_rate'] * 1.1  # 10% 증가 허용
    acceleration_ok = arm_c['accelerated_entries'] > 0 and arm_c['accelerated_tp'] > 0
    
    print(f"\n✓ 승률 유지: {'✅' if winrate_ok else '❌'} ({arm_a['winrate']:.1f}% → {arm_c['winrate']:.1f}%)")
    print(f"✓ PnL 유지: {'✅' if pnl_ok else '❌'} ({arm_a['pnl']:.0f} → {arm_c['pnl']:.0f})")
    print(f"✓ 위험 유지: {'✅' if risk_ok else '❌'} (Fast Collapse {risk_a['fast_collapse_rate']:.1f}% → {risk_c['fast_collapse_rate']:.1f}%)")
    print(f"✓ 가속 효과: {'✅' if acceleration_ok else '❌'} ({arm_c['accelerated_entries']}건 앞당김, {arm_c['accelerated_tp']}건 TP)")
    
    # Case 판정
    all_pass = winrate_ok and pnl_ok and risk_ok
    has_acceleration = acceleration_ok
    
    if all_pass and has_acceleration:
        result = "🟢 Case 1: 성공 - 초동 알파는 OPA 인증 가속기로 작동"
    elif all_pass and not has_acceleration:
        result = "🟡 Case 2: 중립 - 섹터 정보는 무해하지만 불필요"
    else:
        result = "🔴 Case 3: 실패 - 초동/섹터 정보는 실행에 독"
    
    print(f"\n{result}")
    
    # 상관관계 분석 추가
    print("\n" + "=" * 70)
    print("📈 초동 → θ 인증 상관관계 상세")
    print("=" * 70)
    
    early_and_certified = sum(1 for t in all_trades if t.early_signal and t.theta_est >= 1)
    early_not_certified = sum(1 for t in all_trades if t.early_signal and t.theta_est == 0)
    
    print(f"\n초동 신호 중:")
    print(f"  - θ≥1 인증됨: {early_and_certified}건 ({early_and_certified/early_count*100:.1f}%)")
    print(f"  - 미인증: {early_not_certified}건 ({early_not_certified/early_count*100:.1f}%)")
    
    if arm_b['early_tp_rate'] > arm_b['non_early_tp_rate']:
        print(f"\n✅ 초동 신호 TP율({arm_b['early_tp_rate']:.1f}%) > 비초동({arm_b['non_early_tp_rate']:.1f}%)")
        print("   → 초동은 유효한 선행 지표!")
    else:
        print(f"\n⚠️ 초동 신호 TP율({arm_b['early_tp_rate']:.1f}%) ≤ 비초동({arm_b['non_early_tp_rate']:.1f}%)")
        print("   → 초동 단독으로는 예측력 없음")
    
    # 결과 저장
    results = {
        "arm_a": arm_a,
        "arm_b": arm_b,
        "arm_c": arm_c,
        "risk_a": risk_a,
        "risk_c": risk_c,
        "judgment": {
            "winrate_ok": winrate_ok,
            "pnl_ok": pnl_ok,
            "risk_ok": risk_ok,
            "acceleration_ok": acceleration_ok,
            "result": result,
        }
    }
    
    with open('v7-grammar-system/experiments/alpha_sensor_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print("\n결과 저장: alpha_sensor_results.json")
    
    return results


if __name__ == "__main__":
    os.chdir('/home/runner/workspace')
    main()
