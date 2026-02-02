"""
V7 미시 실험 모듈 - 손실 구조 개선 검증
2026-01-26

목적: 방향 변경 없이 손실 분포만 개선되는지 확인
설계: ENTRY 취소 금지, 가상 분기로만 기록

4가지 미시 판정:
1. Expansion Eligibility: ELIGIBLE / DENIED
2. Entry Quality: EARLY / MID / LATE
3. Context Fit: FIT / NEUTRAL / MISFIT
4. Early Failure: NORMAL / EARLY_FAILURE

가상 행동 매핑 (실행 X, 기록 O):
- ELIGIBLE + EARLY + FIT + NORMAL → HOLD_CONTINUE
- DENIED or MISFIT → NO_HOLD / FAST_EXIT
- LATE → BE / REDUCED_TP
- EARLY_FAILURE → DEFENSIVE_EXIT
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional, List

MICRO_LOG_FILE = "v7-grammar-system/logs/micro_experiment.json"

class MicroExperiment:
    def __init__(self):
        self.entries: List[Dict] = []
        self.load_state()
        
    def load_state(self):
        try:
            if os.path.exists(MICRO_LOG_FILE):
                with open(MICRO_LOG_FILE, 'r') as f:
                    data = json.load(f)
                    self.entries = data.get('entries', [])
        except Exception as e:
            print(f"[MICRO] 상태 로드 실패: {e}")
            self.entries = []
    
    def save_state(self):
        os.makedirs(os.path.dirname(MICRO_LOG_FILE), exist_ok=True)
        try:
            with open(MICRO_LOG_FILE, 'w') as f:
                json.dump({
                    'entries': self.entries,
                    'updated': datetime.now().isoformat(),
                    'count': len(self.entries)
                }, f, indent=2)
        except Exception as e:
            print(f"[MICRO] 상태 저장 실패: {e}")
    
    def assess_expansion_eligibility(self, delta: float, atr: float, channel_pct: float) -> str:
        if atr < 10:
            return "DENIED"
        if delta > 1.5 or delta < 0.5:
            return "ELIGIBLE"
        return "DENIED"
    
    def assess_entry_quality(self, channel_pct: float, direction: str) -> str:
        if direction == "SHORT":
            if channel_pct >= 80:
                return "EARLY"
            elif channel_pct >= 50:
                return "MID"
            else:
                return "LATE"
        else:
            if channel_pct <= 20:
                return "EARLY"
            elif channel_pct <= 50:
                return "MID"
            else:
                return "LATE"
    
    def assess_context_fit(self, trend_aligned: bool, momentum_aligned: bool) -> str:
        if trend_aligned and momentum_aligned:
            return "FIT"
        elif not trend_aligned and not momentum_aligned:
            return "MISFIT"
        return "NEUTRAL"
    
    def assess_early_failure(self, bars_held: int, mfe: float, mae: float) -> str:
        if bars_held <= 3 and mfe < 5 and mae > 10:
            return "EARLY_FAILURE"
        return "NORMAL"
    
    def compute_virtual_action(self, eligibility: str, quality: str, context: str, failure: str) -> str:
        if failure == "EARLY_FAILURE":
            return "DEFENSIVE_EXIT"
        if eligibility == "DENIED" or context == "MISFIT":
            return "FAST_EXIT"
        if quality == "LATE":
            return "BE_OR_REDUCED_TP"
        if eligibility == "ELIGIBLE" and quality == "EARLY" and context == "FIT":
            return "HOLD_CONTINUE"
        return "HOLD_NORMAL"
    
    def record_entry(self, trade_id: str, direction: str, entry_price: float,
                     delta: float, atr: float, channel_pct: float,
                     trend_aligned: bool, momentum_aligned: bool) -> Dict:
        eligibility = self.assess_expansion_eligibility(delta, atr, channel_pct)
        quality = self.assess_entry_quality(channel_pct, direction)
        context = self.assess_context_fit(trend_aligned, momentum_aligned)
        
        entry = {
            'trade_id': trade_id,
            'timestamp': datetime.now().isoformat(),
            'direction': direction,
            'entry_price': entry_price,
            'delta': delta,
            'atr': atr,
            'channel_pct': channel_pct,
            'assessments': {
                'eligibility': eligibility,
                'quality': quality,
                'context': context,
                'failure': None
            },
            'virtual_action': None,
            'actual_result': None,
            'virtual_result': None,
            'bars_held': 0,
            'mfe': 0,
            'mae': 0
        }
        
        self.entries.append(entry)
        self.save_state()
        
        print(f"[MICRO_ENTRY] {trade_id} | ELG={eligibility} QTY={quality} CTX={context}")
        return entry
    
    def update_exit(self, trade_id: str, actual_result: str, 
                    bars_held: int, mfe: float, mae: float) -> Optional[Dict]:
        for entry in self.entries:
            if entry['trade_id'] == trade_id:
                entry['bars_held'] = bars_held
                entry['mfe'] = mfe
                entry['mae'] = mae
                entry['actual_result'] = actual_result
                
                failure = self.assess_early_failure(bars_held, mfe, mae)
                entry['assessments']['failure'] = failure
                
                virtual_action = self.compute_virtual_action(
                    entry['assessments']['eligibility'],
                    entry['assessments']['quality'],
                    entry['assessments']['context'],
                    failure
                )
                entry['virtual_action'] = virtual_action
                
                if actual_result == "SL":
                    if virtual_action == "DEFENSIVE_EXIT":
                        entry['virtual_result'] = "DEFENSIVE"
                    elif virtual_action == "FAST_EXIT":
                        entry['virtual_result'] = "FAST_EXIT"
                    elif virtual_action == "BE_OR_REDUCED_TP":
                        entry['virtual_result'] = "BE"
                    else:
                        entry['virtual_result'] = "SL"
                else:
                    entry['virtual_result'] = actual_result
                
                self.save_state()
                
                print(f"[MICRO_EXIT] {trade_id} | ACT={actual_result} → VIRT={entry['virtual_result']} | action={virtual_action}")
                return entry
        
        return None
    
    def get_summary(self) -> Dict:
        total = len(self.entries)
        completed = [e for e in self.entries if e['actual_result']]
        
        sl_count = sum(1 for e in completed if e['actual_result'] == 'SL')
        tp_count = sum(1 for e in completed if e['actual_result'] == 'TP')
        
        sl_to_be_def = sum(1 for e in completed 
                          if e['actual_result'] == 'SL' 
                          and e['virtual_result'] in ['BE', 'DEFENSIVE', 'FAST_EXIT'])
        
        tp_damaged = sum(1 for e in completed 
                        if e['actual_result'] == 'TP' 
                        and e['virtual_result'] != 'TP')
        
        conversion_rate = (sl_to_be_def / sl_count * 100) if sl_count > 0 else 0
        
        return {
            'total_entries': total,
            'completed': len(completed),
            'actual': {'TP': tp_count, 'SL': sl_count},
            'sl_converted_to_be_def': sl_to_be_def,
            'tp_damaged': tp_damaged,
            'conversion_rate_pct': round(conversion_rate, 1),
            'pass_threshold': 30,
            'status': 'PASS' if conversion_rate >= 30 and tp_damaged == 0 else 'PENDING'
        }
    
    def print_report(self):
        summary = self.get_summary()
        print("\n" + "="*50)
        print("📊 미시 실험 중간 보고")
        print("="*50)
        print(f"총 ENTRY: {summary['total_entries']}")
        print(f"완료: {summary['completed']}")
        print(f"실제 TP/SL: {summary['actual']['TP']}/{summary['actual']['SL']}")
        print(f"SL→BE/DEF 전환: {summary['sl_converted_to_be_def']}건")
        print(f"TP 훼손: {summary['tp_damaged']}건")
        print(f"전환율: {summary['conversion_rate_pct']}%")
        print(f"판정: {summary['status']} (기준: ≥30%, TP훼손=0)")
        print("="*50 + "\n")

micro_experiment = MicroExperiment()
