"""
Retry Manager
=============

θ=2 Retry 로직 관리

Retry 허용 조건:
- θ=2 상태
- impulse_count > 2
- recovery_time < 4
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RetryState:
    """Retry 상태"""
    zone: str
    attempts: int = 0
    max_attempts: int = 1
    last_result: str = None


class RetryManager:
    """Retry 관리자"""
    
    def __init__(self, max_attempts: int = 1):
        self.max_attempts = max_attempts
        self.zones: dict[str, RetryState] = {}
    
    def can_retry(self, zone: str, theta: int, 
                  impulse_count: int = 0, recovery_time: float = 0) -> bool:
        """Retry 가능 여부 확인"""
        from .policy_v74 import can_retry as policy_can_retry
        
        if not policy_can_retry(theta, impulse_count, recovery_time):
            return False
        
        state = self.zones.get(zone)
        if state is None:
            return True
        
        return state.attempts < self.max_attempts
    
    def record_attempt(self, zone: str, result: str):
        """시도 기록"""
        if zone not in self.zones:
            self.zones[zone] = RetryState(zone=zone)
        
        self.zones[zone].attempts += 1
        self.zones[zone].last_result = result
    
    def reset_zone(self, zone: str):
        """존 리셋"""
        if zone in self.zones:
            del self.zones[zone]
    
    def reset_all(self):
        """전체 리셋"""
        self.zones = {}
