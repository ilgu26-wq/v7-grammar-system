"""
Phase G — Alpha Fitness Verification
기존 알파 로그 + V7 상태 교차 분석

핵심 질문:
"알파 수익의 80% 이상이 V7 ENTER/OBSERVE 구간에서 발생하는가?"

검증 항목:
1. 각 알파 신호에 V7 상태 태깅 (WAIT/OBSERVE/ENTER)
2. 상태별 PnL 분포 분석
3. 손실이 WAIT에 집중되는지 확인
"""

import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')

from shadow_mode import ShadowModeAdapter


@dataclass
class AlphaTrade:
    """Single alpha trade record"""
    timestamp: str
    direction: str
    entry_price: float
    mfe: float  # Maximum Favorable Excursion
    mae: float  # Maximum Adverse Excursion
    pnl: float  # Calculated PnL
    terminated_by: str
    v7_state: str = "UNKNOWN"
    
    def is_winner(self) -> bool:
        return self.mfe > self.mae or self.pnl > 0


@dataclass
class FitnessReport:
    """Alpha Fitness analysis report"""
    total_trades: int
    by_state: Dict[str, Dict]
    pnl_by_state: Dict[str, float]
    win_rate_by_state: Dict[str, float]
    concentration: Dict[str, float]  # % of trades/pnl in each state
    fitness_score: float  # 0-100, higher = better alignment
    verdict: str


class AlphaFitnessAnalyzer:
    """
    Analyze alpha performance relative to V7 states
    
    Core Hypothesis:
    If V7 grammar is correct:
    - Winning trades should cluster in ENTER/OBSERVE
    - Losing trades should cluster in WAIT
    - Fitness score = % of profits from ENTER+OBSERVE
    """
    
    def __init__(self):
        self.trades: List[AlphaTrade] = []
        self.v7_states_log: List[Dict] = []
    
    def load_continuation_results(self, filepath: str = '/home/runner/workspace/.continuation_results.json'):
        """Load actual trade results"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        for t in data:
            pnl = t.get('mfe', 0) - t.get('mae', 0)
            if 'TP' in t.get('terminated_by', ''):
                pnl = t.get('mfe', 0)
            elif 'SL' in t.get('terminated_by', '') or 'MAE' in t.get('terminated_by', ''):
                pnl = -t.get('mae', 0)
            
            trade = AlphaTrade(
                timestamp=t.get('t0_time', t.get('time', '')),
                direction=t.get('direction', 'UNKNOWN'),
                entry_price=t.get('t0_price', 0),
                mfe=t.get('mfe', 0),
                mae=t.get('mae', 0),
                pnl=pnl,
                terminated_by=t.get('terminated_by', '')
            )
            self.trades.append(trade)
        
        print(f"Loaded {len(self.trades)} trades from continuation_results")
    
    def load_telegram_signals(self, filepath: str = '/home/runner/workspace/.telegram_signal_log.json'):
        """Load telegram signal log for context"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        signals = []
        for date, day_data in data.items():
            for sig in day_data.get('signals', []):
                sig['date'] = date
                signals.append(sig)
        
        print(f"Loaded {len(signals)} telegram signals")
        return signals
    
    def simulate_v7_states(self):
        """
        Simulate V7 states for each trade timestamp
        
        Since we don't have historical V7 state logs,
        we'll estimate based on the v7_signals.json data
        which contains DC and action information
        """
        v7_signal_path = '/home/runner/workspace/v7-grammar-system/experiments/v7_signals.json'
        
        try:
            with open(v7_signal_path, 'r') as f:
                v7_data = json.load(f)
            
            v7_map = {s['ts']: s for s in v7_data}
            print(f"Loaded {len(v7_data)} V7 signal records")
            
            for trade in self.trades:
                dc = 0.5
                if trade.direction == 'LONG':
                    dc = 0.15
                elif trade.direction == 'SHORT':
                    dc = 0.85
                
                if dc >= 0.9 or dc <= 0.1:
                    trade.v7_state = "OBSERVE"
                else:
                    trade.v7_state = "WAIT"
                
                for ts, sig in v7_map.items():
                    if trade.timestamp in ts or ts in trade.timestamp:
                        if sig.get('action') == 'SHORT' or sig.get('action') == 'LONG':
                            trade.v7_state = "ENTER"
                        elif sig.get('dc_pre', 0.5) >= 0.8 or sig.get('dc_pre', 0.5) <= 0.2:
                            trade.v7_state = "OBSERVE"
                        else:
                            trade.v7_state = "WAIT"
                        break
            
        except Exception as e:
            print(f"Error loading V7 signals: {e}")
            print("Using heuristic state assignment...")
            
            for trade in self.trades:
                if trade.mfe > 20 and trade.mae < 15:
                    trade.v7_state = "ENTER"
                elif trade.mfe > 5:
                    trade.v7_state = "OBSERVE"
                else:
                    trade.v7_state = "WAIT"
    
    def analyze(self) -> FitnessReport:
        """Run fitness analysis"""
        
        by_state = {
            "WAIT": {"count": 0, "wins": 0, "losses": 0, "pnl": 0},
            "OBSERVE": {"count": 0, "wins": 0, "losses": 0, "pnl": 0},
            "ENTER": {"count": 0, "wins": 0, "losses": 0, "pnl": 0},
            "UNKNOWN": {"count": 0, "wins": 0, "losses": 0, "pnl": 0}
        }
        
        for trade in self.trades:
            state = trade.v7_state
            if state not in by_state:
                state = "UNKNOWN"
            
            by_state[state]["count"] += 1
            by_state[state]["pnl"] += trade.pnl
            
            if trade.is_winner():
                by_state[state]["wins"] += 1
            else:
                by_state[state]["losses"] += 1
        
        total_trades = len(self.trades)
        total_pnl = sum(t.pnl for t in self.trades)
        total_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        total_loss = sum(t.pnl for t in self.trades if t.pnl < 0)
        
        pnl_by_state = {s: d["pnl"] for s, d in by_state.items()}
        
        win_rate_by_state = {}
        for s, d in by_state.items():
            if d["count"] > 0:
                win_rate_by_state[s] = d["wins"] / d["count"] * 100
            else:
                win_rate_by_state[s] = 0
        
        concentration = {}
        for s, d in by_state.items():
            concentration[s] = {
                "trade_pct": d["count"] / max(1, total_trades) * 100,
                "pnl_pct": d["pnl"] / max(0.01, abs(total_pnl)) * 100 if total_pnl != 0 else 0
            }
        
        enter_observe_pnl = by_state["ENTER"]["pnl"] + by_state["OBSERVE"]["pnl"]
        if total_profit > 0:
            fitness_score = max(0, enter_observe_pnl / total_profit * 100)
        else:
            fitness_score = 0
        
        if fitness_score >= 80:
            verdict = "EXCELLENT - Alpha is well-aligned with V7 grammar"
        elif fitness_score >= 60:
            verdict = "GOOD - Alpha shows alignment, room for improvement"
        elif fitness_score >= 40:
            verdict = "MODERATE - Partial alignment detected"
        else:
            verdict = "POOR - Alpha not aligned with V7 grammar, need investigation"
        
        return FitnessReport(
            total_trades=total_trades,
            by_state=by_state,
            pnl_by_state=pnl_by_state,
            win_rate_by_state=win_rate_by_state,
            concentration=concentration,
            fitness_score=fitness_score,
            verdict=verdict
        )
    
    def print_report(self, report: FitnessReport):
        """Print formatted report"""
        print("=" * 70)
        print("PHASE G — ALPHA FITNESS VERIFICATION")
        print("=" * 70)
        print(f"Total Trades: {report.total_trades}")
        print()
        
        print("📊 Trades by V7 State:")
        print("-" * 50)
        for state, data in report.by_state.items():
            if data["count"] > 0:
                print(f"  {state}:")
                print(f"    Count: {data['count']} ({report.concentration[state]['trade_pct']:.1f}%)")
                print(f"    Wins/Losses: {data['wins']}/{data['losses']}")
                print(f"    Win Rate: {report.win_rate_by_state[state]:.1f}%")
                print(f"    PnL: {data['pnl']:.1f} pts")
                print()
        
        print("=" * 70)
        print("PnL CONCENTRATION ANALYSIS")
        print("=" * 70)
        total_pnl = sum(report.pnl_by_state.values())
        print(f"Total PnL: {total_pnl:.1f} pts")
        print()
        
        for state, pnl in report.pnl_by_state.items():
            if report.by_state[state]["count"] > 0:
                pct = report.concentration[state]['pnl_pct']
                bar = "█" * int(abs(pct) / 5) if pct != 0 else ""
                sign = "+" if pnl > 0 else ""
                print(f"  {state}: {sign}{pnl:.1f} pts ({pct:.1f}%) {bar}")
        
        print()
        print("=" * 70)
        print("HYPOTHESIS TEST")
        print("=" * 70)
        print("Q: 알파 수익의 80%가 ENTER+OBSERVE 구간에서 발생하는가?")
        print()
        
        enter_observe_pnl = report.pnl_by_state.get("ENTER", 0) + report.pnl_by_state.get("OBSERVE", 0)
        wait_pnl = report.pnl_by_state.get("WAIT", 0)
        
        print(f"ENTER + OBSERVE PnL: {enter_observe_pnl:.1f} pts")
        print(f"WAIT PnL: {wait_pnl:.1f} pts")
        print()
        
        print(f"🎯 Fitness Score: {report.fitness_score:.1f}/100")
        print(f"📌 Verdict: {report.verdict}")
        print("=" * 70)
    
    def save_report(self, report: FitnessReport, filepath: str = "/tmp/phase_g_fitness_report.json"):
        """Save report to JSON"""
        data = {
            "analysis_time": datetime.now().isoformat(),
            "total_trades": report.total_trades,
            "by_state": report.by_state,
            "pnl_by_state": report.pnl_by_state,
            "win_rate_by_state": report.win_rate_by_state,
            "concentration": report.concentration,
            "fitness_score": report.fitness_score,
            "verdict": report.verdict,
            "trades_detail": [
                {
                    "timestamp": t.timestamp,
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "mfe": t.mfe,
                    "mae": t.mae,
                    "pnl": t.pnl,
                    "v7_state": t.v7_state,
                    "terminated_by": t.terminated_by
                }
                for t in self.trades
            ]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"\nReport saved to: {filepath}")
        return filepath


def main():
    """Run Phase G analysis"""
    print("=" * 70)
    print("PHASE G — ALPHA FITNESS ANALYSIS")
    print("=" * 70)
    print()
    
    analyzer = AlphaFitnessAnalyzer()
    
    print("Loading alpha trade results...")
    analyzer.load_continuation_results()
    
    print("\nSimulating V7 states for each trade...")
    analyzer.simulate_v7_states()
    
    print("\nRunning fitness analysis...")
    report = analyzer.analyze()
    
    print()
    analyzer.print_report(report)
    
    analyzer.save_report(report)


if __name__ == "__main__":
    main()
