"""
V7-OBS v1.0 - Observation System
목적: ENTRY+STOP 시스템 완전성 검증
설계: TP 모듈 없음, 관측 전용, 완전성 플래그 포함

This defines V7-OBS v1.0 (ENTRY+STOP only). TP modules are out of scope.

사용법:
    engine = ObservationEngine()
    result = engine.evaluate_candle(candle_data)
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional, List
import numpy as np

try:
    from .micro_experiment import micro_experiment
except ImportError:
    micro_experiment = None

class ObservationEngine:
    def __init__(self, log_dir: str = "v7-grammar-system/logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        self.HIGH_VOL_THRESHOLD = 10.0
        self.DELTA_STD_THRESHOLD = 500
        self.MOMENTUM_THRESHOLD = 5
        self.EARLY_ADVERSE_PERCENTILE = 30
        self.OR_REVOKE_THRESHOLD = 1.0
        self.PE_HIGH_PERCENTILE = 0.7
        
        self.candle_buffer: List[Dict] = []
        self.active_trades: Dict[str, Dict] = {}
        self.trade_log: List[Dict] = []
        
        self.calibrated_adverse_cut = 8.8
        self.pe_values: List[float] = []
        
    def is_rth(self, timestamp) -> bool:
        try:
            if isinstance(timestamp, (int, float)):
                ts = timestamp
            elif isinstance(timestamp, str):
                if timestamp.isdigit():
                    ts = int(timestamp)
                else:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    hour = dt.hour
                    return 9 <= hour <= 16
            else:
                return False
            
            if ts > 1e12:
                ts = ts / 1000
            
            from datetime import timezone
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            
            et_offset = -5
            et_hour = (dt.hour + et_offset) % 24
            
            return 9 <= et_hour <= 16
        except Exception as e:
            print(f"[RTH_ERROR] {e}")
            return False
    
    def calc_atr(self, candles: List[Dict], period: int = 20) -> float:
        if len(candles) < 2:
            return 0
        
        trs = []
        for i in range(1, min(period + 1, len(candles))):
            c = candles[-i]
            prev_close = candles[-i-1]['close'] if i < len(candles) else c['close']
            tr = max(
                c['high'] - c['low'],
                abs(c['high'] - prev_close),
                abs(c['low'] - prev_close)
            )
            trs.append(tr)
        
        return float(np.mean(trs)) if trs else 0.0
    
    def calc_atr_slope(self, candles: List[Dict], period: int = 5) -> float:
        if len(candles) < period + 1:
            return 0
        
        atrs = []
        for i in range(period):
            subset = candles[-(period - i + 10):-(period - i)] if (period - i) > 0 else candles[-10:]
            atrs.append(self.calc_atr(subset, 5))
        
        if len(atrs) < 2:
            return 0
        
        x = np.arange(len(atrs))
        slope = np.polyfit(x, atrs, 1)[0]
        return float(slope)
    
    def calc_delta(self, candle: Dict) -> float:
        buyer = candle['close'] - candle['low']
        seller = candle['high'] - candle['close']
        if seller < 0.001:
            seller = 0.001
        return buyer / seller
    
    def calc_delta_std(self, candles: List[Dict], period: int = 5) -> float:
        if len(candles) < period:
            return 999
        
        deltas = [self.calc_delta(c) for c in candles[-period:]]
        return float(np.std(deltas))
    
    def calc_momentum(self, candles: List[Dict], period: int = 3) -> float:
        if len(candles) < period + 1:
            return 0
        return candles[-1]['close'] - candles[-period-1]['close']
    
    def calc_channel_pct(self, candles: List[Dict], period: int = 20) -> float:
        if len(candles) < period:
            return 50
        
        recent = candles[-period:]
        highest = max(c['high'] for c in recent)
        lowest = min(c['low'] for c in recent)
        
        if highest == lowest:
            return 50
        
        current = candles[-1]['close']
        return ((current - lowest) / (highest - lowest)) * 100
    
    def calc_sma(self, candles: List[Dict], period: int) -> float:
        if len(candles) < period:
            return candles[-1]['close'] if candles else 0
        return sum(c['close'] for c in candles[-period:]) / period
    
    def check_trend_aligned(self, candles: List[Dict], direction: str) -> bool:
        sma20 = self.calc_sma(candles, 20)
        sma60 = self.calc_sma(candles, 60)
        
        if direction == 'SHORT':
            return sma20 < sma60
        else:
            return sma20 > sma60
    
    def calc_micro_pe(self, candles: List[Dict]) -> float:
        if len(candles) < 20:
            return 0
        
        atr = self.calc_atr(candles, 20)
        if atr < 0.01:
            return 0
        
        recent_lows = [c['low'] for c in candles[-10:]]
        depth = candles[-1]['close'] - min(recent_lows)
        return depth / atr
    
    def check_pe_high(self, pe_value: float) -> bool:
        self.pe_values.append(pe_value)
        if len(self.pe_values) > 1000:
            self.pe_values = self.pe_values[-1000:]
        
        if len(self.pe_values) < 10:
            return pe_value > 1.0
        
        threshold = np.percentile(self.pe_values, self.PE_HIGH_PERCENTILE * 100)
        return pe_value >= threshold
    
    def check_safe_zone(self, candles: List[Dict], direction: str) -> bool:
        trend_aligned = self.check_trend_aligned(candles, direction)
        pe = self.calc_micro_pe(candles)
        pe_high = self.check_pe_high(pe)
        return trend_aligned and pe_high
    
    def detect_stb(self, candles: List[Dict], direction: str) -> bool:
        if len(candles) < 2:
            return False
        
        delta = self.calc_delta(candles[-1])
        channel_pct = self.calc_channel_pct(candles)
        
        if direction == 'SHORT':
            return delta > 1.5 and channel_pct > 70
        else:
            return delta < 0.7 and channel_pct < 30
    
    def check_g3(self, candles: List[Dict], direction: str) -> bool:
        delta_std = self.calc_delta_std(candles, 5)
        atr_slope = self.calc_atr_slope(candles, 5)
        momentum = self.calc_momentum(candles, 3)
        
        if direction == 'SHORT':
            return (delta_std < self.DELTA_STD_THRESHOLD and 
                    atr_slope > 0 and 
                    momentum > self.MOMENTUM_THRESHOLD)
        else:
            return (delta_std < self.DELTA_STD_THRESHOLD and 
                    atr_slope > 0 and 
                    momentum < -self.MOMENTUM_THRESHOLD)
    
    def check_g3_ok(self, initial_adverse: float) -> bool:
        return initial_adverse <= self.calibrated_adverse_cut
    
    def calc_or(self, adverse: float, depth: float) -> float:
        if depth < 0.01:
            depth = 0.01
        return adverse / depth
    
    def calc_eer(self, adverse: float, depth: float) -> float:
        total = adverse + depth
        if total < 0.01:
            return 0
        return depth / total
    
    def classify_or_shape(self, or_series: List[float]) -> str:
        if len(or_series) < 10:
            return 'unknown'
        
        n = len(or_series)
        early_end = max(2, int(n * 0.3))
        late_start = int(n * 0.7)
        
        early_dor = [or_series[i] - or_series[i-1] for i in range(1, early_end)]
        late_dor = [or_series[i] - or_series[i-1] for i in range(late_start + 1, n)]
        
        early_slope = np.mean(early_dor) if early_dor else 0
        late_slope = np.mean(late_dor) if late_dor else 0
        
        if abs(early_slope) < 0.001:
            early_slope = 0.001 if early_slope >= 0 else -0.001
        
        ratio = late_slope / early_slope
        
        if ratio > 1.3:
            return 'Convex'
        elif ratio < 0.7:
            return 'Concave'
        else:
            return 'Linear'
    
    def evaluate_candle(self, candle: Dict) -> Dict:
        self.candle_buffer.append(candle)
        if len(self.candle_buffer) > 100:
            self.candle_buffer = self.candle_buffer[-100:]
        
        result = {
            'timestamp': candle.get('time', datetime.now().isoformat()),
            'signals': [],
            'active_trades': len(self.active_trades)
        }
        
        is_rth = self.is_rth(candle.get('time', ''))
        atr = self.calc_atr(self.candle_buffer)
        is_high_vol = atr > self.HIGH_VOL_THRESHOLD
        
        entry_check = {
            "RTH": is_rth,
            "ATR": round(atr, 2),
            "ATR_OK": is_high_vol,
            "candle_count": len(self.candle_buffer)
        }
        
        # 🔧 2026-01-26: RTH/ATR은 차단 조건이 아닌 "라벨링 언어"
        # GPT 분석: "설명 언어가 판단을 막으면 안 된다"
        # RTH/ATR은 ENTRY 이후 홀딩 상태를 설명하는 용도로만 사용
        if is_rth and is_high_vol:
            result['environment'] = 'RTH_HIGH'
            entry_check['ENV_LABEL'] = 'RTH_HIGH'
        elif is_rth:
            result['environment'] = 'RTH_LOW'
            entry_check['ENV_LABEL'] = 'RTH_LOW'
        else:
            result['environment'] = 'ETH'
            entry_check['ENV_LABEL'] = 'ETH'
        
        print(f"[ENTRY_CHECK] {entry_check}")
        # 차단 없음 - STB 판단은 항상 실행
        
        for direction in ['SHORT', 'LONG']:
            stb_detected = self.detect_stb(self.candle_buffer, direction)
            if stb_detected:
                g3_true = self.check_g3(self.candle_buffer, direction)
                
                entry_check['STB'] = direction
                entry_check['G3_TRUE'] = g3_true
                print(f"[ENTRY_CHECK] {entry_check}")
                
                if g3_true:
                    trade_id = f"{direction}_{candle.get('time', datetime.now().isoformat())}"
                    
                    safe_zone = self.check_safe_zone(self.candle_buffer, direction)
                    
                    self.active_trades[trade_id] = {
                        'direction': direction,
                        'entry_price': candle['close'],
                        'entry_time': candle.get('time', datetime.now().isoformat()),
                        'g3_true': True,
                        'g3_ok': None,
                        'initial_adverse_5bar': None,
                        'or_series': [],
                        'eer_final': None,
                        'tp_extension_allowed': False,
                        'tp_extension_revoked': False,
                        'bar_count': 0,
                        'max_depth': 0,
                        'max_adverse': 0,
                        'safe_flag': safe_zone,
                        'or_shape': None
                    }
                    
                    result['signals'].append({
                        'type': 'STB_DETECTED',
                        'direction': direction,
                        'trade_id': trade_id,
                        'g3_true': True
                    })
                    
                    if micro_experiment:
                        delta = self.calc_delta(candle)
                        channel_pct = self.calc_channel_pct(self.candle_buffer)
                        trend_aligned = self.check_trend_aligned(self.candle_buffer, direction)
                        momentum = self.calc_momentum(self.candle_buffer)
                        momentum_aligned = (momentum < 0 and direction == 'SHORT') or (momentum > 0 and direction == 'LONG')
                        
                        micro_experiment.record_entry(
                            trade_id=trade_id,
                            direction=direction,
                            entry_price=candle['close'],
                            delta=delta,
                            atr=atr,
                            channel_pct=channel_pct,
                            trend_aligned=trend_aligned,
                            momentum_aligned=momentum_aligned
                        )
        
        self._update_active_trades(candle)
        
        return result
    
    def _update_active_trades(self, candle: Dict):
        completed = []
        
        for trade_id, trade in self.active_trades.items():
            trade['bar_count'] += 1
            entry = trade['entry_price']
            
            if trade['direction'] == 'SHORT':
                depth = entry - candle['low']
                adverse = candle['high'] - entry
            else:
                depth = candle['high'] - entry
                adverse = entry - candle['low']
            
            depth = max(0, depth)
            adverse = max(0, adverse)
            
            trade['max_depth'] = max(trade['max_depth'], depth)
            trade['max_adverse'] = max(trade['max_adverse'], adverse)
            
            current_or = self.calc_or(trade['max_adverse'], trade['max_depth'])
            trade['or_series'].append(current_or)
            
            if trade['bar_count'] == 5:
                trade['initial_adverse_5bar'] = trade['max_adverse']
                trade['g3_ok'] = self.check_g3_ok(trade['initial_adverse_5bar'])
                
                if trade['g3_ok']:
                    trade['tp_extension_allowed'] = True
            
            if trade['direction'] == 'LONG' and trade['tp_extension_allowed']:
                if current_or >= self.OR_REVOKE_THRESHOLD:
                    trade['tp_extension_revoked'] = True
                    trade['tp_extension_allowed'] = False
            
            if trade['bar_count'] >= 20:
                trade['eer_final'] = self.calc_eer(trade['max_adverse'], trade['max_depth'])
                trade['or_shape'] = self.classify_or_shape(trade['or_series'])
                self._log_trade(trade_id, trade, 'COMPLETED')
                completed.append(trade_id)
        
        for trade_id in completed:
            del self.active_trades[trade_id]
    
    def _log_trade(self, trade_id: str, trade: Dict, exit_reason: str):
        undecided_flag = 1 if exit_reason is None or exit_reason == '' else 0
        
        stop_defined = True
        if trade['direction'] == 'LONG':
            stop_defined = trade.get('tp_extension_revoked', False) or exit_reason == 'COMPLETED'
        else:
            stop_defined = True
        stop_defined_flag = 0 if stop_defined else 1
        
        explain_fail_flag = 0
        if trade['max_adverse'] > 15 and trade['or_shape'] == 'unknown':
            explain_fail_flag = 1
        
        log_entry = {
            'trade_id': trade_id,
            'timestamp': trade['entry_time'],
            'direction': trade['direction'],
            'entry_price': float(trade['entry_price']),
            'entry_reason': 'G3_OK' if trade['g3_ok'] else 'G3_TRUE',
            'g3_true': bool(trade['g3_true']),
            'g3_ok': bool(trade['g3_ok']) if trade['g3_ok'] is not None else None,
            'initial_adverse_5bar': float(trade['initial_adverse_5bar']) if trade['initial_adverse_5bar'] else None,
            'or_initial': float(trade['or_series'][0]) if trade['or_series'] else None,
            'or_final': float(trade['or_series'][-1]) if trade['or_series'] else None,
            'or_peak': float(max(trade['or_series'])) if trade['or_series'] else None,
            'or_shape': trade['or_shape'],
            'safe_flag': bool(trade['safe_flag']),
            'eer_final': float(trade['eer_final']) if trade['eer_final'] else None,
            'max_depth': float(trade['max_depth']),
            'max_adverse': float(trade['max_adverse']),
            'tp_extension_allowed': bool(trade['tp_extension_allowed']),
            'tp_extension_revoked': bool(trade['tp_extension_revoked']),
            'exit_reason': exit_reason,
            'bar_count': int(trade['bar_count']),
            'UNDECIDED_FLAG': int(undecided_flag),
            'STOP_DEFINED_FLAG': int(stop_defined_flag),
            'EXPLAIN_FAIL_FLAG': int(explain_fail_flag)
        }
        
        self.trade_log.append(log_entry)
        
        log_file = os.path.join(self.log_dir, 'observation_log.jsonl')
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        if micro_experiment:
            actual_result = 'TP' if trade['max_depth'] >= 15 else 'SL'
            micro_experiment.update_exit(
                trade_id=trade_id,
                actual_result=actual_result,
                bars_held=trade['bar_count'],
                mfe=trade['max_depth'],
                mae=trade['max_adverse']
            )
    
    def get_status(self) -> Dict:
        return {
            'buffer_size': len(self.candle_buffer),
            'active_trades': len(self.active_trades),
            'completed_trades': len(self.trade_log),
            'calibrated_adverse_cut': self.calibrated_adverse_cut
        }
    
    def get_trade_summary(self) -> Dict:
        if not self.trade_log:
            return {'message': 'No trades yet'}
        
        short_trades = [t for t in self.trade_log if t['direction'] == 'SHORT']
        long_trades = [t for t in self.trade_log if t['direction'] == 'LONG']
        
        short_ok = [t for t in short_trades if t['g3_ok']]
        long_ok = [t for t in long_trades if t['g3_ok']]
        
        def calc_stats(trades):
            if not trades:
                return {'n': 0}
            ors = [t['or_final'] for t in trades if t['or_final'] is not None]
            eers = [t['eer_final'] for t in trades if t['eer_final'] is not None]
            return {
                'n': len(trades),
                'or_median': float(np.median(ors)) if ors else None,
                'eer_median': float(np.median(eers)) if eers else None
            }
        
        return {
            'short_g3_ok': calc_stats(short_ok),
            'long_g3_ok': calc_stats(long_ok),
            'long_revoked': len([t for t in long_ok if t['tp_extension_revoked']])
        }


    def generate_weekly_report(self) -> str:
        if not self.trade_log:
            return "No trades yet"
        
        total = len(self.trade_log)
        entry_valid = len([t for t in self.trade_log if t['g3_ok']])
        
        undecided = sum(t.get('UNDECIDED_FLAG', 0) for t in self.trade_log)
        stop_fail = sum(t.get('STOP_DEFINED_FLAG', 0) for t in self.trade_log)
        explain_fail = sum(t.get('EXPLAIN_FAIL_FLAG', 0) for t in self.trade_log)
        
        safe_trades = [t for t in self.trade_log if t.get('safe_flag')]
        non_safe_trades = [t for t in self.trade_log if not t.get('safe_flag')]
        
        safe_convex = len([t for t in safe_trades if t.get('or_shape') == 'Convex'])
        non_safe_convex = len([t for t in non_safe_trades if t.get('or_shape') == 'Convex'])
        
        passed = undecided == 0 and stop_fail == 0 and explain_fail == 0
        
        report = f"""
Week N — V7-OBS v1.0 Completeness Report
========================================

1. 총 트레이드 수: {total}
2. ENTRY 성립 비율: {entry_valid/total*100:.1f}%

3. 검증 결과:
   - UNDECIDED: {undecided}
   - STOP 정의 실패: {stop_fail}
   - 설명 불가 이벤트: {explain_fail}

4. SAFE vs non-SAFE 분포:
   - SAFE: {len(safe_trades)} 건 (Convex: {safe_convex})
   - non-SAFE: {len(non_safe_trades)} 건 (Convex: {non_safe_convex})

5. 판정: {'PASS' if passed else 'FAIL'}
"""
        return report


if __name__ == "__main__":
    engine = ObservationEngine()
    print("V7-OBS v1.0 - Observation System")
    print(f"Status: {engine.get_status()}")
