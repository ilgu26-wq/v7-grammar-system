"""
Phase J-D — CONDITIONAL ALPHA GATE
===================================

목적: Phase J-C에서 "관측된 사실"을 코드로 고정

Alpha Gate 조건 (J-C 결과 기반):
- VOL_LOW:  Alpha Gate ON (60% 효과)
- VOL_MID:  Alpha Gate ON (25% 효과)
- VOL_HIGH: Alpha Gate OFF (0% 효과)

핵심 원칙:
❌ Entry 조건 변경
❌ Session 구조 변경
❌ Exit 조건 변경
✅ Alpha는 Gate only
✅ Alpha ON/OFF는 관측값 기반

검증 체크리스트:
- 세션 수: Baseline과 동일
- EXIT_REASON: 언어 유지
- Gate 비율: J-C 결과와 일치
- 구조 규칙(H-1~H-5): 100% 유지
"""

import json
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from collections import defaultdict

import sys
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/analysis/phase_i')

from shadow_mode import ShadowModeAdapter
from session_orchestrator import SessionOrchestrator, OrchestratorConfig, SessionState


@dataclass
class ConditionalSession:
    """Conditional Alpha Gate 세션 레코드"""
    session_id: int
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    direction: str
    
    volatility_bucket: str = "MID"
    alpha_gate_enabled: bool = True
    alpha_score: float = 0.0
    alpha_bucket: str = "MID"
    force_gated: bool = False
    
    force_created: bool = False
    duration: int = 0
    hold_bars: int = 0
    force_accumulated: float = 0.0
    max_tau: int = 0
    
    exit_reason: str = ""
    pnl: float = 0.0


class VolatilityTracker:
    """변동성 추적기 (실시간)"""
    
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
        
        alpha_score = (
            force_momentum * 0.4 +
            tau_score * 0.3 +
            dc_strength * 10 * 0.3
        )
        
        return alpha_score


class ConditionalAlphaGateAnalyzer:
    """
    Conditional Alpha Gate 분석기
    
    핵심: J-C 결과를 코드로 고정
    - VOL_LOW/MID: Alpha Gate ON
    - VOL_HIGH: Alpha Gate OFF
    """
    
    TAU_MIN = 3
    DIR_THRESHOLD = 2
    FORCE_MIN = 8.0
    MAX_SESSION_BARS = 25
    MAE_LIMIT = 30.0
    OBSERVATION_WINDOW = 2
    
    def __init__(self, mode: str = "conditional"):
        self.mode = mode
        
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
        
        self.sessions: List[ConditionalSession] = []
        self.current_session: Optional[ConditionalSession] = None
        self.session_state: Optional[SessionState] = None
        self.session_counter = 0
        
        self.dir_history = []
        self.force_history = []
        
        self.all_alpha_scores = []
        self.p25 = 0
        self.p75 = 100
    
    def should_enable_alpha_gate(self, vol_bucket: str) -> bool:
        """J-C 결과 기반 Alpha Gate 조건"""
        if self.mode == "always_on":
            return True
        elif self.mode == "always_off":
            return False
        else:
            return vol_bucket in ["LOW", "MID"]
    
    def analyze(self, candles: List[Dict]) -> List[ConditionalSession]:
        print(f"\n{'='*60}")
        print("PHASE J-D — CONDITIONAL ALPHA GATE")
        print(f"{'='*60}")
        print(f"Mode: {self.mode}")
        print(f"Processing {len(candles)} candles...")
        
        self._calibrate_alpha_thresholds(candles)
        
        for i, candle in enumerate(candles):
            self._process_candle(candle, i)
        
        if self.current_session:
            self._close_session(len(candles) - 1, "END_OF_DATA")
        
        self._print_summary()
        
        return self.sessions
    
    def _calibrate_alpha_thresholds(self, candles: List[Dict]):
        """Alpha 임계값 사전 캘리브레이션"""
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
            return
        
        action = result['engine']['action'].get('action', 'WAIT')
        state = result['engine']['state']
        
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
        
        if self.current_session is None:
            if tau >= self.TAU_MIN and abs(dir_count) >= self.DIR_THRESHOLD:
                self._open_session(bar_idx, price, dir_count, vol_bucket)
        else:
            self.session_state = self.orchestrator.update_state(
                self.session_state, tau, force, dir_count
            )
            
            alpha_enabled = self.should_enable_alpha_gate(self.current_session.volatility_bucket)
            
            effective_force = force
            if alpha_enabled and self.current_session.alpha_bucket == "LOW":
                effective_force = 0
                self.current_session.force_gated = True
            
            self.force_history.append(effective_force)
            self.current_session.force_accumulated += effective_force
            self.current_session.max_tau = max(self.current_session.max_tau, tau)
            
            if not self.session_state.can_exit:
                self.current_session.hold_bars += 1
            
            if effective_force >= self.FORCE_MIN:
                self.current_session.force_created = True
            
            should_exit, exit_reason = self._check_exit_conditions(
                tau, effective_force, dir_count, price, bar_idx
            )
            
            if should_exit:
                self._close_session(bar_idx, exit_reason)
    
    def _open_session(self, bar_idx: int, price: float, dir_count: int, vol_bucket: str):
        self.session_counter += 1
        self.force_history = []
        
        alpha_score = self.alpha_calc.calculate_alpha_score()
        alpha_bucket = self._get_alpha_bucket(alpha_score)
        alpha_enabled = self.should_enable_alpha_gate(vol_bucket)
        
        self.current_session = ConditionalSession(
            session_id=self.session_counter,
            entry_bar=bar_idx,
            exit_bar=bar_idx,
            entry_price=price,
            exit_price=price,
            direction="HIGH" if dir_count > 0 else "LOW",
            volatility_bucket=vol_bucket,
            alpha_gate_enabled=alpha_enabled,
            alpha_score=alpha_score,
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
    
    def _print_summary(self):
        print(f"\n📊 Phase J-D Summary ({self.mode}):")
        print(f"  Total Sessions: {len(self.sessions)}")
        
        if self.sessions:
            vol_dist = {"LOW": 0, "MID": 0, "HIGH": 0}
            gated_by_vol = {"LOW": 0, "MID": 0, "HIGH": 0}
            total_by_vol = {"LOW": 0, "MID": 0, "HIGH": 0}
            
            for s in self.sessions:
                vol_dist[s.volatility_bucket] += 1
                total_by_vol[s.volatility_bucket] += 1
                if s.force_gated:
                    gated_by_vol[s.volatility_bucket] += 1
            
            print(f"\n📋 Sessions by Volatility:")
            for vol, count in vol_dist.items():
                gated = gated_by_vol[vol]
                rate = gated / count * 100 if count > 0 else 0
                enabled = self.should_enable_alpha_gate(vol)
                status = "ON" if enabled else "OFF"
                print(f"  {vol}: {count} sessions, {gated} gated ({rate:.1f}%) [Gate: {status}]")


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
    candles = load_force_data()
    print(f"Loaded {len(candles)} candles")
    
    print("\n" + "=" * 70)
    print("BASELINE (Alpha Always OFF)")
    print("=" * 70)
    baseline = ConditionalAlphaGateAnalyzer(mode="always_off")
    baseline_sessions = baseline.analyze(candles)
    
    print("\n" + "=" * 70)
    print("CONDITIONAL (J-C Based: LOW/MID=ON, HIGH=OFF)")
    print("=" * 70)
    conditional = ConditionalAlphaGateAnalyzer(mode="conditional")
    conditional_sessions = conditional.analyze(candles)
    
    print("\n" + "=" * 70)
    print("ALWAYS ON (All Volatility)")
    print("=" * 70)
    always_on = ConditionalAlphaGateAnalyzer(mode="always_on")
    always_on_sessions = always_on.analyze(candles)
    
    output = '/tmp/phase_j_d_results.json'
    with open(output, 'w') as f:
        json.dump({
            "baseline": [asdict(s) for s in baseline_sessions],
            "conditional": [asdict(s) for s in conditional_sessions],
            "always_on": [asdict(s) for s in always_on_sessions]
        }, f, indent=2)
    
    print(f"\nResults saved to: {output}")
    
    return baseline_sessions, conditional_sessions, always_on_sessions


if __name__ == "__main__":
    main()
