"""
IGNITION Lift Verification
모든 신호에 대해 H4_STB_IGNITION 기준으로 lift 계산

기준축 (고정):
- Timeframe: 1m
- Channel Period: 20 bars
- TP/SL: 20pt / 15pt
- Cooldown: 10 bars
- Exit Window: 50 bars
- STB 정의: 채널 상단/하단 + ratio

판정 기준:
- lift >= 1.3 → IGNITION 승격
- lift 1.1~1.3 → 보류
- lift < 1.1 → 삭제 또는 archive
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import defaultdict

DATA_PATH = "data/nq1_full_combined.csv"
RESULTS_PATH = "v7-grammar-system/experiments/ignition_lift_results.json"

CHANNEL_PERIOD = 20
LIFT_WINDOW = 5
TP_POINTS = 20
SL_POINTS = 15


@dataclass
class Bar:
    idx: int
    time: str
    open: float
    high: float
    low: float
    close: float
    ratio: float = 0.0
    channel_pct: float = 50.0
    channel_high: float = 0.0
    channel_low: float = 0.0
    stb_long: bool = False
    stb_short: bool = False
    poc_touch: bool = False
    zpoc_touch: bool = False
    blackline_touch: bool = False
    resist_zscore_05: bool = False
    resist_zscore_10: bool = False
    resist_zscore_15: bool = False


def load_data() -> List[Bar]:
    df = pd.read_csv(DATA_PATH)
    bars = []
    
    for i, row in df.iterrows():
        bar = Bar(
            idx=i,
            time=str(row.get('time', '')),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
        )
        bars.append(bar)
    
    return bars


def calculate_channel(bars: List[Bar], period: int = CHANNEL_PERIOD):
    for i in range(period, len(bars)):
        window = bars[i-period:i]
        high = max(b.high for b in window)
        low = min(b.low for b in window)
        bars[i].channel_high = high
        bars[i].channel_low = low
        
        if high > low:
            bars[i].channel_pct = (bars[i].close - low) / (high - low) * 100
        else:
            bars[i].channel_pct = 50.0


def calculate_ratio(bars: List[Bar]):
    for bar in bars:
        high_close = bar.high - bar.close
        close_low = bar.close - bar.low
        
        if high_close > 0.25:
            bar.ratio = close_low / high_close
        else:
            bar.ratio = 1.0


def calculate_stb(bars: List[Bar]):
    for i, bar in enumerate(bars):
        if i < CHANNEL_PERIOD:
            continue
        
        if bar.channel_pct >= 80 and bar.ratio >= 1.5:
            bar.stb_short = True
        elif bar.channel_pct <= 20 and bar.ratio <= 0.7:
            bar.stb_long = True


def simulate_signals(bars: List[Bar]):
    poc_level = None
    zpoc_level = None
    blackline_level = None
    
    for i, bar in enumerate(bars):
        if i < CHANNEL_PERIOD + 10:
            continue
        
        if poc_level is None:
            poc_level = bars[i-10].close
        if zpoc_level is None:
            zpoc_level = bars[i-15].close
        if blackline_level is None:
            blackline_level = bars[i-20].close
        
        if abs(bar.close - poc_level) <= 5:
            bar.poc_touch = True
        if abs(bar.close - zpoc_level) <= 5:
            bar.zpoc_touch = True
        if abs(bar.close - blackline_level) <= 5:
            bar.blackline_touch = True
        
        if i >= 30:
            window = bars[i-30:i]
            closes = [b.close for b in window]
            mean = np.mean(closes)
            std = np.std(closes) if len(closes) > 1 else 1
            if std > 0:
                zscore = (bar.close - mean) / std
            else:
                zscore = 0
            
            if abs(zscore) >= 0.5:
                bar.resist_zscore_05 = True
            if abs(zscore) >= 1.0:
                bar.resist_zscore_10 = True
            if abs(zscore) >= 1.5:
                bar.resist_zscore_15 = True
        
        if i % 50 == 0:
            poc_level = bar.close
        if i % 75 == 0:
            zpoc_level = bar.close
        if i % 100 == 0:
            blackline_level = bar.close


def calculate_lift(bars: List[Bar], signal_name: str, signal_checker) -> Dict:
    total_bars = len(bars)
    
    total_stb = sum(1 for b in bars if b.stb_short or b.stb_long)
    p_stb_overall = total_stb / total_bars if total_bars > 0 else 0
    
    signal_count = 0
    stb_after_signal = 0
    
    for i in range(CHANNEL_PERIOD, len(bars) - LIFT_WINDOW):
        if signal_checker(bars[i]):
            signal_count += 1
            
            for j in range(1, LIFT_WINDOW + 1):
                if i + j < len(bars):
                    if bars[i + j].stb_short or bars[i + j].stb_long:
                        stb_after_signal += 1
                        break
    
    if signal_count > 0:
        p_stb_given_signal = stb_after_signal / signal_count
    else:
        p_stb_given_signal = 0
    
    if p_stb_overall > 0:
        lift = p_stb_given_signal / p_stb_overall
    else:
        lift = 0
    
    if lift >= 1.3:
        verdict = "IGNITION"
    elif lift >= 1.1:
        verdict = "HOLD"
    else:
        verdict = "DELETE"
    
    return {
        "signal": signal_name,
        "n_signal": signal_count,
        "n_stb_after": stb_after_signal,
        "p_stb_given_signal": round(p_stb_given_signal * 100, 2),
        "p_stb_overall": round(p_stb_overall * 100, 2),
        "lift": round(lift, 3),
        "verdict": verdict,
        "min_sample_met": signal_count >= 100
    }


def run_all_lift_tests():
    print("Loading data...")
    bars = load_data()
    print(f"Loaded {len(bars)} bars")
    
    print("Calculating indicators...")
    calculate_channel(bars)
    calculate_ratio(bars)
    calculate_stb(bars)
    simulate_signals(bars)
    
    signal_definitions = {
        "POC_touch": lambda b: b.poc_touch,
        "ZPOC_touch": lambda b: b.zpoc_touch,
        "Blackline_touch": lambda b: b.blackline_touch,
        "RESIST_zscore_0.5": lambda b: b.resist_zscore_05,
        "RESIST_zscore_1.0": lambda b: b.resist_zscore_10,
        "RESIST_zscore_1.5": lambda b: b.resist_zscore_15,
        "Channel_80plus": lambda b: b.channel_pct >= 80,
        "Channel_20minus": lambda b: b.channel_pct <= 20,
        "Ratio_1.5plus": lambda b: b.ratio >= 1.5,
        "Ratio_0.7minus": lambda b: b.ratio <= 0.7,
    }
    
    print("\n" + "="*80)
    print("IGNITION LIFT VERIFICATION")
    print("="*80)
    print(f"Timeframe: 1m | Channel: {CHANNEL_PERIOD} bars | Lift Window: {LIFT_WINDOW} bars")
    print("="*80)
    
    results = []
    
    for signal_name, checker in signal_definitions.items():
        result = calculate_lift(bars, signal_name, checker)
        results.append(result)
        
        icon = "🔥" if result["verdict"] == "IGNITION" else ("⚠️" if result["verdict"] == "HOLD" else "❌")
        sample_warn = "" if result["min_sample_met"] else " [SAMPLE < 100]"
        
        print(f"\n{icon} {signal_name}")
        print(f"   n={result['n_signal']}{sample_warn}")
        print(f"   P(STB|signal)={result['p_stb_given_signal']}%")
        print(f"   P(STB)={result['p_stb_overall']}%")
        print(f"   lift={result['lift']} → {result['verdict']}")
    
    summary = {
        "metadata": {
            "timeframe": "1m",
            "channel_period": CHANNEL_PERIOD,
            "lift_window": LIFT_WINDOW,
            "data_file": DATA_PATH,
            "test_date": datetime.now().isoformat(),
            "bars_count": len(bars),
            "total_stb_count": sum(1 for b in bars if b.stb_short or b.stb_long)
        },
        "results": results,
        "classification": {
            "IGNITION": [r["signal"] for r in results if r["verdict"] == "IGNITION" and r["min_sample_met"]],
            "HOLD": [r["signal"] for r in results if r["verdict"] == "HOLD" and r["min_sample_met"]],
            "DELETE": [r["signal"] for r in results if r["verdict"] == "DELETE"],
            "INSUFFICIENT_SAMPLE": [r["signal"] for r in results if not r["min_sample_met"]]
        }
    }
    
    print("\n" + "="*80)
    print("FINAL CLASSIFICATION")
    print("="*80)
    print(f"\n🔥 IGNITION: {summary['classification']['IGNITION']}")
    print(f"⚠️ HOLD: {summary['classification']['HOLD']}")
    print(f"❌ DELETE: {summary['classification']['DELETE']}")
    print(f"📊 INSUFFICIENT SAMPLE: {summary['classification']['INSUFFICIENT_SAMPLE']}")
    
    with open(RESULTS_PATH, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to: {RESULTS_PATH}")
    
    return summary


if __name__ == "__main__":
    run_all_lift_tests()
