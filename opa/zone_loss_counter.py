"""
Zone Loss Counter - 연속 손실 추적 (zone 기준)

⚠️ 핵심: 연속 손실은 전역 PnL 기준이 아니라 zone 기준!

loss_key = (state, direction, zone_id)

동일 STATE + 동일 방향 + 동일 구간에서만 누적
"""

from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta


@dataclass
class ZoneKey:
    """Zone 식별자"""
    state: str          # 예: "OVERBOUGHT", "OVERSOLD"
    direction: str      # "LONG" or "SHORT"
    zone_id: str        # 가격 구간 ID (예: "21500-21600")


@dataclass
class LossRecord:
    """손실 기록"""
    count: int
    last_loss_time: datetime
    last_reset_time: datetime


class ZoneLossCounter:
    """
    Zone 기준 연속 손실 카운터
    
    특징:
    - 동일 zone에서만 누적
    - 다른 zone 진입 시 리셋 없음 (독립 추적)
    - 승리 시 해당 zone 카운터 리셋
    - 일일 리셋 옵션
    """
    
    def __init__(self, auto_reset_hours: int = 24):
        self.counters: Dict[Tuple[str, str, str], LossRecord] = {}
        self.auto_reset_hours = auto_reset_hours
    
    def _make_key(self, zone: ZoneKey) -> Tuple[str, str, str]:
        return (zone.state, zone.direction, zone.zone_id)
    
    def _check_auto_reset(self, record: LossRecord) -> bool:
        """자동 리셋 체크"""
        if self.auto_reset_hours <= 0:
            return False
        elapsed = datetime.now() - record.last_loss_time
        return elapsed > timedelta(hours=self.auto_reset_hours)
    
    def get_consecutive_loss(self, zone: ZoneKey) -> int:
        """해당 zone의 연속 손실 수 반환"""
        key = self._make_key(zone)
        
        if key not in self.counters:
            return 0
        
        record = self.counters[key]
        
        # 자동 리셋 체크
        if self._check_auto_reset(record):
            self.reset_zone(zone)
            return 0
        
        return record.count
    
    def record_loss(self, zone: ZoneKey):
        """손실 기록"""
        key = self._make_key(zone)
        now = datetime.now()
        
        if key not in self.counters:
            self.counters[key] = LossRecord(
                count=1,
                last_loss_time=now,
                last_reset_time=now
            )
        else:
            record = self.counters[key]
            
            # 자동 리셋 후 첫 손실
            if self._check_auto_reset(record):
                self.counters[key] = LossRecord(
                    count=1,
                    last_loss_time=now,
                    last_reset_time=now
                )
            else:
                record.count += 1
                record.last_loss_time = now
    
    def record_win(self, zone: ZoneKey):
        """승리 기록 → 해당 zone 카운터 리셋"""
        self.reset_zone(zone)
    
    def reset_zone(self, zone: ZoneKey):
        """특정 zone 카운터 리셋"""
        key = self._make_key(zone)
        if key in self.counters:
            del self.counters[key]
    
    def reset_all(self):
        """전체 리셋"""
        self.counters.clear()
    
    def get_all_zones_with_losses(self) -> Dict[Tuple[str, str, str], int]:
        """손실 있는 모든 zone 반환"""
        return {k: v.count for k, v in self.counters.items() if v.count > 0}
    
    def get_stats(self) -> Dict:
        """통계"""
        return {
            "active_zones": len(self.counters),
            "zones_with_consecutive_loss": sum(1 for v in self.counters.values() if v.count >= 2),
            "total_losses_tracked": sum(v.count for v in self.counters.values()),
        }


def calculate_zone_id(price: float, zone_size: float = 100.0) -> str:
    """가격으로 zone_id 계산"""
    zone_start = int(price // zone_size) * zone_size
    zone_end = zone_start + zone_size
    return f"{zone_start:.0f}-{zone_end:.0f}"
