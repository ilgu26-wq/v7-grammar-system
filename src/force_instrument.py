"""
V7 Grammar System - Force Instrument
================================================================================

V7 is not a system that finds good shorts.
It is a system that refuses bad shorts.

Core Architecture (3 Independent Axes):
  1. ENTRY GATE (DC_pre >= 0.7) - Structural validity threshold
  2. JUDGMENT AXIS 1 (avg_delta) - Energy, controls TP size
  3. JUDGMENT AXIS 2 (force_ratio_30) - Force, controls SKIP/HOLD

RR Policy: Fixed 1R:1R (TP=10pt, SL=10pt)
================================================================================
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import json


@dataclass
class Candle:
    time: str
    open: float
    high: float
    low: float
    close: float


@dataclass
class V7Signal:
    ts: str
    idx: int
    entry_price: float
    
    dc_pre: float
    avg_delta: float
    force_ratio_30: float
    
    action: str
    tp: int
    sl: int
    
    reason: str


class ForceInstrument:
    """
    V7 Grammar System - Judgment-driven short execution framework
    
    Prioritizes loss avoidance over hit-rate maximization
    """
    
    FORCE_K = 30
    
    def __init__(self, candles: List[Dict], fr_q75: float = 1.395, fr_q25: float = 0.687):
        self.candles = [
            Candle(
                time=c.get('time', ''),
                open=float(c['open']),
                high=float(c['high']),
                low=float(c['low']),
                close=float(c['close'])
            ) for c in candles
        ]
        self.fr_q75 = fr_q75
        self.fr_q25 = fr_q25
        self.signals: List[V7Signal] = []
    
    def calc_delta(self, idx: int) -> float:
        c = self.candles[idx]
        if c.high - c.close == 0:
            return 100.0
        return min((c.close - c.low) / (c.high - c.close), 100.0)
    
    def calc_dc(self, deltas: List[float]) -> float:
        if not deltas:
            return 0.0
        signs = [1 if d > 1.0 else -1 for d in deltas]
        return abs(sum(signs)) / len(signs)
    
    def calc_force_ratio(self, idx: int) -> float:
        if idx < self.FORCE_K:
            return 1.0
        
        bull_sum = 0.0
        bear_sum = 0.0
        
        for i in range(idx - self.FORCE_K, idx):
            c = self.candles[i]
            body = c.close - c.open
            if body > 0:
                bull_sum += body
            else:
                bear_sum += abs(body)
        
        return bear_sum / (bull_sum + 0.01)
    
    def evaluate(self, idx: int) -> V7Signal:
        """
        V7 Judgment Logic (Conditional EV System)
        
        Returns action: 'SHORT', 'SKIP', or 'NO_TRADE'
        
        Optimal conditions for positive EV:
        - avg_delta >= 15 & FR <= Q25 → EV = +2.500pt
        """
        c = self.candles[idx]
        
        deltas = [self.calc_delta(i) for i in range(max(0, idx-5), idx)]
        dc_pre = self.calc_dc(deltas)
        avg_delta = sum(deltas) / len(deltas) if deltas else 0
        fr = self.calc_force_ratio(idx)
        
        if dc_pre < 0.7:
            return V7Signal(
                ts=c.time, idx=idx, entry_price=c.close,
                dc_pre=dc_pre, avg_delta=avg_delta, force_ratio_30=fr,
                action='NO_TRADE', tp=0, sl=0,
                reason='DC_pre < 0.7 (ENTRY GATE fail)'
            )
        
        if fr > self.fr_q25:
            return V7Signal(
                ts=c.time, idx=idx, entry_price=c.close,
                dc_pre=dc_pre, avg_delta=avg_delta, force_ratio_30=fr,
                action='SKIP', tp=0, sl=0,
                reason=f'force_ratio > Q25 ({self.fr_q25:.3f}) - EV negative zone'
            )
        
        if avg_delta >= 15:
            tp = 10
            reason = 'avg_delta >= 15 & FR <= Q25 (OPTIMAL: EV +2.5pt)'
        else:
            return V7Signal(
                ts=c.time, idx=idx, entry_price=c.close,
                dc_pre=dc_pre, avg_delta=avg_delta, force_ratio_30=fr,
                action='NO_TRADE', tp=0, sl=0,
                reason='avg_delta < 15 (EV negative zone)'
            )
        
        return V7Signal(
            ts=c.time, idx=idx, entry_price=c.close,
            dc_pre=dc_pre, avg_delta=avg_delta, force_ratio_30=fr,
            action='SHORT', tp=tp, sl=10,
            reason=reason
        )
    
    def scan_all(self) -> List[V7Signal]:
        self.signals = []
        for i in range(60, len(self.candles)):
            signal = self.evaluate(i)
            self.signals.append(signal)
        return self.signals
    
    def get_trade_signals(self) -> List[V7Signal]:
        return [s for s in self.signals if s.action == 'SHORT']
    
    def get_skip_signals(self) -> List[V7Signal]:
        return [s for s in self.signals if s.action == 'SKIP']
    
    def export_signals(self, filepath: str):
        data = [asdict(s) for s in self.signals]
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved: {filepath} ({len(data)} signals)")
    
    def summary(self) -> Dict:
        trades = self.get_trade_signals()
        skips = self.get_skip_signals()
        no_trades = [s for s in self.signals if s.action == 'NO_TRADE']
        
        hold_zone = [s for s in trades if s.force_ratio_30 <= self.fr_q25]
        
        return {
            'total_candles': len(self.candles),
            'total_evaluated': len(self.signals),
            'trades': len(trades),
            'skips': len(skips),
            'no_trades': len(no_trades),
            'hold_zone_trades': len(hold_zone),
            'trade_rate': len(trades) / len(self.signals) * 100 if self.signals else 0
        }


def run_instrument():
    """Run V7 Force Instrument"""
    import csv
    
    DATA_PATH = "attached_assets/chart_data_new/latest_chart.csv"
    
    candles = []
    with open(DATA_PATH, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candles.append({
                'time': row.get('time', ''),
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close']
            })
    
    print("="*80)
    print("V7 Force Instrument")
    print("="*80)
    
    instrument = ForceInstrument(candles)
    instrument.scan_all()
    
    summary = instrument.summary()
    print(f"\nTotal candles: {summary['total_candles']}")
    print(f"Evaluated: {summary['total_evaluated']}")
    print(f"Trade signals: {summary['trades']} ({summary['trade_rate']:.2f}%)")
    print(f"Skip signals: {summary['skips']}")
    print(f"Hold zone trades: {summary['hold_zone_trades']}")
    
    trades = instrument.get_trade_signals()
    if trades:
        print("\nRecent trade signals:")
        for s in trades[-5:]:
            print(f"  idx={s.idx}, DC={s.dc_pre:.2f}, avg={s.avg_delta:.1f}, "
                  f"FR={s.force_ratio_30:.2f}, TP={s.tp} | {s.reason}")
    
    instrument.export_signals("v7-grammar-system/experiments/v7_signals.json")
    
    return instrument


if __name__ == "__main__":
    run_instrument()
