"""
EXP-AXIOM-CROSS-ASSET-PROFIT-01: 다른 자산 검증 + AXIOM 수익 시뮬레이션
========================================================================
목표:
  1. NQ 데이터로 AXIOM 규칙 검증 (MNQ에서 발견 → NQ에서 확인)
  2. AXIOM 적용 후 수익 시뮬레이션

AXIOM 규칙:
  - IE 2.0-4.5 범위 유효
  - RI > q95 → Hard Kill (SPIKE)
  - RI > q90 for 3+ bars → Soft Kill (PLATEAU)
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

OUTPUT_DIR = "v7-grammar-system/images"
RESULT_FILE = "v7-grammar-system/results/exp_axiom_cross_asset_profit_01.json"

TP_POINTS = 6.0
SL_POINTS = 4.0
HORIZON_BARS = 10
PLATEAU_K = 3
WINDOW_PRE = 5
WINDOW_POST = 5

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

def apply_axiom_mask(df: pd.DataFrame) -> pd.DataFrame:
    theta_95 = df['ri'].quantile(0.95)
    theta_90 = df['ri'].quantile(0.90)
    
    df['spike'] = (df['ri'] > theta_95).astype(int)
    
    above_90 = (df['ri'] > theta_90).astype(int)
    plateau = []
    for i in range(len(df)):
        if i < PLATEAU_K - 1:
            plateau.append(0)
        else:
            p = int(above_90.iloc[i-PLATEAU_K+1:i+1].sum() >= PLATEAU_K)
            plateau.append(p)
    df['plateau_90'] = plateau
    
    ie_list = []
    for idx in range(len(df)):
        ie_list.append(compute_ie(df, idx))
    df['ie'] = ie_list
    
    df['axiom_mask'] = 1.0
    df.loc[(df['ie'] < 2.0) | (df['ie'] > 4.5), 'axiom_mask'] = 0.0
    df.loc[df['spike'] == 1, 'axiom_mask'] = 0.0
    df.loc[df['plateau_90'] == 1, 'axiom_mask'] = 0.5
    
    return df, theta_95, theta_90

def compute_collapse_label(df: pd.DataFrame, idx: int, lookforward: int = 30) -> int:
    if idx + lookforward >= len(df):
        return 0
    
    future = df.iloc[idx:idx + lookforward + 1]
    er_min = future['er'].min()
    er_drop = df['er'].iloc[idx] - er_min
    price_drop = (df['close'].iloc[idx] - future['low'].min()) / max(df['range'].iloc[idx], 0.01)
    
    conditions_met = sum([er_min < 0.15, er_drop > 0.50, price_drop > 5.0])
    return 1 if conditions_met >= 2 else 0

def find_entry_signals(df: pd.DataFrame) -> List[Dict]:
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
                        'axiom_mask': df['axiom_mask'].iloc[future_idx],
                        'zpoc_alive': df['zpoc_alive'].iloc[future_idx],
                        'spike': df['spike'].iloc[future_idx],
                        'ie': df['ie'].iloc[future_idx]
                    })
                    break
    
    return signals

def simulate_trade(df: pd.DataFrame, signal: Dict) -> Dict:
    entry_idx = signal['entry_idx']
    entry_price = signal['entry_price']
    direction = signal['direction']
    
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

def calculate_metrics(trades: List[Dict]) -> Dict:
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
        'max_dd': max(drawdowns) if len(drawdowns) > 0 else 0,
        'consecutive_losses': max_consecutive_losses(pnls)
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

def run_experiment(mnq_df: pd.DataFrame, nq_df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-AXIOM-CROSS-ASSET-PROFIT-01")
    print("다른 자산 검증 + AXIOM 수익 시뮬레이션")
    print("=" * 70)
    
    print("\n[PART 1: 교차 자산 검증]")
    print("=" * 70)
    
    results = {}
    
    for name, df in [("MNQ", mnq_df), ("NQ", nq_df)]:
        print(f"\n--- {name} ({len(df)} bars) ---")
        
        df = compute_all_indicators(df)
        df, theta_95, theta_90 = apply_axiom_mask(df)
        
        collapse_list = []
        for idx in range(len(df)):
            collapse_list.append(compute_collapse_label(df, idx))
        df['collapse'] = collapse_list
        
        spike_df = df[df['spike'] == 1]
        none_df = df[(df['spike'] == 0) & (df['plateau_90'] == 0)]
        
        spike_collapse = spike_df['collapse'].mean() if len(spike_df) > 0 else 0
        none_collapse = none_df['collapse'].mean() if len(none_df) > 0 else 0
        
        zpoc_dead = df[df['zpoc_alive'] == 0]
        zpoc_dead_collapse = zpoc_dead['collapse'].mean() if len(zpoc_dead) > 0 else 0
        
        zpoc_dead_spike = df[(df['zpoc_alive'] == 0) & (df['spike'] == 1)]
        zpoc_dead_spike_collapse = zpoc_dead_spike['collapse'].mean() if len(zpoc_dead_spike) > 0 else 0
        
        print(f"  SPIKE (q95): {spike_collapse:.1%} collapse (n={len(spike_df)})")
        print(f"  NONE: {none_collapse:.1%} collapse (n={len(none_df)})")
        print(f"  ZPOC DEAD: {zpoc_dead_collapse:.1%} collapse (n={len(zpoc_dead)})")
        print(f"  ZPOC DEAD + SPIKE: {zpoc_dead_spike_collapse:.1%} collapse (n={len(zpoc_dead_spike)})")
        
        direction_maintained = spike_collapse > none_collapse
        print(f"\n  Direction (SPIKE > NONE): {'✓ MAINTAINED' if direction_maintained else '✗ FAILED'}")
        
        results[name] = {
            'spike_collapse': spike_collapse,
            'none_collapse': none_collapse,
            'zpoc_dead_collapse': zpoc_dead_collapse,
            'zpoc_dead_spike_collapse': zpoc_dead_spike_collapse,
            'direction_maintained': direction_maintained
        }
    
    print("\n[PART 2: AXIOM 수익 시뮬레이션]")
    print("=" * 70)
    
    mnq_df = compute_all_indicators(mnq_df)
    mnq_df, theta_95, theta_90 = apply_axiom_mask(mnq_df)
    
    signals = find_entry_signals(mnq_df)
    print(f"\n  Total signals: {len(signals)}")
    
    groups = {
        'ALL': [s for s in signals],
        'NO_AXIOM': [s for s in signals if s['axiom_mask'] == 1.0],
        'AXIOM_FULL': [s for s in signals if s['axiom_mask'] == 1.0 and s['spike'] == 0]
    }
    
    print(f"  ALL: {len(groups['ALL'])}")
    print(f"  NO_AXIOM (mask=1.0): {len(groups['NO_AXIOM'])}")
    print(f"  AXIOM_FULL (mask=1.0, no spike): {len(groups['AXIOM_FULL'])}")
    
    profit_results = {}
    all_trades = {}
    
    for group_name, group_signals in groups.items():
        trades = []
        for signal in group_signals:
            trade = simulate_trade(mnq_df, signal)
            trade.update(signal)
            trades.append(trade)
        
        metrics = calculate_metrics(trades)
        profit_results[group_name] = metrics
        all_trades[group_name] = trades
        
        print(f"\n  [{group_name}]")
        print(f"    Trades: {metrics['count']}")
        print(f"    Win Rate: {metrics.get('win_rate', 0):.1%}")
        print(f"    Avg PnL: {metrics.get('avg_pnl', 0):+.2f} pts")
        print(f"    Total PnL: {metrics.get('total_pnl', 0):+.2f} pts")
        print(f"    Max DD: {metrics.get('max_dd', 0):.2f} pts")
        print(f"    Consecutive Losses: {metrics.get('consecutive_losses', 0)}")
    
    print("\n" + "=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)
    
    cross_asset_passed = all(r['direction_maintained'] for r in results.values())
    
    all_m = profit_results['ALL']
    axiom_m = profit_results['AXIOM_FULL']
    
    dd_reduced = axiom_m.get('max_dd', 0) < all_m.get('max_dd', 0) * 0.8 if all_m['count'] > 0 else False
    
    print(f"\n  교차 자산 검증: {'✓ PASS' if cross_asset_passed else '✗ FAIL'}")
    print(f"  Max DD 감소: {'✓ PASS' if dd_reduced else '✗ FAIL'}")
    
    if all_m['count'] > 0 and axiom_m['count'] > 0:
        print(f"\n  [비교]")
        print(f"  Trades: {all_m['count']} → {axiom_m['count']} ({axiom_m['count']/all_m['count']*100:.1f}%)")
        print(f"  Win Rate: {all_m['win_rate']:.1%} → {axiom_m['win_rate']:.1%}")
        print(f"  Max DD: {all_m['max_dd']:.1f} → {axiom_m['max_dd']:.1f} ({(1-axiom_m['max_dd']/all_m['max_dd'])*100:.1f}% 감소)")
    
    return {
        'experiment': 'EXP-AXIOM-CROSS-ASSET-PROFIT-01',
        'timestamp': datetime.now().isoformat(),
        'cross_asset': results,
        'profit_simulation': profit_results,
        'verdict': {
            'cross_asset_passed': cross_asset_passed,
            'dd_reduced': dd_reduced
        }
    }, all_trades, mnq_df

def create_visualizations(results: Dict, all_trades: Dict, mnq_df: pd.DataFrame, filename: str):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    ax1 = axes[0, 0]
    assets = list(results['cross_asset'].keys())
    spike_rates = [results['cross_asset'][a]['spike_collapse'] for a in assets]
    none_rates = [results['cross_asset'][a]['none_collapse'] for a in assets]
    
    x = np.arange(len(assets))
    width = 0.35
    ax1.bar(x - width/2, spike_rates, width, label='SPIKE', color='red', alpha=0.7)
    ax1.bar(x + width/2, none_rates, width, label='NONE', color='green', alpha=0.7)
    ax1.set_xticks(x)
    ax1.set_xticklabels(assets)
    ax1.set_ylabel('Collapse Rate')
    ax1.set_title('Cross-Asset Validation: SPIKE > NONE')
    ax1.legend()
    ax1.set_ylim(0, 1)
    
    for i, (s, n) in enumerate(zip(spike_rates, none_rates)):
        ax1.text(i - width/2, s + 0.02, f'{s:.0%}', ha='center', fontsize=9)
        ax1.text(i + width/2, n + 0.02, f'{n:.0%}', ha='center', fontsize=9)
    
    ax2 = axes[0, 1]
    for group_name, trades in all_trades.items():
        if trades:
            pnls = [t['pnl'] for t in trades]
            cumulative = np.cumsum(pnls)
            ax2.plot(cumulative, label=f'{group_name} ({len(trades)} trades)', linewidth=1.5)
    ax2.set_xlabel('Trade #')
    ax2.set_ylabel('Cumulative PnL (pts)')
    ax2.set_title('Equity Curves: AXIOM Effect')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    
    ax3 = axes[1, 0]
    groups = list(results['profit_simulation'].keys())
    max_dds = [results['profit_simulation'][g].get('max_dd', 0) for g in groups]
    colors = ['gray', 'orange', 'green']
    
    bars = ax3.bar(groups, max_dds, color=colors, alpha=0.7)
    ax3.set_ylabel('Max Drawdown (pts)')
    ax3.set_title('Max DD Comparison')
    
    for bar, dd in zip(bars, max_dds):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f'{dd:.1f}', ha='center', fontsize=10)
    
    ax4 = axes[1, 1]
    win_rates = [results['profit_simulation'][g].get('win_rate', 0) for g in groups]
    cons_losses = [results['profit_simulation'][g].get('consecutive_losses', 0) for g in groups]
    
    x = np.arange(len(groups))
    ax4.bar(x - width/2, win_rates, width, label='Win Rate', color='blue', alpha=0.7)
    ax4_twin = ax4.twinx()
    ax4_twin.bar(x + width/2, cons_losses, width, label='Cons. Losses', color='red', alpha=0.7)
    
    ax4.set_xticks(x)
    ax4.set_xticklabels(groups)
    ax4.set_ylabel('Win Rate', color='blue')
    ax4_twin.set_ylabel('Consecutive Losses', color='red')
    ax4.set_title('Win Rate & Consecutive Losses')
    ax4.set_ylim(0, 1)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {filename}")

def main():
    print("Loading data...")
    
    mnq_df = pd.read_csv("data/mnq_december_2025.csv")
    mnq_df.columns = mnq_df.columns.str.lower()
    mnq_df = mnq_df.dropna(subset=['open', 'high', 'low', 'close'])
    print(f"  MNQ: {len(mnq_df)} bars")
    
    nq_df = pd.read_csv("data/nq1_full_combined.csv")
    nq_df.columns = nq_df.columns.str.lower()
    nq_df = nq_df.dropna(subset=['open', 'high', 'low', 'close'])
    print(f"  NQ: {len(nq_df)} bars")
    
    results, all_trades, mnq_df = run_experiment(mnq_df, nq_df)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    
    print("\n[Creating visualizations...]")
    create_visualizations(results, all_trades, mnq_df, f"{OUTPUT_DIR}/axiom_cross_asset_profit.png")
    
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {RESULT_FILE}")

if __name__ == "__main__":
    main()
