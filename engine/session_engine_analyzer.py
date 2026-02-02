"""
Session Engine Analyzer — 엔진별 전수 데이터 분석

핵심 질문:
어떤 엔진 조합에서 EXIT_PROFIT이 구조적으로 나오는가

분석 대상:
- V7 Grammar (τ 상태 판정)
- Entry Alpha (방향성)
- Force Engine (지속 조건)
- OPA (권한 봉인)
- Phase Tracker (시간 추적)
"""

import json
import sys
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')

from shadow_mode import ShadowModeAdapter
from state_session import (
    StateSession, ExitType, ActionLayer,
    create_session_from_enter, add_trajectory_point, close_session,
    SessionAnalyzer, ENGINE_PROFILES
)


FORCE_MIN = 10.0
TAU_DECAY_THRESHOLD = 2
MAX_SESSION_BARS = 50


class SessionEngineAnalyzer:
    """
    세션 중심 엔진 분석기
    
    "엔진 중심" → "세션 중심" 전환
    모든 엔진을 하나의 StateSession 안에 통합
    """
    
    def __init__(self):
        self.shadow = ShadowModeAdapter(encoder_name=None)
        self.sessions: List[StateSession] = []
        self.current_session: Optional[StateSession] = None
        self.session_counter = 0
        
        self.all_candles = 0
        self.enter_count = 0
        self.observe_count = 0
        self.wait_count = 0
    
    def determine_hold_state(self, tau: int, force: float, 
                             prev_tau: int, prev_force: float,
                             mfe: float) -> str:
        """
        HOLD sub-state 결정 (물리 조건 기반)
        
        HOLD 유지 조건:
        - τ 유지 or 증가 → HOLD 유지
        - Force >= Force_min → HOLD 유지
        - Force 급증 + τ 유지 → HOLD_EXTEND
        - τ >= 6 + MFE > 5 → HOLD_SMALL 가능
        """
        tau_change = tau - prev_tau
        force_change = force - prev_force
        
        if force >= FORCE_MIN * 2 and tau_change >= 0:
            return "HOLD_EXTEND"
        
        if tau >= 6 and abs(tau_change) <= 1 and force >= FORCE_MIN and mfe > 5:
            return "HOLD_SMALL"
        
        return "HOLD"
    
    def determine_exit(self, tau: int, force: float, 
                       prev_tau: int, prev_force: float,
                       duration: int, mae: float) -> Tuple[bool, ExitType]:
        """
        EXIT 조건 결정 (명명된 종료)
        """
        if duration >= MAX_SESSION_BARS:
            return True, ExitType.MAX_BARS
        
        if mae > 25:
            return True, ExitType.MAE_EXCESS
        
        tau_drop = prev_tau - tau
        if tau_drop >= 3 and force < FORCE_MIN:
            return True, ExitType.TAU_COLLAPSE
        
        if force < FORCE_MIN / 2 and duration > 3:
            return True, ExitType.FORCE_DECAY
        
        return False, None
    
    def process_candle(self, candle: Dict, bar_idx: int) -> Dict:
        """단일 캔들 처리"""
        self.all_candles += 1
        
        try:
            result = self.shadow.process(candle)
        except Exception as e:
            return {"error": str(e)}
        
        action = result['engine']['action'].get('action', 'WAIT')
        state = result['engine']['state']
        
        tau = state.get('tau_hat', 0)
        force = state.get('force_hat', 0)
        dc = state.get('dc_hat', 0.5)
        delta = state.get('delta_hat', 0)
        price = float(candle.get('close', 0))
        timestamp = candle.get('time', '')
        
        direction = "HIGH" if dc < 0.3 else "LOW" if dc > 0.7 else "NEUTRAL"
        
        if action == "WAIT":
            self.wait_count += 1
        elif action == "OBSERVE":
            self.observe_count += 1
        elif action == "ENTER":
            self.enter_count += 1
        
        if action == "ENTER" and self.current_session is None:
            self.session_counter += 1
            self.current_session = create_session_from_enter(
                session_id=self.session_counter,
                bar_idx=bar_idx,
                timestamp=timestamp,
                price=price,
                tau=tau,
                dc=dc,
                delta=delta,
                force=force,
                direction=direction
            )
            
            add_trajectory_point(
                self.current_session,
                bar_idx=bar_idx,
                tau=tau,
                force=force,
                action="ENTER",
                price=price
            )
            return {"event": "SESSION_START", "session_id": self.session_counter}
        
        if self.current_session is not None:
            entry_price = self.current_session.entry.price
            entry_direction = self.current_session.entry.direction
            
            if entry_direction == "HIGH":
                mfe = max(0, price - entry_price)
                mae = max(0, entry_price - price)
            else:
                mfe = max(0, entry_price - price)
                mae = max(0, price - entry_price)
            
            if self.current_session.trajectory:
                prev = self.current_session.trajectory[-1]
                prev_tau = prev.tau
                prev_force = prev.force
            else:
                prev_tau = self.current_session.entry.tau
                prev_force = self.current_session.entry.force
            
            should_exit, exit_type = self.determine_exit(
                tau, force, prev_tau, prev_force,
                self.current_session.duration(), mae
            )
            
            if should_exit:
                add_trajectory_point(
                    self.current_session,
                    bar_idx=bar_idx,
                    tau=tau,
                    force=force,
                    action="EXIT",
                    price=price
                )
                
                close_session(
                    self.current_session,
                    bar_idx=bar_idx,
                    timestamp=timestamp,
                    exit_type=exit_type,
                    price=price,
                    tau=tau,
                    force=force
                )
                
                self.sessions.append(self.current_session)
                session_id = self.current_session.session_id
                pnl = self.current_session.exit.pnl
                self.current_session = None
                
                return {
                    "event": "SESSION_END",
                    "session_id": session_id,
                    "exit_type": exit_type.value,
                    "pnl": pnl
                }
            
            hold_state = self.determine_hold_state(
                tau, force, prev_tau, prev_force, mfe
            )
            
            add_trajectory_point(
                self.current_session,
                bar_idx=bar_idx,
                tau=tau,
                force=force,
                action=hold_state,
                price=price
            )
            
            return {
                "event": "HOLD",
                "session_id": self.current_session.session_id,
                "hold_state": hold_state,
                "duration": self.current_session.duration()
            }
        
        return {"event": "WAIT", "action": action}
    
    def run_analysis(self, candles: List[Dict]) -> Dict:
        """전체 분석 실행"""
        print(f"Processing {len(candles)} candles...")
        
        for i, candle in enumerate(candles):
            self.process_candle(candle, i)
        
        if self.current_session is not None:
            close_session(
                self.current_session,
                bar_idx=len(candles) - 1,
                timestamp="END",
                exit_type=ExitType.END_OF_DATA,
                price=candles[-1].get('close', 0) if candles else 0,
                tau=0,
                force=0
            )
            self.sessions.append(self.current_session)
            self.current_session = None
        
        return self.generate_report()
    
    def generate_report(self) -> Dict:
        """종합 보고서 생성"""
        
        if not self.sessions:
            return {"error": "No sessions found"}
        
        analyzer = SessionAnalyzer()
        for s in self.sessions:
            analyzer.add_session(s)
        
        hold_stats = self._count_hold_substates()
        engine_impact = self._analyze_engine_impact()
        
        report = {
            "analysis_time": datetime.now().isoformat(),
            "overview": {
                "total_candles": self.all_candles,
                "wait_count": self.wait_count,
                "observe_count": self.observe_count,
                "enter_count": self.enter_count,
                "total_sessions": len(self.sessions)
            },
            "session_metrics": analyzer.avg_metrics(),
            "exit_distribution": analyzer.exit_type_distribution(),
            "hold_substates": hold_stats,
            "engine_impact": engine_impact,
            "sessions_detail": [s.to_dict() for s in self.sessions[:10]]
        }
        
        return report
    
    def _count_hold_substates(self) -> Dict:
        """HOLD sub-state 집계"""
        stats = {"ENTER": 0, "HOLD": 0, "HOLD_SMALL": 0, "HOLD_EXTEND": 0, "EXIT": 0}
        for session in self.sessions:
            for point in session.trajectory:
                if point.action in stats:
                    stats[point.action] += 1
        return stats
    
    def _analyze_engine_impact(self) -> Dict:
        """엔진별 영향 분석"""
        results = {}
        
        for name, profile in ENGINE_PROFILES.items():
            relevant_exits = [
                s for s in self.sessions
                if s.exit and s.exit.exit_type in profile.failure_types
            ]
            
            winning_sessions = [s for s in self.sessions if s.exit and s.exit.pnl > 0]
            
            results[name] = {
                "role": profile.role.value,
                "dimension": profile.dimension,
                "exits_caused": len(relevant_exits),
                "exit_pct": f"{len(relevant_exits) / len(self.sessions) * 100:.1f}%" if self.sessions else "0%",
                "strengths": profile.strengths,
                "required_partners": profile.required_partners
            }
        
        return results
    
    def print_report(self, report: Dict):
        """보고서 출력"""
        print("\n" + "=" * 70)
        print("SESSION ENGINE ANALYZER — 엔진별 전수 데이터 분석")
        print("=" * 70)
        
        o = report['overview']
        print(f"\n📊 Overview:")
        print(f"  Total Candles: {o['total_candles']}")
        print(f"  WAIT: {o['wait_count']} | OBSERVE: {o['observe_count']} | ENTER: {o['enter_count']}")
        print(f"  Total Sessions: {o['total_sessions']}")
        
        m = report['session_metrics']
        print(f"\n📈 Session Metrics:")
        print(f"  Avg Duration: {m.get('avg_duration', 0)} bars")
        print(f"  Avg Max τ: {m.get('avg_max_tau', 0)}")
        print(f"  Avg Integrated Energy: {m.get('avg_integrated_energy', 0)}")
        print(f"  Win Rate: {m.get('win_rate', '0%')}")
        print(f"  Total EV: {m.get('total_ev', 0)} pts")
        print(f"  Has EXTEND: {m.get('has_extend_pct', '0%')}")
        print(f"  Has SMALL: {m.get('has_small_pct', '0%')}")
        
        print(f"\n🔗 HOLD Sub-States:")
        for k, v in report['hold_substates'].items():
            print(f"  {k}: {v}")
        
        print(f"\n🚪 Exit Distribution:")
        for k, v in report['exit_distribution'].items():
            print(f"  {k}: {v}")
        
        print(f"\n⚙️ Engine Impact Analysis:")
        for name, data in report['engine_impact'].items():
            print(f"\n  {name}:")
            print(f"    Role: {data['role']}")
            print(f"    Exits Caused: {data['exits_caused']} ({data['exit_pct']})")
            print(f"    Partners Needed: {data['required_partners']}")
        
        print("\n" + "=" * 70)
    
    def save_report(self, report: Dict, filepath: str = "/tmp/session_engine_report.json"):
        """보고서 저장"""
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nReport saved to: {filepath}")
        return filepath


def load_chart_data() -> List[Dict]:
    """차트 데이터 로드"""
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
    
    print(f"Loaded {len(candles)} candles")
    return candles


def main():
    """메인 실행"""
    print("=" * 70)
    print("SESSION ENGINE ANALYZER")
    print("핵심 질문: 어떤 엔진 조합에서 EXIT_PROFIT이 구조적으로 나오는가")
    print("=" * 70)
    
    candles = load_chart_data()
    
    if len(candles) < 100:
        print("Not enough data")
        return
    
    analyzer = SessionEngineAnalyzer()
    report = analyzer.run_analysis(candles)
    
    analyzer.print_report(report)
    analyzer.save_report(report)


if __name__ == "__main__":
    main()
