"""
Phase K — FULL CHART DATA ANALYSIS
===================================

목표: "우리 시스템이 '어떤 조건에서 무엇을 잘하고, 무엇을 일부러 못 하는지'를
       전 차트 데이터 기준으로 완전히 기술한다."

MODE = OFFLINE / READ-ONLY
ENGINE = FROZEN (Phase J-D 기준)
ALPHA = Conditional Gate (VOL only)

절대 규칙:
❌ 실시간 개입 없음
❌ 파라미터 변경 없음
❌ 임계값 튜닝 없음

출력 테이블:
A. Action 분포
B. Session Lifecycle
C. Engine Handoff Matrix
D. Alpha Effect Map
E. "의도적 실패" 확인
"""

import json
import numpy as np
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import defaultdict

import sys
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/analysis/phase_i')
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/analysis/phase_j_d')

from shadow_mode import ShadowModeAdapter
from session_orchestrator import SessionOrchestrator, OrchestratorConfig, SessionState


@dataclass
class AnalysisSession:
    """분석용 세션 레코드"""
    session_id: int
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    direction: str
    
    volatility_bucket: str = "MID"
    alpha_gate_enabled: bool = True
    alpha_bucket: str = "MID"
    force_gated: bool = False
    
    force_created: bool = False
    duration: int = 0
    hold_bars: int = 0
    force_accumulated: float = 0.0
    max_tau: int = 0
    max_force: float = 0.0
    
    exit_reason: str = ""
    pnl: float = 0.0
    
    entry_to_force: bool = False
    force_to_hold: bool = False
    hold_to_exit: bool = False


@dataclass
class FullChartStats:
    """전체 차트 통계"""
    total_candles: int = 0
    total_sessions: int = 0
    
    action_dist: Dict[str, int] = field(default_factory=dict)
    
    avg_duration: float = 0.0
    avg_hold_bars: float = 0.0
    extend_rate: float = 0.0
    exit_reasons: Dict[str, int] = field(default_factory=dict)
    
    handoff_entry_force: float = 0.0
    handoff_force_hold: float = 0.0
    handoff_alpha_block: float = 0.0
    
    alpha_gate_by_vol: Dict[str, float] = field(default_factory=dict)
    
    intentional_failures: Dict[str, int] = field(default_factory=dict)


class VolatilityTracker:
    """변동성 추적기"""
    
    def __init__(self, window: int = 20):
        self.window = window
        self.prices = []
        self.returns = []
    
    def update(self, price: float) -> str:
        self.prices.append(price)
        if len(self.prices) > 1:
            ret = (self.prices[-1] - self.prices[-2]) / self.prices[-2] if self.prices[-2] > 0 else 0
            self.returns.append(ret)
        
        if len(self.prices) > self.window:
            self.prices = self.prices[-self.window:]
        if len(self.returns) > self.window:
            self.returns = self.returns[-self.window:]
        
        if len(self.returns) < 10:
            return "MID"
        
        vol = np.std(self.returns)
        
        if vol < 0.001:
            return "LOW"
        elif vol > 0.003:
            return "HIGH"
        else:
            return "MID"


class AlphaCalculator:
    """Alpha Score 계산기"""
    
    def __init__(self):
        self.force_history = []
        self.tau_history = []
        self.dc_history = []
    
    def update(self, force: float, tau: int, dc: float):
        self.force_history.append(force)
        self.tau_history.append(tau)
        self.dc_history.append(dc)
        
        if len(self.force_history) > 50:
            self.force_history = self.force_history[-50:]
            self.tau_history = self.tau_history[-50:]
            self.dc_history = self.dc_history[-50:]
    
    def calculate_alpha_score(self) -> float:
        if len(self.force_history) < 10:
            return 0.0
        
        recent_force = self.force_history[-10:]
        force_momentum = (recent_force[-1] - recent_force[0]) / 10.0 if len(recent_force) >= 2 else 0
        
        recent_tau = self.tau_history[-10:]
        tau_stability = np.std(recent_tau) if len(recent_tau) > 1 else 0
        tau_mean = np.mean(recent_tau) if recent_tau else 0
        tau_score = tau_mean / (1 + tau_stability)
        
        recent_dc = self.dc_history[-10:]
        dc_trend = sum(1 if d > 0.5 else -1 for d in recent_dc)
        dc_strength = abs(dc_trend) / len(recent_dc) if recent_dc else 0
        
        return force_momentum * 0.4 + tau_score * 0.3 + dc_strength * 10 * 0.3


class FullChartAnalyzer:
    """
    전체 차트 데이터 분석기
    
    MODE = FROZEN
    ENGINE = Phase J-D 기준
    ALPHA = Conditional Gate (VOL only)
    """
    
    TAU_MIN = 3
    DIR_THRESHOLD = 2
    FORCE_MIN = 8.0
    MAX_SESSION_BARS = 25
    MAE_LIMIT = 30.0
    OBSERVATION_WINDOW = 2
    
    def __init__(self):
        self.config = OrchestratorConfig(
            observation_window_bars=self.OBSERVATION_WINDOW,
            force_min=self.FORCE_MIN,
            tau_min=self.TAU_MIN,
            dir_threshold=self.DIR_THRESHOLD
        )
        self.orchestrator = SessionOrchestrator(self.config)
        self.shadow = ShadowModeAdapter()
        self.vol_tracker = VolatilityTracker()
        self.alpha_calc = AlphaCalculator()
        
        self.sessions: List[AnalysisSession] = []
        self.current_session: Optional[AnalysisSession] = None
        self.session_state: Optional[SessionState] = None
        self.session_counter = 0
        
        self.action_counts = defaultdict(int)
        self.dir_history = []
        self.force_history = []
        
        self.p25 = 0
        self.p75 = 100
        
        self.vol_sessions = {"LOW": [], "MID": [], "HIGH": []}
        self.intentional_blocks = {"VOL_HIGH_NO_GATE": 0, "VOL_LOW_GATED": 0, "DC_EXTREME_WAIT": 0}
    
    def alpha_gate_enabled(self, vol_bucket: str) -> bool:
        """J-D 확정 조건부 Gate"""
        return vol_bucket in ["LOW", "MID"]
    
    def analyze(self, candles: List[Dict]) -> FullChartStats:
        print(f"\n{'='*70}")
        print("PHASE K — FULL CHART DATA ANALYSIS")
        print(f"{'='*70}")
        print(f"MODE: OFFLINE / READ-ONLY / FROZEN")
        print(f"Processing {len(candles)} candles...")
        
        self._calibrate_alpha_thresholds(candles)
        
        for i, candle in enumerate(candles):
            self._process_candle(candle, i)
        
        if self.current_session:
            self._close_session(len(candles) - 1, "END_OF_DATA")
        
        stats = self._compute_stats(len(candles))
        self._print_all_tables(stats)
        
        return stats
    
    def _calibrate_alpha_thresholds(self, candles: List[Dict]):
        """Alpha 임계값 캘리브레이션"""
        temp_calc = AlphaCalculator()
        scores = []
        
        for candle in candles:
            try:
                result = self.shadow.process(candle)
                state = result['engine']['state']
                tau = state.get('tau_hat', 0)
                force = candle.get('force_raw', 0)
                dc = state.get('dc_hat', 0.5)
                temp_calc.update(force, tau, dc)
                score = temp_calc.calculate_alpha_score()
                if score != 0:
                    scores.append(score)
            except:
                pass
        
        if scores:
            self.p25 = np.percentile(scores, 25)
            self.p75 = np.percentile(scores, 75)
        
        self.shadow = ShadowModeAdapter()
    
    def _get_alpha_bucket(self, alpha_score: float) -> str:
        if alpha_score <= self.p25:
            return "LOW"
        elif alpha_score > self.p75:
            return "HIGH"
        else:
            return "MID"
    
    def _process_candle(self, candle: Dict, bar_idx: int):
        try:
            result = self.shadow.process(candle)
        except Exception:
            self.action_counts["ERROR"] += 1
            return
        
        action = result['engine']['action'].get('action', 'WAIT')
        state = result['engine']['state']
        
        self.action_counts[action] += 1
        
        tau = state.get('tau_hat', 0)
        force_from_data = candle.get('force_raw', 0)
        force_from_state = state.get('force_hat', 0)
        force = force_from_data if abs(force_from_data) > 0.1 else force_from_state
        
        dc = state.get('dc_hat', 0.5)
        price = float(candle.get('close', 0))
        
        vol_bucket = self.vol_tracker.update(price)
        self.alpha_calc.update(force, tau, dc)
        
        self.dir_history.append(1 if dc > 0.5 else -1)
        if len(self.dir_history) > 20:
            self.dir_history = self.dir_history[-20:]
        
        dir_count = sum(self.dir_history[-5:]) if len(self.dir_history) >= 5 else 0
        
        if dc < 0.1 or dc > 0.9:
            self.intentional_blocks["DC_EXTREME_WAIT"] += 1
        
        if self.current_session is None:
            if tau >= self.TAU_MIN and abs(dir_count) >= self.DIR_THRESHOLD:
                self._open_session(bar_idx, price, dir_count, vol_bucket)
        else:
            self.session_state = self.orchestrator.update_state(
                self.session_state, tau, force, dir_count
            )
            
            alpha_enabled = self.alpha_gate_enabled(self.current_session.volatility_bucket)
            
            effective_force = force
            if alpha_enabled and self.current_session.alpha_bucket == "LOW":
                effective_force = 0
                self.current_session.force_gated = True
                self.intentional_blocks["VOL_LOW_GATED"] += 1
            
            if not alpha_enabled:
                self.intentional_blocks["VOL_HIGH_NO_GATE"] += 1
            
            self.force_history.append(effective_force)
            self.current_session.force_accumulated += effective_force
            self.current_session.max_tau = max(self.current_session.max_tau, tau)
            self.current_session.max_force = max(self.current_session.max_force, effective_force)
            
            if not self.session_state.can_exit:
                self.current_session.hold_bars += 1
            
            if effective_force >= self.FORCE_MIN:
                self.current_session.force_created = True
                self.current_session.entry_to_force = True
            
            if self.current_session.force_created and self.current_session.hold_bars > 0:
                self.current_session.force_to_hold = True
            
            should_exit, exit_reason = self._check_exit_conditions(
                tau, effective_force, dir_count, price, bar_idx
            )
            
            if should_exit:
                if self.current_session.hold_bars > 0:
                    self.current_session.hold_to_exit = True
                self._close_session(bar_idx, exit_reason)
    
    def _open_session(self, bar_idx: int, price: float, dir_count: int, vol_bucket: str):
        self.session_counter += 1
        self.force_history = []
        
        alpha_score = self.alpha_calc.calculate_alpha_score()
        alpha_bucket = self._get_alpha_bucket(alpha_score)
        alpha_enabled = self.alpha_gate_enabled(vol_bucket)
        
        self.current_session = AnalysisSession(
            session_id=self.session_counter,
            entry_bar=bar_idx,
            exit_bar=bar_idx,
            entry_price=price,
            exit_price=price,
            direction="HIGH" if dir_count > 0 else "LOW",
            volatility_bucket=vol_bucket,
            alpha_gate_enabled=alpha_enabled,
            alpha_bucket=alpha_bucket
        )
        
        self.session_state = SessionState(session_id=self.session_counter)
    
    def _close_session(self, bar_idx: int, exit_reason: str):
        if not self.current_session:
            return
        
        self.current_session.exit_bar = bar_idx
        self.current_session.duration = bar_idx - self.current_session.entry_bar
        self.current_session.exit_reason = exit_reason
        
        if self.current_session.direction == "HIGH":
            self.current_session.pnl = self.current_session.exit_price - self.current_session.entry_price
        else:
            self.current_session.pnl = self.current_session.entry_price - self.current_session.exit_price
        
        self.vol_sessions[self.current_session.volatility_bucket].append(self.current_session)
        self.sessions.append(self.current_session)
        self.current_session = None
        self.session_state = None
    
    def _check_exit_conditions(self, tau: int, force: float, dir_count: int, 
                                price: float, bar_idx: int) -> Tuple[bool, str]:
        if not self.session_state.can_exit:
            return False, ""
        
        duration = bar_idx - self.current_session.entry_bar
        
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
    
    def _compute_stats(self, total_candles: int) -> FullChartStats:
        stats = FullChartStats()
        stats.total_candles = total_candles
        stats.total_sessions = len(self.sessions)
        
        stats.action_dist = dict(self.action_counts)
        
        if self.sessions:
            stats.avg_duration = np.mean([s.duration for s in self.sessions])
            stats.avg_hold_bars = np.mean([s.hold_bars for s in self.sessions])
            stats.extend_rate = sum(1 for s in self.sessions if s.duration > 15) / len(self.sessions)
            
            for s in self.sessions:
                stats.exit_reasons[s.exit_reason] = stats.exit_reasons.get(s.exit_reason, 0) + 1
            
            entry_force_success = sum(1 for s in self.sessions if s.entry_to_force)
            force_hold_success = sum(1 for s in self.sessions if s.force_to_hold)
            alpha_blocks = sum(1 for s in self.sessions if s.force_gated)
            
            stats.handoff_entry_force = entry_force_success / len(self.sessions)
            stats.handoff_force_hold = force_hold_success / len(self.sessions) if entry_force_success > 0 else 0
            stats.handoff_alpha_block = alpha_blocks / len(self.sessions)
            
            for vol_bucket in ["LOW", "MID", "HIGH"]:
                bucket_sessions = self.vol_sessions[vol_bucket]
                if bucket_sessions:
                    gated = sum(1 for s in bucket_sessions if s.force_gated)
                    stats.alpha_gate_by_vol[vol_bucket] = gated / len(bucket_sessions)
                else:
                    stats.alpha_gate_by_vol[vol_bucket] = 0.0
        
        stats.intentional_failures = dict(self.intentional_blocks)
        
        return stats
    
    def _print_all_tables(self, stats: FullChartStats):
        print("\n" + "=" * 70)
        print("📊 A. ACTION DISTRIBUTION")
        print("=" * 70)
        total_actions = sum(stats.action_dist.values())
        print(f"{'Action':<20} {'Count':>10} {'Rate':>10}")
        print("-" * 40)
        for action, count in sorted(stats.action_dist.items(), key=lambda x: -x[1]):
            rate = count / total_actions * 100 if total_actions > 0 else 0
            print(f"{action:<20} {count:>10} {rate:>9.1f}%")
        
        print("\n" + "=" * 70)
        print("📊 B. SESSION LIFECYCLE")
        print("=" * 70)
        print(f"{'Metric':<30} {'Value':>15}")
        print("-" * 45)
        print(f"{'Total Sessions':<30} {stats.total_sessions:>15}")
        print(f"{'Avg Duration (bars)':<30} {stats.avg_duration:>15.1f}")
        print(f"{'Avg HOLD bars':<30} {stats.avg_hold_bars:>15.1f}")
        print(f"{'EXTEND Rate (>15 bars)':<30} {stats.extend_rate*100:>14.1f}%")
        print()
        print("EXIT_REASON Distribution:")
        for reason, count in sorted(stats.exit_reasons.items(), key=lambda x: -x[1]):
            rate = count / stats.total_sessions * 100 if stats.total_sessions > 0 else 0
            print(f"  {reason:<25} {count:>8} ({rate:>5.1f}%)")
        
        print("\n" + "=" * 70)
        print("📊 C. ENGINE HANDOFF MATRIX")
        print("=" * 70)
        print(f"{'Handoff':<30} {'Success Rate':>15}")
        print("-" * 45)
        print(f"{'Entry → Force':<30} {stats.handoff_entry_force*100:>14.1f}%")
        print(f"{'Force → HOLD':<30} {stats.handoff_force_hold*100:>14.1f}%")
        print(f"{'Alpha Gate → Block':<30} {stats.handoff_alpha_block*100:>14.1f}%")
        
        print("\n" + "=" * 70)
        print("📊 D. ALPHA EFFECT MAP (VOL BUCKET)")
        print("=" * 70)
        print(f"{'Vol Bucket':<15} {'Gate Rate':>15} {'Expected':>15} {'Match':>10}")
        print("-" * 55)
        expected = {"LOW": 0.60, "MID": 0.25, "HIGH": 0.00}
        for bucket in ["LOW", "MID", "HIGH"]:
            actual = stats.alpha_gate_by_vol.get(bucket, 0)
            exp = expected[bucket]
            match = "✅" if abs(actual - exp) < 0.15 else "⚠️"
            print(f"{bucket:<15} {actual*100:>14.1f}% {exp*100:>14.1f}% {match:>10}")
        
        print("\n" + "=" * 70)
        print("📊 E. INTENTIONAL FAILURES (설계된 실패)")
        print("=" * 70)
        print(f"{'Condition':<35} {'Count':>10}")
        print("-" * 45)
        for condition, count in stats.intentional_failures.items():
            print(f"{condition:<35} {count:>10}")
        
        print("\n" + "=" * 70)
        print("🎯 SUMMARY")
        print("=" * 70)
        print(f"Total Candles Processed: {stats.total_candles}")
        print(f"Total Sessions Generated: {stats.total_sessions}")
        print(f"Session Rate: {stats.total_sessions / stats.total_candles * 100:.3f}%")
        print(f"Entry→Force Success: {stats.handoff_entry_force*100:.1f}%")
        print(f"Alpha Block Rate: {stats.handoff_alpha_block*100:.1f}%")


def load_force_data() -> List[Dict]:
    """Force 데이터 로드"""
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
    
    return candles


def main():
    print("=" * 70)
    print("PHASE K — FULL CHART DATA ANALYSIS")
    print("=" * 70)
    print(f"\nAnalysis Time: {datetime.now().isoformat()}")
    print("\n목표: 전 차트 데이터 기준 시스템 상태 완전 기술")
    print("모드: OFFLINE / READ-ONLY / FROZEN")
    
    candles = load_force_data()
    print(f"\nLoaded {len(candles)} candles")
    
    analyzer = FullChartAnalyzer()
    stats = analyzer.analyze(candles)
    
    report = {
        "analysis_time": datetime.now().isoformat(),
        "phase": "K",
        "mode": "OFFLINE_FROZEN",
        "total_candles": stats.total_candles,
        "total_sessions": stats.total_sessions,
        "action_dist": stats.action_dist,
        "session_lifecycle": {
            "avg_duration": stats.avg_duration,
            "avg_hold_bars": stats.avg_hold_bars,
            "extend_rate": stats.extend_rate,
            "exit_reasons": stats.exit_reasons
        },
        "engine_handoff": {
            "entry_to_force": stats.handoff_entry_force,
            "force_to_hold": stats.handoff_force_hold,
            "alpha_block": stats.handoff_alpha_block
        },
        "alpha_effect_map": stats.alpha_gate_by_vol,
        "intentional_failures": stats.intentional_failures,
        "sessions": [asdict(s) for s in analyzer.sessions]
    }
    
    report_path = '/tmp/phase_k_full_analysis.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📄 Full report saved to: {report_path}")
    
    return stats, analyzer.sessions


if __name__ == "__main__":
    main()
