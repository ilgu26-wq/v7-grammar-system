"""
EXP-MICRO-SCALP-STABLE-ONLY-01: 미시 스캘핑 최종 검증
======================================================
목적: 수익 극대화 ❌ / 리스크 제거 효과 ⭕

조건: WORLD_STATE == STABLE_BASIN 일 때만 거래
평가: Max DD, 연속 손실, tail risk 감소 확인
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_micro_scalp_stable_only_01.json"

WINDOW_PRE = 5
WINDOW_POST = 5

TP_POINTS = 2.0
SL_POINTS = 1.5
HOLD_BARS = 5

ECS_WEIGHTS = {
    'zpoc_alive': 2.0, 'htf_alive': -1.5, 'tau_alive': 0.6,
    'state_stable': 0.5, 'range_alive': 0.3,
    'recovery': -0.8, 'er_alive': -0.5, 'depth_alive': -0.3
}

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

def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
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
    
    df['recovery'] = ((df['er'].shift(3) < 0.3) & (df['er'] > 0.5)).astype(int)
    df['state_stable'] = (df['er'].diff().abs() < 0.1).astype(int)
    
    df['price_change'] = df['close'].diff().abs()
    df['force_flux'] = df['price_change'] * df['range']
    df['force_flux'] = df['force_flux'].rolling(5, min_periods=1).mean()
    
    df['ecs'] = (
        ECS_WEIGHTS['zpoc_alive'] * df['zpoc_alive'] +
        ECS_WEIGHTS['htf_alive'] * df['htf_alive'] +
        ECS_WEIGHTS['tau_alive'] * df['tau_alive'] +
        ECS_WEIGHTS['state_stable'] * df['state_stable'] +
        ECS_WEIGHTS['range_alive'] * df['range_alive'] +
        ECS_WEIGHTS['recovery'] * df['recovery'] +
        ECS_WEIGHTS['er_alive'] * df['er_alive'] +
        ECS_WEIGHTS['depth_alive'] * df['depth_alive']
    )
    
    resistance = 1.0 + 2.0 * (1 - df['zpoc_alive']) + 0.5 * df['htf_alive'] + 1.0 * df['recovery']
    pg = df['force_flux'] / (df['ecs'] + 2.0).clip(lower=0.1)
    df['ri'] = pg * resistance
    
    return df

def compute_ie(df: pd.DataFrame, idx: int) -> float:
    start = max(0, idx - WINDOW_PRE)
    end = min(len(df), idx + WINDOW_POST + 1)
    window = df.iloc[start:end]
    
    if len(window) < 3:
        return 0.0
    
    fields = [
        window['zpoc_alive'].mean(),
        window['htf_alive'].mean(),
        window['er'].mean() * (1 - window['er'].std()),
        1.0 - min(1.0, window['depth'].std() * 3),
        window['tau_alive'].mean(),
        max(0, 1.0 - window['range'].std() / max(window['range'].mean(), 0.01)),
        min(1.0, window['recovery'].sum()),
        window['state_stable'].mean()
    ]
    
    ie = sum(fields) - np.var(fields)
    
    if fields[0] < 0.3 and fields[2] > 0.6:
        ie -= 1.0
    if fields[0] < 0.3 and sum(fields) > 4.0:
        ie -= 1.5
    
    return ie

def is_stable_basin(ie: float, ri: float, ecs: float, zpoc: int, ri_q75: float) -> bool:
    return (2.3 <= ie <= 3.8 and ri < ri_q75 and ecs > 1.0 and zpoc == 1)

def find_micro_entries(df: pd.DataFrame, ri_q75: float) -> List[Dict]:
    entries = []
    
    for i in range(50, len(df) - HOLD_BARS - 1, 3):
        ie = compute_ie(df, i)
        ri = df['ri'].iloc[i]
        ecs = df['ecs'].iloc[i]
        zpoc = df['zpoc_alive'].iloc[i]
        
        is_stable = is_stable_basin(ie, ri, ecs, zpoc, ri_q75)
        
        if df['er'].iloc[i] > 0.4 and df['er'].iloc[i-1] < 0.4:
            direction = 1 if df['close'].iloc[i] > df['open'].iloc[i] else -1
            direction = -direction
            
            entries.append({
                'idx': i,
                'entry_price': df['close'].iloc[i],
                'direction': direction,
                'is_stable': is_stable,
                'ie': ie,
                'ri': ri
            })
    
    return entries

def simulate_trade(df: pd.DataFrame, entry: Dict) -> Dict:
    idx = entry['idx']
    entry_price = entry['entry_price']
    direction = entry['direction']
    
    tp_price = entry_price + direction * TP_POINTS
    sl_price = entry_price - direction * SL_POINTS
    
    for i in range(1, HOLD_BARS + 1):
        if idx + i >= len(df):
            break
        
        bar = df.iloc[idx + i]
        
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
    
    exit_price = df['close'].iloc[min(idx + HOLD_BARS, len(df) - 1)]
    pnl = direction * (exit_price - entry_price)
    return {'pnl': pnl, 'result': 'TIMEOUT', 'bars': HOLD_BARS}

def calculate_metrics(trades: List[Dict]) -> Dict:
    if not trades:
        return {'count': 0}
    
    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    
    cumulative = np.cumsum(pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdowns = peak - cumulative
    
    max_cons_loss = 0
    current = 0
    for p in pnls:
        if p < 0:
            current += 1
            max_cons_loss = max(max_cons_loss, current)
        else:
            current = 0
    
    loss_tail = np.percentile(losses, 5) if losses else 0
    
    return {
        'count': len(trades),
        'win_rate': len(wins) / len(trades) if trades else 0,
        'avg_pnl': np.mean(pnls),
        'total_pnl': sum(pnls),
        'max_dd': max(drawdowns) if len(drawdowns) > 0 else 0,
        'max_cons_loss': max_cons_loss,
        'loss_tail_5pct': loss_tail,
        'avg_win': np.mean(wins) if wins else 0,
        'avg_loss': np.mean(losses) if losses else 0
    }

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-MICRO-SCALP-STABLE-ONLY-01")
    print("미시 스캘핑 최종 검증 (STABLE_BASIN only)")
    print("=" * 70)
    
    print(f"\n  Trade Params: TP={TP_POINTS}pt, SL={SL_POINTS}pt, Hold={HOLD_BARS} bars")
    
    print("\n[1] Computing indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q90 = df['ri'].quantile(0.90)
    
    print(f"  RI: q75={ri_q75:.2f}, q90={ri_q90:.2f}")
    
    print("\n[2] Finding micro entries...")
    entries = find_micro_entries(df, ri_q75)
    print(f"  Total entries: {len(entries)}")
    
    stable_entries = [e for e in entries if e['is_stable']]
    unstable_entries = [e for e in entries if not e['is_stable']]
    print(f"  STABLE_BASIN: {len(stable_entries)}")
    print(f"  OTHER: {len(unstable_entries)}")
    
    print("\n[3] Simulating trades...")
    
    all_trades = []
    for entry in entries:
        trade = simulate_trade(df, entry)
        trade.update(entry)
        all_trades.append(trade)
    
    stable_trades = [t for t in all_trades if t['is_stable']]
    unstable_trades = [t for t in all_trades if not t['is_stable']]
    
    all_metrics = calculate_metrics(all_trades)
    stable_metrics = calculate_metrics(stable_trades)
    unstable_metrics = calculate_metrics(unstable_trades)
    
    print("\n[4] Results...")
    
    print("\n  [ALL TRADES]")
    print(f"    Count: {all_metrics['count']}")
    print(f"    Win Rate: {all_metrics['win_rate']:.1%}")
    print(f"    Avg PnL: {all_metrics['avg_pnl']:+.3f} pts")
    print(f"    Max DD: {all_metrics['max_dd']:.2f} pts")
    print(f"    Max Cons Loss: {all_metrics['max_cons_loss']}")
    print(f"    Loss Tail (5%): {all_metrics['loss_tail_5pct']:.2f} pts")
    
    print("\n  [STABLE_BASIN ONLY]")
    print(f"    Count: {stable_metrics['count']}")
    print(f"    Win Rate: {stable_metrics['win_rate']:.1%}")
    print(f"    Avg PnL: {stable_metrics['avg_pnl']:+.3f} pts")
    print(f"    Max DD: {stable_metrics['max_dd']:.2f} pts")
    print(f"    Max Cons Loss: {stable_metrics['max_cons_loss']}")
    print(f"    Loss Tail (5%): {stable_metrics['loss_tail_5pct']:.2f} pts")
    
    print("\n  [OTHER (FORBIDDEN ZONES)]")
    print(f"    Count: {unstable_metrics['count']}")
    print(f"    Win Rate: {unstable_metrics['win_rate']:.1%}")
    print(f"    Avg PnL: {unstable_metrics['avg_pnl']:+.3f} pts")
    print(f"    Max DD: {unstable_metrics['max_dd']:.2f} pts")
    print(f"    Max Cons Loss: {unstable_metrics['max_cons_loss']}")
    
    print("\n" + "=" * 70)
    print("RISK REDUCTION ANALYSIS")
    print("=" * 70)
    
    if all_metrics['max_dd'] > 0:
        dd_reduction = (all_metrics['max_dd'] - stable_metrics['max_dd']) / all_metrics['max_dd']
    else:
        dd_reduction = 0
    
    if all_metrics['max_cons_loss'] > 0:
        cons_loss_reduction = (all_metrics['max_cons_loss'] - stable_metrics['max_cons_loss']) / all_metrics['max_cons_loss']
    else:
        cons_loss_reduction = 0
    
    print(f"\n  Max DD: {all_metrics['max_dd']:.1f} → {stable_metrics['max_dd']:.1f} ({dd_reduction*100:+.0f}%)")
    print(f"  Cons Loss: {all_metrics['max_cons_loss']} → {stable_metrics['max_cons_loss']} ({cons_loss_reduction*100:+.0f}%)")
    print(f"  Win Rate: {all_metrics['win_rate']:.1%} → {stable_metrics['win_rate']:.1%}")
    
    dd_pass = dd_reduction >= 0.30
    cons_pass = cons_loss_reduction >= 0.20
    wr_maintained = stable_metrics['win_rate'] >= all_metrics['win_rate'] * 0.9
    
    print(f"\n  [Success Criteria]")
    print(f"    DD ≥ 30% reduced: {'✓ PASS' if dd_pass else '✗ FAIL'} ({dd_reduction*100:.0f}%)")
    print(f"    Cons Loss ≥ 20% reduced: {'✓ PASS' if cons_pass else '✗ FAIL'} ({cons_loss_reduction*100:.0f}%)")
    print(f"    WinRate maintained: {'✓ PASS' if wr_maintained else '✗ FAIL'}")
    
    overall_success = dd_pass and wr_maintained
    
    print(f"\n  Overall: {'✓ STABLE_BASIN VALIDATED' if overall_success else '△ PARTIAL'}")
    
    return {
        'experiment': 'EXP-MICRO-SCALP-STABLE-ONLY-01',
        'timestamp': datetime.now().isoformat(),
        'params': {'tp': TP_POINTS, 'sl': SL_POINTS, 'hold': HOLD_BARS},
        'all_metrics': all_metrics,
        'stable_metrics': stable_metrics,
        'unstable_metrics': unstable_metrics,
        'reduction': {
            'dd': dd_reduction,
            'cons_loss': cons_loss_reduction
        },
        'success': overall_success
    }, all_trades, stable_trades, unstable_trades

def create_visualizations(results: Dict, all_trades: List, stable_trades: List, 
                         unstable_trades: List, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    for name, trades, color in [('ALL', all_trades, 'gray'), 
                                 ('STABLE', stable_trades, 'green'),
                                 ('OTHER', unstable_trades, 'red')]:
        if trades:
            pnls = [t['pnl'] for t in trades]
            cumulative = np.cumsum(pnls)
            ax1.plot(cumulative, label=f'{name} ({len(trades)} trades)', 
                    color=color, linewidth=1.5, alpha=0.8)
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax1.set_xlabel('Trade #')
    ax1.set_ylabel('Cumulative PnL (pts)')
    ax1.set_title('Equity Curves by World State')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    ax2 = axes[0, 1]
    metrics_names = ['Max DD', 'Cons Loss', 'Win Rate']
    all_vals = [results['all_metrics']['max_dd'], 
               results['all_metrics']['max_cons_loss'],
               results['all_metrics']['win_rate']]
    stable_vals = [results['stable_metrics']['max_dd'],
                  results['stable_metrics']['max_cons_loss'],
                  results['stable_metrics']['win_rate']]
    
    x = np.arange(len(metrics_names))
    width = 0.35
    
    all_normalized = [all_vals[0]/max(all_vals[0], stable_vals[0], 1),
                      all_vals[1]/max(all_vals[1], stable_vals[1], 1),
                      all_vals[2]]
    stable_normalized = [stable_vals[0]/max(all_vals[0], stable_vals[0], 1),
                        stable_vals[1]/max(all_vals[1], stable_vals[1], 1),
                        stable_vals[2]]
    
    ax2.bar(x - width/2, all_normalized, width, label='ALL', color='gray', alpha=0.7)
    ax2.bar(x + width/2, stable_normalized, width, label='STABLE', color='green', alpha=0.7)
    ax2.set_xticks(x)
    ax2.set_xticklabels(metrics_names)
    ax2.set_ylabel('Normalized Value')
    ax2.set_title('Risk Metrics Comparison\n(Lower DD/ConsLoss = Better)')
    ax2.legend()
    
    ax3 = axes[1, 0]
    if stable_trades:
        stable_pnls = [t['pnl'] for t in stable_trades]
        ax3.hist(stable_pnls, bins=30, color='green', alpha=0.7, label='STABLE', density=True)
    if unstable_trades:
        unstable_pnls = [t['pnl'] for t in unstable_trades]
        ax3.hist(unstable_pnls, bins=30, color='red', alpha=0.5, label='OTHER', density=True)
    ax3.axvline(x=0, color='black', linestyle='--')
    ax3.set_xlabel('PnL (pts)')
    ax3.set_ylabel('Density')
    ax3.set_title('PnL Distribution by World State')
    ax3.legend()
    
    ax4 = axes[1, 1]
    reductions = results['reduction']
    labels = ['Max DD\nReduction', 'Cons Loss\nReduction']
    values = [reductions['dd'] * 100, reductions['cons_loss'] * 100]
    colors = ['green' if v >= 30 else 'orange' for v in values]
    
    bars = ax4.bar(labels, values, color=colors, alpha=0.7)
    ax4.axhline(y=30, color='green', linestyle='--', alpha=0.5, label='Target (30%)')
    ax4.set_ylabel('Reduction (%)')
    ax4.set_title('Risk Reduction Achievement')
    ax4.set_ylim(0, max(100, max(values) * 1.2))
    
    for bar, val in zip(bars, values):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                f'{val:.0f}%', ha='center', fontsize=11, fontweight='bold')
    
    status = "✓ VALIDATED" if results['success'] else "△ PARTIAL"
    plt.suptitle(f'Micro-Scalping in STABLE_BASIN: {status}', fontsize=12, fontweight='bold')
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
    
    results, all_trades, stable_trades, unstable_trades = run_experiment(df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[5] Creating visualizations...")
    create_visualizations(results, all_trades, stable_trades, unstable_trades,
                         f"{OUTPUT_DIR}/micro_scalp_stable.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
