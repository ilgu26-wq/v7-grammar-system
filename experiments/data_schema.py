"""
V7 Position Lifecycle Data Schema
=================================

bar 단위 물리량 측정을 위한 새로운 데이터 스키마
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
import json


class ExitType(Enum):
    TRAIL_WIN = "trail_win"      # MFE>=7 후 트레일링 익절
    TP_HIT = "tp_hit"            # 고정 TP 도달
    SL_FULL = "sl_full"          # 기본 SL (-30pt)
    SL_DEFENSE = "sl_defense"    # 방어 SL (-12pt, LWS)
    TIMEOUT = "timeout"          # 시간 초과
    MANUAL = "manual"            # 수동 종료


@dataclass
class PositionLifecycle:
    """
    포지션 생명주기 데이터 (bar 단위 추적)
    
    핵심: MFE/MAE path로 "언제 상태가 변했는가" 관측 가능
    """
    # 식별자
    trade_id: str
    
    # 진입 정보
    direction: str                    # 'LONG' or 'SHORT'
    entry_price: float
    entry_bar_idx: int
    entry_time: str
    
    # 진입 조건 (STB)
    stb_ratio: float                  # 배율
    stb_channel_pct: float            # 채널%
    stb_body_z: float                 # body z-score
    
    # bar 단위 경로 (핵심!)
    mfe_path: List[float] = field(default_factory=list)  # 각 봉에서의 MFE
    mae_path: List[float] = field(default_factory=list)  # 각 봉에서의 MAE
    
    # 최종 값
    max_mfe: float = 0.0
    max_mae: float = 0.0
    bars_held: int = 0
    
    # 상태 전이
    mfe_threshold_bar: Optional[int] = None  # MFE>=7 도달한 봉
    trail_active: bool = False
    lws_triggered: bool = False              # Loss Warning State
    lws_bar: Optional[int] = None
    
    # 종료
    exit_type: str = ""
    exit_price: float = 0.0
    exit_bar_idx: int = 0
    pnl: float = 0.0
    
    # Persistence Score 경로 (계산됨)
    persistence_path: List[float] = field(default_factory=list)
    
    def add_bar(self, mfe: float, mae: float):
        """새 봉 데이터 추가"""
        self.mfe_path.append(mfe)
        self.mae_path.append(mae)
        self.bars_held = len(self.mfe_path)
        
        if mfe > self.max_mfe:
            self.max_mfe = mfe
        if mae > self.max_mae:
            self.max_mae = mae
        
        # 상태 전이 체크
        if mfe >= 7.0 and self.mfe_threshold_bar is None:
            self.mfe_threshold_bar = self.bars_held
            self.trail_active = True
        
        # LWS 체크
        if self.bars_held >= 4 and self.max_mfe < 1.5 and not self.lws_triggered:
            self.lws_triggered = True
            self.lws_bar = self.bars_held
    
    def to_dict(self) -> dict:
        return {
            'trade_id': self.trade_id,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'entry_bar_idx': self.entry_bar_idx,
            'entry_time': self.entry_time,
            'stb_ratio': self.stb_ratio,
            'stb_channel_pct': self.stb_channel_pct,
            'stb_body_z': self.stb_body_z,
            'mfe_path': self.mfe_path,
            'mae_path': self.mae_path,
            'max_mfe': self.max_mfe,
            'max_mae': self.max_mae,
            'bars_held': self.bars_held,
            'mfe_threshold_bar': self.mfe_threshold_bar,
            'trail_active': self.trail_active,
            'lws_triggered': self.lws_triggered,
            'lws_bar': self.lws_bar,
            'exit_type': self.exit_type,
            'exit_price': self.exit_price,
            'exit_bar_idx': self.exit_bar_idx,
            'pnl': self.pnl,
            'persistence_path': self.persistence_path
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PositionLifecycle':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PersistenceCalculator:
    """
    Persistence Score 정식 계산기
    
    공식:
    PS = w1 * normalize(mfe) - w2 * normalize(mae) + w3 * stability + w4 * time_survival
    """
    
    # 가중치 (고정)
    W_MFE = 0.35      # 에너지 축적
    W_MAE = 0.30      # 반작용 압력
    W_STABILITY = 0.20  # 상태 흔들림
    W_TIME = 0.15     # 시간 유지
    
    # 정규화 기준
    MFE_NORM = 20.0   # MFE 정규화 기준
    MAE_NORM = 30.0   # MAE 정규화 기준
    
    def calculate_bar(self, mfe: float, mae: float, mfe_path: List[float], bars: int) -> float:
        """
        단일 봉에서의 Persistence Score 계산
        """
        # 1. MFE 점수 (높을수록 좋음)
        mfe_score = min(mfe / self.MFE_NORM, 1.0)
        
        # 2. MAE 점수 (높을수록 나쁨)
        mae_score = min(mae / self.MAE_NORM, 1.0)
        
        # 3. 안정성 (MFE 변동성)
        if len(mfe_path) >= 2:
            mfe_changes = [abs(mfe_path[i] - mfe_path[i-1]) for i in range(1, len(mfe_path))]
            avg_change = sum(mfe_changes) / len(mfe_changes)
            stability = max(0, 1 - avg_change / 5.0)  # 5pt 이상 변동 = 불안정
        else:
            stability = 0.5
        
        # 4. 시간 생존
        if bars <= 3:
            time_survival = 0.3  # 아직 판단 이름
        elif bars <= 10:
            time_survival = 0.7
        else:
            time_survival = 1.0
        
        # 종합
        score = (
            self.W_MFE * mfe_score
            - self.W_MAE * mae_score
            + self.W_STABILITY * stability
            + self.W_TIME * time_survival
        )
        
        return round(score, 4)
    
    def calculate_path(self, position: PositionLifecycle) -> List[float]:
        """
        전체 경로에 대한 Persistence Score 계산
        """
        scores = []
        for i in range(len(position.mfe_path)):
            mfe = position.mfe_path[i]
            mae = position.mae_path[i]
            mfe_path_so_far = position.mfe_path[:i+1]
            bars = i + 1
            
            score = self.calculate_bar(mfe, mae, mfe_path_so_far, bars)
            scores.append(score)
        
        return scores
    
    def detect_collapse(self, persistence_path: List[float], threshold: float = 0.3) -> Optional[int]:
        """
        상태 붕괴 시점 감지
        
        Returns: 붕괴 시작 봉 인덱스 (없으면 None)
        """
        if len(persistence_path) < 2:
            return None
        
        for i in range(1, len(persistence_path)):
            if persistence_path[i] < threshold:
                # 이전 봉에서 급락했는지 체크
                if persistence_path[i-1] >= threshold + 0.2:
                    return i
        
        return None


def demo():
    """데모 실행"""
    print("=" * 60)
    print("V7 Position Lifecycle Data Schema")
    print("=" * 60)
    
    # 예시 포지션 생성
    pos = PositionLifecycle(
        trade_id="T001",
        direction="SHORT",
        entry_price=21580.0,
        entry_bar_idx=100,
        entry_time="2026-01-22 10:30:00",
        stb_ratio=1.8,
        stb_channel_pct=85.0,
        stb_body_z=1.5
    )
    
    # 시뮬레이션된 bar 데이터
    bar_data = [
        (1.2, 0.8),   # bar 1: MFE=1.2, MAE=0.8
        (3.4, 1.5),   # bar 2
        (5.9, 2.0),   # bar 3
        (7.3, 2.5),   # bar 4: MFE >= 7 도달!
        (9.1, 3.0),   # bar 5
        (8.5, 3.5),   # bar 6
        (10.0, 4.0),  # bar 7
    ]
    
    for mfe, mae in bar_data:
        pos.add_bar(mfe, mae)
    
    # Persistence Score 계산
    calc = PersistenceCalculator()
    pos.persistence_path = calc.calculate_path(pos)
    
    # 종료 설정
    pos.exit_type = ExitType.TRAIL_WIN.value
    pos.exit_price = 21570.0
    pos.exit_bar_idx = 107
    pos.pnl = 10.0
    
    print("\n📊 Position Lifecycle:")
    print(f"  Direction: {pos.direction}")
    print(f"  Entry: {pos.entry_price}")
    print(f"  Bars Held: {pos.bars_held}")
    print(f"  Max MFE: {pos.max_mfe}")
    print(f"  Max MAE: {pos.max_mae}")
    print(f"  MFE Threshold Bar: {pos.mfe_threshold_bar}")
    print(f"  Trail Active: {pos.trail_active}")
    print(f"  LWS Triggered: {pos.lws_triggered}")
    
    print("\n📈 MFE Path:", pos.mfe_path)
    print("📉 MAE Path:", pos.mae_path)
    print("🔋 Persistence Path:", pos.persistence_path)
    
    # 붕괴 감지
    collapse_bar = calc.detect_collapse(pos.persistence_path)
    print(f"\n⚠️ Collapse Bar: {collapse_bar}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    demo()
