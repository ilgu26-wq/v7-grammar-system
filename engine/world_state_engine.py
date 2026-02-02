"""
WORLD STATE ENGINE v1.0
========================
실시간 전이 법칙 검증 엔진

목표: 전이 법칙이 실시간에서도 동일하게 작동하는지 확인
- RI_SPIKE / ZPOC_DEATH → RUPTURE 전이 감지
- False Trigger 탐지
- Latency ≤ 1 bar 검증

NO TRADING - ACTION LOG ONLY
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import json
import os

class WorldState(Enum):
    STABLE_BASIN = "STABLE_BASIN"
    TRANSITION_ZONE = "TRANSITION_ZONE"
    RUPTURE_RIDGE = "RUPTURE_RIDGE"
    NOISE_FIELD = "NOISE_FIELD"

class Action(Enum):
    ALLOW = "ALLOW"
    THROTTLE = "THROTTLE"
    KILL = "KILL"

class TriggerType(Enum):
    NONE = "NONE"
    RI_SPIKE = "RI_SPIKE"
    RI_PLATEAU = "RI_PLATEAU"
    ZPOC_DEATH = "ZPOC_DEATH"
    IE_EXIT = "IE_EXIT"
    ECS_DROP = "ECS_DROP"

@dataclass
class StateSnapshot:
    timestamp: str
    bar_idx: int
    price: float
    ie: float
    ecs: float
    ri: float
    zpoc_alive: bool
    world_state: WorldState
    triggers: List[TriggerType]
    action: Action
    prev_state: Optional[WorldState] = None
    transition_detected: bool = False

@dataclass
class TransitionEvent:
    bar_idx: int
    timestamp: str
    from_state: WorldState
    to_state: WorldState
    triggers: List[TriggerType]
    latency_bars: int = 0
    validated: bool = False

ECS_WEIGHTS = {
    'zpoc_alive': 2.0, 'htf_alive': -1.5, 'tau_alive': 0.6,
    'state_stable': 0.5, 'range_alive': 0.3,
    'recovery': -0.8, 'er_alive': -0.5, 'depth_alive': -0.3
}

class WorldStateEngine:
    def __init__(self, lookback: int = 50):
        self.lookback = lookback
        self.history: List[Dict] = []
        self.computed_history: List[Dict] = []
        self.state_log: List[StateSnapshot] = []
        self.transition_log: List[TransitionEvent] = []
        self.pending_triggers: List[Tuple[int, TriggerType]] = []
        
        self.ri_q75 = None
        self.ri_q90 = None
        self.ri_q95 = None
        self.calibrated = False
        
        self.current_state = WorldState.NOISE_FIELD
        self.stable_entry_bar = None
        
    def calibrate(self, df: pd.DataFrame):
        df = self._compute_indicators(df)
        self.ri_q75 = df['ri'].quantile(0.75)
        self.ri_q90 = df['ri'].quantile(0.90)
        self.ri_q95 = df['ri'].quantile(0.95)
        self.calibrated = True
        print(f"[Engine] Calibrated: RI q75={self.ri_q75:.2f}, q90={self.ri_q90:.2f}, q95={self.ri_q95:.2f}")
        
    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
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
        depth_median = df['depth'].median()
        
        zpoc_dist = abs(df['zpoc'] - df['close'])
        zpoc_thresh = df['range'].rolling(20, min_periods=1).mean() * 3
        df['zpoc_alive'] = (zpoc_dist < zpoc_thresh).astype(int)
        df['depth_alive'] = (abs(df['depth'] - depth_median) < 0.3).astype(int)
        df['er_alive'] = (df['er'] > er_median * 0.5).astype(int)
        df['range_alive'] = ((df['range'] >= range_q25) & (df['range'] <= range_q75 * 2)).astype(int)
        df['tau_alive'] = (df['er'].diff(5).abs() < 0.3).astype(int)
        
        df['htf_alive'] = 0
        for p in [5, 15]:
            htf = df['er'].rolling(p, min_periods=1).mean()
            df['htf_alive'] = df['htf_alive'] | (htf > 0.6).astype(int)
        
        df['recovery'] = ((df['er'].shift(3) < 0.3) & (df['er'] > 0.5)).astype(int)
        df['state_stable'] = (df['er'].diff().abs() < 0.1).astype(int)
        
        df['force_flux'] = (df['close'].diff().abs() * df['range']).rolling(5, min_periods=1).mean()
        
        df['ecs'] = sum(ECS_WEIGHTS[k] * df[k] for k in ECS_WEIGHTS if k in df.columns)
        
        resistance = 1.0 + 2.0 * (1 - df['zpoc_alive']) + 0.5 * df['htf_alive'] + 1.0 * df['recovery']
        pg = df['force_flux'] / (df['ecs'] + 2.0).clip(lower=0.1)
        df['ri'] = pg * resistance
        
        return df
    
    def _compute_ie(self, window: pd.DataFrame) -> float:
        if len(window) < 3:
            return 0.0
        
        fields = [
            window['zpoc_alive'].mean(),
            window['htf_alive'].mean(),
            window['er'].mean() * (1 - window['er'].std()),
            1.0 - min(1.0, window['depth'].std() * 3),
            window['tau_alive'].mean(),
            max(0, 1.0 - window['range'].std() / max(window['range'].mean(), 0.01)),
            min(1.0, window['recovery'].sum()),
            window['state_stable'].mean()
        ]
        
        ie = sum(fields) - np.var(fields)
        
        if fields[0] < 0.3 and fields[2] > 0.6:
            ie -= 1.0
        if fields[0] < 0.3 and sum(fields) > 4.0:
            ie -= 1.5
        
        return ie
    
    def _classify_state(self, ie: float, ri: float, ecs: float, zpoc: int) -> WorldState:
        if zpoc == 0 or ri > self.ri_q90:
            return WorldState.RUPTURE_RIDGE
        if ie < 2.0 or ie > 4.5 or ecs < 0:
            return WorldState.NOISE_FIELD
        if 2.3 <= ie <= 3.8 and ri < self.ri_q75 and ecs > 1.0 and zpoc == 1:
            return WorldState.STABLE_BASIN
        if 2.0 <= ie <= 4.5 and ri < self.ri_q90:
            return WorldState.TRANSITION_ZONE
        return WorldState.NOISE_FIELD
    
    def _detect_triggers(self, current: Dict, prev: Optional[Dict]) -> List[TriggerType]:
        triggers = []
        
        if current['ri'] > self.ri_q95:
            triggers.append(TriggerType.RI_SPIKE)
        
        if len(self.computed_history) >= 3:
            recent_ri = [h['ri'] for h in self.computed_history[-3:]]
            if all(r > self.ri_q90 for r in recent_ri):
                triggers.append(TriggerType.RI_PLATEAU)
        
        if prev and prev['zpoc_alive'] == 1 and current['zpoc_alive'] == 0:
            triggers.append(TriggerType.ZPOC_DEATH)
        
        if prev:
            if 2.3 <= prev['ie'] <= 3.8 and (current['ie'] < 2.3 or current['ie'] > 3.8):
                triggers.append(TriggerType.IE_EXIT)
        
        if prev:
            ecs_delta = current['ecs'] - prev['ecs']
            if ecs_delta < -1.0:
                triggers.append(TriggerType.ECS_DROP)
        
        return triggers if triggers else [TriggerType.NONE]
    
    def _determine_action(self, state: WorldState, triggers: List[TriggerType]) -> Action:
        if TriggerType.RI_SPIKE in triggers:
            return Action.KILL
        if state == WorldState.RUPTURE_RIDGE:
            return Action.KILL
        if TriggerType.RI_PLATEAU in triggers or TriggerType.ZPOC_DEATH in triggers:
            return Action.THROTTLE
        if state == WorldState.STABLE_BASIN:
            return Action.ALLOW
        if state == WorldState.TRANSITION_ZONE:
            return Action.THROTTLE
        return Action.KILL
    
    def process_bar(self, bar: Dict, bar_idx: int) -> StateSnapshot:
        if not self.calibrated:
            raise RuntimeError("Engine not calibrated")
        
        self.history.append(bar)
        if len(self.history) > self.lookback:
            self.history = self.history[-self.lookback:]
        
        df = pd.DataFrame(self.history)
        df = self._compute_indicators(df)
        
        current = df.iloc[-1].to_dict()
        current['ie'] = self._compute_ie(df.tail(11))
        
        self.computed_history.append(current)
        if len(self.computed_history) > self.lookback:
            self.computed_history = self.computed_history[-self.lookback:]
        
        prev = self.computed_history[-2] if len(self.computed_history) > 1 else None
        
        triggers = self._detect_triggers(current, prev)
        state = self._classify_state(current['ie'], current['ri'], current['ecs'], current['zpoc_alive'])
        action = self._determine_action(state, triggers)
        
        transition = False
        if state != self.current_state:
            transition = True
            
            trigger_bar = None
            for t in triggers:
                if t in [TriggerType.RI_SPIKE, TriggerType.ZPOC_DEATH]:
                    trigger_bar = bar_idx
                    break
            
            for pending_bar, pending_trigger in self.pending_triggers:
                if state == WorldState.RUPTURE_RIDGE:
                    latency = bar_idx - pending_bar
                    event = TransitionEvent(
                        bar_idx=bar_idx,
                        timestamp=datetime.now().isoformat(),
                        from_state=self.current_state,
                        to_state=state,
                        triggers=[pending_trigger],
                        latency_bars=latency,
                        validated=(latency <= 1)
                    )
                    self.transition_log.append(event)
            
            self.pending_triggers = []
            
            if TriggerType.RI_SPIKE in triggers or TriggerType.ZPOC_DEATH in triggers:
                if state != WorldState.RUPTURE_RIDGE:
                    self.pending_triggers.append((bar_idx, triggers[0]))
        
        prev_state = self.current_state
        self.current_state = state
        
        if state == WorldState.STABLE_BASIN and prev_state != WorldState.STABLE_BASIN:
            self.stable_entry_bar = bar_idx
        
        snapshot = StateSnapshot(
            timestamp=datetime.now().isoformat(),
            bar_idx=bar_idx,
            price=bar.get('close', 0),
            ie=current['ie'],
            ecs=current['ecs'],
            ri=current['ri'],
            zpoc_alive=bool(current['zpoc_alive']),
            world_state=state,
            triggers=triggers,
            action=action,
            prev_state=prev_state,
            transition_detected=transition
        )
        
        self.state_log.append(snapshot)
        
        return snapshot
    
    def get_validation_report(self) -> Dict:
        transitions = self.transition_log
        
        stable_to_rupture = [t for t in transitions 
                           if t.from_state == WorldState.STABLE_BASIN 
                           and t.to_state == WorldState.RUPTURE_RIDGE]
        
        spike_triggered = [t for t in stable_to_rupture 
                          if TriggerType.RI_SPIKE in t.triggers or TriggerType.ZPOC_DEATH in t.triggers]
        
        false_triggers = len([t for t in transitions if t.latency_bars > 1])
        valid_latency = len([t for t in transitions if t.latency_bars <= 1])
        
        return {
            'total_transitions': len(transitions),
            'stable_to_rupture': len(stable_to_rupture),
            'trigger_caused': len(spike_triggered),
            'trigger_rate': len(spike_triggered) / max(len(stable_to_rupture), 1),
            'false_triggers': false_triggers,
            'valid_latency': valid_latency,
            'latency_pass_rate': valid_latency / max(len(transitions), 1)
        }
    
    def export_log(self, filepath: str):
        log_data = {
            'engine_version': '1.0',
            'calibration': {
                'ri_q75': self.ri_q75,
                'ri_q90': self.ri_q90,
                'ri_q95': self.ri_q95
            },
            'state_log': [
                {
                    'bar_idx': s.bar_idx,
                    'price': s.price,
                    'ie': s.ie,
                    'ecs': s.ecs,
                    'ri': s.ri,
                    'world_state': s.world_state.value,
                    'triggers': [t.value for t in s.triggers],
                    'action': s.action.value,
                    'transition': s.transition_detected
                }
                for s in self.state_log[-1000:]
            ],
            'validation': self.get_validation_report()
        }
        
        with open(filepath, 'w') as f:
            json.dump(log_data, f, indent=2)


def run_realtime_validation(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("WORLD STATE ENGINE v1.0 - REALTIME VALIDATION")
    print("=" * 70)
    
    calibration_size = min(2000, len(df) // 3)
    calibration_df = df.iloc[:calibration_size]
    test_df = df.iloc[calibration_size:]
    
    print(f"\n[1] Calibration: {calibration_size} bars")
    engine = WorldStateEngine()
    engine.calibrate(calibration_df)
    
    print(f"\n[2] Processing: {len(test_df)} bars")
    
    for i, (idx, row) in enumerate(test_df.iterrows()):
        bar = row.to_dict()
        snapshot = engine.process_bar(bar, i)
        
        if snapshot.transition_detected:
            print(f"  Bar {i}: {snapshot.prev_state.value[:6]} → {snapshot.world_state.value[:6]} "
                  f"| Triggers: {[t.value for t in snapshot.triggers]} | Action: {snapshot.action.value}")
    
    print("\n[3] Validation Report")
    report = engine.get_validation_report()
    
    print(f"  Total transitions: {report['total_transitions']}")
    print(f"  STABLE → RUPTURE: {report['stable_to_rupture']}")
    print(f"  Trigger-caused: {report['trigger_caused']} ({report['trigger_rate']:.0%})")
    print(f"  False triggers: {report['false_triggers']}")
    print(f"  Latency ≤ 1 bar: {report['valid_latency']} ({report['latency_pass_rate']:.0%})")
    
    success = report['trigger_rate'] >= 0.9 and report['latency_pass_rate'] >= 0.8
    print(f"\n  Validation: {'✓ PASS' if success else '△ PARTIAL'}")
    
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    engine.export_log("v7-grammar-system/results/engine_realtime_log.json")
    print(f"\n  Log saved: v7-grammar-system/results/engine_realtime_log.json")
    
    return report


if __name__ == "__main__":
    for path in ["data/mnq_december_2025.csv", "data/mnq_with_ratio.csv"]:
        if os.path.exists(path):
            df = pd.read_csv(path)
            break
    else:
        print("ERROR: No data")
        exit(1)
    
    df.columns = df.columns.str.lower()
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    
    run_realtime_validation(df)
