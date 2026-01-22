"""
H5 Experiment: 재진입 vs 유지 측정 비교

가설: 재진입을 시도하는 전략보다 상태 유지 측정 + 관리 전략이 우월하다

실험 설계:
- 전략 R: 재진입 허용 (STB 재발생 시 추가 진입)
- 전략 P: 단일 진입 + 유지 점수 기반 관리

검증 지표: 총 PnL, 거래 수, MDD, EV 안정성
"""

from dataclasses import dataclass
from typing import List, Optional, Dict
from enum import Enum
import json


class PersistenceState(Enum):
    HEALTHY = "healthy"           # 유지 양호
    WARNING = "warning"           # 유지 약화
    CRITICAL = "critical"         # 붕괴 임박
    COLLAPSED = "collapsed"       # 붕괴 완료


@dataclass
class TradeSnapshot:
    """진입 시점 스냅샷"""
    idx: int
    entry_price: float
    direction: str  # 'LONG' or 'SHORT'
    
    
@dataclass
class BarData:
    """봉 데이터"""
    idx: int
    high: float
    low: float
    close: float
    mfe: float = 0.0
    mae: float = 0.0


class PersistenceScore:
    """
    상태 유지 점수 계산기
    
    4대 축:
    A. 에너지 축 (Energy Persistence) - MFE slope
    B. 손실 압력 축 (Loss Pressure) - MAE/SL ratio
    C. 시간 축 (Temporal Integrity) - bars + early MFE
    D. 구조 축 (Structural Continuity) - 반증 이벤트
    """
    
    # 가중치 (조정 가능)
    W_ENERGY = 0.35
    W_LOSS_PRESSURE = 0.30
    W_TIME = 0.20
    W_STRUCTURE = 0.15
    
    # 임계값
    SL = 30.0
    MFE_THRESHOLD = 7.0
    LWS_BARS = 4
    LWS_MFE = 1.5
    
    def __init__(self):
        self.history: List[float] = []
    
    def calculate_energy_score(self, mfe: float, mfe_prev: float) -> float:
        """
        에너지 축: MFE 방향성
        MFE 증가 = 양수, MFE 감소 = 음수
        """
        mfe_slope = mfe - mfe_prev
        
        if mfe >= self.MFE_THRESHOLD:
            return 1.0  # 상태 전이 완료 = 최고 점수
        elif mfe_slope >= 0:
            return 0.5 + (mfe / self.MFE_THRESHOLD) * 0.5
        else:
            return max(-1.0, mfe_slope / 5.0)
    
    def calculate_loss_pressure_score(self, mae: float) -> float:
        """
        손실 압력 축: MAE/SL 비율
        낮을수록 좋음
        """
        ratio = mae / self.SL
        
        if ratio < 0.4:
            return 1.0  # 유지 양호
        elif ratio < 0.6:
            return 0.5  # 경고
        elif ratio < 0.8:
            return -0.5  # 위험
        else:
            return -1.0  # 붕괴 임박
    
    def calculate_time_score(self, bars: int, max_mfe: float) -> float:
        """
        시간 축: LWS (Loss Warning State)
        4봉 이상 + MFE < 1.5 = 유지 약화
        """
        if bars >= self.LWS_BARS and max_mfe < self.LWS_MFE:
            return -0.8  # LWS 트리거
        elif bars < 3:
            return 0.3  # 아직 판단 이름
        else:
            return 0.5  # 정상 진행
    
    def calculate_structure_score(self, structural_rejection: bool) -> float:
        """
        구조 축: 반증 이벤트
        반증 없음 = 유지, 반증 발생 = 종료
        """
        return -1.0 if structural_rejection else 1.0
    
    def calculate(self, mfe: float, mfe_prev: float, mae: float, 
                  bars: int, max_mfe: float, structural_rejection: bool = False) -> Dict:
        """
        종합 유지 점수 계산
        """
        energy = self.calculate_energy_score(mfe, mfe_prev)
        loss_pressure = self.calculate_loss_pressure_score(mae)
        time_score = self.calculate_time_score(bars, max_mfe)
        structure = self.calculate_structure_score(structural_rejection)
        
        total = (
            self.W_ENERGY * energy +
            self.W_LOSS_PRESSURE * loss_pressure +
            self.W_TIME * time_score +
            self.W_STRUCTURE * structure
        )
        
        # 상태 판정
        if total >= 0.5:
            state = PersistenceState.HEALTHY
        elif total >= 0:
            state = PersistenceState.WARNING
        elif total >= -0.5:
            state = PersistenceState.CRITICAL
        else:
            state = PersistenceState.COLLAPSED
        
        self.history.append(total)
        
        return {
            'score': round(total, 3),
            'state': state.value,
            'components': {
                'energy': round(energy, 3),
                'loss_pressure': round(loss_pressure, 3),
                'time': round(time_score, 3),
                'structure': round(structure, 3)
            }
        }
    
    def should_exit_early(self) -> bool:
        """
        조기 종료 권고
        score << 0 상태 지속 시
        """
        if len(self.history) < 2:
            return False
        
        recent = self.history[-2:]
        return all(s < -0.5 for s in recent)


class StrategyR:
    """
    재진입 전략 (R)
    STB 재발생 시 추가 진입 허용
    """
    def __init__(self, sl=30, tp=20):
        self.sl = sl
        self.tp = tp
        self.positions: List[TradeSnapshot] = []
        self.trades: List[Dict] = []
        self.total_pnl = 0
        
    def on_stb_signal(self, idx: int, price: float, direction: str):
        """STB 신호 발생 시 진입"""
        self.positions.append(TradeSnapshot(idx, price, direction))
        
    def on_bar(self, bar: BarData):
        """봉 업데이트 - 모든 포지션 체크"""
        closed = []
        for pos in self.positions:
            if pos.direction == 'LONG':
                pnl = bar.close - pos.entry_price
                if pnl <= -self.sl:
                    self.trades.append({'type': 'LOSS', 'pnl': -self.sl, 'bars': bar.idx - pos.idx})
                    self.total_pnl -= self.sl
                    closed.append(pos)
                elif pnl >= self.tp:
                    self.trades.append({'type': 'WIN', 'pnl': self.tp, 'bars': bar.idx - pos.idx})
                    self.total_pnl += self.tp
                    closed.append(pos)
            else:
                pnl = pos.entry_price - bar.close
                if pnl <= -self.sl:
                    self.trades.append({'type': 'LOSS', 'pnl': -self.sl, 'bars': bar.idx - pos.idx})
                    self.total_pnl -= self.sl
                    closed.append(pos)
                elif pnl >= self.tp:
                    self.trades.append({'type': 'WIN', 'pnl': self.tp, 'bars': bar.idx - pos.idx})
                    self.total_pnl += self.tp
                    closed.append(pos)
        
        for pos in closed:
            self.positions.remove(pos)
    
    def get_stats(self) -> Dict:
        wins = sum(1 for t in self.trades if t['type'] == 'WIN')
        losses = sum(1 for t in self.trades if t['type'] == 'LOSS')
        return {
            'strategy': 'R (재진입)',
            'total_trades': len(self.trades),
            'wins': wins,
            'losses': losses,
            'win_rate': wins / len(self.trades) * 100 if self.trades else 0,
            'total_pnl': self.total_pnl,
            'ev': self.total_pnl / len(self.trades) if self.trades else 0
        }


class StrategyP:
    """
    유지 관리 전략 (P)
    단일 진입 + Persistence Score 기반 관리
    """
    def __init__(self, sl=30, tp=20, defense_sl=12):
        self.sl = sl
        self.tp = tp
        self.defense_sl = defense_sl
        self.position: Optional[TradeSnapshot] = None
        self.persistence = PersistenceScore()
        self.trades: List[Dict] = []
        self.total_pnl = 0
        self.max_mfe = 0
        self.mfe_prev = 0
        self.bars_since_entry = 0
        
    def on_stb_signal(self, idx: int, price: float, direction: str):
        """STB 신호 발생 시 진입 (포지션 없을 때만)"""
        if self.position is None:
            self.position = TradeSnapshot(idx, price, direction)
            self.persistence = PersistenceScore()
            self.max_mfe = 0
            self.mfe_prev = 0
            self.bars_since_entry = 0
    
    def on_bar(self, bar: BarData):
        """봉 업데이트 - 유지 점수 기반 관리"""
        if self.position is None:
            return
        
        self.bars_since_entry += 1
        
        # MFE/MAE 계산
        if self.position.direction == 'LONG':
            mfe = bar.high - self.position.entry_price
            mae = self.position.entry_price - bar.low
            current_pnl = bar.close - self.position.entry_price
        else:
            mfe = self.position.entry_price - bar.low
            mae = bar.high - self.position.entry_price
            current_pnl = self.position.entry_price - bar.close
        
        self.max_mfe = max(self.max_mfe, mfe)
        
        # 유지 점수 계산
        ps = self.persistence.calculate(
            mfe=mfe,
            mfe_prev=self.mfe_prev,
            mae=mae,
            bars=self.bars_since_entry,
            max_mfe=self.max_mfe
        )
        
        self.mfe_prev = mfe
        
        # SL 동적 조정 (G3 로직)
        current_sl = self.sl
        if self.bars_since_entry >= 4 and self.max_mfe < 1.5:
            current_sl = self.defense_sl  # LWS → SL 축소
        
        # 종료 조건 체크
        if current_pnl <= -current_sl:
            self.trades.append({
                'type': 'LOSS', 
                'pnl': -current_sl, 
                'bars': self.bars_since_entry,
                'final_ps': ps['score']
            })
            self.total_pnl -= current_sl
            self.position = None
        elif self.max_mfe >= 7 and current_pnl <= self.max_mfe - 1.5:
            # 트레일링 종료
            final_pnl = self.max_mfe - 1.5
            self.trades.append({
                'type': 'WIN', 
                'pnl': final_pnl, 
                'bars': self.bars_since_entry,
                'final_ps': ps['score']
            })
            self.total_pnl += final_pnl
            self.position = None
        elif current_pnl >= self.tp:
            self.trades.append({
                'type': 'WIN', 
                'pnl': self.tp, 
                'bars': self.bars_since_entry,
                'final_ps': ps['score']
            })
            self.total_pnl += self.tp
            self.position = None
    
    def get_stats(self) -> Dict:
        wins = sum(1 for t in self.trades if t['type'] == 'WIN')
        losses = sum(1 for t in self.trades if t['type'] == 'LOSS')
        return {
            'strategy': 'P (유지 관리)',
            'total_trades': len(self.trades),
            'wins': wins,
            'losses': losses,
            'win_rate': wins / len(self.trades) * 100 if self.trades else 0,
            'total_pnl': round(self.total_pnl, 2),
            'ev': round(self.total_pnl / len(self.trades), 2) if self.trades else 0
        }


def demo():
    """데모 실행"""
    print("=" * 60)
    print("H5 Experiment: 재진입 vs 유지 관리")
    print("=" * 60)
    
    # 유지 점수 계산 데모
    ps = PersistenceScore()
    
    print("\n유지 점수 시뮬레이션:")
    print("-" * 40)
    
    scenarios = [
        {'mfe': 2, 'mfe_prev': 0, 'mae': 3, 'bars': 1, 'max_mfe': 2},
        {'mfe': 5, 'mfe_prev': 2, 'mae': 3, 'bars': 2, 'max_mfe': 5},
        {'mfe': 8, 'mfe_prev': 5, 'mae': 3, 'bars': 3, 'max_mfe': 8},  # 상태 전이
        {'mfe': 7, 'mfe_prev': 8, 'mae': 4, 'bars': 4, 'max_mfe': 8},
        {'mfe': 1, 'mfe_prev': 1, 'mae': 10, 'bars': 5, 'max_mfe': 1},  # LWS
    ]
    
    for i, s in enumerate(scenarios, 1):
        result = ps.calculate(**s)
        print(f"Bar {i}: MFE={s['mfe']}, MAE={s['mae']}")
        print(f"  → Score: {result['score']:.3f} ({result['state']})")
        print(f"  → Components: {result['components']}")
    
    print("\n" + "=" * 60)
    print("실제 백테스트 데이터로 실험하려면:")
    print("python h5_persistence_experiment.py --data <백테스트.json>")
    print("=" * 60)


if __name__ == "__main__":
    demo()
