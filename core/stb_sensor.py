"""
STB Sensor
==========

STB = 점화 센서 (Ignition Sensor)
STB 자체는 실행 신호가 아니다.
STB는 "상태 탐색 시작"을 알리는 센서일 뿐이다.

핵심:
- STB 즉시 실행 (θ=0) = 0% 승률
- STB + θ≥1 = 100% 승률
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class STBSignal:
    """STB 신호"""
    name: str
    direction: str  # "LONG" or "SHORT"
    strength: float = 1.0
    
    @property
    def is_long(self) -> bool:
        return self.direction == "LONG"
    
    @property
    def is_short(self) -> bool:
        return self.direction == "SHORT"


STB_SIGNALS = {
    "STB숏": {"direction": "SHORT", "tier": 1},
    "STB롱": {"direction": "LONG", "tier": 1},
    "SCALP_A": {"direction": "BOTH", "tier": 2},
    "HUNT_1": {"direction": "BOTH", "tier": 2},
}


def parse_stb_signal(signal_name: str) -> Optional[STBSignal]:
    """신호 이름을 STBSignal로 파싱"""
    if signal_name not in STB_SIGNALS:
        return None
    
    config = STB_SIGNALS[signal_name]
    
    direction = config.get("direction", "BOTH")
    if direction == "BOTH":
        if "숏" in signal_name or "SHORT" in signal_name.upper():
            direction = "SHORT"
        elif "롱" in signal_name or "LONG" in signal_name.upper():
            direction = "LONG"
    
    return STBSignal(
        name=signal_name,
        direction=direction,
    )


def is_stb_signal(signal_name: str) -> bool:
    """STB 신호인지 확인"""
    return signal_name in STB_SIGNALS or signal_name.startswith("STB")
