"""
OPA v7.4 CONSTITUTION
=====================

DO NOT OPTIMIZE. DO NOT MODIFY.

이 파일은 V7 시스템의 "헌법"이다.
실험 코드에서 이 파일을 import하거나 수정하는 것은 금지된다.

2026-01-22 확정
"""

THETA_POLICY = {
    0: {
        "allow": False,
        "reason": "No state certified",
    },
    1: {
        "allow": True,
        "size": "SMALL",
        "retry": False,
        "trailing": False,
        "exit": "FIXED_TP",
        "tp": 20,
        "sl": 12,
    },
    2: {
        "allow": True,
        "size": ["SMALL", "MEDIUM"],
        "retry": {
            "enabled": True,
            "conditions": {
                "impulse_count": (">", 2),
                "recovery_time": ("<", 4),
            },
        },
        "trailing": False,
        "exit": "FIXED_TP",
        "tp": 20,
        "sl": 12,
    },
    3: {
        "allow": True,
        "size": "LARGE",
        "retry": True,
        "trailing": "OPTIONAL",
        "exit": "FIXED_TP_OR_EXTENSION",
        "tp": 20,
        "sl": 12,
    },
}

SIZE_MULTIPLIER = {
    "SMALL": 1.0,
    "MEDIUM": 2.0,
    "LARGE": 4.0,
}

TIER1_SIGNALS = [
    "STB숏",
    "STB롱",
    "RESIST_zscore_0.5",
    "RESIST_zscore_1.0",
    "RESIST_zscore_1.5",
]

BLACKLIST_SIGNALS = [
    "매수스팟",
    "매도스팟",
    "빗각버팀",
    "저점상승",
    "횡보예상_v1",
]


def get_policy(theta: int) -> dict:
    """θ값에 따른 정책 반환"""
    if theta >= 3:
        return THETA_POLICY[3]
    return THETA_POLICY.get(theta, THETA_POLICY[0])


def is_allowed(theta: int) -> bool:
    """θ값이 실행 허용되는지 확인"""
    return get_policy(theta).get("allow", False)


def get_size(theta: int, preference: str = None) -> str:
    """θ값에 따른 Size 반환"""
    policy = get_policy(theta)
    size_config = policy.get("size", "SMALL")
    
    if isinstance(size_config, list):
        if preference and preference in size_config:
            return preference
        return size_config[0]
    
    return size_config


def get_size_multiplier(size: str) -> float:
    """Size에 따른 배율 반환"""
    return SIZE_MULTIPLIER.get(size, 1.0)


def can_retry(theta: int, impulse_count: int = 0, recovery_time: float = 0) -> bool:
    """Retry 허용 여부 확인"""
    policy = get_policy(theta)
    retry_config = policy.get("retry", False)
    
    if retry_config is True:
        return True
    
    if retry_config is False:
        return False
    
    if isinstance(retry_config, dict) and retry_config.get("enabled"):
        conditions = retry_config.get("conditions", {})
        
        impulse_ok = True
        recovery_ok = True
        
        if "impulse_count" in conditions:
            op, val = conditions["impulse_count"]
            if op == ">":
                impulse_ok = impulse_count > val
        
        if "recovery_time" in conditions:
            op, val = conditions["recovery_time"]
            if op == "<":
                recovery_ok = recovery_time < val
        
        return impulse_ok and recovery_ok
    
    return False


def can_trail(theta: int) -> bool:
    """Trailing 허용 여부 확인"""
    policy = get_policy(theta)
    return policy.get("trailing", False) != False
