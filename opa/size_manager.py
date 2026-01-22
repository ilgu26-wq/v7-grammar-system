"""
Size Manager
============

Position Size 관리

Size 정의:
- SMALL = 1x
- MEDIUM = 2x
- LARGE = 4x
"""

from dataclasses import dataclass
from typing import Dict


SIZE_MULTIPLIER = {
    "SMALL": 1.0,
    "MEDIUM": 2.0,
    "LARGE": 4.0,
}


@dataclass
class AccountConfig:
    """계좌 설정"""
    base_size: float = 1.0
    max_size: float = 4.0
    theta_size_override: Dict[int, str] = None
    
    def __post_init__(self):
        if self.theta_size_override is None:
            self.theta_size_override = {}


def get_position_size(theta: int, account: AccountConfig = None) -> float:
    """θ에 따른 포지션 크기 반환"""
    from .policy_v74 import get_size, get_size_multiplier
    
    size_name = get_size(theta)
    
    if account and theta in account.theta_size_override:
        size_name = account.theta_size_override[theta]
    
    multiplier = get_size_multiplier(size_name)
    
    base = account.base_size if account else 1.0
    max_size = account.max_size if account else 4.0
    
    result = base * multiplier
    return min(result, max_size)


def get_size_for_theta(theta: int) -> str:
    """θ에 따른 Size 이름 반환"""
    from .policy_v74 import get_size
    return get_size(theta)
