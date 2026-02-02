"""
반증 실험 A/B/C/D
목표: 핵심 가설 H1/H2/H3을 깨뜨릴 수 있으면 깨뜨리고, 안 깨지면 살아남게 한다
"""

import os
import sys
import csv
import json
import random
from datetime import datetime
from collections import defaultdict

DATA_PATH = "attached_assets/chart_data_new/latest_chart.csv"


def load_candles():
    """캔들 데이터 로드"""
    candles = []
    with open(DATA_PATH, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candles.append({
                'time': row['time'],
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close'])
            })
    return candles


def calc_delta(bar):
    """delta = (close - low) / (high - close)"""
    h, l, c = bar['high'], bar['low'], bar['close']
    if h - c == 0:
        return 100.0
    return min((c - l) / (h - c), 100.0)


def detect_opa_signals(candles, threshold=0.5):
    """OPA 신호 감지 + 상세 정보 포함"""
    signals = []
    delta_history = []
    
    for i, bar in enumerate(candles):
        delta = calc_delta(bar)
        delta_history.append(delta)
        
        if len(delta_history) < 5:
            continue
        
        recent = delta_history[-5:]
        avg_delta = sum(recent) / len(recent)
        current_delta = recent[-1]
        delta_change = current_delta - avg_delta
        
        direction = None
        if delta_change < -threshold and avg_delta > 1.0:
            direction = 'SHORT'
        elif delta_change > threshold and avg_delta < 1.0:
            direction = 'LONG'
        
        if direction:
            signals.append({
                'idx': i,
                'direction': direction,
                'delta_change': delta_change,
                'avg_delta': avg_delta,
                'current_delta': current_delta
            })
    
    return signals


def experiment_A_survival(candles, signals, N_values=[10, 20, 40]):
    """
    실험 A: OPA 전이 생존성
    - Survival: N bars 동안 반대 신호 없이 유지
    - Invalidation: N bars 이내 반대 전이 발생
    """
    print("\n" + "="*60)
    print("실험 A: OPA 전이 생존성")
    print("="*60)
    
    results = {}
    
    for N in N_values:
        survival_count = 0
        invalidation_count = 0
        time_to_invalidation = []
        
        for sig in signals:
            idx = sig['idx']
            direction = sig['direction']
            
            survived = True
            for offset in range(1, N + 1):
                if idx + offset >= len(candles):
                    break
                
                future_signals = [s for s in signals if s['idx'] == idx + offset]
                for fs in future_signals:
                    if fs['direction'] != direction:
                        survived = False
                        time_to_invalidation.append(offset)
                        break
                if not survived:
                    break
            
            if survived:
                survival_count += 1
            else:
                invalidation_count += 1
        
        total = survival_count + invalidation_count
        survival_rate = survival_count / total * 100 if total else 0
        invalidation_rate = invalidation_count / total * 100 if total else 0
        avg_tti = sum(time_to_invalidation) / len(time_to_invalidation) if time_to_invalidation else 0
        
        results[f"N={N}"] = {
            "survival_count": survival_count,
            "invalidation_count": invalidation_count,
            "survival_rate": round(survival_rate, 1),
            "invalidation_rate": round(invalidation_rate, 1),
            "avg_time_to_invalidation": round(avg_tti, 1)
        }
        
        print(f"\n[N={N}]")
        print(f"  Survival: {survival_count} ({survival_rate:.1f}%)")
        print(f"  Invalidation: {invalidation_count} ({invalidation_rate:.1f}%)")
        print(f"  Avg Time to Invalidation: {avg_tti:.1f} bars")
    
    return results


def experiment_B_physics_separation(candles, signals, N=20):
    """
    실험 B: 이벤트 물리량 분리
    - delta_change 구간별 생존성
    - avg_delta 구간별 생존성
    """
    print("\n" + "="*60)
    print("실험 B: 이벤트 물리량 분리")
    print("="*60)
    
    dc_buckets = [(0.5, 0.7), (0.7, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, float('inf'))]
    ad_buckets = [(0, 1), (1, 2), (2, 4), (4, 8), (8, float('inf'))]
    
    dc_results = defaultdict(lambda: {"total": 0, "survival": 0})
    ad_results = defaultdict(lambda: {"total": 0, "survival": 0})
    
    for sig in signals:
        idx = sig['idx']
        direction = sig['direction']
        dc = abs(sig['delta_change'])
        ad = sig['avg_delta']
        
        survived = True
        for offset in range(1, N + 1):
            if idx + offset >= len(candles):
                break
            future_signals = [s for s in signals if s['idx'] == idx + offset]
            for fs in future_signals:
                if fs['direction'] != direction:
                    survived = False
                    break
            if not survived:
                break
        
        for low, high in dc_buckets:
            if low <= dc < high:
                label = f"{low}-{high}" if high != float('inf') else f"{low}+"
                dc_results[label]["total"] += 1
                if survived:
                    dc_results[label]["survival"] += 1
                break
        
        for low, high in ad_buckets:
            if low <= ad < high:
                label = f"{low}-{high}" if high != float('inf') else f"{low}+"
                ad_results[label]["total"] += 1
                if survived:
                    ad_results[label]["survival"] += 1
                break
    
    print(f"\n[delta_change 구간별 생존성 (N={N})]")
    print(f"{'구간':>12} | {'Total':>6} | {'Survival':>8} | {'Rate':>8}")
    print("-" * 45)
    
    dc_table = {}
    for label in ["0.5-0.7", "0.7-1.0", "1.0-1.5", "1.5-2.0", "2.0+"]:
        data = dc_results.get(label, {"total": 0, "survival": 0})
        rate = data["survival"] / data["total"] * 100 if data["total"] else 0
        print(f"{label:>12} | {data['total']:>6} | {data['survival']:>8} | {rate:>7.1f}%")
        dc_table[label] = {"total": data["total"], "survival": data["survival"], "rate": round(rate, 1)}
    
    print(f"\n[avg_delta 구간별 생존성 (N={N})]")
    print(f"{'구간':>12} | {'Total':>6} | {'Survival':>8} | {'Rate':>8}")
    print("-" * 45)
    
    ad_table = {}
    for label in ["0-1", "1-2", "2-4", "4-8", "8+"]:
        data = ad_results.get(label, {"total": 0, "survival": 0})
        rate = data["survival"] / data["total"] * 100 if data["total"] else 0
        print(f"{label:>12} | {data['total']:>6} | {data['survival']:>8} | {rate:>7.1f}%")
        ad_table[label] = {"total": data["total"], "survival": data["survival"], "rate": round(rate, 1)}
    
    return {"delta_change": dc_table, "avg_delta": ad_table}


def experiment_C_stb_shuffle(candles, signals, n_shuffles=100, N=20):
    """
    실험 C: STB 점화 센서 검증 (셔플 테스트)
    - 진짜 신호 vs 랜덤 셔플 신호 비교
    """
    print("\n" + "="*60)
    print("실험 C: STB/OPA 셔플 테스트")
    print("="*60)
    
    def calc_survival_rate(sigs, all_sigs):
        survival = 0
        total = len(sigs)
        for sig in sigs:
            idx = sig['idx']
            direction = sig['direction']
            survived = True
            for offset in range(1, N + 1):
                if idx + offset >= len(candles):
                    break
                future = [s for s in all_sigs if s['idx'] == idx + offset and s['direction'] != direction]
                if future:
                    survived = False
                    break
            if survived:
                survival += 1
        return survival / total * 100 if total else 0
    
    real_rate = calc_survival_rate(signals, signals)
    print(f"\n[진짜 OPA 신호]")
    print(f"  N = {len(signals)}")
    print(f"  Survival Rate (N={N}): {real_rate:.1f}%")
    
    shuffle_rates = []
    for _ in range(n_shuffles):
        shuffled = []
        indices = list(range(5, len(candles)))
        random.shuffle(indices)
        sample_indices = indices[:len(signals)]
        
        for i, idx in enumerate(sample_indices):
            shuffled.append({
                'idx': idx,
                'direction': signals[i % len(signals)]['direction'],
                'delta_change': signals[i % len(signals)]['delta_change'],
                'avg_delta': signals[i % len(signals)]['avg_delta']
            })
        
        rate = calc_survival_rate(shuffled, shuffled)
        shuffle_rates.append(rate)
    
    avg_shuffle = sum(shuffle_rates) / len(shuffle_rates)
    min_shuffle = min(shuffle_rates)
    max_shuffle = max(shuffle_rates)
    
    print(f"\n[랜덤 셔플 ({n_shuffles}회)]")
    print(f"  Avg Survival Rate: {avg_shuffle:.1f}%")
    print(f"  Range: {min_shuffle:.1f}% - {max_shuffle:.1f}%")
    print(f"\n[비교]")
    print(f"  진짜 - 랜덤평균 = {real_rate - avg_shuffle:.1f}%p")
    
    verdict = "PASS" if real_rate > max_shuffle else "FAIL"
    print(f"  판정: {verdict} (진짜 > 랜덤최대값)")
    
    return {
        "real_rate": round(real_rate, 1),
        "shuffle_avg": round(avg_shuffle, 1),
        "shuffle_min": round(min_shuffle, 1),
        "shuffle_max": round(max_shuffle, 1),
        "diff": round(real_rate - avg_shuffle, 1),
        "verdict": verdict
    }


def experiment_D_filter_funnel(candles, threshold=0.5):
    """
    실험 D: 필터 체인 감사
    - 3306 → 484 감소 과정 분석
    """
    print("\n" + "="*60)
    print("실험 D: 필터 체인 감사 (Funnel)")
    print("="*60)
    
    delta_history = []
    funnel = {
        "total_bars": 0,
        "pass_history_5": 0,
        "pass_delta_mag": 0,
        "pass_avg_dir": 0,
        "final_signals": 0
    }
    
    direction_counts = {"SHORT": 0, "LONG": 0}
    
    for i, bar in enumerate(candles):
        funnel["total_bars"] += 1
        
        delta = calc_delta(bar)
        delta_history.append(delta)
        
        if len(delta_history) < 5:
            continue
        funnel["pass_history_5"] += 1
        
        recent = delta_history[-5:]
        avg_delta = sum(recent) / len(recent)
        current_delta = recent[-1]
        delta_change = current_delta - avg_delta
        
        if abs(delta_change) < threshold:
            continue
        funnel["pass_delta_mag"] += 1
        
        if delta_change < -threshold and avg_delta > 1.0:
            funnel["pass_avg_dir"] += 1
            funnel["final_signals"] += 1
            direction_counts["SHORT"] += 1
        elif delta_change > threshold and avg_delta < 1.0:
            funnel["pass_avg_dir"] += 1
            funnel["final_signals"] += 1
            direction_counts["LONG"] += 1
    
    print(f"\n[Funnel 분석]")
    print(f"  Total bars:        {funnel['total_bars']:>6}")
    print(f"  Pass history>=5:   {funnel['pass_history_5']:>6} ({funnel['pass_history_5']/funnel['total_bars']*100:.1f}%)")
    print(f"  Pass |Δchange|≥{threshold}: {funnel['pass_delta_mag']:>6} ({funnel['pass_delta_mag']/funnel['total_bars']*100:.1f}%)")
    print(f"  Pass avg_dir:      {funnel['pass_avg_dir']:>6} ({funnel['pass_avg_dir']/funnel['total_bars']*100:.1f}%)")
    print(f"  Final signals:     {funnel['final_signals']:>6} ({funnel['final_signals']/funnel['total_bars']*100:.1f}%)")
    print(f"\n[방향 분포]")
    print(f"  SHORT: {direction_counts['SHORT']}")
    print(f"  LONG:  {direction_counts['LONG']}")
    
    return {
        "funnel": funnel,
        "direction_counts": direction_counts
    }


def run_all_experiments():
    """전체 실험 실행"""
    print("="*60)
    print("반증 실험 시작")
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    candles = load_candles()
    print(f"데이터 로드: {len(candles)} bars")
    
    signals = detect_opa_signals(candles, threshold=0.5)
    print(f"OPA 신호 감지: {len(signals)} signals")
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "data_bars": len(candles),
        "total_signals": len(signals)
    }
    
    results["A_survival"] = experiment_A_survival(candles, signals)
    
    results["B_physics"] = experiment_B_physics_separation(candles, signals)
    
    results["C_shuffle"] = experiment_C_stb_shuffle(candles, signals, n_shuffles=50)
    
    results["D_funnel"] = experiment_D_filter_funnel(candles)
    
    print("\n" + "="*60)
    print("전체 실험 완료")
    print("="*60)
    
    output_path = "v7-grammar-system/experiments/falsification_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n결과 저장: {output_path}")
    
    return results


if __name__ == "__main__":
    run_all_experiments()
