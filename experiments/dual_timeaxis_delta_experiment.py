"""
Dual-Time-Axis Delta Experiment

RQ: Δ는
(A) 진입 판단에서 쓸 수 없는 잡음인가?
(B) 특정 시간축에서는 합리적인 정보인가?

실험 설계:
- B1: Entry 판단에서 Δ 사용 (과거 실패 재현)
- B2: Pre-transition (OPA 시간축)에서 Δ 사용 (가설 검증)
- B3: Post-entry에서 Δ 사용 (COMMIT-025 재확인)

성공 기준:
- B1 실패 + B2 성공 → 시간축 분리 정당화
- B1 실패 + B2 실패 → Δ 완전 폐기
- B1 성공 → 아카이브 착시 아님 (재검토 필요)
"""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

def load_nq_data():
    data_files = [
        'nq_1min_data.json',
        '../nq_1min_data.json',
        '../../nq_1min_data.json'
    ]
    for f in data_files:
        if os.path.exists(f):
            with open(f, 'r') as file:
                return json.load(file)
    return None

def calculate_delta(bar):
    high = bar.get('high', 0)
    low = bar.get('low', 0)
    close = bar.get('close', 0)
    
    if high == low:
        return 1.0
    
    buyer = close - low
    seller = high - close
    
    if seller == 0:
        return 10.0
    return buyer / seller

def calculate_channel_pct(bars, idx, lookback=20):
    if idx < lookback:
        return 50.0
    
    window = bars[idx-lookback:idx]
    highs = [b['high'] for b in window]
    lows = [b['low'] for b in window]
    
    highest = max(highs)
    lowest = min(lows)
    
    if highest == lowest:
        return 50.0
    
    close = bars[idx]['close']
    return ((close - lowest) / (highest - lowest)) * 100

def detect_stb_short(bars, idx):
    if idx < 5:
        return False
    
    delta = calculate_delta(bars[idx])
    channel = calculate_channel_pct(bars, idx)
    
    return delta > 1.5 and channel > 80

def detect_stb_long(bars, idx):
    if idx < 5:
        return False
    
    delta = calculate_delta(bars[idx])
    channel = calculate_channel_pct(bars, idx)
    
    return delta < 0.7 and channel < 20

def detect_pre_transition(bars, idx, lookback=5):
    """OPA 시간축: 전환 직전 감지"""
    if idx < lookback + 5:
        return None
    
    deltas = [calculate_delta(bars[i]) for i in range(idx-lookback, idx)]
    avg_delta = sum(deltas) / len(deltas)
    current_delta = calculate_delta(bars[idx])
    
    delta_change = current_delta - avg_delta
    
    if delta_change > 0.5 and avg_delta < 1.0:
        return "TRANSITION_TO_BUYER"
    elif delta_change < -0.5 and avg_delta > 1.0:
        return "TRANSITION_TO_SELLER"
    
    return None

def evaluate_trade(bars, idx, direction, tp=20, sl=15, max_bars=30):
    """진입 후 결과 평가"""
    if idx + max_bars >= len(bars):
        return None, 0, 0
    
    entry_price = bars[idx]['close']
    
    for i in range(1, min(max_bars, len(bars) - idx)):
        bar = bars[idx + i]
        
        if direction == "SHORT":
            pnl = entry_price - bar['low']
            adverse = bar['high'] - entry_price
            
            if pnl >= tp:
                return "WIN", pnl, i
            if adverse >= sl:
                return "LOSS", -adverse, i
        else:
            pnl = bar['high'] - entry_price
            adverse = entry_price - bar['low']
            
            if pnl >= tp:
                return "WIN", pnl, i
            if adverse >= sl:
                return "LOSS", -adverse, i
    
    final_price = bars[idx + max_bars - 1]['close']
    if direction == "SHORT":
        return "TIMEOUT", entry_price - final_price, max_bars
    else:
        return "TIMEOUT", final_price - entry_price, max_bars

def run_experiment_b1_entry_delta(bars):
    """B1: Δ를 Entry 판단에 직접 사용 (과거 실패 패턴)"""
    results = []
    
    for idx in range(100, len(bars) - 50):
        delta = calculate_delta(bars[idx])
        
        if delta > 2.0:
            direction = "SHORT"
        elif delta < 0.5:
            direction = "LONG"
        else:
            continue
        
        result, pnl, duration = evaluate_trade(bars, idx, direction)
        if result:
            results.append({
                'idx': idx,
                'delta': delta,
                'direction': direction,
                'result': result,
                'pnl': pnl
            })
    
    if not results:
        return {'win_rate': 0, 'count': 0, 'avg_pnl': 0}
    
    wins = sum(1 for r in results if r['result'] == 'WIN')
    avg_pnl = sum(r['pnl'] for r in results) / len(results)
    
    return {
        'win_rate': round(wins / len(results) * 100, 1),
        'count': len(results),
        'avg_pnl': round(avg_pnl, 2),
        'sample': results[:5]
    }

def run_experiment_b2_pretransition_delta(bars):
    """B2: Δ를 OPA 시간축 (Pre-transition)에서 사용"""
    results = []
    
    for idx in range(100, len(bars) - 50):
        transition = detect_pre_transition(bars, idx)
        
        if transition == "TRANSITION_TO_SELLER":
            direction = "SHORT"
        elif transition == "TRANSITION_TO_BUYER":
            direction = "LONG"
        else:
            continue
        
        result, pnl, duration = evaluate_trade(bars, idx, direction)
        if result:
            results.append({
                'idx': idx,
                'transition': transition,
                'direction': direction,
                'result': result,
                'pnl': pnl
            })
    
    if not results:
        return {'win_rate': 0, 'count': 0, 'avg_pnl': 0}
    
    wins = sum(1 for r in results if r['result'] == 'WIN')
    avg_pnl = sum(r['pnl'] for r in results) / len(results)
    
    return {
        'win_rate': round(wins / len(results) * 100, 1),
        'count': len(results),
        'avg_pnl': round(avg_pnl, 2),
        'sample': results[:5]
    }

def run_experiment_b3_postentry_delta(bars):
    """B3: Δ를 Post-entry (0-bar 방어)에서 사용"""
    results_normal = []
    results_defended = []
    
    for idx in range(100, len(bars) - 50):
        if detect_stb_short(bars, idx):
            direction = "SHORT"
        elif detect_stb_long(bars, idx):
            direction = "LONG"
        else:
            continue
        
        delta = calculate_delta(bars[idx])
        is_extreme = delta > 3.0 or delta < 0.33
        
        result_normal, pnl_normal, _ = evaluate_trade(bars, idx, direction, tp=20, sl=15)
        
        if is_extreme:
            result_defended, pnl_defended, _ = evaluate_trade(bars, idx, direction, tp=10, sl=8)
        else:
            result_defended, pnl_defended, _ = evaluate_trade(bars, idx, direction, tp=20, sl=15)
        
        if result_normal:
            results_normal.append({'result': result_normal, 'pnl': pnl_normal})
        if result_defended:
            results_defended.append({'result': result_defended, 'pnl': pnl_defended, 'extreme': is_extreme})
    
    def summarize(results):
        if not results:
            return {'win_rate': 0, 'count': 0, 'avg_pnl': 0}
        wins = sum(1 for r in results if r['result'] == 'WIN')
        avg_pnl = sum(r['pnl'] for r in results) / len(results)
        return {
            'win_rate': round(wins / len(results) * 100, 1),
            'count': len(results),
            'avg_pnl': round(avg_pnl, 2)
        }
    
    return {
        'normal': summarize(results_normal),
        'defended': summarize(results_defended),
        'extreme_count': sum(1 for r in results_defended if r.get('extreme', False))
    }

def run_experiment_archive_delta_reproduction(bars):
    """아카이브 델타 승률 재현: 동일 조건, 다른 시간축"""
    
    results_entry = []
    results_confirmation = []
    
    for idx in range(100, len(bars) - 50):
        delta = calculate_delta(bars[idx])
        channel = calculate_channel_pct(bars, idx)
        
        if delta > 1.5 and channel > 80:
            direction = "SHORT"
            
            result_entry, pnl_entry, _ = evaluate_trade(bars, idx, direction)
            if result_entry:
                results_entry.append({'result': result_entry, 'pnl': pnl_entry})
            
            confirmed = False
            for j in range(1, 6):
                if idx + j < len(bars):
                    future_delta = calculate_delta(bars[idx + j])
                    if future_delta < delta:
                        confirmed = True
                        result_conf, pnl_conf, _ = evaluate_trade(bars, idx + j, direction)
                        if result_conf:
                            results_confirmation.append({'result': result_conf, 'pnl': pnl_conf})
                        break
    
    def summarize(results):
        if not results:
            return {'win_rate': 0, 'count': 0, 'avg_pnl': 0}
        wins = sum(1 for r in results if r['result'] == 'WIN')
        avg_pnl = sum(r['pnl'] for r in results) / len(results)
        return {
            'win_rate': round(wins / len(results) * 100, 1),
            'count': len(results),
            'avg_pnl': round(avg_pnl, 2)
        }
    
    return {
        'immediate_entry': summarize(results_entry),
        'confirmed_entry': summarize(results_confirmation),
        'confirmation_effect': round(
            summarize(results_confirmation)['win_rate'] - summarize(results_entry)['win_rate'], 1
        ) if results_confirmation else 0
    }

def run_all_experiments():
    bars = load_nq_data()
    if not bars:
        return {"error": "No data found"}
    
    print(f"Running Dual-Time-Axis Delta Experiment on {len(bars)} bars...")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'total_bars': len(bars),
        'experiments': {}
    }
    
    print("\n[B1] Entry Delta (과거 실패 패턴)...")
    results['experiments']['B1_entry_delta'] = run_experiment_b1_entry_delta(bars)
    print(f"  → Win Rate: {results['experiments']['B1_entry_delta']['win_rate']}%")
    
    print("\n[B2] Pre-transition Delta (OPA 시간축)...")
    results['experiments']['B2_pretransition_delta'] = run_experiment_b2_pretransition_delta(bars)
    print(f"  → Win Rate: {results['experiments']['B2_pretransition_delta']['win_rate']}%")
    
    print("\n[B3] Post-entry Delta (0-bar 방어)...")
    results['experiments']['B3_postentry_delta'] = run_experiment_b3_postentry_delta(bars)
    print(f"  → Normal: {results['experiments']['B3_postentry_delta']['normal']['win_rate']}%")
    print(f"  → Defended: {results['experiments']['B3_postentry_delta']['defended']['win_rate']}%")
    
    print("\n[Archive] Delta 승률 재현 실험...")
    results['experiments']['archive_reproduction'] = run_experiment_archive_delta_reproduction(bars)
    print(f"  → Immediate: {results['experiments']['archive_reproduction']['immediate_entry']['win_rate']}%")
    print(f"  → Confirmed: {results['experiments']['archive_reproduction']['confirmed_entry']['win_rate']}%")
    
    b1 = results['experiments']['B1_entry_delta']['win_rate']
    b2 = results['experiments']['B2_pretransition_delta']['win_rate']
    b3_normal = results['experiments']['B3_postentry_delta']['normal']['win_rate']
    b3_defended = results['experiments']['B3_postentry_delta']['defended']['win_rate']
    
    results['conclusion'] = {
        'B1_failed': b1 < 52,
        'B2_succeeded': b2 > 52,
        'B3_defense_effective': b3_defended >= b3_normal,
        'timeaxis_separation_valid': (b1 < 52 and b2 > 52),
        'delta_completely_useless': (b1 < 52 and b2 < 52),
        'archive_was_illusion': results['experiments']['archive_reproduction']['confirmation_effect'] > 10
    }
    
    print("\n" + "="*60)
    print("CONCLUSION:")
    print(f"  B1 (Entry Delta) Failed: {results['conclusion']['B1_failed']}")
    print(f"  B2 (Pre-transition) Succeeded: {results['conclusion']['B2_succeeded']}")
    print(f"  B3 (Defense) Effective: {results['conclusion']['B3_defense_effective']}")
    print(f"  Time-axis Separation Valid: {results['conclusion']['timeaxis_separation_valid']}")
    print(f"  Archive was Illusion: {results['conclusion']['archive_was_illusion']}")
    print("="*60)
    
    output_path = os.path.join(os.path.dirname(__file__), 'dual_timeaxis_results.json')
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return results

if __name__ == "__main__":
    run_all_experiments()
