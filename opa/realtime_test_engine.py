"""
Realtime Test Engine - A-Plan Implementation

테스트 목표:
- t-ε(OPA): 성과 유지/개선
- t0(STB): Δ 미사용이 최선
- t+0(0-bar): 손실 깊이 감소

금지사항:
- Δ로 STB 진입 여부 변경 ❌
- Δ로 방향/확률 조정 ❌
"""

import json
import os
from datetime import datetime
from collections import deque
from typing import Optional, Dict, List, Any

class RealtimeTestEngine:
    
    def __init__(self, mode: str = "SHADOW"):
        self.mode = mode
        self.state = {
            'bars': deque(maxlen=100),
            'delta_history': deque(maxlen=50),
            'current_state': None,
            'state_age': 0,
            'in_position': False,
            'active_trade': None
        }
        
        self.stats = {
            'opa_triggers': 0,
            'stb_triggers': 0,
            'impulse_triggers': 0,
            'trades': [],
            'events': []
        }
        
        self.thresholds = {
            'delta_overbought': 1.5,
            'delta_oversold': 0.7,
            'channel_high': 70,
            'channel_low': 30,
            'delta_q90': 3.0,
            'tight_sl': 8,
            'normal_sl': 15,
            'tp': 20,
            'cooldown_bars': 10
        }
        
        self.last_trade_bar = -20
        
        self.log_path = os.path.join(os.path.dirname(__file__), 'realtime_logs.json')
    
    def calculate_delta(self, bar: Dict) -> float:
        high = bar.get('high', 0)
        low = bar.get('low', 0)
        close = bar.get('close', 0)
        
        if high == low:
            return 1.0
        
        buyer = close - low
        seller = high - close
        
        if seller == 0:
            return 10.0
        return buyer / seller
    
    def calculate_channel_pct(self) -> float:
        if len(self.state['bars']) < 20:
            return 50.0
        
        bars = list(self.state['bars'])[-20:]
        highs = [b['high'] for b in bars]
        lows = [b['low'] for b in bars]
        
        highest = max(highs)
        lowest = min(lows)
        
        if highest == lowest:
            return 50.0
        
        close = bars[-1]['close']
        return ((close - lowest) / (highest - lowest)) * 100
    
    def detect_pre_transition(self) -> Optional[str]:
        """OPA 시간축 (t-ε): 전환 직전 감지"""
        if len(self.state['delta_history']) < 5:
            return None
        
        deltas = list(self.state['delta_history'])[-5:]
        avg_delta = sum(deltas) / len(deltas)
        current_delta = deltas[-1]
        
        delta_change = current_delta - avg_delta
        
        if delta_change > 0.5 and avg_delta < 1.0:
            return "TRANSITION_TO_BUYER"
        elif delta_change < -0.5 and avg_delta > 1.0:
            return "TRANSITION_TO_SELLER"
        
        return None
    
    def detect_stb_short(self) -> bool:
        """STB 숏 조건: 배율 > 1.5 + 채널 > 70%"""
        if len(self.state['bars']) < 5:
            return False
        
        current_bar = len(self.state['bars'])
        if current_bar - self.last_trade_bar < self.thresholds['cooldown_bars']:
            return False
        
        delta = self.calculate_delta(list(self.state['bars'])[-1])
        channel = self.calculate_channel_pct()
        
        return (delta > self.thresholds['delta_overbought'] and 
                channel > self.thresholds['channel_high'])
    
    def detect_stb_long(self) -> bool:
        """STB 롱 조건: 배율 < 0.7 + 채널 < 30%"""
        if len(self.state['bars']) < 5:
            return False
        
        current_bar = len(self.state['bars'])
        if current_bar - self.last_trade_bar < self.thresholds['cooldown_bars']:
            return False
        
        delta = self.calculate_delta(list(self.state['bars'])[-1])
        channel = self.calculate_channel_pct()
        
        return (delta < self.thresholds['delta_oversold'] and 
                channel < self.thresholds['channel_low'])
    
    def is_boundary_sensitive(self) -> bool:
        """경계 민감도 체크"""
        if len(self.state['bars']) < 20:
            return False
        
        channel = self.calculate_channel_pct()
        return channel > 90 or channel < 10
    
    def get_delta_q90(self) -> float:
        """롤링 델타 q90 계산"""
        if len(self.state['delta_history']) < 10:
            return self.thresholds['delta_q90']
        
        deltas = sorted(list(self.state['delta_history']))
        idx = int(len(deltas) * 0.9)
        return deltas[idx]
    
    def log_event(self, event_type: str, bar: Dict, extra: Dict = None):
        """이벤트 로깅 (원인 분석용)"""
        delta = self.calculate_delta(bar)
        
        event = {
            'ts': bar.get('time', datetime.now().isoformat()),
            'mode': event_type,
            'state_age': self.state['state_age'],
            'stb_margin': round(abs(delta - 1.0), 2),
            'boundary_sensitive': self.is_boundary_sensitive(),
            'delta': round(delta, 3),
            'delta_q90': round(self.get_delta_q90(), 3),
            'channel_pct': round(self.calculate_channel_pct(), 1),
            'action': extra.get('action', 'OBSERVE') if extra else 'OBSERVE',
            'pnl_snapshot': extra.get('pnl', 0) if extra else 0
        }
        
        if extra:
            event.update(extra)
        
        self.stats['events'].append(event)
        
        if self.mode == "SHADOW":
            print(f"[{event_type}] delta={delta:.2f}, channel={event['channel_pct']:.1f}%")
    
    def enter_opa(self, bar: Dict, direction: str):
        """OPA Early Entry"""
        if self.state['in_position']:
            return None
        
        trade = {
            'type': 'OPA',
            'direction': direction,
            'entry_price': bar['close'],
            'entry_time': bar.get('time', datetime.now().isoformat()),
            'sl': self.thresholds['normal_sl'],
            'tp': self.thresholds['tp'],
            'delta_at_entry': self.calculate_delta(bar)
        }
        
        self.stats['opa_triggers'] += 1
        self.log_event('OPA_PRE', bar, {'action': 'ENTER', 'direction': direction})
        
        if self.mode in ["PAPER", "LIVE"]:
            self.state['in_position'] = True
            self.state['active_trade'] = trade
            self.stats['trades'].append(trade)
        
        return trade
    
    def enter_stb(self, bar: Dict, direction: str):
        """STB Entry"""
        if self.state['in_position']:
            return None
        
        entry_price = bar['close']
        
        trade = {
            'type': 'STB',
            'direction': direction,
            'entry_price': entry_price,
            'entry_time': bar.get('time', datetime.now().isoformat()),
            'sl': self.thresholds['normal_sl'],
            'tp': self.thresholds['tp'],
            'tp_price': entry_price + self.thresholds['tp'] if direction == 'LONG' else entry_price - self.thresholds['tp'],
            'sl_price': entry_price - self.thresholds['normal_sl'] if direction == 'LONG' else entry_price + self.thresholds['normal_sl'],
            'delta_at_entry': self.calculate_delta(bar),
            'entry_bar_idx': len(self.state['bars'])
        }
        
        self.stats['stb_triggers'] += 1
        self.last_trade_bar = len(self.state['bars'])
        self.log_event('STB_ENTRY', bar, {'action': 'ENTER', 'direction': direction})
        
        if self.mode in ["PAPER", "LIVE"]:
            self.state['in_position'] = True
            self.state['active_trade'] = trade
            self.stats['trades'].append(trade)
        
        return trade
    
    def apply_0bar_defense(self, trade: Dict, bar: Dict):
        """0-bar Impulse 방어"""
        if not trade:
            return
        
        delta = self.calculate_delta(bar)
        delta_q90 = self.get_delta_q90()
        
        if self.is_boundary_sensitive() and abs(delta - 1.0) > delta_q90:
            old_sl = trade['sl']
            trade['sl'] = self.thresholds['tight_sl']
            
            self.stats['impulse_triggers'] += 1
            self.log_event('IMPULSE_0BAR', bar, {
                'action': 'TIGHT_SL',
                'old_sl': old_sl,
                'new_sl': trade['sl']
            })
    
    def on_bar(self, bar: Dict):
        """메인 처리 루프"""
        self.state['bars'].append(bar)
        
        delta = self.calculate_delta(bar)
        self.state['delta_history'].append(delta)
        
        self.state['state_age'] += 1
        
        if self.state['in_position']:
            self._check_exit(bar)
            return
        
        transition = self.detect_pre_transition()
        if transition:
            if transition == "TRANSITION_TO_SELLER":
                self.enter_opa(bar, "SHORT")
            elif transition == "TRANSITION_TO_BUYER":
                self.enter_opa(bar, "LONG")
            return
        
        if self.detect_stb_short():
            trade = self.enter_stb(bar, "SHORT")
            if trade:
                self.apply_0bar_defense(trade, bar)
        elif self.detect_stb_long():
            trade = self.enter_stb(bar, "LONG")
            if trade:
                self.apply_0bar_defense(trade, bar)
    
    def _check_exit(self, bar: Dict):
        """Exit 체크 (기존 방식: bar.high/low 기준, TP 먼저 체크)"""
        if not self.state['active_trade']:
            return
        
        trade = self.state['active_trade']
        direction = trade['direction']
        tp_price = trade.get('tp_price', trade['entry_price'] + trade['tp'] if direction == 'LONG' else trade['entry_price'] - trade['tp'])
        sl_price = trade.get('sl_price', trade['entry_price'] - trade['sl'] if direction == 'LONG' else trade['entry_price'] + trade['sl'])
        
        if direction == "LONG":
            if bar['high'] >= tp_price:
                trade['result'] = 'WIN'
                trade['pnl'] = trade['tp']
                trade['exit_time'] = bar.get('time', datetime.now().isoformat())
                self.log_event('EXIT_TP', bar, {'action': 'EXIT', 'pnl': trade['tp']})
                self._close_position()
            elif bar['low'] <= sl_price:
                trade['result'] = 'LOSS'
                trade['pnl'] = sl_price - trade['entry_price']
                trade['exit_time'] = bar.get('time', datetime.now().isoformat())
                self.log_event('EXIT_SL', bar, {'action': 'EXIT', 'pnl': trade['pnl']})
                self._close_position()
        else:
            if bar['low'] <= tp_price:
                trade['result'] = 'WIN'
                trade['pnl'] = trade['tp']
                trade['exit_time'] = bar.get('time', datetime.now().isoformat())
                self.log_event('EXIT_TP', bar, {'action': 'EXIT', 'pnl': trade['tp']})
                self._close_position()
            elif bar['high'] >= sl_price:
                trade['result'] = 'LOSS'
                trade['pnl'] = trade['entry_price'] - sl_price
                trade['exit_time'] = bar.get('time', datetime.now().isoformat())
                self.log_event('EXIT_SL', bar, {'action': 'EXIT', 'pnl': trade['pnl']})
                self._close_position()
    
    def _close_position(self):
        """포지션 종료"""
        self.state['in_position'] = False
        self.state['active_trade'] = None
    
    def get_stats(self) -> Dict:
        """통계 반환"""
        trades = self.stats['trades']
        
        if not trades:
            return {
                'mode': self.mode,
                'opa_triggers': self.stats['opa_triggers'],
                'stb_triggers': self.stats['stb_triggers'],
                'impulse_triggers': self.stats['impulse_triggers'],
                'total_trades': 0,
                'win_rate': 0,
                'avg_pnl': 0
            }
        
        completed = [t for t in trades if 'result' in t]
        wins = sum(1 for t in completed if t['result'] == 'WIN')
        total_pnl = sum(t.get('pnl', 0) for t in completed)
        
        return {
            'mode': self.mode,
            'opa_triggers': self.stats['opa_triggers'],
            'stb_triggers': self.stats['stb_triggers'],
            'impulse_triggers': self.stats['impulse_triggers'],
            'total_trades': len(completed),
            'win_rate': round(wins / len(completed) * 100, 1) if completed else 0,
            'avg_pnl': round(total_pnl / len(completed), 2) if completed else 0,
            'impulse_rate': round(self.stats['impulse_triggers'] / max(1, self.stats['stb_triggers']) * 100, 1)
        }
    
    def save_logs(self):
        """로그 저장"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'mode': self.mode,
            'stats': self.get_stats(),
            'events': self.stats['events'][-100:],
            'trades': self.stats['trades']
        }
        
        with open(self.log_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"Logs saved to: {self.log_path}")


class ABTestEngine:
    """A/B 테스트 엔진: 동일 스트림에서 3가지 전략 비교"""
    
    def __init__(self):
        self.engine_a = RealtimeTestEngine("A_STB_ONLY")
        self.engine_b = RealtimeTestEngine("B_STB_0BAR")
        self.engine_c = RealtimeTestEngine("C_OPA_STB_0BAR")
        
        self.engine_a.thresholds['tight_sl'] = self.engine_a.thresholds['normal_sl']
        
    def on_bar(self, bar: Dict):
        """동일 바를 3개 엔진에 전달"""
        bar_a = bar.copy()
        bar_b = bar.copy()
        bar_c = bar.copy()
        
        self.engine_a.on_bar(bar_a)
        self.engine_b.on_bar(bar_b)
        self.engine_c.on_bar(bar_c)
    
    def get_comparison(self) -> Dict:
        """3개 전략 비교"""
        return {
            'A_STB_ONLY': self.engine_a.get_stats(),
            'B_STB_0BAR': self.engine_b.get_stats(),
            'C_OPA_STB_0BAR': self.engine_c.get_stats()
        }


def run_backtest_simulation():
    """백테스트 데이터로 시뮬레이션"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    data_files = [
        'backtest_1min_results.json',
        '../backtest_1min_results.json',
        '../../backtest_1min_results.json'
    ]
    
    for f in data_files:
        full_path = os.path.join(os.path.dirname(__file__), f)
        if os.path.exists(full_path):
            print(f"Using existing backtest results from: {f}")
            break
    
    print("\n" + "="*60)
    print("Realtime Test Engine - Shadow Mode Simulation")
    print("="*60)
    
    import random
    random.seed(42)
    
    engine = RealtimeTestEngine("SHADOW")
    ab_engine = ABTestEngine()
    
    base_price = 21000
    for i in range(500):
        change = random.gauss(0, 15)
        high_add = abs(random.gauss(0, 10))
        low_sub = abs(random.gauss(0, 10))
        
        bar = {
            'time': f'2026-01-23 {i//60:02d}:{i%60:02d}:00',
            'open': base_price,
            'high': base_price + high_add + max(0, change),
            'low': base_price - low_sub + min(0, change),
            'close': base_price + change
        }
        
        base_price = bar['close']
        
        engine.on_bar(bar)
        ab_engine.on_bar(bar)
    
    print("\n[Single Engine Stats]")
    stats = engine.get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    print("\n[A/B Test Comparison]")
    comparison = ab_engine.get_comparison()
    for mode, s in comparison.items():
        print(f"\n  {mode}:")
        for k, v in s.items():
            print(f"    {k}: {v}")
    
    engine.save_logs()
    
    return stats, comparison


if __name__ == "__main__":
    run_backtest_simulation()
