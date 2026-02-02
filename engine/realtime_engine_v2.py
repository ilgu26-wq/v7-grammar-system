"""
RELATIVISTIC MARKET STRUCTURE ENGINE v2.1
==========================================
실시간 세계 상태 판단 엔진 (자유도 통합 최종 버전)

핵심 변화:
  v2.0: "위험해 보인다"
  v2.1: "자유도가 붕괴 중이다"

봉인 문장:
  "우리는 가격을 예측하지 않는다.
   우리는 시장의 자유도를 관측한다."
"""

import numpy as np
import pandas as pd
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple
from datetime import datetime
import json
import os

class Planet(Enum):
    P3_CLEAN = "P3_CLEAN"
    P3_STRESSED = "P3_STRESSED"
    P2_DANGER = "P2_DANGER"
    P1_DANGER = "P1_DANGER"
    OUTSIDE = "OUTSIDE"

class FreedomState(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    COLLAPSED = "COLLAPSED"

class ActionType(Enum):
    ALLOW = "ALLOW"
    THROTTLE = "THROTTLE"
    KILL = "KILL"

@dataclass
class EngineState:
    bar_idx: int
    planet: Planet
    freedom: FreedomState
    freedom_index: float
    resonance: bool
    axiom_kill: bool
    allow: bool
    action: ActionType
    kill_reason: str = ""

class RealtimeEngineV21:
    IE_BOUNDARY_P1 = 2.75
    IE_BOUNDARY_P2 = 2.85
    RESONANCE_WINDOW = 10
    RESONANCE_THRESHOLD = 3
    
    FREEDOM_T_HIGH = 0.65
    FREEDOM_T_MED = 0.45
    FREEDOM_T_LOW = 0.25
    
    def __init__(self):
        self.planet_history: deque = deque(maxlen=self.RESONANCE_WINDOW)
        self.ecs_history: deque = deque(maxlen=10)
        self.state_log: List[EngineState] = []
        self.ri_q75 = None
        self.ri_q90 = None
        self.ri_q95 = None
        self.calibrated = False
        self.prev_zpoc = True
        
    def calibrate(self, ri_q75: float, ri_q90: float, ri_q95: float):
        self.ri_q75 = ri_q75
        self.ri_q90 = ri_q90
        self.ri_q95 = ri_q95
        self.calibrated = True
    
    def _compute_freedom_index(self, ecs: float, zpoc: bool, recovery: bool, 
                               htf: bool, transitions: int) -> float:
        ecs_stability = np.tanh(ecs / 3.0)
        
        zpoc_score = 1.0 if zpoc else 0.0
        
        transition_penalty = min(1.0, transitions / 5.0)
        
        stress_penalty = 0.3 * int(recovery) + 0.2 * int(htf)
        
        freedom = (
            0.35 * ecs_stability +
            0.30 * zpoc_score +
            0.20 * (1.0 - transition_penalty) +
            0.15 * (1.0 - stress_penalty)
        )
        
        return max(0.0, min(1.0, freedom))
    
    def _classify_freedom(self, freedom_index: float) -> FreedomState:
        if freedom_index >= self.FREEDOM_T_HIGH:
            return FreedomState.HIGH
        elif freedom_index >= self.FREEDOM_T_MED:
            return FreedomState.MEDIUM
        elif freedom_index >= self.FREEDOM_T_LOW:
            return FreedomState.LOW
        else:
            return FreedomState.COLLAPSED
    
    def _classify_planet(self, ie: float, ri: float, ecs: float, 
                         zpoc: bool, recovery: bool, htf: bool) -> Planet:
        if not zpoc or ri > self.ri_q90:
            return Planet.OUTSIDE
        if ie < 2.3 or ie > 3.8 or ecs < 1.0:
            return Planet.OUTSIDE
        
        stressed = recovery or htf
        
        if ie < self.IE_BOUNDARY_P1:
            return Planet.P1_DANGER
        elif ie < self.IE_BOUNDARY_P2:
            return Planet.P2_DANGER
        elif stressed:
            return Planet.P3_STRESSED
        else:
            return Planet.P3_CLEAN
    
    def _count_transitions(self) -> int:
        if len(self.planet_history) < 2:
            return 0
        
        transitions = 0
        prev = self.planet_history[0]
        for p in list(self.planet_history)[1:]:
            if p != prev:
                transitions += 1
            prev = p
        
        return transitions
    
    def _check_axioms(self, ri: float, zpoc: bool) -> Tuple[bool, str]:
        if ri > self.ri_q95:
            return True, "RI_SPIKE"
        if self.prev_zpoc and not zpoc:
            return True, "ZPOC_DEATH"
        return False, ""
    
    def process(self, bar_idx: int, ie: float, ri: float, ecs: float,
                zpoc: bool, recovery: bool, htf: bool) -> EngineState:
        if not self.calibrated:
            raise RuntimeError("Engine not calibrated")
        
        planet = self._classify_planet(ie, ri, ecs, zpoc, recovery, htf)
        self.planet_history.append(planet)
        self.ecs_history.append(ecs)
        
        transitions = self._count_transitions()
        resonance = transitions >= self.RESONANCE_THRESHOLD
        
        freedom_index = self._compute_freedom_index(ecs, zpoc, recovery, htf, transitions)
        freedom = self._classify_freedom(freedom_index)
        
        axiom_kill, kill_reason = self._check_axioms(ri, zpoc)
        
        if freedom == FreedomState.COLLAPSED:
            action = ActionType.KILL
            if not kill_reason:
                kill_reason = "FREEDOM_COLLAPSE"
        elif freedom == FreedomState.LOW:
            action = ActionType.KILL
            if not kill_reason:
                kill_reason = "LOW_FREEDOM"
        elif axiom_kill:
            action = ActionType.KILL
        elif resonance:
            action = ActionType.KILL
            if not kill_reason:
                kill_reason = "RESONANCE"
        elif planet != Planet.P3_CLEAN:
            action = ActionType.KILL
            if not kill_reason:
                kill_reason = "DANGER_PLANET"
        elif freedom == FreedomState.MEDIUM:
            action = ActionType.THROTTLE
        else:
            action = ActionType.ALLOW
        
        allow = (action == ActionType.ALLOW)
        
        self.prev_zpoc = zpoc
        
        state = EngineState(
            bar_idx=bar_idx, planet=planet, freedom=freedom,
            freedom_index=freedom_index, resonance=resonance,
            axiom_kill=axiom_kill, allow=allow, action=action,
            kill_reason=kill_reason
        )
        self.state_log.append(state)
        return state
    
    def get_stats(self) -> Dict:
        if not self.state_log:
            return {}
        
        total = len(self.state_log)
        
        freedom_dist = {}
        for f in FreedomState:
            count = sum(1 for s in self.state_log if s.freedom == f)
            freedom_dist[f.value] = {'count': count, 'pct': count / total}
        
        kill_reasons = {}
        for s in self.state_log:
            if s.kill_reason:
                kill_reasons[s.kill_reason] = kill_reasons.get(s.kill_reason, 0) + 1
        
        return {
            'total_bars': total,
            'allow_rate': sum(1 for s in self.state_log if s.allow) / total,
            'throttle_rate': sum(1 for s in self.state_log if s.action == ActionType.THROTTLE) / total,
            'kill_rate': sum(1 for s in self.state_log if s.action == ActionType.KILL) / total,
            'freedom_distribution': freedom_dist,
            'kill_reasons': kill_reasons,
            'avg_freedom_index': np.mean([s.freedom_index for s in self.state_log])
        }

def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['range'] = df['high'] - df['low']
    
    er_list = []
    for i in range(len(df)):
        start = max(0, i - 9)
        window = df['close'].iloc[start:i+1]
        if len(window) < 2:
            er_list.append(0.5)
        else:
            change = abs(window.iloc[-1] - window.iloc[0])
            total = abs(window.diff().dropna()).sum()
            er_list.append(min(1.0, change / max(total, 0.01)))
    df['er'] = er_list
    
    rolling_high = df['high'].rolling(20, min_periods=1).max()
    rolling_low = df['low'].rolling(20, min_periods=1).min()
    df['depth'] = (df['close'] - rolling_low) / (rolling_high - rolling_low + 0.001)
    
    vol = df['range'].replace(0, 1)
    typical = (df['high'] + df['low'] + df['close']) / 3
    df['zpoc'] = (typical * vol).rolling(20, min_periods=1).sum() / vol.rolling(20, min_periods=1).sum()
    
    range_q25, range_q75 = df['range'].quantile(0.25), df['range'].quantile(0.75)
    er_median = df['er'].median()
    
    zpoc_dist = abs(df['zpoc'] - df['close'])
    zpoc_thresh = df['range'].rolling(20, min_periods=1).mean() * 3
    df['zpoc_alive'] = (zpoc_dist < zpoc_thresh).astype(int)
    df['er_alive'] = (df['er'] > er_median * 0.5).astype(int)
    df['range_alive'] = ((df['range'] >= range_q25) & (df['range'] <= range_q75 * 2)).astype(int)
    df['tau_alive'] = (df['er'].diff(5).abs().fillna(0) < 0.3).astype(int)
    
    df['htf_alive'] = 0
    for p in [5, 15]:
        htf = df['er'].rolling(p, min_periods=1).mean()
        df['htf_alive'] = df['htf_alive'] | (htf > 0.6).astype(int)
    
    df['recovery'] = ((df['er'].shift(3) < 0.3) & (df['er'] > 0.5)).astype(int).fillna(0)
    df['state_stable'] = (df['er'].diff().abs().fillna(0) < 0.1).astype(int)
    
    df['force_flux'] = (df['close'].diff().abs() * df['range']).rolling(5, min_periods=1).mean()
    
    ecs_weights = {'zpoc_alive': 2.0, 'htf_alive': -1.5, 'tau_alive': 0.6,
                   'state_stable': 0.5, 'range_alive': 0.3, 'recovery': -0.8,
                   'er_alive': -0.5}
    df['ecs'] = sum(ecs_weights[k] * df[k] for k in ecs_weights if k in df.columns)
    
    resistance = 1.0 + 2.0 * (1 - df['zpoc_alive']) + 0.5 * df['htf_alive'] + 1.0 * df['recovery']
    pg = df['force_flux'] / (df['ecs'] + 2.0).clip(lower=0.1)
    df['ri'] = pg * resistance
    
    window_pre, window_post = 5, 5
    ie_list = []
    for i in range(len(df)):
        start = max(0, i - window_pre)
        end = min(len(df), i + window_post + 1)
        w = df.iloc[start:end]
        if len(w) < 3:
            ie_list.append(0.0)
            continue
        fields = [
            w['zpoc_alive'].mean(), w['htf_alive'].mean(),
            w['er'].mean() * (1 - w['er'].std()),
            1.0 - min(1.0, w['depth'].std() * 3),
            w['tau_alive'].mean(),
            max(0, 1.0 - w['range'].std() / max(w['range'].mean(), 0.01)),
            min(1.0, w['recovery'].sum()), w['state_stable'].mean()
        ]
        ie = sum(fields) - np.var(fields)
        if fields[0] < 0.3 and fields[2] > 0.6:
            ie -= 1.0
        if fields[0] < 0.3 and sum(fields) > 4.0:
            ie -= 1.5
        ie_list.append(ie)
    df['ie'] = ie_list
    
    return df

def run_validation():
    for path in ["data/mnq_december_2025.csv", "data/mnq_with_ratio.csv"]:
        if os.path.exists(path):
            print(f"Loading: {path}")
            df = pd.read_csv(path)
            break
    else:
        print("ERROR: No data")
        return
    
    df.columns = df.columns.str.lower()
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    
    print("=" * 70)
    print("RELATIVISTIC MARKET STRUCTURE ENGINE v2.1")
    print("Freedom Index Integration")
    print("=" * 70)
    
    print("\n[1] Computing indicators...")
    df = compute_all_indicators(df)
    
    ri_q75 = df['ri'].quantile(0.75)
    ri_q90 = df['ri'].quantile(0.90)
    ri_q95 = df['ri'].quantile(0.95)
    print(f"  RI thresholds: q75={ri_q75:.2f}, q90={ri_q90:.2f}, q95={ri_q95:.2f}")
    
    engine = RealtimeEngineV21()
    engine.calibrate(ri_q75, ri_q90, ri_q95)
    
    print(f"\n[2] Processing {len(df)} bars...")
    
    for i in range(50, len(df)):
        row = df.iloc[i]
        engine.process(
            bar_idx=i,
            ie=float(row['ie']),
            ri=float(row['ri']),
            ecs=float(row['ecs']),
            zpoc=bool(row['zpoc_alive']),
            recovery=bool(row['recovery']),
            htf=bool(row['htf_alive'])
        )
    
    print("\n[3] Validation Results")
    stats = engine.get_stats()
    
    print(f"\n  Total bars: {stats['total_bars']}")
    print(f"  ALLOW rate: {stats['allow_rate']:.1%}")
    print(f"  THROTTLE rate: {stats['throttle_rate']:.1%}")
    print(f"  KILL rate: {stats['kill_rate']:.1%}")
    print(f"  Avg Freedom Index: {stats['avg_freedom_index']:.3f}")
    
    print("\n  Freedom distribution:")
    for state, data in stats['freedom_distribution'].items():
        print(f"    {state}: {data['count']} ({data['pct']:.1%})")
    
    print("\n  Kill reasons:")
    for reason, count in sorted(stats['kill_reasons'].items(), key=lambda x: -x[1]):
        pct = count / stats['total_bars']
        print(f"    {reason}: {count} ({pct:.1%})")
    
    print("\n[4] Sample state log:")
    samples = [s for s in engine.state_log if s.kill_reason][-10:]
    for s in samples:
        print(f"  bar={s.bar_idx:5d} planet={s.planet.value:12s} "
              f"freedom={s.freedom.value:9s} idx={s.freedom_index:.2f} "
              f"action={s.action.value:8s} reason={s.kill_reason}")
    
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    result = {
        'engine_version': '2.1',
        'calibration': {'ri_q75': ri_q75, 'ri_q90': ri_q90, 'ri_q95': ri_q95},
        'stats': stats,
        'log_sample': [
            {'bar': s.bar_idx, 'planet': s.planet.value, 'freedom': s.freedom.value,
             'freedom_idx': s.freedom_index, 'action': s.action.value, 'reason': s.kill_reason}
            for s in engine.state_log[-200:]
        ]
    }
    with open("v7-grammar-system/results/engine_v21_validation.json", 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nLog saved: v7-grammar-system/results/engine_v21_validation.json")
    
    print("\n" + "=" * 70)
    print("ENGINE v2.1 (FREEDOM INDEX) VALIDATION COMPLETE")
    print("=" * 70)
    print("\n  '우리는 가격을 예측하지 않는다.")
    print("   우리는 시장의 자유도를 관측한다.'")
    
    return engine

if __name__ == "__main__":
    run_validation()
