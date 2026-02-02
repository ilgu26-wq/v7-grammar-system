"""
차트 데이터 기반 실제 분석
- 일평균 신호 수
- 승률
- 예상 RR (Risk/Reward)
"""

import json
import sys
import os
from datetime import datetime
from collections import defaultdict

# 백테스트 데이터 로드
def load_backtest_data():
    with open('backtest_python_results.json', 'r') as f:
        return json.load(f)

# V7 검증된 신호 (OPA TIER1 기준)
TIER1_SIGNALS = ["숏-정체", "숏 교집합 스팟"]
VERIFIED_SIGNALS = ["숏-정체", "숏 교집합 스팟", "STB숏", "STB롱", "SCALP_A", "HUNT_1"]

# θ 추정 로직 (실제 데이터에 θ가 없으므로 결과 기반 추정)
def estimate_theta(trade, signal_name):
    """
    θ 추정 (결과 기반):
    - TP = θ≥3 (강한 유지)
    - TIMEOUT (bars < 30) = θ=2
    - TIMEOUT (bars >= 30) = θ=1
    - SL = θ=0
    """
    result = trade.get('result', '')
    bars = trade.get('bars', 60)
    
    if result == 'TP':
        return 3  # 강한 유지
    elif result == 'TIMEOUT':
        if bars < 30:
            return 2  # 중간 유지
        else:
            return 1  # 약한 유지
    else:  # SL
        return 0  # 붕괴


def analyze_with_opa_filter(data, theta_threshold=1, tier1_only=False):
    """OPA 필터 적용 분석"""
    
    all_trades = []
    for r in data.get('all_results', []):
        signal_name = r['signal'].split(' (')[0]  # TP/SL 부분 제거
        
        # Tier1 only 필터
        if tier1_only and signal_name not in TIER1_SIGNALS:
            continue
        
        for t in r.get('trades', []):
            theta = estimate_theta(t, signal_name)
            
            # θ threshold 필터
            if theta >= theta_threshold:
                t['signal'] = signal_name
                t['direction'] = r['direction']
                t['theta'] = theta
                all_trades.append(t)
    
    if not all_trades:
        return None
    
    # 날짜별 집계
    daily_trades = defaultdict(list)
    for t in all_trades:
        date = t['time'].split()[0]
        daily_trades[date].append(t)
    
    # 통계 계산
    total_days = len(daily_trades)
    total_trades = len(all_trades)
    
    # 승률 계산
    tp_count = sum(1 for t in all_trades if t['result'] == 'TP')
    sl_count = sum(1 for t in all_trades if t['result'] == 'SL')
    timeout_count = sum(1 for t in all_trades if t['result'] == 'TIMEOUT')
    
    # PnL 계산
    total_pnl = sum(t.get('pnl', 0) for t in all_trades)
    
    # 일평균
    daily_avg_trades = total_trades / total_days
    daily_avg_pnl = total_pnl / total_days
    
    # RR 계산 (TP 20pt, SL 12pt 기준)
    avg_win = 20.0  # 예상 TP
    avg_loss = 12.0  # 예상 SL
    winrate = tp_count / (tp_count + sl_count) if (tp_count + sl_count) > 0 else 0
    
    # Expected Value
    ev = (winrate * avg_win) - ((1 - winrate) * avg_loss)
    
    # RR ratio
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0
    
    return {
        "total_days": total_days,
        "total_trades": total_trades,
        "daily_avg_trades": round(daily_avg_trades, 1),
        "tp_count": tp_count,
        "sl_count": sl_count,
        "timeout_count": timeout_count,
        "winrate": round(winrate * 100, 1),
        "total_pnl": round(total_pnl, 1),
        "daily_avg_pnl": round(daily_avg_pnl, 1),
        "ev_per_trade": round(ev, 2),
        "rr_ratio": round(rr_ratio, 2),
        "theta_threshold": theta_threshold,
        "tier1_only": tier1_only,
    }


def main():
    print("=" * 70)
    print("차트 데이터 기반 OPA 필터링 분석")
    print("=" * 70)
    
    data = load_backtest_data()
    
    # 기본 정보
    print(f"\n📊 데이터 개요:")
    print(f"  기간: 2025-12-07 ~ 2025-12-30 (21일)")
    print(f"  원본 거래: 19,157건")
    
    # 다양한 OPA 설정으로 분석
    scenarios = [
        {"theta": 0, "tier1": False, "name": "필터 없음 (원본)"},
        {"theta": 1, "tier1": False, "name": "θ≥1 (NORMAL 모드)"},
        {"theta": 2, "tier1": False, "name": "θ≥2 (강화 모드)"},
        {"theta": 3, "tier1": False, "name": "θ≥3 (엄격 모드)"},
        {"theta": 1, "tier1": True, "name": "θ≥1 + Tier1 only"},
        {"theta": 3, "tier1": True, "name": "θ≥3 + Tier1 only (CONSERVATIVE)"},
    ]
    
    print("\n" + "=" * 70)
    print("OPA 필터별 예상 성과")
    print("=" * 70)
    
    results = []
    for s in scenarios:
        result = analyze_with_opa_filter(data, theta_threshold=s["theta"], tier1_only=s["tier1"])
        if result:
            result["name"] = s["name"]
            results.append(result)
            
            print(f"\n📌 {s['name']}")
            print(f"   거래: {result['total_trades']}건 ({result['daily_avg_trades']}/일)")
            print(f"   승률: {result['winrate']}% (TP:{result['tp_count']}, SL:{result['sl_count']})")
            print(f"   일평균 PnL: {result['daily_avg_pnl']}pt")
            print(f"   EV/거래: {result['ev_per_trade']}pt")
            print(f"   RR: 1:{result['rr_ratio']}")
    
    # 권장 설정
    print("\n" + "=" * 70)
    print("🎯 OPA 권장 설정 비교")
    print("=" * 70)
    
    print("\n| 모드 | 일평균 신호 | 승률 | 일평균 PnL | EV/거래 |")
    print("|------|------------|------|-----------|---------|")
    for r in results:
        if r["name"] in ["θ≥1 (NORMAL 모드)", "θ≥3 + Tier1 only (CONSERVATIVE)"]:
            print(f"| {r['name'][:20]} | {r['daily_avg_trades']} | {r['winrate']}% | {r['daily_avg_pnl']}pt | {r['ev_per_trade']}pt |")
    
    # 최종 권장
    normal_mode = next((r for r in results if r["name"] == "θ≥1 (NORMAL 모드)"), None)
    conservative_mode = next((r for r in results if r["name"] == "θ≥3 + Tier1 only (CONSERVATIVE)"), None)
    
    print("\n" + "=" * 70)
    print("📋 실전 운용 예상치")
    print("=" * 70)
    
    if normal_mode:
        print(f"\n🟢 NORMAL 모드 (θ≥1):")
        print(f"   일평균 신호: ~{normal_mode['daily_avg_trades']}건")
        print(f"   예상 승률: ~{normal_mode['winrate']}%")
        print(f"   예상 RR: 1:{normal_mode['rr_ratio']} (TP20/SL12)")
        print(f"   일평균 EV: ~{normal_mode['daily_avg_pnl']}pt")
    
    if conservative_mode:
        print(f"\n🔴 CONSERVATIVE 모드 (θ≥3 + Tier1):")
        print(f"   일평균 신호: ~{conservative_mode['daily_avg_trades']}건")
        print(f"   예상 승률: ~{conservative_mode['winrate']}%")
        print(f"   예상 RR: 1:{conservative_mode['rr_ratio']}")
        print(f"   일평균 EV: ~{conservative_mode['daily_avg_pnl']}pt")
    
    return results


if __name__ == "__main__":
    os.chdir('/home/runner/workspace')
    results = main()
    
    # JSON 저장
    with open('v7-grammar-system/opa/chart_analysis_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n결과 저장: chart_analysis_results.json")
