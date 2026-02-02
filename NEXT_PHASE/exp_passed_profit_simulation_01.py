"""
EXP-PASSED-PROFIT-SIMULATION-01: PASSED 영역 수익 시뮬레이션
============================================================
목적: "World Validity가 TRUE인 구간에서 돈을 벌 수 있는 환경인가?"

규칙:
  - ENTRY: V7 기본 조건 (Ignition 후 retouch)
  - EXIT: Fixed horizon (N bars) 또는 Fixed TP/SL
  - 비교: ALL vs ZPOC_ONLY vs PASSED

성공 기준:
  - PASSED에서 Max DD 감소
  - PASSED에서 worst loss cluster 제거
  - PASSED에서 collapse 이후 손실 감소
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_passed_profit_sim_01.json"

WEIGHTS = {
    'zpoc_alive': 2.0, 'htf_alive': -1.5, 'range_alive': 1.0,
    'depth_alive': 0.8, 'tau_alive': 0.5, 'er_alive': 0.3
}

TP_POINTS = 6.0
SL_POINTS = 4.0
HORIZON_BARS = 10

def calc_er(close_series: pd.Series, lookback: int = 10) -> pd.Series:
    result = []
    for i in range(len(close_series)):
        start = max(0, i - lookback + 1)
        window = close_series.iloc[start:i + 1]
        if len(window) < 2:
            result.append(0.5)
            continue
        price_change = abs(window.iloc[-1] - window.iloc[0])
        bar_changes = abs(window.diff().dropna()).sum()
        result.append(min(1.0, price_change / max(bar_changes, 0.01)))
    return pd.Series(result, index=close_series.index)

def calc_depth(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    rolling_high = df['high'].rolling(lookback, min_periods=1).max()
    rolling_low = df['low'].rolling(lookback, min_periods=1).min()
    return (df['close'] - rolling_low) / (rolling_high - rolling_low + 0.001)

def calc_zpoc(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    vol = df['range'].replace(0, 1)
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * vol).rolling(lookback, min_periods=1).sum() / vol.rolling(lookback, min_periods=1).sum()

def compute_action_mask(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['range'] = df['high'] - df['low']
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['zpoc'] = calc_zpoc(df)
    
    range_q25, range_q75 = df['range'].quantile(0.25), df['range'].quantile(0.75)
    er_median = df['er'].median()
    depth_median = df['depth'].median()
    
    zpoc_distance = abs(df['zpoc'] - df['close'])
    zpoc_threshold = df['range'].rolling(20, min_periods=1).mean() * 3
    df['zpoc_alive'] = (zpoc_distance < zpoc_threshold).astype(int)
    df['depth_alive'] = (abs(df['depth'] - depth_median) < 0.3).astype(int)
    df['er_alive'] = (df['er'] > er_median * 0.5).astype(int)
    df['range_alive'] = ((df['range'] >= range_q25) & (df['range'] <= range_q75 * 2)).astype(int)
    er_change = df['er'].diff(5).abs()
    df['tau_alive'] = (er_change < 0.3).astype(int)
    df['htf_alive'] = 0
    for period in [5, 15]:
        htf_er = df['er'].rolling(period, min_periods=1).mean()
        df['htf_alive'] = df['htf_alive'] | (htf_er > 0.6).astype(int)
    
    df['alive_count'] = (df['zpoc_alive'] + df['htf_alive'] + df['depth_alive'] + 
                         df['er_alive'] + df['range_alive'] + df['tau_alive'])
    
    df['ecs'] = sum(WEIGHTS[k] * df[k] for k in WEIGHTS)
    penalty = ((df['alive_count'] >= 5) & (df['htf_alive'] == 1)).astype(float) * 1.5
    df['ecs_penalized'] = df['ecs'] - penalty
    
    df['action_mask'] = 1.0
    df.loc[df['zpoc_alive'] == 0, 'action_mask'] = 0.0
    df.loc[(df['htf_alive'] == 1) & (df['alive_count'] >= 4), 'action_mask'] = 0.0
    df.loc[df['ecs_penalized'] < 1.0, 'action_mask'] = 0.0
    df.loc[(df['ecs_penalized'] >= 1.0) & (df['ecs_penalized'] < 2.0), 'action_mask'] = 0.5
    
    return df

def find_entry_signals(df: pd.DataFrame) -> List[Dict]:
    """V7 기본 ENTRY: Ignition 후 retouch"""
    signals = []
    
    for i in range(20, len(df) - HORIZON_BARS - 1):
        if df['er'].iloc[i] > 0.7 and df['er'].iloc[i-1] < 0.7:
            for j in range(1, min(15, len(df) - i - HORIZON_BARS)):
                future_idx = i + j
                ignition_price = df['close'].iloc[i]
                price_band = df['range'].iloc[i] * 2
                
                if abs(df['close'].iloc[future_idx] - ignition_price) < price_band:
                    direction = 1 if df['close'].iloc[i] > df['open'].iloc[i] else -1
                    
                    signals.append({
                        'entry_idx': future_idx,
                        'entry_price': df['close'].iloc[future_idx],
                        'direction': direction,
                        'action_mask': df['action_mask'].iloc[future_idx],
                        'zpoc_alive': df['zpoc_alive'].iloc[future_idx]
                    })
                    break
    
    return signals

def simulate_trade(df: pd.DataFrame, signal: Dict, use_tp_sl: bool = True) -> Dict:
    """단일 거래 시뮬레이션"""
    entry_idx = signal['entry_idx']
    entry_price = signal['entry_price']
    direction = signal['direction']
    
    if use_tp_sl:
        tp_price = entry_price + direction * TP_POINTS
        sl_price = entry_price - direction * SL_POINTS
        
        for i in range(1, HORIZON_BARS + 1):
            if entry_idx + i >= len(df):
                break
            
            bar = df.iloc[entry_idx + i]
            
            if direction == 1:
                if bar['high'] >= tp_price:
                    return {'pnl': TP_POINTS, 'result': 'TP', 'bars': i}
                if bar['low'] <= sl_price:
                    return {'pnl': -SL_POINTS, 'result': 'SL', 'bars': i}
            else:
                if bar['low'] <= tp_price:
                    return {'pnl': TP_POINTS, 'result': 'TP', 'bars': i}
                if bar['high'] >= sl_price:
                    return {'pnl': -SL_POINTS, 'result': 'SL', 'bars': i}
        
        exit_price = df['close'].iloc[min(entry_idx + HORIZON_BARS, len(df) - 1)]
        pnl = direction * (exit_price - entry_price)
        return {'pnl': pnl, 'result': 'TIMEOUT', 'bars': HORIZON_BARS}
    else:
        exit_price = df['close'].iloc[min(entry_idx + HORIZON_BARS, len(df) - 1)]
        pnl = direction * (exit_price - entry_price)
        return {'pnl': pnl, 'result': 'HORIZON', 'bars': HORIZON_BARS}

def calculate_metrics(trades: List[Dict]) -> Dict:
    """수익 지표 계산"""
    if not trades:
        return {'count': 0}
    
    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    
    cumulative = np.cumsum(pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdowns = peak - cumulative
    
    return {
        'count': len(trades),
        'win_rate': len(wins) / len(trades) if trades else 0,
        'avg_pnl': np.mean(pnls),
        'total_pnl': sum(pnls),
        'avg_win': np.mean(wins) if wins else 0,
        'avg_loss': np.mean(losses) if losses else 0,
        'max_dd': max(drawdowns) if len(drawdowns) > 0 else 0,
        'expectancy': np.mean(pnls),
        'worst_loss': min(pnls) if pnls else 0,
        'best_win': max(pnls) if pnls else 0,
        'consecutive_losses': max_consecutive_losses(pnls),
        'sharpe': np.mean(pnls) / np.std(pnls) if np.std(pnls) > 0 else 0
    }

def max_consecutive_losses(pnls: List[float]) -> int:
    max_streak = 0
    current = 0
    for p in pnls:
        if p < 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak

def run_simulation(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-PASSED-PROFIT-SIMULATION-01")
    print("PASSED 영역 수익 시뮬레이션")
    print("=" * 70)
    
    print("\n[1] Computing ACTION_MASK...")
    df = compute_action_mask(df)
    
    print("\n[2] Finding entry signals...")
    all_signals = find_entry_signals(df)
    print(f"  Total signals: {len(all_signals)}")
    
    groups = {
        'ALL': [s for s in all_signals],
        'ZPOC_ONLY': [s for s in all_signals if s['zpoc_alive'] == 1],
        'PASSED': [s for s in all_signals if s['action_mask'] == 1.0]
    }
    
    print(f"\n  ALL: {len(groups['ALL'])}")
    print(f"  ZPOC_ONLY: {len(groups['ZPOC_ONLY'])}")
    print(f"  PASSED: {len(groups['PASSED'])}")
    
    print("\n[3] Running simulations...")
    
    results = {}
    all_trades = {}
    
    for group_name, signals in groups.items():
        trades = []
        for signal in signals:
            trade = simulate_trade(df, signal, use_tp_sl=True)
            trade.update(signal)
            trades.append(trade)
        
        metrics = calculate_metrics(trades)
        results[group_name] = metrics
        all_trades[group_name] = trades
        
        print(f"\n  [{group_name}]")
        print(f"    Trades: {metrics['count']}")
        print(f"    Win Rate: {metrics.get('win_rate', 0):.1%}")
        print(f"    Avg PnL: {metrics.get('avg_pnl', 0):+.2f} pts")
        print(f"    Total PnL: {metrics.get('total_pnl', 0):+.2f} pts")
        print(f"    Max DD: {metrics.get('max_dd', 0):.2f} pts")
        print(f"    Worst Loss: {metrics.get('worst_loss', 0):.2f} pts")
        print(f"    Consecutive Losses: {metrics.get('consecutive_losses', 0)}")
    
    print("\n" + "=" * 70)
    print("COMPARISON ANALYSIS")
    print("=" * 70)
    
    all_m = results['ALL']
    passed_m = results['PASSED']
    
    print(f"\n[Trade Reduction]")
    print(f"  ALL → PASSED: {len(groups['ALL'])} → {len(groups['PASSED'])} ({len(groups['PASSED'])/len(groups['ALL'])*100:.1f}%)")
    
    if all_m['count'] > 0 and passed_m['count'] > 0:
        print(f"\n[Win Rate Change]")
        print(f"  ALL: {all_m['win_rate']:.1%} → PASSED: {passed_m['win_rate']:.1%} ({(passed_m['win_rate'] - all_m['win_rate'])*100:+.1f}%p)")
        
        print(f"\n[Max DD Change]")
        print(f"  ALL: {all_m['max_dd']:.2f} → PASSED: {passed_m['max_dd']:.2f} ({passed_m['max_dd'] - all_m['max_dd']:+.2f})")
        
        print(f"\n[Worst Loss Change]")
        print(f"  ALL: {all_m['worst_loss']:.2f} → PASSED: {passed_m['worst_loss']:.2f}")
        
        print(f"\n[Consecutive Losses]")
        print(f"  ALL: {all_m['consecutive_losses']} → PASSED: {passed_m['consecutive_losses']}")
    
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    
    success_criteria = []
    
    if passed_m['count'] > 0:
        if passed_m['max_dd'] < all_m['max_dd'] * 0.8:
            success_criteria.append("Max DD reduced by 20%+")
        
        if passed_m['consecutive_losses'] < all_m['consecutive_losses']:
            success_criteria.append("Consecutive losses reduced")
        
        if passed_m['win_rate'] > all_m['win_rate']:
            success_criteria.append("Win rate improved")
        
        if passed_m['avg_pnl'] > all_m['avg_pnl']:
            success_criteria.append("Avg PnL improved")
    
    if success_criteria:
        print(f"\n  SUCCESS: {len(success_criteria)} criteria met")
        for c in success_criteria:
            print(f"    ✓ {c}")
        verdict = "SUCCESS"
    else:
        print(f"\n  INCONCLUSIVE: Need more analysis")
        verdict = "INCONCLUSIVE"
    
    return {
        'experiment': 'EXP-PASSED-PROFIT-SIMULATION-01',
        'timestamp': datetime.now().isoformat(),
        'settings': {'TP': TP_POINTS, 'SL': SL_POINTS, 'HORIZON': HORIZON_BARS},
        'results': results,
        'trade_counts': {k: len(v) for k, v in groups.items()},
        'verdict': verdict,
        'success_criteria': success_criteria
    }, all_trades

def create_equity_curves(trades_dict: Dict, filename: str):
    """Equity curve 비교 차트"""
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    for group_name, trades in trades_dict.items():
        if trades:
            pnls = [t['pnl'] for t in trades]
            cumulative = np.cumsum(pnls)
            ax1.plot(cumulative, label=f'{group_name} ({len(trades)} trades)', linewidth=1.5)
    ax1.set_xlabel('Trade #')
    ax1.set_ylabel('Cumulative PnL (pts)')
    ax1.set_title('Equity Curves Comparison')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    
    ax2 = axes[0, 1]
    for group_name, trades in trades_dict.items():
        if trades:
            pnls = [t['pnl'] for t in trades]
            ax2.hist(pnls, bins=20, alpha=0.5, label=group_name)
    ax2.set_xlabel('PnL per Trade')
    ax2.set_ylabel('Frequency')
    ax2.set_title('PnL Distribution')
    ax2.legend()
    ax2.axvline(x=0, color='black', linestyle='--', linewidth=0.5)
    
    ax3 = axes[1, 0]
    groups = list(trades_dict.keys())
    win_rates = []
    for g in groups:
        if trades_dict[g]:
            wins = sum(1 for t in trades_dict[g] if t['pnl'] > 0)
            win_rates.append(wins / len(trades_dict[g]))
        else:
            win_rates.append(0)
    
    colors = ['gray', 'blue', 'green']
    bars = ax3.bar(groups, win_rates, color=colors[:len(groups)], alpha=0.7)
    ax3.set_ylabel('Win Rate')
    ax3.set_title('Win Rate by Group')
    ax3.set_ylim(0, 1)
    for bar, rate in zip(bars, win_rates):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02, 
                f'{rate:.1%}', ha='center')
    
    ax4 = axes[1, 1]
    metrics_names = ['Avg PnL', 'Max DD', 'Worst Loss']
    x = np.arange(len(metrics_names))
    width = 0.25
    
    for i, (group_name, trades) in enumerate(trades_dict.items()):
        if trades:
            pnls = [t['pnl'] for t in trades]
            cumulative = np.cumsum(pnls)
            peak = np.maximum.accumulate(cumulative)
            max_dd = max(peak - cumulative) if len(cumulative) > 0 else 0
            
            values = [np.mean(pnls), max_dd, abs(min(pnls)) if pnls else 0]
            ax4.bar(x + i*width, values, width, label=group_name, alpha=0.7)
    
    ax4.set_xticks(x + width)
    ax4.set_xticklabels(metrics_names)
    ax4.set_title('Risk Metrics Comparison')
    ax4.legend()
    
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {filename}")

def main():
    for path in ["data/mnq_december_2025.csv", "data/mnq_with_ratio.csv"]:
        if os.path.exists(path):
            print(f"Loading: {path}")
            df = pd.read_csv(path)
            break
    else:
        print("ERROR: No data")
        return
    
    df.columns = df.columns.str.lower()
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    print(f"Loaded {len(df)} bars")
    
    results, all_trades = run_simulation(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[4] Creating equity curves...")
    create_equity_curves(all_trades, f"{OUTPUT_DIR}/equity_curves_comparison.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
