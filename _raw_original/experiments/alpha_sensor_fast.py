"""
초동 알파 + 섹터 동조 검증 - 최적화 버전
============================================

시간 복잡도 개선: O(n²) → O(n log n) 
시간 윈도우 기반 해시맵 사용
"""

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Trade:
    time: str
    signal: str
    direction: str
    entry: float
    result: str
    pnl: float
    bars: int
    theta_est: int = 0
    minute_key: str = ""  # 분 단위 키


def load_and_process():
    """데이터 로드 및 전처리"""
    with open('backtest_python_results.json', 'r') as f:
        data = json.load(f)
    
    trades = []
    for r in data.get('all_results', []):
        signal_name = r['signal'].split(' (')[0]
        for t in r.get('trades', []):
            # 시간 정규화 (분 단위)
            time_str = t['time'].split('-05:00')[0] if '-05:00' in t['time'] else t['time']
            minute_key = time_str[:16]  # YYYY-MM-DD HH:MM
            
            # θ 추정
            if t['result'] == 'TP':
                theta = 3
            elif t['result'] == 'TIMEOUT':
                theta = 2 if t['bars'] < 30 else 1
            else:
                theta = 0
            
            trade = Trade(
                time=time_str,
                signal=signal_name,
                direction=r['direction'],
                entry=t['entry'],
                result=t['result'],
                pnl=t['pnl'],
                bars=t['bars'],
                theta_est=theta,
                minute_key=minute_key,
            )
            trades.append(trade)
    
    return trades


def build_time_index(trades: List[Trade]) -> Dict:
    """시간별 인덱스 구축 (5분 윈도우)"""
    index = defaultdict(list)
    for t in trades:
        # 5분 단위로 그룹화
        minute = int(t.minute_key[-2:])
        window = minute // 5 * 5
        window_key = f"{t.minute_key[:-2]}{window:02d}"
        index[window_key].append(t)
    return index


def analyze_early_signals(trades: List[Trade], time_index: Dict) -> Dict:
    """초동 신호 분석 (같은 5분 윈도우에 3개 이상)"""
    
    # 5분 윈도우별 방향별 거래 수
    window_stats = defaultdict(lambda: defaultdict(list))
    
    for window_key, window_trades in time_index.items():
        for t in window_trades:
            window_stats[window_key][t.direction].append(t)
    
    # 초동 신호: 윈도우에 같은 방향 3개 이상
    early_trades = []
    non_early_trades = []
    
    for t in trades:
        minute = int(t.minute_key[-2:])
        window = minute // 5 * 5
        window_key = f"{t.minute_key[:-2]}{window:02d}"
        
        same_dir_count = len(window_stats[window_key][t.direction])
        if same_dir_count >= 3:
            early_trades.append(t)
        else:
            non_early_trades.append(t)
    
    # 통계
    early_tp = sum(1 for t in early_trades if t.result == 'TP')
    early_sl = sum(1 for t in early_trades if t.result == 'SL')
    non_early_tp = sum(1 for t in non_early_trades if t.result == 'TP')
    non_early_sl = sum(1 for t in non_early_trades if t.result == 'SL')
    
    return {
        "early_count": len(early_trades),
        "non_early_count": len(non_early_trades),
        "early_tp_rate": early_tp / (early_tp + early_sl) * 100 if (early_tp + early_sl) > 0 else 0,
        "non_early_tp_rate": non_early_tp / (non_early_tp + non_early_sl) * 100 if (non_early_tp + non_early_sl) > 0 else 0,
        "early_certified": sum(1 for t in early_trades if t.theta_est >= 1),
    }


def analyze_sector_alignment(trades: List[Trade], time_index: Dict) -> Dict:
    """섹터 동조 분석 (10분 윈도우에서 같은 방향 TP율 70%+)"""
    
    # 10분 윈도우별 TP율 계산
    aligned_trades = []
    non_aligned_trades = []
    
    for t in trades:
        minute = int(t.minute_key[-2:])
        window = minute // 10 * 10
        window_key = f"{t.minute_key[:-2]}{window:02d}"
        
        # 같은 10분 윈도우의 같은 방향 거래들
        same_dir = [
            tr for tr in time_index.get(window_key, [])
            if tr.direction == t.direction
        ]
        
        if len(same_dir) >= 3:
            tp_rate = sum(1 for tr in same_dir if tr.result == 'TP') / len(same_dir)
            if tp_rate >= 0.7:
                aligned_trades.append(t)
            else:
                non_aligned_trades.append(t)
        else:
            non_aligned_trades.append(t)
    
    # 통계
    aligned_tp = sum(1 for t in aligned_trades if t.result == 'TP')
    aligned_sl = sum(1 for t in aligned_trades if t.result == 'SL')
    
    return {
        "aligned_count": len(aligned_trades),
        "aligned_tp_rate": aligned_tp / (aligned_tp + aligned_sl) * 100 if (aligned_tp + aligned_sl) > 0 else 0,
        "aligned_pnl": sum(t.pnl for t in aligned_trades),
    }


def run_3arm_experiment(trades: List[Trade]) -> Dict:
    """3-Arm 실험"""
    
    # Arm A: Baseline OPA (θ≥1)
    arm_a_trades = [t for t in trades if t.theta_est >= 1]
    arm_a_tp = sum(1 for t in arm_a_trades if t.result == 'TP')
    arm_a_sl = sum(1 for t in arm_a_trades if t.result == 'SL')
    
    arm_a = {
        "total": len(arm_a_trades),
        "winrate": arm_a_tp / (arm_a_tp + arm_a_sl) * 100 if (arm_a_tp + arm_a_sl) > 0 else 0,
        "pnl": sum(t.pnl for t in arm_a_trades),
        "fast_collapse": sum(1 for t in arm_a_trades if t.result == 'SL' and t.bars <= 5),
    }
    
    # Arm C: 섹터 가중 (θ=0이지만 동조 시 +1)
    # 시뮬레이션: 동조 윈도우의 θ=0 거래를 추가
    time_index = build_time_index(trades)
    
    # 동조 감지
    accelerated = []
    for t in trades:
        if t.theta_est == 0:  # 기존 OPA에서 차단된 거래
            minute = int(t.minute_key[-2:])
            window = minute // 10 * 10
            window_key = f"{t.minute_key[:-2]}{window:02d}"
            
            same_dir = [tr for tr in time_index.get(window_key, []) if tr.direction == t.direction]
            if len(same_dir) >= 3:
                tp_rate = sum(1 for tr in same_dir if tr.result == 'TP') / len(same_dir)
                if tp_rate >= 0.7:
                    accelerated.append(t)
    
    arm_c_trades = arm_a_trades + accelerated
    arm_c_tp = sum(1 for t in arm_c_trades if t.result == 'TP')
    arm_c_sl = sum(1 for t in arm_c_trades if t.result == 'SL')
    
    arm_c = {
        "total": len(arm_c_trades),
        "winrate": arm_c_tp / (arm_c_tp + arm_c_sl) * 100 if (arm_c_tp + arm_c_sl) > 0 else 0,
        "pnl": sum(t.pnl for t in arm_c_trades),
        "fast_collapse": sum(1 for t in arm_c_trades if t.result == 'SL' and t.bars <= 5),
        "accelerated": len(accelerated),
        "accelerated_tp": sum(1 for t in accelerated if t.result == 'TP'),
        "accelerated_sl": sum(1 for t in accelerated if t.result == 'SL'),
    }
    
    return {"arm_a": arm_a, "arm_c": arm_c}


def main():
    print("=" * 70)
    print("초동 알파 + 섹터 동조 검증 (최적화)")
    print("=" * 70)
    
    # 데이터 로드
    trades = load_and_process()
    print(f"\n📊 데이터: {len(trades)} 거래")
    
    # 시간 인덱스 구축
    time_index = build_time_index(trades)
    print(f"   시간 윈도우: {len(time_index)}개")
    
    # 초동 신호 분석
    print("\n" + "=" * 70)
    print("📌 Arm B: 초동 신호 분석")
    print("=" * 70)
    
    early_stats = analyze_early_signals(trades, time_index)
    print(f"   초동 신호: {early_stats['early_count']}건 ({early_stats['early_count']/len(trades)*100:.1f}%)")
    print(f"   초동 TP율: {early_stats['early_tp_rate']:.1f}%")
    print(f"   비초동 TP율: {early_stats['non_early_tp_rate']:.1f}%")
    print(f"   초동 중 θ≥1 인증: {early_stats['early_certified']}건")
    
    correlation = "양의 상관" if early_stats['early_tp_rate'] > early_stats['non_early_tp_rate'] else "음의 상관"
    print(f"   상관관계: {correlation}")
    
    # 3-Arm 실험
    print("\n" + "=" * 70)
    print("📌 3-Arm 실험 결과")
    print("=" * 70)
    
    results = run_3arm_experiment(trades)
    arm_a = results["arm_a"]
    arm_c = results["arm_c"]
    
    print(f"\n[Arm A: Baseline OPA (θ≥1)]")
    print(f"   거래: {arm_a['total']}건")
    print(f"   승률: {arm_a['winrate']:.1f}%")
    print(f"   PnL: {arm_a['pnl']:.1f}pt")
    print(f"   Fast Collapse: {arm_a['fast_collapse']}건")
    
    print(f"\n[Arm C: 섹터 동조 가중 OPA]")
    print(f"   거래: {arm_c['total']}건")
    print(f"   승률: {arm_c['winrate']:.1f}%")
    print(f"   PnL: {arm_c['pnl']:.1f}pt")
    print(f"   Fast Collapse: {arm_c['fast_collapse']}건")
    print(f"   앞당겨진 진입: {arm_c['accelerated']}건")
    print(f"   앞당겨진 TP/SL: {arm_c['accelerated_tp']}/{arm_c['accelerated_sl']}")
    
    # 판정
    print("\n" + "=" * 70)
    print("🎯 최종 판정")
    print("=" * 70)
    
    winrate_ok = arm_c['winrate'] >= arm_a['winrate'] - 2
    pnl_ok = arm_c['pnl'] >= arm_a['pnl'] * 0.95
    fc_rate_a = arm_a['fast_collapse'] / arm_a['total'] * 100 if arm_a['total'] > 0 else 0
    fc_rate_c = arm_c['fast_collapse'] / arm_c['total'] * 100 if arm_c['total'] > 0 else 0
    risk_ok = fc_rate_c <= fc_rate_a * 1.1
    acceleration_ok = arm_c['accelerated_tp'] > 0
    
    print(f"\n| 지표 | Arm A | Arm C | 판정 |")
    print(f"|------|-------|-------|------|")
    print(f"| 거래 수 | {arm_a['total']} | {arm_c['total']} | - |")
    print(f"| 승률 | {arm_a['winrate']:.1f}% | {arm_c['winrate']:.1f}% | {'✅' if winrate_ok else '❌'} |")
    print(f"| PnL | {arm_a['pnl']:.0f}pt | {arm_c['pnl']:.0f}pt | {'✅' if pnl_ok else '❌'} |")
    print(f"| Fast Collapse | {fc_rate_a:.1f}% | {fc_rate_c:.1f}% | {'✅' if risk_ok else '❌'} |")
    
    # Case 판정
    all_pass = winrate_ok and pnl_ok and risk_ok
    
    if all_pass and acceleration_ok:
        case = "🟢 Case 1: 성공"
        conclusion = "초동 알파는 OPA 인증 가속기로 작동"
    elif all_pass:
        case = "🟡 Case 2: 중립"
        conclusion = "섹터 정보는 무해하지만 불필요"
    else:
        case = "🔴 Case 3: 실패"
        conclusion = "초동/섹터 정보는 실행에 독"
    
    print(f"\n{case}")
    print(f"결론: {conclusion}")
    
    # 앞당겨진 진입 상세
    if arm_c['accelerated'] > 0:
        acc_winrate = arm_c['accelerated_tp'] / (arm_c['accelerated_tp'] + arm_c['accelerated_sl']) * 100 if (arm_c['accelerated_tp'] + arm_c['accelerated_sl']) > 0 else 0
        print(f"\n📈 앞당겨진 진입 상세:")
        print(f"   {arm_c['accelerated']}건 중 TP {arm_c['accelerated_tp']}건 (승률 {acc_winrate:.1f}%)")
        
        if acc_winrate >= 70:
            print(f"   → ✅ 앞당겨도 승률 유지!")
        else:
            print(f"   → ⚠️ 앞당기면 승률 하락")
    
    # 결과 저장
    all_results = {
        "early_stats": early_stats,
        "arm_a": arm_a,
        "arm_c": arm_c,
        "judgment": {
            "winrate_ok": winrate_ok,
            "pnl_ok": pnl_ok,
            "risk_ok": risk_ok,
            "case": case,
            "conclusion": conclusion,
        }
    }
    
    with open('v7-grammar-system/experiments/alpha_sensor_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print("\n결과 저장: alpha_sensor_results.json")
    
    return all_results


if __name__ == "__main__":
    os.chdir('/home/runner/workspace')
    main()
