"""
V7 State → Profit Analyzer
목표: "ENTER는 OBSERVE보다 통계적으로 우월한가?"

핵심 질문:
1. 상태별 MFE (Maximum Favorable Excursion) 분포
2. 상태별 MAE (Maximum Adverse Excursion) 분포  
3. 상태별 n-bar forward return
4. 변동성 대비 기대값

중요: 알파 없이 순수 가격 행동만으로 검증
→ "가격 그 자체가 알파 후보가 되는지" 확인
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import json
from datetime import datetime


class StateRegion(Enum):
    WAIT = "WAIT"
    OBSERVE = "OBSERVE"  
    ENTER = "ENTER"


@dataclass
class BarData:
    """Single bar data for analysis"""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    state: str  # WAIT/OBSERVE/ENTER
    dc: float
    tau: int
    force: float
    delta: float
    direction: str


@dataclass
class RegionStats:
    """Statistics for a state region"""
    state: str
    sample_count: int = 0
    
    mfe_sum: float = 0.0
    mae_sum: float = 0.0
    
    forward_3_sum: float = 0.0
    forward_5_sum: float = 0.0
    forward_10_sum: float = 0.0
    
    forward_3_count: int = 0
    forward_5_count: int = 0
    forward_10_count: int = 0
    
    wins_3: int = 0
    wins_5: int = 0
    wins_10: int = 0
    
    def avg_mfe(self) -> float:
        return self.mfe_sum / max(1, self.sample_count)
    
    def avg_mae(self) -> float:
        return self.mae_sum / max(1, self.sample_count)
    
    def avg_forward_3(self) -> float:
        return self.forward_3_sum / max(1, self.forward_3_count)
    
    def avg_forward_5(self) -> float:
        return self.forward_5_sum / max(1, self.forward_5_count)
    
    def avg_forward_10(self) -> float:
        return self.forward_10_sum / max(1, self.forward_10_count)
    
    def win_rate_3(self) -> float:
        return self.wins_3 / max(1, self.forward_3_count) * 100
    
    def win_rate_5(self) -> float:
        return self.wins_5 / max(1, self.forward_5_count) * 100
    
    def win_rate_10(self) -> float:
        return self.wins_10 / max(1, self.forward_10_count) * 100
    
    def to_dict(self) -> Dict:
        return {
            "state": self.state,
            "sample_count": self.sample_count,
            "mfe": {
                "avg": round(self.avg_mfe(), 2),
                "total": round(self.mfe_sum, 2)
            },
            "mae": {
                "avg": round(self.avg_mae(), 2),
                "total": round(self.mae_sum, 2)
            },
            "forward_return": {
                "3_bar": {
                    "avg": round(self.avg_forward_3(), 2),
                    "count": self.forward_3_count,
                    "win_rate": f"{self.win_rate_3():.1f}%"
                },
                "5_bar": {
                    "avg": round(self.avg_forward_5(), 2),
                    "count": self.forward_5_count,
                    "win_rate": f"{self.win_rate_5():.1f}%"
                },
                "10_bar": {
                    "avg": round(self.avg_forward_10(), 2),
                    "count": self.forward_10_count,
                    "win_rate": f"{self.win_rate_10():.1f}%"
                }
            },
            "edge_ratio": round(self.avg_mfe() / max(0.01, self.avg_mae()), 2)
        }


class StateProfitAnalyzer:
    """
    Analyze profit potential by V7 state
    
    Core Question:
    "ENTER는 OBSERVE보다 통계적으로 우월한가?"
    
    검증 방법:
    1. 각 상태 진입 시점에서 n-bar forward return 측정
    2. MFE/MAE로 "얼마나 좋았고 얼마나 나빴는지" 측정
    3. Edge Ratio = MFE/MAE로 상태별 품질 비교
    """
    
    def __init__(self):
        self.bar_history: List[BarData] = []
        self.stats: Dict[str, RegionStats] = {
            "WAIT": RegionStats("WAIT"),
            "OBSERVE": RegionStats("OBSERVE"),
            "ENTER": RegionStats("ENTER")
        }
        self.analysis_ready = False
    
    def add_bar(self, bar: BarData):
        """Add bar to history"""
        self.bar_history.append(bar)
        self.stats[bar.state].sample_count += 1
        self.analysis_ready = False
    
    def add_bar_from_dict(self, data: Dict, state: str, dc: float = 0.5, 
                          tau: int = 0, force: float = 0, delta: float = 0,
                          direction: str = "NONE"):
        """Add bar from dictionary format"""
        bar = BarData(
            timestamp=data.get('time', data.get('timestamp', '')),
            open=float(data.get('open', 0)),
            high=float(data.get('high', 0)),
            low=float(data.get('low', 0)),
            close=float(data.get('close', 0)),
            state=state,
            dc=dc,
            tau=tau,
            force=force,
            delta=delta,
            direction=direction
        )
        self.add_bar(bar)
    
    def analyze(self):
        """Run full analysis on collected data"""
        if len(self.bar_history) < 15:
            return
        
        for s in self.stats.values():
            s.mfe_sum = 0
            s.mae_sum = 0
            s.forward_3_sum = 0
            s.forward_5_sum = 0
            s.forward_10_sum = 0
            s.forward_3_count = 0
            s.forward_5_count = 0
            s.forward_10_count = 0
            s.wins_3 = 0
            s.wins_5 = 0
            s.wins_10 = 0
        
        for i, bar in enumerate(self.bar_history):
            if bar.state not in self.stats:
                continue
            
            stat = self.stats[bar.state]
            entry_price = bar.close
            is_long = bar.direction == "HIGH"
            
            if i + 10 < len(self.bar_history):
                future_bars = self.bar_history[i+1:i+11]
                
                mfe, mae = self._calc_mfe_mae(entry_price, future_bars, is_long)
                stat.mfe_sum += mfe
                stat.mae_sum += mae
            
            if i + 3 < len(self.bar_history):
                ret_3 = self._calc_return(entry_price, 
                                          self.bar_history[i+3].close, 
                                          is_long)
                stat.forward_3_sum += ret_3
                stat.forward_3_count += 1
                if ret_3 > 0:
                    stat.wins_3 += 1
            
            if i + 5 < len(self.bar_history):
                ret_5 = self._calc_return(entry_price,
                                          self.bar_history[i+5].close,
                                          is_long)
                stat.forward_5_sum += ret_5
                stat.forward_5_count += 1
                if ret_5 > 0:
                    stat.wins_5 += 1
            
            if i + 10 < len(self.bar_history):
                ret_10 = self._calc_return(entry_price,
                                           self.bar_history[i+10].close,
                                           is_long)
                stat.forward_10_sum += ret_10
                stat.forward_10_count += 1
                if ret_10 > 0:
                    stat.wins_10 += 1
        
        self.analysis_ready = True
    
    def _calc_mfe_mae(self, entry: float, future_bars: List[BarData], 
                      is_long: bool) -> Tuple[float, float]:
        """Calculate MFE and MAE"""
        mfe = 0.0
        mae = 0.0
        
        for bar in future_bars:
            if is_long:
                favorable = bar.high - entry
                adverse = entry - bar.low
            else:
                favorable = entry - bar.low
                adverse = bar.high - entry
            
            mfe = max(mfe, favorable)
            mae = max(mae, adverse)
        
        return mfe, mae
    
    def _calc_return(self, entry: float, exit: float, is_long: bool) -> float:
        """Calculate directional return"""
        if is_long:
            return exit - entry
        else:
            return entry - exit
    
    def get_report(self) -> Dict:
        """Generate analysis report"""
        if not self.analysis_ready:
            self.analyze()
        
        observe_stats = self.stats["OBSERVE"]
        enter_stats = self.stats["ENTER"]
        
        observe_edge = observe_stats.avg_mfe() / max(0.01, observe_stats.avg_mae())
        enter_edge = enter_stats.avg_mfe() / max(0.01, enter_stats.avg_mae())
        
        is_enter_superior = (
            enter_stats.avg_forward_5() > observe_stats.avg_forward_5() and
            enter_edge > observe_edge
        )
        
        return {
            "analysis_time": datetime.now().isoformat(),
            "total_bars": len(self.bar_history),
            "states": {
                state: stat.to_dict() 
                for state, stat in self.stats.items()
            },
            "hypothesis_test": {
                "question": "ENTER는 OBSERVE보다 통계적으로 우월한가?",
                "observe_edge_ratio": round(observe_edge, 2),
                "enter_edge_ratio": round(enter_edge, 2),
                "observe_5bar_return": round(observe_stats.avg_forward_5(), 2),
                "enter_5bar_return": round(enter_stats.avg_forward_5(), 2),
                "verdict": "YES" if is_enter_superior else "NO",
                "conclusion": self._generate_conclusion(is_enter_superior, 
                                                        observe_stats, 
                                                        enter_stats)
            }
        }
    
    def _generate_conclusion(self, is_superior: bool, 
                             observe: RegionStats, 
                             enter: RegionStats) -> str:
        """Generate human-readable conclusion"""
        if enter.sample_count < 5:
            return "ENTER 샘플 부족 - 더 많은 데이터 필요"
        
        if observe.sample_count < 10:
            return "OBSERVE 샘플 부족 - 더 많은 데이터 필요"
        
        if is_superior:
            return (f"ENTER가 우월함: "
                    f"Edge Ratio {enter.avg_mfe()/max(0.01,enter.avg_mae()):.2f} > "
                    f"{observe.avg_mfe()/max(0.01,observe.avg_mae()):.2f}, "
                    f"5-bar return {enter.avg_forward_5():.1f} > {observe.avg_forward_5():.1f}")
        else:
            return (f"ENTER 우월성 미확인: "
                    f"Edge Ratio {enter.avg_mfe()/max(0.01,enter.avg_mae()):.2f} vs "
                    f"{observe.avg_mfe()/max(0.01,observe.avg_mae()):.2f}")
    
    def print_report(self):
        """Print formatted report"""
        report = self.get_report()
        
        print("=" * 70)
        print("V7 STATE → PROFIT ANALYSIS REPORT")
        print("=" * 70)
        print(f"Total Bars: {report['total_bars']}")
        print()
        
        for state in ["WAIT", "OBSERVE", "ENTER"]:
            s = report['states'][state]
            print(f"--- {state} ---")
            print(f"  Samples: {s['sample_count']}")
            print(f"  MFE avg: {s['mfe']['avg']:.2f} pts")
            print(f"  MAE avg: {s['mae']['avg']:.2f} pts")
            print(f"  Edge Ratio: {s['edge_ratio']:.2f}")
            print(f"  5-bar return: {s['forward_return']['5_bar']['avg']:.2f} pts "
                  f"(win {s['forward_return']['5_bar']['win_rate']})")
            print()
        
        print("=" * 70)
        print("HYPOTHESIS TEST")
        print("=" * 70)
        h = report['hypothesis_test']
        print(f"Q: {h['question']}")
        print(f"OBSERVE Edge: {h['observe_edge_ratio']}")
        print(f"ENTER Edge: {h['enter_edge_ratio']}")
        print(f"Verdict: {h['verdict']}")
        print(f"Conclusion: {h['conclusion']}")
        print("=" * 70)
    
    def save_report(self, filepath: str = "/tmp/state_profit_report.json"):
        """Save report to JSON file"""
        report = self.get_report()
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        return filepath


def test_analyzer():
    """Test with synthetic data"""
    import random
    
    analyzer = StateProfitAnalyzer()
    
    price = 21000.0
    states = ["WAIT", "WAIT", "WAIT", "OBSERVE", "OBSERVE", "ENTER"]
    
    for i in range(200):
        state = random.choice(states)
        direction = random.choice(["HIGH", "LOW"])
        
        change = random.gauss(0, 2)
        
        if state == "ENTER":
            if direction == "HIGH":
                change += 0.5
            else:
                change -= 0.5
        
        price += change
        
        bar = BarData(
            timestamp=f"2026-01-30T{10+i//60:02d}:{i%60:02d}:00Z",
            open=price - 0.5,
            high=price + abs(random.gauss(0, 3)),
            low=price - abs(random.gauss(0, 3)),
            close=price,
            state=state,
            dc=random.uniform(0.1, 0.9),
            tau=random.randint(0, 10),
            force=random.uniform(20, 80),
            delta=random.uniform(-30, 30),
            direction=direction
        )
        analyzer.add_bar(bar)
    
    analyzer.print_report()
    
    filepath = analyzer.save_report()
    print(f"\nReport saved to: {filepath}")


if __name__ == "__main__":
    test_analyzer()
