"""
V7 Shadow Mode Large-Scale Backtest
5428+ 레코드로 검증

데이터 소스:
- v7_signals.json (5428 records)
- force_readings.json (5428 records)
"""

import json
import sys
from datetime import datetime

sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')

from shadow_mode import ShadowModeAdapter


def load_force_readings():
    """Load force readings with mid_price"""
    filepath = '/home/runner/workspace/v7-grammar-system/experiments/force_readings.json'
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    print(f"Loaded {len(data)} records from force_readings.json")
    return data


def load_v7_signals():
    """Load v7_signals with entry_price"""
    filepath = '/home/runner/workspace/v7-grammar-system/experiments/v7_signals.json'
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    print(f"Loaded {len(data)} records from v7_signals.json")
    return data


def merge_data_sources():
    """Merge force_readings and v7_signals by timestamp"""
    force_data = load_force_readings()
    signal_data = load_v7_signals()
    
    signal_map = {s['ts']: s for s in signal_data}
    
    merged = []
    for f in force_data:
        ts = f['ts']
        s = signal_map.get(ts, {})
        
        price = f.get('mid_price', s.get('entry_price', 0))
        
        if price > 0:
            candle = {
                'time': ts,
                'open': price - 2,
                'high': price + 10,
                'low': price - 10,
                'close': price,
                'volume': 1000,
                'dc_pre': f.get('dc_pre', 0.5),
                'avg_delta': f.get('avg_delta', 0),
                'force_ratio': f.get('force_ratio_20', 1.0),
                'sps_ratio': f.get('sps_ratio_20', 0),
                'original_action': s.get('action', 'UNKNOWN'),
                'original_reason': s.get('reason', '')
            }
            merged.append(candle)
    
    print(f"Merged {len(merged)} candles")
    return merged


def run_large_backtest(candles: list, verbose: bool = False):
    """Run V7 Shadow Mode backtest on large dataset"""
    
    print("=" * 70)
    print("V7 SHADOW MODE LARGE-SCALE BACKTEST")
    print("=" * 70)
    print(f"Total candles: {len(candles)}")
    
    if candles:
        print(f"Date range: {candles[0]['time']} to {candles[-1]['time']}")
    print()
    
    shadow = ShadowModeAdapter(encoder_name=None)
    
    action_counts = {'WAIT': 0, 'OBSERVE': 0, 'ENTER': 0, 'OTHER': 0}
    state_by_original = {}
    errors = []
    
    for i, candle in enumerate(candles):
        try:
            result = shadow.process(candle)
            action = result['engine']['action'].get('action', 'WAIT')
            
            if action in action_counts:
                action_counts[action] += 1
            else:
                action_counts['OTHER'] += 1
            
            orig = candle.get('original_action', 'UNKNOWN')
            if orig not in state_by_original:
                state_by_original[orig] = {'WAIT': 0, 'OBSERVE': 0, 'ENTER': 0}
            if action in state_by_original[orig]:
                state_by_original[orig][action] += 1
            
            if verbose and i % 500 == 0:
                dc = result['engine']['state'].get('dc_hat', 0)
                tau = result['engine']['state'].get('tau_hat', 0)
                print(f"Bar {i}: {action} | DC={dc:.2f} | τ={tau}")
                
        except Exception as e:
            errors.append({'bar': i, 'error': str(e)})
            if len(errors) < 5:
                print(f"Bar {i}: ERROR - {e}")
    
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)
    
    total = len(candles)
    print(f"\n📊 Action Distribution (N={total}):")
    for action, count in action_counts.items():
        pct = count / total * 100 if total > 0 else 0
        print(f"  {action}: {count} ({pct:.1f}%)")
    
    if errors:
        print(f"\n⚠️ Errors: {len(errors)} (first 5 shown above)")
    
    summary = shadow.get_summary()
    
    print(f"\n📈 Virtual Trades:")
    print(f"  OBSERVE trades: {summary['observe_virtual_trades']['total']}")
    print(f"    - TP Small: {summary['observe_virtual_trades']['tp_small']}")
    print(f"    - TP Full:  {summary['observe_virtual_trades']['tp_full']}")
    print(f"    - SL:       {summary['observe_virtual_trades']['sl']}")
    print(f"    - Win Rate: {summary['observe_virtual_trades']['win_rate']}")
    
    print(f"\n  ENTER trades: {summary['enter_virtual_trades']['total']}")
    print(f"    - TP Small: {summary['enter_virtual_trades']['tp_small']}")
    print(f"    - TP Full:  {summary['enter_virtual_trades']['tp_full']}")
    print(f"    - SL:       {summary['enter_virtual_trades']['sl']}")
    print(f"    - Win Rate: {summary['enter_virtual_trades']['win_rate']}")
    
    print("\n" + "=" * 70)
    print("V7 STATE vs ORIGINAL ACTION CROSS-TAB")
    print("=" * 70)
    print(f"{'Original':<20} {'V7 WAIT':<12} {'V7 OBSERVE':<12} {'V7 ENTER':<12}")
    print("-" * 56)
    for orig, counts in sorted(state_by_original.items()):
        print(f"{orig:<20} {counts.get('WAIT',0):<12} {counts.get('OBSERVE',0):<12} {counts.get('ENTER',0):<12}")
    
    print("\n" + "=" * 70)
    print("OPA OVERLAY ANALYSIS")
    print("=" * 70)
    opa_summary = shadow.get_opa_summary()
    print(f"Total ENTER signals: {opa_summary['total_entries']}")
    print(f"OPA ALLOW: {opa_summary['opa_allow']}")
    print(f"OPA DENY:  {opa_summary['opa_deny']}")
    print(f"Deny Rate: {opa_summary['deny_rate']}")
    
    print("\n" + "=" * 70)
    print("STATE → PROFIT ANALYSIS")
    print("=" * 70)
    shadow.print_profit_report()
    
    filepath = shadow.save_results("/tmp/v7_large_backtest_results.json")
    print(f"\nFull results saved to: {filepath}")
    
    profit_report = shadow.get_profit_report()
    profit_filepath = "/tmp/v7_large_profit_analysis.json"
    with open(profit_filepath, 'w') as f:
        json.dump(profit_report, f, indent=2, default=str)
    print(f"Profit analysis saved to: {profit_filepath}")
    
    return {
        'summary': summary,
        'action_counts': action_counts,
        'state_by_original': state_by_original,
        'opa': opa_summary,
        'profit': profit_report,
        'errors': len(errors)
    }


def main():
    """Main entry point"""
    print("Loading and merging data sources...")
    candles = merge_data_sources()
    
    if len(candles) < 100:
        print("Not enough candles for meaningful backtest")
        return
    
    results = run_large_backtest(candles, verbose=True)
    
    print("\n" + "=" * 70)
    print("FINAL HYPOTHESIS VERDICT")
    print("=" * 70)
    h = results['profit'].get('hypothesis_test', {})
    print(f"Q: {h.get('question', 'N/A')}")
    print(f"OBSERVE Edge: {h.get('observe_edge_ratio', 'N/A')}")
    print(f"ENTER Edge:   {h.get('enter_edge_ratio', 'N/A')}")
    print(f"Verdict: {h.get('verdict', 'N/A')}")
    print(f"Conclusion: {h.get('conclusion', 'N/A')}")


if __name__ == "__main__":
    main()
