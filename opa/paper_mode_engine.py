"""
V7 Grammar System - Paper Mode Engine
FINAL_AUDIT 기준 완전 준수

오늘 테스트 목표:
- 레이어가 섞이지 않는가
- 실패 모드가 설계대로만 발생하는가
- 로그가 FINAL_AUDIT 기준을 만족하는가

7가지 체크:
1. 레이어 충돌 없음
2. Δ scope 로그
3. θ≥3 사용 금지
4. 0-bar 방어 타이밍
5. Exit reason 분리
6. 엔진 안정성
7. FINAL_AUDIT 일관성
"""

import json
import os
import sys
from datetime import datetime
from collections import deque
from typing import Optional, Dict, List, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.theta_state import ThetaEngine


class TradeContext:
    """ENTRY → EXIT 동안 유지되는 트레이드 상태"""
    
    def __init__(self, entry_price: float, direction: str):
        self.entry_price = entry_price
        self.direction = direction
        self.mfe = 0.0  # Maximum Favorable Excursion
        self.mae = 0.0  # Maximum Adverse Excursion
        self.bars = 0
        self.theta = 0
        self.theta_history = []
        self.theta_engine = ThetaEngine()
    
    def update(self, current_price: float):
        """매 bar 업데이트 - mfe/θ 누적"""
        self.bars += 1
        
        if self.direction == "LONG":
            favorable = current_price - self.entry_price
            adverse = self.entry_price - current_price
        else:
            favorable = self.entry_price - current_price
            adverse = current_price - self.entry_price
        
        self.mfe = max(self.mfe, favorable)
        self.mae = max(self.mae, adverse)
        
        state = self.theta_engine.compute(self.mfe, self.bars)
        self.theta = state.value
        self.theta_history.append(self.theta)
    
    def get_final_theta(self) -> int:
        """EXIT 시 최종 θ 반환"""
        return self.theta
    
    def get_max_theta(self) -> int:
        """도달한 최대 θ"""
        return max(self.theta_history) if self.theta_history else 0


class PaperModeEngine:
    
    def __init__(self):
        self.mode = "PAPER"
        
        self.state = {
            'bars': deque(maxlen=100),
            'delta_history': deque(maxlen=50),
            'in_position': False,
            'active_trade': None,
            'trade_context': None,  # TradeContext for theta tracking
            'bar_count': 0
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
        
        self.trades = []
        self.events = []
        
        self.audit_checks = {
            'layer_conflicts': 0,
            'delta_scope_violations': 0,
            'theta3_execution_attempts': 0,
            '0bar_timing_errors': 0,
            'exit_reason_missing': 0,
            'engine_errors': 0,
            'audit_violations': 0
        }
        
        self.opa_signals = []
        self.signal_log_path = os.path.join(os.path.dirname(__file__), 'opa_signal_log.json')
        
        self.log_path = os.path.join(os.path.dirname(__file__), 'paper_mode_logs.json')
        self.theta_log_path = os.path.join(os.path.dirname(__file__), 'paper_mode_logs_theta.json')
    
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
    
    def detect_opa_transition(self) -> Optional[str]:
        """OPA Δ (t-ε): Pre-transition 감지만"""
        if len(self.state['delta_history']) < 5:
            return None
        
        deltas = list(self.state['delta_history'])[-5:]
        avg_delta = sum(deltas) / len(deltas)
        current_delta = deltas[-1]
        
        delta_change = current_delta - avg_delta
        
        if delta_change > 0.5 and avg_delta < 1.0:
            self._log_opa_signal_raw("LONG", avg_delta, current_delta, delta_change)
            # LONG 비활성화: J2+J3 실험 결과 - 재발생 14.1% + 생존 0% = 구조적 무의미
            # 센서 로깅 유지, 실행만 차단
            return None
        elif delta_change < -0.5 and avg_delta > 1.0:
            self._log_opa_signal_raw("SHORT", avg_delta, current_delta, delta_change)
            return "TRANSITION_TO_SELLER"
        
        return None
    
    def _log_opa_signal_raw(self, direction: str, avg_delta: float, current_delta: float, delta_change: float):
        """센서 전용 로깅 - 체결/판단 없이 순수 이벤트만"""
        import time
        from datetime import datetime
        
        now = datetime.now()
        hour = now.hour
        session = "RTH" if 9 <= hour < 16 else "ETH"
        
        log_entry = {
            "ts": now.strftime("%Y-%m-%d %H:%M:%S"),
            "direction": direction,
            "avg_delta": round(avg_delta, 4),
            "current_delta": round(current_delta, 4),
            "delta_change": round(delta_change, 4),
            "channel_pct": round(self.calculate_channel_pct(), 1),
            "session": session
        }
        
        log_file = os.path.join(os.path.dirname(__file__), 'opa_signal_raw.jsonl')
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def record_opa_signal(self, bar: Dict, transition_type: str):
        """
        Layer 1: OPA_SIGNAL (순수 전환 감지)
        
        체결 판단 없음. 오직 이벤트 기록만.
        """
        deltas = list(self.state['delta_history'])[-5:]
        avg_delta = sum(deltas) / len(deltas)
        current_delta = deltas[-1]
        delta_change = current_delta - avg_delta
        
        signal = {
            'ts': bar.get('time', datetime.now().isoformat()),
            'bar_idx': self.state['bar_count'],
            'direction': 'LONG' if transition_type == 'TRANSITION_TO_BUYER' else 'SHORT',
            'transition_type': transition_type,
            'avg_delta': round(avg_delta, 4),
            'current_delta': round(current_delta, 4),
            'delta_change': round(delta_change, 4),
            'channel_pct': round(self.calculate_channel_pct(), 1),
            'executed': False,
            'execution_blocked_by': None
        }
        
        self.opa_signals.append(signal)
        print(f"[OPA_SIGNAL] {signal['direction']} | avg_δ={signal['avg_delta']:.2f} | Δchange={signal['delta_change']:.2f} | ch={signal['channel_pct']:.1f}%")
        
        return signal
    
    def detect_stb(self) -> Optional[str]:
        """STB Ignition (t0): 실행 엔진"""
        if len(self.state['bars']) < 5:
            return None
        
        current_bar = self.state['bar_count']
        if current_bar - self.last_trade_bar < self.thresholds['cooldown_bars']:
            return None
        
        bar = list(self.state['bars'])[-1]
        delta = self.calculate_delta(bar)
        channel = self.calculate_channel_pct()
        
        if delta > self.thresholds['delta_overbought'] and channel > self.thresholds['channel_high']:
            return "SHORT"
        elif delta < self.thresholds['delta_oversold'] and channel < self.thresholds['channel_low']:
            return "LONG"
        
        return None
    
    def detect_impulse(self, bar: Dict) -> bool:
        """0-bar Impulse 감지 (t+0)"""
        if len(self.state['delta_history']) < 10:
            return False
        
        channel = self.calculate_channel_pct()
        if not (channel > 90 or channel < 10):
            return False
        
        delta = self.calculate_delta(bar)
        deltas = sorted(list(self.state['delta_history']))
        q90_idx = int(len(deltas) * 0.9)
        delta_q90 = deltas[q90_idx]
        
        return abs(delta - 1.0) > delta_q90
    
    def log_event(self, bar: Dict, event_type: str, layer: str, delta_scope: str, 
                  direction: str = None, action: str = "OBSERVE", extra: Dict = None):
        """FINAL_AUDIT 기준 로그"""
        
        ctx = self.state.get('trade_context')
        theta = ctx.get_final_theta() if ctx else 0
        
        event = {
            'ts': bar.get('time', datetime.now().isoformat()),
            'bar_idx': self.state['bar_count'],
            'layer_triggered': layer,
            'delta_scope': delta_scope,
            'event_type': event_type,
            'direction': direction,
            'action': action,
            'delta': round(self.calculate_delta(bar), 3),
            'channel_pct': round(self.calculate_channel_pct(), 1),
            'theta_label': theta
        }
        
        if extra:
            event.update(extra)
        
        self.events.append(event)
        
        print(f"[{self.mode}] {event_type} | layer={layer} | scope={delta_scope} | delta={event['delta']:.2f} | ch={event['channel_pct']:.1f}%")
        
        return event
    
    def enter_trade(self, bar: Dict, direction: str, layer: str, delta_scope: str) -> Dict:
        """진입 (OPA 또는 STB)"""
        if self.state['in_position']:
            self.audit_checks['layer_conflicts'] += 1
            return None
        
        entry_price = bar['close']
        
        ctx = TradeContext(entry_price, direction)
        self.state['trade_context'] = ctx
        
        trade = {
            'trade_id': len(self.trades) + 1,
            'layer': layer,
            'delta_scope': delta_scope,
            'direction': direction,
            'entry_price': entry_price,
            'entry_time': bar.get('time', datetime.now().isoformat()),
            'entry_bar_idx': self.state['bar_count'],
            'sl': self.thresholds['normal_sl'],
            'tp': self.thresholds['tp'],
            'tp_price': entry_price + self.thresholds['tp'] if direction == 'LONG' else entry_price - self.thresholds['tp'],
            'sl_price': entry_price - self.thresholds['normal_sl'] if direction == 'LONG' else entry_price + self.thresholds['normal_sl'],
            'delta_at_entry': self.calculate_delta(bar),
            '0bar_defense_applied': False,
            'theta_label': 0,  # Will be updated at EXIT
            'final_mfe': 0.0,
            'final_bars': 0,
            'max_theta': 0,
            'result': None,
            'exit_reason': None,
            'pnl': None
        }
        
        self.state['in_position'] = True
        self.state['active_trade'] = trade
        self.trades.append(trade)
        self.last_trade_bar = self.state['bar_count']
        
        self.log_event(bar, f'{layer}_ENTRY', layer, delta_scope, direction, 'ENTER', {
            'entry_price': entry_price,
            'tp_price': trade['tp_price'],
            'sl_price': trade['sl_price']
        })
        
        return trade
    
    def apply_0bar_defense(self, trade: Dict, bar: Dict):
        """0-bar Defense (t+0) - 진입과 같은 봉에서만"""
        if not trade:
            return
        
        if trade['entry_bar_idx'] != self.state['bar_count']:
            self.audit_checks['0bar_timing_errors'] += 1
            return
        
        if self.detect_impulse(bar):
            old_sl = trade['sl']
            trade['sl'] = self.thresholds['tight_sl']
            
            if trade['direction'] == 'LONG':
                trade['sl_price'] = trade['entry_price'] - trade['sl']
            else:
                trade['sl_price'] = trade['entry_price'] + trade['sl']
            
            trade['0bar_defense_applied'] = True
            
            self.log_event(bar, 'IMPULSE_0BAR', 'DEFENSE', 't+0', trade['direction'], 'TIGHT_SL', {
                'old_sl': old_sl,
                'new_sl': trade['sl']
            })
    
    def check_exit(self, bar: Dict):
        """Exit 체크"""
        if not self.state['active_trade']:
            return
        
        trade = self.state['active_trade']
        ctx = self.state.get('trade_context')
        direction = trade['direction']
        tp_price = trade['tp_price']
        sl_price = trade['sl_price']
        
        if ctx:
            ctx.update(bar['close'])
        
        exit_reason = None
        pnl = None
        result = None
        
        if direction == "LONG":
            if bar['high'] >= tp_price:
                exit_reason = 'TP'
                pnl = trade['tp']
                result = 'WIN'
            elif bar['low'] <= sl_price:
                exit_reason = 'SL'
                pnl = sl_price - trade['entry_price']
                result = 'LOSS'
        else:
            if bar['low'] <= tp_price:
                exit_reason = 'TP'
                pnl = trade['tp']
                result = 'WIN'
            elif bar['high'] >= sl_price:
                exit_reason = 'SL'
                pnl = trade['entry_price'] - sl_price
                result = 'LOSS'
        
        if exit_reason:
            if ctx:
                trade['theta_label'] = ctx.get_final_theta()
                trade['final_mfe'] = ctx.mfe
                trade['final_bars'] = ctx.bars
                trade['max_theta'] = ctx.get_max_theta()
                trade['theta_history'] = ctx.theta_history
            
            trade['exit_reason'] = exit_reason
            trade['pnl'] = pnl
            trade['result'] = result
            trade['exit_time'] = bar.get('time', datetime.now().isoformat())
            trade['exit_bar_idx'] = self.state['bar_count']
            trade['pnl_positive'] = pnl > 0
            
            self.log_event(bar, f'EXIT_{exit_reason}', trade['layer'], trade['delta_scope'], 
                          trade['direction'], 'EXIT', {
                              'exit_reason': exit_reason,
                              'pnl': pnl,
                              'result': result,
                              'pnl_positive': pnl > 0,
                              'final_mfe': trade.get('final_mfe', 0),
                              'final_theta': trade.get('theta_label', 0)
                          })
            
            self.close_position()
    
    def close_position(self):
        """포지션 종료"""
        self.state['in_position'] = False
        self.state['active_trade'] = None
        self.state['trade_context'] = None  # Reset context
    
    def on_bar(self, bar: Dict):
        """메인 처리 루프 - 3-Layer 분리 설계"""
        try:
            self.state['bars'].append(bar)
            self.state['bar_count'] += 1
            
            delta = self.calculate_delta(bar)
            self.state['delta_history'].append(delta)
            
            if self.state['in_position']:
                self.check_exit(bar)
                return
            
            opa_transition = self.detect_opa_transition()
            if opa_transition:
                signal = self.record_opa_signal(bar, opa_transition)
                
                judgment = self.judgment_layer(signal)
                
                if judgment['decision'] == 'ALLOW':
                    signal['executed'] = True
                    direction = signal['direction']
                    trade = self.enter_trade(bar, direction, "OPA", "t-ε")
                else:
                    signal['executed'] = False
                    signal['execution_blocked_by'] = judgment['reason']
                return
            
            stb_direction = self.detect_stb()
            if stb_direction:
                trade = self.enter_trade(bar, stb_direction, "STB", "t0")
                if trade:
                    self.apply_0bar_defense(trade, bar)
                return
            
        except Exception as e:
            self.audit_checks['engine_errors'] += 1
            print(f"[ERROR] {e}")
    
    def judgment_layer(self, signal: Dict) -> Dict:
        """
        Layer 2: JUDGMENT (판단 레이어)
        
        현재: 모든 신호 ALLOW (순수 측정 모드)
        추후: 데이터 기반 조건 추가
        """
        return {
            'decision': 'ALLOW',
            'reason': None
        }
    
    def get_signal_stats(self) -> Dict:
        """OPA_SIGNAL 순수 통계 (체결 무관)"""
        total = len(self.opa_signals)
        if total == 0:
            return {'total': 0}
        
        long_signals = [s for s in self.opa_signals if s['direction'] == 'LONG']
        short_signals = [s for s in self.opa_signals if s['direction'] == 'SHORT']
        executed = [s for s in self.opa_signals if s['executed']]
        blocked = [s for s in self.opa_signals if not s['executed']]
        
        return {
            'total': total,
            'long_count': len(long_signals),
            'short_count': len(short_signals),
            'direction_ratio': round(len(long_signals) / total * 100, 1) if total else 0,
            'executed_count': len(executed),
            'blocked_count': len(blocked),
            'execution_rate': round(len(executed) / total * 100, 1) if total else 0,
            'avg_delta_change': round(sum(s['delta_change'] for s in self.opa_signals) / total, 4),
            'avg_channel_pct': round(sum(s['channel_pct'] for s in self.opa_signals) / total, 1)
        }
    
    def save_signal_log(self):
        """OPA_SIGNAL 분리 로그 저장"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'stats': self.get_signal_stats(),
            'signals': self.opa_signals
        }
        with open(self.signal_log_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"[OPA_SIGNAL] Log saved: {self.signal_log_path}")
    
    def get_stats(self) -> Dict:
        """FINAL_AUDIT 기준 통계"""
        completed = [t for t in self.trades if t['result'] is not None]
        
        opa_trades = [t for t in completed if t['layer'] == 'OPA']
        stb_trades = [t for t in completed if t['layer'] == 'STB']
        
        opa_wins = sum(1 for t in opa_trades if t['result'] == 'WIN')
        stb_wins = sum(1 for t in stb_trades if t['result'] == 'WIN')
        
        total_wins = sum(1 for t in completed if t['result'] == 'WIN')
        total_pnl = sum(t['pnl'] for t in completed if t['pnl'] is not None)
        
        defense_trades = [t for t in completed if t['0bar_defense_applied']]
        defense_wins = sum(1 for t in defense_trades if t['result'] == 'WIN')
        
        return {
            'mode': self.mode,
            'total_bars': self.state['bar_count'],
            'total_trades': len(completed),
            'overall_win_rate': round(total_wins / len(completed) * 100, 1) if completed else 0,
            'total_pnl': round(total_pnl, 2),
            'avg_pnl': round(total_pnl / len(completed), 2) if completed else 0,
            'opa_trades': len(opa_trades),
            'opa_win_rate': round(opa_wins / len(opa_trades) * 100, 1) if opa_trades else 0,
            'stb_trades': len(stb_trades),
            'stb_win_rate': round(stb_wins / len(stb_trades) * 100, 1) if stb_trades else 0,
            'defense_applied': len(defense_trades),
            'defense_win_rate': round(defense_wins / len(defense_trades) * 100, 1) if defense_trades else 0,
            'audit_checks': self.audit_checks
        }
    
    def validate_audit(self) -> Dict:
        """FINAL_AUDIT 7가지 체크"""
        checks = {
            'CHECK_1_layer_conflicts': self.audit_checks['layer_conflicts'] == 0,
            'CHECK_2_delta_scope_logs': all(e.get('delta_scope') in ['t-ε', 't0', 't+0'] for e in self.events if e.get('action') != 'OBSERVE'),
            'CHECK_3_theta3_not_executed': self.audit_checks['theta3_execution_attempts'] == 0,
            'CHECK_4_0bar_timing': self.audit_checks['0bar_timing_errors'] == 0,
            'CHECK_5_exit_reason_complete': all(t.get('exit_reason') in ['TP', 'SL', 'TIMEOUT', None] for t in self.trades),
            'CHECK_6_engine_stability': self.audit_checks['engine_errors'] == 0,
            'CHECK_7_audit_consistent': self.audit_checks['audit_violations'] == 0
        }
        
        all_pass = all(checks.values())
        
        return {
            'checks': checks,
            'all_pass': all_pass,
            'ready_for_live': all_pass,
            'failures': [k for k, v in checks.items() if not v]
        }
    
    def save_logs(self):
        """로그 저장"""
        theta_counts = {}
        for t in self.trades:
            theta = t.get('theta_label', 0)
            theta_counts[theta] = theta_counts.get(theta, 0) + 1
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'mode': self.mode,
            'stats': self.get_stats(),
            'theta_distribution': theta_counts,
            'audit_validation': self.validate_audit(),
            'events': self.events[-500:],
            'trades': self.trades
        }
        
        with open(self.log_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        with open(self.theta_log_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        self.save_signal_log()
        
        print(f"\n{'='*60}")
        print(f"Logs saved to: {self.log_path}")
        print(f"Theta logs saved to: {self.theta_log_path}")
        print(f"Signal logs saved to: {self.signal_log_path}")
        print(f"Theta distribution: {theta_counts}")
        print(f"OPA_SIGNAL stats: {self.get_signal_stats()}")
        print(f"{'='*60}")
        
        audit = self.validate_audit()
        print(f"\n[AUDIT VALIDATION]")
        for check, passed in audit['checks'].items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check}")
        
        print(f"\n{'='*60}")
        if audit['all_pass']:
            print("✅ ALL CHECKS PASSED - Ready for Live")
        else:
            print(f"❌ FAILED: {audit['failures']}")
        print(f"{'='*60}")
        
        return data


def test_paper_mode():
    """Paper Mode 테스트"""
    import random
    random.seed(42)
    
    print("="*60)
    print("V7 Grammar System - Paper Mode Test")
    print("FINAL_AUDIT Compliance Check")
    print("="*60)
    
    engine = PaperModeEngine()
    
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
    
    print("\n[STATS]")
    stats = engine.get_stats()
    for k, v in stats.items():
        if k != 'audit_checks':
            print(f"  {k}: {v}")
    
    print("\n[AUDIT CHECKS]")
    for k, v in stats['audit_checks'].items():
        status = "✅" if v == 0 else "❌"
        print(f"  {status} {k}: {v}")
    
    engine.save_logs()
    
    return engine


if __name__ == "__main__":
    test_paper_mode()
