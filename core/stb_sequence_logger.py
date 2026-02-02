"""
STB SEQUENCE LOGGER v1.0
========================
목적: 순서 관측기 (order observer) - 판단 추가 없음

LOCKED 정의 (STB_SEQUENCE v1.2):
- same direction
- STB_confirmed = True
- entry_time gap ≤ 30 minutes

허용:
- stb_seq_id 계산
- stb_index (first/re-entry) 기록

금지:
- θ 계산 ❌
- 결과 참조 ❌
- 성능 기반 분기 ❌
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional

WINDOW_MINUTES = 30
LOG_PATH = "v7-grammar-system/logs/runtime_stb_log.jsonl"


@dataclass
class STBLogEntry:
    trade_id: int
    timestamp: str
    direction: str
    stb_seq_id: int
    stb_index: str
    stb_confirmed: bool
    cooldown: bool


class STBSequenceLogger:
    """
    Runtime STB 시퀀스 로거
    
    핵심 원칙:
    - 순서만 관측 (판단 ❌)
    - θ 미사용
    - 결과 미참조
    """
    
    def __init__(self, log_path: str = LOG_PATH):
        self.log_path = log_path
        self.stb_seq_id = 0
        self.last_stb_time: Optional[datetime] = None
        self.last_direction: Optional[str] = None
        self.cooldown_until: Optional[datetime] = None
        
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    def _parse_time(self, ts: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except:
            return None
    
    def _is_in_cooldown(self, now: datetime) -> bool:
        if self.cooldown_until is None:
            return False
        return now < self.cooldown_until
    
    def set_cooldown(self, duration_minutes: int = 5):
        """DEATH 발생 시 쿨다운 설정"""
        self.cooldown_until = datetime.now()
    
    def clear_cooldown(self):
        self.cooldown_until = None
    
    def compute_stb_index(
        self,
        trade_id: int,
        timestamp: str,
        direction: str,
        stb_confirmed: bool
    ) -> STBLogEntry:
        """
        STB 시퀀스 계산 (Runtime-safe)
        
        로직:
        - STB_confirmed가 False면 로깅만
        - 30분 초과 또는 방향 변경 → 새 시퀀스
        - 그 외 → re-entry
        """
        now = self._parse_time(timestamp)
        if now is None:
            now = datetime.now()
        
        in_cooldown = self._is_in_cooldown(now)
        
        if not stb_confirmed:
            return STBLogEntry(
                trade_id=trade_id,
                timestamp=timestamp,
                direction=direction,
                stb_seq_id=self.stb_seq_id,
                stb_index="N/A",
                stb_confirmed=False,
                cooldown=in_cooldown
            )
        
        new_sequence = False
        
        if self.last_stb_time is None:
            new_sequence = True
        else:
            time_diff = (now - self.last_stb_time).total_seconds() / 60
            if time_diff > WINDOW_MINUTES:
                new_sequence = True
            elif direction != self.last_direction:
                new_sequence = True
        
        if new_sequence:
            self.stb_seq_id += 1
            stb_index = "first"
        else:
            stb_index = "re-entry"
        
        self.last_stb_time = now
        self.last_direction = direction
        
        entry = STBLogEntry(
            trade_id=trade_id,
            timestamp=timestamp,
            direction=direction,
            stb_seq_id=self.stb_seq_id,
            stb_index=stb_index,
            stb_confirmed=True,
            cooldown=in_cooldown
        )
        
        return entry
    
    def log(self, entry: STBLogEntry):
        """JSONL 형식으로 로그 저장"""
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(asdict(entry)) + '\n')
    
    def compute_and_log(
        self,
        trade_id: int,
        timestamp: str,
        direction: str,
        stb_confirmed: bool
    ) -> STBLogEntry:
        """계산 + 로깅 원스텝"""
        entry = self.compute_stb_index(trade_id, timestamp, direction, stb_confirmed)
        self.log(entry)
        return entry
    
    def is_ignition_candidate(self, entry: STBLogEntry) -> bool:
        """
        IGNITION_CANDIDATE 판정 (v1.0)
        
        조건:
        - stb_index == "first"
        - stb_confirmed == True
        - cooldown == False
        
        이것은 예측이 아니라 권한 부여다.
        """
        return (
            entry.stb_index == "first" and
            entry.stb_confirmed and
            not entry.cooldown
        )


def test_logger():
    """로거 테스트"""
    logger = STBSequenceLogger("/tmp/test_stb_log.jsonl")
    
    test_cases = [
        (1, "2026-01-25T10:00:00", "SHORT", True),
        (2, "2026-01-25T10:05:00", "SHORT", True),
        (3, "2026-01-25T10:10:00", "SHORT", True),
        (4, "2026-01-25T11:00:00", "SHORT", True),
        (5, "2026-01-25T11:05:00", "LONG", True),
    ]
    
    print("STB Sequence Logger Test")
    print("=" * 50)
    
    for tid, ts, direction, confirmed in test_cases:
        entry = logger.compute_stb_index(tid, ts, direction, confirmed)
        candidate = "🔥 IGNITION_CANDIDATE" if logger.is_ignition_candidate(entry) else ""
        print(f"ID={tid} seq={entry.stb_seq_id} index={entry.stb_index:8} {candidate}")
    
    print("\nExpected:")
    print("  ID=1: seq=1, first (new)")
    print("  ID=2: seq=1, re-entry")
    print("  ID=3: seq=1, re-entry")
    print("  ID=4: seq=2, first (>30min)")
    print("  ID=5: seq=3, first (direction change)")


if __name__ == "__main__":
    test_logger()
