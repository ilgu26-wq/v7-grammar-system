"""
Phase J-A — INJECT ALPHA READONLY
=================================

목적: 알파를 관측 변수로만 삽입
❌ 의사결정 영향 없음
❌ Force 생성 영향 없음
✅ Alpha_Score 계산 + 로깅만

핵심 원칙:
"Alpha observation does not contaminate decision structure"
"""

import json
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime

import sys
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/analysis/phase_i')

from shadow_mode import ShadowModeAdapter
from session_orchestrator import SessionOrchestrator, OrchestratorConfig, SessionState


@dataclass
class AlphaSessionRecord:
    """Alpha 관측이 포함된 세션 레코드"""
    session_id: int
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    direction: str
    
    alpha_score: float = 0.0
    alpha_bucket: str = "MID"
    
    force_created: bool = False
    duration: int = 0
    hold_bars: int = 0
    force_accumulated: float = 0.0
    max_tau: int = 0
    
    exit_reason: str = ""
    pnl: float = 0.0
    
    bar_records: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)


class AlphaCalculator:
    """
    Alpha Score 계산기 (Read-Only)
    
    Alpha는 Entry 시점에 한 번만 계산
    Session 동안 고정 (재계산 금지)
    """
    
    def __init__(self):
        self.force_history = []
        self.tau_history = []
        self.dc_history = []
    
    def update(self, force: float, tau: int, dc: float):
        """히스토리 업데이트"""
        self.force_history.append(force)
        self.tau_history.append(tau)
        self.dc_history.append(dc)
        
        if len(self.force_history) > 50:
            self.force_history = self.force_history[-50:]
            self.tau_history = self.tau_history[-50:]
            self.dc_history = self.dc_history[-50:]
    
    def calculate_alpha_score(self) -> float:
        """
        Alpha Score 계산
        
        구성요소:
        1. Force momentum (최근 변화)
        2. τ stability (안정도)
        3. DC trend (방향성 강도)
        """
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


def classify_alpha_bucket(alpha_score: float, all_scores: List[float]) -> str:
    """Alpha Bucket 분류 (사후 분석용)"""
    if not all_scores:
        return "MID"
    
    p25 = np.percentile(all_scores, 25)
    p75 = np.percentile(all_scores, 75)
    
    if alpha_score <= p25:
        return "LOW"
    elif alpha_score > p75:
        return "HIGH"
    else:
        return "MID"


class AlphaInjectionAnalyzer:
    """
    Alpha Injection Analyzer (Read-Only Mode)
    
    핵심: Session Orchestrator 로직은 100% 동일
    추가: Alpha_Score 관측 및 로깅만
    """
    
    TAU_MIN = 5
    DIR_THRESHOLD = 3
    FORCE_MIN = 10.0
    MAX_SESSION_BARS = 30
    MAE_LIMIT = 25.0
    
    def __init__(self):
        self.config = OrchestratorConfig()
        self.orchestrator = SessionOrchestrator(self.config)
        self.shadow = ShadowModeAdapter()
        self.alpha_calc = AlphaCalculator()
        
        self.sessions: List[AlphaSessionRecord] = []
        self.current_session: Optional[AlphaSessionRecord] = None
        self.session_state: Optional[SessionState] = None
        self.session_counter = 0
        
        self.dir_history = []
        self.force_history = []
    
    def analyze(self, candles: List[Dict]) -> List[AlphaSessionRecord]:
        """Phase J-A 분석 실행"""
        print(f"\n{'='*60}")
        print("PHASE J-A — ALPHA INJECTION DRY-RUN")
        print(f"{'='*60}")
        print(f"Mode: READ-ONLY (No decision impact)")
        print(f"Processing {len(candles)} candles...")
        
        for i, candle in enumerate(candles):
            self._process_candle(candle, i)
        
        if self.current_session:
            self._close_session(len(candles) - 1, "END_OF_DATA")
        
        self._classify_buckets()
        self._print_summary()
        
        return self.sessions
    
    def _process_candle(self, candle: Dict, bar_idx: int):
        """단일 캔들 처리 (Phase I와 동일 + Alpha 관측)"""
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
        
        self.alpha_calc.update(force, tau, dc)
        
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
            
            if force >= self.FORCE_MIN:
                self.current_session.force_created = True
            
            self._record_bar(bar_idx, tau, force, dir_count, price)
            
            should_exit, exit_reason = self._check_exit_conditions(
                tau, force, dir_count, price, bar_idx
            )
            
            if should_exit:
                self._close_session(bar_idx, exit_reason)
    
    def _open_session(self, bar_idx: int, price: float, dir_count: int):
        """세션 시작 + Alpha 계산"""
        self.session_counter += 1
        self.force_history = []
        
        alpha_score = self.alpha_calc.calculate_alpha_score()
        
        self.current_session = AlphaSessionRecord(
            session_id=self.session_counter,
            entry_bar=bar_idx,
            exit_bar=bar_idx,
            entry_price=price,
            exit_price=price,
            direction="HIGH" if dir_count > 0 else "LOW",
            alpha_score=alpha_score
        )
        
        self.session_state = SessionState(session_id=self.session_counter)
    
    def _close_session(self, bar_idx: int, exit_reason: str):
        """세션 종료"""
        if not self.current_session:
            return
        
        self.current_session.exit_bar = bar_idx
        self.current_session.duration = bar_idx - self.current_session.entry_bar
        self.current_session.exit_reason = exit_reason
        self.current_session.exit_price = self.current_session.bar_records[-1]['price'] if self.current_session.bar_records else self.current_session.entry_price
        
        if self.current_session.direction == "HIGH":
            self.current_session.pnl = self.current_session.exit_price - self.current_session.entry_price
        else:
            self.current_session.pnl = self.current_session.entry_price - self.current_session.exit_price
        
        self.sessions.append(self.current_session)
        self.current_session = None
        self.session_state = None
    
    def _check_exit_conditions(self, tau: int, force: float, dir_count: int, 
                                price: float, bar_idx: int):
        """EXIT 조건 확인 (Phase I와 동일)"""
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
    
    def _record_bar(self, bar_idx: int, tau: int, force: float, dir_count: int, price: float):
        """바 기록"""
        if self.current_session:
            self.current_session.bar_records.append({
                "t": bar_idx,
                "session_id": self.current_session.session_id,
                "tau": tau,
                "force": force,
                "price": price,
                "alpha_score": self.current_session.alpha_score
            })
    
    def _classify_buckets(self):
        """Alpha Bucket 분류 (사후)"""
        all_scores = [s.alpha_score for s in self.sessions]
        
        for session in self.sessions:
            session.alpha_bucket = classify_alpha_bucket(session.alpha_score, all_scores)
    
    def _print_summary(self):
        """요약 출력"""
        print(f"\n📊 Phase J-A Summary:")
        print(f"  Total Sessions: {len(self.sessions)}")
        
        if self.sessions:
            bucket_dist = {"LOW": 0, "MID": 0, "HIGH": 0}
            for s in self.sessions:
                bucket_dist[s.alpha_bucket] += 1
            
            print(f"\n📋 Alpha Bucket Distribution:")
            for bucket, count in bucket_dist.items():
                pct = count / len(self.sessions) * 100
                print(f"  {bucket}: {count} ({pct:.1f}%)")
            
            print(f"\n📋 Alpha Score Range:")
            scores = [s.alpha_score for s in self.sessions]
            print(f"  Min: {min(scores):.2f}")
            print(f"  Max: {max(scores):.2f}")
            print(f"  Mean: {np.mean(scores):.2f}")


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
    
    print(f"Loaded {len(candles)} candles")
    return candles


def main():
    candles = load_force_data()
    
    analyzer = AlphaInjectionAnalyzer()
    sessions = analyzer.analyze(candles)
    
    output_path = '/tmp/phase_j_a_sessions.json'
    with open(output_path, 'w') as f:
        json.dump([s.to_dict() for s in sessions], f, indent=2, default=str)
    
    print(f"\nSessions saved to: {output_path}")
    return sessions


if __name__ == "__main__":
    main()
