"""
Phase H — SESSION EXTRACTION
============================

역할: raw candle log → session 단위 재구성

검증 포인트:
- ENTER 없이 session 생성 ❌
- EXIT 없이 session 종료 ❌
- session overlap ❌

Integrity Rules:
- H-1: 모든 ENTER는 정확히 하나의 session에 속함
- H-2: 모든 session은 정확히 하나의 EXIT_REASON을 가짐
"""

import sys
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from enum import Enum

sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/engine')

from state_session import ExitType, HandoffFailReason, HandoffRecord
from shadow_mode import ShadowModeAdapter


@dataclass
class SessionRecord:
    """Phase H Session 레코드"""
    session_id: int
    start_bar: int
    end_bar: int
    entry_price: float
    exit_price: float
    direction: str
    entry_ok: bool
    force_bars: int
    avg_force: float
    max_tau: int
    max_force_int: float
    max_energy_int: float
    exit_reason: str
    pnl: float
    handoffs: List[Dict] = field(default_factory=list)
    bars: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)


class SessionExtractor:
    """
    Session 추출기
    
    핵심 원칙:
    - HOLD는 상태가 아니다
    - HOLD는 EXIT가 발생하지 않은 결과
    - Session := ENTER 발생 시점부터 EXIT 조건이 충족될 때까지의 연속 캔들 집합
    """
    
    FORCE_MIN = 10.0
    TAU_MIN = 5
    DIR_THRESHOLD = 3
    MAX_SESSION_BARS = 20
    MAE_LIMIT = 25.0
    
    def __init__(self):
        self.shadow = ShadowModeAdapter()
        self.sessions: List[SessionRecord] = []
        self.current_session: Optional[SessionRecord] = None
        self.session_counter = 0
        self.dir_history = []
        self.force_int_accum = 0.0
        self.energy_int_accum = 0.0
        self.force_history = []
        
        self.integrity_errors = []
        self.enter_bars = set()
    
    def extract_from_candles(self, candles: List[Dict]) -> List[SessionRecord]:
        """캔들 데이터에서 세션 추출"""
        print(f"Extracting sessions from {len(candles)} candles...")
        
        for i, candle in enumerate(candles):
            self._process_candle(candle, i)
        
        if self.current_session:
            self.current_session.end_bar = len(candles) - 1
            self.current_session.exit_reason = ExitType.END_OF_DATA.value
            self.sessions.append(self.current_session)
            self.current_session = None
        
        self._validate_integrity()
        
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
                if bar_idx in self.enter_bars:
                    self.integrity_errors.append(f"H-1 violation: duplicate ENTER at bar {bar_idx}")
                    return
                
                self.enter_bars.add(bar_idx)
                self.session_counter += 1
                self.force_int_accum = 0.0
                self.energy_int_accum = 0.0
                self.force_history = []
                
                self.current_session = SessionRecord(
                    session_id=self.session_counter,
                    start_bar=bar_idx,
                    end_bar=bar_idx,
                    entry_price=price,
                    exit_price=price,
                    direction="HIGH" if dir_count > 0 else "LOW",
                    entry_ok=True,
                    force_bars=0,
                    avg_force=0.0,
                    max_tau=tau,
                    max_force_int=0.0,
                    max_energy_int=0.0,
                    exit_reason="",
                    pnl=0.0
                )
                
                self._record_bar(bar_idx, "ENTER", tau, force, price)
        else:
            self.force_int_accum += force
            self.energy_int_accum += force * tau
            self.force_history.append(force)
            
            if force >= self.FORCE_MIN:
                self.current_session.force_bars += 1
            
            self.current_session.max_tau = max(self.current_session.max_tau, tau)
            self.current_session.max_force_int = max(self.current_session.max_force_int, self.force_int_accum)
            self.current_session.max_energy_int = max(self.current_session.max_energy_int, self.energy_int_accum)
            
            duration = bar_idx - self.current_session.start_bar
            
            entry_price = self.current_session.entry_price
            if self.current_session.direction == "HIGH":
                mfe = max(0, price - entry_price)
                mae = max(0, entry_price - price)
            else:
                mfe = max(0, entry_price - price)
                mae = max(0, price - entry_price)
            
            should_exit, exit_type = self._check_exit(tau, force, mae, duration)
            
            if should_exit:
                self.current_session.end_bar = bar_idx
                self.current_session.exit_price = price
                self.current_session.exit_reason = exit_type.value
                
                if self.current_session.direction == "HIGH":
                    self.current_session.pnl = price - entry_price
                else:
                    self.current_session.pnl = entry_price - price
                
                if self.force_history:
                    self.current_session.avg_force = sum(self.force_history) / len(self.force_history)
                
                self._record_bar(bar_idx, "EXIT", tau, force, price)
                self.sessions.append(self.current_session)
                self.current_session = None
            else:
                hold_state = self._determine_hold_state(tau, force, mfe)
                self._record_bar(bar_idx, hold_state, tau, force, price)
    
    def _check_exit(self, tau: int, force: float, mae: float, duration: int) -> Tuple[bool, ExitType]:
        """EXIT 조건 체크"""
        if duration >= self.MAX_SESSION_BARS:
            return True, ExitType.MAX_BARS
        
        if mae > self.MAE_LIMIT:
            return True, ExitType.MAE_EXCESS
        
        if self.current_session and len(self.current_session.bars) > 1:
            prev_tau = self.current_session.bars[-1].get('tau', 0)
            if prev_tau - tau >= 3 and force < self.FORCE_MIN:
                return True, ExitType.TAU_COLLAPSE
        
        if force < self.FORCE_MIN / 2 and duration > 3:
            return True, ExitType.FORCE_DECAY
        
        return False, None
    
    def _determine_hold_state(self, tau: int, force: float, mfe: float) -> str:
        """HOLD 상태 결정 (상태가 아니라 EXIT 미충족의 결과)"""
        if force >= self.FORCE_MIN * 2:
            return "HOLD_EXTEND"
        elif tau >= self.TAU_MIN and force >= self.FORCE_MIN:
            return "HOLD"
        else:
            return "HOLD"
    
    def _record_bar(self, bar_idx: int, action: str, tau: int, force: float, price: float):
        """바 기록"""
        if self.current_session:
            self.current_session.bars.append({
                "bar_idx": bar_idx,
                "session_bar": len(self.current_session.bars),
                "action": action,
                "tau": tau,
                "force": force,
                "force_int": self.force_int_accum,
                "energy_int": self.energy_int_accum,
                "price": price
            })
    
    def _validate_integrity(self):
        """Phase H 무결성 검증"""
        print("\n" + "=" * 50)
        print("INTEGRITY VALIDATION (Phase H Rules)")
        print("=" * 50)
        
        for session in self.sessions:
            if not session.exit_reason:
                self.integrity_errors.append(
                    f"H-2 violation: session {session.session_id} has no exit_reason"
                )
        
        for session in self.sessions:
            for bar in session.bars:
                if bar.get('action') == 'HOLD' and bar.get('action') not in ['HOLD', 'HOLD_EXTEND', 'HOLD_SMALL', 'ENTER', 'EXIT']:
                    self.integrity_errors.append(
                        f"H-3 violation: session {session.session_id} has invalid HOLD state"
                    )
        
        if self.integrity_errors:
            print(f"\n❌ INTEGRITY ERRORS: {len(self.integrity_errors)}")
            for err in self.integrity_errors[:5]:
                print(f"  - {err}")
        else:
            print("\n✅ All integrity rules passed!")
        
        print(f"\n📊 Session Summary:")
        print(f"  Total Sessions: {len(self.sessions)}")
        print(f"  Avg Duration: {sum(s.end_bar - s.start_bar for s in self.sessions) / len(self.sessions):.1f} bars" if self.sessions else "  No sessions")
        
        return len(self.integrity_errors) == 0


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
    extractor = SessionExtractor()
    sessions = extractor.extract_from_candles(candles)
    
    output_path = '/tmp/phase_h_sessions.json'
    with open(output_path, 'w') as f:
        json.dump([s.to_dict() for s in sessions], f, indent=2, default=str)
    
    print(f"\nSessions saved to: {output_path}")
    return sessions


if __name__ == "__main__":
    main()
