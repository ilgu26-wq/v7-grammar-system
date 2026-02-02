"""
V7 Grammar System - Candle Validator
입력 레이어 방어: 중복, Out-of-order, 스키마 오류 차단

2026-01-23 구현
"""

import os
import json
from datetime import datetime
from typing import Dict, Optional, Tuple

LAST_TS_FILE = os.path.join(os.path.dirname(__file__), 'last_candle_ts.json')

last_ts = None
seen_timestamps = set()


def load_last_ts() -> Optional[int]:
    """재시작 후 복구용: 마지막 처리 timestamp 로드"""
    global last_ts
    try:
        if os.path.exists(LAST_TS_FILE):
            with open(LAST_TS_FILE, 'r') as f:
                data = json.load(f)
                last_ts = data.get('last_ts')
                return last_ts
    except Exception as e:
        print(f"[CANDLE_VALIDATOR] last_ts 로드 실패: {e}")
    return None


def save_last_ts(ts: int):
    """마지막 처리 timestamp 저장"""
    global last_ts
    last_ts = ts
    try:
        with open(LAST_TS_FILE, 'w') as f:
            json.dump({'last_ts': ts, 'updated': datetime.now().isoformat()}, f)
    except Exception as e:
        print(f"[CANDLE_VALIDATOR] last_ts 저장 실패: {e}")


def validate_candle_schema(data: Dict) -> Tuple[bool, str]:
    """
    H-A3, H-A4: 캔들 스키마 검증
    Returns: (valid, error_message)
    """
    required_fields = ['time', 'open', 'high', 'low', 'close']
    
    for field in required_fields:
        if field not in data:
            return False, f"MISSING_FIELD:{field}"
        
        value = data[field]
        if field == 'time':
            if not value:
                return False, f"EMPTY_FIELD:{field}"
        else:
            try:
                num_val = float(value)
                if num_val <= 0:
                    return False, f"INVALID_VALUE:{field}={value}"
            except (ValueError, TypeError):
                return False, f"TYPE_ERROR:{field}={type(value).__name__}"
    
    high = float(data['high'])
    low = float(data['low'])
    open_price = float(data['open'])
    close = float(data['close'])
    
    if high < low:
        return False, f"INVALID_RANGE:high({high})<low({low})"
    
    if close < low or close > high:
        return False, f"CLOSE_OUT_OF_RANGE:close={close},range=[{low},{high}]"
    
    if open_price < low or open_price > high:
        return False, f"OPEN_OUT_OF_RANGE:open={open_price},range=[{low},{high}]"
    
    return True, "OK"


def check_out_of_order(ts: str) -> Tuple[bool, str]:
    """
    H-A2: Out-of-order 캔들 차단
    Returns: (valid, error_message)
    """
    global last_ts
    
    if last_ts is None:
        load_last_ts()
    
    try:
        current_ts = int(ts)
    except (ValueError, TypeError):
        return False, f"INVALID_TIMESTAMP:{ts}"
    
    # 🛡️ 미래 타임스탬프 보호 가드 (2026-01-26 추가)
    # last_ts가 현재 시각보다 미래면 오염 상태 → 리셋
    import time
    now_ms = int(time.time() * 1000)
    if last_ts is not None and last_ts > now_ms + 120_000:  # 2분 허용
        print(f"[TS_RESET] last_ts in future! last={last_ts}, now={now_ms}, delta={last_ts - now_ms}ms → RESET")
        reset_validator_state()
        return True, "OK"  # 리셋 후 통과
    
    if last_ts is not None and current_ts <= last_ts:
        return False, f"OUT_OF_ORDER:current={current_ts},last={last_ts}"
    
    return True, "OK"


def reset_validator_state():
    """타임스탬프 상태 리셋 (미래 오염 복구용)"""
    global last_ts, seen_timestamps
    last_ts = None
    seen_timestamps = set()
    try:
        if os.path.exists(LAST_TS_FILE):
            os.remove(LAST_TS_FILE)
            print(f"[TS_RESET] last_candle_ts.json 삭제 완료")
    except Exception as e:
        print(f"[TS_RESET] 파일 삭제 실패: {e}")


def check_duplicate(ts: str) -> Tuple[bool, str]:
    """
    H-A1: 중복 캔들 차단
    Returns: (valid, error_message)
    """
    global seen_timestamps
    
    if ts in seen_timestamps:
        return False, f"DUPLICATE:{ts}"
    
    return True, "OK"


def register_candle(ts: str):
    """캔들 처리 완료 등록"""
    global seen_timestamps
    
    seen_timestamps.add(ts)
    if len(seen_timestamps) > 500:
        oldest = sorted(seen_timestamps)[:250]
        seen_timestamps.difference_update(set(oldest))
    
    try:
        save_last_ts(int(ts))
    except:
        pass


def validate_candle_full(data: Dict) -> Dict:
    """
    전체 캔들 검증 (스키마 + 순서 + 중복)
    
    Returns:
        {
            'valid': bool,
            'errors': list,
            'action': 'ACCEPT' | 'REJECT'
        }
    """
    errors = []
    
    schema_valid, schema_msg = validate_candle_schema(data)
    if not schema_valid:
        errors.append(f"SCHEMA:{schema_msg}")
    
    ts = data.get('time', '')
    
    dup_valid, dup_msg = check_duplicate(ts)
    if not dup_valid:
        errors.append(f"DUP:{dup_msg}")
    
    order_valid, order_msg = check_out_of_order(ts)
    if not order_valid:
        errors.append(f"ORDER:{order_msg}")
    
    if errors:
        print(f"[CANDLE_REJECT] {errors}")
        return {
            'valid': False,
            'errors': errors,
            'action': 'REJECT'
        }
    
    register_candle(ts)
    
    return {
        'valid': True,
        'errors': [],
        'action': 'ACCEPT'
    }


def get_validator_status() -> Dict:
    """검증기 상태 조회"""
    global last_ts, seen_timestamps
    return {
        'last_ts': last_ts,
        'seen_count': len(seen_timestamps),
        'last_ts_file': LAST_TS_FILE,
        'file_exists': os.path.exists(LAST_TS_FILE)
    }


load_last_ts()
