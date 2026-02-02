"""
V7 Shadow Mode Backtest
실제 차트 데이터로 V7 엔진 검증

목표:
1. 상태별 분포 확인 (WAIT/OBSERVE/ENTER)
2. 상태→수익 분석 (MFE/MAE/Forward Return)
3. "ENTER > OBSERVE" 가설 검증
"""

import json
import sys
from datetime import datetime

sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')

from shadow_mode import ShadowModeAdapter


def load_candle_history(filepath: str = '/home/runner/workspace/.candle_history.json'):
    """Load candle history from JSON file"""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    candles = []
    for c in data:
        candle = {
            'time': c.get('time', ''),
            'open': float(c.get('open', 0)),
            'high': float(c.get('high', 0)),
            'low': float(c.get('low', 0)),
            'close': float(c.get('close', 0)),
            'volume': float(c.get('volume', 0))
        }
        candles.append(candle)
    
    return candles


def run_backtest(candles: list, verbose: bool = False):
    """Run V7 Shadow Mode backtest"""
    
    print("=" * 70)
    print("V7 SHADOW MODE BACKTEST")
    print("=" * 70)
    print(f"Total candles: {len(candles)}")
    print()
    
    shadow = ShadowModeAdapter(encoder_name=None)
    
    state_transitions = []
    prev_action = None
    
    for i, candle in enumerate(candles):
        try:
            result = shadow.process(candle)
            action = result['engine']['action'].get('action', 'WAIT')
            
            if action != prev_action:
                state_transitions.append({
                    'bar': i,
                    'from': prev_action,
                    'to': action,
                    'price': candle['close']
                })
                prev_action = action
            
            if verbose and i % 50 == 0:
                print(f"Bar {i}: {action} | DC={result['engine']['state'].get('dc_hat', 0):.2f} | "
                      f"τ={result['engine']['state'].get('tau_hat', 0)}")
                
        except Exception as e:
            if verbose:
                print(f"Bar {i}: ERROR - {e}")
    
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)
    
    summary = shadow.get_summary()
    
    print(f"\n📊 Action Distribution:")
    print(f"  WAIT:    {summary['action_distribution']['WAIT']}")
    print(f"  OBSERVE: {summary['action_distribution']['OBSERVE']}")
    print(f"  ENTER:   {summary['action_distribution']['ENTER']}")
    
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
    
    print(f"\n🔄 State Transitions: {len(state_transitions)}")
    if state_transitions:
        print("  Last 10 transitions:")
        for t in state_transitions[-10:]:
            print(f"    Bar {t['bar']}: {t['from']} → {t['to']} @ {t['price']:.2f}")
    
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
    
    filepath = shadow.save_results("/tmp/v7_backtest_results.json")
    print(f"\nFull results saved to: {filepath}")
    
    profit_report = shadow.get_profit_report()
    profit_filepath = "/tmp/v7_profit_analysis.json"
    with open(profit_filepath, 'w') as f:
        json.dump(profit_report, f, indent=2, default=str)
    print(f"Profit analysis saved to: {profit_filepath}")
    
    return {
        'summary': summary,
        'opa': opa_summary,
        'profit': profit_report,
        'transitions': state_transitions
    }


def main():
    """Main entry point"""
    print("Loading candle history...")
    candles = load_candle_history()
    print(f"Loaded {len(candles)} candles")
    
    if len(candles) < 50:
        print("Not enough candles for meaningful backtest (need at least 50)")
        return
    
    results = run_backtest(candles, verbose=True)
    
    print("\n" + "=" * 70)
    print("HYPOTHESIS VERDICT")
    print("=" * 70)
    h = results['profit'].get('hypothesis_test', {})
    print(f"Q: {h.get('question', 'N/A')}")
    print(f"Verdict: {h.get('verdict', 'N/A')}")
    print(f"Conclusion: {h.get('conclusion', 'N/A')}")


if __name__ == "__main__":
    main()
