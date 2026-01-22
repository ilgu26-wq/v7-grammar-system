# experiments/configs.py
# Experimental configurations (NON-CORE)

from dataclasses import dataclass

@dataclass(frozen=True)
class G3DefenseConfig:
    """
    Optional SL defense (NON-PHYSICS).
    Purpose: reduce tail-loss.
    """
    LWS_BARS: int = 4
    LWS_MFE_THRESHOLD: float = 1.5
    DEFENSE_SL: int = 12
    DEFAULT_SL: int = 30


@dataclass(frozen=True)
class MFE5HarvestConfig:
    """
    Harvest-optimized mode (NON-PHYSICS).
    WARNING: Removes physical guarantees.
    """
    MFE_THRESHOLD: int = 5
    TRAIL_OFFSET: float = 1.5
