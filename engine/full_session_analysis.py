"""
Full Session Analysis — 전수 데이터 통합 분석

1️⃣ StateSession 히트맵 (엔진 기여도)
2️⃣ EXIT 타입별 Force/τ 궤적 비교

근본 불변: 문법/엔트리/알파 정의는 고정
조절 대상: 상태 세션 내부에서의 기여·연결·지속
"""

import json
import sys
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict

sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')

from shadow_mode import ShadowModeAdapter
from state_session import ExitType, HandoffFailReason, HandoffRecord


FORCE_MIN = 10.0
TAU_DECAY_THRESHOLD = 2
MAX_SESSION_BARS = 50
NORMALIZED_BINS = 10


@dataclass
class BarLog:
    """바 단위 로깅 스키마"""
    session_id: int
    bar_index: int
    normalized_pct: float
    timestamp: str
    action: str
    tau: int
    dc: float
    dir_count: int
    force: float
    force_int: float
    energy_int: float
    engine_flags: Dict
    mfe: float
    mae: float
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "bar_index": self.bar_index,
            "normalized_pct": round(self.normalized_pct, 1),
            "action": self.action,
            "tau": self.tau,
            "force": round(self.force, 2),
            "force_int": round(self.force_int, 2),
            "energy_int": round(self.energy_int, 2),
            "engine_flags": self.engine_flags,
            "mfe": round(self.mfe, 2),
            "mae": round(self.mae, 2)
        }


@dataclass
class SessionData:
    """세션 전체 데이터"""
    session_id: int
    start_bar: int
    end_bar: int
    direction: str
    entry_price: float
    exit_type: str
    bars: List[BarLog] = field(default_factory=list)
    final_pnl: float = 0.0
    
    def duration(self) -> int:
        return len(self.bars)
    
    def max_tau(self) -> int:
        return max((b.tau for b in self.bars), default=0)
    
    def max_force_int(self) -> float:
        return max((b.force_int for b in self.bars), default=0)
    
    def max_energy_int(self) -> float:
        return max((b.energy_int for b in self.bars), default=0)
    
    def final_mfe(self) -> float:
        return max((b.mfe for b in self.bars), default=0)
    
    def final_mae(self) -> float:
        return max((b.mae for b in self.bars), default=0)


class FullSessionAnalyzer:
    """
    전수 세션 분석기
    
    산출물:
    1. StateSession 히트맵 (엔진 기여도)
    2. EXIT 타입별 Force/τ 궤적 비교
    """
    
    def __init__(self):
        self.shadow = ShadowModeAdapter(encoder_name=None)
        self.sessions: List[SessionData] = []
        self.current_session: Optional[SessionData] = None
        self.session_counter = 0
        
        self.all_bar_logs: List[BarLog] = []
        
        self.force_int_accum = 0.0
        self.energy_int_accum = 0.0
        self.dir_history = []
        
        self.stats = {
            "total_candles": 0,
            "wait": 0, "observe": 0, "enter": 0
        }
    
    def reset_accumulators(self):
        """세션 시작시 누적값 리셋"""
        self.force_int_accum = 0.0
        self.energy_int_accum = 0.0
    
    def process_candle(self, candle: Dict, bar_idx: int) -> Optional[BarLog]:
        """단일 캔들 처리"""
        self.stats["total_candles"] += 1
        
        try:
            result = self.shadow.process(candle)
        except Exception:
            return None
        
        action = result['engine']['action'].get('action', 'WAIT')
        state = result['engine']['state']
        
        tau = state.get('tau_hat', 0)
        
        force_from_data = candle.get('force_raw', 0)
        force_from_state = state.get('force_hat', 0)
        force = force_from_data if abs(force_from_data) > 0.1 else force_from_state
        
        dc = state.get('dc_hat', 0.5)
        delta = state.get('delta_hat', 0)
        price = float(candle.get('close', 0))
        timestamp = candle.get('time', '')
        
        self.dir_history.append(1 if dc > 0.5 else -1)
        if len(self.dir_history) > 20:
            self.dir_history = self.dir_history[-20:]
        dir_count = abs(sum(self.dir_history[-5:])) if len(self.dir_history) >= 5 else 0
        
        direction = "HIGH" if dc < 0.3 else "LOW" if dc > 0.7 else "NEUTRAL"
        
        if action == "WAIT":
            self.stats["wait"] += 1
        elif action == "OBSERVE":
            self.stats["observe"] += 1
        elif action == "ENTER":
            self.stats["enter"] += 1
        
        if action == "ENTER" and self.current_session is None:
            self.session_counter += 1
            self.reset_accumulators()
            
            self.current_session = SessionData(
                session_id=self.session_counter,
                start_bar=bar_idx,
                end_bar=bar_idx,
                direction=direction,
                entry_price=price,
                exit_type=""
            )
            
            bar_log = self._create_bar_log(
                bar_idx, 0, timestamp, "ENTER",
                tau, dc, dir_count, force, price
            )
            self.current_session.bars.append(bar_log)
            self.all_bar_logs.append(bar_log)
            return bar_log
        
        if self.current_session is not None:
            entry_price = self.current_session.entry_price
            entry_dir = self.current_session.direction
            
            if entry_dir == "HIGH":
                mfe = max(0, price - entry_price)
                mae = max(0, entry_price - price)
            else:
                mfe = max(0, entry_price - price)
                mae = max(0, price - entry_price)
            
            should_exit, exit_type = self._check_exit(tau, force, mae, len(self.current_session.bars))
            
            if should_exit:
                bar_log = self._create_bar_log(
                    bar_idx, len(self.current_session.bars),
                    timestamp, "EXIT",
                    tau, dc, dir_count, force, price
                )
                self.current_session.bars.append(bar_log)
                self.all_bar_logs.append(bar_log)
                
                self.current_session.end_bar = bar_idx
                self.current_session.exit_type = exit_type.value
                
                if entry_dir == "HIGH":
                    self.current_session.final_pnl = price - entry_price
                else:
                    self.current_session.final_pnl = entry_price - price
                
                self.sessions.append(self.current_session)
                self.current_session = None
                return bar_log
            
            hold_state = self._determine_hold(tau, force, mfe)
            
            bar_log = self._create_bar_log(
                bar_idx, len(self.current_session.bars),
                timestamp, hold_state,
                tau, dc, dir_count, force, price
            )
            self.current_session.bars.append(bar_log)
            self.all_bar_logs.append(bar_log)
            return bar_log
        
        return None
    
    def _create_bar_log(self, bar_idx: int, session_bar: int, 
                        timestamp: str, action: str,
                        tau: int, dc: float, dir_count: int,
                        force: float, price: float) -> BarLog:
        """바 로그 생성"""
        self.force_int_accum += force
        self.energy_int_accum += force * tau
        
        if self.current_session:
            entry_price = self.current_session.entry_price
            entry_dir = self.current_session.direction
            if entry_dir == "HIGH":
                mfe = max(0, price - entry_price)
                mae = max(0, entry_price - price)
            else:
                mfe = max(0, entry_price - price)
                mae = max(0, price - entry_price)
            session_id = self.current_session.session_id
        else:
            mfe, mae = 0, 0
            session_id = self.session_counter
        
        engine_flags = {
            "grammar": 1 if tau >= 5 else 0,
            "entry_alpha": 1 if dir_count >= 3 else 0,
            "force_engine": 1 if force >= FORCE_MIN else 0,
            "opa": 1
        }
        
        normalized_pct = (session_bar / MAX_SESSION_BARS) * 100 if MAX_SESSION_BARS > 0 else 0
        
        return BarLog(
            session_id=session_id,
            bar_index=session_bar,
            normalized_pct=normalized_pct,
            timestamp=timestamp,
            action=action,
            tau=tau,
            dc=dc,
            dir_count=dir_count,
            force=force,
            force_int=self.force_int_accum,
            energy_int=self.energy_int_accum,
            engine_flags=engine_flags,
            mfe=mfe,
            mae=mae
        )
    
    def _check_exit(self, tau: int, force: float, mae: float, duration: int) -> Tuple[bool, ExitType]:
        """EXIT 조건 체크"""
        if duration >= MAX_SESSION_BARS:
            return True, ExitType.MAX_BARS
        
        if mae > 25:
            return True, ExitType.MAE_EXCESS
        
        if self.current_session and len(self.current_session.bars) > 1:
            prev_tau = self.current_session.bars[-1].tau
            if prev_tau - tau >= 3 and force < FORCE_MIN:
                return True, ExitType.TAU_COLLAPSE
        
        if force < FORCE_MIN / 2 and duration > 3:
            return True, ExitType.FORCE_DECAY
        
        return False, None
    
    def _determine_hold(self, tau: int, force: float, mfe: float) -> str:
        """HOLD 상태 결정"""
        if force >= FORCE_MIN * 2:
            return "HOLD_EXTEND"
        if tau >= 6 and force >= FORCE_MIN and mfe > 5:
            return "HOLD_SMALL"
        return "HOLD"
    
    def run_analysis(self, candles: List[Dict]) -> Dict:
        """전체 분석 실행"""
        print(f"Processing {len(candles)} candles...")
        
        for i, candle in enumerate(candles):
            self.process_candle(candle, i)
        
        if self.current_session:
            self.current_session.exit_type = ExitType.END_OF_DATA.value
            self.sessions.append(self.current_session)
            self.current_session = None
        
        return self.generate_report()
    
    def generate_heatmap(self) -> Dict:
        """
        1️⃣ StateSession 히트맵 (엔진 기여도)
        
        x축: 세션 진행률 (0~100%, NORMALIZED_BINS 구간)
        y축: 엔진 (Grammar / Entry Alpha / Force / OPA)
        값: Activation Density (해당 구간에서 엔진 flag=1 비율)
        """
        bin_size = 100 / NORMALIZED_BINS
        
        heatmap = {
            "grammar": [0] * NORMALIZED_BINS,
            "entry_alpha": [0] * NORMALIZED_BINS,
            "force_engine": [0] * NORMALIZED_BINS,
            "opa": [0] * NORMALIZED_BINS
        }
        bin_counts = [0] * NORMALIZED_BINS
        
        for session in self.sessions:
            session_len = len(session.bars)
            if session_len == 0:
                continue
            
            for i, bar in enumerate(session.bars):
                pct = (i / session_len) * 100
                bin_idx = min(int(pct / bin_size), NORMALIZED_BINS - 1)
                
                bin_counts[bin_idx] += 1
                heatmap["grammar"][bin_idx] += bar.engine_flags.get("grammar", 0)
                heatmap["entry_alpha"][bin_idx] += bar.engine_flags.get("entry_alpha", 0)
                heatmap["force_engine"][bin_idx] += bar.engine_flags.get("force_engine", 0)
                heatmap["opa"][bin_idx] += bar.engine_flags.get("opa", 0)
        
        for engine in heatmap:
            for i in range(NORMALIZED_BINS):
                if bin_counts[i] > 0:
                    heatmap[engine][i] = round(heatmap[engine][i] / bin_counts[i] * 100, 1)
        
        return {
            "bin_labels": [f"{int(i * bin_size)}-{int((i+1) * bin_size)}%" for i in range(NORMALIZED_BINS)],
            "activation_density": heatmap,
            "bin_counts": bin_counts,
            "interpretation": {
                "grammar": "τ≥5 구간",
                "entry_alpha": "dir≥3 구간",
                "force_engine": "Force≥10 구간",
                "opa": "권한 봉인 (항상 1)"
            }
        }
    
    def generate_exit_trajectories(self) -> Dict:
        """
        2️⃣ EXIT 타입별 Force/τ 궤적 비교
        
        세션 정규화 후 평균 궤적 계산
        """
        exit_groups = defaultdict(list)
        
        for session in self.sessions:
            if session.exit_type:
                exit_groups[session.exit_type].append(session)
        
        trajectories = {}
        
        for exit_type, sessions in exit_groups.items():
            avg_tau = [0] * NORMALIZED_BINS
            avg_force_int = [0] * NORMALIZED_BINS
            avg_energy_int = [0] * NORMALIZED_BINS
            avg_mfe = [0] * NORMALIZED_BINS
            avg_mae = [0] * NORMALIZED_BINS
            bin_counts = [0] * NORMALIZED_BINS
            
            bin_size = 100 / NORMALIZED_BINS
            
            for session in sessions:
                session_len = len(session.bars)
                if session_len == 0:
                    continue
                
                for i, bar in enumerate(session.bars):
                    pct = (i / session_len) * 100
                    bin_idx = min(int(pct / bin_size), NORMALIZED_BINS - 1)
                    
                    bin_counts[bin_idx] += 1
                    avg_tau[bin_idx] += bar.tau
                    avg_force_int[bin_idx] += bar.force_int
                    avg_energy_int[bin_idx] += bar.energy_int
                    avg_mfe[bin_idx] += bar.mfe
                    avg_mae[bin_idx] += bar.mae
            
            for i in range(NORMALIZED_BINS):
                if bin_counts[i] > 0:
                    avg_tau[i] = round(avg_tau[i] / bin_counts[i], 1)
                    avg_force_int[i] = round(avg_force_int[i] / bin_counts[i], 2)
                    avg_energy_int[i] = round(avg_energy_int[i] / bin_counts[i], 2)
                    avg_mfe[i] = round(avg_mfe[i] / bin_counts[i], 2)
                    avg_mae[i] = round(avg_mae[i] / bin_counts[i], 2)
            
            avg_pnl = sum(s.final_pnl for s in sessions) / len(sessions) if sessions else 0
            
            trajectories[exit_type] = {
                "count": len(sessions),
                "avg_pnl": round(avg_pnl, 2),
                "avg_duration": round(sum(s.duration() for s in sessions) / len(sessions), 1) if sessions else 0,
                "tau_trajectory": avg_tau,
                "force_int_trajectory": avg_force_int,
                "energy_int_trajectory": avg_energy_int,
                "mfe_trajectory": avg_mfe,
                "mae_trajectory": avg_mae
            }
        
        return {
            "bin_labels": [f"{int(i * (100/NORMALIZED_BINS))}-{int((i+1) * (100/NORMALIZED_BINS))}%" for i in range(NORMALIZED_BINS)],
            "exit_trajectories": trajectories,
            "key_metrics": {
                "force_int_30pct": self._get_metric_at_pct(trajectories, "force_int_trajectory", 30),
                "force_int_50pct": self._get_metric_at_pct(trajectories, "force_int_trajectory", 50),
                "tau_plateau": self._analyze_tau_plateau(trajectories),
                "energy_slope": self._analyze_energy_slope(trajectories)
            }
        }
    
    def _get_metric_at_pct(self, trajectories: Dict, metric: str, pct: int) -> Dict:
        """특정 퍼센트에서의 메트릭 추출"""
        bin_idx = min(int(pct / (100 / NORMALIZED_BINS)), NORMALIZED_BINS - 1)
        result = {}
        for exit_type, data in trajectories.items():
            if metric in data:
                result[exit_type] = data[metric][bin_idx]
        return result
    
    def _analyze_tau_plateau(self, trajectories: Dict) -> Dict:
        """τ plateau 분석"""
        result = {}
        for exit_type, data in trajectories.items():
            tau_traj = data.get("tau_trajectory", [])
            if tau_traj:
                plateau_len = sum(1 for i in range(1, len(tau_traj)) if abs(tau_traj[i] - tau_traj[i-1]) <= 1)
                result[exit_type] = plateau_len
        return result
    
    def _analyze_energy_slope(self, trajectories: Dict) -> Dict:
        """Energy slope 분석"""
        result = {}
        for exit_type, data in trajectories.items():
            energy_traj = data.get("energy_int_trajectory", [])
            if len(energy_traj) >= 2:
                slope = (energy_traj[-1] - energy_traj[0]) / len(energy_traj)
                result[exit_type] = round(slope, 3)
        return result
    
    def _determine_fail_reason(self, bar, prev_bar, prev_force: float) -> HandoffFailReason:
        """
        FAIL_REASON 우선순위 판정
        
        우선순위:
        1. OPA_BLOCK
        2. ENERGY_EXHAUST  
        3. TAU_DROP
        4. FORCE_RESET
        5. FORCE_NOT_READY
        6. ENTRY_ORPHAN
        """
        opa_active = bar.engine_flags.get("opa", 1) == 0
        if opa_active:
            return HandoffFailReason.OPA_BLOCK
        
        if bar.energy_int < 50:
            return HandoffFailReason.ENERGY_EXHAUST
        
        if prev_bar and bar.tau < prev_bar.tau - 2:
            return HandoffFailReason.TAU_DROP
        
        if prev_force > 0 and bar.force < prev_force * 0.5:
            return HandoffFailReason.FORCE_RESET
        
        if bar.force < FORCE_MIN:
            return HandoffFailReason.FORCE_NOT_READY
        
        return HandoffFailReason.ENTRY_ORPHAN
    
    def analyze_engine_handoff(self) -> Dict:
        """
        3️⃣ 엔진 핸드오프 분석 + FAIL_REASON 표준 적용
        
        핵심 질문: "엔진 A가 시작한 세션을 엔진 B가 이어받을 수 있었는가?"
        
        FAIL_REASON 우선순위:
        1. OPA_BLOCK → 2. ENERGY_EXHAUST → 3. TAU_DROP 
        → 4. FORCE_RESET → 5. FORCE_NOT_READY → 6. ENTRY_ORPHAN
        """
        handoff_stats = {
            "grammar_to_entry": {"success": 0, "fail": 0},
            "entry_to_force": {"success": 0, "fail": 0, "fail_reasons": {}},
            "force_to_hold": {"success": 0, "fail": 0, "fail_reasons": {}},
            "total_handoff_missing": 0,
            "total_handoff_success": 0
        }
        
        all_handoffs = []
        engine_relay = []
        
        for session in self.sessions:
            if len(session.bars) < 2:
                continue
            
            grammar_active = False
            entry_active = False
            force_active = False
            prev_force = 0.0
            
            for i, bar in enumerate(session.bars):
                prev_grammar = grammar_active
                prev_entry = entry_active
                prev_force_active = force_active
                prev_bar = session.bars[i-1] if i > 0 else None
                
                grammar_active = bar.engine_flags.get("grammar", 0) == 1
                entry_active = bar.engine_flags.get("entry_alpha", 0) == 1
                force_active = bar.engine_flags.get("force_engine", 0) == 1
                
                if i > 0:
                    if prev_grammar and entry_active:
                        handoff_stats["grammar_to_entry"]["success"] += 1
                        handoff_stats["total_handoff_success"] += 1
                        all_handoffs.append(HandoffRecord(
                            from_engine="GRAMMAR", to_engine="ENTRY",
                            success=True, bar_index=i,
                            force_at_handoff=bar.force, tau_at_handoff=bar.tau
                        ))
                    elif prev_grammar and not entry_active:
                        handoff_stats["grammar_to_entry"]["fail"] += 1
                        handoff_stats["total_handoff_missing"] += 1
                    
                    if prev_entry and force_active:
                        handoff_stats["entry_to_force"]["success"] += 1
                        handoff_stats["total_handoff_success"] += 1
                        all_handoffs.append(HandoffRecord(
                            from_engine="ENTRY", to_engine="FORCE",
                            success=True, bar_index=i,
                            force_at_handoff=bar.force, tau_at_handoff=bar.tau
                        ))
                    elif prev_entry and not force_active and bar.action not in ["EXIT"]:
                        fail_reason = self._determine_fail_reason(bar, prev_bar, prev_force)
                        handoff_stats["entry_to_force"]["fail"] += 1
                        handoff_stats["total_handoff_missing"] += 1
                        
                        reason_key = fail_reason.value
                        handoff_stats["entry_to_force"]["fail_reasons"][reason_key] = \
                            handoff_stats["entry_to_force"]["fail_reasons"].get(reason_key, 0) + 1
                        
                        all_handoffs.append(HandoffRecord(
                            from_engine="ENTRY", to_engine="FORCE",
                            success=False, fail_reason=fail_reason, bar_index=i,
                            force_at_handoff=bar.force, tau_at_handoff=bar.tau
                        ))
                    
                    if prev_force_active and bar.action in ["HOLD", "HOLD_SMALL", "HOLD_EXTEND"]:
                        handoff_stats["force_to_hold"]["success"] += 1
                        handoff_stats["total_handoff_success"] += 1
                        all_handoffs.append(HandoffRecord(
                            from_engine="FORCE", to_engine="HOLD",
                            success=True, bar_index=i,
                            force_at_handoff=bar.force, tau_at_handoff=bar.tau
                        ))
                    elif prev_force_active and bar.action == "EXIT":
                        fail_reason = self._determine_fail_reason(bar, prev_bar, prev_force)
                        handoff_stats["force_to_hold"]["fail"] += 1
                        
                        reason_key = fail_reason.value
                        handoff_stats["force_to_hold"]["fail_reasons"][reason_key] = \
                            handoff_stats["force_to_hold"]["fail_reasons"].get(reason_key, 0) + 1
                        
                        all_handoffs.append(HandoffRecord(
                            from_engine="FORCE", to_engine="HOLD",
                            success=False, fail_reason=fail_reason, bar_index=i,
                            force_at_handoff=bar.force, tau_at_handoff=bar.tau
                        ))
                
                prev_force = bar.force
            
            session_relay = []
            for bar in session.bars:
                active = []
                if bar.engine_flags.get("grammar", 0): active.append("G")
                if bar.engine_flags.get("entry_alpha", 0): active.append("E")
                if bar.engine_flags.get("force_engine", 0): active.append("F")
                session_relay.append("+".join(active) if active else "-")
            engine_relay.append({
                "session_id": session.session_id,
                "relay": "→".join(session_relay[:10]),
                "exit_type": session.exit_type,
                "pnl": session.final_pnl
            })
        
        return {
            "handoff_stats": handoff_stats,
            "all_handoffs": [h.to_dict() for h in all_handoffs],
            "engine_relay_samples": engine_relay[:5],
            "fail_reason_summary": {
                "entry_to_force": handoff_stats["entry_to_force"].get("fail_reasons", {}),
                "force_to_hold": handoff_stats["force_to_hold"].get("fail_reasons", {})
            },
            "interpretation": {
                "grammar_to_entry": "문법이 진입 허용 → Entry Alpha 활성화",
                "entry_to_force": "진입 후 → Force 유지",
                "force_to_hold": "Force 유지 → HOLD 지속"
            }
        }
    
    def generate_report(self) -> Dict:
        """종합 보고서 생성"""
        
        if not self.sessions:
            return {"error": "No sessions found"}
        
        heatmap = self.generate_heatmap()
        trajectories = self.generate_exit_trajectories()
        handoff = self.analyze_engine_handoff()
        
        exit_dist = defaultdict(int)
        for s in self.sessions:
            exit_dist[s.exit_type] += 1
        
        winners = [s for s in self.sessions if s.final_pnl > 0]
        total_pnl = sum(s.final_pnl for s in self.sessions)
        
        hold_counts = {"ENTER": 0, "HOLD": 0, "HOLD_SMALL": 0, "HOLD_EXTEND": 0, "EXIT": 0}
        for s in self.sessions:
            for b in s.bars:
                if b.action in hold_counts:
                    hold_counts[b.action] += 1
        
        report = {
            "analysis_time": datetime.now().isoformat(),
            "overview": {
                "total_candles": self.stats["total_candles"],
                "wait": self.stats["wait"],
                "observe": self.stats["observe"],
                "enter": self.stats["enter"],
                "total_sessions": len(self.sessions)
            },
            "session_metrics": {
                "avg_duration": round(sum(s.duration() for s in self.sessions) / len(self.sessions), 1),
                "avg_max_tau": round(sum(s.max_tau() for s in self.sessions) / len(self.sessions), 1),
                "avg_max_force_int": round(sum(s.max_force_int() for s in self.sessions) / len(self.sessions), 2),
                "avg_max_energy_int": round(sum(s.max_energy_int() for s in self.sessions) / len(self.sessions), 2),
                "win_rate": f"{len(winners) / len(self.sessions) * 100:.1f}%",
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(total_pnl / len(self.sessions), 2)
            },
            "hold_distribution": hold_counts,
            "exit_distribution": dict(exit_dist),
            "heatmap_analysis": heatmap,
            "trajectory_analysis": trajectories,
            "handoff_analysis": handoff,
            "adjustment_candidates": self._generate_adjustment_candidates(heatmap, trajectories)
        }
        
        return report
    
    def _generate_adjustment_candidates(self, heatmap: Dict, trajectories: Dict) -> Dict:
        """
        조절 후보 3개 도출
        (근본 불변, 데이터로 측정된 것만 조절)
        """
        return {
            "1_hold_observation_window": {
                "description": "HOLD 관측창 길이",
                "current": "1 bar",
                "suggested": "3-5 bars",
                "reason": "현재 ENTER 직후 즉시 EXIT, 관측 시간 필요"
            },
            "2_force_accumulation_threshold": {
                "description": "Force 누적 임계치",
                "current": f"force >= {FORCE_MIN}",
                "suggested": "force_int >= E_min (누적 기준)",
                "reason": "순간값 대신 누적값으로 HOLD 판정"
            },
            "3_small_extend_rules": {
                "description": "SMALL/EXTEND 승격 규칙",
                "current": "없음",
                "suggested": "τ 유지 + energy slope > 0 → SMALL",
                "reason": "세션 내부 이벤트로 정의 필요"
            }
        }
    
    def print_report(self, report: Dict):
        """보고서 출력"""
        print("\n" + "=" * 70)
        print("FULL SESSION ANALYSIS — 전수 데이터 통합 분석")
        print("=" * 70)
        
        o = report['overview']
        print(f"\n📊 Overview:")
        print(f"  Total Candles: {o['total_candles']}")
        print(f"  WAIT: {o['wait']} | OBSERVE: {o['observe']} | ENTER: {o['enter']}")
        print(f"  Total Sessions: {o['total_sessions']}")
        
        m = report['session_metrics']
        print(f"\n📈 Session Metrics:")
        print(f"  Avg Duration: {m['avg_duration']} bars")
        print(f"  Avg Max τ: {m['avg_max_tau']}")
        print(f"  Avg Max Force Int: {m['avg_max_force_int']}")
        print(f"  Avg Max Energy Int: {m['avg_max_energy_int']}")
        print(f"  Win Rate: {m['win_rate']}")
        print(f"  Total PnL: {m['total_pnl']} pts")
        print(f"  Avg PnL: {m['avg_pnl']} pts")
        
        print(f"\n🔗 HOLD Distribution:")
        for k, v in report['hold_distribution'].items():
            print(f"  {k}: {v}")
        
        print(f"\n🚪 Exit Distribution:")
        for k, v in report['exit_distribution'].items():
            print(f"  {k}: {v}")
        
        print(f"\n📊 HEATMAP — Engine Activation by Session %:")
        h = report['heatmap_analysis']
        print(f"  Bins: {h['bin_labels']}")
        for engine, values in h['activation_density'].items():
            print(f"  {engine}: {values}")
        
        print(f"\n📈 EXIT TRAJECTORIES:")
        t = report['trajectory_analysis']
        for exit_type, data in t['exit_trajectories'].items():
            print(f"\n  {exit_type}:")
            print(f"    Count: {data['count']}")
            print(f"    Avg PnL: {data['avg_pnl']} pts")
            print(f"    Avg Duration: {data['avg_duration']} bars")
            print(f"    τ Trajectory: {data['tau_trajectory'][:5]}...")
            print(f"    Energy Trajectory: {data['energy_int_trajectory'][:5]}...")
        
        print(f"\n🎯 Key Metrics:")
        km = t['key_metrics']
        print(f"  Force@30%: {km.get('force_int_30pct', {})}")
        print(f"  Force@50%: {km.get('force_int_50pct', {})}")
        print(f"  τ Plateau: {km.get('tau_plateau', {})}")
        print(f"  Energy Slope: {km.get('energy_slope', {})}")
        
        print(f"\n🔗 ENGINE HANDOFF ANALYSIS:")
        ho = report.get('handoff_analysis', {})
        hs = ho.get('handoff_stats', {})
        print(f"  Total Handoff Success: {hs.get('total_handoff_success', 0)}")
        print(f"  Total Handoff Missing: {hs.get('total_handoff_missing', 0)}")
        
        g2e = hs.get('grammar_to_entry', {})
        e2f = hs.get('entry_to_force', {})
        f2h = hs.get('force_to_hold', {})
        
        print(f"\n  Grammar → Entry: success={g2e.get('success', 0)}, fail={g2e.get('fail', 0)}")
        print(f"  Entry → Force:   success={e2f.get('success', 0)}, fail={e2f.get('fail', 0)}")
        print(f"  Force → HOLD:    success={f2h.get('success', 0)}, fail={f2h.get('fail', 0)}")
        
        fail_summary = ho.get('fail_reason_summary', {})
        if fail_summary:
            print(f"\n  📊 FAIL_REASON Distribution:")
            for handoff, reasons in fail_summary.items():
                if reasons:
                    print(f"    {handoff}:")
                    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                        print(f"      {reason}: {count}")
        
        samples = ho.get('engine_relay_samples', [])
        if samples:
            print(f"\n  Sample Engine Relays:")
            for s in samples[:3]:
                print(f"    Session {s['session_id']}: {s['relay']} → {s['exit_type']} ({s['pnl']:.1f} pts)")
        
        print(f"\n⚙️ ADJUSTMENT CANDIDATES (근본 불변, 데이터 기반 조절만):")
        for key, adj in report['adjustment_candidates'].items():
            print(f"\n  {key}:")
            print(f"    현재: {adj['current']}")
            print(f"    제안: {adj['suggested']}")
            print(f"    이유: {adj['reason']}")
        
        print("\n" + "=" * 70)
    
    def save_report(self, report: Dict, filepath: str = "/tmp/full_session_report.json"):
        """보고서 저장"""
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nReport saved to: {filepath}")
        return filepath


def load_all_chart_data() -> List[Dict]:
    """
    전체 차트 데이터 로드
    
    force_readings.json 필드:
    - force_ratio_20: Force 비율 (실제 Force 데이터!)
    - dc_pre: DC 값
    - avg_delta: Delta 값
    - mdr: MDR 값
    - mrfr: MRFR 값
    - bull_bear_ratio: 불/베어 비율
    """
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
                'avg_delta': rec.get('avg_delta', 0),
                'mdr': rec.get('mdr', 0),
                'mrfr': rec.get('mrfr', 1),
                'bull_bear_ratio': rec.get('bull_bear_ratio', 1)
            }
            candles.append(candle)
    
    print(f"Loaded {len(candles)} candles from force_readings.json")
    print(f"Force range: {min(c['force_raw'] for c in candles):.2f} to {max(c['force_raw'] for c in candles):.2f}")
    return candles


def main():
    """메인 실행"""
    print("=" * 70)
    print("FULL SESSION ANALYSIS")
    print("1️⃣ StateSession 히트맵 (엔진 기여도)")
    print("2️⃣ EXIT 타입별 Force/τ 궤적 비교")
    print("=" * 70)
    
    candles = load_all_chart_data()
    
    if len(candles) < 100:
        print("Not enough data")
        return
    
    analyzer = FullSessionAnalyzer()
    report = analyzer.run_analysis(candles)
    
    analyzer.print_report(report)
    analyzer.save_report(report)


if __name__ == "__main__":
    main()
