"""
IGNITION GUARD v1.0
====================
목적: IGNITION_CANDIDATE에 대한 제약 완화만 담당

핵심 원칙:
- IGNITION_CANDIDATE는 판단이 아니다
- IGNITION_CANDIDATE는 행동을 직접 유발하지 않는다
- OPA는 제약만 조정한다
- θ / WR / MFE는 절대 runtime으로 역류하지 않는다
- 정책 변경은 항상 수동 커밋

허용:
- SIZE_DOWN 차단 여부 조절
- 제약 완화 플래그 설정

금지:
- 신호 생성 ❌
- 진입 결정 ❌
- 방향 변경 ❌
- 행동 추가 ❌
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class PrivilegeLevel(Enum):
    STANDARD = "STANDARD"
    ELEVATED = "ELEVATED"


@dataclass
class PolicyContext:
    """OPA 정책 컨텍스트"""
    privilege: PrivilegeLevel = PrivilegeLevel.STANDARD
    allow_size_down_skip: bool = False
    reason: str = ""


class IgnitionGuard:
    """
    IGNITION_CANDIDATE 권한 관리자
    
    이것은 예측이 아니라 권한 부여다.
    
    입력:
    - stb_index: "first" / "re-entry"
    - stb_confirmed: True / False
    - in_cooldown: True / False
    
    출력:
    - PolicyContext (제약 완화 수준만)
    """
    
    def __init__(self):
        self.total_first_count = 0
        self.total_reentry_count = 0
    
    def evaluate(
        self,
        stb_index: str,
        stb_confirmed: bool,
        in_cooldown: bool
    ) -> PolicyContext:
        """
        IGNITION_CANDIDATE 평가
        
        조건 (v1.0):
        - stb_index == "first"
        - stb_confirmed == True
        - in_cooldown == False
        
        효과:
        - ELEVATED 권한 부여
        - SIZE_DOWN 차단 해제
        """
        
        is_candidate = (
            stb_index == "first" and
            stb_confirmed and
            not in_cooldown
        )
        
        if stb_index == "first":
            self.total_first_count += 1
        elif stb_index == "re-entry":
            self.total_reentry_count += 1
        
        if is_candidate:
            return PolicyContext(
                privilege=PrivilegeLevel.ELEVATED,
                allow_size_down_skip=True,
                reason="IGNITION_CANDIDATE: first opportunity in sequence"
            )
        
        return PolicyContext(
            privilege=PrivilegeLevel.STANDARD,
            allow_size_down_skip=False,
            reason=self._get_rejection_reason(stb_index, stb_confirmed, in_cooldown)
        )
    
    def _get_rejection_reason(
        self,
        stb_index: str,
        stb_confirmed: bool,
        in_cooldown: bool
    ) -> str:
        if in_cooldown:
            return "IN_COOLDOWN: waiting for structure recovery"
        if not stb_confirmed:
            return "STB_NOT_CONFIRMED: no valid STB signal"
        if stb_index != "first":
            return f"RE_ENTRY: position {stb_index} in sequence"
        return "STANDARD"
    
    def get_stats(self) -> dict:
        return {
            "total_first": self.total_first_count,
            "total_reentry": self.total_reentry_count,
            "first_ratio": self.total_first_count / max(1, self.total_first_count + self.total_reentry_count)
        }


def test_ignition_guard():
    """IgnitionGuard 테스트"""
    guard = IgnitionGuard()
    
    test_cases = [
        ("first", True, False, "ELEVATED"),
        ("re-entry", True, False, "STANDARD"),
        ("first", True, True, "STANDARD"),
        ("first", False, False, "STANDARD"),
        ("N/A", False, False, "STANDARD"),
    ]
    
    print("IGNITION GUARD Test")
    print("=" * 60)
    
    for stb_index, confirmed, cooldown, expected in test_cases:
        ctx = guard.evaluate(stb_index, confirmed, cooldown)
        status = "✅" if ctx.privilege.value == expected else "❌"
        print(f"{status} index={stb_index:8} conf={confirmed} cool={cooldown} → {ctx.privilege.value}")
        print(f"   reason: {ctx.reason}")
    
    print(f"\nStats: {guard.get_stats()}")


if __name__ == "__main__":
    test_ignition_guard()
