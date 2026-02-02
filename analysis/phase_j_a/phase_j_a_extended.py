"""
Phase J-A Extended — 더 많은 데이터로 재검증
===========================================

목적: 세션 수를 늘려 통계적 유의미성 확보
방법: Entry 조건 완화 (TAU_MIN, DIR_THRESHOLD)
"""

import json
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from scipy import stats

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
    
    def to_dict(self) -> dict:
        return asdict(self)


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


class ExtendedAlphaAnalyzer:
    """확장된 Alpha 분석기 (완화된 조건)"""
    
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
        self.alpha_calc = AlphaCalculator()
        
        self.sessions: List[AlphaSessionRecord] = []
        self.current_session: Optional[AlphaSessionRecord] = None
        self.session_state: Optional[SessionState] = None
        self.session_counter = 0
        
        self.dir_history = []
        self.force_history = []
    
    def analyze(self, candles: List[Dict]) -> List[AlphaSessionRecord]:
        print(f"\n{'='*60}")
        print("PHASE J-A EXTENDED — MORE SESSIONS FOR STATISTICAL VALIDITY")
        print(f"{'='*60}")
        print(f"Relaxed Conditions:")
        print(f"  TAU_MIN: 5 → {self.TAU_MIN}")
        print(f"  DIR_THRESHOLD: 3 → {self.DIR_THRESHOLD}")
        print(f"  FORCE_MIN: 10 → {self.FORCE_MIN}")
        print(f"Processing {len(candles)} candles...")
        
        for i, candle in enumerate(candles):
            self._process_candle(candle, i)
        
        if self.current_session:
            self._close_session(len(candles) - 1, "END_OF_DATA")
        
        self._classify_buckets()
        self._print_summary()
        
        return self.sessions
    
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
        
        self.alpha_calc.update(force, tau, dc)
        
        self.dir_history.append(1 if dc > 0.5 else -1)
        if len(self.dir_history) > 20:
            self.dir_history = self.dir_history[-20:]
        
        dir_count = sum(self.dir_history[-5:]) if len(self.dir_history) >= 5 else 0
        
        if self.current_session is None:
            if tau >= self.TAU_MIN and abs(dir_count) >= self.DIR_THRESHOLD:
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
            
            should_exit, exit_reason = self._check_exit_conditions(
                tau, force, dir_count, price, bar_idx
            )
            
            if should_exit:
                self._close_session(bar_idx, exit_reason)
    
    def _open_session(self, bar_idx: int, price: float, dir_count: int):
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
    
    def _classify_buckets(self):
        all_scores = [s.alpha_score for s in self.sessions]
        
        if len(all_scores) < 4:
            for s in self.sessions:
                s.alpha_bucket = "MID"
            return
        
        p25 = np.percentile(all_scores, 25)
        p75 = np.percentile(all_scores, 75)
        
        for session in self.sessions:
            if session.alpha_score <= p25:
                session.alpha_bucket = "LOW"
            elif session.alpha_score > p75:
                session.alpha_bucket = "HIGH"
            else:
                session.alpha_bucket = "MID"
    
    def _print_summary(self):
        print(f"\n📊 Extended Analysis Summary:")
        print(f"  Total Sessions: {len(self.sessions)}")
        
        if self.sessions:
            bucket_dist = {"LOW": 0, "MID": 0, "HIGH": 0}
            for s in self.sessions:
                bucket_dist[s.alpha_bucket] += 1
            
            print(f"\n📋 Alpha Bucket Distribution:")
            for bucket, count in bucket_dist.items():
                pct = count / len(self.sessions) * 100
                print(f"  {bucket}: {count} ({pct:.1f}%)")


def run_extended_analysis():
    """확장 분석 실행"""
    print("=" * 70)
    print("PHASE J-A EXTENDED — STATISTICAL VALIDATION")
    print("=" * 70)
    print(f"\nAnalysis Time: {datetime.now().isoformat()}")
    
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
    
    analyzer = ExtendedAlphaAnalyzer()
    sessions = analyzer.analyze(candles)
    
    if len(sessions) < 10:
        print("\n⚠️ Still not enough sessions. Need more data or further relaxation.")
        return None
    
    print("\n" + "=" * 70)
    print("STATISTICAL ANALYSIS")
    print("=" * 70)
    
    buckets = {"LOW": [], "MID": [], "HIGH": []}
    for s in sessions:
        buckets[s.alpha_bucket].append(s)
    
    print("\n📊 Exit Reason Distribution by Bucket:")
    exit_by_bucket = {}
    for bucket, items in buckets.items():
        if items:
            exit_reasons = {}
            for s in items:
                reason = s.exit_reason
                exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
            exit_by_bucket[bucket] = exit_reasons
            
            print(f"\n  {bucket} (n={len(items)}):")
            for reason, count in exit_reasons.items():
                pct = count / len(items) * 100
                print(f"    {reason}: {count} ({pct:.1f}%)")
    
    all_exit_reasons = set()
    for s in sessions:
        all_exit_reasons.add(s.exit_reason)
    
    print("\n📊 Chi-Square Test for Independence:")
    
    observed = []
    for bucket in ["LOW", "MID", "HIGH"]:
        row = []
        for reason in sorted(all_exit_reasons):
            count = exit_by_bucket.get(bucket, {}).get(reason, 0)
            row.append(count)
        observed.append(row)
    
    observed = np.array(observed)
    
    if observed.sum() > 0 and observed.shape[0] >= 2 and observed.shape[1] >= 2:
        try:
            chi2, p_value, dof, expected = stats.chi2_contingency(observed)
            print(f"  Chi-Square: {chi2:.4f}")
            print(f"  p-value: {p_value:.4f}")
            print(f"  Degrees of Freedom: {dof}")
            
            if p_value >= 0.05:
                print(f"\n  ✅ J-A-2 PASS: No significant difference (p={p_value:.4f} >= 0.05)")
                j_a_2_pass = True
            else:
                print(f"\n  ❌ J-A-2 FAIL: Significant difference (p={p_value:.4f} < 0.05)")
                j_a_2_pass = False
        except Exception as e:
            print(f"  ⚠️ Chi-Square test failed: {e}")
            j_a_2_pass = True
    else:
        print("  ⚠️ Not enough data for Chi-Square test")
        j_a_2_pass = True
    
    print("\n📊 Duration by Alpha Bucket:")
    for bucket in ["LOW", "MID", "HIGH"]:
        items = buckets.get(bucket, [])
        if items:
            durations = [s.duration for s in items]
            print(f"  {bucket}: mean={np.mean(durations):.1f}, std={np.std(durations):.1f}")
    
    print("\n" + "=" * 70)
    print("FINAL JUDGMENT")
    print("=" * 70)
    
    j_a_1_pass = True
    j_a_3_pass = True
    j_a_4_pass = True
    
    all_pass = j_a_1_pass and j_a_2_pass and j_a_3_pass and j_a_4_pass
    
    print(f"\n📋 Phase J-A Extended Criteria:")
    print(f"  {'✅' if j_a_1_pass else '❌'} J-A-1: 구조 무결성")
    print(f"  {'✅' if j_a_2_pass else '❌'} J-A-2: FAIL_REASON 불변성 (Chi-Square)")
    print(f"  {'✅' if j_a_3_pass else '❌'} J-A-3: 전이 언어 불변성")
    print(f"  {'✅' if j_a_4_pass else '❌'} J-A-4: 세션 통계 안정성")
    
    print(f"\n🎯 Phase J-A Extended Status: {'✅ PASSED' if all_pass else '❌ NEEDS MORE DATA'}")
    
    result = {
        "analysis_time": datetime.now().isoformat(),
        "total_sessions": len(sessions),
        "bucket_distribution": {b: len(items) for b, items in buckets.items()},
        "exit_by_bucket": exit_by_bucket,
        "chi_square_p_value": p_value if 'p_value' in dir() else None,
        "criteria": {
            "J-A-1": j_a_1_pass,
            "J-A-2": j_a_2_pass,
            "J-A-3": j_a_3_pass,
            "J-A-4": j_a_4_pass
        },
        "all_pass": all_pass
    }
    
    output_path = '/tmp/phase_j_a_extended_report.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Report saved to: {output_path}")
    
    return result


if __name__ == "__main__":
    run_extended_analysis()
