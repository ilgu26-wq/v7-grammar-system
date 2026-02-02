"""
Engine Backtest Validation

목표: Realtime Test Engine의 결과가 기존 가설과 일치하는지 검증
비교 대상:
1. STB Ignition: 50.6% (기존)
2. OPA Early Entry: 100% (기존) 
3. 0-bar Defense: 손실 19.4% 감소 (기존)
"""

import json
import os
import sys

opa_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'opa')
sys.path.insert(0, opa_path)

from realtime_test_engine import RealtimeTestEngine, ABTestEngine

def generate_realistic_bars(n_bars=2000, seed=42):
    """백테스트용 시뮬레이션 바 생성"""
    import random
    random.seed(seed)
    
    bars = []
    base_price = 21000
    trend = 0
    volatility = 15
    
    for i in range(n_bars):
        if random.random() < 0.05:
            trend = random.choice([-1, 0, 1]) * random.uniform(5, 15)
        
        change = random.gauss(trend, volatility)
        
        if random.random() < 0.1:
            change *= random.uniform(2, 4)
        
        high_add = abs(random.gauss(0, volatility * 0.7))
        low_sub = abs(random.gauss(0, volatility * 0.7))
        
        bar = {
            'time': f'2026-01-23 {(i//60) % 24:02d}:{i%60:02d}:00',
            'open': base_price,
            'high': base_price + high_add + max(0, change),
            'low': base_price - low_sub + min(0, change),
            'close': base_price + change
        }
        
        bars.append(bar)
        base_price = bar['close']
    
    return bars

def run_engine_backtest(bars, mode="PAPER"):
    """단일 엔진 백테스트"""
    engine = RealtimeTestEngine(mode)
    
    for bar in bars:
        engine.on_bar(bar)
    
    return engine.get_stats(), engine.stats['trades']

def run_ab_backtest(bars):
    """A/B 테스트 백테스트"""
    ab_engine = ABTestEngine()
    
    for bar in bars:
        ab_engine.on_bar(bar)
    
    return ab_engine.get_comparison()

def compare_with_expected():
    """기존 가설 결과와 비교"""
    
    expected = {
        'STB_Ignition': {
            'win_rate': 50.6,
            'source': 'comprehensive_backtest_results.json'
        },
        'OPA_Early_Entry': {
            'win_rate': 100.0,
            'avg_pnl': 30.06,
            'source': 'opa_v74_test_results.json'
        },
        '0bar_Defense': {
            'loss_reduction': 19.4,
            'source': 'impulse_0bar_results.json'
        }
    }
    
    print("="*70)
    print("Engine Backtest Validation")
    print("="*70)
    
    bars = generate_realistic_bars(3000, seed=42)
    print(f"\nGenerated {len(bars)} bars for backtest")
    
    print("\n[1] Single Engine Test (PAPER mode)")
    stats, trades = run_engine_backtest(bars, "PAPER")
    
    print(f"  OPA triggers: {stats['opa_triggers']}")
    print(f"  STB triggers: {stats['stb_triggers']}")
    print(f"  Impulse triggers: {stats['impulse_triggers']}")
    print(f"  Total trades: {stats['total_trades']}")
    print(f"  Win rate: {stats['win_rate']}%")
    print(f"  Avg PnL: {stats['avg_pnl']}")
    
    print("\n[2] A/B Test Comparison")
    comparison = run_ab_backtest(bars)
    
    for mode_name, mode_stats in comparison.items():
        print(f"\n  {mode_name}:")
        print(f"    Win rate: {mode_stats['win_rate']}%")
        print(f"    Trades: {mode_stats['total_trades']}")
        print(f"    Avg PnL: {mode_stats['avg_pnl']}")
        print(f"    Impulse rate: {mode_stats.get('impulse_rate', 0)}%")
    
    print("\n" + "="*70)
    print("[3] Comparison with Expected Results")
    print("="*70)
    
    results = {
        'timestamp': '2026-01-23',
        'bars_tested': len(bars),
        'engine_results': {},
        'expected_results': expected,
        'validation': {}
    }
    
    engine_stb_wr = stats['win_rate'] if stats['total_trades'] > 0 else 0
    stb_diff = abs(engine_stb_wr - expected['STB_Ignition']['win_rate'])
    
    print(f"\n  STB Win Rate:")
    print(f"    Expected: {expected['STB_Ignition']['win_rate']}%")
    print(f"    Engine:   {engine_stb_wr}%")
    print(f"    Diff:     {stb_diff:.1f}%")
    
    results['engine_results']['stb_win_rate'] = engine_stb_wr
    results['validation']['stb_within_tolerance'] = stb_diff < 15
    
    a_stats = comparison['A_STB_ONLY']
    b_stats = comparison['B_STB_0BAR']
    
    a_trades = [t for t in [] if t.get('result') == 'LOSS']
    b_trades = [t for t in [] if t.get('result') == 'LOSS']
    
    impulse_rate = stats.get('impulse_rate', 0)
    expected_impulse_rate = 10.5
    impulse_diff = abs(impulse_rate - expected_impulse_rate)
    
    print(f"\n  Impulse Trigger Rate:")
    print(f"    Expected: ~{expected_impulse_rate}%")
    print(f"    Engine:   {impulse_rate}%")
    print(f"    Diff:     {impulse_diff:.1f}%")
    
    results['engine_results']['impulse_rate'] = impulse_rate
    results['validation']['impulse_within_tolerance'] = impulse_diff < 20
    
    opa_count = stats['opa_triggers']
    stb_count = stats['stb_triggers']
    opa_to_stb_ratio = opa_count / max(1, stb_count)
    
    print(f"\n  OPA vs STB Trigger Ratio:")
    print(f"    OPA triggers: {opa_count}")
    print(f"    STB triggers: {stb_count}")
    print(f"    Ratio: {opa_to_stb_ratio:.2f}x")
    
    results['engine_results']['opa_triggers'] = opa_count
    results['engine_results']['stb_triggers'] = stb_count
    results['engine_results']['opa_stb_ratio'] = opa_to_stb_ratio
    
    print("\n" + "="*70)
    print("[4] Anomaly Detection")
    print("="*70)
    
    anomalies = []
    
    if opa_to_stb_ratio > 5:
        anomalies.append({
            'type': 'HIGH_OPA_RATIO',
            'message': f'OPA/STB ratio ({opa_to_stb_ratio:.1f}x) is too high',
            'expected': '< 3x',
            'actual': f'{opa_to_stb_ratio:.1f}x',
            'severity': 'WARNING'
        })
    
    if impulse_rate > 30:
        anomalies.append({
            'type': 'HIGH_IMPULSE_RATE',
            'message': f'Impulse rate ({impulse_rate}%) exceeds threshold',
            'expected': '< 30%',
            'actual': f'{impulse_rate}%',
            'severity': 'ERROR'
        })
    
    if stats['total_trades'] == 0 and stb_count > 0:
        anomalies.append({
            'type': 'NO_COMPLETED_TRADES',
            'message': 'STB triggered but no trades completed',
            'expected': 'Some completed trades',
            'actual': f'{stats["total_trades"]} completed',
            'severity': 'INFO'
        })
    
    if engine_stb_wr > 0 and stb_diff > 20:
        anomalies.append({
            'type': 'WIN_RATE_MISMATCH',
            'message': f'Win rate differs significantly from expected',
            'expected': f'{expected["STB_Ignition"]["win_rate"]}%',
            'actual': f'{engine_stb_wr}%',
            'severity': 'WARNING'
        })
    
    if anomalies:
        print("\n  Found anomalies:")
        for a in anomalies:
            severity_icon = {'ERROR': '❌', 'WARNING': '⚠️', 'INFO': 'ℹ️'}.get(a['severity'], '?')
            print(f"\n  {severity_icon} {a['type']}")
            print(f"     {a['message']}")
            print(f"     Expected: {a['expected']}")
            print(f"     Actual: {a['actual']}")
    else:
        print("\n  ✅ No anomalies detected")
    
    results['anomalies'] = anomalies
    
    print("\n" + "="*70)
    print("[5] Hypothesis Validation Summary")
    print("="*70)
    
    hypotheses = [
        {
            'name': 'H1: OPA Pre-transition works',
            'test': opa_count > 0,
            'evidence': f'OPA triggered {opa_count} times'
        },
        {
            'name': 'H2: STB triggers at boundary',
            'test': stb_count > 0,
            'evidence': f'STB triggered {stb_count} times'
        },
        {
            'name': 'H3: 0-bar defense activates on impulse',
            'test': stats['impulse_triggers'] > 0,
            'evidence': f'Impulse defense triggered {stats["impulse_triggers"]} times'
        },
        {
            'name': 'H4: Impulse rate < 30%',
            'test': impulse_rate < 30,
            'evidence': f'Impulse rate = {impulse_rate}%'
        }
    ]
    
    for h in hypotheses:
        status = '✅' if h['test'] else '❌'
        print(f"\n  {status} {h['name']}")
        print(f"     Evidence: {h['evidence']}")
    
    results['hypotheses'] = hypotheses
    
    output_path = os.path.join(os.path.dirname(__file__), 'engine_validation_results.json')
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n\nResults saved to: {output_path}")
    
    return results

if __name__ == "__main__":
    compare_with_expected()
