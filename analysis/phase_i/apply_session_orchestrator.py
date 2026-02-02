"""
Phase I — APPLY SESSION ORCHESTRATOR
=====================================

역할: Session Orchestrator 규칙을 적용하여 세션 재구성

Phase H와 동일한 데이터, 동일한 엔진, 
단 하나 다른 것: EXIT 허용 시점
"""

import sys
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/analysis/phase_i')

from shadow_mode import ShadowModeAdapter
from session_orchestrator import SessionOrchestrator, OrchestratorConfig, SessionState


@dataclass
class PhaseISession:
    """Phase I 세션 레코드"""
    session_id: int
    start_bar: int
    end_bar: int
    entry_price: float
    exit_price: float
    direction: str
    
    duration_bars: int = 0
    force_accumulated: float = 0.0
    avg_force: float = 0.0
    max_tau: int = 0
    
    hold_bars: int = 0
    hold_extend_bars: int = 0
    observation_window_blocks: int = 0
    
    exit_reason: str = ""
    exit_allowed_by: str = ""
    pnl: float = 0.0
    
    bar_details: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)


class PhaseIAnalyzer:
    """Phase I 분석기 — Session Orchestrator 적용"""
    
    MAE_LIMIT = 25.0
    MAX_SESSION_BARS = 30
    TAU_MIN = 5
    DIR_THRESHOLD = 3
    FORCE_MIN = 10.0
    
    def __init__(self, config: OrchestratorConfig = None):
        self.config = config or OrchestratorConfig()
        self.orchestrator = SessionOrchestrator(self.config)
        self.shadow = ShadowModeAdapter()
        
        self.sessions: List[PhaseISession] = []
        self.current_session: Optional[PhaseISession] = None
        self.session_state: Optional[SessionState] = None
        self.session_counter = 0
        
        self.dir_history = []
        self.force_history = []
    
    def analyze(self, candles: List[Dict]) -> List[PhaseISession]:
        """Phase I 분석 실행"""
        print(f"\n{'='*60}")
        print("PHASE I — SESSION ORCHESTRATOR ANALYSIS")
        print(f"{'='*60}")
        print(f"Config: {self.config.to_dict()}")
        print(f"Processing {len(candles)} candles...")
        
        for i, candle in enumerate(candles):
            self._process_candle(candle, i)
        
        if self.current_session:
            self._close_session(len(candles) - 1, "END_OF_DATA")
        
        self._print_summary()
        return self.sessions
    
    def _process_candle(self, candle: Dict, bar_idx: int):
        """단일 캔들 처리"""
        try:
            result = self.shadow.process(candle)
        except Exception:
            return
        
        action = result['engine']['action'].get('action', 'WAIT')
        state = result['engine']['state']
        
        tau = state.get('tau_hat', 0)
        force_from_data = candle.get('force_raw', 0)
        force_from_state = state.get('force_hat', 0)
        force = force_from_data if abs(force_from_data) > 0.1 else force_from_state
        
        dc = state.get('dc_hat', 0.5)
        price = float(candle.get('close', 0))
        
        self.dir_history.append(1 if dc > 0.5 else -1)
        if len(self.dir_history) > 20:
            self.dir_history = self.dir_history[-20:]
        
        dir_count = sum(self.dir_history[-5:]) if len(self.dir_history) >= 5 else 0
        
        if self.current_session is None:
            if action == "ENTER" and tau >= self.TAU_MIN and abs(dir_count) >= self.DIR_THRESHOLD:
                self._open_session(bar_idx, price, dir_count)
        else:
            self.session_state = self.orchestrator.update_state(
                self.session_state, tau, force, dir_count
            )
            
            self.force_history.append(force)
            self.current_session.force_accumulated += force
            self.current_session.max_tau = max(self.current_session.max_tau, tau)
            
            if not self.session_state.can_exit:
                self.current_session.hold_bars += 1
                if "OBSERVATION_WINDOW" in self.session_state.hold_reason:
                    self.current_session.observation_window_blocks += 1
            
            if self.orchestrator.check_hold_extend(self.session_state):
                self.current_session.hold_extend_bars += 1
            
            self._record_bar(bar_idx, tau, force, dir_count, price)
            
            should_exit, exit_reason = self._check_exit_conditions(
                tau, force, dir_count, price, bar_idx
            )
            
            if should_exit:
                self._close_session(bar_idx, exit_reason)
    
    def _open_session(self, bar_idx: int, price: float, dir_count: int):
        """세션 시작"""
        self.session_counter += 1
        self.force_history = []
        
        self.current_session = PhaseISession(
            session_id=self.session_counter,
            start_bar=bar_idx,
            end_bar=bar_idx,
            entry_price=price,
            exit_price=price,
            direction="HIGH" if dir_count > 0 else "LOW"
        )
        
        self.session_state = SessionState(session_id=self.session_counter)
    
    def _close_session(self, bar_idx: int, exit_reason: str):
        """세션 종료"""
        if not self.current_session:
            return
        
        self.current_session.end_bar = bar_idx
        self.current_session.duration_bars = bar_idx - self.current_session.start_bar
        self.current_session.exit_reason = exit_reason
        
        if self.force_history:
            self.current_session.avg_force = sum(self.force_history) / len(self.force_history)
        
        if self.current_session.direction == "HIGH":
            self.current_session.pnl = self.current_session.exit_price - self.current_session.entry_price
        else:
            self.current_session.pnl = self.current_session.entry_price - self.current_session.exit_price
        
        self.sessions.append(self.current_session)
        self.current_session = None
        self.session_state = None
    
    def _check_exit_conditions(self, tau: int, force: float, dir_count: int, 
                                price: float, bar_idx: int) -> Tuple[bool, str]:
        """EXIT 조건 확인 (Orchestrator 규칙 적용)"""
        
        if not self.session_state.can_exit:
            return False, ""
        
        duration = bar_idx - self.current_session.start_bar
        
        if duration >= self.MAX_SESSION_BARS:
            return True, "MAX_BARS"
        
        entry_price = self.current_session.entry_price
        if self.current_session.direction == "HIGH":
            mae = max(0, entry_price - price)
        else:
            mae = max(0, price - entry_price)
        
        if mae > self.MAE_LIMIT:
            return True, "MAE_EXCESS"
        
        if self.session_state.last_tau < self.TAU_MIN and force < self.FORCE_MIN / 2:
            return True, "CONDITIONS_EXHAUSTED"
        
        return False, ""
    
    def _record_bar(self, bar_idx: int, tau: int, force: float, dir_count: int, price: float):
        """바 기록"""
        if self.current_session:
            self.current_session.bar_details.append({
                "bar_idx": bar_idx,
                "session_bar": len(self.current_session.bar_details),
                "tau": tau,
                "force": force,
                "force_accumulated": self.current_session.force_accumulated,
                "dir_count": dir_count,
                "price": price,
                "can_exit": self.session_state.can_exit,
                "hold_reason": self.session_state.hold_reason,
                "rules_blocking": self.session_state.rules_blocking_exit
            })
    
    def _print_summary(self):
        """요약 출력"""
        print(f"\n📊 Phase I Summary:")
        print(f"  Total Sessions: {len(self.sessions)}")
        
        if self.sessions:
            avg_duration = sum(s.duration_bars for s in self.sessions) / len(self.sessions)
            avg_force = sum(s.force_accumulated for s in self.sessions) / len(self.sessions)
            win_rate = sum(1 for s in self.sessions if s.pnl > 0) / len(self.sessions) * 100
            total_hold = sum(s.hold_bars for s in self.sessions)
            total_obs_blocks = sum(s.observation_window_blocks for s in self.sessions)
            
            print(f"  Avg Duration: {avg_duration:.1f} bars")
            print(f"  Avg Force Accumulated: {avg_force:.1f}")
            print(f"  Win Rate: {win_rate:.1f}%")
            print(f"  Total HOLD bars: {total_hold}")
            print(f"  Observation Window Blocks: {total_obs_blocks}")
        
        print(f"\n📋 Orchestrator Statistics:")
        stats = self.orchestrator.get_statistics()
        for rule, count in stats['rule_blocks'].items():
            print(f"  {rule}: {count} blocks")


def load_force_data() -> List[Dict]:
    """Force 데이터 로드 (Phase H와 동일)"""
    force_path = '/home/runner/workspace/v7-grammar-system/experiments/force_readings.json'
    with open(force_path, 'r') as f:
        force_data = json.load(f)
    
    candles = []
    for rec in force_data:
        price = rec.get('mid_price', 0)
        if price > 0:
            force_ratio = rec.get('force_ratio_20', 1.0)
            force_value = (force_ratio - 1.0) * 100
            
            candle = {
                'time': rec['ts'],
                'open': price - 2,
                'high': price + 10,
                'low': price - 10,
                'close': price,
                'volume': 1000,
                'force_raw': force_value,
                'force_ratio': force_ratio,
                'dc_pre': rec.get('dc_pre', 0.5),
                'avg_delta': rec.get('avg_delta', 0)
            }
            candles.append(candle)
    
    print(f"Loaded {len(candles)} candles")
    return candles


def main():
    candles = load_force_data()
    
    analyzer = PhaseIAnalyzer()
    sessions = analyzer.analyze(candles)
    
    output_path = '/tmp/phase_i_sessions.json'
    with open(output_path, 'w') as f:
        json.dump([s.to_dict() for s in sessions], f, indent=2, default=str)
    
    print(f"\nSessions saved to: {output_path}")
    return sessions


if __name__ == "__main__":
    main()
