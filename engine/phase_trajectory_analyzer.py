"""
Phase G′ — State Session Trajectory Analyzer
ENTER 이후를 "4차원 상태 세션"으로 재해석

핵심 변화:
- 기존: 엔트리 1회 = 트레이드 1회
- 신규: ENTER → EXIT 전체 = State Session

4차원 Phase 좌표계:
- θ(t): Grammar state depth (WAIT/OBSERVE/ENTER/HOLD)
- τ(t): 상태 지속 시간
- F(t): Force / Energy
- A(t): Action layer (진입/유지/확장)

핵심 지표:
1. Phase Trajectory Length (τ 분포)
2. Integrated Energy = ∑ F(t) over session
3. Action Layer 전이 확률
4. Tornado/SMALL 발생 위치
"""

import json
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum

sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')

from shadow_mode import ShadowModeAdapter


class SessionState(Enum):
    IDLE = "IDLE"
    ENTER = "ENTER"
    HOLD = "HOLD"
    HOLD_SMALL = "HOLD_SMALL"
    HOLD_EXTEND = "HOLD_EXTEND"
    EXIT = "EXIT"


FORCE_MIN = 10.0
TAU_DECAY_THRESHOLD = 2


@dataclass
class PhasePoint:
    """Single point in 4D phase space"""
    bar_idx: int
    timestamp: str
    theta: str      # Grammar state (WAIT/OBSERVE/ENTER)
    tau: int        # State duration
    force: float    # Force value
    action: str     # Current action layer
    price: float
    dc: float
    delta: float


@dataclass
class StateSession:
    """ENTER → EXIT as single analysis unit"""
    session_id: int
    start_bar: int
    start_time: str
    entry_price: float
    direction: str
    
    trajectory: List[PhasePoint] = field(default_factory=list)
    end_bar: int = 0
    end_time: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    
    def duration(self) -> int:
        return len(self.trajectory)
    
    def max_tau(self) -> int:
        return max((p.tau for p in self.trajectory), default=0)
    
    def integrated_energy(self) -> float:
        return sum(p.force for p in self.trajectory)
    
    def avg_force(self) -> float:
        if not self.trajectory:
            return 0
        return sum(p.force for p in self.trajectory) / len(self.trajectory)
    
    def mfe(self) -> float:
        if not self.trajectory:
            return 0
        if self.direction == "HIGH":
            return max(p.price - self.entry_price for p in self.trajectory)
        else:
            return max(self.entry_price - p.price for p in self.trajectory)
    
    def mae(self) -> float:
        if not self.trajectory:
            return 0
        if self.direction == "HIGH":
            return max(self.entry_price - p.price for p in self.trajectory)
        else:
            return max(p.price - self.entry_price for p in self.trajectory)
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "start_bar": self.start_bar,
            "start_time": self.start_time,
            "end_bar": self.end_bar,
            "duration": self.duration(),
            "direction": self.direction,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "max_tau": self.max_tau(),
            "integrated_energy": round(self.integrated_energy(), 2),
            "avg_force": round(self.avg_force(), 2),
            "mfe": round(self.mfe(), 2),
            "mae": round(self.mae(), 2),
            "trajectory_length": len(self.trajectory)
        }


class PhaseTrajectoryAnalyzer:
    """
    Analyze ENTER → EXIT as 4D phase trajectories
    
    핵심 질문:
    1. ENTER 이후 τ가 얼마나 오래 유지되는가?
    2. Force × τ 누적(Integrated Energy)은 얼마인가?
    3. Action Layer 전이 패턴은 어떠한가?
    """
    
    MAX_SESSION_BARS = 50
    
    def __init__(self):
        self.shadow = ShadowModeAdapter(encoder_name=None)
        self.sessions: List[StateSession] = []
        self.current_session: Optional[StateSession] = None
        self.session_counter = 0
        
        self.transitions: Dict[str, Dict[str, int]] = {}
        self.all_points: List[PhasePoint] = []
    
    def process_candle(self, candle: Dict, bar_idx: int) -> Optional[PhasePoint]:
        """Process single candle through V7 engine"""
        try:
            result = self.shadow.process(candle)
        except Exception as e:
            return None
        
        action = result['engine']['action'].get('action', 'WAIT')
        state = result['engine']['state']
        
        point = PhasePoint(
            bar_idx=bar_idx,
            timestamp=candle.get('time', ''),
            theta=action,
            tau=state.get('tau_hat', 0),
            force=state.get('force_hat', 0),
            action=action,
            price=float(candle.get('close', 0)),
            dc=state.get('dc_hat', 0.5),
            delta=state.get('delta_hat', 0)
        )
        
        self.all_points.append(point)
        return point
    
    def update_session(self, point: PhasePoint, direction: str):
        """
        Update session state based on current point
        
        핵심 변경: ENTER → HOLD (default)
        HOLD는 "결정"이 아니라 "기본 지속 상태"
        """
        
        if point.theta == "ENTER" and self.current_session is None:
            self.session_counter += 1
            self.current_session = StateSession(
                session_id=self.session_counter,
                start_bar=point.bar_idx,
                start_time=point.timestamp,
                entry_price=point.price,
                direction=direction
            )
            point.action = "ENTER"
            self.current_session.trajectory.append(point)
            return
        
        if self.current_session is not None:
            prev_point = self.current_session.trajectory[-1] if self.current_session.trajectory else None
            
            hold_state = self._determine_hold_state(point, prev_point)
            point.action = hold_state
            
            self.current_session.trajectory.append(point)
            
            should_exit, exit_reason = self._check_exit_conditions(point, prev_point)
            
            if should_exit:
                self.current_session.end_bar = point.bar_idx
                self.current_session.end_time = point.timestamp
                self.current_session.exit_price = point.price
                self.current_session.exit_reason = exit_reason
                self.sessions.append(self.current_session)
                self.current_session = None
        
        elif point.theta == "OBSERVE":
            pass
    
    def _determine_hold_state(self, point: PhasePoint, prev_point: Optional[PhasePoint]) -> str:
        """
        Determine HOLD sub-state based on physics
        
        HOLD 유지 조건 (의사결정 아님, 물리 조건):
        - τ 유지 or 증가 → HOLD 유지
        - Force >= Force_min → HOLD 유지
        - Force 급증 + τ 유지 → HOLD_EXTEND
        - τ >= 6 이후 소폭 하락 → HOLD_SMALL 가능
        """
        if prev_point is None:
            return "HOLD"
        
        tau_change = point.tau - prev_point.tau
        force_change = point.force - prev_point.force
        
        if point.force >= FORCE_MIN * 2 and tau_change >= 0:
            return "HOLD_EXTEND"
        
        if point.tau >= 6 and abs(tau_change) <= 1 and point.force >= FORCE_MIN:
            if self.current_session and self.current_session.mfe() > 5:
                return "HOLD_SMALL"
        
        if tau_change >= -TAU_DECAY_THRESHOLD and point.force >= FORCE_MIN:
            return "HOLD"
        
        return "HOLD"
    
    def _check_exit_conditions(self, point: PhasePoint, prev_point: Optional[PhasePoint]) -> Tuple[bool, str]:
        """
        Check exit conditions
        
        EXIT 조건:
        - τ 급락 (감쇠)
        - Force < Force_min
        - MAX_BARS 초과
        - MAE 초과
        """
        if len(self.current_session.trajectory) >= self.MAX_SESSION_BARS:
            return True, "MAX_BARS"
        
        if self.current_session.mae() > 25:
            return True, "MAE_EXCESS"
        
        if prev_point:
            tau_drop = prev_point.tau - point.tau
            if tau_drop >= 3 and point.force < FORCE_MIN:
                return True, "TAU_COLLAPSE"
        
        if point.force < FORCE_MIN / 2 and len(self.current_session.trajectory) > 3:
            return True, "FORCE_EXHAUSTED"
        
        if self.current_session.mfe() > 20 and point.force < FORCE_MIN:
            return True, "PROFIT_SECURED"
        
        return False, ""
    
    def record_transition(self, from_state: str, to_state: str):
        """Record state transition"""
        if from_state not in self.transitions:
            self.transitions[from_state] = {}
        if to_state not in self.transitions[from_state]:
            self.transitions[from_state][to_state] = 0
        self.transitions[from_state][to_state] += 1
    
    def run_analysis(self, candles: List[Dict]) -> Dict:
        """Run full trajectory analysis on candle data"""
        
        print(f"Processing {len(candles)} candles...")
        
        prev_state = None
        for i, candle in enumerate(candles):
            point = self.process_candle(candle, i)
            
            if point is None:
                continue
            
            direction = "HIGH" if point.dc < 0.3 else "LOW" if point.dc > 0.7 else "NONE"
            self.update_session(point, direction)
            
            if prev_state and prev_state != point.theta:
                self.record_transition(prev_state, point.theta)
            prev_state = point.theta
        
        if self.current_session is not None:
            self.current_session.exit_reason = "END_OF_DATA"
            self.sessions.append(self.current_session)
            self.current_session = None
        
        return self.generate_report()
    
    def _count_hold_substates(self) -> Dict:
        """Count HOLD sub-states across all sessions"""
        substates = {"ENTER": 0, "HOLD": 0, "HOLD_SMALL": 0, "HOLD_EXTEND": 0}
        for session in self.sessions:
            for point in session.trajectory:
                if point.action in substates:
                    substates[point.action] += 1
        return substates
    
    def generate_report(self) -> Dict:
        """Generate comprehensive analysis report"""
        
        if not self.sessions:
            return {"error": "No sessions found"}
        
        durations = [s.duration() for s in self.sessions]
        taus = [s.max_tau() for s in self.sessions]
        energies = [s.integrated_energy() for s in self.sessions]
        mfes = [s.mfe() for s in self.sessions]
        maes = [s.mae() for s in self.sessions]
        
        avg_duration = sum(durations) / len(durations)
        avg_tau = sum(taus) / len(taus)
        avg_energy = sum(energies) / len(energies)
        avg_mfe = sum(mfes) / len(mfes)
        avg_mae = sum(maes) / len(maes)
        
        winners = [s for s in self.sessions if s.mfe() > s.mae()]
        win_rate = len(winners) / len(self.sessions) * 100
        
        tau_distribution = {
            "short_0_5": len([t for t in taus if t <= 5]),
            "medium_6_10": len([t for t in taus if 6 <= t <= 10]),
            "long_11_plus": len([t for t in taus if t > 10])
        }
        
        exit_reasons = {}
        for s in self.sessions:
            r = s.exit_reason
            exit_reasons[r] = exit_reasons.get(r, 0) + 1
        
        transition_probs = {}
        for from_s, to_dict in self.transitions.items():
            total = sum(to_dict.values())
            transition_probs[from_s] = {
                to_s: round(count / total * 100, 1)
                for to_s, count in to_dict.items()
            }
        
        hold_substates = self._count_hold_substates()
        
        report = {
            "analysis_time": datetime.now().isoformat(),
            "total_candles": len(self.all_points),
            "total_sessions": len(self.sessions),
            "session_metrics": {
                "avg_duration_bars": round(avg_duration, 1),
                "avg_max_tau": round(avg_tau, 1),
                "avg_integrated_energy": round(avg_energy, 1),
                "avg_mfe": round(avg_mfe, 2),
                "avg_mae": round(avg_mae, 2),
                "session_win_rate": f"{win_rate:.1f}%"
            },
            "hold_substates": hold_substates,
            "tau_distribution": tau_distribution,
            "exit_reasons": exit_reasons,
            "transition_probabilities": transition_probs,
            "sessions_detail": [s.to_dict() for s in self.sessions[:20]],
            "hypothesis_answers": {
                "Q1_tau_persistence": self._answer_tau_question(taus),
                "Q2_integrated_energy": self._answer_energy_question(energies),
                "Q3_action_transitions": self._answer_transition_question(),
                "Q4_hold_structure": self._answer_hold_question(hold_substates)
            }
        }
        
        return report
    
    def _answer_tau_question(self, taus: List[int]) -> Dict:
        """Q1: ENTER 이후 τ가 얼마나 오래 유지되는가?"""
        if not taus:
            return {"answer": "No data"}
        
        avg_tau = sum(taus) / len(taus)
        long_sessions = len([t for t in taus if t > 10])
        long_pct = long_sessions / len(taus) * 100
        
        return {
            "avg_max_tau": round(avg_tau, 1),
            "long_session_pct": f"{long_pct:.1f}%",
            "interpretation": "GOOD" if avg_tau > 5 else "NEEDS_WORK"
        }
    
    def _answer_energy_question(self, energies: List[float]) -> Dict:
        """Q2: Force × τ 누적은 충분한가?"""
        if not energies:
            return {"answer": "No data"}
        
        avg_energy = sum(energies) / len(energies)
        high_energy = len([e for e in energies if e > 100])
        high_pct = high_energy / len(energies) * 100
        
        return {
            "avg_integrated_energy": round(avg_energy, 1),
            "high_energy_session_pct": f"{high_pct:.1f}%",
            "interpretation": "GOOD" if avg_energy > 50 else "NEEDS_WORK"
        }
    
    def _answer_transition_question(self) -> Dict:
        """Q3: Action Layer 전이 패턴은 어떠한가?"""
        if "ENTER" not in self.transitions:
            return {"answer": "No ENTER transitions found"}
        
        enter_next = self.transitions.get("ENTER", {})
        
        return {
            "enter_transitions": enter_next,
            "interpretation": "Shows state flow patterns"
        }
    
    def _answer_hold_question(self, hold_substates: Dict) -> Dict:
        """Q4: HOLD 구조가 제대로 형성되는가?"""
        total_hold = hold_substates.get("HOLD", 0) + hold_substates.get("HOLD_SMALL", 0) + hold_substates.get("HOLD_EXTEND", 0)
        enter_count = hold_substates.get("ENTER", 0)
        
        if enter_count == 0:
            return {"answer": "No ENTER events"}
        
        avg_hold_per_enter = total_hold / enter_count
        
        return {
            "hold_substates": hold_substates,
            "avg_hold_bars_per_enter": round(avg_hold_per_enter, 1),
            "has_extend": hold_substates.get("HOLD_EXTEND", 0) > 0,
            "has_small": hold_substates.get("HOLD_SMALL", 0) > 0,
            "interpretation": "GOOD" if avg_hold_per_enter >= 5 else "NEEDS_MORE_HOLD"
        }
    
    def print_report(self, report: Dict):
        """Print formatted report"""
        print("=" * 70)
        print("PHASE G′ — STATE SESSION TRAJECTORY ANALYSIS")
        print("=" * 70)
        print(f"Total Candles: {report['total_candles']}")
        print(f"Total Sessions: {report['total_sessions']}")
        print()
        
        m = report['session_metrics']
        print("📊 Session Metrics:")
        print(f"  Avg Duration: {m['avg_duration_bars']} bars")
        print(f"  Avg Max τ: {m['avg_max_tau']}")
        print(f"  Avg Integrated Energy: {m['avg_integrated_energy']}")
        print(f"  Avg MFE: {m['avg_mfe']} pts")
        print(f"  Avg MAE: {m['avg_mae']} pts")
        print(f"  Session Win Rate: {m['session_win_rate']}")
        print()
        
        print("📈 τ Distribution:")
        for k, v in report['tau_distribution'].items():
            print(f"  {k}: {v}")
        print()
        
        print("🔗 HOLD Sub-States:")
        for k, v in report['hold_substates'].items():
            print(f"  {k}: {v}")
        print()
        
        print("🚪 Exit Reasons:")
        for k, v in report['exit_reasons'].items():
            print(f"  {k}: {v}")
        print()
        
        print("🔄 Transition Probabilities:")
        for from_s, to_dict in report['transition_probabilities'].items():
            print(f"  From {from_s}:")
            for to_s, prob in sorted(to_dict.items(), key=lambda x: -x[1])[:3]:
                print(f"    → {to_s}: {prob}%")
        print()
        
        print("=" * 70)
        print("HYPOTHESIS ANSWERS")
        print("=" * 70)
        
        for q, answer in report['hypothesis_answers'].items():
            print(f"\n{q}:")
            for k, v in answer.items():
                print(f"  {k}: {v}")
        
        print("=" * 70)
    
    def save_report(self, report: Dict, filepath: str = "/tmp/phase_trajectory_report.json"):
        """Save report to JSON"""
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nReport saved to: {filepath}")
        return filepath


def load_chart_data() -> List[Dict]:
    """Load chart data from available sources"""
    
    force_path = '/home/runner/workspace/v7-grammar-system/experiments/force_readings.json'
    with open(force_path, 'r') as f:
        force_data = json.load(f)
    
    candles = []
    for f in force_data:
        price = f.get('mid_price', 0)
        if price > 0:
            candle = {
                'time': f['ts'],
                'open': price - 2,
                'high': price + 10,
                'low': price - 10,
                'close': price,
                'volume': 1000
            }
            candles.append(candle)
    
    print(f"Loaded {len(candles)} candles from force_readings.json")
    return candles


def main():
    """Run Phase Trajectory Analysis"""
    print("=" * 70)
    print("PHASE G′ — STATE SESSION TRAJECTORY ANALYZER")
    print("=" * 70)
    print()
    
    print("Loading chart data...")
    candles = load_chart_data()
    
    if len(candles) < 100:
        print("Not enough data for analysis")
        return
    
    analyzer = PhaseTrajectoryAnalyzer()
    
    print("\nRunning trajectory analysis...")
    report = analyzer.run_analysis(candles)
    
    print()
    analyzer.print_report(report)
    analyzer.save_report(report)


if __name__ == "__main__":
    main()
