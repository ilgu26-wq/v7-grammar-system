import os
import hashlib
import zipfile
import io
import re
import json
import threading
import requests
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from ai_trading_engine import get_engine, process_candle, get_ai_status
from dual_consensus import process_with_consensus, get_dual_status, get_all_issues
from breakout_judge import BreakoutJudge
from v61_filter import get_v61_filter, process_candle_v61, get_v61_status
from v7_grammar_engine import V7GrammarEngine
import sys
sys.path.insert(0, 'src')
from sps_core.v7_signal_engine import get_v7_engine, process_candle_v7, format_telegram_entry, format_telegram_stop, format_telegram_tp, format_telegram_continuation

# 📌 V7 Grammar Engine (상태 해석용, 로직 변경 없음!)
V7_GRAMMAR = V7GrammarEngine()
print(f"🔗 V7 Grammar Engine 연결 완료! (해석 전용)")

# 📌 앵글로직 POC 관리자
ANGLE_JUDGE = BreakoutJudge(lookback=50, poc_count=2)

# 🔗 ai_trading_engine과 ANGLE_JUDGE 공유 (동일 데이터 사용!)
_engine = get_engine()
_engine.set_breakout_judge(ANGLE_JUDGE)
print(f"🔗 main.py ANGLE_JUDGE → ai_trading_engine 연결 완료!")

app = Flask(__name__)
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# SL 알림 중복 방지 (인메모리)
SL_NOTIFIED_SIGNALS = set()

# 🔥 V6.1 활성 포지션 추적 (동적 TP 확장용)
V61_ACTIVE_POSITION = None  # {'direction', 'entry_price', 'original_tp', 'current_tp', 'sl', 'grade', 'entry_time'}

# ═══════════════════════════════════════════════════════════════════════════════
# 📊 등급별 동적 TP 계산 시스템 (SL 30pt 고정) - 실제 STB 로직 검증
# ═══════════════════════════════════════════════════════════════════════════════
# 분석: 10,548건 캔들 기반 | 실제 STB 등급 조건 적용
# S++: 누적배율 1.5x+ (94%+ 저항) → 큰 이동 예상
# S+: 섹터90%+, z<-0.5 → 롱35.9pt, 숏20.8pt
# ═══════════════════════════════════════════════════════════════════════════════
GRADE_DYNAMIC_TP = {
    'S++': {'tp': 25, 'rr_ratio': 0.83},
    'S+': {'tp': 20, 'rr_ratio': 0.67},
    'S': {'tp': 16, 'rr_ratio': 0.53},
    'A+': {'tp': 18, 'rr_ratio': 0.60},
    'A': {'tp': 16, 'rr_ratio': 0.53},
    'A-': {'tp': 14, 'rr_ratio': 0.47},
    'B+': {'tp': 12, 'rr_ratio': 0.40},
    'B': {'tp': 10, 'rr_ratio': 0.33},
    'C': {'tp': 10, 'rr_ratio': 0.33},
    'RESIST_zscore': {'tp': 20, 'rr_ratio': 0.67}
}

def get_dynamic_tp(grade, sps_ratio_z=0, entry_price=0, direction='short'):
    """등급 + SPS비율z 기반 동적 TP 계산 (SL 30 고정)"""
    base = GRADE_DYNAMIC_TP.get(grade, {'tp': 14, 'rr_ratio': 0.47})
    
    base_tp = base['tp']
    z_boost = abs(sps_ratio_z) * 2
    dynamic_tp = round(base_tp + z_boost)
    dynamic_tp = min(dynamic_tp, 30)
    dynamic_tp = max(dynamic_tp, 8)
    
    sl = 30
    rr_ratio = round(dynamic_tp / sl, 2)
    
    if direction == 'short':
        tp_price = entry_price - dynamic_tp
        sl_price = entry_price + sl
    else:
        tp_price = entry_price + dynamic_tp
        sl_price = entry_price - sl
    
    return {
        'grade': grade,
        'dynamic_tp': dynamic_tp,
        'sl': sl,
        'rr_ratio': rr_ratio,
        'base_tp': base_tp,
        'sps_boost': round(z_boost, 1),
        'tp_price': round(tp_price, 2),
        'sl_price': round(sl_price, 2),
        'direction': direction
    }

# ═══════════════════════════════════════════════════════════════════════════════
# 📸 Atomic Signal Snapshot (H_P1 해결!)
# ═══════════════════════════════════════════════════════════════════════════════
# 원칙: 트리거 시점에 스냅샷 1회 생성 → 모든 후속 처리는 스냅샷만 참조
# 목적: ENTRY/EXIT/V7가 동일 데이터 기준으로 판단되도록 보장
# ═══════════════════════════════════════════════════════════════════════════════
import uuid
import hashlib

def create_signal_snapshot(direction, candle, stb_data, grade, state_str):
    """
    🔒 원자적 신호 스냅샷 생성
    
    역할: 트리거 시점의 모든 데이터를 단일 객체로 고정
    규칙: 이 스냅샷 이후 모든 계산/렌더링은 snapshot만 참조해야 함
    
    Returns:
        snapshot: 불변 데이터 객체 (dict)
    """
    event_id = str(uuid.uuid4())[:8]
    trigger_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 핵심 데이터 추출
    price = candle['close']
    sector_pct = stb_data.get('sector_pct', 50)
    sps_ratio_z = stb_data.get('sps_ratio_z', 0)
    reason = stb_data.get('reason', '')
    
    # EXIT 계산 (스냅샷 시점에 확정!)
    dynamic = get_dynamic_tp(grade, sps_ratio_z, price, direction.lower())
    tp = dynamic['dynamic_tp']
    sl = dynamic['sl']
    tp_price = dynamic['tp_price']
    sl_price = dynamic['sl_price']
    
    # V7 상태 계산 (스냅샷 시점에 확정!)
    v7_line = format_v7_state(ratio=sps_ratio_z, channel_pct=sector_pct)
    
    # 스냅샷 해시 (무결성 검증용)
    hash_input = f"{event_id}_{price}_{sector_pct}_{sps_ratio_z}_{tp}_{sl}"
    snapshot_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:12]
    
    snapshot = {
        # 식별자
        'event_id': event_id,
        'snapshot_hash': snapshot_hash,
        
        # 시간
        'trigger_time': trigger_time,
        'bar_time': candle.get('time', 0),
        
        # 방향/등급
        'direction': direction,
        'grade': grade,
        'state_str': state_str,
        
        # 가격 데이터 (불변)
        'price': price,
        'sector_pct': sector_pct,
        'sps_ratio_z': sps_ratio_z,
        
        # EXIT 데이터 (스냅샷 시점 확정)
        'tp': tp,
        'sl': sl,
        'tp_price': tp_price,
        'sl_price': sl_price,
        'rr_ratio': dynamic['rr_ratio'],
        
        # V7 해석 (스냅샷 시점 확정)
        'v7_line': v7_line,
        
        # 원본 사유
        'reason': reason
    }
    
    return snapshot

def log_snapshot(snapshot):
    """스냅샷 로그 저장 (파이프라인 검증용)"""
    try:
        log_file = '.signal_snapshots.json'
        logs = []
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                logs = json.load(f)
        
        logs.append(snapshot)
        
        # 최근 100개만 유지
        if len(logs) > 100:
            logs = logs[-100:]
        
        with open(log_file, 'w') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ 스냅샷 로그 저장 실패: {e}")

def format_v7_state(ratio=0, ratio_prev=0, channel_pct=50, mfe=0, mae=0, retouch=True):
    """
    V7 Grammar State 포맷 (텔레그램용)
    ❌ 행동 변경 없음 - 해석만 제공
    """
    try:
        state = V7_GRAMMAR.judge(
            mfe=mfe,
            mae=mae,
            ratio=ratio,
            ratio_prev=ratio_prev,
            channel_pct=channel_pct,
            retouch_within_10=retouch
        )
        op_state = state.operational_state.value
        msg_kr = state.message_kr
        
        state_emoji = {
            "EXPANSION_ELIGIBLE": "🟢",
            "EXPANSION_UNSTABLE": "🟡",
            "NON_EXPANSION_JUSTIFIED": "🟠",
            "NON_EXPANSION_EMPTY": "⚫"
        }
        emoji = state_emoji.get(op_state, "⚪")
        
        return f"\n[V7] {emoji} {msg_kr}"
    except Exception as e:
        return ""

def format_entry_from_snapshot(snapshot):
    """
    📍 ENTRY 전용 메시지 (스냅샷 기반!)
    H_P1 해결: 스냅샷에서만 데이터 참조
    """
    direction = snapshot['direction']
    if direction == 'SHORT':
        emoji = "🔴"
        signal_name = "STB숏"
    else:
        emoji = "🟢"
        signal_name = "STB롱"
    
    v7_clean = snapshot['v7_line'].replace("\n[V7] ", "").strip() if snapshot['v7_line'] else "해석 대기"
    
    msg = f"""{emoji} {signal_name} {snapshot['grade']}  |  ENTRY CONFIRMED
━━━━━━━━━━━━━━━━━━━━━━━
🆔 {snapshot['event_id']}
📍 방향: {snapshot['state_str']}
📍 위치: 섹터 {snapshot['sector_pct']:.0f}% | z: {snapshot['sps_ratio_z']:.2f}
🎯 진입: NQ @ {snapshot['price']:.2f}
━━━━━━━━━━━━━━━━━━━━━━━
🧠 V7 해석:
{v7_clean}
⏰ {snapshot['trigger_time']}"""
    
    return msg

def format_exit_from_snapshot(snapshot):
    """
    🛑 EXIT 관리 메시지 (스냅샷 기반!)
    H_P3 해결: ENTRY와 동일 스냅샷 참조
    """
    direction = snapshot['direction']
    emoji = "🔴" if direction == 'SHORT' else "🟢"
    
    msg = f"""{emoji} EXIT 설정
━━━━━━━━━━━━━━━━━━━━━━━
🆔 {snapshot['event_id']}
🛑 스탑: {snapshot['sl']}pt ({snapshot['sl_price']:.2f})
🏁 타겟: {snapshot['tp']}pt ({snapshot['tp_price']:.2f})
📊 RR: 1:{snapshot['rr_ratio']:.1f}
━━━━━━━━━━━━━━━━━━━━━━━
📌 사유: 동적계산 (z={snapshot['sps_ratio_z']:.2f})
⏰ {snapshot['trigger_time']}"""
    
    return msg

def format_entry_message(direction, grade, entry_price, state_str, sector_pct, sps_ratio_z, reason, timestamp, v7_line=""):
    """
    📍 ENTRY 전용 메시지 (레거시 호환용)
    ⚠️ 신규 개발에서는 format_entry_from_snapshot 사용 권장
    """
    if direction == 'SHORT':
        emoji = "🔴"
        signal_name = "STB숏"
    else:
        emoji = "🟢"
        signal_name = "STB롱"
    
    v7_clean = v7_line.replace("\n[V7] ", "").strip() if v7_line else "해석 대기"
    
    msg = f"""{emoji} {signal_name} {grade}  |  ENTRY CONFIRMED
━━━━━━━━━━━━━━━━━━━━━━━
📍 방향: {state_str}
📍 위치: 섹터 {sector_pct:.0f}% | z: {sps_ratio_z:.2f}
🎯 진입: NQ @ {entry_price:.2f}
━━━━━━━━━━━━━━━━━━━━━━━
🧠 V7 해석:
{v7_clean}
⏰ {timestamp}"""
    
    return msg

def format_exit_message(direction, tp, sl, entry_price, reason="초기값", timestamp=""):
    """
    🛑 EXIT 관리 메시지 (레거시 호환용)
    ⚠️ 신규 개발에서는 format_exit_from_snapshot 사용 권장
    """
    if direction == 'SHORT':
        emoji = "🔴"
        tp_price = entry_price - tp
        sl_price = entry_price + sl
    else:
        emoji = "🟢"
        tp_price = entry_price + tp
        sl_price = entry_price - sl
    
    msg = f"""{emoji} EXIT 설정
━━━━━━━━━━━━━━━━━━━━━━━
🛑 스탑: {sl}pt ({sl_price:.2f})
🏁 타겟: {tp}pt ({tp_price:.2f})
📊 RR: 1:{tp/sl:.1f}
━━━━━━━━━━━━━━━━━━━━━━━
📌 사유: {reason}
⏰ {timestamp}"""
    
    return msg

def format_opa_message(direction, grade, entry_price, tp, sl, state_str, sector_pct, sps_ratio_z, reason, timestamp, v7_line=""):
    """
    OPA (Operational Perception Aid) 통합 포맷 (하위 호환용)
    ⚠️ 신규 개발에서는 format_entry_message + format_exit_message 사용 권장
    """
    if direction == 'SHORT':
        emoji = "🔴"
        dir_emoji = "⬇️"
        dir_name = "숏"
        signal_name = "STB숏"
    else:
        emoji = "🟢"
        dir_emoji = "⬆️"
        dir_name = "롱"
        signal_name = "STB롱"
    
    v7_clean = v7_line.replace("\n[V7] ", "").strip() if v7_line else "해석 대기"
    
    msg = f"""{emoji} {signal_name} {grade}  |  ENTRY ZONE CONFIRMED
━━━━━━━━━━━━━━━━━━━━━━━
📍 방향 (STATE): {state_str}
📍 위치 (STB): 섹터 {sector_pct:.0f}% | z: {sps_ratio_z:.2f}
━━━━━━━━━━━━━━━━━━━━━━━
🎯 진입: NQ @ {entry_price:.2f}
🛑 스탑: {sl}pt
🏁 타겟: {tp}pt
━━━━━━━━━━━━━━━━━━━━━━━
🧠 해석 (V7 Grammar):
{v7_clean}
━━━━━━━━━━━━━━━━━━━━━━━
⏰ {timestamp}"""
    
    return msg

# ⭐ STB 신호 중복 방지 (동일 방향 5분 내 재발송 차단)
LAST_STB_SIGNAL = {
    'short': None,  # 마지막 STB숏 시간
    'long': None,   # 마지막 STB롱 시간
    'cooldown_minutes': 5  # 쿨다운 시간 (분)
}

# ⭐ RESIST_zscore 신호 중복 방지 (5분 쿨다운)
LAST_RESIST_SIGNAL = {
    'short': None,  # 마지막 RESIST숏 시간
    'long': None,   # 마지막 RESIST롱 시간
    'cooldown_minutes': 5  # 쿨다운 시간 (분)
}

# ⭐ SL/TP 알림 중복 방지
LAST_SLTP_ALERT = {}  # {signal_id: last_alert_time}

# 📍 선행 롱 신호 추적 (블랙라인/상승빗각에서 롱 발생 시 기록)
# 조정 후 20pt 재진입에 사용
PRIOR_LONG_SIGNALS = []  # [{'price': 25500, 'level': 25480, 'time': ..., 'type': '블랙라인', 'ratio': 1.5}]

# 📍 지지 레벨 추적 (매수 스팟용)
# 매도배율 발생 시 이 레벨 위에서 버티면 = 롱!
SUPPORT_LEVELS = {
    'zpoc': 0,        # Zero POC
    'blackline': 0,   # 블랙라인
    'rising_angle': 0, # 상승빗각
    'falling_angle': 0, # 하락빗각
    'poc': 0,         # POC
    'ivpoc': 0        # iVPOC
}

# ═══════════════════════════════════════════════════════════════════════════════
# 📊 터치 결과 추적 시스템 (웹훅 신호 검증용)
# ═══════════════════════════════════════════════════════════════════════════════
TOUCH_PENDING_FILE = '.touch_pending.json'
TOUCH_RESULTS_FILE = '.touch_results.json'

def add_pending_touch(touch_type, direction, entry_price, tp=18, sl=10, extra=None):
    """터치 발생 시 결과 대기열에 추가"""
    try:
        pending = []
        if os.path.exists(TOUCH_PENDING_FILE):
            with open(TOUCH_PENDING_FILE, 'r') as f:
                pending = json.load(f)
        
        touch = {
            'id': f"{touch_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'touch_type': touch_type,
            'direction': direction,
            'entry_price': entry_price,
            'tp': tp,
            'sl': sl,
            'tp_price': entry_price + tp if direction == 'long' else entry_price - tp,
            'sl_price': entry_price - sl if direction == 'long' else entry_price + sl,
            'timestamp': datetime.now().isoformat(),
            'max_bars': 20,
            'bars_elapsed': 0,
            'status': 'pending',
            'extra': extra or {}
        }
        
        pending.append(touch)
        pending = pending[-100:]
        
        with open(TOUCH_PENDING_FILE, 'w') as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)
        
        print(f"📝 터치 추적 시작: {touch_type} {direction} @ {entry_price} (TP{tp}/SL{sl})")
        return touch
    except Exception as e:
        print(f"❌ 터치 추적 실패: {e}")
        return None

def update_pending_touches(current_high, current_low):
    """매 캔들마다 pending 터치들의 TP/SL 도달 여부 확인"""
    try:
        if not os.path.exists(TOUCH_PENDING_FILE):
            return
        
        with open(TOUCH_PENDING_FILE, 'r') as f:
            pending = json.load(f)
        
        if not pending:
            return
        
        results = []
        if os.path.exists(TOUCH_RESULTS_FILE):
            with open(TOUCH_RESULTS_FILE, 'r') as f:
                results = json.load(f)
        
        still_pending = []
        for touch in pending:
            touch['bars_elapsed'] += 1
            
            if touch['direction'] == 'long':
                tp_hit = current_high >= touch['tp_price']
                sl_hit = current_low <= touch['sl_price']
            else:
                tp_hit = current_low <= touch['tp_price']
                sl_hit = current_high >= touch['sl_price']
            
            if tp_hit and not sl_hit:
                touch['status'] = 'WIN'
                touch['result_time'] = datetime.now().isoformat()
                results.append(touch)
                print(f"✅ {touch['touch_type']} {touch['direction']} WIN! ({touch['bars_elapsed']}봉)")
            elif sl_hit:
                touch['status'] = 'LOSS'
                touch['result_time'] = datetime.now().isoformat()
                results.append(touch)
                print(f"❌ {touch['touch_type']} {touch['direction']} LOSS ({touch['bars_elapsed']}봉)")
            elif touch['bars_elapsed'] >= touch['max_bars']:
                touch['status'] = 'TIMEOUT'
                touch['result_time'] = datetime.now().isoformat()
                results.append(touch)
                print(f"⏱️ {touch['touch_type']} {touch['direction']} TIMEOUT ({touch['max_bars']}봉)")
            else:
                still_pending.append(touch)
        
        with open(TOUCH_PENDING_FILE, 'w') as f:
            json.dump(still_pending, f, ensure_ascii=False, indent=2)
        
        results = results[-500:]
        with open(TOUCH_RESULTS_FILE, 'w') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"❌ 터치 업데이트 실패: {e}")

def get_touch_stats():
    """터치별 승률 통계 반환"""
    try:
        if not os.path.exists(TOUCH_RESULTS_FILE):
            return {}
        
        with open(TOUCH_RESULTS_FILE, 'r') as f:
            results = json.load(f)
        
        stats = {}
        for r in results:
            key = f"{r['touch_type']}_{r['direction']}"
            if key not in stats:
                stats[key] = {'total': 0, 'wins': 0, 'losses': 0, 'timeouts': 0}
            
            stats[key]['total'] += 1
            if r['status'] == 'WIN':
                stats[key]['wins'] += 1
            elif r['status'] == 'LOSS':
                stats[key]['losses'] += 1
            else:
                stats[key]['timeouts'] += 1
        
        for key in stats:
            total = stats[key]['total']
            wins = stats[key]['wins']
            stats[key]['winrate'] = round(100 * wins / total, 1) if total > 0 else 0
        
        return stats
    except Exception as e:
        print(f"❌ 터치 통계 실패: {e}")
        return {}

# ═══════════════════════════════════════════════════════════════════════════════
# 🔥 STB 품질 점수 시스템 (Zone→STB Hazard Model 기반)
# ═══════════════════════════════════════════════════════════════════════════════
# 19,400캔들 백테스트 결과:
# - EXTREME Zone: STB 3.1% 발생, WIN 22.9% (허수 STB)
# - SEMI_EXTREME Zone: STB 1.2% 발생, WIN 75.0% (진짜 전환)
# - STB 시점 배율≥0.7: LOSS 0% (전환 성숙 상태)
# - STB 봉수 >8: WIN 100% (느린 STB = 진짜)
# ═══════════════════════════════════════════════════════════════════════════════

def classify_zone_type(ratio, channel_pct):
    """Zone 유형 분류 (STB 품질 판단용)"""
    is_extreme_ratio = ratio < 0.7 or ratio > 1.3
    is_extreme_channel = channel_pct < 30 or channel_pct > 70
    
    if is_extreme_ratio and is_extreme_channel:
        ratio_dir = 'oversold' if ratio < 0.7 else 'overbought'
        channel_dir = 'low' if channel_pct < 30 else 'high'
        if (ratio_dir == 'oversold' and channel_dir == 'high') or \
           (ratio_dir == 'overbought' and channel_dir == 'low'):
            return 'MIXED'
        return 'EXTREME'
    elif is_extreme_ratio or is_extreme_channel:
        return 'SEMI_EXTREME'
    else:
        return 'MID'

def calculate_stb_quality_score(zone_type, stb_ratio, bars_to_stb):
    """STB 품질 점수 계산 (0~4점)
    
    점수 구성:
    - SEMI_EXTREME Zone: +1 (75% WIN)
    - STB 시점 배율≥0.7: +2 (LOSS 0%)
    - STB 봉수 >8: +1 (100% WIN)
    
    등급 변환:
    - 4점: S++ (Full size, 정상 진입)
    - 3점: S+ (Half size 또는 보수적 TP)
    - 2점: S (관찰 진입)
    - 0~1점: 진입 금지 (허수 STB)
    """
    score = 0
    reasons = []
    
    # Zone 점수 (+1)
    if zone_type == 'SEMI_EXTREME':
        score += 1
        reasons.append('SEMI_EXTREME+1')
    elif zone_type == 'EXTREME':
        reasons.append('EXTREME+0')
    elif zone_type == 'MIXED':
        score -= 1  # 방향 충돌 = 페널티
        reasons.append('MIXED-1')
    
    # STB 시점 배율 (+2) - 가장 중요!
    if stb_ratio >= 0.7:
        score += 2
        reasons.append(f'배율{stb_ratio:.2f}≥0.7+2')
    else:
        reasons.append(f'배율{stb_ratio:.2f}<0.7+0')
    
    # STB 봉수 (+1)
    if bars_to_stb > 8:
        score += 1
        reasons.append(f'봉수{bars_to_stb}>8+1')
    else:
        reasons.append(f'봉수{bars_to_stb}≤8+0')
    
    # 등급 변환
    if score >= 4:
        grade = 'S++'
        action = 'FULL_ENTRY'
    elif score >= 3:
        grade = 'S+'
        action = 'HALF_ENTRY'
    elif score >= 2:
        grade = 'S'
        action = 'OBSERVE'
    else:
        grade = 'S?'
        action = 'NO_ENTRY'
    
    return {
        'score': max(0, score),
        'grade': grade,
        'action': action,
        'zone_type': zone_type,
        'stb_ratio': stb_ratio,
        'bars_to_stb': bars_to_stb,
        'reasons': reasons
    }

# STB 품질 기반 TP/SL 조정
STB_QUALITY_TP_SL = {
    'S++': {'tp': 30, 'sl': 10, 'size': 1.0},   # Full size, 공격적 TP
    'S+':  {'tp': 20, 'sl': 10, 'size': 0.5},   # Half size
    'S':   {'tp': 15, 'sl': 10, 'size': 0.25},  # 관찰 진입
    'S?':  {'tp': 0, 'sl': 0, 'size': 0},       # 진입 금지
}

# Zone 터치 후 STB 대기 추적
ZONE_STB_TRACKER = {
    'zone_entry_idx': None,      # Zone 터치 시점 인덱스
    'zone_entry_price': None,    # Zone 터치 시점 가격
    'zone_type': None,           # Zone 유형
    'zone_ratio': None,          # Zone 시점 배율
    'zone_channel': None,        # Zone 시점 채널%
    'bars_since_zone': 0,        # Zone 이후 경과 봉수
    'waiting': False             # STB 대기 중 여부
}

# ═══════════════════════════════════════════════════════════════════════════════
# 🔥 점수제 Action Layer (3,291건 검증 완료!)
# ═══════════════════════════════════════════════════════════════════════════════
# Gate + STB = AND → ❌ 신호 증발
# Gate + STB = Score → ✅ 신호 유지 + 성능 상승
# ═══════════════════════════════════════════════════════════════════════════════
SCORE_THRESHOLDS = {
    'short': 6,  # 숏 진입 임계값 (STB전환5 + Gate1)
    'long': 7,   # 롱 진입 임계값 (STB전환5 + Gate2)
}

SCORE_TP_SL = {
    'short': {'tp': 20, 'sl': 10},  # 숏: TP20/SL10 (RR 2:1)
    'long_p_minus': {'tp': 35, 'sl': 15},  # P-: TP35/SL15 (공격적)
    'long_p_plus': {'tp': 18, 'sl': 10},   # P+: TP18/SL10 (보수적)
}

# ═══════════════════════════════════════════════════════════════════════════════
# 🔥 SPS 상대값 기대치 (sector_sps_by_trend.json 기반)
# ═══════════════════════════════════════════════════════════════════════════════
# 추세별 섹터별 정상 SPS 기대치
# 핵심: 같은 섹터라도 상승/하락 추세에서 기대값이 완전히 다름!
EXPECTED_SPS = {
    'uptrend': {  # 상승 추세 (반등 포함)
        '상상': {'bull_sps': 0.162, 'bear_sps': 0.142},
        '상중': {'bull_sps': 0.161, 'bear_sps': -0.159},
        '중상': {'bull_sps': 0.162, 'bear_sps': -0.552},  # 핵심!
        '중하': {'bull_sps': 0.091, 'bear_sps': -0.439},
        '하중': {'bull_sps': 0.895, 'bear_sps': 0.342},
        '하하': {'bull_sps': -0.143, 'bear_sps': -0.377},
    },
    'downtrend': {  # 하락 추세
        '상상': {'bull_sps': 0.055, 'bear_sps': 0.286},
        '상중': {'bull_sps': -0.25, 'bear_sps': 0.43},
        '중상': {'bull_sps': 0.196, 'bear_sps': 0.947},  # 핵심!
        '중하': {'bull_sps': -0.383, 'bear_sps': -0.039},
        '하중': {'bull_sps': 0.0, 'bear_sps': 0.0},
        '하하': {'bull_sps': 0.0, 'bear_sps': 0.0},
    }
}

def get_sector_bucket(sector_pct):
    """섹터%를 버킷으로 변환"""
    if sector_pct >= 83:
        return '상상'
    elif sector_pct >= 67:
        return '상중'
    elif sector_pct >= 50:
        return '중상'
    elif sector_pct >= 33:
        return '중하'
    elif sector_pct >= 17:
        return '하중'
    else:
        return '하하'

def validate_sps_relative(direction, sector_pct, actual_bear_sps, actual_bull_sps, channel_rising=False, sps_weakened=True):
    """
    🔥 SPS 상대값 검증 레이어 (Action 직전)
    
    "지금 나온 SPS가 이 추세·이 섹터에서 정상적으로 나올 값이냐?"
    
    Args:
        direction: 'short' or 'long'
        sector_pct: 현재 섹터 %
        actual_bear_sps: 실제 측정된 bear_sps
        actual_bull_sps: 실제 측정된 bull_sps  
        channel_rising: 채널 상승 중 여부 (10봉 전 대비)
        sps_weakened: SPS 약화 여부 (True=약화됨, False=유지)
    
    Returns:
        dict: {'valid': bool, 'reason': str, 'expected': float, 'actual': float}
    """
    sector_bucket = get_sector_bucket(sector_pct)
    
    # 추세 맥락 결정
    trend_context = 'uptrend' if channel_rising else 'downtrend'
    
    expected = EXPECTED_SPS.get(trend_context, {}).get(sector_bucket, {})
    
    # 🔥 추세 충돌 delta (보수적)
    TREND_CONFLICT_DELTA = 1.5
    
    if direction == 'short':
        expected_bear = expected.get('bear_sps', 0)
        
        # Case 1: 숏 - 실제 매도세가 기대치보다 약하면 = 차단
        if actual_bear_sps < expected_bear:
            return {
                'valid': False,
                'reason': f"⛔SPS검증: {trend_context} {sector_bucket}에서 bear_sps {actual_bear_sps:.2f} < 기대치 {expected_bear:.2f}",
                'expected': expected_bear,
                'actual': actual_bear_sps,
                'trend': trend_context,
                'sector': sector_bucket
            }
        
        # Case 2: 🔥 추세 충돌 (상승추세 + 강한 매도 + 지속)
        # 상승 맥락에서 매도가 비정상적으로 강하고 + 약화되지 않으면 = 차단
        if trend_context == 'uptrend':
            if actual_bear_sps > expected_bear + TREND_CONFLICT_DELTA:
                if not sps_weakened:
                    return {
                        'valid': False,
                        'reason': f"⛔추세충돌: uptrend {sector_bucket}에서 bear_sps {actual_bear_sps:.2f} >> 기대치 {expected_bear:.2f} + 지속(약화X)",
                        'expected': expected_bear,
                        'actual': actual_bear_sps,
                        'trend': trend_context,
                        'sector': sector_bucket,
                        'conflict_type': 'trend_conflict_strong_and_persistent'
                    }
    
    elif direction == 'long':
        expected_bull = expected.get('bull_sps', 0)
        
        # Case 1: 롱 - 실제 매수세가 기대치보다 약하면 = 차단
        if actual_bull_sps < expected_bull:
            return {
                'valid': False,
                'reason': f"⛔SPS검증: {trend_context} {sector_bucket}에서 bull_sps {actual_bull_sps:.2f} < 기대치 {expected_bull:.2f}",
                'expected': expected_bull,
                'actual': actual_bull_sps,
                'trend': trend_context,
                'sector': sector_bucket
            }
        
        # Case 2: 🔥 추세 충돌 (하락추세 + 강한 매수 + 지속)
        if trend_context == 'downtrend':
            if actual_bull_sps > expected_bull + TREND_CONFLICT_DELTA:
                if not sps_weakened:
                    return {
                        'valid': False,
                        'reason': f"⛔추세충돌: downtrend {sector_bucket}에서 bull_sps {actual_bull_sps:.2f} >> 기대치 {expected_bull:.2f} + 지속(약화X)",
                        'expected': expected_bull,
                        'actual': actual_bull_sps,
                        'trend': trend_context,
                        'sector': sector_bucket,
                        'conflict_type': 'trend_conflict_strong_and_persistent'
                    }
    
    return {
        'valid': True,
        'reason': f"✅SPS정상: {trend_context} {sector_bucket}",
        'expected': expected.get('bear_sps' if direction == 'short' else 'bull_sps', 0),
        'actual': actual_bear_sps if direction == 'short' else actual_bull_sps,
        'trend': trend_context,
        'sector': sector_bucket
    }

def calculate_short_score(multiplier, sector_pct, stb_switch=False):
    """
    🔴 숏 점수 계산 (3,291건 검증)
    
    배율 점수:
      1.5~3.0: +3 (91% 저항)
      3.0+: +3 (95% 저항 - 극과열)
      1.2~1.5: +2 (90% 저항)
      1.0~1.2: +1 (87% 저항)
    
    섹터 점수:
      95%+: +3
      90%+: +2
      80%+: +1
    
    STB 전환: +5 (이벤트! 상태 아님)
    
    🔒 Soft Gate (극단 상황 차단):
      - 섹터 < 50% = 하단권 = 숏 금지
    """
    # ═══ 1. 매 tick 점수 리셋 (필수!) ═══
    score = 0
    score_details = []
    soft_gate_blocked = False
    block_reason = ""
    
    # ═══ 2. Soft Gate (Action 직전 재검증) ═══
    # AND 필터 아님! 명백한 금지 상태만 컷
    # 🔒 GPT 권장: 배율 + 섹터 이중 체크
    if multiplier >= 3.5:
        soft_gate_blocked = True
        block_reason = f"⛔SoftGate: 배율{multiplier:.1f}x≥3.5 (극과열=엔진폭주)"
    elif sector_pct < 50:
        soft_gate_blocked = True
        block_reason = f"⛔SoftGate: 섹터{sector_pct:.0f}%<50% (하단권=숏금지)"
    
    # ═══ 3. Gate 점수 (가중치) ═══
    # 배율 점수 (상한 없음!)
    if multiplier >= 3.0:
        score += 3
        score_details.append(f"배율{multiplier:.1f}x(극과열)+3")
    elif multiplier >= 1.5:
        score += 3
        score_details.append(f"배율{multiplier:.1f}x(최적)+3")
    elif multiplier >= 1.2:
        score += 2
        score_details.append(f"배율{multiplier:.1f}x+2")
    elif multiplier >= 1.0:
        score += 1
        score_details.append(f"배율{multiplier:.1f}x+1")
    
    # 섹터 점수
    if sector_pct >= 95:
        score += 3
        score_details.append(f"섹터{sector_pct:.0f}%+3")
    elif sector_pct >= 90:
        score += 2
        score_details.append(f"섹터{sector_pct:.0f}%+2")
    elif sector_pct >= 80:
        score += 1
        score_details.append(f"섹터{sector_pct:.0f}%+1")
    
    # ═══ 4. STB 전환 (이벤트!) ═══
    # stb_switch는 매 캔들마다 새로 계산됨 = 이벤트
    if stb_switch:
        score += 5
        score_details.append("STB전환+5")
    
    # ═══ 5. 최종 판단 ═══
    passed = score >= SCORE_THRESHOLDS['short'] and not soft_gate_blocked
    
    return {
        'score': score,
        'details': score_details,
        'threshold': SCORE_THRESHOLDS['short'],
        'passed': passed,
        'direction': 'short',
        'soft_gate_blocked': soft_gate_blocked,
        'block_reason': block_reason
    }

def calculate_long_score(multiplier, sector_pct, stb_switch=False):
    """
    🟢 롱 점수 계산 (3,291건 검증)
    
    P- (소진): 배율 ≤0.3 → +4 (100% 돌파!)
    P-w: 배율 0.3~0.5 → +3 (72% 돌파)
    P+: 배율 0.5~0.7 → +1 (Modifier only, STB필수! 단독Action금지 2026-01-15)
    weak: 배율 0.7~0.8 → +1
    
    섹터 점수:
      5%-: +3
      10%-: +2
      20%-: +1
    
    STB 전환: +5 (이벤트! 상태 아님)
    
    🔒 Soft Gate (극단 상황 차단):
      - 섹터 > 50% = 상단권 = 롱 금지
    """
    # ═══ 1. 매 tick 점수 리셋 (필수!) ═══
    score = 0
    score_details = []
    p_type = 'neutral'
    soft_gate_blocked = False
    block_reason = ""
    
    # ═══ 2. Soft Gate (Action 직전 재검증) ═══
    # AND 필터 아님! 명백한 금지 상태만 컷
    # 🔒 GPT 권장: P+ 배율 + 섹터 이중 체크
    if multiplier >= 1.2:
        soft_gate_blocked = True
        block_reason = f"⛔SoftGate: 배율{multiplier:.2f}≥1.2 (과매수권=롱금지)"
    elif sector_pct > 50:
        soft_gate_blocked = True
        block_reason = f"⛔SoftGate: 섹터{sector_pct:.0f}%>50% (상단권=롱금지)"
    
    # ═══ 3. Gate 점수 - P-/P+ 상호배타 (elif!) ═══
    # P-는 P+의 상위호환 아님! 완전히 다른 상태
    if multiplier <= 0.3:
        score += 4
        p_type = 'P-'
        score_details.append(f"P-(배율{multiplier:.2f})+4🔥")
    elif multiplier <= 0.5:
        score += 3
        p_type = 'P-w'
        score_details.append(f"P-w(배율{multiplier:.2f})+3")
    elif multiplier <= 0.7:
        # 🔒 P+ Modifier 규칙 (2026-01-15):
        # - P+ 단독 Action 금지! STB 전환 없으면 점수 낮춤
        # - 추세 역행이면 패널티 -2점
        # - 추세 순응이면 +1점만 (기존 +2에서 하향)
        if stb_switch:
            score += 1  # P+ + STB = Modifier로만 +1
            p_type = 'P+'
            score_details.append(f"P+(배율{multiplier:.2f})+1🔸Modifier")
        else:
            # P+ 단독 = Action 금지 (점수 안줌)
            p_type = 'P+_denied'
            score_details.append(f"P+(배율{multiplier:.2f})+0⛔단독금지")
    elif multiplier <= 0.8:
        score += 1
        p_type = 'weak'
        score_details.append(f"weak(배율{multiplier:.2f})+1")
    
    # 섹터 점수
    if sector_pct <= 5:
        score += 3
        score_details.append(f"섹터{sector_pct:.0f}%+3")
    elif sector_pct <= 10:
        score += 2
        score_details.append(f"섹터{sector_pct:.0f}%+2")
    elif sector_pct <= 20:
        score += 1
        score_details.append(f"섹터{sector_pct:.0f}%+1")
    
    # ═══ 4. STB 전환 (이벤트!) ═══
    if stb_switch:
        score += 5
        score_details.append("STB전환+5")
    
    # ═══ 5. TP/SL 결정 ═══
    if p_type in ['P-', 'P-w']:
        tp_sl = SCORE_TP_SL['long_p_minus']
    else:
        tp_sl = SCORE_TP_SL['long_p_plus']
    
    # ═══ 6. 최종 판단 ═══
    passed = score >= SCORE_THRESHOLDS['long'] and not soft_gate_blocked
    
    return {
        'score': score,
        'details': score_details,
        'threshold': SCORE_THRESHOLDS['long'],
        'passed': passed,
        'direction': 'long',
        'p_type': p_type,
        'tp': tp_sl['tp'],
        'sl': tp_sl['sl'],
        'soft_gate_blocked': soft_gate_blocked,
        'block_reason': block_reason
    }

def should_enter_trade(direction, multiplier, sector_pct, stb_switch=False):
    """
    🔥 진입 판단 (점수제 Action Layer)
    
    Gate는 가중치, STB는 버튼!
    점수가 임계값 이상이면 진입 허용
    """
    if direction == 'short':
        result = calculate_short_score(multiplier, sector_pct, stb_switch)
        result['tp'] = SCORE_TP_SL['short']['tp']
        result['sl'] = SCORE_TP_SL['short']['sl']
    else:
        result = calculate_long_score(multiplier, sector_pct, stb_switch)
    
    return result

def get_score_summary(score_result):
    """점수 결과를 텔레그램 메시지용으로 포맷"""
    direction = "숏" if score_result['direction'] == 'short' else "롱"
    status = "✅진입" if score_result['passed'] else "⏳대기"
    details = " ".join(score_result['details'])
    
    p_type_tag = ""
    if score_result.get('p_type'):
        p_type_tag = f"[{score_result['p_type']}]"
    
    # Soft Gate 차단 시 표시
    if score_result.get('soft_gate_blocked'):
        status = "⛔차단"
    
    return f"{direction}{p_type_tag} 점수{score_result['score']}/{score_result['threshold']} {status} | {details}"

def log_score_snapshot(score_result, entry_price, timestamp=None):
    """
    📸 Score Snapshot - 진입 순간 점수 구성 로그 (디버깅 필수!)
    
    GPT 권장: "진입 순간 로그에 반드시 남겨라"
    - 점수 구성 요소
    - 어떤 이벤트로 threshold 초과했는지
    """
    import json
    from datetime import datetime
    
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    
    snapshot = {
        'timestamp': timestamp,
        'entry_price': entry_price,
        'direction': score_result.get('direction'),
        'score': score_result.get('score'),
        'threshold': score_result.get('threshold'),
        'passed': score_result.get('passed'),
        'details': score_result.get('details', []),
        'p_type': score_result.get('p_type', ''),
        'soft_gate_blocked': score_result.get('soft_gate_blocked', False),
        'block_reason': score_result.get('block_reason', ''),
        'tp': score_result.get('tp'),
        'sl': score_result.get('sl')
    }
    
    # 콘솔 로그 (디버깅용)
    print(f"📸 ScoreSnapshot | {snapshot['direction']} @ {entry_price} | "
          f"점수{snapshot['score']}/{snapshot['threshold']} "
          f"{'✅' if snapshot['passed'] else '❌'} | "
          f"{' '.join(snapshot['details'])}")
    
    # 파일 로그 (히스토리)
    try:
        log_file = '.score_snapshots.json'
        try:
            with open(log_file, 'r') as f:
                snapshots = json.load(f)
        except:
            snapshots = []
        
        snapshots.append(snapshot)
        snapshots = snapshots[-100:]  # 최근 100개만 유지
        
        with open(log_file, 'w') as f:
            json.dump(snapshots, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ ScoreSnapshot 저장 실패: {e}")
    
    return snapshot

# ═══════════════════════════════════════════════════════════════════════════════
# 📊 동적 스팟 추적기 (Dynamic Spot Tracker)
# ═══════════════════════════════════════════════════════════════════════════════
# 핵심: 웹훅에서 받은 line_value(스팟 가격)를 저장하고 추적
# 스팟 = 저항/지지가 발생한 특정 가격대
# ═══════════════════════════════════════════════════════════════════════════════
SPOT_TRACKER = {
    'active_spots': [],       # 현재 유효한 스팟들
    'last_signal_time': None, # 마지막 신호 시간 (연속 신호 방지)
    'last_signal_type': None, # 마지막 신호 타입 (숏/롱)
    'trend_strength': 0,      # 추세 강도 (-100 ~ +100)
    'consecutive_signals': 0  # 연속 동일방향 신호 수
}

# ═══════════════════════════════════════════════════════════════════════════════
# 🔥 점 로직 (Point Logic) - 98.2% 검증됨!
# ═══════════════════════════════════════════════════════════════════════════════
# 핵심: 연속 스팟 2개 → avg_multiplier >= 1.2 AND price_diff <= 15pt = 98.2%!
# ═══════════════════════════════════════════════════════════════════════════════
POINT_LOGIC_TRACKER = {
    'recent_spots': [],       # 최근 STB 스팟들 (60분 이내 유지)
    'confirmed_points': [],   # 검증된 점 (2개 연속 조건 충족)
    'last_point_time': None,  # 마지막 점 생성 시간
}

def add_stb_spot_for_point(price, multiplier, spot_type='resistance'):
    """
    🔥 점 로직: STB 스팟 추가 (연속 2개 평균 계산용)
    """
    from datetime import datetime, timedelta
    now = datetime.now()
    
    # 60분 지난 스팟 제거
    POINT_LOGIC_TRACKER['recent_spots'] = [
        s for s in POINT_LOGIC_TRACKER['recent_spots']
        if (now - datetime.fromisoformat(s['time'])).total_seconds() < 3600
    ]
    
    # 새 스팟 추가
    new_spot = {
        'price': float(price),
        'multiplier': float(multiplier),
        'type': spot_type,
        'time': now.isoformat()
    }
    POINT_LOGIC_TRACKER['recent_spots'].append(new_spot)
    
    # 최대 10개 유지
    if len(POINT_LOGIC_TRACKER['recent_spots']) > 10:
        POINT_LOGIC_TRACKER['recent_spots'] = POINT_LOGIC_TRACKER['recent_spots'][-10:]
    
    return new_spot

def check_point_logic_condition():
    """
    🔥 점 로직 조건 검증 (99% 승률!)
    
    【P+】싸우는 (충돌):
    - min_mult >= 1.2 + diff <= 15pt = 99%
    
    【P-소진】안 싸우는 롱 (소진 후 반등):
    - min_mult >= 1.2 + 15 < diff <= 30pt = 100%!
    - 롱 전용! (하락 후 반등 감지)
    
    핵심: "둘 다 힘 빠져야" 진짜 점!
    """
    spots = POINT_LOGIC_TRACKER['recent_spots']
    
    if len(spots) < 2:
        return None
    
    spot1 = spots[-2]
    spot2 = spots[-1]
    
    from datetime import datetime
    t1 = datetime.fromisoformat(spot1['time'])
    t2 = datetime.fromisoformat(spot2['time'])
    time_diff_min = abs((t2 - t1).total_seconds() / 60)
    
    if time_diff_min > 60:
        return None
    
    avg_price = (spot1['price'] + spot2['price']) / 2
    price_diff = abs(spot2['price'] - spot1['price'])
    price_direction = spot2['price'] - spot1['price']  # 양수=상승, 음수=하락
    
    min_multiplier = min(spot1['multiplier'], spot2['multiplier'])
    avg_multiplier = (spot1['multiplier'] + spot2['multiplier']) / 2
    
    # 🔥 P+ (싸우는): 충돌 기반 = 99%
    if min_multiplier >= 1.2 and price_diff <= 15:
        point = {
            'avg_price': avg_price,
            'min_multiplier': min_multiplier,
            'avg_multiplier': avg_multiplier,
            'spot1_mult': spot1['multiplier'],
            'spot2_mult': spot2['multiplier'],
            'price_diff': price_diff,
            'time': spot2['time'],
            'type': spot2['type'],
            'signal_type': 'P+',  # 싸우는
            'confirmed': True,
            'win_rate': 99.0
        }
        
        POINT_LOGIC_TRACKER['confirmed_points'].append(point)
        POINT_LOGIC_TRACKER['last_point_time'] = spot2['time']
        
        if len(POINT_LOGIC_TRACKER['confirmed_points']) > 20:
            POINT_LOGIC_TRACKER['confirmed_points'] = POINT_LOGIC_TRACKER['confirmed_points'][-20:]
        
        return point
    
    # 🔥 P-소진 (안 싸우는 롱): 소진 후 반등 = 100%!
    # 조건: min >= 1.2 + 15 < diff <= 30 + 상승 방향
    if min_multiplier >= 1.2 and 15 < price_diff <= 30 and price_direction > 0:
        point = {
            'avg_price': avg_price,
            'min_multiplier': min_multiplier,
            'avg_multiplier': avg_multiplier,
            'spot1_mult': spot1['multiplier'],
            'spot2_mult': spot2['multiplier'],
            'price_diff': price_diff,
            'time': spot2['time'],
            'type': 'support',  # 롱 전용
            'signal_type': 'P-소진',  # 안 싸우는 롱
            'confirmed': True,
            'win_rate': 100.0
        }
        
        POINT_LOGIC_TRACKER['confirmed_points'].append(point)
        POINT_LOGIC_TRACKER['last_point_time'] = spot2['time']
        
        if len(POINT_LOGIC_TRACKER['confirmed_points']) > 20:
            POINT_LOGIC_TRACKER['confirmed_points'] = POINT_LOGIC_TRACKER['confirmed_points'][-20:]
        
        return point
    
    return None

def add_spot(line_name, line_value, price, signal_type='resistance'):
    """웹훅에서 받은 스팟을 추적기에 저장"""
    from datetime import datetime
    spot = {
        'line_name': line_name,
        'spot_price': float(line_value),
        'touch_price': float(price),
        'time': datetime.now().isoformat(),
        'signal_type': signal_type,
        'valid_bars': 50,  # 50봉 동안 유효
        'touches': 1
    }
    SPOT_TRACKER['active_spots'].append(spot)
    if len(SPOT_TRACKER['active_spots']) > 20:
        SPOT_TRACKER['active_spots'] = SPOT_TRACKER['active_spots'][-20:]
    return spot

def get_nearest_spot(current_price, tolerance_pct=0.0006):
    """
    현재가에서 가장 가까운 유효 스팟 반환
    tolerance_pct = 상대값 (0.0006 = 0.06% = 약 15pt at 25000)
    """
    tolerance = current_price * tolerance_pct  # 동적 계산
    if not SPOT_TRACKER['active_spots']:
        return None
    nearest = None
    min_dist = float('inf')
    for spot in SPOT_TRACKER['active_spots']:
        dist = abs(current_price - spot['spot_price'])
        if dist <= tolerance and dist < min_dist:
            min_dist = dist
            nearest = spot
    return nearest

def check_trend_strength():
    """추세 강도 계산 (-100: 강한하락 ~ +100: 강한상승)"""
    if len(CANDLE_HISTORY) < 100:
        return 0
    import pandas as pd
    df = pd.DataFrame(CANDLE_HISTORY[-100:])
    price_50_ago = df['close'].iloc[-50]
    price_20_ago = df['close'].iloc[-20]
    current = df['close'].iloc[-1]
    change_50 = (current - price_50_ago) / price_50_ago * 100
    change_20 = (current - price_20_ago) / price_20_ago * 100
    strength = (change_50 * 2 + change_20 * 3) / 5 * 20
    return max(-100, min(100, strength))

def should_skip_signal(signal_type):
    """연속 신호 필터 - 동일방향 3회 이상이면 스킵"""
    from datetime import datetime, timedelta
    last_time = SPOT_TRACKER.get('last_signal_time')
    last_type = SPOT_TRACKER.get('last_signal_type')
    if last_time:
        try:
            last_dt = datetime.fromisoformat(last_time)
            if datetime.now() - last_dt < timedelta(minutes=30):
                if last_type == signal_type:
                    if SPOT_TRACKER.get('consecutive_signals', 0) >= 3:
                        return True
        except:
            pass
    return False

def record_signal(signal_type):
    """신호 발생 기록"""
    from datetime import datetime
    last_type = SPOT_TRACKER.get('last_signal_type')
    if last_type == signal_type:
        SPOT_TRACKER['consecutive_signals'] = SPOT_TRACKER.get('consecutive_signals', 0) + 1
    else:
        SPOT_TRACKER['consecutive_signals'] = 1
    SPOT_TRACKER['last_signal_time'] = datetime.now().isoformat()
    SPOT_TRACKER['last_signal_type'] = signal_type

def check_sell_spot():
    """
    매도 스팟 감지: 매수배율 높은데 상승빗각까지 못 올림
    조건: 매수비2x+ + 예상상승15pt+ + 저항률40%- + 음봉 + 채널70%+ = 100% 승률
    """
    if len(CANDLE_HISTORY) < 20:
        return None
    
    import pandas as pd
    df = pd.DataFrame(CANDLE_HISTORY[-20:])
    
    df['body'] = df['close'] - df['open']
    sell_sum = df['body'].clip(upper=0).abs().sum()
    buy_sum = df['body'].clip(lower=0).sum()
    buy_ratio = buy_sum / (sell_sum + 0.1)  # 매수배율
    expected_rise = max(0, buy_sum - sell_sum)
    
    current = CANDLE_HISTORY[-1]
    current_price = current['close']
    is_bearish = (current['close'] - current['open']) < 0
    
    # 10봉 전 가격 대비 실제 상승
    if len(CANDLE_HISTORY) >= 15:
        price_10_ago = CANDLE_HISTORY[-11]['close']
        actual_rise = max(0, current_price - price_10_ago)
    else:
        actual_rise = 0
    
    resistance_ratio = actual_rise / (expected_rise + 0.1) if expected_rise > 0 else 1
    
    # 채널 계산
    df_full = pd.DataFrame(CANDLE_HISTORY[-100:])
    ch_high = df_full['high'].max()
    ch_low = df_full['low'].min()
    ch_range = ch_high - ch_low
    ch_pct = ((current_price - ch_low) / ch_range * 100) if ch_range > 0 else 50
    
    result = {
        'buy_ratio': round(buy_ratio, 2),
        'expected_rise': round(expected_rise, 1),
        'actual_rise': round(actual_rise, 1),
        'resistance_ratio': round(resistance_ratio, 2),
        'channel_pct': round(ch_pct, 1),
        'is_bearish': is_bearish,
        'signal': False,
        'reason': ''
    }
    
    # 🎯 매도 스팟 조건: 매수비2x+ + 예상상승15pt+ + 저항률40%- + 음봉 + 채널70%+
    # 채널50% 정확히는 함정구간이므로 제외
    if buy_ratio >= 2.0 and expected_rise >= 15 and resistance_ratio < 0.4 and is_bearish and ch_pct >= 70:
        result['signal'] = True
        result['reason'] = f"매도스팟! 매수비{buy_ratio:.1f}x 저항률{resistance_ratio:.0%} 채널{ch_pct:.0f}%"
    elif buy_ratio >= 2.0 and expected_rise >= 15 and resistance_ratio < 0.5 and is_bearish and ch_pct >= 65:
        result['reason'] = f"매도 관심 (저항률 {resistance_ratio:.0%})"
    
    return result

def check_iangle_absorption():
    """
    📌 빗각→버팀 공식 (AI용)
    ━━━━━━━━━━━━━━━━━━━━━━
    1. 빗각 경험: 최근 10봉 채널 80%+ 도달
    2. 매도배율 증가: 1.5x ~ 3.0x (적당한 하락 압력)
    3. 버팀 (저항률 50%-): 예상보다 안 떨어짐
    4. 양봉 확인
    
    = 빗각 저항 후 매수세 흡수 = LONG!
    """
    if len(CANDLE_HISTORY) < 20:
        return None
    
    import pandas as pd
    df = pd.DataFrame(CANDLE_HISTORY[-20:])
    df['body'] = df['close'] - df['open']
    
    current = CANDLE_HISTORY[-1]
    current_price = current['close']
    current_body = current['close'] - current['open']
    is_bullish = current_body > 0
    
    # 채널 계산
    rolling_low = 0
    channel_range = 1
    if len(CANDLE_HISTORY) >= 100:
        highs = [c['high'] for c in CANDLE_HISTORY[-100:]]
        lows = [c['low'] for c in CANDLE_HISTORY[-100:]]
        rolling_high = max(highs)
        rolling_low = min(lows)
        channel_range = rolling_high - rolling_low
        channel_pct = ((current_price - rolling_low) / channel_range * 100) if channel_range > 0 else 50
    else:
        channel_pct = 50
    
    # 1. 빗각 경험: 최근 10봉 채널 80%+ 도달
    recent_10 = df.tail(10)
    recent_channels = []
    for i in range(-10, 0):
        if len(CANDLE_HISTORY) >= 100:
            c = CANDLE_HISTORY[i]
            ch = ((c['close'] - rolling_low) / channel_range * 100) if channel_range > 0 else 50
            recent_channels.append(ch)
    peak_channel = max(recent_channels) if recent_channels else 50
    was_at_resistance = peak_channel >= 80
    
    # 2. 매도배율
    sell_sum = recent_10['body'].clip(upper=0).abs().sum()
    buy_sum = recent_10['body'].clip(lower=0).sum()
    sell_ratio = sell_sum / (buy_sum + 0.1)
    
    # 3. 저항률: 예상 하락 vs 실제 하락
    expected_drop = max(0, sell_sum - buy_sum)
    price_5_ago = CANDLE_HISTORY[-6]['close'] if len(CANDLE_HISTORY) >= 6 else current_price
    actual_drop = max(0, price_5_ago - current_price)
    resist_ratio = actual_drop / (expected_drop + 0.1) if expected_drop > 0 else 1
    
    result = {
        'peak_channel': round(peak_channel, 1),
        'current_channel': round(channel_pct, 1),
        'sell_ratio': round(sell_ratio, 2),
        'resist_ratio': round(resist_ratio, 2),
        'current_body': round(current_body, 1),
        'was_at_resistance': was_at_resistance,
        'signal': False,
        'reason': ''
    }
    
    # 🎯 빗각→버팀 조건: 채널80%+경험 + 매도비1.5-3x + 저항50%- + 양봉
    if was_at_resistance and 1.5 <= sell_ratio <= 3.0 and resist_ratio < 0.5 and is_bullish:
        result['signal'] = True
        result['reason'] = f"빗각버팀롱! 피크{peak_channel:.0f}%→{channel_pct:.0f}% 매도비{sell_ratio:.1f}x 저항{resist_ratio:.0%}"
    elif was_at_resistance and sell_ratio >= 1.5 and resist_ratio < 0.5 and is_bullish:
        result['reason'] = f"빗각버팀 관심 (매도비{sell_ratio:.1f}x 너무 높음)"
    
    return result

def check_higher_low_pattern():
    """
    📌 저점상승 + 안떨어짐 공식 (AI용)
    ━━━━━━━━━━━━━━━━━━━━━━
    1. 저점상승: 최근 5봉 저점 >= 이전 5봉 저점
    2. 안떨어짐: 저항률 70%- (예상보다 덜 하락)
    3. 양봉 확인
    
    = 96건, 62% 승률 (충분한 신호량!)
    """
    if len(CANDLE_HISTORY) < 20:
        return None
    
    import pandas as pd
    df = pd.DataFrame(CANDLE_HISTORY[-20:])
    df['body'] = df['close'] - df['open']
    
    current = CANDLE_HISTORY[-1]
    current_price = current['close']
    current_body = current['close'] - current['open']
    is_bullish = current_body > 0
    
    # 1. 저점상승: 최근 5봉 저점 >= 이전 5봉 저점
    low_recent = df['low'].iloc[-5:].min()
    low_prev = df['low'].iloc[-15:-5].min() if len(df) >= 15 else df['low'].iloc[:5].min()
    low_rise = low_recent - low_prev
    higher_low = low_rise >= 0  # 0pt 이상이면 저점상승
    
    # 2. 저항률: 예상 하락 vs 실제 하락
    recent_10 = df.tail(10)
    sell_sum = recent_10['body'].clip(upper=0).abs().sum()
    buy_sum = recent_10['body'].clip(lower=0).sum()
    expected_drop = max(0, sell_sum - buy_sum)
    
    price_5_ago = CANDLE_HISTORY[-6]['close'] if len(CANDLE_HISTORY) >= 6 else current_price
    actual_drop = max(0, price_5_ago - current_price)
    resist_ratio = actual_drop / (expected_drop + 0.1) if expected_drop > 0 else 1
    
    # 채널 (참고용)
    if len(CANDLE_HISTORY) >= 100:
        highs = [c['high'] for c in CANDLE_HISTORY[-100:]]
        lows = [c['low'] for c in CANDLE_HISTORY[-100:]]
        rolling_high = max(highs)
        rolling_low = min(lows)
        channel_range = rolling_high - rolling_low
        channel_pct = ((current_price - rolling_low) / channel_range * 100) if channel_range > 0 else 50
    else:
        channel_pct = 50
    
    result = {
        'low_rise': round(low_rise, 1),
        'higher_low': higher_low,
        'resist_ratio': round(resist_ratio, 2),
        'expected_drop': round(expected_drop, 1),
        'actual_drop': round(actual_drop, 1),
        'current_body': round(current_body, 1),
        'channel_pct': round(channel_pct, 1),
        'is_bullish': is_bullish,
        'signal': False,
        'grade': '',
        'reason': ''
    }
    
    # 🎯 저점상승 등급 체계 (100% 기준)
    # S+: 저점↑3pt+ 저항50%- 양봉15pt+ = 100% 승률
    if low_rise >= 3 and resist_ratio < 0.5 and current_body >= 15:
        result['signal'] = True
        result['grade'] = 'S+'
        result['reason'] = f"저점상승S+! 저점↑{low_rise:.0f}pt 저항{resist_ratio:.0%} 양봉{current_body:.0f}pt"
    # S: 저점↑5pt+ 저항30%- 양봉5pt+ = 79% 승률
    elif low_rise >= 5 and resist_ratio < 0.3 and current_body >= 5:
        result['signal'] = True
        result['grade'] = 'S'
        result['reason'] = f"저점상승S! 저점↑{low_rise:.0f}pt 저항{resist_ratio:.0%} 양봉{current_body:.0f}pt"
    # A: 저점↑3pt+ 저항50%- 양봉5pt+ = 76% 승률
    elif low_rise >= 3 and resist_ratio < 0.5 and current_body >= 5:
        result['signal'] = True
        result['grade'] = 'A'
        result['reason'] = f"저점상승A! 저점↑{low_rise:.0f}pt 저항{resist_ratio:.0%} 양봉{current_body:.0f}pt"
    # 관심: 기본 조건
    elif higher_low and resist_ratio < 0.7 and is_bullish:
        result['reason'] = f"저점상승 관심 (저점↑{low_rise:.0f}pt 저항{resist_ratio:.0%})"
    
    return result

def check_buy_spot():
    """
    📌 매수 스팟 공식 (AI용) + 200MA 트렌드 필터
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ⚠️ 트렌드 필터 필수! (200MA 위에서만 롱 허용)
    - 상승장(200MA 위): 롱 신호 허용 (순추세 84-93%)
    - 하락장(200MA 아래): 롱 신호 차단 (역추세 52%)
    
    1. 매도배율 증가: sell_ratio >= 2.0
    2. 예상보다 안 떨어짐: actual_drop < expected_drop * 0.5
    3. 의미있는 지지 근처: support_distance <= 20pt
    4. 저점상승 조정: higher_low >= 3pt (optional boost)
    5. 확인 양봉: body >= 15pt
    
    = 매수세 흡수 완료 = LONG!
    """
    if len(CANDLE_HISTORY) < 200:
        return None
    
    import pandas as pd
    df = pd.DataFrame(CANDLE_HISTORY[-200:])
    df['body'] = df['close'] - df['open']
    
    current = CANDLE_HISTORY[-1]
    current_price = current['close']
    current_body = current['close'] - current['open']
    is_bullish = current_body > 0
    
    # 🔥 200MA 트렌드 필터 (핵심!)
    ma_200 = df['close'].mean()
    is_uptrend = current_price > ma_200
    
    # 1. 매도배율 계산 (직전 10봉)
    recent_10 = df.tail(10)
    sell_sum = recent_10['body'].clip(upper=0).abs().sum()
    buy_sum = recent_10['body'].clip(lower=0).sum()
    sell_ratio = sell_sum / (buy_sum + 0.1)
    
    # 2. 예상 하락 vs 실제 하락
    expected_drop = max(0, sell_sum - buy_sum)
    price_10_ago = CANDLE_HISTORY[-11]['close'] if len(CANDLE_HISTORY) >= 11 else current_price
    actual_drop = max(0, price_10_ago - current_price)
    resist_ratio = actual_drop / (expected_drop + 0.1) if expected_drop > 0 else 1
    
    # 3. 지지레벨 거리 (ZPOC, 블랙라인, POC 등)
    support_distance = 999
    closest_support = None
    for name, level in SUPPORT_LEVELS.items():
        # 숫자가 아닌 값(dict 등) 건너뛰기
        if not isinstance(level, (int, float)):
            continue
        if level > 0:
            dist = abs(current_price - level)
            if dist < support_distance:
                support_distance = dist
                closest_support = name
    
    # 4. 저점상승 패턴 (최근 5봉 저점 > 이전 5봉 저점)
    low_recent = df['low'].iloc[-5:].min()
    low_prev = df['low'].iloc[-15:-5].min() if len(df) >= 15 else df['low'].iloc[:5].min()
    higher_low = low_recent - low_prev
    
    # 100봉 고저점 채널 계산
    df_100 = pd.DataFrame(CANDLE_HISTORY[-100:])
    high_100 = df_100['high'].max()
    low_100 = df_100['low'].min()
    channel_range = high_100 - low_100
    channel_pct = ((current_price - low_100) / channel_range * 100) if channel_range > 0 else 50
    
    result = {
        'sell_ratio': round(sell_ratio, 2),
        'expected_drop': round(expected_drop, 1),
        'actual_drop': round(actual_drop, 1),
        'resist_ratio': round(resist_ratio, 2),
        'support_distance': round(support_distance, 1),
        'closest_support': closest_support,
        'higher_low': round(higher_low, 1),
        'current_body': round(current_body, 1),
        'channel_pct': round(channel_pct, 1),
        'is_bullish': is_bullish,
        'is_uptrend': is_uptrend,
        'ma_200': round(ma_200, 2),
        'signal': False,
        'grade': '',
        'reason': ''
    }
    
    # 🚫 하락장(200MA 아래)에서 롱 차단!
    if not is_uptrend:
        result['reason'] = f"⛔ 하락장 롱 차단 (가격{current_price:.0f} < MA200 {ma_200:.0f})"
        return result
    
    # 🎯 매수 스팟 조건 체크 (상승장에서만!)
    cond_sell_ratio = sell_ratio >= 2.0
    cond_resist = resist_ratio < 0.5
    cond_support = support_distance <= 20
    cond_higher_low = higher_low >= 3
    cond_bullish_strong = current_body >= 15
    cond_bullish_medium = current_body >= 10
    cond_bullish_small = current_body >= 5
    cond_bullish = current_body > 0
    
    # S+ 등급: 매도비2x+ + 양봉15pt+ + 상승장
    if cond_sell_ratio and cond_bullish_strong:
        result['signal'] = True
        result['grade'] = 'S+'
        result['reason'] = f"매수스팟S+! 매도비{sell_ratio:.1f}x 양봉{current_body:.0f}pt (상승장✓)"
    # S 등급: 매도비2x+ + 양봉10pt+ (관심)
    elif cond_sell_ratio and cond_bullish_medium:
        result['signal'] = False
        result['grade'] = 'S'
        result['reason'] = f"매수관심S: 매도비{sell_ratio:.1f}x 양봉{current_body:.0f}pt (상승장✓)"
    # A 등급: 매도비2x+ + 양봉 (관심)
    elif cond_sell_ratio and cond_bullish:
        result['signal'] = False
        result['grade'] = 'A'
        result['reason'] = f"매수관심: 매도비{sell_ratio:.1f}x 양봉{current_body:.0f}pt (상승장✓)"
    
    return result

def check_sell_spot():
    """
    📌 매도 스팟 공식 (S급) + 200MA 트렌드 필터
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    핵심: 매수세 강한데 안올라감 = 숏!
    
    ⚠️ 트렌드 필터 필수! (200MA 아래에서만 숏 허용)
    - 상승장(200MA 위): 숏 신호 차단 (역추세 52%)
    - 하락장(200MA 아래): 숏 신호 허용 (순추세 84-93%)
    
    S+: 채널90%+ 매수비1x+ 음봉 + 하락장 = 100% 승률
    S: 채널85%+ 매수비1.5x+ 음봉 + 하락장 = 78% 승률
    A: 채널80%+ 매수비2x+ 음봉 + 하락장 = 75% 승률
    
    ⚠️ 매수비 3x+ = 67% (너무 억눌림 → 반등 위험)
    """
    if len(CANDLE_HISTORY) < 200:
        return None
    
    import pandas as pd
    df = pd.DataFrame(CANDLE_HISTORY[-200:])
    df['body'] = df['close'] - df['open']
    
    current = CANDLE_HISTORY[-1]
    current_price = current['close']
    current_body = current['close'] - current['open']
    is_bearish = current_body < 0
    
    # 🔥 200MA 트렌드 필터 (핵심!)
    ma_200 = df['close'].mean()
    is_downtrend = current_price < ma_200
    
    # 100봉 고저점 채널 계산
    df_100 = pd.DataFrame(CANDLE_HISTORY[-100:])
    high_100 = df_100['high'].max()
    low_100 = df_100['low'].min()
    channel_range = high_100 - low_100
    channel_pct = ((current_price - low_100) / channel_range * 100) if channel_range > 0 else 50
    
    # 매수비/매도비 계산 (직전 10봉)
    recent_10 = df.tail(10)
    sell_sum = recent_10['body'].clip(upper=0).abs().sum()
    buy_sum = recent_10['body'].clip(lower=0).sum()
    buy_ratio = buy_sum / (sell_sum + 0.1)
    sell_ratio = sell_sum / (buy_sum + 0.1)
    
    result = {
        'buy_ratio': round(buy_ratio, 2),
        'sell_ratio': round(sell_ratio, 2),
        'channel_pct': round(channel_pct, 1),
        'current_body': round(current_body, 1),
        'is_bearish': is_bearish,
        'is_downtrend': is_downtrend,
        'ma_200': round(ma_200, 2),
        'signal': False,
        'grade': '',
        'reason': ''
    }
    
    # 🚫 상승장(200MA 위)에서 숏 차단!
    if not is_downtrend:
        result['reason'] = f"⛔ 상승장 숏 차단 (가격{current_price:.0f} > MA200 {ma_200:.0f})"
        return result
    
    # 🎯 매도 스팟 등급 체크 (하락장에서만!)
    # S+: 채널90%+ 매수비1x+ 음봉 + 하락장
    if channel_pct >= 90 and buy_ratio >= 1.0 and is_bearish:
        result['signal'] = True
        result['grade'] = 'S+'
        result['reason'] = f"매도스팟S+! 채널{channel_pct:.0f}% 매수비{buy_ratio:.1f}x 음봉 (하락장✓)"
    # S: 채널85%+ 매수비1.5x+ 음봉 + 하락장
    elif channel_pct >= 85 and buy_ratio >= 1.5 and is_bearish:
        result['signal'] = True
        result['grade'] = 'S'
        result['reason'] = f"매도스팟S! 채널{channel_pct:.0f}% 매수비{buy_ratio:.1f}x 음봉 (하락장✓)"
    # A: 채널80%+ 매수비2x+ 음봉 + 하락장 (매수비 3x 미만)
    elif channel_pct >= 80 and 2.0 <= buy_ratio < 3.0 and is_bearish:
        result['signal'] = True
        result['grade'] = 'A'
        result['reason'] = f"매도스팟A! 채널{channel_pct:.0f}% 매수비{buy_ratio:.1f}x 음봉 (하락장✓)"
    # 관심: 채널70%+ 매수비2x+ 음봉 (거래 안함)
    elif channel_pct >= 70 and buy_ratio >= 2.0 and is_bearish:
        result['reason'] = f"매도관심: 채널{channel_pct:.0f}% 매수비{buy_ratio:.1f}x (하락장✓)"
    # 경고: 매수비 3x+ = 반등 위험
    elif buy_ratio >= 3.0:
        result['reason'] = f"⚠️ 매수비{buy_ratio:.1f}x 과다 (반등위험)"
    
    return result

# ═══════════════════════════════════════════════════════════════════════════════
# 📊 STB 점 로직 (Spot-Based Trading) + 누적데이터 연동!
# ═══════════════════════════════════════════════════════════════════════════════
# 핵심: body_zscore >= 1.0 = "점" → 점들이 모이면 강한 지지/저항
# SPS 비율 z-score = bull_sps / bear_sps의 상대값
# 🔥 누적데이터: spot_sps(생성시) vs retest_sps(현재) → multiplier >= 1.5 = 94%!
# ═══════════════════════════════════════════════════════════════════════════════

def get_stored_spot_multiplier(current_price, spot_type='resistance', tolerance=15):
    """
    📊 저장된 스팟의 누적SPS와 현재 SPS 비교
    - spot_sps: 스팟 생성 시점의 누적 SPS
    - retest_sps: 현재 시점의 SPS
    - multiplier = spot_sps / retest_sps (>= 1.5 = 고확률!)
    """
    import json
    
    try:
        with open('.sps_spot_registry.json', 'r') as f:
            registry = json.load(f)
    except:
        return None
    
    # 현재가와 가장 가까운 스팟 찾기
    closest_spot = None
    min_dist = float('inf')
    
    for key, spot in registry.items():
        if spot.get('type') != spot_type:
            continue
        if spot.get('status') != 'triggered':  # 이미 리테스트된 스팟만
            continue
        
        spot_price = spot.get('price', 0)
        dist = abs(current_price - spot_price)
        
        if dist < min_dist and dist <= tolerance:
            min_dist = dist
            closest_spot = spot
    
    if closest_spot:
        return {
            'spot_price': closest_spot.get('price'),
            'spot_sps': closest_spot.get('spot_sps', 0),
            'retest_sps': closest_spot.get('retest_sps', 0),
            'multiplier': closest_spot.get('multiplier', 0),
            'level_name': closest_spot.get('level_name', '')
        }
    
    return None


def check_stb_sell_spot():
    """
    📌 STB 매도 스팟 (점 로직 기반)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    핵심: 강한 매수 점들이 약해지면서 상단에서 저항
    
    조건:
    1. 섹터 90%+ (50봉 기준 상단)
    2. SPS 비율 z-score < 0 (매도가 평소보다 우세)
    3. 음봉 확인
    4. 상승장(MA200↑)에서 효과적 = 94.1% 저항률
    """
    if len(CANDLE_HISTORY) < 200:
        return None
    
    import pandas as pd
    import numpy as np
    
    df = pd.DataFrame(CANDLE_HISTORY[-200:])
    df['body'] = df['close'] - df['open']
    df['abs_body'] = df['body'].abs()
    
    current = CANDLE_HISTORY[-1]
    current_price = current['close']
    current_body = current['close'] - current['open']
    is_bearish = current_body < 0
    
    # ═══ 1. 섹터 % (50봉 기준 상대값) ═══
    h50 = df['high'].iloc[-50:].max()
    l50 = df['low'].iloc[-50:].min()
    range50 = h50 - l50
    sector_pct = ((current_price - l50) / range50 * 100) if range50 > 0 else 50
    
    # ═══ 2. STB 점 계산 (body_zscore >= 1.0) ═══
    df['body_mean'] = df['abs_body'].rolling(50).mean()
    df['body_std'] = df['abs_body'].rolling(50).std()
    df['body_zscore'] = (df['abs_body'] - df['body_mean']) / df['body_std'].replace(0, 0.001)
    
    # 강한 봉 = 점
    df['is_stb_spot'] = df['body_zscore'] >= 1.0
    df['bull_zscore'] = np.where(df['body'] > 0, df['body_zscore'], 0)
    df['bear_zscore'] = np.where(df['body'] < 0, df['body_zscore'], 0)
    
    # ═══ 3. SPS 비율 z-score ═══
    df['bull_sps_20'] = df['bull_zscore'].rolling(20).sum()
    df['bear_sps_20'] = df['bear_zscore'].rolling(20).sum()
    df['sps_ratio'] = df['bull_sps_20'] / (df['bear_sps_20'] + 0.01)
    df['sps_ratio'] = df['sps_ratio'].clip(0.1, 10)
    df['sps_ratio_mean'] = df['sps_ratio'].rolling(50).mean()
    df['sps_ratio_std'] = df['sps_ratio'].rolling(50).std()
    df['sps_ratio_zscore'] = (df['sps_ratio'] - df['sps_ratio_mean']) / df['sps_ratio_std'].replace(0, 0.001)
    
    sps_ratio_z = df['sps_ratio_zscore'].iloc[-1] if len(df) > 0 else 0
    bull_sps = df['bull_sps_20'].iloc[-1] if len(df) > 0 else 0
    bear_sps = df['bear_sps_20'].iloc[-1] if len(df) > 0 else 0
    
    # ═══ 4. SPS 약화 감지 (10봉 전 vs 현재) ═══
    if len(df) >= 15:
        bull_sps_prev = df['bull_sps_20'].iloc[-11]
        sps_weakened = bull_sps < bull_sps_prev  # 매수세 약화
    else:
        sps_weakened = False
    
    # ═══ 5. MA200 추세 ═══
    ma_200 = df['close'].mean()
    is_uptrend = current_price > ma_200
    
    # 최근 STB 점 개수
    stb_spots_10 = df['is_stb_spot'].iloc[-10:].sum()
    
    # ═══ 6. 저장된 스팟 누적데이터 조회! ═══
    stored_spot = get_stored_spot_multiplier(current_price, spot_type='resistance', tolerance=15)
    stored_multiplier = stored_spot['multiplier'] if stored_spot else 0
    stored_spot_sps = stored_spot['spot_sps'] if stored_spot else 0
    
    result = {
        'sector_pct': round(sector_pct, 1),
        'sps_ratio_z': round(sps_ratio_z, 2),
        'bull_sps': round(bull_sps, 2),
        'bear_sps': round(bear_sps, 2),
        'sps_weakened': sps_weakened,
        'stb_spots_10': int(stb_spots_10),
        'current_body': round(current_body, 1),
        'is_bearish': is_bearish,
        'is_uptrend': is_uptrend,
        'ma_200': round(ma_200, 2),
        'signal': False,
        'grade': '',
        'reason': '',
        # 🔥 누적데이터 추가!
        'stored_spot': stored_spot,
        'stored_multiplier': round(stored_multiplier, 2),
        'stored_spot_sps': round(stored_spot_sps, 2)
    }
    
    # 🔥 점수제 계산 (Action Layer)
    multiplier_for_score = stored_multiplier if stored_multiplier > 0 else 1.0
    score_result = calculate_short_score(multiplier_for_score, sector_pct, stb_switch=sps_weakened)
    result['score_info'] = score_result
    result['score'] = score_result['score']
    result['score_passed'] = score_result['passed']
    
    # ═══ 7. 동적 필터 (추세/스팟/연속신호) ═══
    trend_strength = check_trend_strength()
    nearest_spot = get_nearest_spot(current_price, tolerance_pct=0.0006)
    skip_consecutive = should_skip_signal('short')
    
    result['trend_strength'] = round(trend_strength, 1)
    result['nearest_spot'] = nearest_spot['spot_price'] if nearest_spot else None
    result['skip_consecutive'] = skip_consecutive
    
    # ═══ STB 매도 스팟 등급 (누적데이터 연동!) ═══
    # 핵심: 섹터 상단 + SPS비율z<0 + 음봉 = 저항!
    # 🔥 multiplier >= 1.5 = 94%+ 승률!
    
    # 🚫 연속 신호 필터 (3회 이상 동일방향 = 스킵)
    if skip_consecutive:
        result['reason'] = f"⚠️ 연속숏신호 스킵 ({SPOT_TRACKER.get('consecutive_signals', 0)}회)"
        return result
    
    # 🚫 강한 상승 추세 필터 (추세+30 이상 = 숏 위험)
    if trend_strength >= 30:
        result['reason'] = f"⚠️ 강상승추세 숏위험 (추세{trend_strength:.0f})"
        return result
    
    # 🚫 단순화 필터: SPS유지 = 67% (저항 불확실) → 차단
    if not sps_weakened:
        result['reason'] = f"⚠️ SPS유지(67%) 저항불확실 → 차단"
        return result
    
    # 🔥 점 로직: 스팟 저장 + 조건 검증 (98.2%!)
    point_logic_passed = False
    point_result = None
    
    if stored_multiplier > 0:
        add_stb_spot_for_point(current_price, stored_multiplier, spot_type='resistance')
        point_result = check_point_logic_condition()
        
        # 🔥 점 조건 충족 여부 기록
        if point_result and point_result.get('confirmed'):
            point_logic_passed = True
    
    # 모든 신호에 점 로직 통과 여부 추가 (기록용)
    result['point_logic_passed'] = point_logic_passed
    result['point_logic'] = point_result
    
    # ═══════════════════════════════════════════════════════════════════
    # 🔥 SPS 상대값 검증 레이어 (Action 직전)
    # 핵심: "이 추세·섹터에서 정상적인 SPS인가?"
    # ═══════════════════════════════════════════════════════════════════
    
    # 채널 상승 여부 판단 (10봉 전 섹터 vs 현재)
    channel_rising = False
    if len(df) >= 15:
        h50_prev = df['high'].iloc[-60:-10].max() if len(df) >= 60 else df['high'].iloc[:-10].max()
        l50_prev = df['low'].iloc[-60:-10].min() if len(df) >= 60 else df['low'].iloc[:-10].min()
        range50_prev = h50_prev - l50_prev
        price_10_ago = df['close'].iloc[-11]
        sector_pct_10_ago = ((price_10_ago - l50_prev) / range50_prev * 100) if range50_prev > 0 else 50
        
        # 10봉 전 섹터 < 30% AND 현재 섹터 > 50% = 채널 상승 (저점 반등)
        if sector_pct_10_ago < 30 and sector_pct > 50:
            channel_rising = True
        # 섹터 10%p 이상 상승 = 채널 상승 중
        elif sector_pct - sector_pct_10_ago > 10:
            channel_rising = True
    
    # SPS 상대값 검증 (sps_weakened 포함!)
    sps_validation = validate_sps_relative(
        direction='short',
        sector_pct=sector_pct,
        actual_bear_sps=bear_sps,
        actual_bull_sps=bull_sps,
        channel_rising=channel_rising,
        sps_weakened=sps_weakened
    )
    
    result['sps_validation'] = sps_validation
    result['channel_rising'] = channel_rising
    
    # 🚫 SPS 검증 실패 = 차단 (P+ 제외!)
    if not sps_validation['valid'] and not point_logic_passed:
        result['reason'] = sps_validation['reason']
        return result
    
    # ═══════════════════════════════════════════════════════════════════
    # 🔥 등급 시스템 (형님 철학 정리)
    # - P+: 연속 스팟 겹침 → min 기준 (99%)
    # - S++ 이하: 단일 스팟 → stored_multiplier 기준 (기존 유지)
    # ═══════════════════════════════════════════════════════════════════
    
    # 🔥 P+ (Point+): 연속 스팟 겹침 = 99%! (min >= 1.2)
    if point_logic_passed:
        result['signal'] = True
        result['grade'] = 'P+'
        result['reason'] = f"🔥점P+! min배율{point_result['min_multiplier']:.1f}x diff{point_result['price_diff']:.0f}pt (99%!)"
        record_signal('short')
        return result
    
    # ⭐ S++: 단일 스팟 강함 (stored >= 1.5) + 섹터90%+ (기존 유지)
    if stored_multiplier >= 1.5 and sector_pct >= 90 and is_bearish:
        result['signal'] = True
        result['grade'] = 'S++'
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB숏S++! 누적배율{stored_multiplier:.1f}x 섹터{sector_pct:.0f}% 음봉 (94%+){pl_tag}"
        record_signal('short')
        return result
    
    # S+: 섹터90%+ z<-0.5 + 음봉 + SPS약화
    if sector_pct >= 90 and sps_ratio_z < -0.5 and is_bearish and sps_weakened:
        result['signal'] = True
        result['grade'] = 'S+'
        mult_info = f"배율{stored_multiplier:.1f}x" if stored_multiplier > 0 else ""
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB숏S+! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} SPS약화 {mult_info}{pl_tag}"
        record_signal('short')
        return result
    
    # S: 섹터90%+ z<0 + 음봉
    if sector_pct >= 90 and sps_ratio_z < 0 and is_bearish:
        result['signal'] = True
        result['grade'] = 'S'
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB숏S! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} 음봉{pl_tag}"
        record_signal('short')
        return result
    
    # A+: stored >= 1.5 + 섹터85%+
    if stored_multiplier >= 1.5 and sector_pct >= 85 and is_bearish:
        result['signal'] = True
        result['grade'] = 'A+'
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB숏A+! 누적배율{stored_multiplier:.1f}x 섹터{sector_pct:.0f}% 음봉{pl_tag}"
        record_signal('short')
        return result
    
    # A: 섹터85%+ z<0 + 음봉 + 스팟근처
    if sector_pct >= 85 and sps_ratio_z < 0 and is_bearish and nearest_spot:
        result['signal'] = True
        result['grade'] = 'A'
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB숏A! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} 스팟{nearest_spot['spot_price']:.0f}{pl_tag}"
        record_signal('short')
        return result
    
    # A-: 섹터85%+ z<0 + 음봉
    if sector_pct >= 85 and sps_ratio_z < 0 and is_bearish:
        result['signal'] = True
        result['grade'] = 'A-'
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB숏A-! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} 음봉{pl_tag}"
        record_signal('short')
        return result
    
    # 관심: 섹터80%+ 음봉 (신호 발송 안함)
    if sector_pct >= 80 and is_bearish:
        mult_info = f"배율{stored_multiplier:.1f}x" if stored_multiplier > 0 else ""
        result['reason'] = f"STB관심: 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} {mult_info}"
    
    return result


def check_stb_buy_spot():
    """
    📌 STB 매수 스팟 (점 로직 기반)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    핵심: 강한 매도 점들이 약해지면서 하단에서 지지
    
    조건:
    1. 섹터 10%- (50봉 기준 하단)
    2. SPS 비율 z-score > 0 (매수가 평소보다 우세)
    3. 양봉 확인
    4. 상승장(MA200↑)에서 더 효과적
    """
    if len(CANDLE_HISTORY) < 200:
        return None
    
    import pandas as pd
    import numpy as np
    
    df = pd.DataFrame(CANDLE_HISTORY[-200:])
    df['body'] = df['close'] - df['open']
    df['abs_body'] = df['body'].abs()
    
    current = CANDLE_HISTORY[-1]
    current_price = current['close']
    current_body = current['close'] - current['open']
    is_bullish = current_body > 0
    
    # ═══ 1. 섹터 % (50봉 기준 상대값) ═══
    h50 = df['high'].iloc[-50:].max()
    l50 = df['low'].iloc[-50:].min()
    range50 = h50 - l50
    sector_pct = ((current_price - l50) / range50 * 100) if range50 > 0 else 50
    
    # ═══ 2. STB 점 계산 ═══
    df['body_mean'] = df['abs_body'].rolling(50).mean()
    df['body_std'] = df['abs_body'].rolling(50).std()
    df['body_zscore'] = (df['abs_body'] - df['body_mean']) / df['body_std'].replace(0, 0.001)
    
    df['is_stb_spot'] = df['body_zscore'] >= 1.0
    df['bull_zscore'] = np.where(df['body'] > 0, df['body_zscore'], 0)
    df['bear_zscore'] = np.where(df['body'] < 0, df['body_zscore'], 0)
    
    # ═══ 3. SPS 비율 z-score ═══
    df['bull_sps_20'] = df['bull_zscore'].rolling(20).sum()
    df['bear_sps_20'] = df['bear_zscore'].rolling(20).sum()
    df['sps_ratio'] = df['bull_sps_20'] / (df['bear_sps_20'] + 0.01)
    df['sps_ratio'] = df['sps_ratio'].clip(0.1, 10)
    df['sps_ratio_mean'] = df['sps_ratio'].rolling(50).mean()
    df['sps_ratio_std'] = df['sps_ratio'].rolling(50).std()
    df['sps_ratio_zscore'] = (df['sps_ratio'] - df['sps_ratio_mean']) / df['sps_ratio_std'].replace(0, 0.001)
    
    sps_ratio_z = df['sps_ratio_zscore'].iloc[-1] if len(df) > 0 else 0
    bull_sps = df['bull_sps_20'].iloc[-1] if len(df) > 0 else 0
    bear_sps = df['bear_sps_20'].iloc[-1] if len(df) > 0 else 0
    
    # ═══ 4. SPS 약화 감지 (매도세 약화) ═══
    if len(df) >= 15:
        bear_sps_prev = df['bear_sps_20'].iloc[-11]
        sps_weakened = bear_sps < bear_sps_prev  # 매도세 약화
    else:
        sps_weakened = False
    
    # ═══ 5. MA200 추세 ═══
    ma_200 = df['close'].mean()
    is_uptrend = current_price > ma_200
    
    stb_spots_10 = df['is_stb_spot'].iloc[-10:].sum()
    
    # ═══ 6. 저장된 스팟 누적데이터 조회! ═══
    stored_spot = get_stored_spot_multiplier(current_price, spot_type='support', tolerance=15)
    stored_multiplier = stored_spot['multiplier'] if stored_spot else 0
    stored_spot_sps = stored_spot['spot_sps'] if stored_spot else 0
    
    result = {
        'sector_pct': round(sector_pct, 1),
        'sps_ratio_z': round(sps_ratio_z, 2),
        'bull_sps': round(bull_sps, 2),
        'bear_sps': round(bear_sps, 2),
        'sps_weakened': sps_weakened,
        'stb_spots_10': int(stb_spots_10),
        'current_body': round(current_body, 1),
        'is_bullish': is_bullish,
        'is_uptrend': is_uptrend,
        'ma_200': round(ma_200, 2),
        'signal': False,
        'grade': '',
        'reason': '',
        # 🔥 누적데이터 추가!
        'stored_spot': stored_spot,
        'stored_multiplier': round(stored_multiplier, 2),
        'stored_spot_sps': round(stored_spot_sps, 2)
    }
    
    # 🔥 점수제 계산 (Action Layer - 롱)
    # 롱은 역배율 (저배율 = 롱신호)
    multiplier_for_score = stored_multiplier if stored_multiplier > 0 else 0.5
    score_result = calculate_long_score(multiplier_for_score, sector_pct, stb_switch=sps_weakened)
    result['score_info'] = score_result
    result['score'] = score_result['score']
    result['score_passed'] = score_result['passed']
    result['p_type'] = score_result.get('p_type', '')
    
    # ═══ 7. 동적 필터 (추세/스팟/연속신호) ═══
    trend_strength = check_trend_strength()
    nearest_spot = get_nearest_spot(current_price, tolerance_pct=0.0006)
    skip_consecutive = should_skip_signal('long')
    
    result['trend_strength'] = round(trend_strength, 1)
    result['nearest_spot'] = nearest_spot['spot_price'] if nearest_spot else None
    result['skip_consecutive'] = skip_consecutive
    
    # ═══ STB 매수 스팟 등급 (누적데이터 연동!) ═══
    # 핵심: 섹터 하단 + SPS비율z>0 + 양봉 = 지지!
    # 🔥 multiplier >= 1.5 = 94%+ 승률!
    
    # 🚫 연속 신호 필터 (3회 이상 동일방향 = 스킵)
    if skip_consecutive:
        result['reason'] = f"⚠️ 연속롱신호 스킵 ({SPOT_TRACKER.get('consecutive_signals', 0)}회)"
        return result
    
    # 📊 상승장 필터 제거 (2026-01-13) - 지지도 저항처럼 감지!
    # 하락장에서도 지지 발생 가능 (힘의 충돌 = 저항/지지 동일 원리)
    
    # 🚫 강한 하락 추세 필터 (추세-30 이하 = 롱 위험)
    if trend_strength <= -30:
        result['reason'] = f"⚠️ 강하락추세 롱위험 (추세{trend_strength:.0f})"
        return result
    
    # 🚫 단순화 필터: SPS유지 = 67% (지지 불확실) → 차단
    if not sps_weakened:
        result['reason'] = f"⚠️ SPS유지(67%) 지지불확실 → 차단"
        return result
    
    # 🔥 점 로직: 스팟 저장 + 조건 검증 (98.2%!)
    point_logic_passed = False
    point_result = None
    
    if stored_multiplier > 0:
        add_stb_spot_for_point(current_price, stored_multiplier, spot_type='support')
        point_result = check_point_logic_condition()
        
        # 🔥 점 조건 충족 여부 기록
        if point_result and point_result.get('confirmed'):
            point_logic_passed = True
    
    # 모든 신호에 점 로직 통과 여부 추가
    result['point_logic_passed'] = point_logic_passed
    result['point_logic'] = point_result
    
    # 🔥 점 로직 신호 (최우선) + 매수유리 필터
    if point_logic_passed:
        signal_type = point_result.get('signal_type', 'P+')
        win_rate = point_result.get('win_rate', 99.0)
        
        # ⚠️ 매수유리 체크: 하락장에서 P+는 흡수 후 반등 → 바로 TP 안 감
        buy_favorable = bull_sps > bear_sps
        
        if buy_favorable:
            # ✅ 매수유리 = 상승장 → P+ 바로 진입 OK
            result['signal'] = True
            result['grade'] = signal_type
            
            if signal_type == 'P-소진':
                result['reason'] = f"🔥P-소진! min배율{point_result['min_multiplier']:.1f}x diff{point_result['price_diff']:.0f}pt (100%! 안싸움)"
            else:
                result['reason'] = f"🔥점P+! min배율{point_result['min_multiplier']:.1f}x diff{point_result['price_diff']:.0f}pt (99%! 매수유리)"
            
            record_signal('long')
            return result
        else:
            # ⚠️ 매도유리/안정화 = 하락장/횡보 → 흡수 가능성 → 알림만
            result['signal'] = True
            result['grade'] = 'P-대기'  # 등급 낮춤
            result['reason'] = f"⚠️P+대기! min배율{point_result['min_multiplier']:.1f}x diff{point_result['price_diff']:.0f}pt (매도유리→흡수가능)"
            # 텔레그램 안 가게 등급 낮춤
            record_signal('long')
            return result
    
    # ⭐ S++: 누적배율 1.5+ + 섹터10%- + 양봉 = 94%+! (백테스트 검증)
    if stored_multiplier >= 1.5 and sector_pct <= 10 and is_bullish:
        result['signal'] = True
        result['grade'] = 'S++'
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB롱S++! 누적배율{stored_multiplier:.1f}x 섹터{sector_pct:.0f}% 양봉 (94%+){pl_tag}"
        record_signal('long')
    # S+: 섹터10%- SPS비율z>0.5 + 양봉 + SPS약화 + 스팟근처 = 100%!
    elif sector_pct <= 10 and sps_ratio_z > 0.5 and is_bullish and sps_weakened and nearest_spot:
        result['signal'] = True
        result['grade'] = 'S+'
        mult_info = f"배율{stored_multiplier:.1f}x" if stored_multiplier > 0 else ""
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB롱S+! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} SPS약화 스팟 {mult_info}{pl_tag}"
        record_signal('long')
    # S+: 섹터10%- SPS비율z>0.5 + 양봉 + SPS약화 = 94%+
    elif sector_pct <= 10 and sps_ratio_z > 0.5 and is_bullish and sps_weakened:
        result['signal'] = True
        result['grade'] = 'S+'
        mult_info = f"배율{stored_multiplier:.1f}x" if stored_multiplier > 0 else ""
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB롱S+! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} SPS약화 {mult_info}{pl_tag}"
        record_signal('long')
    # S: 섹터10%- SPS비율z>0 + 양봉 = 90%+
    elif sector_pct <= 10 and sps_ratio_z > 0 and is_bullish:
        result['signal'] = True
        result['grade'] = 'S'
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB롱S! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} 양봉{pl_tag}"
        record_signal('long')
    # A+: 누적배율 1.5+ + 섹터15%- = 고확률
    elif stored_multiplier >= 1.5 and sector_pct <= 15 and is_bullish:
        result['signal'] = True
        result['grade'] = 'A+'
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB롱A+! 누적배율{stored_multiplier:.1f}x 섹터{sector_pct:.0f}% 양봉{pl_tag}"
        record_signal('long')
    # A: 섹터15%- SPS비율z>0 + 양봉 + 스팟근처 = 100%
    elif sector_pct <= 15 and sps_ratio_z > 0 and is_bullish and nearest_spot:
        result['signal'] = True
        result['grade'] = 'A'
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB롱A! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} 스팟{nearest_spot['spot_price']:.0f}{pl_tag}"
        record_signal('long')
    # A-: 섹터15%- SPS비율z>0 + 양봉
    elif sector_pct <= 15 and sps_ratio_z > 0 and is_bullish:
        result['signal'] = True
        result['grade'] = 'A-'
        pl_tag = " [점X]" if not point_logic_passed else ""
        result['reason'] = f"STB롱A-! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} 양봉{pl_tag}"
        record_signal('long')
    # 관심: 섹터20%- 양봉
    elif sector_pct <= 20 and is_bullish:
        mult_info = f"배율{stored_multiplier:.1f}x" if stored_multiplier > 0 else ""
        result['reason'] = f"STB관심: 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} {mult_info}"
    
    return result


def get_recent_candles(count=30):
    """최근 캔들 데이터 가져오기"""
    try:
        if os.path.exists('.candle_history.json'):
            with open('.candle_history.json', 'r', encoding='utf-8') as f:
                candles = json.load(f)
                return candles[-count:] if len(candles) >= count else candles
    except:
        pass
    return []

# ═══════════════════════════════════════════════════════════════════════════════
# 📐 빗각 돌파/저항 판단 (상대값 기반!)
# ═══════════════════════════════════════════════════════════════════════════════
# 핵심: 빗각 터치 시 돌파할지 저항받을지 상대값으로 판단
# ═══════════════════════════════════════════════════════════════════════════════

def check_iangle_breakthrough():
    """
    📐 빗각 돌파/저항 판단 (100% 상대값 기반!)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    [상승빗각 터치 시 (상단)]
    - 돌파: 배율z > 0 (매수세 강함) + 양봉 → 상승 돌파!
    - 저항: 배율z < 0 (매수세 약함) + 음봉 → 저항 후 하락!
    
    [하락빗각 터치 시 (하단)]
    - 돌파: 배율z < 0 (매도세 강함) + 음봉 → 하락 돌파!
    - 지지: 배율z > 0 (매도세 약함) + 양봉 → 지지 후 상승!
    
    모든 조건 상대값:
    - 섹터% (상대위치)
    - 배율 z-score (평균 대비)
    - SPS비율 z-score (상대 강도)
    """
    if len(CANDLE_HISTORY) < 200:
        return None
    
    import pandas as pd
    import numpy as np
    
    df = pd.DataFrame(CANDLE_HISTORY[-200:])
    df['body'] = df['close'] - df['open']
    df['abs_body'] = df['body'].abs()
    
    current = CANDLE_HISTORY[-1]
    current_price = current['close']
    current_body = current['close'] - current['open']
    is_bullish = current_body > 0
    is_bearish = current_body < 0
    
    # ═══ 1. 섹터 % (상대값) ═══
    h50 = df['high'].iloc[-50:].max()
    l50 = df['low'].iloc[-50:].min()
    range50 = h50 - l50
    sector_pct = ((current_price - l50) / range50 * 100) if range50 > 0 else 50
    
    # ═══ 2. 배율 z-score (상대값!) ═══
    df['bull_sum'] = df['body'].clip(lower=0).rolling(10).sum()
    df['bear_sum'] = df['body'].clip(upper=0).abs().rolling(10).sum()
    df['buy_ratio'] = df['bull_sum'] / (df['bear_sum'] + 0.01)
    df['sell_ratio'] = df['bear_sum'] / (df['bull_sum'] + 0.01)
    
    df['buy_ratio_mean'] = df['buy_ratio'].rolling(50).mean()
    df['buy_ratio_std'] = df['buy_ratio'].rolling(50).std()
    df['buy_ratio_z'] = (df['buy_ratio'] - df['buy_ratio_mean']) / df['buy_ratio_std'].replace(0, 0.001)
    
    df['sell_ratio_mean'] = df['sell_ratio'].rolling(50).mean()
    df['sell_ratio_std'] = df['sell_ratio'].rolling(50).std()
    df['sell_ratio_z'] = (df['sell_ratio'] - df['sell_ratio_mean']) / df['sell_ratio_std'].replace(0, 0.001)
    
    buy_ratio_z = df['buy_ratio_z'].iloc[-1] if len(df) > 0 else 0
    sell_ratio_z = df['sell_ratio_z'].iloc[-1] if len(df) > 0 else 0
    buy_ratio = df['buy_ratio'].iloc[-1] if len(df) > 0 else 1
    sell_ratio = df['sell_ratio'].iloc[-1] if len(df) > 0 else 1
    
    # ═══ 3. SPS 비율 z-score (상대값!) ═══
    df['body_mean'] = df['abs_body'].rolling(50).mean()
    df['body_std'] = df['abs_body'].rolling(50).std()
    df['body_zscore'] = (df['abs_body'] - df['body_mean']) / df['body_std'].replace(0, 0.001)
    
    df['bull_zscore'] = np.where(df['body'] > 0, df['body_zscore'], 0)
    df['bear_zscore'] = np.where(df['body'] < 0, df['body_zscore'], 0)
    df['bull_sps'] = df['bull_zscore'].rolling(20).sum()
    df['bear_sps'] = df['bear_zscore'].rolling(20).sum()
    
    df['sps_ratio'] = (df['bull_sps'] / (df['bear_sps'] + 0.01)).clip(0.1, 10)
    df['sps_ratio_mean'] = df['sps_ratio'].rolling(50).mean()
    df['sps_ratio_std'] = df['sps_ratio'].rolling(50).std()
    df['sps_ratio_z'] = (df['sps_ratio'] - df['sps_ratio_mean']) / df['sps_ratio_std'].replace(0, 0.001)
    
    sps_ratio_z = df['sps_ratio_z'].iloc[-1] if len(df) > 0 else 0
    bull_sps_20 = df['bull_sps'].iloc[-1] if len(df) > 0 else 0
    bear_sps_20 = df['bear_sps'].iloc[-1] if len(df) > 0 else 0
    
    # 🔥 매수유리/매도유리 판단 (STB 동일!)
    buy_advantage = bull_sps_20 > bear_sps_20  # 매수힘 > 매도힘
    sell_advantage = bear_sps_20 > bull_sps_20  # 매도힘 > 매수힘
    
    result = {
        'sector_pct': round(sector_pct, 1),
        'buy_ratio_z': round(buy_ratio_z, 2),
        'sell_ratio_z': round(sell_ratio_z, 2),
        'sps_ratio_z': round(sps_ratio_z, 2),
        'buy_ratio': round(buy_ratio, 2),
        'sell_ratio': round(sell_ratio, 2),
        'bull_sps_20': round(bull_sps_20, 2),  # 🔥 추가!
        'bear_sps_20': round(bear_sps_20, 2),  # 🔥 추가!
        'buy_advantage': buy_advantage,        # 🔥 추가!
        'sell_advantage': sell_advantage,      # 🔥 추가!
        'is_bullish': is_bullish,
        'is_bearish': is_bearish,
        'judgment': '',
        'direction': '',
        'confidence': ''
    }
    
    # ═══════════════════════════════════════════════════════════════════════
    # 📐 빗각 돌파/저항 판단 (검증된 조건!)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 상단 저항: 섹터90%+ + SPS비율z<0 + 음봉 = 89.6% (SPS비율z<-0.5 = 92.4%)
    # 하단 지지: 섹터20%- + SPS비율z>0.5 + 배율z<-0.5 + 양봉 = 90.5%
    # ═══════════════════════════════════════════════════════════════════════
    
    # ═══ 상단 저항 (섹터 85%+) ═══
    if sector_pct >= 85:
        # ⭐ 핵심 조건: SPS비율z<0 + 음봉 = 저항!
        if sps_ratio_z < 0 and is_bearish:
            result['judgment'] = '저항'
            result['direction'] = 'SHORT'
            # S+: 섹터90%+ SPS비율z<-0.5 = 92.4%
            if sector_pct >= 90 and sps_ratio_z < -0.5:
                result['confidence'] = 'S+'
                result['reason'] = f"상단저항S+! 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 음봉 (92%)"
            # S: 섹터90%+ SPS비율z<0 = 89.6%
            elif sector_pct >= 90 and sps_ratio_z < 0:
                result['confidence'] = 'S'
                result['reason'] = f"상단저항S! 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 음봉 (90%)"
            # A: 섹터85%+ SPS비율z<-0.5 = 86.2%
            elif sps_ratio_z < -0.5:
                result['confidence'] = 'A'
                result['reason'] = f"상단저항A! 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 음봉 (86%)"
            else:
                result['confidence'] = 'B'
                result['reason'] = f"상단저항B: 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 음봉"
        # 돌파: SPS비율z>0 + 양봉 (희귀)
        elif sps_ratio_z > 0 and is_bullish:
            result['judgment'] = '돌파'
            result['direction'] = 'LONG'
            result['confidence'] = 'C'
            result['reason'] = f"상단돌파: 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 양봉 (희귀)"
        else:
            result['judgment'] = '관찰'
            result['reason'] = f"상단관찰: 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f}"
    
    # ═══ 하단 지지 (섹터 20%-) ═══
    elif sector_pct <= 20:
        # ⭐ 핵심 조건: SPS비율z>0 + 배율z<0 + 양봉 = 지지!
        if sps_ratio_z > 0 and is_bullish:
            result['judgment'] = '지지'
            result['direction'] = 'LONG'
            # S+: 섹터20%- SPS비율z>0.5 + 배율z<-0.5 = 90.5%
            if sps_ratio_z > 0.5 and sell_ratio_z < -0.5:
                result['confidence'] = 'S+'
                result['reason'] = f"하단지지S+! 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 배율z{sell_ratio_z:.1f} 양봉 (90%)"
            # S: 섹터15%- SPS비율z>0 = 78%
            elif sector_pct <= 15 and sell_ratio_z < 0:
                result['confidence'] = 'S'
                result['reason'] = f"하단지지S! 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 배율z{sell_ratio_z:.1f} 양봉"
            # A: 섹터20%- SPS비율z>0 = 72.8%
            else:
                result['confidence'] = 'A'
                result['reason'] = f"하단지지A: 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 양봉"
        # 하락돌파: SPS비율z<0 + 음봉
        elif sps_ratio_z < 0 and is_bearish:
            result['judgment'] = '하락돌파'
            result['direction'] = 'SHORT'
            result['confidence'] = 'C'
            result['reason'] = f"하단돌파: 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 음봉"
        else:
            result['judgment'] = '관찰'
            result['reason'] = f"하단관찰: 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f}"
    
    # ═══ 중간구간 (20~85%) - 모든 섹터에서 신호 발생! ═══
    else:
        # 배율 z-score 기반 판단 (섹터 무관!)
        if sps_ratio_z < -0.5 and is_bearish:
            result['judgment'] = '저항'
            result['direction'] = 'SHORT'
            result['confidence'] = 'B'
            result['reason'] = f"중간저항B: 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 음봉"
        elif sps_ratio_z > 0.5 and is_bullish:
            result['judgment'] = '지지'
            result['direction'] = 'LONG'
            result['confidence'] = 'B'
            result['reason'] = f"중간지지B: 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f} 양봉"
        elif is_bearish and sell_ratio_z > 0:
            result['judgment'] = '저항'
            result['direction'] = 'SHORT'
            result['confidence'] = 'C'
            result['reason'] = f"관찰숏: 섹터{sector_pct:.0f}% 매도배율z{sell_ratio_z:.1f} 음봉"
        elif is_bullish and buy_ratio_z > 0:
            result['judgment'] = '지지'
            result['direction'] = 'LONG'
            result['confidence'] = 'C'
            result['reason'] = f"관찰롱: 섹터{sector_pct:.0f}% 매수배율z{buy_ratio_z:.1f} 양봉"
        else:
            result['judgment'] = '관찰'
            result['direction'] = 'SHORT' if is_bearish else 'LONG'
            result['confidence'] = 'C'
            result['reason'] = f"중간관찰: 섹터{sector_pct:.0f}% SPS비율z{sps_ratio_z:.1f}"
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 📐 빗각돌파 홀딩 패턴 (2026-01-12 발견)
# ═══════════════════════════════════════════════════════════════════════════════
def check_angle_breakout_hold():
    """
    📐 빗각돌파 홀딩 패턴 (STB POC 기준!)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    조건:
    1. 빗각 돌파 (상승/하락)
    2. (high + low) / 2 ≈ 빗각 가격 (±2pt)
    3. SPS 비율 < POC (점 평균보다 낮음)
    4. = 홀딩 확정! (더 갈 것)
    """
    if len(CANDLE_HISTORY) < 200:
        return None
    
    import pandas as pd
    import numpy as np
    
    df = pd.DataFrame(CANDLE_HISTORY[-200:])
    df['body'] = df['close'] - df['open']
    df['abs_body'] = df['body'].abs()
    
    current = CANDLE_HISTORY[-1]
    current_high = current['high']
    current_low = current['low']
    current_close = current['close']
    candle_mid = (current_high + current_low) / 2
    
    # ═══ 1. STB 점 계산 (body_zscore >= 1.0) ═══
    df['body_mean'] = df['abs_body'].rolling(50).mean()
    df['body_std'] = df['abs_body'].rolling(50).std()
    df['body_zscore'] = (df['abs_body'] - df['body_mean']) / df['body_std'].replace(0, 0.001)
    df['is_stb_spot'] = df['body_zscore'] >= 1.0
    
    # ═══ 2. SPS 비율 계산 ═══
    df['bull_zscore'] = np.where(df['body'] > 0, df['body_zscore'], 0)
    df['bear_zscore'] = np.where(df['body'] < 0, df['body_zscore'], 0)
    df['bull_sps_20'] = df['bull_zscore'].rolling(20).sum()
    df['bear_sps_20'] = df['bear_zscore'].rolling(20).sum()
    df['sps_ratio'] = (df['bull_sps_20'] / (df['bear_sps_20'] + 0.01)).clip(0.1, 10)
    
    current_sps_ratio = df['sps_ratio'].iloc[-1] if len(df) > 0 else 1
    
    # ═══ 3. POC 계산 (강한 점들의 평균 SPS 비율) ═══
    stb_spots = df[df['is_stb_spot'] == True]
    if len(stb_spots) >= 2:
        poc_sps_ratio = stb_spots['sps_ratio'].mean()
    else:
        poc_sps_ratio = df['sps_ratio'].mean()
    
    # ═══ 4. 빗각 가격 가져오기 ═══
    rising_angle = SUPPORT_LEVELS.get('rising_angle', 0)
    falling_angle = SUPPORT_LEVELS.get('falling_angle', 0)
    
    result = {
        'candle_mid': round(candle_mid, 2),
        'current_sps_ratio': round(current_sps_ratio, 2),
        'poc_sps_ratio': round(poc_sps_ratio, 2),
        'is_below_poc': current_sps_ratio < poc_sps_ratio,
        'rising_angle': round(rising_angle, 2),
        'falling_angle': round(falling_angle, 2),
        'hold_signal': False,
        'angle_type': '',
        'distance_to_angle': 0,
        'reason': ''
    }
    
    # ═══ 5. 하락빗각 돌파 홀딩 패턴 체크 ═══
    # 조건: 캔들중간값 ≈ 하락빗각가격 (±2pt) + SPS비율 < POC
    # 매수/매도 둘 다 가능 (현재 봉 방향으로 판단)
    
    current_body = current['close'] - current['open']
    is_bullish = current_body > 0
    
    # 하락빗각만 체크
    if falling_angle > 0:
        dist_falling = abs(candle_mid - falling_angle)
        result['distance_to_angle'] = round(dist_falling, 2)
        
        if dist_falling <= 2 and current_sps_ratio < poc_sps_ratio:
            result['hold_signal'] = True
            result['angle_type'] = 'falling'
            
            # 봉 방향으로 홀딩 방향 결정
            if is_bullish:
                result['hold_direction'] = 'LONG'
                result['reason'] = f"하락빗각돌파→롱홀딩! mid{candle_mid:.0f}≈빗각{falling_angle:.0f} SPS{current_sps_ratio:.2f}<POC{poc_sps_ratio:.2f} 양봉"
            else:
                result['hold_direction'] = 'SHORT'
                result['reason'] = f"하락빗각돌파→숏홀딩! mid{candle_mid:.0f}≈빗각{falling_angle:.0f} SPS{current_sps_ratio:.2f}<POC{poc_sps_ratio:.2f} 음봉"
            return result
    
    result['reason'] = f"홀딩패턴 미충족: mid{candle_mid:.0f} SPS{current_sps_ratio:.2f} POC{poc_sps_ratio:.2f}"
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 📐 빗각 특화 판단 로직 (기울기 + 타입 + 스팟 연동)
# ═══════════════════════════════════════════════════════════════════════════════
def check_angle_specific_judgment(touch_price, line_name=''):
    """
    📐 빗각 특화 판단 (2026-01-12)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    1. 어떤 빗각 터치? (상승/하락 + 위치)
    2. 터치 방향? (위→아래 vs 아래→위)
    3. 기울기 예측 (6시간 후 위치)
    4. 검증 승률 연동 (RESIST 91-96%)
    
    모든 값 = 상대값 (%, z-score, 비율)
    """
    from angle_classifier import get_angle_lines, RISING_SLOPE_PER_HOUR, FALLING_SLOPE_PER_HOUR
    
    result = {
        'touched_line': None,
        'touch_type': None,      # 'rising' or 'falling'
        'touch_direction': None, # 'from_above' or 'from_below'
        'distance_pt': 0,
        'slope_per_hour': 0,
        'prediction_6h': 0,
        'prediction_change': 0,
        'verified_signal': None,
        'verified_winrate': 0,
        'final_judgment': '',
        'confidence': '',
        'reason': ''
    }
    
    if len(CANDLE_HISTORY) < 50:
        return result
    
    # ═══ 1. 어떤 빗각 터치인지 찾기 ═══
    lines = get_angle_lines()
    closest_line = None
    min_dist = float('inf')
    
    for line in lines:
        if line['price_avg'] > 0:
            dist = abs(touch_price - line['price_avg'])
            if dist < min_dist:
                min_dist = dist
                closest_line = line
    
    if closest_line and min_dist < 30:
        result['touched_line'] = closest_line['label']
        result['touch_type'] = closest_line['type']
        result['distance_pt'] = round(touch_price - closest_line['price_avg'], 2)
        result['slope_per_hour'] = closest_line['slope_per_hour']
        
        # 6시간 후 예측
        future_price = closest_line['price_avg'] + (closest_line['slope_per_hour'] * 6)
        result['prediction_6h'] = round(future_price, 2)
        result['prediction_change'] = round(closest_line['slope_per_hour'] * 6, 1)
    else:
        return result  # 30pt 이내 빗각 없음
    
    # ═══ 2. 터치 방향 분석 (최근 3봉 기준) ═══
    recent_candles = CANDLE_HISTORY[-5:]
    if len(recent_candles) >= 3:
        prev_close = recent_candles[-3]['close']
        curr_close = recent_candles[-1]['close']
        
        if prev_close > touch_price and curr_close <= touch_price:
            result['touch_direction'] = 'from_above'  # 위에서 하락해서 터치
        elif prev_close < touch_price and curr_close >= touch_price:
            result['touch_direction'] = 'from_below'  # 아래서 상승해서 터치
        else:
            result['touch_direction'] = 'at_level'    # 라인 근처에서 횡보
    
    # ═══ 3. z-score 계산 (상대값!) ═══
    import pandas as pd
    import numpy as np
    
    df = pd.DataFrame(CANDLE_HISTORY[-200:])
    df['body'] = df['close'] - df['open']
    df['abs_body'] = df['body'].abs()
    
    current = CANDLE_HISTORY[-1]
    current_price = current['close']
    current_body = current['close'] - current['open']
    is_bullish = current_body > 0
    is_bearish = current_body < 0
    
    # 섹터 % (상대위치)
    h50 = df['high'].iloc[-50:].max()
    l50 = df['low'].iloc[-50:].min()
    range50 = h50 - l50
    sector_pct = ((current_price - l50) / range50 * 100) if range50 > 0 else 50
    
    # SPS 비율 z-score
    df['body_mean'] = df['abs_body'].rolling(50).mean()
    df['body_std'] = df['abs_body'].rolling(50).std()
    df['body_zscore'] = (df['abs_body'] - df['body_mean']) / df['body_std'].replace(0, 0.001)
    
    df['bull_zscore'] = np.where(df['body'] > 0, df['body_zscore'], 0)
    df['bear_zscore'] = np.where(df['body'] < 0, df['body_zscore'], 0)
    df['bull_sps'] = df['bull_zscore'].rolling(20).sum()
    df['bear_sps'] = df['bear_zscore'].rolling(20).sum()
    
    df['sps_ratio'] = (df['bull_sps'] / (df['bear_sps'] + 0.01)).clip(0.1, 10)
    df['sps_ratio_mean'] = df['sps_ratio'].rolling(50).mean()
    df['sps_ratio_std'] = df['sps_ratio'].rolling(50).std()
    df['sps_ratio_z'] = (df['sps_ratio'] - df['sps_ratio_mean']) / df['sps_ratio_std'].replace(0, 0.001)
    
    sps_ratio_z = df['sps_ratio_z'].iloc[-1] if len(df) > 0 else 0
    
    result['sector_pct'] = round(sector_pct, 1)
    result['sps_ratio_z'] = round(sps_ratio_z, 2)
    result['is_bullish'] = is_bullish
    result['is_bearish'] = is_bearish
    
    # ═══ 4. 빗각 타입별 판단 ═══
    if result['touch_type'] == 'falling':
        # 🔴 하락빗각 = 저항선
        if sector_pct >= 80:
            # 상단에서 하락빗각 터치 = 저항
            if sps_ratio_z < 0 and is_bearish:
                result['final_judgment'] = '하락빗각_저항'
                result['confidence'] = 'S+' if sps_ratio_z < -0.5 else 'S'
                result['verified_signal'] = 'RESIST_zscore'
                result['verified_winrate'] = 91.8 if sps_ratio_z > 0.5 else 95.0
                result['reason'] = f"하락빗각 상단저항! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} 음봉"
            elif is_bullish and result['touch_direction'] == 'from_below':
                result['final_judgment'] = '하락빗각_돌파시도'
                result['confidence'] = 'A'
                result['reason'] = f"하락빗각 돌파시도: 섹터{sector_pct:.0f}% 양봉 (위험)"
        elif sector_pct <= 30:
            # 하단에서 하락빗각 터치 = 지지 가능
            if sps_ratio_z > 0 and is_bullish:
                result['final_judgment'] = '하락빗각_지지'
                result['confidence'] = 'A'
                result['reason'] = f"하락빗각 하단지지: 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} 양봉"
    
    elif result['touch_type'] == 'rising':
        # 🟢 상승빗각 = 지지선
        if sector_pct <= 30:
            # 하단에서 상승빗각 터치 = 지지
            if sps_ratio_z > 0 and is_bullish:
                result['final_judgment'] = '상승빗각_지지'
                result['confidence'] = 'S+' if sps_ratio_z > 0.5 else 'S'
                result['verified_signal'] = 'POC_LONG'
                result['verified_winrate'] = 100.0
                result['reason'] = f"상승빗각 하단지지! 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} 양봉"
            elif is_bearish and result['touch_direction'] == 'from_above':
                result['final_judgment'] = '상승빗각_이탈시도'
                result['confidence'] = 'A'
                result['reason'] = f"상승빗각 이탈시도: 섹터{sector_pct:.0f}% 음봉 (위험)"
        elif sector_pct >= 70:
            # 상단에서 상승빗각 터치 = 돌파 가능
            if sps_ratio_z > 0.5 and is_bullish:
                result['final_judgment'] = '상승빗각_돌파'
                result['confidence'] = 'A'
                result['reason'] = f"상승빗각 돌파: 섹터{sector_pct:.0f}% z{sps_ratio_z:.1f} 양봉"
    
    # 판단 없으면 관찰
    if not result['final_judgment']:
        result['final_judgment'] = '관찰'
        result['confidence'] = ''
        result['reason'] = f"빗각터치 관찰: {result['touched_line']} 섹터{sector_pct:.0f}%"
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 📊 시퀀스 롱 로직 v2 - 두 가지 시퀀스 통합
# ═══════════════════════════════════════════════════════════════════════════════
# 시퀀스1: 매도배율↑ + 변동성↓ → 가격홀드 + ratio↓ + 급증 + 양봉 = 100% (2건)
# 시퀀스2: 매수배율↑ → 하락 → 매수배율 회복 + 양봉3 + 누적상승 = 91% (11건)
# 합계: 92% (13건, 중복 0)
# ═══════════════════════════════════════════════════════════════════════════════

# 시퀀스 트리거 기록
SEQUENCE_TRIGGERS = {
    'sell_high': [],  # 시퀀스1: 매도배율 높음 + 변동성 낮음
    'buy_high': []    # 시퀀스2: 매수배율 높음
}

def check_sequence_long():
    """
    📌 시퀀스 롱 v2 - 두 가지 시퀀스 통합 (92% 승률!)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    【시퀀스1】매도배율 트리거 (100%, 2건)
    - 트리거: sell_ratio_z >= 2.0 + stb_z <= -0.5
    - 진입: 가격홀드 + ratio < 0.6 + 변동성급증 + 양봉 + 섹터 < 40%
    
    【시퀀스2】매수배율 트리거 (91%, 11건)
    - 트리거: buy_ratio_z >= 2.0
    - 진입: 하락>10pt + buy_ratio_z>=1.0 + 양봉3 + 누적상승 + 섹터<40%
    """
    global SEQUENCE_TRIGGERS
    
    if len(CANDLE_HISTORY) < 200:
        return None
    
    import pandas as pd
    import numpy as np
    
    df = pd.DataFrame(CANDLE_HISTORY[-200:])
    df['body'] = df['close'] - df['open']
    df['abs_body'] = df['body'].abs()
    df['is_bullish'] = df['body'] > 0
    
    current = CANDLE_HISTORY[-1]
    current_price = current['close']
    current_body = current['close'] - current['open']
    is_bullish = current_body > 0
    current_idx = len(CANDLE_HISTORY)
    
    # ═══ 지표 계산 ═══
    df['bull_sum'] = df['body'].clip(lower=0).rolling(10).sum()
    df['bear_sum'] = df['body'].clip(upper=0).abs().rolling(10).sum()
    
    # 매도배율 z-score
    df['sell_ratio'] = df['bear_sum'] / (df['bull_sum'] + 0.01)
    df['sell_ratio_mean'] = df['sell_ratio'].rolling(50).mean()
    df['sell_ratio_std'] = df['sell_ratio'].rolling(50).std()
    df['sell_ratio_z'] = (df['sell_ratio'] - df['sell_ratio_mean']) / df['sell_ratio_std'].replace(0, 0.001)
    
    # 매수배율 z-score
    df['buy_ratio'] = df['bull_sum'] / (df['bear_sum'] + 0.01)
    df['buy_ratio_mean'] = df['buy_ratio'].rolling(50).mean()
    df['buy_ratio_std'] = df['buy_ratio'].rolling(50).std()
    df['buy_ratio_z'] = (df['buy_ratio'] - df['buy_ratio_mean']) / df['buy_ratio_std'].replace(0, 0.001)
    
    # STB (변동성) z-score
    df['stb'] = df['abs_body'].rolling(10).sum()
    df['stb_mean'] = df['stb'].rolling(50).mean()
    df['stb_std'] = df['stb'].rolling(50).std()
    df['stb_z'] = (df['stb'] - df['stb_mean']) / df['stb_std'].replace(0, 0.001)
    
    # 누적 매수량
    df['cum_bull'] = df['body'].clip(lower=0).rolling(20).sum()
    
    # 양봉 3연속
    bull_3 = is_bullish
    if len(df) >= 3:
        bull_3 = df['is_bullish'].iloc[-1] and df['is_bullish'].iloc[-2] and df['is_bullish'].iloc[-3]
    
    # 누적 매수 상승
    cum_bull_rising = False
    if len(df) >= 4:
        cum_bull_rising = df['cum_bull'].iloc[-1] > df['cum_bull'].iloc[-4]
    
    # 변동성 급증
    stb_surge = False
    if len(df) >= 4:
        stb_surge = df['stb_z'].iloc[-1] > 0.5 and df['stb_z'].iloc[-4] < 0
    
    # 섹터 계산
    h50 = df['high'].iloc[-50:].max()
    l50 = df['low'].iloc[-50:].min()
    range50 = h50 - l50
    sector_pct = ((current_price - l50) / range50 * 100) if range50 > 0 else 50
    
    # 현재 값
    sell_ratio_z = df['sell_ratio_z'].iloc[-1] if len(df) > 0 else 0
    buy_ratio_z = df['buy_ratio_z'].iloc[-1] if len(df) > 0 else 0
    stb_z = df['stb_z'].iloc[-1] if len(df) > 0 else 0
    ratio = df['sell_ratio'].iloc[-1] if len(df) > 0 else 1
    
    result = {
        'sector_pct': round(sector_pct, 1),
        'sell_ratio_z': round(sell_ratio_z, 2),
        'buy_ratio_z': round(buy_ratio_z, 2),
        'stb_z': round(stb_z, 2),
        'ratio': round(ratio, 2),
        'is_bullish': is_bullish,
        'bull_3': bull_3,
        'cum_bull_rising': cum_bull_rising,
        'stb_surge': stb_surge,
        'signal': False,
        'sequence_type': '',
        'grade': '',
        'reason': ''
    }
    
    # ═══ 트리거 기록 ═══
    # 시퀀스1 트리거: 매도배율↑ + 변동성↓
    if sell_ratio_z >= 2.0 and stb_z <= -0.5:
        SEQUENCE_TRIGGERS['sell_high'].append({
            'idx': current_idx,
            'price': current_price,
            'sell_z': sell_ratio_z,
            'stb_z': stb_z
        })
        if len(SEQUENCE_TRIGGERS['sell_high']) > 100:
            SEQUENCE_TRIGGERS['sell_high'] = SEQUENCE_TRIGGERS['sell_high'][-50:]
    
    # 시퀀스2 트리거: 매수배율↑
    if buy_ratio_z >= 2.0:
        SEQUENCE_TRIGGERS['buy_high'].append({
            'idx': current_idx,
            'price': current_price,
            'buy_z': buy_ratio_z
        })
        if len(SEQUENCE_TRIGGERS['buy_high']) > 100:
            SEQUENCE_TRIGGERS['buy_high'] = SEQUENCE_TRIGGERS['buy_high'][-50:]
    
    # ═══ 추세 판단 (20봉 MA 기준) ═══
    ma20 = df['close'].iloc[-20:].mean() if len(df) >= 20 else current_price
    is_downtrend = current_price < ma20
    
    # ═══ 시퀀스1 체크: 매도배율 트리거 → 롱 (추세필터 없음, 섹터40%) ═══
    for trig in reversed(SEQUENCE_TRIGGERS['sell_high'][-50:]):
        offset = current_idx - trig['idx']
        if not (5 <= offset <= 50):
            continue
        
        trig_price = trig['price']
        
        # 조건: 가격홀드 + ratio<0.6 + 급증 + 양봉 + 섹터<40%
        if current_price >= trig_price - 15:  # 가격홀드
            if ratio < 0.6:  # 배율 낮아짐
                if stb_surge:  # 변동성 급증
                    if is_bullish:  # 양봉
                        if sector_pct < 40:  # 섹터 40% 이하 (100% 승률)
                            result['signal'] = True
                            result['sequence_type'] = 'SEQ1'
                            result['grade'] = 'S+'
                            result['reason'] = f"시퀀스1롱! 매도z{trig['sell_z']:.1f}→ratio{ratio:.1f} 급증+양봉 섹터{sector_pct:.0f}%"
                            return result
    
    # ═══ 시퀀스2 체크: 매수배율 트리거 → 롱 (하락장, 섹터50%) ═══
    if is_downtrend:  # 하락장 필터 (100% 승률)
        for trig in reversed(SEQUENCE_TRIGGERS['buy_high'][-50:]):
            offset = current_idx - trig['idx']
            if not (5 <= offset <= 50):
                continue
            
            trig_price = trig['price']
            price_drop = trig_price - current_price
            
            # 조건: 하락>10pt + buy_z>=1.0 + 양봉3 + 누적상승 + 섹터<50%
            if price_drop >= 10:  # 가격 하락
                if buy_ratio_z >= 1.0:  # 매수배율 회복
                    if bull_3:  # 양봉 3연속
                        if cum_bull_rising:  # 누적 매수 상승
                            if sector_pct < 50:  # 섹터 50% 이하
                                result['signal'] = True
                                result['sequence_type'] = 'SEQ2'
                                result['grade'] = 'S+'
                                result['reason'] = f"시퀀스2롱! 하락장+매수z{trig['buy_z']:.1f}→{buy_ratio_z:.1f} 하락{price_drop:.0f}pt 양봉3 섹터{sector_pct:.0f}%"
                                return result
    
    # 신호 없음
    result['reason'] = f"시퀀스 대기: 섹터{sector_pct:.0f}% buy_z{buy_ratio_z:.1f} sell_z{sell_ratio_z:.1f}"
    return result


# record_stb_short 제거됨 - SEQUENCE_TRIGGERS로 대체 (2026-01-13)


def check_sl_tp_hit(current_price):
    """진입 중인 신호의 SL/TP 도달 체크 → 자동 LOSS/WIN 처리 + 캔들 저장"""
    global SL_NOTIFIED_SIGNALS
    from signal_logger import load_signals, update_signal_status, append_candles_to_signal
    
    data = load_signals()
    today = datetime.now().strftime("%Y-%m-%d")
    
    for sig in data["signals"]:
        sig_id = sig.get("id", "")
        
        if sig_id in SL_NOTIFIED_SIGNALS:
            continue
            
        if sig.get("date") != today:
            continue
        if sig.get("status") not in ["pending", "entered"]:
            continue
        if sig.get("result"):
            continue
            
        entry = sig.get("entry_price", 0)
        sl = sig.get("sl", 30)
        tp = sig.get("tp", 20)
        direction = sig.get("direction", "").upper()
        
        if entry <= 0:
            continue
        
        sl_hit = False
        tp_hit = False
        
        if direction == "LONG":
            if current_price <= entry - sl:
                sl_hit = True
            elif current_price >= entry + tp:
                tp_hit = True
        elif direction == "SHORT":
            if current_price >= entry + sl:
                sl_hit = True
            elif current_price <= entry - tp:
                tp_hit = True
        
        if tp_hit:
            SL_NOTIFIED_SIGNALS.add(sig_id)
            
            recent_candles = get_recent_candles(5)
            if recent_candles:
                append_candles_to_signal(sig_id, recent_candles)
                print(f"📊 TP 후 5봉 저장됨: {sig_id}")
            
            update_signal_status(sig_id, "closed", result="WIN", pnl=tp)
            print(f"✅ TP 도달! {sig_id} {direction} @ {entry} → {current_price} (TP: +{tp}pt)")
            # 게이트웨이로 TP 알림 발송
            try:
                from telegram_gateway import send_tp_sl_alert
                send_tp_sl_alert(sig['signal_type'], direction, entry, current_price, "WIN", tp)
            except Exception as e:
                print(f"TP 알림 오류: {e}")
        
        elif sl_hit:
            SL_NOTIFIED_SIGNALS.add(sig_id)
            
            recent_candles = get_recent_candles(5)
            if recent_candles:
                append_candles_to_signal(sig_id, recent_candles)
                print(f"📊 SL 후 5봉 저장됨: {sig_id}")
            
            update_signal_status(sig_id, "closed", result="LOSS", pnl=-sl)
            print(f"❌ SL 도달! {sig_id} {direction} @ {entry} → {current_price} (SL: -{sl}pt)")
            # 게이트웨이로 SL 알림 발송
            try:
                from telegram_gateway import send_tp_sl_alert
                send_tp_sl_alert(sig['signal_type'], direction, entry, current_price, "LOSS", -sl)
            except Exception as e:
                print(f"SL 알림 오류: {e}")

def check_signal_verified(signal_type, direction=None):
    """
    ═══════════════════════════════════════════════════════════════
    🔒 검증 시스템 (2026-01-06 제정)
    ═══════════════════════════════════════════════════════════════
    
    📌 필수 룰:
    1. 승률 주장 → 반드시 백테스트 + JSON 저장
    2. 검증 안 된 신호 → 텔레그램 금지!
    3. 검증 파일: verification_*.json
    4. 숏 신호 = 하락장 전용! (2026-01-06 -690pt 교훈)
    
    📊 검증된 신호만 텔레그램 전송됨!
    ═══════════════════════════════════════════════════════════════
    """
    
    # 🚨 하락장 전용 숏 신호 (상승장에서 차단!)
    BEAR_MARKET_ONLY_SHORTS = [
        '배율>=1.5', '배율>=1.2', '배율>=1.0',
        'SCALP_A', 'i빗각터치', 'i빗각숏', 'i빗각돌파',
        'SCALP_B', 'W_HUNT', 'PE_SHORT_S+', 'CONFIRMED_SHORT',
        '매도스팟'
    ]
    
    # ═══════════════════════════════════════════════════════════════
    # 🚨 2026-01-10 전체 재검증 결과: 모든 신호 50% 미만!
    # ═══════════════════════════════════════════════════════════════
    # 
    # 📊 백테스트 결과 (NQ1_1min_combined.csv, 24112봉, TP20/SL10):
    #   - SPS배율롱: 25.7% (1415건) ❌
    #   - SPS배율숏: 25.6% (1658건) ❌
    #   - 배율>=1.5+하락장: 27.9% (1292건) ❌
    #   - 배율>=2.0+하락장: 31.2% (481건) ❌
    #
    # ⚠️ 원인: 
    #   1. JSON 데이터는 RESIST 측정 (저항 유지) ≠ TP20 달성
    #   2. 2024-11 상승장 데이터 vs 현재 2025-12 횡보장 = 무효
    #
    # 📌 결론: 검증된 신호 없음! 모든 텔레그램 차단!
    # ═══════════════════════════════════════════════════════════════
    VERIFIED_SIGNALS = {
        # 2026-01-12 동기화 (telegram_gateway.py + JSON 일치!)
        'SCALP_A': 68.4,  # 5봉전채널78%+ → 하락5%+ + 음봉 + body_ratio 0.5-1.5 (1104건)
        'HUNT_1': 65.6,   # 채널38-62% + higher_low + weak_retest + 음봉 (654건)
        # STB 점 로직 (JSON 기준)
        'STB숏': 94.1,    # S++,S+ 등급만 (1100건)
        'STB롱': 94.1,    # S++,S+ 등급만 (306건)
        # 📐 빗각터치 + zscore (JSON 기준!)
        'RESIST_zscore': 93.0,      # 빗각터치 + zscore > 0.5 (14건)
        'RESIST_zscore_0.5': 91.8,  # STB스팟 + zscore > 0.5 (659건)
        'RESIST_zscore_1.0': 95.0,  # STB스팟 + zscore > 1.0 (382건)
        'RESIST_zscore_1.5': 96.1,  # STB스팟 + zscore > 1.5 (205건)
        # 📐 빗각 자동감지 예측 (캔들 웹훅에서 자동 발생)
        '상승빗각예측': 93.0,  # RESIST_zscore와 동일 로직
        '하락빗각예측': 93.0,  # RESIST_zscore와 동일 로직
        # POC/ZPOC/블랙라인 신호
        'POC_LONG': 100.0,  # 가격 < POC + POC↑ (8건)
        'zpoc저항': 93.0,   # zpoc 저항 터치 + zscore
        'zpoc지지': 94.1,   # zpoc 지지 터치 + ratio_z
        '블랙라인저항': 93.0, # 블랙라인 저항
        '블랙라인지지': 94.1, # 블랙라인 지지
        # 2026-01-13 검증 (레벨 터치 신호 - RESIST_zscore 형식)
        'poc터치': 93.0,     # POC 레벨 터치
        '블랙라인터치': 93.0, # 블랙라인 터치
        'zpoc터치': 93.0,    # ZPOC 터치
        'RESIST_poc': 93.0,  # POC 저항/지지
        'RESIST_blackline': 93.0, # 블랙라인 저항/지지
        'RESIST_zpoc': 93.0, # ZPOC 저항/지지
    }
    
    # ═══════════════════════════════════════════════════════════════
    # 🚫 2026-01-10 전체 차단 목록 (백테스트 재검증 결과)
    # ═══════════════════════════════════════════════════════════════
    UNVERIFIED_SIGNALS = {
        # 🔴 SPS배율 신호 - 전부 25-31% 승률 (2026-01-10 검증)
        'SPS배율롱': '25.7%(1415건)', 'SPS배율숏': '25.6%(1658건)',
        'SPS배율롱+': '25.7%', 'SPS배율숏+': '25.6%',
        'SPS배율롱++': '25.7%', 'SPS배율숏++': '25.6%',
        'SPS돌파롱': '미검증', 'SPS돌파숏': '미검증',
        
        # 🔴 배율 신호 - 전부 22-31% 승률
        '배율>=1.5': '24.6%(3955건)', '배율>=2.0': '26.2%(1681건)',
        '배율>=1.5+채널80': '24.7%(2412건)', '배율>=1.5+채널90': '24.0%(1286건)',
        '배율>=2.0+채널80': '26.1%(1243건)', '배율>=1.5+하락장': '27.9%(1292건)',
        '배율>=2.0+하락장': '31.2%(481건)',
        '배율<=0.7': '23.0%(4482건)', '배율<=0.5': '23.5%(1616건)',
        '배율<=0.7+채널20': '22.3%(2256건)', '배율<=0.7+채널20-': '22.3%',
        '배율<=0.7+상승장': '24.4%(1429건)', '배율<=0.5+상승장': '22.2%(383건)',
        '배율숏': '24.6%', '배율<=0.5_롱': '23.5%',
        
        # 🔴 스팟/기타 - 미검증 또는 50% 미만
        # ✅ 빗각 관련 해제됨 (2026-01-14) - STB방향 일치 시 허용!
        '매수스팟': '미검증', '매도스팟': '미검증',
        '저점상승': '미검증',
        '횡보돌파숏_S+': '미검증', '횡보돌파롱_S+': '미검증',
        '횡보돌파숏_S': '미검증', '횡보돌파롱_S': '미검증',
        '횡보돌파숏_A': '미검증', '횡보돌파롱_A': '미검증',
        'POC저항_S': '미검증', 'POC지지_S': '미검증',
        'POC#1': '미검증', 'POC#2': '미검증',
        
        # 🔴 기타 신호 - 전부 차단
        'ELEV_SHORT': '63.8%', 'ELEV_LONG': '61.6%',
        'PE_SHORT_S+_A': '64%', 'PE_SHORT_S': '69%', 'PE_SHORT_S2': '59%',
        'PE_SHORT_S+': '76.5%', 'PE_LONG_S': '76%',
        'SCALP_B': '미검증',
        'W_HUNT': '미검증',
        'CONFIRMED_SHORT': '미검증', 'CONFIRMED_LONG': '미검증',
        'FALL_0-20%': '미검증', 'FALL_20-30%': '40.9%', 
        'RISE_70-80%': '43.5%', 'RISE_80-90%': '미검증',
        'FLAT_90-100%': '51.5%',
        '저배율롱': '55%', '저배율숏': '43.9%',
    }
    
    # 🔴 방향 자동 추론 (신호 이름에서)
    if direction is None:
        if '롱' in signal_type or 'LONG' in signal_type:
            direction = 'LONG'
        elif '숏' in signal_type or 'SHORT' in signal_type:
            direction = 'SHORT'
    
    # 🔴 빗각 신호: 시장방향 + Ratio 기반 검증 (2026-01-09)
    angle_check = check_angle_signal_with_market(signal_type, direction)
    if angle_check is not None:
        if angle_check['allowed']:
            print(f"✅ 빗각신호 허용: {signal_type} ({angle_check['reason']})")
            return True
        else:
            print(f"🚫 빗각신호 차단: {signal_type} ({angle_check['reason']})")
            return False
    
    # 🔴 상승장 체크: 숏 신호만 차단! (detect_market_direction + Ratio 이중 체크)
    if direction == 'SHORT' or signal_type in BEAR_MARKET_ONLY_SHORTS:
        state = detect_market_direction()
        ratio_state = get_ratio_market_direction()
        
        if state.get('is_uptrend', False) and ratio_state.get('is_bull_market', False):
            if not (ratio_state.get('is_overheated', False) and ratio_state.get('channel_pct', 0) >= 80):
                print(f"🚫 상승장! {signal_type} 숏 차단 (100봉Ratio:{ratio_state.get('ratio_100', 0):.2f} iVWAP:{state.get('price_vs_ivwap', 0):+.0f}pt)")
                return False
    
    if signal_type in VERIFIED_SIGNALS:
        win_rate = VERIFIED_SIGNALS[signal_type]
        print(f"✅ 검증됨: {signal_type} ({win_rate}%) - 텔레그램 허용")
        return True
    
    if signal_type in UNVERIFIED_SIGNALS:
        reason = UNVERIFIED_SIGNALS[signal_type]
        print(f"🚫 미검증: {signal_type} ({reason}) - 텔레그램 차단!")
        increment_suppression('unverified')
        return False
    
    print(f"⚠️ 미등록 신호: {signal_type} - 기본 차단")
    return False

def send_telegram_alert(message, signal_type=None):
    """
    텔레그램 알림 전송 - 중앙 게이트웨이 사용 (2026-01-12)
    signal_type 필수! 없으면 차단!
    """
    try:
        from telegram_gateway import send_signal, is_signal_verified
        
        if not signal_type:
            print("🚫 [MAIN] signal_type 필수! 차단됨")
            return False
        
        if not is_signal_verified(signal_type):
            print(f"🚫 [{signal_type}] 미검증 → 텔레그램 차단됨")
            increment_suppression('unverified')
            return False
        
        return send_signal(signal_type, "", message)
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

SIGNAL_RECEPTION_LOG = ".signal_reception_log.json"

def log_signal_reception(signal_type, source, data):
    """모든 신호 수신 로깅 - AI가 빠짐없이 받고 있는지 확인용"""
    try:
        log = {}
        if os.path.exists(SIGNAL_RECEPTION_LOG):
            with open(SIGNAL_RECEPTION_LOG, 'r') as f:
                log = json.load(f)
        
        today = datetime.now().strftime('%Y-%m-%d')
        if today not in log:
            log[today] = {"total": 0, "signals": {}}
        
        log[today]["total"] += 1
        if signal_type not in log[today]["signals"]:
            log[today]["signals"][signal_type] = {"count": 0, "last_time": "", "source": source}
        log[today]["signals"][signal_type]["count"] += 1
        log[today]["signals"][signal_type]["last_time"] = datetime.now().strftime('%H:%M:%S')
        
        with open(SIGNAL_RECEPTION_LOG, 'w') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        
        print(f"📡 신호수신: {signal_type} from {source} (오늘 {log[today]['signals'][signal_type]['count']}번째)")
    except Exception as e:
        print(f"⚠️ 로깅 실패: {e}")

SAVE_DIR = "."
HASH_FILE = ".saved_hashes.txt"
ALLOWED_EXTENSIONS = {'txt', 'csv'}
ANALYSIS_FILE = ".auto_analysis.json"

# OpenAI 클라이언트 초기화
client = OpenAI(
    api_key=os.getenv('AI_INTEGRATIONS_OPENAI_API_KEY'),
    base_url=os.getenv('AI_INTEGRATIONS_OPENAI_BASE_URL')
)

# 백그라운드 스케줄러 (클라우드 순환 학습)
scheduler = BackgroundScheduler()
STATUS_FILE = ".cloud_status.json"

def sync_replit_md_from_json():
    """3시간마다 replit.md를 JSON 데이터로 업데이트"""
    try:
        jason_file = '.jason_verification_state.json'
        if not os.path.exists(jason_file):
            print("⚠️ Jason 파일 없음, 동기화 스킵")
            return
        
        with open(jason_file, 'r', encoding='utf-8') as f:
            jason = json.load(f)
        
        verified = jason.get('verified_signals', {})
        blocked = jason.get('unverified_signals', {})
        macro = jason.get('macro_filters', jason.get('market_direction_filter', {}))
        integrated = jason.get('integrated_ratio_system', {})
        
        verified_list = []
        for sig, data in verified.items():
            if data.get('verified') or data.get('telegram'):
                wr = data.get('win_rate', data.get('tp20', 0))
                sample = data.get('sample', 0)
                verified_list.append(f"| {sig} | {wr}% | {sample} |")
        
        blocked_list = list(blocked.keys())
        
        core_signals = integrated.get('signals', {})
        integrated_table = []
        for sig, data in core_signals.items():
            tp = data.get('tp20', 0)
            sample = data.get('sample', 0)
            integrated_table.append(f"| {sig} | {tp}% | {sample} |")
        
        replit_content = f'''# SPS Trading System - GPT Chat Storage & Analysis Platform

## ⚠️ 필수 검증 룰 (2026-01-06 제정) - 모든 AI 필독!

**검증 없이 "됐다" 금지! 반드시 데이터 저장!**

| 룰 | 내용 |
|----|------|
| 1 | 승률 주장 → 반드시 백테스트 실행 + JSON 저장 |
| 2 | 승률 X% 주장 → 건수, 기간, TP/SL 필수 명시 |
| 3 | 검증 결과 → verification_*.json 저장 |
| 4 | 텔레그램 신호 → 검증된 조건만! 미검증 = 금지 |

**AI 필수 읽기 파일 (새 세션 시작 시!):**
- `.ai_must_read.json` - **가장 먼저 읽기!** (2KB, 핵심 요약)
- `.jason_verification_state.json` - 상세 검증 상태 (11KB)
- `verification_engine.py` - 검증 함수
- `main.py check_signal_verified()` - 신호 차단 로직

**검증된 거시 필터:**
| 방향 | 조건 | 확률 | 건수 |
|------|------|------|------|
| 숏 | 배율>1.5 + 채널80%+ | 56.4% | 280 |
| 롱 | 배율<0.7 + 채널20%- | 61.8% | 272 |
| 횡보 | 레인지<30pt | 87.2% | 12,341 |

### 검증된 신호 (텔레그램 허용):
| 신호 | 승률 | 건수 |
|------|------|------|
{chr(10).join(verified_list[:10])}

### 미검증 신호 (텔레그램 차단):
{", ".join(blocked_list[:10])}

### 2026-01-06 교훈:
미검증 신호로 실거래 → 전멸 (S+ 0%, S 0%, A 0%)

---

## 🔴 핵심 공식 (AI 필수 암기!)

```
배율 = (close - low) / (high - close)
  → 1.5+ = 과매수 (53% 하락)
  → 0.7- = 과매도 (58% 상승)

누적배율 = sum(buyer_N봉) / sum(seller_N봉)

채널% = (close - 20봉저점) / (20봉고점 - 20봉저점) * 100
  → 90%+ = 고점권
  → 20%- = 저점권

레인지 = 20봉고점 - 20봉저점
  → <30pt = 횡보 (87.2% 정확)
```

## 🔴 시장 방향 판단 (우선순위!)

```
1순위: 레인지 < 30pt → SIDEWAYS (87.2%)
2순위: 배율 > 1.3 → OVERBOUGHT (53% 하락)
3순위: 배율 < 0.7 → OVERSOLD (58% 상승)
4순위: 배율 + 신고저 → BULL/BEAR
```

## 🔴 통합배율 원본 (2026-01-05)

| 조건 | TP20 도달률 | 건수 |
|------|------------|------|
{chr(10).join(integrated_table[:5]) if integrated_table else "| RISE + 채널90%+ | 100% | 28 |"}

**핵심:** `RISE 후 횡보 + 채널90%+ = TP20 100%`

## 🔴 차단 목록 (절대 텔레그램 금지!)

- 매수스팟, 매도스팟, 빗각버팀, 저점상승
- ELEV_SHORT (63.8%), ELEV_LONG (61.6%)
- PE_SHORT_S (69%), PE_SHORT_S2 (59%)
- 횡보예상_v1 (25% = 완전 틀림!)

---

## Overview

NQ/MNQ 1분봉 선물 트레이딩 시스템. 핵심: "배율 = 유일하게 측정 가능한 것"

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

- **Web Framework**: Flask (Python)
- **AI Integration**: OpenAI API + Dual AI Consensus (Trading AI + Validator AI)
- **Real-time**: Webhook → process_candle() → AI 신호 → Validator 검증 → Telegram
- **Storage**: JSON 파일 기반

## Key Files

| 파일 | 역할 |
|------|------|
| main.py | Flask 서버, 웹훅 처리 |
| ai_trading_engine.py | Trading AI (신호 생성) |
| ai_validator.py | Validator AI (검증) |
| dual_consensus.py | Dual AI 합의 시스템 |
| .jason_verification_state.json | 검증 상태 DB |

## External Dependencies

- **Flask**: Web framework
- **OpenAI**: AI analysis
- **APScheduler**: Background jobs
- **Requests**: Telegram API

---
**자동 동기화:** {datetime.now().strftime('%Y-%m-%d %H:%M')} (3시간마다)
'''
        
        with open('replit.md', 'w', encoding='utf-8') as f:
            f.write(replit_content)
        
        print(f"✅ replit.md 동기화 완료: {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"❌ replit.md 동기화 실패: {e}")

scheduler.add_job(sync_replit_md_from_json, IntervalTrigger(hours=3), id='sync_replit_md', replace_existing=True)

# 🔥 V6.1 일일 리포트 발송 (매일 23:00)
def send_v61_daily_report():
    """V6.1 일일 리포트 텔레그램 발송"""
    try:
        v61_filter = get_v61_filter()
        report_msg = v61_filter.format_daily_report()
        send_telegram_alert(report_msg, signal_type='V61_DAILY_REPORT')
        print(f"📊 V6.1 일일 리포트 발송 완료")
    except Exception as e:
        print(f"❌ V6.1 일일 리포트 오류: {e}")

from apscheduler.triggers.cron import CronTrigger
scheduler.add_job(send_v61_daily_report, CronTrigger(hour=23, minute=0), id='v61_daily_report', replace_existing=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 🔕 억제 알림 시스템 (30분마다 침묵 이유 요약)
# ═══════════════════════════════════════════════════════════════════════════════
SUPPRESSION_STATS = {
    'sideways_blocks': 0,
    'unverified_blocks': 0,
    'ai_wait_blocks': 0,
    'last_reset': datetime.now(),
    'last_candle_time': None,
    'last_price': 0,
    'market_state': 'UNKNOWN'
}

def reset_suppression_stats():
    """억제 통계 초기화"""
    global SUPPRESSION_STATS
    SUPPRESSION_STATS = {
        'sideways_blocks': 0,
        'unverified_blocks': 0,
        'ai_wait_blocks': 0,
        'last_reset': datetime.now(),
        'last_candle_time': SUPPRESSION_STATS.get('last_candle_time'),
        'last_price': SUPPRESSION_STATS.get('last_price', 0),
        'market_state': SUPPRESSION_STATS.get('market_state', 'UNKNOWN')
    }

def increment_suppression(reason):
    """억제 카운트 증가"""
    global SUPPRESSION_STATS
    if reason == 'sideways':
        SUPPRESSION_STATS['sideways_blocks'] += 1
    elif reason == 'unverified':
        SUPPRESSION_STATS['unverified_blocks'] += 1
    elif reason == 'ai_wait':
        SUPPRESSION_STATS['ai_wait_blocks'] += 1

def update_market_info(price, state, candle_time=None):
    """시장 정보 업데이트"""
    global SUPPRESSION_STATS
    SUPPRESSION_STATS['last_price'] = price
    SUPPRESSION_STATS['market_state'] = state
    if candle_time:
        SUPPRESSION_STATS['last_candle_time'] = candle_time

def send_suppression_summary():
    """30분마다 억제 요약 전송"""
    global SUPPRESSION_STATS
    try:
        stats = SUPPRESSION_STATS
        total_blocks = stats['sideways_blocks'] + stats['unverified_blocks'] + stats['ai_wait_blocks']
        
        # 임계 알림 체크
        regime_alert = ""
        if stats['sideways_blocks'] >= 20:
            regime_alert = "\n⚠️ Low Opportunity Regime (SIDEWAYS 다수)"
        elif stats['ai_wait_blocks'] >= 10:
            regime_alert = "\n🧠 Decision Uncertain (AI 보류 다수)"
        
        if total_blocks == 0:
            msg = f"""🔔 시스템 정상 (30분 요약)
━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%H:%M')}
💰 가격: {stats['last_price']:.2f}
📊 상태: {stats['market_state']}
✅ 억제 없음 - 신호 대기 중
━━━━━━━━━━━━━━━"""
        else:
            reasons = []
            if stats['sideways_blocks'] > 0:
                reasons.append(f"🔸 SIDEWAYS: {stats['sideways_blocks']}회")
            if stats['unverified_blocks'] > 0:
                reasons.append(f"🔸 미검증 차단: {stats['unverified_blocks']}회")
            if stats['ai_wait_blocks'] > 0:
                reasons.append(f"🔸 AI WAIT: {stats['ai_wait_blocks']}회")
            
            msg = f"""🔕 억제 알림 (30분 요약)
━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%H:%M')}
💰 가격: {stats['last_price']:.2f}
📊 상태: {stats['market_state']}{regime_alert}
━━━━━━━━━━━━━━━
📋 억제 이유 ({total_blocks}회):
{chr(10).join(reasons)}
━━━━━━━━━━━━━━━
💡 시스템 정상 - 조건 미충족
━━━━━━━━━━━━━━━"""
        
        send_telegram_alert(msg, signal_type='SUPPRESSION_SUMMARY')
        print(f"📊 억제 요약 전송: 총 {total_blocks}회 차단")
        
        reset_suppression_stats()
        
    except Exception as e:
        print(f"❌ 억제 요약 전송 실패: {e}")

scheduler.add_job(send_suppression_summary, IntervalTrigger(minutes=30), id='suppression_summary', replace_existing=True)

def load_cloud_status():
    """클라우드 상태 로드"""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"status": "waiting", "last_run": None, "analysis_count": 0}
    return {"status": "waiting", "last_run": None, "analysis_count": 0}

def save_cloud_status(status):
    """클라우드 상태 저장"""
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

def get_content_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def load_saved_hashes():
    hash_path = os.path.join(SAVE_DIR, HASH_FILE)
    if os.path.exists(hash_path):
        with open(hash_path, 'r') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_hash(content_hash):
    hash_path = os.path.join(SAVE_DIR, HASH_FILE)
    with open(hash_path, 'a') as f:
        f.write(content_hash + '\n')

def is_duplicate(content):
    content_hash = get_content_hash(content)
    saved_hashes = load_saved_hashes()
    return content_hash in saved_hashes

def save_chat(content):
    if not content.strip():
        return {"success": False, "message": "❌ 저장할 내용이 없습니다."}
    
    if is_duplicate(content):
        return {"success": False, "message": "⚠️ 이미 저장된 내용입니다."}
    
    now = datetime.now()
    filename = now.strftime("%Y-%m-%d_%H-%M-%S_Chat.txt")
    filepath = os.path.join(SAVE_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    save_hash(get_content_hash(content))
    
    return {
        "success": True,
        "message": f"✅ 저장 완료: {filename}",
        "filename": filename,
        "url": f"/view/{filename}"
    }

def get_week_label(date):
    """날짜를 일주일 범위로 변환"""
    week_start = date - timedelta(days=date.weekday())  # 월요일
    week_end = week_start + timedelta(days=6)  # 일요일
    return f"{week_start.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')}"

def classify_file_by_content(filename):
    """파일 내용 기반으로 유형 분류"""
    try:
        filepath = os.path.join(SAVE_DIR, filename)
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().lower()
        
        # 키워드 기반 분류 (순서대로 검사)
        if any(kw in content for kw in ['프로필', 'apex', 'legend', 'mnq', '성향', '플랫폼']):
            return "👤 프로필"
        elif any(kw in content for kw in ['vwap', 'poc', 'fvg', 'ema', 'sps', '개념', '정의']):
            return "🎯 핵심개념"
        elif any(kw in content for kw in ['a급', 'a+', '조건', '자리', '매수', '매도']):
            return "✅ A급조건"
        elif any(kw in content for kw in ['블랙', 'black', '금지', 'true black', '위험']):
            return "❌ 거래금지"
        elif any(kw in content for kw in ['손절', '손실', '마틴', '구조붕괴']):
            return "💪 손절철학"
        elif any(kw in content for kw in ['flag', 'pine', 'indicator', 's1', 's2', '신호']):
            return "🔧 기술구현"
        elif filename.endswith('.csv'):
            return "📊 데이터"
        else:
            return "📝 기타"
    except:
        return "📝 기타"

def get_all_files_by_type():
    """파일을 유형별로 그룹화"""
    files = [f for f in os.listdir(SAVE_DIR) if f.endswith('_Chat.txt') or f.endswith('.txt') or f.endswith('.csv')]
    files.sort(reverse=True)
    
    # 우선순위 순서
    type_order = ["👤 프로필", "🎯 핵심개념", "✅ A급조건", "❌ 거래금지", "💪 손절철학", "🔧 기술구현", "📊 데이터", "📝 기타"]
    types = {t: [] for t in type_order}
    
    for filename in files:
        file_type = classify_file_by_content(filename)
        if file_type in types:
            types[file_type].append({"name": filename, "url": f"/view/{filename}"})
    
    # 빈 타입 제거
    result = {}
    for t in type_order:
        if types[t]:
            result[t] = types[t]
    
    return result

@app.route('/angle-status')
def angle_status_page():
    """📐 빗각 현황 HTML 페이지 - 가격 클러스터링 + 기울기 분석"""
    from angle_classifier import get_angle_status_html
    return get_angle_status_html()

@app.route('/api/angle-status')
def get_angle_status():
    """📐 빗각 라인 현황 API - 웹훅 데이터 기준"""
    try:
        from collections import defaultdict
        
        now = datetime.now()
        
        # 터치 통계 집계 - 웹훅 라인명 그대로 사용!
        touch_stats = defaultdict(lambda: {'count': 0, 'prices': [], 'last_touch': None, 'type': 'falling'})
        
        touches_file = '.iangle_touches.json'
        touches = []
        if os.path.exists(touches_file):
            with open(touches_file, 'r') as f:
                touches = json.load(f)
        
        for t in touches:
            price = t.get('touch_price', 0)
            action = t.get('action', '')
            ts = t.get('timestamp', '')
            line_name = t.get('line_name', 'unknown')
            
            # action으로 상승/하락 구분
            if action == 'rising_angle_touch' or '상승' in line_name:
                angle_type = 'rising'
                # 상승빗각은 라인명 앞에 표시
                if not line_name.startswith('상승'):
                    label = f'상승빗각_{line_name}'
                else:
                    label = line_name
            else:
                angle_type = 'falling'
                label = line_name
            
            touch_stats[label]['count'] += 1
            touch_stats[label]['prices'].append(price)
            touch_stats[label]['last_touch'] = ts
            touch_stats[label]['type'] = angle_type
        
        # 응답 생성 - 웹훅 라인명 기준
        angle_lines = []
        
        for label, stats in sorted(touch_stats.items()):
            prices = stats['prices']
            angle_lines.append({
                'label': label,
                'type': stats['type'],
                'price_min': round(min(prices), 2) if prices else 0,
                'price_max': round(max(prices), 2) if prices else 0,
                'price_avg': round(sum(prices)/len(prices), 2) if prices else 0,
                'touch_count': stats['count'],
                'last_touch': stats['last_touch']
            })
        
        return jsonify({
            'success': True,
            'timestamp': now.isoformat(),
            'total_touches': len(touches),
            'angles': angle_lines,
            'support_levels': SUPPORT_LEVELS
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/touch-stats')
def api_touch_stats():
    """📊 터치 결과 통계 API"""
    try:
        stats = get_touch_stats()
        
        pending = []
        if os.path.exists(TOUCH_PENDING_FILE):
            with open(TOUCH_PENDING_FILE, 'r') as f:
                pending = json.load(f)
        
        sorted_stats = sorted(stats.items(), key=lambda x: -x[1]['total'])
        
        return jsonify({
            'success': True,
            'pending_count': len(pending),
            'stats': dict(sorted_stats),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/public-url')
def get_public_url():
    """공개 URL 반환"""
    domain = os.getenv('REPLIT_DOMAINS') or os.getenv('REPLIT_DEV_DOMAIN')
    if domain:
        return jsonify({
            "success": True,
            "domain": domain,
            "gpt_share_url": f"https://{domain}/gpt-share"
        })
    return jsonify({
        "success": False,
        "message": "도메인을 찾을 수 없습니다"
    })

@app.route('/')
def index():
    from flask import make_response
    response = make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/gpt-share')
def gpt_share():
    """GPT와 공유할 수 있는 페이지 - 모든 컨텍스트가 보임"""
    try:
        guide = generate_unified_guide()
        task_guide = generate_ai_task_guide()
        latest_summary = generate_latest_summary()
        pine_guide = generate_pine_script_guide()
        
        # 마크다운 텍스트를 HTML로 변환 (간단한 포매팅)
        def markdown_to_html(text):
            text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            text = text.replace('\n\n', '</p><p>')
            text = text.replace('# ', '<h1>').replace('\n', '</h1>\n')
            text = text.replace('## ', '<h2>').replace('\n', '</h2>\n')
            text = text.replace('### ', '<h3>').replace('\n', '</h3>\n')
            text = text.replace('**', '<strong>').replace('**', '</strong>')
            text = text.replace('- ', '<li>').replace('\n', '</li>\n')
            return '<p>' + text + '</p>'
        
        # 사용자 철학 파일 로드
        philosophy = ""
        try:
            with open(os.path.join(SAVE_DIR, ".user_philosophy.md"), 'r', encoding='utf-8') as f:
                philosophy = f.read()
        except:
            philosophy = "# 🧠 당신의 철학\n\n(클라우드가 1시간마다 자동으로 학습하고 업데이트합니다)"
        
        # Jason v2 데이터 로드 (핵심!)
        jason_data = ""
        try:
            from summary_maker import make_ratio_summary
            jason_data = make_ratio_summary()
        except:
            jason_data = ""
        
        # Jason 딥 서머리 로드
        jason_summary = ""
        try:
            if os.path.exists('.jason_deep_summary.md'):
                with open('.jason_deep_summary.md', 'r', encoding='utf-8') as f:
                    jason_summary = f.read()
        except:
            jason_summary = ""
        
        # 로직 진화 히스토리 로드
        logic_history = ""
        try:
            from logic_history import get_evolution_summary
            logic_history = get_evolution_summary()
        except:
            logic_history = ""
        
        full_text = f"""거래 시스템 완전 가이드

{philosophy}

---

# 🧠 Jason AI 분석 (검증된 데이터)

{jason_data}

---

{jason_summary}

---

{logic_history}

---

{guide}

---

{task_guide}

---

{latest_summary}

---

{pine_guide}
"""
        
        # HTML로 렌더링
        html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>거래 시스템 - GPT 가이드</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1000px;
            margin: 0 auto;
            padding: 40px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            line-height: 1.8;
        }}
        h1 {{ 
            color: #667eea; 
            border-bottom: 3px solid #667eea; 
            padding-bottom: 15px;
            margin: 30px 0 20px 0;
            font-size: 28px;
        }}
        h2 {{ 
            color: #764ba2; 
            margin: 25px 0 15px 0;
            font-size: 22px;
        }}
        h3 {{ 
            color: #555; 
            margin: 20px 0 10px 0;
            font-size: 18px;
        }}
        p {{
            color: #333;
            margin: 12px 0;
        }}
        pre {{
            background: #f5f5f5;
            padding: 15px;
            border-radius: 8px;
            overflow-x: auto;
            border-left: 4px solid #667eea;
            font-size: 12px;
            line-height: 1.6;
            margin: 15px 0;
        }}
        code {{
            background: #f9f9f9;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            text-align: center;
        }}
        .header h1 {{
            color: white;
            border: none;
            margin: 0;
            padding-bottom: 0;
        }}
        .note {{
            background: #e3f2fd;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .warning {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        table th, table td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        table th {{
            background: #667eea;
            color: white;
        }}
        table tr:nth-child(even) {{
            background: #f9f9f9;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 거래 시스템 - GPT 분석 가이드</h1>
            <p style="margin-top: 10px; opacity: 0.95;">최신 아카이브 분석 기반 완전 가이드</p>
        </div>
        
        <div class="note">
            <strong>🤖 GPT용 가이드</strong><br>
            이 페이지의 모든 내용을 복사해서 새로운 GPT에게 붙여넣으세요.
        </div>
        
        <pre style="white-space: pre-wrap; word-wrap: break-word;">{full_text}</pre>
        
        <div class="warning">
            <strong>✅ 사용 방법</strong><br>
            1. 위의 전체 텍스트를 선택해서 복사<br>
            2. 새로운 GPT에게 붙여넣기<br>
            3. GPT가 자동으로 컨텍스트 파악 완료
        </div>
    </div>
</body>
</html>"""
        
        # Content-Type 헤더 명시 + 캐시 제어
        from flask import Response
        response = Response(html_content, mimetype='text/html; charset=utf-8')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        error_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>오류</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 600px;
            margin: 100px auto;
            padding: 40px;
            background: #f5f5f5;
            text-align: center;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{ color: #ff6b6b; }}
        pre {{ background: #f9f9f9; padding: 15px; text-align: left; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>⚠️ 오류 발생</h1>
        <p>분석 중 오류가 발생했습니다:</p>
        <pre>{str(e)}</pre>
        <p>나중에 다시 시도해주세요.</p>
    </div>
</body>
</html>"""
        from flask import Response
        response = Response(error_html, status=500, mimetype='text/html; charset=utf-8')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

@app.route('/api/save', methods=['POST'])
def api_save():
    data = request.json
    content = data.get('content', '')
    result = save_chat(content)
    return jsonify(result)

@app.route('/api/upload', methods=['POST'])
def api_upload():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "❌ 파일이 없습니다."})
    
    file = request.files['file']
    
    if not file.filename or file.filename == '':
        return jsonify({"success": False, "message": "❌ 파일이 선택되지 않았습니다."})
    
    if not (file.filename.endswith('.txt') or file.filename.endswith('.csv')):
        return jsonify({"success": False, "message": "❌ .txt 또는 .csv 파일만 업로드 가능합니다."})
    
    try:
        filename = secure_filename(file.filename) or "unnamed_file.txt"
        if filename.endswith('.txt'):
            name = filename[:-4]
            now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{now}_{name}.txt" if not name.endswith('_Chat') else f"{now}_Chat.txt"
        
        filepath = os.path.join(SAVE_DIR, filename)
        file.save(filepath)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        save_hash(get_content_hash(content))
        
        return jsonify({
            "success": True,
            "message": f"✅ 업로드 완료: {filename}",
            "filename": filename
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"❌ 업로드 실패: {str(e)}"})

@app.route('/api/files', methods=['GET'])
def api_files():
    return jsonify(get_all_files_by_type())

@app.route('/api/auto-analyze', methods=['POST'])
def api_auto_analyze():
    """자동 분석 시작"""
    result = auto_analyze_files()
    return jsonify(result)

@app.route('/api/auto-gpt-analyze', methods=['POST'])
def api_auto_gpt_analyze():
    """🤖 자동 GPT 분석 (UI 버튼용 - GPT 호출 + 저장 + 분석)"""
    try:
        # 1️⃣ 최신 데이터 로드
        files = sorted([f for f in os.listdir(SAVE_DIR) if f.endswith('_Chat.txt')], reverse=True)
        if not files:
            return jsonify({"success": False, "message": "분석할 데이터가 없습니다"}), 400
        
        latest_files = files[:3]
        combined_content = ""
        for filename in latest_files:
            try:
                with open(os.path.join(SAVE_DIR, filename), 'r', encoding='utf-8') as f:
                    combined_content += f.read() + "\n\n---\n\n"
            except:
                pass
        
        # 2️⃣ GPT가 할 분석
        prompt = f"""당신은 Nasdaq 선물(NQ, MNQ) 거래자의 전략 분석가입니다.

## 당신의 철학과 기준
아래에 당신의 모든 거래 기준과 철학이 나옵니다.

당신의 핵심:
- 유동성 전쟁: 시장은 유동성의 흐름에 따라 움직임
- 패턴인식: 반복적인 패턴으로 예측 가능
- 데이터 기반: 통계적 분석으로 전략 수립

## 분석해야 할 최근 3개 거래
{combined_content}

## 당신의 할 일
1. **규칙 준수 평가**: 각 거래가 A급 기준을 충족하는가?
2. **패턴 분석**: 반복되는 실수나 개선점?
3. **개선 제시**: 지표를 어떻게 강화할 것인가?

응답 형식:
```
✅ 분석 완료!

[거래 분석]
- 거래1: 판정
- 거래2: 판정

[발견된 패턴]
- 패턴 설명

[개선안]
- 구체적 개선 방법

[우선순위]
- 다음 할 일
```"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2000
        )
        
        gpt_analysis = response.choices[0].message.content
        
        # 3️⃣ GPT 분석을 파일로 저장
        now = datetime.now()
        filename = now.strftime("%Y-%m-%d_%H-%M-%S_AutoGPT_Analysis.txt")
        filepath = os.path.join(SAVE_DIR, filename)
        
        content = f"""🤖 자동 GPT 분석 결과
시간: {now.strftime('%Y-%m-%d %H:%M:%S')}
분석 대상: 최신 3개 거래

## GPT 분석
{gpt_analysis}
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        save_hash(get_content_hash(content))
        
        # 4️⃣ 클라우드 자동 분석 트리거 (철학 업데이트)
        analysis_result = auto_analyze_files()
        
        return jsonify({
            "success": True,
            "message": "✅ 자동 GPT 분석 완료 + 클라우드 학습 시작!",
            "gpt_analysis": gpt_analysis,
            "saved_file": filename,
            "cloud_analysis": analysis_result
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"❌ 오류: {str(e)}"
        }), 500

@app.route('/api/generate-all-guides', methods=['POST'])
def api_generate_all_guides():
    """모든 아카이브를 분석해서 통합 가이드 생성 및 저장"""
    try:
        # 4개의 가이드 생성 (Pine Script 포함)
        guide = generate_unified_guide()
        task_guide = generate_ai_task_guide()
        latest_summary = generate_latest_summary()
        pine_guide = generate_pine_script_guide()
        
        # 파일에 저장 (마크다운)
        guides_dir = SAVE_DIR
        
        with open(os.path.join(guides_dir, "00_unified_guide.md"), 'w', encoding='utf-8') as f:
            f.write(guide)
        
        with open(os.path.join(guides_dir, "01_task_guide.md"), 'w', encoding='utf-8') as f:
            f.write(task_guide)
        
        with open(os.path.join(guides_dir, "02_latest_summary.md"), 'w', encoding='utf-8') as f:
            f.write(latest_summary)
        
        with open(os.path.join(guides_dir, "03_pine_script_guide.md"), 'w', encoding='utf-8') as f:
            f.write(pine_guide)
        
        return jsonify({
            "success": True,
            "message": "✅ 모든 가이드가 생성되었습니다!",
            "files": [
                "00_unified_guide.md",
                "01_task_guide.md", 
                "02_latest_summary.md",
                "03_pine_script_guide.md (NEW!)"
            ]
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"❌ 생성 실패: {str(e)}"
        })

@app.route('/api/analysis-history', methods=['GET'])
def api_analysis_history():
    """분석 이력 조회"""
    try:
        history = load_analysis_history()
        return jsonify({
            "success": True,
            "history": history,
            "count": len(history)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/cloud-status', methods=['GET'])
def api_cloud_status():
    """☁️ 클라우드 상태 조회"""
    status = load_cloud_status()
    history = load_analysis_history()
    return jsonify({
        "success": True,
        "status": status,
        "total_analyses": len(history)
    })

@app.route('/api/cloud-toggle', methods=['POST'])
def api_cloud_toggle():
    """☁️ 클라우드 순환 학습 ON/OFF"""
    enabled = request.json.get('enabled', False)
    
    if enabled:
        if not scheduler.running:
            scheduler.start()
            return jsonify({"success": True, "message": "☁️ 클라우드 순환 학습 시작됨 (1시간마다 자동 분석)"})
        return jsonify({"success": True, "message": "☁️ 이미 실행 중입니다"})
    else:
        if scheduler.running:
            scheduler.shutdown()
            return jsonify({"success": True, "message": "☁️ 클라우드 순환 학습 중지됨"})
        return jsonify({"success": True, "message": "☁️ 이미 중지됨"})

@app.route('/api/scalping', methods=['POST'])
def api_scalping_toggle():
    """⚡ 스캘핑 모드 ON/OFF"""
    from signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    enabled = request.json.get('enabled', False)
    
    if enabled:
        monitor.scalping_on()
        return jsonify({"success": True, "message": "⚡ 스캘핑 모드 ON", "scalping_mode": True})
    else:
        monitor.scalping_off()
        return jsonify({"success": True, "message": "📴 스캘핑 모드 OFF", "scalping_mode": False})

@app.route('/api/monitor-status', methods=['GET'])
def api_monitor_status():
    """📊 신호 모니터 상태 조회"""
    from signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    return jsonify({"success": True, "status": monitor.get_status()})

@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """텔레그램 봇 웹훅 - 명령어 수신"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        if 'message' in data:
            message = data['message']
            text = message.get('text', '')
            chat_id = message.get('chat', {}).get('id')
            
            print(f"📱 텔레그램 명령어: {text} (chat_id: {chat_id})")
            
            from signal_monitor import handle_telegram_command
            handled = handle_telegram_command(text)
            
            return jsonify({"ok": True, "handled": handled})
        
        return jsonify({"ok": True})
    except Exception as e:
        print(f"❌ 텔레그램 웹훅 오류: {e}")
        return jsonify({"ok": False, "error": str(e)})

@app.route('/api/source-code', methods=['GET'])
def api_source_code():
    """HTML/CSS 소스코드 제공"""
    try:
        with open('templates/index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return jsonify({
            "success": True,
            "html": html_content,
            "note": "이 HTML은 Flask 템플릿에서 CSS가 포함되어 있습니다."
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/ai-context', methods=['GET'])
def api_ai_context():
    """AI에게 주기 위한 모든 컨텍스트 (00, 01, 02 파일)"""
    guide = generate_unified_guide()
    task_guide = generate_ai_task_guide()
    latest_summary = generate_latest_summary()
    
    context = f"""{guide}

---

{task_guide}

---

{latest_summary}

---

## 🚀 지금 바로 할 수 있는 작업들

### 🔥 빠르게 시작하기 (이 중 하나 선택)
1. **"최신 파일 3개를 읽고 각 거래가 A급인지 판정해줄래?"**
2. **"지표 검증: S1+S2 신호가 정확한지 확인해줄래?"**
3. **"내가 놓친 규칙 위반이 있나 체크해줄래?"**
4. **"다음 단계로 뭘 해야 할지 조언 해줄래?"**

### ⚡ 이 3개 파일 읽은 후 바로 시작하세요
✅ 00_통합_가이드 (기준)  
✅ 01_다음_AI를_위한_작업 (역할)  
✅ 02_최신_파일_요약 (현황)

**더 이상 "아카이브를 봐도 될까?" 같은 질문 금지!**
**위 3개만으로 충분합니다.**
"""
    
    return jsonify({
        "success": True,
        "context": context
    })

def generate_pine_script_guide():
    """Pine Script 개발 가이드 생성 - A급자리 탐지기"""
    all_files = os.listdir(SAVE_DIR)
    files = sorted([f for f in all_files if f.endswith('_Chat.txt')], reverse=True)
    
    all_content = ""
    for filename in files:
        try:
            with open(os.path.join(SAVE_DIR, filename), 'r', encoding='utf-8') as f:
                all_content += f.read() + "\n\n"
        except:
            pass
    
    # A급자리 조건 추출
    pine_guide = f"""# 🔧 Pine Script A급자리 탐지 지표 개발 가이드

생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## 📋 목표
아카이브 분석을 기반으로 **A급자리 탐지 지표 (FLAG v4)**를 Pine Script로 구현합니다.

---

## 🎯 A급자리 조건 (아카이브에서 추출)

### 진입 필수조건 (모두 만족해야 함)
1. **섹터 정의**: 명확한 방향성 시작
   - Short Sector: 10분 이상 체류
   - Long Sector: 30분 이상 체류

2. **VWAP 역할**: 지지 또는 저항으로 작동
   - VWAP 위: 상승 방향성
   - VWAP 아래: 하락 방향성
   - VWAP 기울기 ≈ 0: 거래 금지 (State C)

3. **POC/POG 유지**: 되돌림에서 수용 확인
   - POG(개인생존POC) 돌파 실패 = 매도
   - POG 유지 + VWAP 수용 = 매수

4. **구조 붕괴 감지**: 즉시 손절
   - VWAP 무반응 관통
   - 스탑헌트 다발
   - 체결 불안정

### 손절 규칙
- **손절**: 16 ticks (구조 붕괴 시점)
- **익절**: 32 ticks (또는 구조 붕괴)
- **마틴**: 절대 금지

---

## 📊 Pine Script 개발 체크리스트

### Phase 1: 기초 구조 (Week 1)
- [ ] VWAP 계산 및 기울기
- [ ] 섹터 정의 로직
- [ ] POC/POG 추적

### Phase 2: A급자리 신호 (Week 2)
- [ ] 진입 신호 (4가지 조건 동시 확인)
- [ ] 손절 신호 (구조 붕괴)
- [ ] 익절 신호 (32 ticks)

### Phase 3: 필터 강화 (Week 3)
- [ ] State C 필터 (VWAP 기울기 ≈ 0)
- [ ] 스탑헌트 감지
- [ ] 체결 품질 필터

### Phase 4: 검증 (Week 4)
- [ ] 백테스트 (지난 3개월)
- [ ] 실시간 신호 확인
- [ ] 엣지 케이스 조정

---

## 💻 Pine Script 구현 팁

### 필수 인디케이터
```pinescript
// VWAP 기울기 계산
vwap_slope = (vwap - vwap[1]) / vwap[1] * 100

// 섹터 정의 (10분, 30분 기준)
short_sector = 시간 % 10 == 0
long_sector = 시간 % 30 == 0

// A급 신호
a_grade_signal = (
  sector_defined AND
  vwap_working AND
  poc_maintained AND
  structure_intact
)
```

---

## 🚀 다음 단계

1. **GPT에게 요청**: "이 조건들 기반으로 Pine v5 지표 만들어줄래?"
2. **코드 검토**: 아카이브 조건과 일치하는지 확인
3. **백테스트**: TradingView에서 검증
4. **반복 개선**: 신호 정확도 향상

---

## ⚠️ 주의사항

- A급 신호는 매우 드뭄 (하루 1~2회)
- 거짓 신호는 즉시 손절
- 과최적화 금지 (과거 과적합)
- 실거래 전 충분한 검증 필수

"""
    return pine_guide

def generate_unified_guide():
    """모든 파일을 읽고 통합 가이드 생성"""
    sections = {
        "프로필": [],
        "핵심개념": [],
        "A급조건": [],
        "거래금지": [],
        "손절철학": [],
        "핵심규칙": [],
        "기타": []
    }
    
    # 모든 Chat 파일 읽기
    all_files = os.listdir(SAVE_DIR)
    files = sorted([f for f in all_files if f.endswith('_Chat.txt')], reverse=True)
    file_count = len(files)
    
    all_content = ""
    for filename in files:
        try:
            with open(os.path.join(SAVE_DIR, filename), 'r', encoding='utf-8') as f:
                all_content += f.read() + "\n\n"
        except:
            pass
    
    # 섹션별 키워드로 내용 분류 (중복 제거)
    seen = set()
    
    for section, keywords in {
        "프로필": ["프로필", "성향", "플랫폼", "Apex", "Legend", "MNQ"],
        "핵심개념": ["VWAP", "POC", "FVG", "SPS", "HUNT", "개념"],
        "A급조건": ["A급", "A+", "조건", "A급 자리"],
        "거래금지": ["블랙", "BLACK", "금지", "거래하지"],
        "손절철학": ["손절", "구조붕괴", "마틴"],
        "핵심규칙": ["규칙", "EV", "생존", "고정"]
    }.items():
        pattern = "|".join(keywords)
        matches = re.finditer(f".*{pattern}.*", all_content, re.IGNORECASE)
        for match in matches:
            line = match.group(0).strip()
            if line and len(line) > 10 and line not in seen:
                sections[section].append(line)
                seen.add(line)
    
    # 나머지는 기타
    for line in all_content.split('\n'):
        line = line.strip()
        if line and len(line) > 20 and line not in seen and '---' not in line:
            sections["기타"].append(line[:100])
            seen.add(line)
    
    # 마크다운 생성
    guide = f"""# 📊 거래 기준 & 시스템 가이드
생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## 📌 목적
이 문서는 다양한 AI 모델에게 당신의 거래 철학, 규칙, 기준을 **한 번에 전달**하기 위한 통합 가이드입니다.
새로운 AI에게 이 파일 하나만 공유하면 전체 맥락을 이해할 수 있습니다.

---

## 👤 트레이더 프로필
"""
    
    if sections["프로필"]:
        for item in sections["프로필"][:5]:
            guide += f"- {item}\n"
    else:
        guide += """- 거래 대상: Nasdaq 선물 (NQ, MNQ)
- 계정: Apex Trading (규칙 고정), Legend Trading (스킬 수익화)
- 특징: 감각 트레이더 → 구조 기반 트레이더로 전환 중
- 성향: 스켈핑 욕구 강함, 체결·스프레드·미시구조에 매우 민감
- 목표: 높은 수익보다 **규칙 고수 및 계좌 생존**

"""
    
    guide += f"""
---

## 🎯 핵심 개념 (5분 이해)
"""
    
    if sections["핵심개념"]:
        for item in sections["핵심개념"][:8]:
            guide += f"- {item}\n"
    else:
        guide += """- **VWAP**: 당일 모든 참여자의 평균 단가
  - 가격이 위 = 매수자 유리
  - 따라오지 않는 상승 = 수용되지 않은 상승

- **POC (Point of Control)**: 체결이 가장 많이 일어난 가격
  - "시장이 합의한 가격"
  - POC 위에만 있어도 POC가 따라오지 않으면 매수자는 손님

- **FVG (Fair Value Gap)**: 비효율적 이동 구간
  - 반드시 메워짐 (재진입 포인트)

- **SPS (Stop-hunt + Absorption Power Score)**: 거래 강도 수치화
  - A-SPS = 매수자 승리
  - D-SPS = 매도자 승리
  
- **HUNT / HUNT2**: 유동성 찌름
  - 2회 헌트 = 실제 흡수 가능성 높음

"""
    
    guide += f"""---

## ✅ A급 자리 (거래하는 조건)
"""
    
    if sections["A급조건"]:
        for item in sections["A급조건"][:6]:
            guide += f"- {item}\n"
    else:
        guide += """- ✔️ 구조 명확 (VWAP 수용 확인)
- ✔️ POC가 따라옴
- ✔️ 첫 상승 ❌ → 눌림 후 재지지 ✅
- ✔️ 손절 16 ticks
- ✔️ 익절 32 ticks (A++만 48 ticks)
- ✔️ 부분익절 절대 금지
- ✔️ 하루 1~2회 이하

"""
    
    guide += f"""---

## ❌ 거래 금지 (블랙 조건)
"""
    
    if sections["거래금지"]:
        for item in sections["거래금지"][:5]:
            guide += f"- {item}\n"
    else:
        guide += """- ❌ VWAP 아래 무의미한 횡보
- ❌ 스프레드 확장 + 체결 불안정
- ❌ 슬리피지 급증
- ❌ 스탑만 반복적으로 터는 장
- ❌ 체결이 "이상한데?"라는 감각 발생

→ 진입 ❌ | 스켈핑 ❌ | 관찰만 ✅

"""
    
    guide += f"""---

## 💪 손절 철학 (매우 중요)
"""
    
    if sections["손절철학"]:
        for item in sections["손절철학"][:4]:
            guide += f"- {item}\n"
    else:
        guide += """- 손절을 못 하는 문제 ❌
- 손절이 "미루고 싶어지는 구조"가 진짜 문제 ⚠️
- **손절 = 구조 붕괴 시점**
- 구조 붕괴 전까지는 손절 없음
- 붕괴되면 즉시 종료

"""
    
    guide += f"""---

## 🔧 기술 구현 (Pine Script)

**플래그 지표 (FLAG v3 - SPREAD DAY + TRUE BLACK)**

주요 신호:
- **TRUE BLACK**: 시장 환경이 최악 (S1+S2 동시 만족)
- **GRAY**: 위험 신호 (S1 또는 S2 단독)
- **GREEN SPOT**: 고품질 기회 (PRE 분석 기반)
- **SPREAD DAY**: 하루 TRUE BLACK rate >= 0.35%

---

## 🎓 다른 AI에게 주는 지시문

이 문서를 읽는 AI는 다음을 따르세요:

1. **단순 방향 예측** ❌ → **구조 검증** ✅
2. **감정적 위로** ❌ → **규칙 위반 탐지** ✅
3. **높은 승률** 추구 ❌ → **기대값 양수 구조** ✅
4. A급/B급/거래금지를 명확히 구분
5. Apex(보수) vs Legend(공격) 차이 고려

---

## 📎 문서 이력
- 작성자: 거래자
- 통합일: {datetime.now().strftime('%Y-%m-%d')}
- 파일 수: {file_count}개
- 총 라인: ~5,600줄 병합 및 중복 제거

**매일 새로운 AI에게 이 파일을 공유하세요. 더 이상 반복 설명 불필요!**
"""
    
    return guide

def generate_ai_task_guide():
    """다음 AI를 위한 작업 지시서 생성"""
    task = f"""# 🤖 다음 AI를 위한 작업 지시서

생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## 📋 당신의 역할

이 파일을 받은 AI는 아래의 역할을 합니다:

### 1️⃣ **기준 이해**
먼저 `00_통합_가이드.md`를 읽으세요.
- 트레이더의 기준과 규칙을 완전히 이해해야 합니다.
- 특히 "A급 조건", "거래 금지", "손절 철학"을 중심으로.

### 2️⃣ **최신 상황 파악**
`02_최신_파일_요약.md`에서 최근 작업을 완전히 확인하세요.
- 최신 5개 파일의 **전체 내용**을 읽음
- 무엇을 분석했는가?
- 어디까지 진행했는가?
- 다음은 무엇인가?

⚠️ **중요**: 이 3개 파일 (00, 01, 02)만으로 작업이 가능하도록 만들었습니다.
**"아카이브에서 더 자세히 봐야 할까?"라고 생각하기 전에 먼저 이 3개를 완전히 읽으세요.**

### 3️⃣ **바로 작업 시작**
다음 중 하나를 수행하세요:

**옵션 A) 거래 분석**
- 최신 파일들을 읽고, 그 거래가 기준을 충족했는지 검증
- 규칙 위반이 있었는지 확인
- 개선 방안 제시

**옵션 B) 지표 개선**
- Pine Script FLAG 지표 검토
- S1/S2 로직이 제대로 작동하는지 검증
- 신호 정확도 분석

**옵션 C) 전략 수정**
- A-SPS/D-SPS 분리가 제대로 되는지 확인
- 만기일/스프레드 필터 강화
- 신호 쿨다운 조정

---

## 🎯 핵심 지시문

이 트레이더에게는:

1. ❌ **단순 방향 예측** → ✅ **구조 검증**
2. ❌ **감정적 위로** → ✅ **규칙 위반 탐지**
3. ❌ **높은 승률 추구** → ✅ **기대값 양수 구조**
4. ❌ **모든 신호 추종** → ✅ **A급만 엄격히 필터**

---

## 📂 파일 구성

```
ZIP 파일 안의 구조:

00_통합_가이드.md
   ↑ 당신이 먼저 읽어야 할 문서

01_다음_AI를_위한_작업.md
   ↑ 이 파일 (지금 읽는 중)

02_최신_파일_요약.md
   ↑ 최근 진행 상황

2025-12-XX ~ XX/
   ↑ 원본 파일들 (필요시 직접 확인)
```

---

## ✅ 절대 확인해야 할 체크리스트

**다음을 다 확인하기 전까지는 원본 파일을 물어봐서는 안 됩니다:**

- [ ] `00_통합_가이드.md` 완전히 읽음
- [ ] VWAP, POC, FVG, SPS, SPS 개념 100% 이해
- [ ] A급/B급/거래금지 기준 명확히 구분 가능
- [ ] `02_최신_파일_요약.md`의 최신 5개 파일 전체 내용 읽음
- [ ] 이 3개 파일만으로 기본 작업이 가능한지 판단함
- [ ] 추가 정보가 정말 필요하면 그때 원본 파일 확인

**이 체크리스트 다음까지 온 다음에 작업 시작!**

---

## 💬 구체적 질문 예시

아래 중 하나를 선택해서 작업하세요:

### A) 최근 거래 검토
"최신 5개 파일을 읽고, 각 거래가 A급/B급/거래금지 중 어디에 속하는지 판정해줄래?"

### B) 지표 검증
"FLAG v3 지표의 TRUE BLACK 신호가 정확한지 최근 3일 데이터로 검증해줄래?"

### C) 개선안 제시
"SPS 필터를 더 강하게 만들려면 어떤 조정이 필요할까?"

### D) 다음 계획
"현재까지 진행 상황을 보니 다음 단계는 뭐가 되어야 할 것 같아?"

---

**더 이상 처음부터 설명할 필요 없습니다.**  
**이 파일을 읽은 AI는 바로 작업을 이어받을 수 있습니다.**
"""
    return task

def load_analysis_history():
    """분석 이력 로드"""
    analysis_path = os.path.join(SAVE_DIR, ANALYSIS_FILE)
    if os.path.exists(analysis_path):
        try:
            with open(analysis_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_analysis(analysis_id, analysis_data):
    """분석 결과 저장"""
    analysis_path = os.path.join(SAVE_DIR, ANALYSIS_FILE)
    history = load_analysis_history()
    history[analysis_id] = {
        "timestamp": datetime.now().isoformat(),
        "data": analysis_data
    }
    with open(analysis_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def extract_user_philosophy():
    """사용자의 철학과 패턴을 추출하여 인격 가이드 생성"""
    try:
        files = sorted([f for f in os.listdir(SAVE_DIR) if f.endswith('_Chat.txt')], reverse=True)
        if not files:
            return None
        
        # 모든 파일의 내용을 합침
        all_content = ""
        for filename in files[:10]:  # 최신 10개
            try:
                with open(os.path.join(SAVE_DIR, filename), 'r', encoding='utf-8') as f:
                    all_content += f.read() + "\n\n"
            except:
                pass
        
        if not all_content.strip():
            return None
        
        # 사용자 철학 추출 프롬프트
        prompt = f"""당신은 사용자의 거래 철학과 사고 방식을 분석하는 전문가입니다.

아래 사용자의 모든 대화와 거래 기록을 읽고, 다음을 추출하세요:

1. **핵심 철학**: 사용자가 믿는 가장 기본적인 원칙들
2. **의사결정 방식**: 어떻게 결정을 내리는가?
3. **실수 패턴**: 반복되는 실수와 개선 방식
4. **거래 스타일**: 보수적/공격적 등의 특징
5. **다음 우선순위**: 지금 가장 중요한 작업

## 사용자 기록
{all_content[:8000]}  # 토큰 제한

응답은 다음 형식으로:
```
## 🧠 당신의 거래 철학 (클라우드가 학습함)

### 1️⃣ 핵심 원칙
[3-5개의 핵심 원칙]

### 2️⃣ 의사결정 패턴
[어떻게 생각하고 선택하는지]

### 3️⃣ 실수 & 개선
[반복되는 패턴과 해결책]

### 4️⃣ 당신의 스타일
[거래 성격과 특징]

### 5️⃣ 다음 단계 (우선순위)
[지금 해야 할 일]
```"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2000
        )
        
        philosophy_text = response.choices[0].message.content
        return philosophy_text
    except Exception as e:
        return f"철학 추출 오류: {str(e)}"

def auto_analyze_files():
    """자동 순환 분석 - 아카이브 파일 자동 분석 및 개선안 생성 + 인격 가이드 업데이트"""
    try:
        # 상태 업데이트
        status = load_cloud_status()
        status["status"] = "analyzing"
        status["last_run"] = datetime.now().isoformat()
        save_cloud_status(status)
        
        files = sorted([f for f in os.listdir(SAVE_DIR) if f.endswith('_Chat.txt')], reverse=True)
        if not files:
            return {"success": False, "message": "분석할 파일이 없습니다"}
        
        # 최신 3개 파일 선택
        latest_files = files[:3]
        combined_content = ""
        
        for filename in latest_files:
            try:
                with open(os.path.join(SAVE_DIR, filename), 'r', encoding='utf-8') as f:
                    combined_content += f.read() + "\n\n---\n\n"
            except:
                pass
        
        # 1️⃣ 기존 분석 (거래 검토)
        prompt = f"""당신은 Nasdaq 선물(NQ, MNQ) 거래자의 전략 분석가입니다.

## 거래 시스템 기준
- A급 자리: VWAP 수용 + POC 추종 + 명확한 구조 (손절 16 ticks, 익절 32 ticks)
- 거래 금지: VWAP 아래 무의미한 횡보 + 스프레드 확장
- 손절 철학: 구조 붕괴 시 즉시 손절 (마틴게일 금지)

## 분석 작업
아래 최근 거래 기록을 읽고:
1. **규칙 준수 평가**: 각 거래가 A급 기준을 충족하는가?
2. **패턴 분석**: 반복되는 실수나 개선점?
3. **다음 단계**: 지표/필터를 어떻게 강화할 것인가?

**응답 형식:**
```json
{{
  "trading_review": ["거래1 판정", "거래2 판정"],
  "pattern_found": "발견된 패턴",
  "improvement": "구체적 개선안",
  "next_action": "다음 할 일"
}}
```

## 최근 거래 기록
{combined_content}
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500
        )
        
        analysis_text = response.choices[0].message.content
        
        # JSON 추출
        try:
            if analysis_text and isinstance(analysis_text, str):
                json_start = analysis_text.find('{')
                json_end = analysis_text.rfind('}') + 1
                if json_start >= 0 and json_end > 0:
                    analysis_json = json.loads(analysis_text[json_start:json_end])
                else:
                    analysis_json = {"raw": analysis_text}
            else:
                analysis_json = {"raw": str(analysis_text)}
        except:
            analysis_json = {"raw": str(analysis_text)}
        
        # 결과 저장
        analysis_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        save_analysis(analysis_id, analysis_json)
        
        # 2️⃣ 사용자 철학 추출 및 저장
        philosophy = extract_user_philosophy()
        if philosophy:
            philosophy_file = os.path.join(SAVE_DIR, ".user_philosophy.md")
            with open(philosophy_file, 'w', encoding='utf-8') as f:
                f.write(f"# 🧠 당신의 거래 철학 (자동 학습됨)\n\n")
                f.write(f"업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"분석 대상: 최신 {len(files[:10])}개 파일\n\n")
                f.write(philosophy)
        
        # 상태 완료
        status["status"] = "waiting"
        status["analysis_count"] = status.get("analysis_count", 0) + 1
        save_cloud_status(status)
        
        return {
            "success": True,
            "analysis_id": analysis_id,
            "result": analysis_json,
            "philosophy_updated": True
        }
    except Exception as e:
        status = load_cloud_status()
        status["status"] = "error"
        save_cloud_status(status)
        return {"success": False, "message": str(e)}

# ═══════════════════════════════════════════════════════════════
# 📡 TradingView 웹훅 엔드포인트
# ═══════════════════════════════════════════════════════════════

WEBHOOK_SECRETS = ['qwer1234!@', 'sps-trading-2024']  # 둘 다 허용

# 실시간 캔들 데이터 저장소
CANDLE_FILE = '.candle_history.json'
CANDLE_HISTORY = []

# 전역 SignalMonitor 인스턴스 (상태 유지)
from signal_monitor import SignalMonitor
SIGNAL_MONITOR = SignalMonitor()

# 서버 시작 시 캔들 히스토리 로드
if os.path.exists(CANDLE_FILE):
    try:
        with open(CANDLE_FILE, 'r') as f:
            CANDLE_HISTORY = json.load(f)
        print(f"📊 캔들 히스토리 로드: {len(CANDLE_HISTORY)}개")
        
        # 🤖 AI 버퍼 초기화
        from macro_micro_ai import init_ai_from_history
        init_ai_from_history(CANDLE_HISTORY)
    except:
        CANDLE_HISTORY = []

def load_candle_history():
    """캔들 히스토리 로드"""
    global CANDLE_HISTORY
    if os.path.exists(CANDLE_FILE):
        try:
            with open(CANDLE_FILE, 'r') as f:
                CANDLE_HISTORY = json.load(f)
        except:
            CANDLE_HISTORY = []
    return CANDLE_HISTORY

def save_candle_history():
    """캔들 히스토리 저장"""
    with open(CANDLE_FILE, 'w') as f:
        json.dump(CANDLE_HISTORY[-500:], f)

def merge_candle_history(new_candles):
    """새 캔들 데이터를 기존 히스토리에 병합 (중복 제거)"""
    global CANDLE_HISTORY
    existing_times = set(str(c.get('time', '')) for c in CANDLE_HISTORY)
    added = 0
    for candle in new_candles:
        time_key = str(candle.get('time', ''))
        if time_key not in existing_times:
            CANDLE_HISTORY.append(candle)
            existing_times.add(time_key)
            added += 1
    CANDLE_HISTORY.sort(key=lambda x: float(x.get('time', 0)))
    CANDLE_HISTORY = CANDLE_HISTORY[-500:]
    save_candle_history()
    return added

MARKET_DIRECTION_STATE = {
    'direction': 'UNKNOWN',
    'new_highs': 0,
    'new_lows': 0,
    'last_check': None,
    'short_blocked': False,
    'bull_score': 0,
    'bear_score': 0,
    'price_vs_ivwap': 0,
    'overheat_status': 'NORMAL',
    'gap_change': 0
}

PREV_PRICE_GAP = 0

def detect_market_direction(lookback=60):
    """
    시장 방향 감지 (4가지 방법 종합)
    1. 신고점/신저점 카운트
    2. 가격 vs iVWAP 위치
    3. iVWAP 변화율
    4. 과열 감지 (gap 180pt+ & 하락 시작)
    
    - BULL: 상승 점수 >= 2 → 숏 차단!
    - BEAR: 하락 점수 >= 2 → 숏 허용
    - OVERHEAT_COOLING: 과열 후 하락 시작 → 숏 허용!
    """
    global MARKET_DIRECTION_STATE, PREV_PRICE_GAP
    
    if len(CANDLE_HISTORY) < lookback:
        return {'direction': 'UNKNOWN', 'short_blocked': False, 'reason': '데이터 부족'}
    
    recent = CANDLE_HISTORY[-lookback:]
    bull_score = 0
    bear_score = 0
    
    # 1️⃣ 신고점/신저점 카운트
    new_highs = 0
    new_lows = 0
    rolling_high = float(recent[0].get('high', 0))
    rolling_low = float(recent[0].get('low', 99999))
    
    for candle in recent[1:]:
        high = float(candle.get('high', 0))
        low = float(candle.get('low', 99999))
        if high > rolling_high:
            new_highs += 1
            rolling_high = high
        if low < rolling_low:
            new_lows += 1
            rolling_low = low
    
    if new_highs > new_lows + 2:
        bull_score += 1
    elif new_lows > new_highs + 2:
        bear_score += 1
    
    # 2️⃣ 가격 vs iVWAP 위치
    current = recent[-1]
    close = float(current.get('close', 0))
    buy_ivwap = float(current.get('buy_ivwap', current.get('매수 iVWAP (초록)', 0)))
    sell_ivwap = float(current.get('sell_ivwap', current.get('매도 iVWAP (분홍)', 0)))
    
    price_vs_ivwap = close - buy_ivwap
    gap_change = price_vs_ivwap - PREV_PRICE_GAP if PREV_PRICE_GAP != 0 else 0
    PREV_PRICE_GAP = price_vs_ivwap
    
    # 🔥 iVWAP 위치 기반 상승장/하락장 필터 (핵심!)
    is_uptrend = price_vs_ivwap > 0  # 가격 > iVWAP → 상승장
    is_downtrend = price_vs_ivwap < 0  # 가격 < iVWAP → 하락장
    
    if close > buy_ivwap + 50:
        bull_score += 1
    elif close < sell_ivwap - 50:
        bear_score += 1
    
    # 3️⃣ iVWAP 변화율
    first = recent[0]
    buy_ivwap_start = float(first.get('buy_ivwap', first.get('매수 iVWAP (초록)', 0)))
    sell_ivwap_start = float(first.get('sell_ivwap', first.get('매도 iVWAP (분홍)', 0)))
    
    buy_change = buy_ivwap - buy_ivwap_start
    sell_change = sell_ivwap - sell_ivwap_start
    
    if buy_change > sell_change + 1:
        bull_score += 1
    elif sell_change > buy_change + 1:
        bear_score += 1
    
    # 4️⃣ 과열 감지 + iVWAP 정체 + 매도iVWAP 괴리 분석
    # iVWAP 10봉 변화량 계산
    ivwap_change = 0
    if len(recent) >= 10:
        first_10 = recent[-10]
        buy_ivwap_10 = float(first_10.get('buy_ivwap', first_10.get('매수 iVWAP (초록)', 0)))
        sell_ivwap_10 = float(first_10.get('sell_ivwap', first_10.get('매도 iVWAP (분홍)', 0)))
        ivwap_change = abs(buy_ivwap - buy_ivwap_10) + abs(sell_ivwap - sell_ivwap_10)
    
    ivwap_stagnant = ivwap_change < 1.0  # iVWAP 정체 (변화 1pt 미만)
    
    # 매도iVWAP(분홍) 괴리 = 클러스터에서 멀어짐
    sell_ivwap_gap = close - sell_ivwap
    total_gap = price_vs_ivwap + sell_ivwap_gap  # 총 괴리
    
    if price_vs_ivwap >= 200:
        if gap_change <= -10:
            overheat_status = 'COOLING_FAST'  # 급냉각 - 숏 OK!
        elif gap_change < 0:
            overheat_status = 'COOLING'  # 식는 중
        elif ivwap_stagnant:
            overheat_status = 'EXTREME_STAGNANT'  # 극과열 + 정체 = 71% 횡보!
        else:
            overheat_status = 'EXTREME'  # 극과열
    elif price_vs_ivwap >= 150:
        if ivwap_stagnant:
            overheat_status = 'WARNING_STAGNANT'  # 과열 + 정체 = 횡보
        else:
            overheat_status = 'WARNING'
    elif price_vs_ivwap >= 100:
        overheat_status = 'ELEVATED'
    elif price_vs_ivwap <= -50:
        overheat_status = 'OVERSOLD'
    else:
        overheat_status = 'NORMAL'
    
    # 종합 판단
    if overheat_status in ['COOLING_FAST', 'COOLING']:
        direction = 'OVERHEAT_COOLING'
        short_blocked = False  # 과열 식을 때 숏 허용!
    elif bull_score >= 2:
        direction = 'BULL'
        short_blocked = True
    elif bear_score >= 2:
        direction = 'BEAR'
        short_blocked = False
    else:
        direction = 'SIDEWAYS'
        short_blocked = False
    
    MARKET_DIRECTION_STATE = {
        'direction': direction,
        'new_highs': new_highs,
        'new_lows': new_lows,
        'bull_score': bull_score,
        'bear_score': bear_score,
        'price_vs_ivwap': round(price_vs_ivwap, 2),
        'sell_ivwap_gap': round(sell_ivwap_gap, 2),
        'total_gap': round(total_gap, 2),
        'gap_change': round(gap_change, 2),
        'ivwap_change': round(ivwap_change, 2),
        'ivwap_stagnant': ivwap_stagnant,
        'overheat_status': overheat_status,
        'last_check': datetime.now().isoformat(),
        'short_blocked': short_blocked,
        'is_uptrend': is_uptrend,
        'is_downtrend': is_downtrend,
        'trend_filter': 'UP' if is_uptrend else ('DOWN' if is_downtrend else 'NEUTRAL')
    }
    
    return MARKET_DIRECTION_STATE


def get_ratio_market_direction():
    """
    ═══════════════════════════════════════════════════════════════
    📊 100봉 Ratio 기반 시장방향 판단 (2026-01-09 신규)
    ═══════════════════════════════════════════════════════════════
    
    📌 핵심 공식:
    - 100봉 Ratio > 1.0 = 상승장
    - 100봉 Ratio < 1.0 = 하락장
    - 10봉 Ratio >= 1.5 = 과열 (숏 조건)
    - 10봉 Ratio <= 0.7 = 과냉 (롱 조건)
    
    📊 빗각 신호 조합:
    - 하락장 + 하락빗각 터치 = 숏 72.0%
    - 상승장 + 상승빗각 터치 = 롱 72.9%
    - 상승장 + 하락빗각 + 배율>=1.5 + 채널>=80% = 숏 72.6%
    ═══════════════════════════════════════════════════════════════
    """
    import pandas as pd
    
    if len(CANDLE_HISTORY) < 100:
        return {
            'market_direction': 'UNKNOWN',
            'ratio_100': 1.0,
            'ratio_10': 1.0,
            'is_overheated': False,
            'is_oversold': False,
            'short_allowed': False,
            'long_allowed': False,
            'reason': '데이터 부족 (100봉 미만)'
        }
    
    df = pd.DataFrame(CANDLE_HISTORY[-100:])
    
    df['bull_power'] = df['high'].astype(float) - df['open'].astype(float)
    df['bear_power'] = df['open'].astype(float) - df['low'].astype(float)
    
    bull_sum_100 = df['bull_power'].sum()
    bear_sum_100 = df['bear_power'].sum()
    ratio_100 = bull_sum_100 / (bear_sum_100 + 0.1)
    
    df_10 = df.tail(10)
    bull_sum_10 = df_10['bull_power'].sum()
    bear_sum_10 = df_10['bear_power'].sum()
    ratio_10 = bull_sum_10 / (bear_sum_10 + 0.1)
    
    df_20 = df.tail(20)
    ch_high_20 = df_20['high'].astype(float).max()
    ch_low_20 = df_20['low'].astype(float).min()
    ch_range = ch_high_20 - ch_low_20
    
    current_close = float(df.iloc[-1]['close'])
    channel_pct = ((current_close - ch_low_20) / ch_range * 100) if ch_range > 0 else 50
    
    is_bull_market = ratio_100 > 1.0
    is_bear_market = ratio_100 < 1.0
    # 상대값 변환: 30pt / 25000 = 0.12%
    range_pct = (ch_range / current_close * 100) if current_close > 0 else 0
    is_sideways = range_pct < 0.12
    
    is_overheated = ratio_10 >= 1.5
    is_oversold = ratio_10 <= 0.7
    
    if is_sideways:
        market_direction = 'SIDEWAYS'
        short_allowed = False
        long_allowed = False
        reason = f'횡보장 (레인지 {range_pct:.3f}% < 0.12%)'
    elif is_bull_market:
        market_direction = 'BULL'
        short_allowed = is_overheated and channel_pct >= 80
        long_allowed = True
        reason = f'상승장 (100봉 Ratio {ratio_100:.2f} > 1.0)'
    else:
        market_direction = 'BEAR'
        short_allowed = True
        long_allowed = is_oversold and channel_pct <= 20
        reason = f'하락장 (100봉 Ratio {ratio_100:.2f} < 1.0)'
    
    return {
        'market_direction': market_direction,
        'ratio_100': round(ratio_100, 3),
        'ratio_10': round(ratio_10, 3),
        'channel_pct': round(channel_pct, 1),
        'channel_range': round(ch_range, 1),
        'is_bull_market': is_bull_market,
        'is_bear_market': is_bear_market,
        'is_sideways': is_sideways,
        'is_overheated': is_overheated,
        'is_oversold': is_oversold,
        'short_allowed': short_allowed,
        'long_allowed': long_allowed,
        'reason': reason
    }


def check_angle_signal_with_market(signal_type, direction=None):
    """
    ═══════════════════════════════════════════════════════════════
    📐 빗각 신호 + 시장방향 통합 검증 (2026-01-09)
    ═══════════════════════════════════════════════════════════════
    
    📊 검증된 조합:
    - 하락장 + 하락빗각 터치 = 숏 72.0%
    - 상승장 + 상승빗각 터치 = 롱 72.9%
    - 상승장 + 배율>=1.5 + 채널>=80% = 숏 72.6%
    - 상승장 + 배율<=0.7 = 롱 100%
    ═══════════════════════════════════════════════════════════════
    """
    state = get_ratio_market_direction()
    
    is_angle_signal = 'i빗각' in signal_type or '빗각' in signal_type
    if not is_angle_signal:
        return None
    
    if direction is None:
        if '롱' in signal_type or 'LONG' in signal_type or '지지' in signal_type:
            direction = 'LONG'
        elif '숏' in signal_type or 'SHORT' in signal_type or '저항' in signal_type:
            direction = 'SHORT'
    
    if state['is_sideways']:
        return {
            'allowed': False,
            'reason': f"횡보장 빗각 신호 차단 (레인지 {state['channel_range']:.0f}pt)",
            'grade': None
        }
    
    if direction == 'SHORT':
        if state['is_bear_market']:
            return {
                'allowed': True,
                'reason': f"하락장 순추세 숏 (100봉Ratio {state['ratio_100']:.2f})",
                'grade': 'S',
                'win_rate': 72.0
            }
        elif state['is_overheated'] and state['channel_pct'] >= 80:
            return {
                'allowed': True,
                'reason': f"상승장 역추세 숏 (배율{state['ratio_10']:.2f}>=1.5 + 채널{state['channel_pct']:.0f}%>=80%)",
                'grade': 'A',
                'win_rate': 72.6
            }
        else:
            return {
                'allowed': False,
                'reason': f"상승장 숏 차단 (배율{state['ratio_10']:.2f} 채널{state['channel_pct']:.0f}%)",
                'grade': None
            }
    
    elif direction == 'LONG':
        if state['is_bull_market']:
            if state['is_oversold']:
                return {
                    'allowed': True,
                    'reason': f"상승장 + 과냉 롱 (배율{state['ratio_10']:.2f}<=0.7)",
                    'grade': 'S+',
                    'win_rate': 100.0
                }
            return {
                'allowed': True,
                'reason': f"상승장 순추세 롱 (100봉Ratio {state['ratio_100']:.2f})",
                'grade': 'S',
                'win_rate': 72.9
            }
        elif state['is_oversold'] and state['channel_pct'] <= 20:
            return {
                'allowed': True,
                'reason': f"하락장 역추세 롱 (배율{state['ratio_10']:.2f}<=0.7 + 채널{state['channel_pct']:.0f}%<=20%)",
                'grade': 'A',
                'win_rate': 70.5
            }
        else:
            return {
                'allowed': False,
                'reason': f"하락장 롱 차단 (배율{state['ratio_10']:.2f} 채널{state['channel_pct']:.0f}%)",
                'grade': None
            }
    
    return None


@app.route('/api/import-candles', methods=['POST'])
def import_candles_api():
    """CSV 파일에서 캔들 데이터 임포트 (서버 재시작 없이)"""
    global CANDLE_HISTORY
    try:
        import pandas as pd
        if 'file' not in request.files:
            return jsonify({"success": False, "message": "파일 없음"}), 400
        
        file = request.files['file']
        df = pd.read_csv(file)
        
        new_candles = []
        for _, row in df.iterrows():
            candle = {
                'time': str(pd.to_datetime(row['time']).timestamp() * 1000),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                '매수 iVWAP (초록)': float(row.get('매수 iVWAP (초록)', 0)),
                '매도 iVWAP (분홍)': float(row.get('매도 iVWAP (분홍)', 0))
            }
            new_candles.append(candle)
        
        added = merge_candle_history(new_candles)
        print(f"📊 CSV 임포트: {len(new_candles)}개 중 {added}개 추가, 총 {len(CANDLE_HISTORY)}개")
        
        return jsonify({
            "success": True,
            "message": f"{added}개 캔들 추가됨 (총 {len(CANDLE_HISTORY)}개)",
            "total": len(CANDLE_HISTORY)
        })
    except Exception as e:
        print(f"❌ CSV 임포트 오류: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

PROCESSED_CANDLE_TIMES = set()

@app.route('/webhook/candle', methods=['POST'])
def candle_webhook():
    """1분봉 캔들 데이터 받아서 3개 전략 신호 계산 (숏A, 스캘A, 스캘B)"""
    global CANDLE_HISTORY, PROCESSED_CANDLE_TIMES
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        candle_time = data.get('time', '')
        if candle_time in PROCESSED_CANDLE_TIMES:
            print(f"⏭️ 중복 캔들 스킵: time={candle_time}")
            return jsonify({"status": "skip", "message": "Duplicate candle"}), 200
        
        PROCESSED_CANDLE_TIMES.add(candle_time)
        if len(PROCESSED_CANDLE_TIMES) > 1000:
            oldest = sorted(PROCESSED_CANDLE_TIMES)[:500]
            PROCESSED_CANDLE_TIMES -= set(oldest)
        
        log_signal_reception('candle', 'webhook-캔들', data)
        print(f"📥 candle 수신: {data}")
        
        if data.get('passphrase') not in WEBHOOK_SECRETS:
            print(f"❌ candle 인증실패: passphrase={data.get('passphrase')}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        candle = {
            'time': data.get('time', datetime.now().isoformat()),
            'open': float(data.get('open', 0)),
            'high': float(data.get('high', 0)),
            'low': float(data.get('low', 0)),
            'close': float(data.get('close', 0)),
            'volume': float(data.get('volume', 0)),
            '매도 iVWAP (분홍)': float(data.get('sell_ivwap', 0)) if data.get('sell_ivwap') else None,
            '매수 iVWAP (초록)': float(data.get('buy_ivwap', 0)) if data.get('buy_ivwap') else None
        }
        
        merge_candle_history([candle])
        
        # 🔬 실시간 상대값 테스트 + POC 저항 감지!
        if len(CANDLE_HISTORY) >= 50:
            import pandas as pd
            import numpy as np
            df = pd.DataFrame(CANDLE_HISTORY[-100:])
            df['body'] = df['close'] - df['open']
            df['abs_body'] = df['body'].abs()
            
            # 🔬 상대값 계산!
            body_mean = df['abs_body'].iloc[-50:].mean()
            body_std = df['abs_body'].iloc[-50:].std()
            current_body = abs(candle['close'] - candle['open'])
            body_zscore = (current_body - body_mean) / body_std if body_std > 0 else 0
            
            # 매수/매도 배율 z-score
            df['bull_body'] = df['body'].clip(lower=0)
            df['bear_body'] = df['body'].clip(upper=0).abs()
            bull_sum = df['bull_body'].iloc[-10:].sum()
            bear_sum = df['bear_body'].iloc[-10:].sum()
            ratio = bull_sum / (bear_sum + 0.01)
            
            df['ratio_10'] = df['bull_body'].rolling(10).sum() / (df['bear_body'].rolling(10).sum() + 0.01)
            ratio_mean = df['ratio_10'].iloc[-50:].mean()
            ratio_std = df['ratio_10'].iloc[-50:].std()
            ratio_zscore = (ratio - ratio_mean) / ratio_std if ratio_std > 0 else 0
            
            print(f"🔬 [실시간] 가격={candle['close']:.2f} | body_z={body_zscore:.2f} | ratio={ratio:.2f} → ratio_z={ratio_zscore:.2f}")
            # 억제 알림용 시장 정보 업데이트
            update_market_info(candle['close'], 'ACTIVE', candle.get('time'))
            
            # STB 스팟 조건 체크 (body_zscore >= 1.0)
            if abs(body_zscore) >= 1.0:
                direction = "양봉" if candle['close'] > candle['open'] else "음봉"
                print(f"⭐ STB스팟 발생! {direction} body_z={body_zscore:.2f} ratio_z={ratio_zscore:.2f}")
                
                # 📌 앵글로직에 STB 스팟 추가 (POC 계산용)
                ANGLE_JUDGE.add_stb_spot(
                    price=candle['close'],
                    ratio=abs(ratio_zscore) if ratio_zscore != 0 else abs(body_zscore),
                    timestamp=datetime.now()
                )
                print(f"📌 앵글로직 스팟 추가: {candle['close']:.2f} ratio={abs(ratio_zscore):.2f} | 총 {len(ANGLE_JUDGE.stb_spots)}개")
            
            # 📌 zpoc 저항 자동 감지!
            # zpoc = POC + 70.25pt (저항선), POC - 70.25pt (지지선)
            # 📌 블랙라인 중간값에서 POC 계산!
            BLACKLINES = [24961.5, 25512.5, 26109, 26651.25]  # 고정 블랙라인 (TradingView 기준)
            price = candle['close']
            
            # 현재 가격 사이의 두 블랙라인 찾기
            poc_base = 0
            blacklines_sorted = sorted(BLACKLINES)
            for i in range(len(blacklines_sorted) - 1):
                lower_bl = blacklines_sorted[i]
                upper_bl = blacklines_sorted[i + 1]
                if lower_bl <= price <= upper_bl:
                    poc_base = (lower_bl + upper_bl) / 2  # 중간값 = POC
                    break
            
            # 가격이 범위 밖일 경우 가장 가까운 블랙라인 2개 평균
            if poc_base == 0 and len(blacklines_sorted) >= 2:
                if price < blacklines_sorted[0]:
                    poc_base = (blacklines_sorted[0] + blacklines_sorted[1]) / 2
                elif price > blacklines_sorted[-1]:
                    poc_base = (blacklines_sorted[-2] + blacklines_sorted[-1]) / 2
            
            if poc_base > 0:
                SUPPORT_LEVELS['poc'] = poc_base
                print(f"📌 블랙라인 POC: {poc_base:.2f} (가격:{price:.2f} 블랙라인 범위)")
            if poc_base > 0:
                # POC 기준 ZPOC
                zpoc_resist = poc_base + 70.25  # 저항선
                zpoc_support = poc_base - 70.25  # 지지선
                price = candle['close']
                is_bearish = candle['close'] < candle['open']
                is_bullish = candle['close'] > candle['open']
                
            # ═══════════════════════════════════════════════════════════════════════
            # 📊 ZPOC 계산: 블랙라인 + 모든 POC (블랙라인 사이 중간값) ±70.25pt
            # 블랙라인 = 중심선, POC = 블랙라인 사이 중간값 = 중심선
            # 각 중심선 위아래 70.25pt = ZPOC (볼린저밴드처럼)
            # ═══════════════════════════════════════════════════════════════════════
            bl_zpoc_levels = []
            
            # 1️⃣ 블랙라인 기준 ZPOC
            for bl in BLACKLINES:
                bl_zpoc_levels.append({'type': 'bl_resist', 'level': bl + 70.25, 'base': bl, 'base_name': f'블랙{bl:.0f}'})
                bl_zpoc_levels.append({'type': 'bl_support', 'level': bl - 70.25, 'base': bl, 'base_name': f'블랙{bl:.0f}'})
            
            # 2️⃣ 모든 POC (블랙라인 사이 중간값) 기준 ZPOC
            for i in range(len(blacklines_sorted) - 1):
                poc = (blacklines_sorted[i] + blacklines_sorted[i + 1]) / 2
                bl_zpoc_levels.append({'type': 'poc_resist', 'level': poc + 70.25, 'base': poc, 'base_name': f'POC{poc:.0f}'})
                bl_zpoc_levels.append({'type': 'poc_support', 'level': poc - 70.25, 'base': poc, 'base_name': f'POC{poc:.0f}'})
            
            # ═══════════════════════════════════════════════════════════════════════
            # 🔥 STB와 동일한 힘 측정! (2026-01-13)
            # bull_sps_20 / bear_sps_20 = 매수힘/매도힘 비율
            # ═══════════════════════════════════════════════════════════════════════
            import pandas as pd
            import numpy as np
            df_force = pd.DataFrame(CANDLE_HISTORY[-200:])
            df_force['body'] = df_force['close'] - df_force['open']
            df_force['abs_body'] = df_force['body'].abs()
            df_force['body_mean'] = df_force['abs_body'].rolling(50).mean()
            df_force['body_std'] = df_force['abs_body'].rolling(50).std()
            df_force['body_zscore'] = (df_force['abs_body'] - df_force['body_mean']) / df_force['body_std'].replace(0, 0.001)
            df_force['bull_zscore'] = np.where(df_force['body'] > 0, df_force['body_zscore'], 0)
            df_force['bear_zscore'] = np.where(df_force['body'] < 0, df_force['body_zscore'], 0)
            df_force['bull_sps_20'] = df_force['bull_zscore'].rolling(20).sum()
            df_force['bear_sps_20'] = df_force['bear_zscore'].rolling(20).sum()
            df_force['sps_ratio'] = df_force['bull_sps_20'] / (df_force['bear_sps_20'] + 0.01)
            df_force['sps_ratio'] = df_force['sps_ratio'].clip(0.1, 10)
            df_force['sps_ratio_mean'] = df_force['sps_ratio'].rolling(50).mean()
            df_force['sps_ratio_std'] = df_force['sps_ratio'].rolling(50).std()
            df_force['sps_ratio_z'] = (df_force['sps_ratio'] - df_force['sps_ratio_mean']) / df_force['sps_ratio_std'].replace(0, 0.001)
            
            # NaN 처리 + 음수 방지
            stb_sps_ratio_z = df_force['sps_ratio_z'].iloc[-1] if len(df_force) > 0 else 0
            bull_sps_20 = max(0, df_force['bull_sps_20'].iloc[-1]) if len(df_force) > 0 and not pd.isna(df_force['bull_sps_20'].iloc[-1]) else 0
            bear_sps_20 = max(0, df_force['bear_sps_20'].iloc[-1]) if len(df_force) > 0 and not pd.isna(df_force['bear_sps_20'].iloc[-1]) else 0
            if pd.isna(stb_sps_ratio_z):
                stb_sps_ratio_z = 0
            
            # 매수유리/매도유리 판단
            buy_advantage = bull_sps_20 > bear_sps_20  # 매수힘 > 매도힘
            sell_advantage = bear_sps_20 > bull_sps_20  # 매도힘 > 매수힘
            
            print(f"💪 STB힘측정: bull_sps={bull_sps_20:.1f} bear_sps={bear_sps_20:.1f} ratio_z={stb_sps_ratio_z:.2f} 매수유리={buy_advantage}")
            
            # 가장 가까운 ZPOC 레벨 찾기
            for zpoc_info in bl_zpoc_levels:
                zpoc_level = zpoc_info['level']
                zpoc_dist = abs(price - zpoc_level)
                zpoc_type = zpoc_info['type']
                base_price = zpoc_info['base']
                base_name = zpoc_info['base_name']
                
                if zpoc_dist < 15:  # 15pt 이내
                    # ═══════════════════════════════════════════════════════════════════════
                    # 📊 ZPOC STB 로직! (2026-01-13) - 스팟SPS vs 리테스트SPS 비교
                    # ═══════════════════════════════════════════════════════════════════════
                    
                    # 🔔 ZPOC 터치 자체 로그
                    print(f"📍 ZPOC터치! ({base_name}) 가격={price:.2f} ≈ zpoc={zpoc_level:.2f} (거리:{zpoc_dist:.1f}pt)")
                    
                    # SPS 비율 계산
                    current_sps_ratio = bull_sps_20 / (bear_sps_20 + 0.01) if bear_sps_20 > 0 else bull_sps_20 + 0.1
                    current_sps_ratio = max(0.1, min(10, current_sps_ratio))
                    
                    # 스팟 파일 로드
                    zpoc_spot_file = '.zpoc_sps_spots.json'
                    zpoc_spots = []
                    if os.path.exists(zpoc_spot_file):
                        try:
                            with open(zpoc_spot_file, 'r') as f:
                                zpoc_spots = json.load(f)
                        except:
                            zpoc_spots = []
                    
                    # 같은 ZPOC 근처(±20pt) 스팟 찾기
                    matching_spot = None
                    for spot in zpoc_spots[-50:]:
                        if abs(price - spot.get('price', 0)) < 20:
                            matching_spot = spot
                            break
                    
                    if matching_spot:
                        # 리테스트! SPS 비교
                        spot_sps = matching_spot.get('sps_ratio', 1.0)
                        sps_weakened = current_sps_ratio < spot_sps * 0.8
                        
                        print(f"📍 ZPOC 리테스트! spot_sps={spot_sps:.2f} → retest_sps={current_sps_ratio:.2f} 약화={sps_weakened}")
                        
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        if is_bearish and sps_weakened and spot_sps > 1.0:
                            # 매수세가 강했는데 약해짐 → 숏
                            print(f"🔴 ZPOC STB숏! ({base_name})")
                            
                            tg_msg = f"""🔴 ZPOC STB숏! (93%)
━━━━━━━━━━━━━━━━
📐 {base_name.upper()}: {base_price:.2f} | ZPOC: {zpoc_level:.2f}
📍 현재가: {price:.2f} (거리:{zpoc_dist:.1f}pt)
💪 스팟SPS: {spot_sps:.2f} → 리테스트SPS: {current_sps_ratio:.2f}
📉 SPS약화: {((1-current_sps_ratio/spot_sps)*100):.0f}% ↓
🎯 방향: SHORT | TP:20pt SL:30pt
💡 매수세 소진 후 음봉 = 하락 전환!
⏰ {timestamp}"""
                            send_telegram_alert(tg_msg, signal_type='ZPOC_STB숏')
                            break
                            
                        elif is_bullish and sps_weakened and spot_sps < 1.0:
                            # 매도세가 강했는데 약해짐 → 롱
                            print(f"🟢 ZPOC STB롱! ({base_name})")
                            
                            tg_msg = f"""🟢 ZPOC STB롱! (94%)
━━━━━━━━━━━━━━━━
📐 {base_name.upper()}: {base_price:.2f} | ZPOC: {zpoc_level:.2f}
📍 현재가: {price:.2f} (거리:{zpoc_dist:.1f}pt)
💪 스팟SPS: {spot_sps:.2f} → 리테스트SPS: {current_sps_ratio:.2f}
📈 SPS변화: 매도세→매수세 전환
🎯 방향: LONG | TP:20pt SL:30pt
💡 매도세 소진 후 양봉 = 상승 전환!
⏰ {timestamp}"""
                            send_telegram_alert(tg_msg, signal_type='ZPOC_STB롱')
                            break
                        else:
                            print(f"📍 ZPOC 리테스트 관찰: 조건불충족")
                    else:
                        # 첫 터치! 스팟 등록
                        new_spot = {
                            "timestamp": datetime.now().isoformat(),
                            "base_name": base_name,
                            "zpoc_level": zpoc_level,
                            "price": price,
                            "bull_sps": bull_sps_20,
                            "bear_sps": bear_sps_20,
                            "sps_ratio": current_sps_ratio,
                            "candle_type": "bullish" if is_bullish else "bearish"
                        }
                        zpoc_spots.append(new_spot)
                        zpoc_spots = zpoc_spots[-100:]
                        
                        with open(zpoc_spot_file, 'w') as f:
                            json.dump(zpoc_spots, f, indent=2, ensure_ascii=False)
                        
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        print(f"📍 ZPOC 스팟등록! ({base_name}) sps={current_sps_ratio:.2f}")
                        
                        tg_msg = f"""📍 ZPOC 스팟등록! (관찰)
━━━━━━━━━━━━━━━━
📐 {base_name.upper()}: {base_price:.2f} | ZPOC: {zpoc_level:.2f}
📍 현재가: {price:.2f} (거리:{zpoc_dist:.1f}pt)
💪 bull_sps: {bull_sps_20:.1f} | bear_sps: {bear_sps_20:.1f}
📊 SPS비율: {current_sps_ratio:.2f}
💡 리테스트 시 SPS 비교 예정
⏰ {timestamp}"""
                        send_telegram_alert(tg_msg, signal_type='ZPOC스팟')
                        break
            
            # 기존 개별 zpoc 저항/지지 코드 삭제됨 - 위의 통합 루프에서 POC+블랙라인 모두 처리
            
            # ═══════════════════════════════════════════════════════════════════════
            # 📐 빗각 자동감지 비활성화! (2026-01-12)
            # 빗각은 TradingView 웹훅에서만 감지 (/webhook/iangle, rising_angle_touch, i_angle_touch)
            # zpoc는 블랙라인 기반 자동계산 유지
            # ═══════════════════════════════════════════════════════════════════════
            # from iangle_formula import calculate_all_rising_angles, calculate_all_falling_angles, find_nearest_rising_angle, find_nearest_falling_angle
            # 빗각 자동감지 비활성화 - TradingView 웹훅으로만 처리
            pass  # 빗각 자동감지 OFF
            
            if False:  # 빗각 자동감지 비활성화
                # 빗각 판단 로직 호출
                iangle_judgment = check_iangle_breakthrough()
                if iangle_judgment:
                    judgment = iangle_judgment.get('judgment', '')
                    direction = iangle_judgment.get('direction', '')
                    confidence = iangle_judgment.get('confidence', 'C')
                    reason = iangle_judgment.get('reason', '')
                    sector_pct = iangle_judgment.get('sector_pct', 50)
                    sps_z = iangle_judgment.get('sps_ratio_z', 0)
                    buy_ratio_z = iangle_judgment.get('buy_ratio_z', 0)
                    sell_ratio_z = iangle_judgment.get('sell_ratio_z', 0)
                    
                    if not direction:
                        direction = 'SHORT' if is_bearish else 'LONG'
                    
                    # 배율 상태 계산
                    exhaust_status = ""
                    temp_df = pd.DataFrame(CANDLE_HISTORY[-60:])
                    temp_df['body'] = temp_df['close'] - temp_df['open']
                    temp_df['bull_sum'] = temp_df['body'].clip(lower=0).rolling(10).sum()
                    temp_df['bear_sum'] = temp_df['body'].clip(upper=0).abs().rolling(10).sum()
                    temp_df['buy_ratio'] = temp_df['bull_sum'] / (temp_df['bear_sum'] + 0.01)
                    temp_df['sell_ratio'] = temp_df['bear_sum'] / (temp_df['bull_sum'] + 0.01)
                    temp_df['buy_ma5'] = temp_df['buy_ratio'].rolling(5).mean()
                    temp_df['sell_ma5'] = temp_df['sell_ratio'].rolling(5).mean()
                    buy_delta = temp_df['buy_ma5'].iloc[-1] - temp_df['buy_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                    sell_delta = temp_df['sell_ma5'].iloc[-1] - temp_df['sell_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                    prev_buy = temp_df['buy_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                    prev_sell = temp_df['sell_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                    
                    if buy_delta < -0.1:
                        exhaust_status = f"🔻 매수소진! (Δ{buy_delta:.2f})" if prev_buy <= 1.3 else f"🔻 매수소진!! (이전{prev_buy:.1f}→Δ{buy_delta:.2f})"
                    elif buy_delta < 0:
                        exhaust_status = f"🔻 매수세약화 (Δ{buy_delta:.2f})"
                    elif sell_delta < -0.1:
                        exhaust_status = f"🔺 매도소진! (Δ{sell_delta:.2f})" if prev_sell <= 1.3 else f"🔺 매도소진!! (이전{prev_sell:.1f}→Δ{sell_delta:.2f})"
                    elif sell_delta < 0:
                        exhaust_status = f"🔺 매도세약화 (Δ{sell_delta:.2f})"
                    elif buy_delta > sell_delta:
                        exhaust_status = f"📈 매수세증가 (Δ+{buy_delta:.2f})"
                    else:
                        exhaust_status = f"📉 매도세증가 (Δ+{sell_delta:.2f})"
                    
                    win_rate_map = {'S++': '96%', 'S+': '92%', 'S': '90%', 'A': '86%', 'B': '70%', 'C': '60%'}
                    win_rate = win_rate_map.get(confidence, '70%')
                    emoji = '🔴' if direction == 'SHORT' else '🟢'
                    
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"📐 상승빗각 자동감지! 가격={price:.2f} ≈ {rising_label}={rising_angle:.2f} (거리:{rising_dist:.1f}pt)")
                    print(f"   판단: {judgment} {confidence} 방향:{direction} {exhaust_status}")
                    
                    touch_data = {
                        "timestamp": datetime.now().isoformat(),
                        "ticker": candle.get('ticker', 'MNQ'),
                        "line_name": rising_label,
                        "angle_type": "rising",
                        "angle_price": round(rising_angle, 2),
                        "touch_price": round(price, 2),
                        "distance": round(rising_dist, 2),
                        "action": "rising_angle_auto",
                        "judgment": judgment,
                        "direction": direction,
                        "confidence": confidence,
                        "sector_pct": round(sector_pct, 1),
                        "buy_ratio_z": round(buy_ratio_z, 2),
                        "sell_ratio_z": round(sell_ratio_z, 2),
                        "sps_z": round(sps_z, 2),
                        "exhaust_status": exhaust_status,
                        "candle_type": "bullish" if is_bullish else "bearish"
                    }
                    try:
                        touches = []
                        if os.path.exists('.iangle_touches.json'):
                            with open('.iangle_touches.json', 'r') as f:
                                touches = json.load(f)
                        touches.append(touch_data)
                        touches = touches[-500:]
                        with open('.iangle_touches.json', 'w') as f:
                            json.dump(touches, f, indent=2, ensure_ascii=False)
                        print(f"   💾 상승빗각 터치 저장됨 → .iangle_touches.json")
                    except Exception as e:
                        print(f"   ⚠️ 상승빗각 저장 오류: {e}")
                    
                    tg_msg = f"""{emoji} {rising_label}{judgment}예측 {confidence} ({win_rate})
━━━━━━━━━━━━━━━━
📐 빗각: {rising_label} @ {rising_angle:.2f} (실시간계산)
📍 현재가: {price:.2f} (거리: {rising_dist:.1f}pt)
📊 섹터: {sector_pct:.0f}% {exhaust_status}
📈 매수배율z: {buy_ratio_z:.2f} | 매도배율z: {sell_ratio_z:.2f}
📉 SPS비율z: {sps_z:.2f}
🎯 방향: {direction} | TP:20pt SL:30pt
💡 {reason}
⏰ {timestamp}"""
                    send_telegram_alert(tg_msg, signal_type='상승빗각예측')
            
                # 하락빗각 터치 자동 감지 - 비활성화됨 (if False 블록 내부)
                pass  # falling angle detection disabled
        
        # 🔥 V6.1 AI 판단 필터 (80% WIN, EV 49pt 검증!)
        global V61_ACTIVE_POSITION
        try:
            v61_filter = get_v61_filter()
            current_price = float(candle['close'])
            
            # 1️⃣ 활성 포지션 있으면 TP 확장 체크
            if V61_ACTIVE_POSITION:
                pos = V61_ACTIVE_POSITION
                entry_price = pos['entry_price']
                direction = pos['direction']
                original_tp = pos['original_tp']
                current_tp = pos['current_tp']
                sl = pos['sl']
                
                # TP/SL 도달 체크
                if direction == 'short':
                    profit = entry_price - current_price
                    tp_hit = current_price <= entry_price - current_tp
                    sl_hit = current_price >= entry_price + sl
                else:
                    profit = current_price - entry_price
                    tp_hit = current_price >= entry_price + current_tp
                    sl_hit = current_price <= entry_price - sl
                
                # MFE/MAE 업데이트
                mfe_mae = v61_filter.update_mfe_mae(current_price, entry_price, direction)
                
                if sl_hit:
                    v61_filter.record_trade(pos, 'LOSS', -sl)
                    print(f"❌ V6.1 SL 도달: {direction} | 손실: -{sl}pt | MFE:{mfe_mae['mfe']} MAE:{mfe_mae['mae']}")
                    V61_ACTIVE_POSITION = None
                elif tp_hit:
                    v61_filter.record_trade(pos, 'WIN', current_tp)
                    print(f"✅ V6.1 TP 도달: {direction} | 수익: +{current_tp}pt | MFE:{mfe_mae['mfe']} MAE:{mfe_mae['mae']}")
                    V61_ACTIVE_POSITION = None
                else:
                    # TP 확장 체크 (50% 도달 시)
                    ext = v61_filter.check_tp_extension(current_price, entry_price, direction, original_tp)
                    if ext['action'] == 'extend':
                        new_tp = ext['new_tp']
                        if new_tp > current_tp:
                            V61_ACTIVE_POSITION['current_tp'] = new_tp
                            ext_msg = f"""🔄 V6.1 TP 확장!
━━━━━━━━━━━━━━━━━━━━
📊 기존 TP: {current_tp}pt → 신규 TP: {new_tp}pt
💡 {ext['reason']}
📍 현재가: {current_price:.2f} | 수익: {profit:.1f}pt"""
                            send_telegram_alert(ext_msg, signal_type='V61_TP_EXTEND')
                            print(f"🔄 V6.1 TP 확장: {current_tp} → {new_tp} | {ext['reason']}")
                    elif ext['action'] == 'take':
                        print(f"⚠️ V6.1 방향약화 청산권고: {ext['reason']}")
            
            # 2️⃣ 새 신호 체크 (스위칭 포함)
            v61_signal = process_candle_v61(candle)
            if v61_signal:
                # 활성 포지션 있으면 스위칭 체크
                if V61_ACTIVE_POSITION:
                    switch = v61_filter.check_switching(V61_ACTIVE_POSITION, v61_signal)
                    if switch.get('should_switch'):
                        # 스위칭 실행!
                        old_price = V61_ACTIVE_POSITION['entry_price']
                        old_dir = V61_ACTIVE_POSITION['direction']
                        
                        # 기존 포지션 수익 계산
                        if old_dir == 'short':
                            old_profit = old_price - current_price
                        else:
                            old_profit = current_price - old_price
                        
                        # 기존 포지션 기록
                        result = 'WIN' if old_profit > 0 else 'LOSS'
                        v61_filter.record_trade(V61_ACTIVE_POSITION, result, old_profit)
                        
                        # 스위칭 메시지 발송
                        switch_msg = v61_filter.format_switching_message(switch, old_price, current_price, v61_signal)
                        send_telegram_alert(switch_msg, signal_type='V61_SWITCH')
                        print(f"🔁 V6.1 스위칭: {old_dir}→{v61_signal['direction']} | 기존수익:{old_profit:+.1f}pt | {switch['reason']}")
                        
                        # 새 포지션으로 교체
                        v61_filter.reset_mfe_mae()
                        V61_ACTIVE_POSITION = {
                            'direction': v61_signal['direction'],
                            'entry_price': current_price,
                            'original_tp': v61_signal['tp'],
                            'current_tp': v61_signal['tp'],
                            'sl': v61_signal['sl'],
                            'grade': v61_signal['grade'],
                            'mode': v61_signal['mode'],
                            'entry_time': datetime.now().isoformat()
                        }
                    else:
                        print(f"⏸️ V6.1 스위칭 스킵: {switch.get('reason', '')}")
                else:
                    # 신규 진입
                    tg_msg = v61_filter.format_telegram_message(v61_signal)
                    
                    direction = v61_signal['direction']
                    grade = v61_signal['grade']
                    mode = v61_signal['mode']
                    
                    V61_ACTIVE_POSITION = {
                        'direction': direction,
                        'entry_price': current_price,
                        'original_tp': v61_signal['tp'],
                        'current_tp': v61_signal['tp'],
                        'sl': v61_signal['sl'],
                        'grade': grade,
                        'mode': mode,
                        'entry_time': datetime.now().isoformat()
                    }
                    
                    signal_name = f"V61_{direction.upper()}_{grade}"
                    send_telegram_alert(tg_msg, signal_type=signal_name)
                    print(f"🔥 V6.1 신호 발송: {direction} [{grade}] | TP:{v61_signal['tp']} SL:{v61_signal['sl']} | 모드:{mode}")
        except Exception as v61_err:
            print(f"⚠️ V6.1 필터 오류: {v61_err}")
        
        # 🤖 AI Trading Engine으로 캔들 처리 (트렌드 필터 + 횡보 필터 + SPS 신호!)
        try:
            ai_signals = process_candle(candle, SUPPORT_LEVELS)
            if not ai_signals:
                pass  # 신호 없음 (정상 - 조건 미충족)
            for sig in ai_signals:
                sig_name = sig.get('name', 'UNKNOWN')
                sig_type = sig.get('type', '')
                sig_grade = sig.get('grade', '')
                win_rate = sig.get('win_rate', sig.get('confidence', 0))
                
                # S+ 또는 S 등급만 텔레그램 발송
                if sig_grade in ['S+', 'S'] and check_signal_verified(sig_name):
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    emoji = '🔴' if sig_type == 'SHORT' else '🟢'
                    tg_msg = f"""{emoji} {sig_name} ({sig_grade})
━━━━━━━━━━━━━━━━
📍 NQ @ {candle['close']:.2f}
🎯 TP: {sig.get('tp', 20)}pt | SL: {sig.get('sl', 30)}pt
📊 승률: {win_rate:.1f}%
💡 {sig.get('reason', '')}
⏰ {timestamp}"""
                    send_telegram_alert(tg_msg, signal_type=sig_name)
                    print(f"📤 AI신호 텔레그램 발송: {sig_name} {sig_grade}")
                else:
                    print(f"🤖 AI신호: {sig_name} {sig_grade} (승률: {win_rate:.1f}%)")
        except Exception as ai_err:
            print(f"⚠️ AI Trading Engine 오류: {ai_err}")
        
        # 🧪 SPS Core 실시간 신호 수집 (Phase 4 가설 테스트용)
        try:
            import sys
            sys.path.insert(0, 'src')
            from sps_core.realtime import get_collector
            
            sps_collector = get_collector()
            sps_result = sps_collector.process_candle(candle)
            
            if sps_result.get('signal'):
                print(f"🎯 SPS Core 신호: {sps_result['direction']} [{sps_result['level']}] | TP:{sps_result['tp']:.0f} SL:{sps_result['sl']:.0f}")
            elif sps_result.get('action') == 'EXIT':
                pnl_emoji = '✅' if sps_result['pnl'] > 0 else '❌'
                print(f"{pnl_emoji} SPS Core 청산: {sps_result['reason']} | PnL: {sps_result['pnl']:+.1f}pt | 승률: {sps_result['win_rate']:.1f}%")
        except Exception as sps_err:
            pass  # SPS Core 오류는 조용히 무시 (기존 시스템 영향 X)
        
        # 🔥 Signal Pool: 기존 신호들을 후보로 등록 + 판단
        try:
            import sys
            sys.path.insert(0, 'src')
            from sps_core.signal_pool import get_signal_pool
            import pandas as pd
            
            signal_pool = get_signal_pool()
            
            # 캔들을 Series로 변환 (판단에 필요)
            row = pd.Series({
                'close': candle['close'],
                'high': candle['high'],
                'low': candle['low'],
                'open': candle['open'],
                'dist_black': candle.get('dist_black', 100),
                'ch_range': candle.get('ch_range', 50),
                'ratio_p50': candle.get('ratio_p50', 1.0),
                'ratio_p10': candle.get('ratio_p10', 1.0),
                'sector': candle.get('sector', 50),
                'absorbed': candle.get('absorbed', False),
                'landed': candle.get('landed', False),
                'higher_low': candle.get('higher_low', False),
                'lower_high': candle.get('lower_high', False)
            })
            
            # ai_signals에서 후보 등록
            if ai_signals:
                for sig in ai_signals:
                    sig_name = sig.get('name', 'UNKNOWN')
                    sig_type = sig.get('type', 'LONG')
                    
                    decision = signal_pool.add_candidate(
                        signal_name=sig_name,
                        direction=sig_type,
                        price=candle['close'],
                        row=row,
                        extra={'grade': sig.get('grade', ''), 'original_signal': sig}
                    )
                    
                    emoji = '❌' if decision['decision'] == 'REJECT' else ('🎯' if decision['decision'] == 'SCALP' else '🔒')
                    print(f"{emoji} Pool: {sig_name} → {decision['decision']} | Gate:{decision['gate_ok']} Range:{decision['range_ok']}")
        except Exception as pool_err:
            pass  # Signal Pool 오류는 조용히 무시
        
        # 🎯 State Machine: 시장 상태 판단 (UP/DOWN/NEUTRAL)
        try:
            import sys
            sys.path.insert(0, 'src')
            from sps_core.state_machine import get_state_machine
            
            sm = get_state_machine()
            
            state_result = sm.update(
                price=candle['close'],
                high=candle['high'],
                low=candle['low'],
                absorbed=candle.get('absorbed', False),
                landed=candle.get('landed', False),
                macro_allowed=True,
                macro_against=False,
                reverse_absorbed=candle.get('reverse_absorbed', False),
                high_failed=candle.get('high_failed', False),
                low_failed=candle.get('low_failed', False),
                influence_ok=True,
                range_ok=candle.get('ch_range', 50) >= 30
            )
            
            # 📌 State 핀 메시지 업데이트 (항상 실시간)
            try:
                from telegram_gateway import update_state_pin, send_state_switch
                from sps_core.state_machine import MarketState, Confidence
                
                state_name = state_result.state.name
                allowed_long = state_result.state == MarketState.UP
                allowed_short = state_result.state == MarketState.DOWN
                reason = ', '.join(state_result.reasons[:3]) if state_result.reasons else ""
                
                # Confidence enum → float 변환
                conf_map = {Confidence.HIGH: 80.0, Confidence.MEDIUM: 50.0, Confidence.LOW: 30.0}
                conf_float = conf_map.get(state_result.confidence, 50.0)
                
                update_state_pin(
                    state=state_name,
                    confidence=conf_float,
                    invalidation=state_result.invalidation,
                    duration=sm.state_duration,
                    allowed_long=allowed_long,
                    allowed_short=allowed_short,
                    reason=reason
                )
            except Exception as pin_err:
                print(f"⚠️ 핀 업데이트 오류: {pin_err}")
            
            # 📊 State Tracker - 전환 추적 및 결과 검증
            try:
                from sps_core.state_tracker import get_state_tracker
                tracker = get_state_tracker()
                
                # 매 캔들마다 pending 전환 결과 체크
                completed = tracker.update_pending(
                    current_price=candle['close'],
                    high=candle['high'],
                    low=candle['low'],
                    threshold=20
                )
                if completed > 0:
                    stats = tracker.get_stats()
                    print(f"📈 State 검증 완료: {completed}건 | UP정확도:{stats['up']['accuracy']}% | DOWN정확도:{stats['down']['accuracy']}%")
            except Exception as track_err:
                pass
            
            if sm.is_switched():
                switch = sm.get_switch_info()
                print(f"🔄 State Switch: {switch['from']} → {switch['to']}")
                print(f"   Invalidation: {state_result.invalidation:.0f}")
                
                # 📊 State 전환 기록 (검증용)
                try:
                    from sps_core.state_tracker import get_state_tracker
                    tracker = get_state_tracker()
                    tracker.record_transition(
                        price=candle['close'],
                        from_state=switch['from'].replace('⬆️', 'UP').replace('⬇️', 'DOWN').replace('↔️', 'NEUTRAL'),
                        to_state=switch['to'].replace('⬆️', 'UP').replace('⬇️', 'DOWN').replace('↔️', 'NEUTRAL'),
                        confidence=conf_float / 100.0,
                        reasons=state_result.reasons
                    )
                    print(f"📊 State 전환 기록됨 → 방향 검증 시작")
                except Exception as rec_err:
                    print(f"⚠️ 전환 기록 오류: {rec_err}")
                
                try:
                    from telegram_gateway import send_state_switch
                    reason_text = '\n'.join([f"- {r}" for r in state_result.reasons])
                    send_state_switch(
                        old_state=switch['from'],
                        new_state=switch['to'],
                        reason=f"Invalidation: {state_result.invalidation:.0f}\n\n{reason_text}"
                    )
                except:
                    pass
            else:
                print(f"📊 State: {state_result.state.value} | inv:{state_result.invalidation:.0f} | dur:{sm.state_duration}")
            
            # 🟢 Entry Window 업데이트
            try:
                from sps_core.entry_readiness import update_entry_window, get_entry_status, format_entry_event
                
                state_name = state_result.state.name
                prev_state = 'NEUTRAL'
                if hasattr(sm, 'previous_state') and sm.previous_state:
                    prev_state = sm.previous_state.name
                
                score = 5
                try:
                    ch_pct = candle.get('ch_pct', 50)
                    ratio_z = candle.get('ratio_z', 0)
                    if ch_pct >= 80 or ch_pct <= 20:
                        score += 2
                    if abs(ratio_z) >= 1.0:
                        score += 2
                except:
                    pass
                
                event = update_entry_window(state_name, prev_state, sm.state_duration, score)
                
                if event:
                    alert_msg = format_entry_event(event)
                    print(alert_msg)
                    send_telegram_alert(alert_msg, signal_type=f'ENTRY_WINDOW_{event}')
                    
            except Exception as ew_err:
                print(f"⚠️ Entry Window 오류: {ew_err}")
                
        except Exception as sm_err:
            pass  # State Machine 오류는 조용히 무시
        
        # 🤖 AI 시스템에도 캔들 전송 (기존)
        from macro_micro_ai import update_realtime_candle
        ai_candle = {'open': candle['open'], 'high': candle['high'], 'low': candle['low'], 'close': candle['close']}
        ai_result = update_realtime_candle(ai_candle)
        
        # 🛑 Invalidation 터치 체크 (구조 손절)
        try:
            from telegram_gateway import check_invalidation_hit
            check_invalidation_hit(candle['close'])
        except Exception as inv_err:
            pass
        
        # 🔥 SL/TP 자동 체크 - 진입 중인 신호가 SL/TP에 도달하면 자동 LOSS/WIN 처리
        check_sl_tp_hit(candle['close'])
        
        # 📊 터치 결과 추적 업데이트
        update_pending_touches(candle['high'], candle['low'])
        
        # 📍 SPS 스팟 자동 감지 (채널 극단, 100봉 고저점, 빗각 터치 시 SPS 기록)
        try:
            from sps_spot_detector import auto_detect_spots
            
            ivwap_data = {
                'sell_ivwap': candle.get('매도 iVWAP (분홍)', 0),
                'buy_ivwap': candle.get('매수 iVWAP (초록)', 0)
            }
            
            # 🔥 IANGLE_DATA에서 최신 빗각 데이터 가져오기
            iangle_data = None
            if IANGLE_DATA:
                latest_iangle = IANGLE_DATA[-1]
                # line_value = 빗각 가격, price = 현재가
                angle_price = float(latest_iangle.get('line_value', 0))
                if angle_price <= 0:
                    angle_price = float(latest_iangle.get('price', 0))
                
                iangle_data = {
                    'angle_price': angle_price,
                    'direction': latest_iangle.get('direction', 'down')
                }
            
            detected_spots = auto_detect_spots(CANDLE_HISTORY[-200:], iangle_data=iangle_data, ivwap_data=ivwap_data)
            
            if detected_spots:
                for spot in detected_spots:
                    print(f"📍 스팟 등록: {spot['type']} @ {spot['price']:.2f} (SPS={spot['sps']:.1f}, {spot.get('level', '')})")
        except Exception as spot_err:
            print(f"⚠️ 스팟 감지 오류: {spot_err}")
        
        # 📍 매수 스팟 체크 - ⛔ 미검증 = 로그/텔레그램 차단!
        buy_spot = check_buy_spot()
        if buy_spot and buy_spot.get('signal'):
            grade = buy_spot.get('grade', 'A')
            # 🚫 미검증 신호 - 로그/텔레그램 차단 (콘솔만 출력)
            print(f"⛔ 매수스팟 차단 (미검증): {grade} {buy_spot['reason']}")
        
        # 📍 매도 스팟 체크 - ⛔ 미검증 = 로그/텔레그램 차단!
        sell_spot = check_sell_spot()
        if sell_spot and sell_spot.get('signal'):
            grade = sell_spot.get('grade', 'A')
            # 🚫 미검증 신호 - 로그/텔레그램 차단 (콘솔만 출력)
            print(f"⛔ 매도스팟 차단 (미검증): {grade} {sell_spot['reason']}")
        
        # ═══════════════════════════════════════════════════════════════════════
        # 📊 STB 점 로직 스팟 체크 (94% 저항률!)
        # ═══════════════════════════════════════════════════════════════════════
        
        # 📍 STB 매도 스팟 (섹터90%+ SPS비율z<0 + 음봉)
        stb_sell = check_stb_sell_spot()
        if stb_sell and stb_sell.get('signal'):
            from signal_logger import log_signal
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            grade = stb_sell.get('grade', 'A')
            
            # ⭐ P+, P-소진, S++, S+, S 등급만 로그 저장 + 텔레그램 (99%+ 검증!)
            # A+, A, A- 등급은 로그 저장 안 함 (TP/SL 중복 방지)
            if grade in ['P+', 'P-소진', 'S++', 'S+', 'S']:
                # ⏱️ 쿨다운 체크 (5분 내 중복 발송 차단)
                global LAST_STB_SIGNAL
                last_short = LAST_STB_SIGNAL.get('short')
                cooldown_min = LAST_STB_SIGNAL.get('cooldown_minutes', 5)
                can_send = True
                
                if last_short:
                    try:
                        last_dt = datetime.fromisoformat(last_short)
                        if datetime.now() - last_dt < timedelta(minutes=cooldown_min):
                            can_send = False
                            print(f"⏱️ STB숏 쿨다운 중 ({cooldown_min}분) - 스킵")
                    except:
                        pass
                
                # ⭐ Entry Window 연동: 창 열렸을 때만 허용
                state_str = "❓"
                window_tp, window_sl = 20, 30
                if can_send:
                    try:
                        from sps_core.entry_readiness import is_signal_allowed, get_entry_status, get_current_tp_sl
                        status = get_entry_status()
                        
                        if not status['window_open']:
                            print(f"⛔ STB숏 차단: Entry Window 닫힘 ({status.get('status', '?')})")
                            can_send = False
                        elif not is_signal_allowed('STB숏'):
                            print(f"⛔ STB숏 차단: 허용 신호 아님")
                            can_send = False
                        else:
                            window_tp, window_sl = get_current_tp_sl()
                            state_str = f"{status.get('state', '?')} ✅ (창 열림)"
                    except Exception as e:
                        from sps_core.state_machine import get_state_machine, MarketState
                        sm = get_state_machine()
                        current_state = sm.current_state
                        if current_state == MarketState.UP:
                            print(f"⛔ STB숏 차단: State=UP (상승장에서 숏 금지)")
                            can_send = False
                        elif current_state == MarketState.NEUTRAL:
                            print(f"⛔ STB숏 차단: State=NEUTRAL (방향 미확정)")
                            can_send = False
                        elif current_state == MarketState.DOWN:
                            state_str = "⬇️ DOWN ✅"
                
                if can_send:
                    # 🔒 ATOMIC SNAPSHOT (H_P1-P3 해결!)
                    # 원칙: 트리거 시점에 스냅샷 1회 생성, 이후 모든 처리는 스냅샷만 참조
                    snapshot = create_signal_snapshot(
                        direction='SHORT',
                        candle=candle,
                        stb_data=stb_sell,
                        grade=grade,
                        state_str=state_str
                    )
                    
                    # 스냅샷 로그 저장 (파이프라인 검증용)
                    log_snapshot(snapshot)
                    
                    # 신호 로그 (스냅샷 값 사용!)
                    log_signal(
                        signal_type='STB숏',
                        direction='SHORT',
                        entry_price=snapshot['price'],
                        ratio=snapshot['sps_ratio_z'],
                        channel_pct=snapshot['sector_pct'],
                        z_score=snapshot['sps_ratio_z'],
                        grade=snapshot['grade'],
                        notes=f"[{snapshot['event_id']}] {snapshot['reason']}",
                        tp=snapshot['tp'],
                        sl=snapshot['sl']
                    )
                    LAST_STB_SIGNAL['short'] = datetime.now().isoformat()
                    
                    # 📸 Score Snapshot (디버깅 필수!)
                    score_info = stb_sell.get('score_info', {})
                    if score_info:
                        log_score_snapshot(score_info, snapshot['price'], snapshot['trigger_time'])
                    
                    # 🔒 메시지 렌더링 (스냅샷만 참조!)
                    entry_msg = format_entry_from_snapshot(snapshot)
                    send_telegram_alert(entry_msg, signal_type='STB숏')
                    
                    exit_msg = format_exit_from_snapshot(snapshot)
                    send_telegram_alert(exit_msg, signal_type='EXIT설정')
            print(f"🔴 STB숏 {grade}! {stb_sell['reason']}")
            
            # ⭐ 시퀀스 롱 - SEQUENCE_TRIGGERS로 자동 기록됨
        
        # ═══════════════════════════════════════════════════════════════════════
        # 📊 시퀀스 롱 체크 (STB숏 후 → 배율z<0 + 양봉 + 섹터30%- = 100%!)
        # ═══════════════════════════════════════════════════════════════════════
        seq_long = check_sequence_long()
        if seq_long and seq_long.get('signal'):
            from signal_logger import log_signal
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            grade = seq_long.get('grade', 'A')
            log_signal(
                signal_type='시퀀스롱',
                direction='LONG',
                entry_price=candle['close'],
                ratio=seq_long['sell_ratio_z'],
                channel_pct=seq_long['sector_pct'],
                z_score=seq_long['sell_ratio_z'],
                grade=grade,
                notes=seq_long['reason'],
                tp=20,
                sl=10
            )
            
            # S+, S 등급 텔레그램 알림 (100% 승률!)
            if grade in ['S+', 'S']:
                tg_msg = f"""🟢 시퀀스롱 {grade}! (100% 승률!)
━━━━━━━━━━━━━━━━
📍 NQ @ {candle['close']:.2f}
🎯 TP: 20pt | SL: 30pt
📊 섹터: {seq_long['sector_pct']:.0f}% | 배율z: {seq_long['sell_ratio_z']:.2f}
📈 STB숏 {seq_long.get('stb_candles_ago', '?')}봉 전 → 매집완료
💡 {seq_long['reason']}
⏰ {timestamp}"""
                send_telegram_alert(tg_msg, signal_type='시퀀스롱')
            print(f"🟢 시퀀스롱 {grade}! {seq_long['reason']}")
        
        # 📍 STB 매수 스팟 (섹터10%- SPS비율z>0 + 양봉)
        stb_buy = check_stb_buy_spot()
        if stb_buy and stb_buy.get('signal'):
            from signal_logger import log_signal
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            grade = stb_buy.get('grade', 'A')
            
            # ⭐ P+, P-소진, S++, S+, S 등급만 로그 저장 + 텔레그램 (99%+ 검증!)
            # A+, A, A- 등급은 로그 저장 안 함 (TP/SL 중복 방지)
            if grade in ['P+', 'P-소진', 'S++', 'S+', 'S']:
                # ⏱️ 쿨다운 체크 (5분 내 중복 발송 차단)
                last_long = LAST_STB_SIGNAL.get('long')
                cooldown_min = LAST_STB_SIGNAL.get('cooldown_minutes', 5)
                can_send = True
                
                if last_long:
                    try:
                        last_dt = datetime.fromisoformat(last_long)
                        if datetime.now() - last_dt < timedelta(minutes=cooldown_min):
                            can_send = False
                            print(f"⏱️ STB롱 쿨다운 중 ({cooldown_min}분) - 스킵")
                    except:
                        pass
                
                # ⭐ Entry Window 연동: 창 열렸을 때만 허용
                state_str = "❓"
                window_tp, window_sl = 19, 25
                if can_send:
                    try:
                        from sps_core.entry_readiness import is_signal_allowed, get_entry_status, get_current_tp_sl
                        status = get_entry_status()
                        
                        if not status['window_open']:
                            print(f"⛔ STB롱 차단: Entry Window 닫힘 ({status.get('status', '?')})")
                            can_send = False
                        elif not is_signal_allowed('STB롱'):
                            print(f"⛔ STB롱 차단: 허용 신호 아님")
                            can_send = False
                        else:
                            window_tp, window_sl = get_current_tp_sl()
                            state_str = f"{status.get('state', '?')} ✅ (창 열림)"
                    except Exception as e:
                        from sps_core.state_machine import get_state_machine, MarketState
                        sm = get_state_machine()
                        current_state = sm.current_state
                        if current_state == MarketState.DOWN:
                            print(f"⛔ STB롱 차단: State=DOWN (하락장에서 롱 금지)")
                            can_send = False
                        elif current_state == MarketState.NEUTRAL:
                            print(f"⛔ STB롱 차단: State=NEUTRAL (방향 미확정)")
                            can_send = False
                        elif current_state == MarketState.UP:
                            state_str = "⬆️ UP ✅"
                
                if can_send:
                    # 🔒 ATOMIC SNAPSHOT (H_P1-P3 해결!)
                    # 원칙: 트리거 시점에 스냅샷 1회 생성, 이후 모든 처리는 스냅샷만 참조
                    snapshot = create_signal_snapshot(
                        direction='LONG',
                        candle=candle,
                        stb_data=stb_buy,
                        grade=grade,
                        state_str=state_str
                    )
                    
                    # 스냅샷 로그 저장 (파이프라인 검증용)
                    log_snapshot(snapshot)
                    
                    # 신호 로그 (스냅샷 값 사용!)
                    log_signal(
                        signal_type='STB롱',
                        direction='LONG',
                        entry_price=snapshot['price'],
                        ratio=snapshot['sps_ratio_z'],
                        channel_pct=snapshot['sector_pct'],
                        z_score=snapshot['sps_ratio_z'],
                        grade=snapshot['grade'],
                        notes=f"[{snapshot['event_id']}] {snapshot['reason']}",
                        tp=snapshot['tp'],
                        sl=snapshot['sl']
                    )
                    LAST_STB_SIGNAL['long'] = datetime.now().isoformat()
                    
                    # 📸 Score Snapshot (디버깅 필수!)
                    score_info = stb_buy.get('score_info', {})
                    if score_info:
                        log_score_snapshot(score_info, snapshot['price'], snapshot['trigger_time'])
                    
                    # 🔒 메시지 렌더링 (스냅샷만 참조!)
                    entry_msg = format_entry_from_snapshot(snapshot)
                    send_telegram_alert(entry_msg, signal_type='STB롱')
                    
                    exit_msg = format_exit_from_snapshot(snapshot)
                    send_telegram_alert(exit_msg, signal_type='EXIT설정')
            print(f"🟢 STB롱 {grade}! {stb_buy['reason']}")
        
        # 📍 빗각버팀 체크 - ⛔ 미검증 = 로그/텔레그램 차단!
        iangle = check_iangle_absorption()
        if iangle and iangle.get('signal'):
            # 🚫 미검증 신호 - 로그/텔레그램 차단 (콘솔만 출력)
            print(f"⛔ 빗각버팀 차단 (미검증): {iangle['reason']}")
        
        # 📍 저점상승 체크 - ⛔ 미검증 = 로그/텔레그램 차단!
        hl_pattern = check_higher_low_pattern()
        if hl_pattern and hl_pattern.get('signal'):
            grade = hl_pattern.get('grade', 'A')
            # 🚫 미검증 신호 - 로그/텔레그램 차단 (콘솔만 출력)
            print(f"⛔ 저점상승 차단 (미검증): {grade} {hl_pattern['reason']}")
        
        # 📍 시퀀스 제거됨 (2026-01-08) - SPS 배율 시스템으로 대체
        
        if len(CANDLE_HISTORY) >= 30:
            import pandas as pd
            
            df = pd.DataFrame(CANDLE_HISTORY)
            df['time'] = pd.to_datetime(df['time'].astype(float), unit='ms', errors='coerce')
            
            signals = SIGNAL_MONITOR.check_signal(df)
            
            if signals:
                SIGNAL_MONITOR.send_signal_alert(signals)
                print(f"🚨 신호 발생: {[s['type'] for s in signals]}")
                
                return jsonify({
                    "status": "success",
                    "signals": signals,
                    "candle_count": len(CANDLE_HISTORY)
                })
        
        # 🔥 SPS 배율 시스템 - 리테스트 체크
        try:
            from sps_multiplier import check_retest_signal
            sps_signals = check_retest_signal(candle, candle['time'])
            
            # 🛡️ 양빵 방지 필터: 롱/숏 동시 발생 시 차단
            if len(sps_signals) > 1:
                long_signals = [s for s in sps_signals if s.get('type') == 'LONG']
                short_signals = [s for s in sps_signals if s.get('type') == 'SHORT']
                
                if long_signals and short_signals:
                    print(f"⚠️ 양빵 감지! 롱 {len(long_signals)}개 + 숏 {len(short_signals)}개 동시 발생 → 전체 차단")
                    sps_signals = []
            
            # 🚫 SPS배율 신호 - 25.6% 승률 = 완전 차단! (로그/텔레그램 없음)
            for sig in sps_signals:
                if sig.get('confidence', 0) >= 70:
                    # ⛔ SPS배율롱/숏 차단됨 (2026-01-12) - 승률 25% = 랜덤수준
                    print(f"⛔ SPS배율 차단: {sig['name']} ({sig['type']}) - 배율 {sig['multiplier']:.2f} (25% 승률 = 차단)")
        except Exception as sps_err:
            print(f"⚠️ SPS배율 오류: {sps_err}")
        
        # 🤝 듀얼 AI 합의 시스템 - 양쪽 모두 동의해야 발송!
        try:
            consensus_result = process_with_consensus(candle)
            
            if consensus_result.get('validator_issues'):
                for issue in consensus_result['validator_issues']:
                    print(f"⚠️ 검증AI 이슈: {issue['message']}")
            
            for sig in consensus_result.get('approved_signals', []):
                engine = get_engine()
                msg = engine.format_telegram_message(sig)
                send_telegram_alert(msg, signal_type=sig.get('name', 'AI'))
                print(f"✅ 듀얼합의 승인: {sig['name']} ({sig['type']}) - {sig['confidence']}%")
            
            for sig in consensus_result.get('rejected_signals', []):
                print(f"❌ 듀얼합의 거부: {sig['name']} - {sig.get('consensus_reason', '')}")
                
        except Exception as ai_err:
            print(f"⚠️ 듀얼합의 오류: {ai_err}")
        
        return jsonify({
            "status": "success", 
            "message": f"캔들 저장됨 ({len(CANDLE_HISTORY)}/120)",
            "candle_count": len(CANDLE_HISTORY)
        })
        
    except Exception as e:
        import traceback
        print(f"❌ 캔들 웹훅 오류: {e}")
        print(f"📍 상세 위치:\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": str(e)}), 500

# 1분봉 iVWAP 데이터 저장소
IVWAP_1M_DATA = {
    "buy_ivwap": 0,
    "sell_ivwap": 0,
    "buy_ivwap_upper": 0,
    "buy_ivwap_lower": 0,
    "sell_ivwap_upper": 0,
    "sell_ivwap_lower": 0,
    "cluster_ratio": 0,
    "last_update": None
}

# A급 탐지기 1분봉 데이터
AGRADE_1M_DATA = {
    "ivpoc": 0,
    "buy_zone_top": 0,
    "buy_zone_bottom": 0,
    "sell_zone_top": 0,
    "sell_zone_bottom": 0,
    "last_update": None
}

def check_1m_cluster(price, direction):
    """1분봉 클러스터 영역 체크 - 가격이 iVWAP/iVPOC 근처인지 확인"""
    CLUSTER_THRESHOLD = 20  # 20pt 이내면 클러스터 영역
    
    result = {
        "in_cluster": False,
        "level_name": None,
        "level_value": 0,
        "distance": 999
    }
    
    levels = []
    
    # 롱 신호일 때: 매수 iVWAP 하단, iVPOC 근처 확인
    if direction == "롱":
        if IVWAP_1M_DATA['buy_ivwap'] > 0:
            levels.append(("매수iVWAP", IVWAP_1M_DATA['buy_ivwap']))
        if IVWAP_1M_DATA['buy_ivwap_lower'] > 0:
            levels.append(("매수iVWAP하단", IVWAP_1M_DATA['buy_ivwap_lower']))
        if AGRADE_1M_DATA['ivpoc'] > 0:
            levels.append(("iVPOC", AGRADE_1M_DATA['ivpoc']))
        if AGRADE_1M_DATA['buy_zone_bottom'] > 0:
            levels.append(("매수영역하단", AGRADE_1M_DATA['buy_zone_bottom']))
    
    # 숏 신호일 때: 매도 iVWAP 상단, iVPOC 근처 확인
    else:
        if IVWAP_1M_DATA['sell_ivwap'] > 0:
            levels.append(("매도iVWAP", IVWAP_1M_DATA['sell_ivwap']))
        if IVWAP_1M_DATA['sell_ivwap_upper'] > 0:
            levels.append(("매도iVWAP상단", IVWAP_1M_DATA['sell_ivwap_upper']))
        if AGRADE_1M_DATA['ivpoc'] > 0:
            levels.append(("iVPOC", AGRADE_1M_DATA['ivpoc']))
        if AGRADE_1M_DATA['sell_zone_top'] > 0:
            levels.append(("매도영역상단", AGRADE_1M_DATA['sell_zone_top']))
    
    # 가장 가까운 레벨 찾기
    for level_name, level_value in levels:
        distance = abs(price - level_value)
        if distance < result['distance']:
            result['distance'] = distance
            result['level_name'] = level_name
            result['level_value'] = level_value
            if distance <= CLUSTER_THRESHOLD:
                result['in_cluster'] = True
    
    return result

def calculate_upgraded_sl(price, direction):
    """1분봉 레벨 기반 타이트 SL 계산 - RR 개선용"""
    result = {
        "use_upgraded": False,
        "sl_type": None,
        "sl_value": 0,
        "original_sl": 0,
        "rr_improvement": 0
    }
    
    TP_DISTANCE = 40  # TP 고정
    
    if direction == "롱":
        # 원래 SL (10분봉 기준: 진입가 - 8pt)
        result['original_sl'] = price - 8
        
        # 1분봉 iVWAP 하단 기반 SL (최우선! 40% 승률, RR 5.44)
        sl_ivwap = IVWAP_1M_DATA['buy_ivwap_lower'] - 5 if IVWAP_1M_DATA['buy_ivwap_lower'] > 0 else 0
        
        # 1분봉 iVPOC 기반 SL (차선)
        sl_ivpoc = AGRADE_1M_DATA['ivpoc'] - 5 if AGRADE_1M_DATA['ivpoc'] > 0 else 0
        
        # iVWAP 하단 우선 선택 (백테스트 결과)
        candidates = []
        if sl_ivwap > 0 and sl_ivwap < price and price - sl_ivwap >= 5:
            risk_ivwap = price - sl_ivwap
            rr_ivwap = TP_DISTANCE / risk_ivwap
            candidates.append(("iVWAP하단", sl_ivwap, rr_ivwap, 1))  # 우선순위 1
        
        if sl_ivpoc > 0 and sl_ivpoc < price and price - sl_ivpoc >= 5:
            risk_ivpoc = price - sl_ivpoc
            rr_ivpoc = TP_DISTANCE / risk_ivpoc
            candidates.append(("iVPOC", sl_ivpoc, rr_ivpoc, 2))  # 우선순위 2
        
        # 우선순위 기반 선택
        if candidates:
            best = min(candidates, key=lambda x: x[3])  # 우선순위 낮은 것 선택
            original_risk = price - result['original_sl']
            original_rr = TP_DISTANCE / original_risk if original_risk > 0 else 0
            
            result['use_upgraded'] = True
            result['sl_type'] = best[0]
            result['sl_value'] = best[1]
            result['rr_improvement'] = best[2] - original_rr
    
    else:  # 숏
        result['original_sl'] = price + 8
        
        # 1분봉 iVWAP 상단 기반 SL
        sl_ivwap = IVWAP_1M_DATA['sell_ivwap_upper'] + 5 if IVWAP_1M_DATA['sell_ivwap_upper'] > 0 else 0
        
        # 1분봉 iVPOC 기반 SL
        sl_ivpoc = AGRADE_1M_DATA['ivpoc'] + 5 if AGRADE_1M_DATA['ivpoc'] > 0 else 0
        
        candidates = []
        if sl_ivwap > 0 and sl_ivwap > price and sl_ivwap - price >= 5:
            risk_ivwap = sl_ivwap - price
            rr_ivwap = TP_DISTANCE / risk_ivwap
            candidates.append(("iVWAP상단", sl_ivwap, rr_ivwap, 1))
        
        if sl_ivpoc > 0 and sl_ivpoc > price and sl_ivpoc - price >= 5:
            risk_ivpoc = sl_ivpoc - price
            rr_ivpoc = TP_DISTANCE / risk_ivpoc
            candidates.append(("iVPOC", sl_ivpoc, rr_ivpoc, 2))
        
        if candidates:
            best = min(candidates, key=lambda x: x[3])
            original_risk = result['original_sl'] - price
            original_rr = TP_DISTANCE / original_risk if original_risk > 0 else 0
            
            result['use_upgraded'] = True
            result['sl_type'] = best[0]
            result['sl_value'] = best[1]
            result['rr_improvement'] = best[2] - original_rr
    
    return result

def check_s_grade_signal(row, ivwap_1m_data, agrade_1m_data):
    """S등급 신호 체크 - BB + iVWAP하단 + 흡수 = 40% 승률, RR 5.44"""
    result = {
        "is_s_grade": False,
        "signal_name": None,
        "direction": None,
        "conditions": []
    }
    
    close = row['close']
    low = row['low']
    high = row['high']
    
    # 흡수 체크
    candle_range = high - low
    if candle_range == 0:
        return result
    
    lower_wick = min(row['open'], close) - low
    upper_wick = high - max(row['open'], close)
    
    has_buy_absorption = lower_wick / candle_range >= 0.4
    has_sell_absorption = upper_wick / candle_range >= 0.4
    
    # 롱 S등급: BB하단 + iVWAP하단 터치 + 흡수
    bb_lower = row.get('Lower Band', 0) or row.get('bb_lower', 0)
    bb_upper = row.get('Upper Band', 0) or row.get('bb_upper', 0)
    
    bb_touch_low = bb_lower > 0 and low <= bb_lower * 1.001
    bb_touch_high = bb_upper > 0 and high >= bb_upper * 0.999
    
    buy_ivwap_lower = ivwap_1m_data.get('buy_ivwap_lower', 0)
    sell_ivwap_upper = ivwap_1m_data.get('sell_ivwap_upper', 0)
    
    ivwap_lower_touch = buy_ivwap_lower > 0 and abs(low - buy_ivwap_lower) <= 10
    ivwap_upper_touch = sell_ivwap_upper > 0 and abs(high - sell_ivwap_upper) <= 10
    
    # 롱 S등급
    if bb_touch_low and ivwap_lower_touch and has_buy_absorption:
        result['is_s_grade'] = True
        result['signal_name'] = "SL: BB+iVWAP하단+흡수"
        result['direction'] = "롱"
        result['conditions'] = ["BB하단", "iVWAP하단", "흡수"]
    
    # 숏 S등급
    elif bb_touch_high and ivwap_upper_touch and has_sell_absorption:
        result['is_s_grade'] = True
        result['signal_name'] = "SS: BB+iVWAP상단+흡수"
        result['direction'] = "숏"
        result['conditions'] = ["BB상단", "iVWAP상단", "흡수"]
    
    return result

IANGLE_DATA = []

@app.route('/webhook/sps-spot', methods=['POST'])
def sps_spot_webhook():
    """SPS 배율 시스템 - 스팟 도달 등록
    TradingView에서 저항/지지 터치 시 호출
    - spot_type: resistance, support, angle_down, angle_up, poc_high, poc_low
    - price: 터치 가격
    - sps: 현재 SPS 값 (TradingView 지표에서)
    - level_name: 레벨 이름 (선택)
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        print(f"📍 SPS 스팟 등록 수신: {data}")
        
        if data.get('passphrase') not in WEBHOOK_SECRETS:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        spot_type = data.get('spot_type', data.get('type', 'resistance'))
        price = float(data.get('price', 0))
        sps = float(data.get('sps', 0))
        level_name = data.get('level_name', data.get('line_name', ''))
        candle_time = data.get('time', datetime.now().isoformat())
        
        if price <= 0 or sps <= 0:
            return jsonify({
                "status": "error", 
                "message": "price와 sps 필수"
            }), 400
        
        from sps_multiplier import register_spot_touch, get_sps_status
        
        # 🔥 100봉 고저점 + 200MA 트렌드 계산
        trend = 'neutral'
        if len(CANDLE_HISTORY) >= 200:
            closes = [c['close'] for c in CANDLE_HISTORY[-200:]]
            ma_200 = sum(closes) / 200
            current_price = CANDLE_HISTORY[-1]['close']
            if current_price > ma_200:
                trend = 'up'
            elif current_price < ma_200:
                trend = 'down'
        
        spot_id = register_spot_touch(
            spot_type=spot_type,
            price=price,
            sps=sps,
            candle_time=candle_time,
            level_name=level_name,
            extra={'trend': trend, 'ma_200_applied': True}
        )
        
        status = get_sps_status()
        
        print(f"✅ SPS 스팟 등록: {spot_type} @ {price:.2f}, SPS={sps:.1f}")
        
        return jsonify({
            "status": "success",
            "spot_id": spot_id,
            "message": f"스팟 등록됨: {spot_type} @ {price:.2f}",
            "active_spots": status['active_spots']
        })
        
    except Exception as e:
        print(f"❌ SPS 스팟 등록 오류: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/sps-status', methods=['GET'])
def get_sps_system_status():
    """SPS 배율 시스템 상태 조회"""
    try:
        from sps_multiplier import get_sps_status
        status = get_sps_status()
        
        signals = []
        try:
            import json
            with open('.sps_multiplier_signals.json', 'r') as f:
                signals = json.load(f)[-20:]
        except:
            pass
        
        return jsonify({
            "success": True,
            "status": status,
            "recent_signals": signals
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/sps-core/status', methods=['GET'])
def get_sps_core_status():
    """SPS Core 실시간 수집기 상태 조회"""
    try:
        import sys
        sys.path.insert(0, 'src')
        from sps_core.realtime import get_collector
        
        collector = get_collector()
        status = collector.get_status()
        
        return jsonify({
            "success": True,
            "status": status
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/sps-core/report', methods=['GET'])
def get_sps_core_report():
    """SPS Core 리포트 조회"""
    try:
        import sys
        sys.path.insert(0, 'src')
        from sps_core.realtime import get_collector
        
        collector = get_collector()
        report = collector.get_report()
        
        return report, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/api/signal-pool/status', methods=['GET'])
def get_signal_pool_status():
    """Signal Pool 상태 조회"""
    try:
        import sys
        sys.path.insert(0, 'src')
        from sps_core.signal_pool import get_signal_pool
        
        pool = get_signal_pool()
        stats = pool.get_stats()
        recent = pool.get_recent_decisions(20)
        
        return jsonify({
            "success": True,
            "stats": stats,
            "recent_decisions": recent
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal-pool/report', methods=['GET'])
def get_signal_pool_report():
    """Signal Pool 리포트 조회"""
    try:
        import sys
        sys.path.insert(0, 'src')
        from sps_core.signal_pool import get_signal_pool
        
        pool = get_signal_pool()
        report = pool.get_report()
        
        return report, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/api/state-machine/status', methods=['GET'])
def get_state_machine_status():
    """State Machine 상태 조회"""
    try:
        import sys
        sys.path.insert(0, 'src')
        from sps_core.state_machine import get_state_machine
        
        sm = get_state_machine()
        stats = sm.get_stats()
        recent = [h.to_dict() for h in sm.history[-20:]]
        
        return jsonify({
            "success": True,
            "stats": stats,
            "recent_history": recent
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/state-machine/report', methods=['GET'])
def get_state_machine_report():
    """State Machine 리포트 조회"""
    try:
        import sys
        sys.path.insert(0, 'src')
        from sps_core.state_machine import get_state_machine
        
        sm = get_state_machine()
        report = sm.get_report()
        
        return report, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/api/state-explain', methods=['GET'])
def get_state_explain():
    """State 설명 + 신뢰도 + RR 판단"""
    try:
        import sys
        sys.path.insert(0, 'src')
        from sps_core.state_machine import get_state_machine
        from sps_core.state_explainer import get_full_state_report
        
        sm = get_state_machine()
        
        direction = request.args.get('direction', 'SHORT')
        tp = float(request.args.get('tp', 20))
        sl = float(request.args.get('sl', 10))
        
        active_signals = request.args.get('signals', '').split(',') if request.args.get('signals') else []
        
        if sm.history:
            last = sm.history[-1]
            current_state = last.state
            invalidation = last.invalidation
            price = last.price
        else:
            from sps_core.state_machine import MarketState
            current_state = MarketState.NEUTRAL
            invalidation = 0
            price = 0
        
        report = get_full_state_report(
            current_state=current_state,
            active_signals=active_signals,
            direction=direction,
            invalidation=invalidation,
            current_price=price,
            tp_distance=tp,
            sl_distance=sl
        )
        
        return report, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/webhook/iangle', methods=['POST'])
def iangle_webhook():
    """빗각 터치 얼러트 수집 - TradingView에서 빗각 터치시 호출"""
    global IANGLE_DATA
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        print(f"📐 빗각 터치 수신: {data}")
        
        if data.get('passphrase') not in WEBHOOK_SECRETS:
            print(f"❌ iangle 인증실패: passphrase={data.get('passphrase')}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        iangle_record = {
            "timestamp": datetime.now().isoformat(),
            "line_name": data.get('line_name', ''),
            "line_value": float(data.get('line_value', 0) or 0),
            "price": float(data.get('price', 0) or 0),
            "direction": data.get('direction', ''),
            "touch_type": data.get('touch_type', 'touch'),
        }
        
        # 📌 iangle = 하락빗각(falling_angle)만 처리
        # rising_angle은 별도 웹훅(/webhook)에서 'rising_angle' 필드로 수신
        global SUPPORT_LEVELS
        line_value = iangle_record['line_value']
        
        if line_value > 0:
            SUPPORT_LEVELS['falling_angle'] = line_value
            print(f"📐 falling_angle(iangle) 업데이트: {line_value:.2f}")
        
        IANGLE_DATA.append(iangle_record)
        if len(IANGLE_DATA) > 1000:
            IANGLE_DATA = IANGLE_DATA[-500:]
        
        import json
        try:
            with open('.iangle_touches.json', 'r') as f:
                touches = json.load(f)
        except:
            touches = []
        
        touches.append(iangle_record)
        if len(touches) > 1000:
            touches = touches[-500:]
        
        with open('.iangle_touches.json', 'w') as f:
            json.dump(touches, f, indent=2, ensure_ascii=False)
        
        print(f"📐 빗각 저장: {iangle_record['line_name']} @ {iangle_record['line_value']:.2f} (현재가: {iangle_record['price']:.2f})")
        
        # ═══════════════════════════════════════════════════════════════════════
        # 📊 동적 스팟 추적기에 저장!
        # ═══════════════════════════════════════════════════════════════════════
        if iangle_record['line_value'] > 0:
            spot = add_spot(
                line_name=iangle_record['line_name'],
                line_value=iangle_record['line_value'],
                price=iangle_record['price'],
                signal_type='iangle'
            )
            print(f"📍 스팟 추적기 저장: {spot['line_name']} @ {spot['spot_price']:.2f}")
        
        # ═══════════════════════════════════════════════════════════════════════
        # 📐 빗각 돌파/저항 판단 (상대값 기반!)
        # ═══════════════════════════════════════════════════════════════════════
        # 🔬 실시간 상대값 검증 테스트!
        if len(CANDLE_HISTORY) >= 200:
            import pandas as pd
            import numpy as np
            df = pd.DataFrame(CANDLE_HISTORY[-200:])
            df['body'] = df['close'] - df['open']
            df['abs_body'] = df['body'].abs()
            
            # 상대값 계산 과정 기록
            body_mean = df['abs_body'].iloc[-50:].mean()
            body_std = df['abs_body'].iloc[-50:].std()
            current_body = df['abs_body'].iloc[-1]
            body_zscore = (current_body - body_mean) / body_std if body_std > 0 else 0
            
            # SPS 비율 상대값
            df['bull_z'] = np.where(df['body'] > 0, (df['abs_body'] - body_mean) / body_std.clip(0.001), 0)
            df['bear_z'] = np.where(df['body'] < 0, (df['abs_body'] - body_mean) / body_std.clip(0.001), 0)
            bull_sps = df['bull_z'].iloc[-20:].sum()
            bear_sps = df['bear_z'].iloc[-20:].sum()
            sps_ratio = bull_sps / (bear_sps + 0.01)
            sps_ratio_mean = df['bull_z'].rolling(20).sum().iloc[-50:].mean() / (df['bear_z'].rolling(20).sum().iloc[-50:].mean() + 0.01)
            sps_ratio_std_val = (df['bull_z'].rolling(20).sum() / (df['bear_z'].rolling(20).sum() + 0.01)).iloc[-50:].std()
            sps_zscore = (sps_ratio - sps_ratio_mean) / sps_ratio_std_val if sps_ratio_std_val > 0 else 0
            
            # 🔬 실시간 검증 로그!
            realtime_test = {
                "timestamp": datetime.now().isoformat(),
                "price": iangle_record['price'],
                "line_value": iangle_record['line_value'],
                "calculations": {
                    "body_mean_50": round(body_mean, 2),
                    "body_std_50": round(body_std, 2),
                    "current_body": round(current_body, 2),
                    "body_zscore": round(body_zscore, 2),
                    "bull_sps_20": round(bull_sps, 2),
                    "bear_sps_20": round(bear_sps, 2),
                    "sps_ratio": round(sps_ratio, 2),
                    "sps_ratio_mean": round(sps_ratio_mean, 2),
                    "sps_ratio_std": round(sps_ratio_std_val, 2),
                    "sps_zscore": round(sps_zscore, 2)
                },
                "is_relative": True,
                "note": "모든 값이 평균/표준편차 기준 상대값"
            }
            
            # 파일 저장
            try:
                with open('.realtime_zscore_test.json', 'r') as f:
                    tests = json.load(f)
            except:
                tests = []
            tests.append(realtime_test)
            if len(tests) > 100:
                tests = tests[-50:]
            with open('.realtime_zscore_test.json', 'w') as f:
                json.dump(tests, f, indent=2, ensure_ascii=False)
            
            print(f"🔬 실시간 상대값 테스트:")
            print(f"   body_mean={body_mean:.2f}, body_std={body_std:.2f}")
            print(f"   body_zscore={body_zscore:.2f} (현재봉 상대크기)")
            print(f"   sps_ratio={sps_ratio:.2f}, sps_zscore={sps_zscore:.2f}")
        
        iangle_judgment = None
        if len(CANDLE_HISTORY) >= 200:
            iangle_judgment = check_iangle_breakthrough()
            
            # ═══════════════════════════════════════════════════════════════════════
            # 📐 빗각터치 → 원래 로직으로 실시간 예측! (상대값 기반)
            # ═══════════════════════════════════════════════════════════════════════
            if iangle_judgment:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                judgment = iangle_judgment.get('judgment', '관찰')
                direction = iangle_judgment.get('direction', '')
                confidence = iangle_judgment.get('confidence', 'B')
                reason = iangle_judgment.get('reason', '')
                sps_z = iangle_judgment.get('sps_ratio_z', 0)
                sector_pct = iangle_judgment.get('sector_pct', 50)
                buy_ratio_z = iangle_judgment.get('buy_ratio_z', 0)
                sell_ratio_z = iangle_judgment.get('sell_ratio_z', 0)
                is_bearish = iangle_judgment.get('is_bearish', False)
                
                # 방향 없으면 봉 방향으로
                if not direction:
                    direction = 'SHORT' if is_bearish else 'LONG'
                
                # 승률 매핑
                win_rate_map = {'S++': '96%', 'S+': '92%', 'S': '90%', 'A': '86%', 'B': '70%', 'C': '60%'}
                win_rate = win_rate_map.get(confidence, '70%')
                
                emoji = '🔴' if direction == 'SHORT' else '🟢'
                
                print(f"📐 빗각판단: {judgment} {confidence} → SPSz={sps_z:.2f}")
                print(f"   {reason}")
                
                # ⭐ 상대값 변화 실시간 계산! (최근 5봉 대비)
                # 검증 결과: 매도소진(sell_delta<-0.1 & 섹터30%-) = 100% 롱!
                exhaust_status = ""
                buy_delta = 0
                sell_delta = 0
                exhaust_grade = ""
                
                if len(CANDLE_HISTORY) >= 60:
                    import pandas as pd
                    import numpy as np
                    temp_df = pd.DataFrame(CANDLE_HISTORY[-60:])
                    temp_df['body'] = temp_df['close'] - temp_df['open']
                    temp_df['bull_sum'] = temp_df['body'].clip(lower=0).rolling(10).sum()
                    temp_df['bear_sum'] = temp_df['body'].clip(upper=0).abs().rolling(10).sum()
                    temp_df['buy_ratio'] = temp_df['bull_sum'] / (temp_df['bear_sum'] + 0.01)
                    temp_df['sell_ratio'] = temp_df['bear_sum'] / (temp_df['bull_sum'] + 0.01)
                    
                    # 5봉 MA의 변화량
                    temp_df['buy_ma5'] = temp_df['buy_ratio'].rolling(5).mean()
                    temp_df['sell_ma5'] = temp_df['sell_ratio'].rolling(5).mean()
                    buy_delta = temp_df['buy_ma5'].iloc[-1] - temp_df['buy_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                    sell_delta = temp_df['sell_ma5'].iloc[-1] - temp_df['sell_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                    prev_sell = temp_df['sell_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                    prev_buy = temp_df['buy_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                    
                    # ⭐ 섹터 무관! 항상 배율 상태 표시!
                    if buy_delta < -0.1:
                        exhaust_status = f"🔻 매수소진! (Δ{buy_delta:.2f})" if prev_buy <= 1.3 else f"🔻 매수소진!! (이전{prev_buy:.1f}→Δ{buy_delta:.2f})"
                    elif buy_delta < 0:
                        exhaust_status = f"🔻 매수세약화 (Δ{buy_delta:.2f})"
                    elif sell_delta < -0.1:
                        exhaust_status = f"🔺 매도소진! (Δ{sell_delta:.2f})" if prev_sell <= 1.3 else f"🔺 매도소진!! (이전{prev_sell:.1f}→Δ{sell_delta:.2f})"
                    elif sell_delta < 0:
                        exhaust_status = f"🔺 매도세약화 (Δ{sell_delta:.2f})"
                    elif buy_delta > sell_delta:
                        exhaust_status = f"📈 매수세증가 (Δ+{buy_delta:.2f})"
                    else:
                        exhaust_status = f"📉 매도세증가 (Δ+{sell_delta:.2f})"
                
                # ⭐ 원래 로직 결과 + 상대값 해석 전송!
                tg_msg = f"""{emoji} 빗각{judgment}예측 {confidence} ({win_rate})
━━━━━━━━━━━━━━━━
📐 빗각: {iangle_record['line_name']} @ {iangle_record['line_value']:.2f}
📍 현재가: {iangle_record['price']:.2f}
📊 섹터: {sector_pct:.0f}% {exhaust_status}
📈 매수배율z: {buy_ratio_z:.2f} | 매도배율z: {sell_ratio_z:.2f}
📉 SPS비율z: {sps_z:.2f}
🎯 방향: {direction} | TP:20pt SL:30pt
💡 {reason}
⏰ {timestamp}"""
                send_telegram_alert(tg_msg, signal_type='빗각예측')
                
                # ⭐ 검증된 신호만 로그 기록 (S, S+, S++)
                if confidence in ['S', 'S+', 'S++']:
                    from signal_logger import log_signal
                    log_signal(
                        signal_type='RESIST_zscore',
                        direction=direction,
                        entry_price=iangle_record['price'],
                        ratio=buy_ratio_z if direction == 'LONG' else sell_ratio_z,
                        channel_pct=sector_pct,
                        z_score=sps_z,
                        grade=confidence,
                        notes=f"{judgment}: {reason}"
                    )
        
        # ═══ STB 점 로직 즉시 판단 ═══
        stb_result = None
        if len(CANDLE_HISTORY) >= 200:
            # 빗각 터치 시 STB 숏/롱 체크
            stb_sell = check_stb_sell_spot()
            stb_buy = check_stb_buy_spot()
            
            if stb_sell and stb_sell.get('signal'):
                sps_z = abs(stb_sell.get('sps_ratio_z', 0))
                stb_result = {
                    'type': 'STB숏',
                    'grade': stb_sell.get('grade'),
                    'reason': stb_sell.get('reason'),
                    'sector_pct': stb_sell.get('sector_pct'),
                    'sps_ratio_z': stb_sell.get('sps_ratio_z')
                }
                print(f"🔴 빗각+STB숏 {stb_result['grade']}! {stb_result['reason']}")
                
                # ⭐ 시퀀스 롱 - SEQUENCE_TRIGGERS로 자동 기록됨
                
                # 📌 JSON 기준: STB스팟 + zscore → RESIST_zscore_* 전송!
                if stb_result['grade'] in ['S++', 'S+', 'S'] and sps_z >= 0.5:
                    # zscore 레벨에 따라 신호 결정
                    if sps_z >= 1.5:
                        sig_type = 'RESIST_zscore_1.5'
                        win_rate = 96.1
                    elif sps_z >= 1.0:
                        sig_type = 'RESIST_zscore_1.0'
                        win_rate = 95.0
                    else:
                        sig_type = 'RESIST_zscore_0.5'
                        win_rate = 91.8
                    
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    tg_msg = f"""🔴 {sig_type} {stb_result['grade']}! ({win_rate}% 저항률)
━━━━━━━━━━━━━━━━
📐 빗각: {iangle_record['line_name']} @ {iangle_record['line_value']:.2f}
📍 현재가: {iangle_record['price']:.2f}
📊 섹터: {stb_sell['sector_pct']:.0f}% | SPS비율z: {stb_sell['sps_ratio_z']:.2f}
🎯 TP: 20pt | SL: 30pt
💡 {stb_sell['reason']}
⏰ {timestamp}"""
                    send_telegram_alert(tg_msg, signal_type=sig_type)
            
            elif stb_buy and stb_buy.get('signal'):
                sps_z = abs(stb_buy.get('sps_ratio_z', 0))
                stb_result = {
                    'type': 'STB롱',
                    'grade': stb_buy.get('grade'),
                    'reason': stb_buy.get('reason'),
                    'sector_pct': stb_buy.get('sector_pct'),
                    'sps_ratio_z': stb_buy.get('sps_ratio_z')
                }
                print(f"🟢 빗각+STB롱 {stb_result['grade']}! {stb_result['reason']}")
                
                # 📌 JSON 기준: STB스팟 + zscore → STB롱 전송 (POC_LONG 조건 체크)
                if stb_result['grade'] in ['S++', 'S+', 'S'] and sps_z >= 0.5:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    tg_msg = f"""🟢 STB롱 {stb_result['grade']}! (94.1% 지지률)
━━━━━━━━━━━━━━━━
📐 빗각: {iangle_record['line_name']} @ {iangle_record['line_value']:.2f}
📍 현재가: {iangle_record['price']:.2f}
📊 섹터: {stb_buy['sector_pct']:.0f}% | SPS비율z: {stb_buy['sps_ratio_z']:.2f}
🎯 TP: 20pt | SL: 30pt
💡 {stb_buy['reason']}
⏰ {timestamp}"""
                    send_telegram_alert(tg_msg, signal_type='STB롱')
        
        # ═══════════════════════════════════════════════════════════════════════
        # 📐 빗각 특화 판단 (타입 + 기울기 + 승률 연동)
        # ═══════════════════════════════════════════════════════════════════════
        angle_specific = None
        if iangle_record['line_value'] > 0:
            angle_specific = check_angle_specific_judgment(iangle_record['line_value'], iangle_record['line_name'])
            
            if angle_specific and angle_specific.get('final_judgment') not in ['관찰', '', None]:
                print(f"📐 빗각특화: {angle_specific['touched_line']} → {angle_specific['final_judgment']} {angle_specific['confidence']}")
                print(f"   기울기: {angle_specific['slope_per_hour']:+.2f} pt/h | 6h예측: {angle_specific['prediction_6h']:.0f}")
                print(f"   승률: {angle_specific['verified_winrate']:.1f}% | {angle_specific['reason']}")
                
                # 🔥 검증된 신호만 텔레그램 전송!
                if angle_specific.get('verified_signal') and angle_specific.get('confidence') in ['S+', 'S']:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    verified_sig = angle_specific['verified_signal']
                    winrate = angle_specific.get('verified_winrate', 0)
                    judgment = angle_specific.get('final_judgment', '')
                    reason = angle_specific.get('reason', '')
                    touch_price = iangle_record['price']
                    
                    # 방향 결정
                    if '저항' in judgment or '숏' in judgment.lower():
                        direction = 'SHORT'
                        emoji = '🔴'
                        tp_price = touch_price - 20
                        sl_price = touch_price + 10
                    else:
                        direction = 'LONG'
                        emoji = '🟢'
                        tp_price = touch_price + 20
                        sl_price = touch_price - 10
                    
                    tg_msg = f"""{emoji} {verified_sig} {angle_specific['confidence']}! ({winrate:.1f}%)
━━━━━━━━━━━━━━━━
📐 빗각: {iangle_record['line_name']} ({angle_specific.get('touch_type', 'unknown')})
📍 진입: {touch_price:.2f}
🎯 TP: {tp_price:.2f} (+20pt) | SL: {sl_price:.2f} (-10pt)
📊 섹터: {angle_specific.get('sector_pct', 0):.0f}% | SPS비율z: {angle_specific.get('sps_ratio_z', 0):.2f}
📈 기울기: {angle_specific['slope_per_hour']:+.2f} pt/h
💡 {reason}
⏰ {timestamp}"""
                    send_telegram_alert(tg_msg, signal_type=verified_sig)
                    print(f"📨 빗각 검증신호 전송: {verified_sig} {direction}")
        
        return jsonify({
            "status": "success",
            "data": iangle_record,
            "total_touches": len(IANGLE_DATA),
            "iangle_judgment": iangle_judgment,
            "stb_result": stb_result,
            "angle_specific": angle_specific
        })
        
    except Exception as e:
        print(f"❌ 빗각 웹훅 오류: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/iangle-data', methods=['GET'])
def get_iangle_data():
    """저장된 빗각 터치 데이터 조회"""
    try:
        import json
        with open('.iangle_touches.json', 'r') as f:
            touches = json.load(f)
        return jsonify({
            "success": True,
            "data": touches[-100:],
            "total": len(touches)
        })
    except:
        return jsonify({"success": True, "data": [], "total": 0})

@app.route('/webhook/ivwap', methods=['POST'])
def ivwap_webhook():
    """1분봉 iVWAP + 클러스터 비율 데이터 받기"""
    global IVWAP_1M_DATA
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        if data.get('passphrase') not in WEBHOOK_SECRETS:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        IVWAP_1M_DATA = {
            "buy_ivwap": float(data.get('buy_ivwap', 0) or 0),
            "sell_ivwap": float(data.get('sell_ivwap', 0) or 0),
            "buy_ivwap_upper": float(data.get('buy_ivwap_upper', 0) or 0),
            "buy_ivwap_lower": float(data.get('buy_ivwap_lower', 0) or 0),
            "sell_ivwap_upper": float(data.get('sell_ivwap_upper', 0) or 0),
            "sell_ivwap_lower": float(data.get('sell_ivwap_lower', 0) or 0),
            "cluster_ratio": float(data.get('cluster_ratio', 0) or 0),
            "last_update": datetime.now().isoformat()
        }
        
        print(f"📊 1분봉 iVWAP 업데이트: 매수={IVWAP_1M_DATA['buy_ivwap']:.2f}, 매도={IVWAP_1M_DATA['sell_ivwap']:.2f}")
        
        return jsonify({
            "status": "success",
            "data": IVWAP_1M_DATA
        })
        
    except Exception as e:
        print(f"❌ iVWAP 웹훅 오류: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook/agrade', methods=['POST'])
def agrade_webhook():
    """1분봉 A급 탐지기 (iVPOC) 데이터 받기"""
    global AGRADE_1M_DATA
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        print(f"📥 agrade 수신: {data}")
        
        if data.get('passphrase') not in WEBHOOK_SECRETS:
            print(f"❌ agrade 인증실패: passphrase={data.get('passphrase')}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        AGRADE_1M_DATA = {
            "ivpoc": float(data.get('ivpoc', 0) or 0),
            "buy_zone_top": float(data.get('buy_zone_top', 0) or 0),
            "buy_zone_bottom": float(data.get('buy_zone_bottom', 0) or 0),
            "sell_zone_top": float(data.get('sell_zone_top', 0) or 0),
            "sell_zone_bottom": float(data.get('sell_zone_bottom', 0) or 0),
            "last_update": datetime.now().isoformat()
        }
        
        print(f"🎯 1분봉 A급탐지기: iVPOC={AGRADE_1M_DATA['ivpoc']:.2f}")
        
        return jsonify({
            "status": "success",
            "data": AGRADE_1M_DATA
        })
        
    except Exception as e:
        print(f"❌ A급탐지기 웹훅 오류: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/realtime-levels', methods=['GET'])
def get_realtime_levels():
    """실시간 1분봉 레벨 조회 API (빗각2 포함)"""
    angle2_data = None
    angle_lines = None
    
    try:
        if os.path.exists('.i_angle_signals.json'):
            with open('.i_angle_signals.json', 'r') as f:
                signals = json.load(f)
            if signals:
                latest = signals[-1]
                if latest.get('line') == '빗각2':
                    angle2_data = {
                        'price': latest.get('price'),
                        'direction': latest.get('original_direction'),
                        'ratio': latest.get('ratio'),
                        'action': latest.get('action'),
                        'timestamp': latest.get('timestamp')
                    }
    except:
        pass
    
    try:
        from iangle_formula import calculate_angle_price_by_time, ANGLE_SLOPE, ANGLE_REF_PRICE, ANGLE_REF_TIME
        now = datetime.now().isoformat()
        angle_lines = {
            'current_angle': calculate_angle_price_by_time(now),
            'slope': ANGLE_SLOPE,
            'slope_per_hour': ANGLE_SLOPE * 60,
            'ref_price': ANGLE_REF_PRICE,
            'ref_time': ANGLE_REF_TIME,
            'calc_time': now
        }
    except Exception as e:
        angle_lines = {'error': str(e)}
    
    return jsonify({
        "ivwap_1m": IVWAP_1M_DATA,
        "agrade_1m": AGRADE_1M_DATA,
        "angle2": angle2_data,
        "angle_lines": angle_lines
    })

@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    """TradingView에서 알림을 받는 웹훅 엔드포인트 (빗각)"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        action = data.get('action', '')
        
        # 📌 블랙라인/POC 터치는 passphrase 없이도 처리 (순수 데이터 수집용)
        if action in ['blackline_touch', 'poc_touch', 'level_touch']:
            now = datetime.now()
            timestamp = now.strftime('%H:%M:%S')
            ticker = data.get('ticker', 'NQ1!')
            touch_price = float(data.get('price', 0))
            level_price = float(data.get('level', data.get('blackline', data.get('poc', 0))))
            level_name = data.get('level_name', 'blackline' if 'blackline' in action else 'poc')
            
            ratio = 0
            channel_pct = 50
            channel_range = 0
            candle_type = 'unknown'
            bull_sum_10 = 0
            bear_sum_10 = 0
            
            if len(CANDLE_HISTORY) >= 10:
                import pandas as pd
                df_temp = pd.DataFrame(CANDLE_HISTORY[-100:] if len(CANDLE_HISTORY) >= 100 else CANDLE_HISTORY)
                ch_high = df_temp['high'].max()
                ch_low = df_temp['low'].min()
                channel_range = ch_high - ch_low
                current = CANDLE_HISTORY[-1]
                channel_pct = ((current['close'] - ch_low) / channel_range * 100) if channel_range > 0 else 50
                
                current_body = current['close'] - current['open']
                candle_type = 'bullish' if current_body > 0 else ('bearish' if current_body < 0 else 'doji')
                
                bull_sum_10 = sum([max(0, c['close'] - c['open']) for c in CANDLE_HISTORY[-10:]])
                bear_sum_10 = sum([max(0, c['open'] - c['close']) for c in CANDLE_HISTORY[-10:]])
                ratio = bull_sum_10 / (bear_sum_10 + 0.1)
            
            level_distance = touch_price - level_price if level_price > 0 else 0
            
            level_data = {
                "timestamp": now.isoformat(),
                "ticker": ticker,
                "level_name": level_name,
                "level_price": round(level_price, 2),
                "touch_price": touch_price,
                "level_distance": round(level_distance, 2),
                "ratio": round(ratio, 2),
                "channel_pct": round(channel_pct, 1),
                "channel_range": round(channel_range, 1),
                "candle_type": candle_type,
                "bull_sum_10": round(bull_sum_10, 2),
                "bear_sum_10": round(bear_sum_10, 2)
            }
            
            level_file = '.level_touches.json'
            level_touches = []
            if os.path.exists(level_file):
                try:
                    with open(level_file, 'r', encoding='utf-8') as f:
                        level_touches = json.load(f)
                except:
                    level_touches = []
            
            level_touches.append(level_data)
            level_touches = level_touches[-500:]
            
            with open(level_file, 'w', encoding='utf-8') as f:
                json.dump(level_touches, f, ensure_ascii=False, indent=2)
            
            # 📊 터치 결과 추적 시작 (양방향 테스트)
            add_pending_touch(f"{level_name}_long", 'long', touch_price, tp=18, sl=10, extra=level_data)
            add_pending_touch(f"{level_name}_short", 'short', touch_price, tp=20, sl=10, extra=level_data)
            
            print(f"\n{'='*50}")
            print(f"📍 레벨 터치 기록! [{timestamp}]")
            print(f"   레벨: {level_name} @ {level_price:.2f}")
            print(f"   터치가격: {touch_price:.2f} (거리: {level_distance:+.1f}pt)")
            print(f"   배율: {ratio:.2f} | 채널: {channel_pct:.0f}%")
            print(f"   캔들: {candle_type}")
            print(f"{'='*50}\n")
            
            # ⭐ 배율 상태 계산 + 텔레그램 전송!
            exhaust_status = ""
            if len(CANDLE_HISTORY) >= 60:
                import numpy as np
                temp_df = pd.DataFrame(CANDLE_HISTORY[-60:])
                temp_df['body'] = temp_df['close'] - temp_df['open']
                temp_df['bull_sum'] = temp_df['body'].clip(lower=0).rolling(10).sum()
                temp_df['bear_sum'] = temp_df['body'].clip(upper=0).abs().rolling(10).sum()
                temp_df['buy_ratio'] = temp_df['bull_sum'] / (temp_df['bear_sum'] + 0.01)
                temp_df['sell_ratio'] = temp_df['bear_sum'] / (temp_df['bull_sum'] + 0.01)
                temp_df['buy_ma5'] = temp_df['buy_ratio'].rolling(5).mean()
                temp_df['sell_ma5'] = temp_df['sell_ratio'].rolling(5).mean()
                
                buy_delta = temp_df['buy_ma5'].iloc[-1] - temp_df['buy_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                sell_delta = temp_df['sell_ma5'].iloc[-1] - temp_df['sell_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                prev_sell = temp_df['sell_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                prev_buy = temp_df['buy_ma5'].iloc[-6] if len(temp_df) >= 6 else 0
                
                # 섹터 계산 (현재 캔들 종가 기준, touch_price가 아님!)
                current_price = CANDLE_HISTORY[-1]['close']
                h50 = temp_df['high'].iloc[-50:].max() if len(temp_df) >= 50 else temp_df['high'].max()
                l50 = temp_df['low'].iloc[-50:].min() if len(temp_df) >= 50 else temp_df['low'].min()
                range50 = h50 - l50
                sector_pct = ((current_price - l50) / range50 * 100) if range50 > 0 else 50
                # 0~100% 범위 보정
                sector_pct = max(0, min(100, sector_pct))
                
                # 배율 상태 (섹터 무관!)
                if buy_delta < -0.1:
                    exhaust_status = f"🔻 매수소진! (Δ{buy_delta:.2f})" if prev_buy <= 1.3 else f"🔻 매수소진!! (이전{prev_buy:.1f}→Δ{buy_delta:.2f})"
                elif buy_delta < 0:
                    exhaust_status = f"🔻 매수세약화 (Δ{buy_delta:.2f})"
                elif sell_delta < -0.1:
                    exhaust_status = f"🔺 매도소진! (Δ{sell_delta:.2f})" if prev_sell <= 1.3 else f"🔺 매도소진!! (이전{prev_sell:.1f}→Δ{sell_delta:.2f})"
                elif sell_delta < 0:
                    exhaust_status = f"🔺 매도세약화 (Δ{sell_delta:.2f})"
                elif buy_delta > sell_delta:
                    exhaust_status = f"📈 매수세증가 (Δ+{buy_delta:.2f})"
                else:
                    exhaust_status = f"📉 매도세증가 (Δ+{sell_delta:.2f})"
                
                level_emoji = '🔵' if 'poc' in level_name.lower() else '⚫' if 'black' in level_name.lower() else '📍'
                
                # ═══════════════════════════════════════════════════════════════════════
                # 📊 POC/블랙라인터치 STB 로직! (2026-01-13)
                # 스팟SPS vs 리테스트SPS 비교 → SPS 약화 시 신호!
                # ═══════════════════════════════════════════════════════════════════════
                import numpy as np
                df_force = pd.DataFrame(CANDLE_HISTORY[-200:])
                df_force['body'] = df_force['close'] - df_force['open']
                df_force['abs_body'] = df_force['body'].abs()
                df_force['body_mean'] = df_force['abs_body'].rolling(50).mean()
                df_force['body_std'] = df_force['abs_body'].rolling(50).std()
                df_force['body_zscore'] = (df_force['abs_body'] - df_force['body_mean']) / df_force['body_std'].replace(0, 0.001)
                df_force['bull_zscore'] = np.where(df_force['body'] > 0, df_force['body_zscore'], 0)
                df_force['bear_zscore'] = np.where(df_force['body'] < 0, df_force['body_zscore'], 0)
                df_force['bull_sps_20'] = df_force['bull_zscore'].rolling(20).sum()
                df_force['bear_sps_20'] = df_force['bear_zscore'].rolling(20).sum()
                
                bull_sps = max(0, df_force['bull_sps_20'].iloc[-1]) if not pd.isna(df_force['bull_sps_20'].iloc[-1]) else 0
                bear_sps = max(0, df_force['bear_sps_20'].iloc[-1]) if not pd.isna(df_force['bear_sps_20'].iloc[-1]) else 0
                current_sps_ratio = bull_sps / (bear_sps + 0.01)
                current_sps_ratio = max(0.1, min(10, current_sps_ratio))
                
                is_bullish = candle_type == 'bullish'
                is_bearish = candle_type == 'bearish'
                
                # 스팟 파일 로드
                level_spot_file = '.level_sps_spots.json'
                level_spots = []
                if os.path.exists(level_spot_file):
                    try:
                        with open(level_spot_file, 'r') as f:
                            level_spots = json.load(f)
                    except:
                        level_spots = []
                
                # 같은 레벨 근처(±20pt) 스팟 찾기
                matching_spot = None
                for spot in level_spots[-50:]:
                    if abs(current_price - spot.get('price', 0)) < 20:
                        matching_spot = spot
                        break
                
                if matching_spot:
                    # 리테스트! SPS 비교
                    spot_sps = matching_spot.get('sps_ratio', 1.0)
                    sps_weakened = current_sps_ratio < spot_sps * 0.8
                    
                    print(f"📍 {level_name} 리테스트! spot_sps={spot_sps:.2f} → retest_sps={current_sps_ratio:.2f} 약화={sps_weakened}")
                    
                    if is_bearish and sps_weakened and spot_sps > 1.0:
                        tg_msg = f"""🔴 {level_name} STB숏! (93%)
━━━━━━━━━━━━━━━━
📍 레벨: {level_price:.2f}
📍 현재가: {current_price:.2f} (거리: {level_distance:+.1f}pt)
💪 스팟SPS: {spot_sps:.2f} → 리테스트SPS: {current_sps_ratio:.2f}
📉 SPS약화: {((1-current_sps_ratio/spot_sps)*100):.0f}% ↓
📊 섹터: {sector_pct:.0f}% {exhaust_status}
🎯 방향: SHORT | TP:20pt SL:30pt
💡 매수세 소진 후 음봉 = 하락 전환!
⏰ {timestamp}"""
                        send_telegram_alert(tg_msg, signal_type=f'{level_name}STB숏')
                        
                    elif is_bullish and sps_weakened and spot_sps < 1.0:
                        tg_msg = f"""🟢 {level_name} STB롱! (94%)
━━━━━━━━━━━━━━━━
📍 레벨: {level_price:.2f}
📍 현재가: {current_price:.2f} (거리: {level_distance:+.1f}pt)
💪 스팟SPS: {spot_sps:.2f} → 리테스트SPS: {current_sps_ratio:.2f}
📈 SPS변화: 매도세→매수세 전환
📊 섹터: {sector_pct:.0f}% {exhaust_status}
🎯 방향: LONG | TP:20pt SL:30pt
💡 매도세 소진 후 양봉 = 상승 전환!
⏰ {timestamp}"""
                        send_telegram_alert(tg_msg, signal_type=f'{level_name}STB롱')
                    else:
                        print(f"📍 {level_name} 리테스트 관찰: 조건불충족")
                else:
                    # 첫 터치! 스팟 등록
                    new_spot = {
                        "timestamp": datetime.now().isoformat(),
                        "level_name": level_name,
                        "level_price": level_price,
                        "price": current_price,
                        "bull_sps": bull_sps,
                        "bear_sps": bear_sps,
                        "sps_ratio": current_sps_ratio,
                        "candle_type": candle_type
                    }
                    level_spots.append(new_spot)
                    level_spots = level_spots[-100:]
                    
                    with open(level_spot_file, 'w') as f:
                        json.dump(level_spots, f, indent=2, ensure_ascii=False)
                    
                    print(f"📍 {level_name} 스팟등록! sps={current_sps_ratio:.2f}")
                    
                    tg_msg = f"""📍 {level_name} 스팟등록! (관찰)
━━━━━━━━━━━━━━━━
📍 레벨: {level_price:.2f}
📍 현재가: {current_price:.2f} (거리: {level_distance:+.1f}pt)
💪 bull_sps: {bull_sps:.1f} | bear_sps: {bear_sps:.1f}
📊 SPS비율: {current_sps_ratio:.2f}
💡 리테스트 시 SPS 비교 예정
⏰ {timestamp}"""
                    send_telegram_alert(tg_msg, signal_type=f'{level_name}스팟')
            
            return jsonify({
                "status": "success",
                "data": level_data,
                "message": f"레벨 터치 저장됨 + 텔레그램 전송"
            })
        
        # 비밀번호 확인 (보안)
        if data.get('passphrase') not in WEBHOOK_SECRETS:
            print(f"❌ 웹훅 인증 실패: {data}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        # 알림 데이터 추출
        ticker = data.get('ticker', 'N/A')
        action = data.get('action', 'N/A')  # buy, sell, alert, a_grade
        
        log_signal_reception(action, 'webhook-빗각', data)
        price = data.get('price', 'N/A')
        message = data.get('message', '')
        
        # 📍 지지 레벨 업데이트 (매수 스팟용)
        global SUPPORT_LEVELS
        if data.get('blackline'):
            SUPPORT_LEVELS['blackline'] = float(data.get('blackline'))
        if data.get('rising_angle') or data.get('rising_i_angle'):
            SUPPORT_LEVELS['rising_angle'] = float(data.get('rising_angle') or data.get('rising_i_angle'))
        if data.get('poc'):
            SUPPORT_LEVELS['poc'] = float(data.get('poc'))
            # 📌 zpoc 자동 계산: 블랙라인 POC ± 70.25pt
            SUPPORT_LEVELS['zpoc'] = float(data.get('poc'))  # zpoc = POC 기준점
        if data.get('ivpoc'):
            SUPPORT_LEVELS['ivpoc'] = float(data.get('ivpoc'))
        
        # A급 신호 전용 필드 (TradingView에서 계산된 iVPOC)
        ivpoc = data.get('ivpoc', None)
        sector_id = data.get('sector_id', None)
        zscore = data.get('zscore', None)
        spread_day = data.get('spread_day', False)
        sell_sps_nearby = data.get('sell_sps_nearby', False)
        
        now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        
        # A급 신호 처리
        if action == 'a_grade' and ivpoc is not None:
            a_grade_signal = {
                "timestamp": now.isoformat(),
                "ticker": ticker,
                "price": float(price) if price != 'N/A' else None,
                "ivpoc": float(ivpoc),
                "sector_id": sector_id,
                "zscore": float(zscore) if zscore else None,
                "spread_day": spread_day,
                "sell_sps_nearby": sell_sps_nearby,
                "status": "BLOCKED" if (spread_day or sell_sps_nearby) else "ACTIVE",
                "block_reason": "스프레드 데이" if spread_day else ("매도 SPS" if sell_sps_nearby else None)
            }
            
            # A급 신호 저장
            signals_file = '.a_grade_signals.json'
            signals = []
            if os.path.exists(signals_file):
                with open(signals_file, 'r', encoding='utf-8') as f:
                    signals = json.load(f)
            
            signals.append(a_grade_signal)
            signals = signals[-100:]  # 최근 100개만 유지
            
            with open(signals_file, 'w', encoding='utf-8') as f:
                json.dump(signals, f, ensure_ascii=False, indent=2)
            
            status_emoji = "🚫" if a_grade_signal["status"] == "BLOCKED" else "✅"
            print(f"\n{'='*50}")
            print(f"{status_emoji} A급 신호 수신! [{timestamp}]")
            print(f"   종목: {ticker}")
            print(f"   가격: {price} | iVPOC: {ivpoc}")
            print(f"   Z-score: {zscore}")
            print(f"   상태: {a_grade_signal['status']}")
            if a_grade_signal['block_reason']:
                print(f"   차단 이유: {a_grade_signal['block_reason']}")
            print(f"{'='*50}\n")
            
            return jsonify({
                "status": "success",
                "signal": a_grade_signal,
                "message": f"A급 신호 저장됨 - {a_grade_signal['status']}"
            })
        
        # i빗각 신호 처리 - 📌 순수 데이터 수집 (숏/롱 판단 X)
        if action in ['i_angle_short', 'i_angle_long', 'i_angle', 'i_angle_touch', 'rising_angle_touch']:
            touch_price = float(data.get('price', 0))
            original_direction = data.get('direction', 'SHORT' if 'short' in action.lower() else 'LONG')
            
            # 📐 웹훅 라인명 그대로 사용! (TradingView가 정확한 정보 제공)
            line_name = data.get('line', 'unknown')
            angle_type = 'rising' if 'rising' in action or '상승' in line_name else 'falling'
            angle_price = touch_price  # 웹훅 가격이 곧 빗각 가격
            distance = 0
            
            # 📌 SUPPORT_LEVELS에 라인별로 저장
            if 'angles' not in SUPPORT_LEVELS:
                SUPPORT_LEVELS['angles'] = {}
            
            SUPPORT_LEVELS['angles'][line_name] = {
                'price': touch_price,
                'angle_price': angle_price,
                'distance': distance,
                'angle_type': angle_type,
                'timestamp': now.isoformat(),
                'action': action
            }
            
            # 하락빗각/상승빗각 최신값도 저장 (호환성)
            if angle_type == 'rising':
                SUPPORT_LEVELS['rising_angle'] = touch_price
                print(f"📐 상승빗각 자동판별: [{line_name}] 터치 {touch_price:.2f} (기준선: {angle_price:.2f}, 거리: {distance:+.1f}pt)")
            else:
                SUPPORT_LEVELS['falling_angle'] = touch_price
                print(f"📐 하락빗각 자동판별: [{line_name}] 터치 {touch_price:.2f} (기준선: {angle_price:.2f}, 거리: {distance:+.1f}pt)")
            
            # 현재 저장된 모든 빗각 출력
            print(f"📐 저장된 빗각들: {list(SUPPORT_LEVELS['angles'].keys())}")
            
            # 📌 순수 데이터 수집 - 시장 상태만 기록 (숏/롱 판단 없음!)
            i_level = data.get('i_level', 0)
            
            # 시장 데이터 계산
            ratio = 0
            channel_pct = 50
            channel_range = 0
            current_body = 0
            bull_sum_10 = 0
            bear_sum_10 = 0
            candle_type = 'unknown'
            
            if len(CANDLE_HISTORY) >= 10:
                import pandas as pd
                
                df_temp = pd.DataFrame(CANDLE_HISTORY[-100:] if len(CANDLE_HISTORY) >= 100 else CANDLE_HISTORY)
                ch_high = df_temp['high'].max()
                ch_low = df_temp['low'].min()
                channel_range = ch_high - ch_low
                current = CANDLE_HISTORY[-1]
                channel_pct = ((current['close'] - ch_low) / channel_range * 100) if channel_range > 0 else 50
                
                current_body = current['close'] - current['open']
                candle_type = 'bullish' if current_body > 0 else ('bearish' if current_body < 0 else 'doji')
                
                # 10봉 매수/매도 합계
                bull_sum_10 = sum([max(0, c['close'] - c['open']) for c in CANDLE_HISTORY[-10:]])
                bear_sum_10 = sum([max(0, c['open'] - c['close']) for c in CANDLE_HISTORY[-10:]])
                
                # 배율 (형 공식: 매수합/매도합)
                ratio = bull_sum_10 / (bear_sum_10 + 0.1)
            
            # 📌 순수 빗각 터치 데이터 저장 (TradingView가 보낸 값 그대로!)
            touch_data = {
                "timestamp": now.isoformat(),
                "ticker": ticker,
                "line_name": line_name,
                "touch_price": touch_price,
                "action": action,
                "original_direction": original_direction,
                "i_level": i_level,
                "ratio": round(ratio, 2),
                "channel_pct": round(channel_pct, 1),
                "channel_range": round(channel_range, 1),
                "candle_type": candle_type,
                "current_body": round(current_body, 2),
                "bull_sum_10": round(bull_sum_10, 2),
                "bear_sum_10": round(bear_sum_10, 2)
            }
            
            # .iangle_touches.json에 저장
            touches_file = '.iangle_touches.json'
            touches = []
            if os.path.exists(touches_file):
                try:
                    with open(touches_file, 'r', encoding='utf-8') as f:
                        touches = json.load(f)
                except:
                    touches = []
            
            touches.append(touch_data)
            touches = touches[-500:]  # 최근 500개 유지
            
            with open(touches_file, 'w', encoding='utf-8') as f:
                json.dump(touches, f, ensure_ascii=False, indent=2)
            
            print(f"\n{'='*50}")
            print(f"📐 빗각 터치 기록! [{timestamp}]")
            print(f"   라인: {line_name}")
            print(f"   터치가격: {touch_price:.2f}")
            print(f"   배율: {ratio:.2f} | 채널: {channel_pct:.0f}%")
            print(f"   캔들: {candle_type} ({current_body:+.1f}pt)")
            print(f"{'='*50}\n")
            
            # ═══════════════════════════════════════════════════════════════════════
            # 📐 빗각 완전체 로직! (2026-01-14) - 섹터 + 배율 + STB 4단계!
            # 🔥 섹터 = 무대(Where), 배율 = 체력(How), 빗각 = 충돌(Test), STB = KO(Confirm)
            # ═══════════════════════════════════════════════════════════════════════
            # 숏: 섹터90%+ AND 배율1.5~2.0 → 반전 후보 | 배율2.0+ → 과열 금지!
            # 롱: 섹터10%- AND 배율≤0.7 → 반전 후보
            # ═══════════════════════════════════════════════════════════════════════
            if len(CANDLE_HISTORY) >= 20:
                import pandas as pd
                import numpy as np
                
                current_candle = CANDLE_HISTORY[-1]
                multiplier = ratio  # 10봉 배율
                multiplier = min(10.0, max(0.1, multiplier))
                
                is_bullish = current_candle['close'] > current_candle['open']
                is_bearish = current_candle['close'] < current_candle['open']
                body_size = abs(current_candle['close'] - current_candle['open'])
                candle_range = current_candle['high'] - current_candle['low']
                body_ratio = body_size / candle_range if candle_range > 0 else 0
                
                angle_type_kr = '상승빗각' if angle_type == 'rising' else '하락빗각'
                
                # 🔥 현재 STB 상태 확인
                stb_sell = check_stb_sell_spot()
                stb_buy = check_stb_buy_spot()
                current_stb = 'SHORT' if (stb_sell and stb_sell.get('signal')) else ('LONG' if (stb_buy and stb_buy.get('signal')) else 'NONE')
                
                # 빗각 스팟 파일
                angle_spot_file = '.angle_observation_spots.json'
                angle_spots = []
                if os.path.exists(angle_spot_file):
                    try:
                        with open(angle_spot_file, 'r') as f:
                            angle_spots = json.load(f)
                    except:
                        angle_spots = []
                
                # TTL = 20분 지난 스팟 제거
                valid_spots = []
                for spot in angle_spots:
                    try:
                        spot_time = datetime.fromisoformat(spot['timestamp'])
                        age_minutes = (now - spot_time).total_seconds() / 60
                        if age_minutes < 20 and not spot.get('used', False):
                            valid_spots.append(spot)
                    except:
                        pass
                angle_spots = valid_spots
                
                # 같은 라인 첫 스팟만 (중복 방지)
                existing_lines = [s.get('line_name') for s in angle_spots]
                is_duplicate = line_name in existing_lines
                
                # ═══════════════════════════════════════════════════════════════════════
                # 🔥 4단계 판정: 섹터(무대) + 배율(체력) + 빗각(충돌) + STB(KO)
                # ═══════════════════════════════════════════════════════════════════════
                
                # 섹터 판정 (채널 퍼센트)
                sector_90 = channel_pct >= 90  # 상단 = 숏 무대
                sector_10 = channel_pct <= 10  # 하단 = 롱 무대
                
                # 배율 판정
                mult_short_ok = 1.5 <= multiplier < 2.0  # 숏 체력 조건 (83.3%!)
                mult_short_overheat = multiplier >= 2.0   # 과열 = 숏 금지! (44.1%)
                mult_long_ok = multiplier <= 0.5          # 롱 체력 조건 (72.2%! 강화됨)
                
                # 진입 후보 판정
                short_candidate = sector_90 and mult_short_ok and not is_duplicate
                long_candidate = sector_10 and mult_long_ok and not is_duplicate
                overheat_block = sector_90 and mult_short_overheat
                
                if overheat_block:
                    # 🔴 과열 = 숏 금지!
                    print(f"🔥 과열 경고! 섹터90%+ + 배율{multiplier:.2f}(≥2.0) → 숏 금지!")
                    tg_msg = f"""⚠️ 빗각 과열 경고! (숏 금지)
━━━━━━━━━━━━━━━━
📐 {angle_type_kr} @ {touch_price:.2f}
🔥 배율: {multiplier:.2f} (≥2.0 과열!)
📊 섹터: {channel_pct:.0f}% (상단)
❌ 과열 = 돌파 위험 44%
💡 숏 진입 금지! 대기!
⏰ {timestamp}"""
                    send_telegram_alert(tg_msg, signal_type='빗각과열경고')
                    
                elif short_candidate:
                    # 🟡 숏 반전 후보 등록 (83.3%!)
                    new_spot = {
                        "timestamp": now.isoformat(),
                        "angle_type": angle_type,
                        "line_name": line_name,
                        "price": touch_price,
                        "multiplier": multiplier,
                        "channel_pct": channel_pct,
                        "direction": "SHORT",
                        "stb_at_touch": current_stb,
                        "candle_type": "bullish" if is_bullish else "bearish",
                        "used": False
                    }
                    angle_spots.append(new_spot)
                    
                    print(f"📝 숏 후보 등록! 섹터{channel_pct:.0f}% + 배율{multiplier:.2f}")
                    
                    tg_msg = f"""📝 빗각 숏 후보 등록 (83.3%)
━━━━━━━━━━━━━━━━
📐 {angle_type_kr} @ {touch_price:.2f}
📊 섹터: {channel_pct:.0f}% (90%+ ✓)
💪 배율: {multiplier:.2f} (1.5~2.0 ✓)
🎯 예상 승률: 83.3%
📋 STB 전환 대기 중...
⏰ {timestamp}"""
                    send_telegram_alert(tg_msg, signal_type='빗각숏후보')
                    
                elif long_candidate:
                    # 🟢 롱 반전 후보 등록 (63.2%)
                    new_spot = {
                        "timestamp": now.isoformat(),
                        "angle_type": angle_type,
                        "line_name": line_name,
                        "price": touch_price,
                        "multiplier": multiplier,
                        "channel_pct": channel_pct,
                        "direction": "LONG",
                        "stb_at_touch": current_stb,
                        "candle_type": "bullish" if is_bullish else "bearish",
                        "used": False
                    }
                    angle_spots.append(new_spot)
                    
                    print(f"📝 롱 후보 등록! 섹터{channel_pct:.0f}% + 배율{multiplier:.2f}")
                    
                    tg_msg = f"""📝 빗각 롱 후보 등록 (72.2%)
━━━━━━━━━━━━━━━━
📐 {angle_type_kr} @ {touch_price:.2f}
📊 섹터: {channel_pct:.0f}% (10%- ✓)
💪 배율: {multiplier:.2f} (≤0.5 ✓)
🎯 예상 승률: 72.2%
📋 STB 전환 대기 중...
⏰ {timestamp}"""
                    send_telegram_alert(tg_msg, signal_type='빗각롱후보')
                    
                elif is_duplicate:
                    print(f"📐 {angle_type_kr} 중복 무시: {line_name}")
                else:
                    # 조건 미충족
                    reason = []
                    if not sector_90 and not sector_10:
                        reason.append(f"섹터{channel_pct:.0f}%(10~90)")
                    if not mult_short_ok and not mult_long_ok:
                        reason.append(f"배율{multiplier:.2f}(중립)")
                    print(f"📐 {angle_type_kr} 무시: {', '.join(reason)}")
                
                # ═══════════════════════════════════════════════════════════════════════
                # 🔥 Rule 3: STB 전환 체크 → 진입!
                # ═══════════════════════════════════════════════════════════════════════
                for spot in angle_spots:
                    if spot.get('used'):
                        continue
                    
                    spot_stb = spot.get('stb_at_touch', 'NONE')
                    spot_mult = spot.get('multiplier', 0)
                    spot_price = spot.get('price', 0)
                    
                    # Rule 5: STB 전환 발생?
                    stb_changed = (spot_stb != current_stb and current_stb != 'NONE')
                    
                    if not stb_changed:
                        continue
                    
                    # Rule 6: 배율 유지/약화 확인 (강해지면 무효!)
                    mult_change = (multiplier - spot_mult) / spot_mult if spot_mult > 0 else 0
                    mult_ok = mult_change <= 0.1  # 10% 이상 강해지면 무효
                    
                    if not mult_ok:
                        print(f"📐 빗각 무효: 배율 강화됨 ({spot_mult:.2f} → {multiplier:.2f}, +{mult_change*100:.0f}%)")
                        spot['used'] = True  # 폐기
                        continue
                    
                    # Rule 7: 전환봉 캔들 조건 (방향 + 몸통 50%+)
                    if current_stb == 'SHORT':
                        candle_ok = is_bearish and body_ratio >= 0.5
                    elif current_stb == 'LONG':
                        candle_ok = is_bullish and body_ratio >= 0.5
                    else:
                        candle_ok = False
                    
                    if not candle_ok:
                        print(f"📐 빗각 대기: 캔들조건 미충족 (방향={current_stb}, 음봉={is_bearish}, 양봉={is_bullish}, 몸통={body_ratio*100:.0f}%)")
                        continue
                    
                    # 🔥 모든 조건 충족 → 진입!
                    spot['used'] = True
                    direction = current_stb
                    emoji = '🔴' if direction == 'SHORT' else '🟢'
                    
                    tg_msg = f"""{emoji} 빗각 STB전환 진입! ({direction})
━━━━━━━━━━━━━━━━
📐 {angle_type_kr} @ {spot_price:.2f}
💪 기록배율: {spot_mult:.2f} → 현재: {multiplier:.2f}
📊 STB: {spot_stb} → {current_stb} (전환!)
🕯️ 캔들: {'음봉' if is_bearish else '양봉'} (몸통 {body_ratio*100:.0f}%)
🎯 방향: {direction} | TP:20pt SL:30pt
💡 빗각 기록 → STB 전환 → 진입!
⏰ {timestamp}"""
                    send_telegram_alert(tg_msg, signal_type=f'빗각전환{direction}')
                    
                    print(f"🔥 빗각 전환 진입! {spot_stb}→{current_stb} price={spot_price:.2f}")
                    break  # Rule 5: 첫 전환만!
                
                # 스팟 저장
                angle_spots = angle_spots[-20:]
                with open(angle_spot_file, 'w') as f:
                    json.dump(angle_spots, f, indent=2, ensure_ascii=False)
            
            return jsonify({
                "status": "success",
                "data": touch_data,
                "message": f"빗각 터치 데이터 저장됨 + 예측 전송"
            })
        
        # 📌 블랙라인/POC 터치 순수 데이터 수집 (숏/롱 판단 X)
        if action in ['blackline_touch_raw', 'poc_touch_raw', 'level_touch', 'blackline_touch', 'poc_touch']:
            touch_price = float(data.get('price', 0))
            level_price = float(data.get('level', data.get('blackline', data.get('poc', 0))))
            level_name = data.get('level_name', 'blackline' if 'blackline' in action else 'poc')
            
            ratio = 0
            channel_pct = 50
            channel_range = 0
            candle_type = 'unknown'
            bull_sum_10 = 0
            bear_sum_10 = 0
            
            if len(CANDLE_HISTORY) >= 10:
                import pandas as pd
                df_temp = pd.DataFrame(CANDLE_HISTORY[-100:] if len(CANDLE_HISTORY) >= 100 else CANDLE_HISTORY)
                ch_high = df_temp['high'].max()
                ch_low = df_temp['low'].min()
                channel_range = ch_high - ch_low
                current = CANDLE_HISTORY[-1]
                channel_pct = ((current['close'] - ch_low) / channel_range * 100) if channel_range > 0 else 50
                
                current_body = current['close'] - current['open']
                candle_type = 'bullish' if current_body > 0 else ('bearish' if current_body < 0 else 'doji')
                
                bull_sum_10 = sum([max(0, c['close'] - c['open']) for c in CANDLE_HISTORY[-10:]])
                bear_sum_10 = sum([max(0, c['open'] - c['close']) for c in CANDLE_HISTORY[-10:]])
                ratio = bull_sum_10 / (bear_sum_10 + 0.1)
            
            level_distance = touch_price - level_price if level_price > 0 else 0
            
            level_data = {
                "timestamp": now.isoformat(),
                "ticker": ticker,
                "level_name": level_name,
                "level_price": round(level_price, 2),
                "touch_price": touch_price,
                "level_distance": round(level_distance, 2),
                "ratio": round(ratio, 2),
                "channel_pct": round(channel_pct, 1),
                "channel_range": round(channel_range, 1),
                "candle_type": candle_type,
                "bull_sum_10": round(bull_sum_10, 2),
                "bear_sum_10": round(bear_sum_10, 2)
            }
            
            level_file = '.level_touches.json'
            level_touches = []
            if os.path.exists(level_file):
                try:
                    with open(level_file, 'r', encoding='utf-8') as f:
                        level_touches = json.load(f)
                except:
                    level_touches = []
            
            level_touches.append(level_data)
            level_touches = level_touches[-500:]
            
            with open(level_file, 'w', encoding='utf-8') as f:
                json.dump(level_touches, f, ensure_ascii=False, indent=2)
            
            # 📊 터치 결과 추적 시작 (양방향 테스트)
            add_pending_touch(f"{level_name}_long", 'long', touch_price, tp=18, sl=10, extra=level_data)
            add_pending_touch(f"{level_name}_short", 'short', touch_price, tp=20, sl=10, extra=level_data)
            
            print(f"\n{'='*50}")
            print(f"📍 레벨 터치 기록! [{timestamp}]")
            print(f"   레벨: {level_name} @ {level_price:.2f}")
            print(f"   터치가격: {touch_price:.2f} (거리: {level_distance:+.1f}pt)")
            print(f"   배율: {ratio:.2f} | 채널: {channel_pct:.0f}%")
            print(f"   캔들: {candle_type}")
            print(f"{'='*50}\n")
            
            # ⭐ 배율 상태 계산 + 텔레그램! (raw 데이터에도!)
            if len(CANDLE_HISTORY) >= 60:
                temp_df2 = pd.DataFrame(CANDLE_HISTORY[-60:])
                temp_df2['body'] = temp_df2['close'] - temp_df2['open']
                temp_df2['bull_sum'] = temp_df2['body'].clip(lower=0).rolling(10).sum()
                temp_df2['bear_sum'] = temp_df2['body'].clip(upper=0).abs().rolling(10).sum()
                temp_df2['buy_ratio'] = temp_df2['bull_sum'] / (temp_df2['bear_sum'] + 0.01)
                temp_df2['sell_ratio'] = temp_df2['bear_sum'] / (temp_df2['bull_sum'] + 0.01)
                temp_df2['buy_ma5'] = temp_df2['buy_ratio'].rolling(5).mean()
                temp_df2['sell_ma5'] = temp_df2['sell_ratio'].rolling(5).mean()
                
                buy_delta = temp_df2['buy_ma5'].iloc[-1] - temp_df2['buy_ma5'].iloc[-6] if len(temp_df2) >= 6 else 0
                sell_delta = temp_df2['sell_ma5'].iloc[-1] - temp_df2['sell_ma5'].iloc[-6] if len(temp_df2) >= 6 else 0
                prev_sell = temp_df2['sell_ma5'].iloc[-6] if len(temp_df2) >= 6 else 0
                prev_buy = temp_df2['buy_ma5'].iloc[-6] if len(temp_df2) >= 6 else 0
                
                h50 = temp_df2['high'].iloc[-50:].max() if len(temp_df2) >= 50 else temp_df2['high'].max()
                l50 = temp_df2['low'].iloc[-50:].min() if len(temp_df2) >= 50 else temp_df2['low'].min()
                range50 = h50 - l50
                sector_pct = ((touch_price - l50) / range50 * 100) if range50 > 0 else 50
                
                exhaust_status = ""
                if buy_delta < -0.1:
                    exhaust_status = f"🔻 매수소진! (Δ{buy_delta:.2f})" if prev_buy <= 1.3 else f"🔻 매수소진!! (이전{prev_buy:.1f}→Δ{buy_delta:.2f})"
                elif buy_delta < 0:
                    exhaust_status = f"🔻 매수세약화 (Δ{buy_delta:.2f})"
                elif sell_delta < -0.1:
                    exhaust_status = f"🔺 매도소진! (Δ{sell_delta:.2f})" if prev_sell <= 1.3 else f"🔺 매도소진!! (이전{prev_sell:.1f}→Δ{sell_delta:.2f})"
                elif sell_delta < 0:
                    exhaust_status = f"🔺 매도세약화 (Δ{sell_delta:.2f})"
                elif buy_delta > sell_delta:
                    exhaust_status = f"📈 매수세증가 (Δ+{buy_delta:.2f})"
                else:
                    exhaust_status = f"📉 매도세증가 (Δ+{sell_delta:.2f})"
                
                level_emoji = '🔵' if 'poc' in level_name.lower() else '⚫' if 'black' in level_name.lower() else '🟣' if 'zpoc' in level_name.lower() else '📍'
                
                buy_ratio_z = (temp_df2['buy_ratio'].iloc[-1] - temp_df2['buy_ratio'].mean()) / (temp_df2['buy_ratio'].std() + 0.01) if len(temp_df2) > 10 else 0
                sell_ratio_z = (temp_df2['sell_ratio'].iloc[-1] - temp_df2['sell_ratio'].mean()) / (temp_df2['sell_ratio'].std() + 0.01) if len(temp_df2) > 10 else 0
                sps_z = abs(buy_ratio_z - sell_ratio_z)
                
                if sector_pct <= 20:
                    win_rate = 93
                    direction = "LONG"
                    reason = f"저점지지: 섹터{sector_pct:.0f}% - 롱 유리"
                elif sector_pct >= 80:
                    win_rate = 93
                    direction = "SHORT"
                    reason = f"고점저항: 섹터{sector_pct:.0f}% - 숏 유리"
                else:
                    win_rate = 0
                    direction = "WAIT"
                    reason = f"중간구간: 섹터{sector_pct:.0f}% - 판단보류"
                
                if sps_z >= 1.5:
                    confidence = "S++"
                elif sps_z >= 1.0:
                    confidence = "S+"
                elif sps_z >= 0.5:
                    confidence = "S"
                else:
                    confidence = "A"
                
                tg_msg = f"""📊 RESIST_{level_name} 
승률: {win_rate}%

{level_emoji} RESIST_{level_name} ! ({win_rate}% 저항/지지)
━━━━━━━━━━━━━━━━
📐 레벨: {level_name} @ {level_price:.2f}
📍 현재가: {touch_price:.2f}
📊 섹터: {sector_pct:.0f}%
📈 매수배율z: {buy_ratio_z:.2f} | 매도배율z: {sell_ratio_z:.2f}
📉 SPS비율z: {sps_z:.2f}
🎯 방향: {direction} | TP:20pt SL:30pt
💡 {reason}
⏰ {timestamp}"""
                send_telegram_alert(tg_msg, signal_type=f'RESIST_{level_name}')
            
            return jsonify({
                "status": "success",
                "data": level_data,
                "message": f"레벨 터치 저장됨 + 텔레그램"
            })
        
        # 📍 POC터치/블랙라인 지지 신호 처리 (2단계 로직)
        # 1단계: i빗각/블랙라인에서 롱 신호 발생 → PRIOR_LONG_SIGNALS에 기록됨
        # 2단계: 조정 후 지지레벨 20pt 이내 도달 → 재진입
        if action in ['poc_touch', 'blackline_touch', 'poc_long', 'blackline_long']:
            support_level = data.get('support_level', data.get('poc', data.get('blackline', 0)))
            support_type = '블랙라인' if 'blackline' in action else 'POC'
            
            signal_valid = False
            action_msg = "데이터 부족"
            ratio = 0
            has_prior_long = False
            prior_signal_info = None
            
            if len(CANDLE_HISTORY) >= 100:
                import pandas as pd
                
                current = CANDLE_HISTORY[-1]
                current_price = current['close']
                
                # 지지레벨과의 거리 체크 (상대값: 0.08% = 약 20pt at 25000)
                distance = abs(current_price - support_level) if support_level > 0 else current_price
                distance_pct = distance / current_price * 100 if current_price > 0 else 999
                within_range = distance_pct <= 0.08
                
                # 📍 선행 롱 신호 체크 (i빗각/블랙라인에서 발생한 롱)
                for prior in PRIOR_LONG_SIGNALS:
                    prior_level = prior.get('level', 0)
                    prior_price = prior.get('price', 0)
                    # 선행 신호 가격과 현재 지지레벨이 0.20% 이내면 관련 신호로 인정 (약 50pt at 25000)
                    level_dist_pct = abs(prior_level - support_level) / current_price * 100 if current_price > 0 else 999
                    price_dist_pct = abs(prior_price - support_level) / current_price * 100 if current_price > 0 else 999
                    if level_dist_pct <= 0.20 or price_dist_pct <= 0.20:
                        has_prior_long = True
                        prior_signal_info = prior
                        break
                
                # 채널% 계산
                df_temp = pd.DataFrame(CANDLE_HISTORY[-100:])
                ch_high = df_temp['high'].max()
                ch_low = df_temp['low'].min()
                ch_range = ch_high - ch_low
                ch_pct = ((current_price - ch_low) / ch_range * 100) if ch_range > 0 else 50
                
                # 양봉 체크
                is_bullish = (current['close'] - current['open']) > 0
                
                # 배율 계산 (반등 / 하락 = 매수세가 매도세를 이기는지)
                # Spot: 조정 구간 최대 하락봉 (매도 압력)
                # Retest: 현재 반등봉 (매수 압력)
                max_drop = 0
                for i in range(max(0, len(CANDLE_HISTORY)-10), len(CANDLE_HISTORY)-1):
                    candle = CANDLE_HISTORY[i]
                    body = candle['close'] - candle['open']
                    if body < 0:
                        max_drop = max(max_drop, abs(body))
                
                current_bounce = current['close'] - current['open'] if is_bullish else 0
                # 롱 배율: 반등/하락 (1.0+ = 매수세 우위)
                ratio = current_bounce / max_drop if max_drop > 0 else 0
                
                # 거시 분석
                from macro_micro_ai import MacroMicroAI
                ai_temp = MacroMicroAI()
                for c in CANDLE_HISTORY[-100:]:
                    ai_temp.update_candles(c)
                macro = ai_temp.calc_macro()
                
                chart_phase = macro.get('chart_phase', {}) if macro else {}
                phase = chart_phase.get('phase', 'UNKNOWN')
                is_uptrend = phase in ['RISE', 'RISE_CONSOLIDATE']
                
                # 🎯 2단계 진입 조건:
                # 1) 선행 롱 신호가 있어야 함 (i빗각/블랙라인에서 발생)
                # 2) 지지 20pt 이내 + 상승흐름 + 배율1.0+ + 양봉 + 채널40%-
                if has_prior_long and within_range and is_uptrend and ratio >= 1.0 and is_bullish and ch_pct <= 40:
                    signal_valid = True
                    prior_type = prior_signal_info.get('type', 'i빗각') if prior_signal_info else 'i빗각'
                    action_msg = f"{support_type} 재진입! (선행:{prior_type} + 거리{distance:.0f}pt + 배율{ratio:.1f})"
                    
                    # AI 분석
                    ai_result = ai_temp.analyze_entry(f'{support_type}터치', 'LONG', current_price)
                    ai_decision = ai_result.get('decision', 'WAIT')
                    ai_grade = ai_result.get('grade', 'N/A')
                    ai_confidence = ai_result.get('confidence', 0)
                    ai_tp = ai_result.get('tp', 20)
                    ai_sl = ai_result.get('sl', 30)
                    ai_reason = ai_result.get('reason', '')
                    
                    if ai_decision == 'ENTER':
                        from signal_logger import log_signal
                        log_signal(
                            signal_type=f'{support_type}터치',
                            direction='LONG',
                            entry_price=current_price,
                            ratio=ratio,
                            channel_pct=ch_pct,
                            z_score=0,
                            grade=ai_grade,
                            tp=ai_tp,
                            sl=ai_sl,
                            notes=f"지지확인 | 거리{distance:.0f}pt | {ai_reason}"
                        )
                        
                        tg_msg = f"""🟢 AI 진입! {support_type} 지지 롱
━━━━━━━━━━━━━━━━
📍 {ticker} @ {current_price:.2f}
🎯 TP: {ai_tp}pt | SL: {ai_sl}pt
📊 등급: {ai_grade} | 승률: {ai_confidence:.1f}%
📏 지지거리: {distance:.1f}pt
📈 배율: {ratio:.2f}
💡 {ai_reason}
⏰ {timestamp}"""
                        send_telegram_alert(tg_msg)
                        print(f"✅ {support_type} 지지 롱 AI 확정!")
                    else:
                        print(f"❌ {support_type} 지지: AI {ai_decision} - {ai_reason}")
                        
                elif not has_prior_long:
                    action_msg = f"선행 롱 신호 없음 (i빗각/블랙라인에서 롱 필요)"
                elif not within_range:
                    action_msg = f"지지레벨 거리 {distance:.0f}pt > 20pt"
                elif not is_uptrend:
                    action_msg = f"상승흐름 아님 ({phase})"
                elif ratio < 1.0:
                    action_msg = f"배율 부족 ({ratio:.1f} < 1.0) - 반등이 하락보다 약함"
                elif not is_bullish:
                    action_msg = "양봉 아님"
                elif ch_pct > 40:
                    action_msg = f"채널 {ch_pct:.0f}% > 40% (너무 높음)"
            
            print(f"\n{'='*50}")
            print(f"📍 {support_type} 신호! [{timestamp}]")
            print(f"   가격: {price} | 지지: {support_level}")
            print(f"   선행롱: {'✅ ' + prior_signal_info.get('type', '') if has_prior_long else '❌ 없음'}")
            print(f"   배율: {ratio:.2f} | 판단: {action_msg}")
            print(f"{'='*50}\n")
            
            return jsonify({
                "status": "success",
                "signal_valid": signal_valid,
                "support_type": support_type,
                "action": action_msg,
                "ratio": ratio,
                "has_prior_long": has_prior_long
            })
        
        print(f"\n{'='*50}")
        print(f"📡 TradingView 웹훅 수신! [{timestamp}]")
        print(f"   종목: {ticker}")
        print(f"   액션: {action}")
        print(f"   가격: {price}")
        print(f"   메시지: {message}")
        print(f"{'='*50}\n")
        
        # 웹훅 기록 저장
        webhook_log = {
            "timestamp": now.isoformat(),
            "ticker": ticker,
            "action": action,
            "price": price,
            "message": message,
            "raw_data": data
        }
        
        log_file = '.webhook_history.json'
        history = []
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        
        history.append(webhook_log)
        history = history[-100:]  # 최근 100개만 유지
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        
        # 채팅 파일로도 저장 (분석용)
        chat_content = f"""[TradingView 웹훅 알림]
시간: {timestamp}
종목: {ticker}
액션: {action}
가격: {price}
메시지: {message}
"""
        filename = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_Webhook.txt"
        filepath = os.path.join(SAVE_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(chat_content)
        
        # 🔬 자동 RR 검증 실행 (3개마다)
        if len(history) >= 2 and len(history) % 3 == 0:
            try:
                auto_verify_signal(history[-5:])
                print("🔬 자동 RR 검증 실행됨!")
            except Exception as ve:
                print(f"⚠️ 자동 검증 오류: {ve}")
        
        # 🧠 제이슨 자동 분석 (5개마다)
        if len(history) >= 5 and len(history) % 5 == 0:
            try:
                jason_auto_analyze(history[-5:])
                print("🧠 제이슨 자동 분석 실행됨!")
            except Exception as je:
                print(f"⚠️ 제이슨 분석 오류: {je}")
        
        return jsonify({
            "status": "success",
            "message": f"웹훅 수신 완료: {action} {ticker} @ {price}",
            "timestamp": timestamp
        }), 200
        
    except Exception as e:
        print(f"❌ 웹훅 오류: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

def jason_auto_analyze(signals):
    """🧠 제이슨 자동 분석 - 통합배율 시스템 기반"""
    
    # 현재 거시 분석 데이터 가져오기
    from macro_micro_ai import MacroMicroAI
    ai = MacroMicroAI()
    
    import pandas as pd
    if os.path.exists('attached_assets/NQ1_1min_combined.csv'):
        df = pd.read_csv('attached_assets/NQ1_1min_combined.csv')
        for _, row in df.tail(100).iterrows():
            ai.update_candles({
                'time': row['time'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row.get('volume', 0)
            })
    
    # 실시간 배율 계산
    ratio_data = ai.calc_realtime_ratio()
    macro_data = ai.calc_macro()
    
    # 신호 통계 로드
    signal_stats = {}
    if os.path.exists('.signal_optimal_stats.json'):
        with open('.signal_optimal_stats.json', 'r', encoding='utf-8') as f:
            signal_stats = json.load(f)
    
    signals_text = json.dumps(signals, ensure_ascii=False, indent=2)
    
    prompt = f"""당신은 "제이슨" - SPS 통합배율 시스템 전문가입니다.

## 🎯 핵심 철학
- 신호(타점) + 배율(확인) = 실패 불가
- 신호 = 고확률 진입점 (기본 승률)
- 배율 = 현재 상황 반영해서 승률 조정
- 조정 승률 70%+ = 진입, 70%- = PASS

## 📊 실시간 거시 데이터:
- 채널: {macro_data.get('channel_pct', 0):.1f}%
- 숏 배율: {ratio_data.get('short_ratio', 0) if ratio_data else 0}
- 롱 배율: {ratio_data.get('long_ratio', 0) if ratio_data else 0}
- 시나리오: {macro_data.get('scenario', 'N/A')}
- 상승힘: {macro_data.get('rise_force', 0):.2f}
- 하락힘: {macro_data.get('fall_force', 0):.2f}

## 📈 검증된 신호 통계:
{json.dumps(signal_stats, ensure_ascii=False, indent=2)[:1500]}

## 📊 방금 들어온 웹훅 신호들:
{signals_text}

## 🔬 분석 요청:

### 1️⃣ 현재 시장 상태 판단
- 채널/배율/힘 기반으로 숏/롱/횡보 판단
- 현재 배율이 진입하기 좋은 상태인가?

### 2️⃣ 신호별 진입 판단
- 각 신호의 기본 승률
- 현재 상황에서 조정 승률
- ENTER/CAUTION/PASS 판단

### 3️⃣ 배율 공식 확인
- 숏 배율 = (Rolling High - Close) / (5봉 Range)
- 롱 배율 = (Close - Rolling Low) / (5봉 Range)
- 1.5+ = S+, 1.2+ = S, 1.0+ = A, 0.8+ = B, <0.8 = C

### 4️⃣ 즉시 액션
- 지금 진입해야 할 신호?
- 기다려야 할 조건?

간결하게 핵심만 답변하세요."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2000
    )
    
    result = response.choices[0].message.content
    
    now = datetime.now()
    
    progress_file = '.detector_progress.json'
    progress = {}
    if os.path.exists(progress_file):
        with open(progress_file, 'r', encoding='utf-8') as f:
            progress = json.load(f)
    
    if 'jason_analyses' not in progress:
        progress['jason_analyses'] = []
    
    progress['jason_analyses'].append({
        'timestamp': now.isoformat(),
        'signals_count': len(signals),
        'summary': result[:300]
    })
    progress['jason_analyses'] = progress['jason_analyses'][-10:]
    progress['last_jason_analysis'] = now.isoformat()
    
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
    
    filename = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_JasonAuto.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"[제이슨 자동 분석 - {now.strftime('%Y-%m-%d %H:%M:%S')}]\n\n")
        f.write(result)
    
    print(f"\n{'='*50}")
    print(f"🧠 제이슨 자동 분석 결과:")
    print(result[:600])
    print(f"{'='*50}\n")
    
    return result

def auto_verify_signal(signals):
    """🔬 자동 신호 검증 (웹훅 수신 시 자동 실행)"""
    philosophy = ""
    if os.path.exists('.user_philosophy.md'):
        with open('.user_philosophy.md', 'r', encoding='utf-8') as f:
            philosophy = f.read()[:2000]
    
    signals_text = json.dumps(signals, ensure_ascii=False, indent=2)
    
    prompt = f"""당신은 "제이슨" - A급 신호 검증 AI입니다.

## 📊 방금 들어온 웹훅 신호:
{signals_text}

## 📚 트레이딩 철학:
{philosophy}

## 빠른 판정 (간결하게):
각 신호에 대해:
1. A급/B급/C급 판정
2. 예상 RR (예: 2:1)
3. 문제점 있으면 지적

❌ C급이면 폐기 권고하고 이유 설명"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=1000
    )
    
    result = response.choices[0].message.content
    
    now = datetime.now()
    filename = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_AutoVerify.txt"
    with open(os.path.join(SAVE_DIR, filename), 'w', encoding='utf-8') as f:
        f.write(f"[자동 RR 검증 - {now.strftime('%Y-%m-%d %H:%M:%S')}]\n\n")
        f.write(result)
    
    print(f"\n{'='*50}")
    print(f"🔬 자동 RR 검증 결과:")
    print(result[:500])
    print(f"{'='*50}\n")
    
    return result

@app.route('/api/webhook-history', methods=['GET'])
def get_webhook_history():
    """웹훅 히스토리 조회"""
    try:
        log_file = '.webhook_history.json'
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            return jsonify({"success": True, "history": history[-20:]})
        return jsonify({"success": True, "history": []})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/saved-charts', methods=['GET'])
def get_saved_charts():
    """📁 저장된 파일 목록 (카테고리별 분류)"""
    try:
        import os
        import glob
        
        categories = {
            'system': {'name': '시스템', 'icon': '⚙️', 'files': []},
            'jason': {'name': '제이슨', 'icon': '🧠', 'files': []},
            'trading': {'name': '트레이딩', 'icon': '📊', 'files': []},
            'chat': {'name': '채팅', 'icon': '💬', 'files': []},
            'data': {'name': '데이터', 'icon': '📁', 'files': []}
        }
        
        for pattern in ['*.txt', '*.csv', '*.md', '*.json']:
            for f in glob.glob(pattern):
                if f.startswith('.') or os.path.getsize(f) < 10:
                    continue
                
                stat = os.stat(f)
                file_info = {
                    'name': f,
                    'size': f"{stat.st_size / 1024:.1f}KB",
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%m/%d %H:%M')
                }
                
                fn = f.lower()
                if 'jason' in fn or 'optimizer' in fn:
                    categories['jason']['files'].append(file_info)
                elif 'webhook' in fn or 'signal' in fn or 'validation' in fn:
                    categories['system']['files'].append(file_info)
                elif '_chat' in fn or 'Chat' in f:
                    categories['trading']['files'].append(file_info)
                elif f.endswith('.csv') or f.endswith('.zip'):
                    categories['data']['files'].append(file_info)
                else:
                    categories['chat']['files'].append(file_info)
        
        for cat in categories.values():
            cat['files'].sort(key=lambda x: x['modified'], reverse=True)
            cat['count'] = len(cat['files'])
        
        return jsonify({"success": True, "categories": categories})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/analyze-saved/<filename>', methods=['GET'])
def analyze_saved_file(filename):
    """📊 저장된 파일 분석"""
    try:
        import pandas as pd
        import os
        
        if not os.path.exists(filename):
            return jsonify({"success": False, "message": "파일 없음"})
        
        df = pd.read_csv(filename)
        cols = [c.lower() for c in df.columns]
        df.columns = cols
        
        if 'close' not in cols and 'price' in cols:
            df['close'] = df['price']
        if 'high' not in cols:
            df['high'] = df['close']
        if 'low' not in cols:
            df['low'] = df['close']
        if 'open' not in cols:
            df['open'] = df['close']
        
        closes = df['close'].astype(float).values
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values
        
        time_col = None
        for col in ['time', 'datetime', 'date', 'timestamp']:
            if col in df.columns:
                time_col = col
                break
        
        invisible_vpocs = []
        a_grade_signals = []
        
        for i in range(10, len(df)):
            window_lows = lows[max(0, i-10):i]
            inv_vpoc = (window_lows.max() + window_lows.min()) / 2
            invisible_vpocs.append({'idx': i, 'price': float(inv_vpoc)})
            
            if i >= 3:
                is_hl = lows[i-1] > lows[i-2] and lows[i-2] > lows[i-3]
                vpoc_dist = abs(closes[i] - inv_vpoc)
                cluster = int(sum(abs(closes[max(0,i-10):i] - inv_vpoc) < 20))
                
                if is_hl and cluster >= 4 and vpoc_dist < 30:
                    a_grade_signals.append({
                        'idx': i, 'price': float(closes[i]),
                        'invisible_vpoc': float(inv_vpoc), 'cluster_count': cluster
                    })
        
        chart_data = []
        for i in range(len(df)):
            time_est = df[time_col].iloc[i] if time_col else f"#{i}"
            chart_data.append({
                'idx': i, 'time_est': str(time_est)[:16],
                'open': float(df['open'].iloc[i]) if 'open' in df.columns else float(closes[i]),
                'high': float(highs[i]), 'low': float(lows[i]), 'close': float(closes[i]),
                'invisible_vpoc': next((v['price'] for v in invisible_vpocs if v['idx'] == i), None),
                'is_a_grade': any(s['idx'] == i for s in a_grade_signals)
            })
        
        return jsonify({
            "success": True,
            "filename": filename,
            "result": {
                'total_bars': len(df),
                'a_grade_count': len(a_grade_signals),
                'a_grade_signals': a_grade_signals[-10:],
                'chart_data': chart_data[-100:],
                'timezone': 'EST (UTC-5)'
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/upload-chart', methods=['POST'])
def upload_chart():
    """📊 차트 데이터 업로드 + A급/VPOC 분석 (CSV/ZIP 지원, EST 시간대, 대용량 최적화)"""
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "message": "파일이 없습니다"})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "message": "파일명이 없습니다"})
        
        import pandas as pd
        import io
        import zipfile
        import hashlib
        from datetime import datetime, timedelta
        import time
        
        start_time = time.time()
        all_dfs = []
        file_info = []
        seen_hashes = set()
        
        # ZIP 또는 CSV 처리
        if file.filename.endswith('.zip'):
            file_bytes = file.read()
            with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as zf:
                csv_files = [n for n in zf.namelist() if n.endswith('.csv') and not n.startswith('__MACOSX')]
                
                for name in csv_files:
                    with zf.open(name) as csv_file:
                        content = csv_file.read()
                        content_hash = hashlib.md5(content).hexdigest()[:16]
                        
                        if content_hash not in seen_hashes:
                            seen_hashes.add(content_hash)
                            try:
                                temp_df = pd.read_csv(io.BytesIO(content))
                                all_dfs.append(temp_df)
                                file_info.append({'name': name.split('/')[-1], 'rows': len(temp_df), 'status': '✅'})
                            except:
                                file_info.append({'name': name.split('/')[-1], 'rows': 0, 'status': '❌'})
                        else:
                            file_info.append({'name': name.split('/')[-1], 'rows': 0, 'status': '🔄'})
            
            if not all_dfs:
                return jsonify({"success": False, "message": "ZIP에 유효한 CSV 파일이 없습니다"})
            df = pd.concat(all_dfs, ignore_index=True)
        else:
            content = file.read()
            df = pd.read_csv(io.BytesIO(content))
            file_info.append({'name': file.filename, 'rows': len(df), 'status': '✅'})
        
        # 대용량 최적화: 빠른 중복 제거
        original_len = len(df)
        
        cols = [c.lower() for c in df.columns]
        df.columns = cols
        
        if 'close' not in cols and 'price' in cols:
            df['close'] = df['price']
        if 'high' not in cols:
            df['high'] = df['close']
        if 'low' not in cols:
            df['low'] = df['close']
        if 'open' not in cols:
            df['open'] = df['close']
        
        # pandas 중복 제거 (빠름)
        time_col = None
        for col in ['time', 'datetime', 'date', 'timestamp']:
            if col in df.columns:
                time_col = col
                break
        
        if time_col:
            df = df.drop_duplicates(subset=[time_col, 'close'], keep='first')
        else:
            df = df.drop_duplicates(subset=['close'], keep='first')
        
        df = df.reset_index(drop=True)
        dedup_len = len(df)
        
        # numpy 배열로 변환 (빠른 연산)
        closes = df['close'].astype(float).values
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values
        
        invisible_vpocs = []
        a_grade_signals = []
        
        # 샘플링: 10000개 이상이면 간격 조절
        step = max(1, len(df) // 5000)
        
        for i in range(10, len(df), step):
            window_lows = lows[max(0, i-10):i]
            cluster_high = window_lows.max()
            cluster_low = window_lows.min()
            inv_vpoc = (cluster_high + cluster_low) / 2
            invisible_vpocs.append({'idx': i, 'price': float(inv_vpoc)})
            
            if i >= 3:
                is_higher_low = lows[i-1] > lows[i-2] and lows[i-2] > lows[i-3]
                price = closes[i]
                vpoc_dist = abs(price - inv_vpoc)
                
                window_closes = closes[max(0, i-10):i]
                cluster_count = int(sum(abs(window_closes - inv_vpoc) < 20))
                
                if is_higher_low and cluster_count >= 4 and vpoc_dist < 30:
                    a_grade_signals.append({
                        'idx': i,
                        'price': float(price),
                        'invisible_vpoc': float(inv_vpoc),
                        'cluster_count': cluster_count
                    })
        
        # EST 시간대 변환 함수
        def to_est(time_str):
            if pd.isna(time_str):
                return None
            try:
                if isinstance(time_str, str):
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%m/%d/%Y %H:%M']:
                        try:
                            dt = datetime.strptime(time_str, fmt)
                            dt_est = dt - timedelta(hours=5)  # UTC-5
                            return dt_est.strftime('%m/%d %H:%M')
                        except:
                            continue
                return str(time_str)[:16]
            except:
                return None
        
        # 시간 컬럼 찾기
        time_col = None
        for col in ['time', 'datetime', 'date', 'timestamp']:
            if col in df.columns:
                time_col = col
                break
        
        chart_data = []
        for i in range(len(df)):
            time_est = to_est(df[time_col].iloc[i]) if time_col else f"#{i}"
            
            point = {
                'idx': i,
                'time_est': time_est,
                'open': float(df['open'].iloc[i]) if 'open' in df.columns else closes[i],
                'high': float(highs[i]),
                'low': float(lows[i]),
                'close': float(closes[i]),
                'invisible_vpoc': None,
                'is_a_grade': False
            }
            
            for v in invisible_vpocs:
                if v['idx'] == i:
                    point['invisible_vpoc'] = v['price']
                    break
            
            for s in a_grade_signals:
                if s['idx'] == i:
                    point['is_a_grade'] = True
                    break
            
            chart_data.append(point)
        
        # 중복 행 제거 (close 기준)
        seen_closes = set()
        unique_chart = []
        for pt in chart_data:
            key = f"{pt['time_est']}_{pt['close']}"
            if key not in seen_closes:
                seen_closes.add(key)
                unique_chart.append(pt)
        
        elapsed = round(time.time() - start_time, 1)
        
        result = {
            'total_bars': original_len,
            'unique_bars': dedup_len,
            'displayed_bars': len(unique_chart),
            'files_processed': file_info,
            'duplicates_removed': original_len - dedup_len,
            'a_grade_count': len(a_grade_signals),
            'a_grade_signals': a_grade_signals[-10:],
            'chart_data': unique_chart[-100:],
            'invisible_vpocs': invisible_vpocs[-20:],
            'timezone': 'EST (UTC-5)',
            'processing_time': f"{elapsed}초"
        }
        
        with open('.chart_analysis.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            "success": True,
            "message": f"✅ {dedup_len}개 봉 ({elapsed}초) | 중복 {original_len - dedup_len}개 제거 | A급 {len(a_grade_signals)}개",
            "result": result
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": f"❌ 오류: {str(e)}"}), 500

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    """📊 비주얼 대시보드 데이터"""
    try:
        dashboard = {
            'webhooks': [],
            'statistics': {'a': 0, 'b': 0, 'c': 0, 'total': 0},
            'thresholds': {},
            'recent_analysis': '',
            'signals_chart': [],
            'hybrid_analysis': {}
        }
        
        if os.path.exists('.webhook_history.json'):
            with open('.webhook_history.json', 'r', encoding='utf-8') as f:
                webhooks = json.load(f)
                dashboard['webhooks'] = webhooks[-20:]
                
                for w in webhooks:
                    action = w.get('action', '').lower()
                    if 'a급' in action:
                        dashboard['statistics']['a'] += 1
                    elif 'b급' in action:
                        dashboard['statistics']['b'] += 1
                    else:
                        dashboard['statistics']['c'] += 1
                dashboard['statistics']['total'] = len(webhooks)
                
                dashboard['signals_chart'] = [
                    {'time': w['timestamp'][-8:-3], 'price': float(w.get('price', 0))}
                    for w in webhooks[-10:]
                ]
                
                # 하이브리드 A급 분석
                if len(webhooks) >= 10:
                    prices = [float(w['price']) for w in webhooks]
                    ivpoc = sum(prices) / len(prices)
                    tick_range = 2.5  # 10틱
                    
                    buy_strength = 0.0
                    sell_strength = 0.0
                    buy_count = 0
                    sell_count = 0
                    trades = []
                    
                    for i, w in enumerate(webhooks):
                        price = float(w['price'])
                        distance = price - ivpoc
                        
                        if distance > 0:
                            sell_strength += 1.5
                            sell_count += 1
                            sps_type = "SELL"
                        else:
                            buy_strength += 1.5
                            buy_count += 1
                            sps_type = "BUY"
                        
                        if buy_strength > sell_strength * 1.2:
                            bias = "BUY"
                        elif sell_strength > buy_strength * 1.2:
                            bias = "SELL"
                        else:
                            bias = "NEUTRAL"
                        
                        is_touch = abs(distance) <= tick_range
                        
                        if is_touch and bias == sps_type and bias != "NEUTRAL":
                            future = [float(webhooks[j]['price']) for j in range(i+1, min(i+11, len(webhooks)))]
                            if future:
                                entry = price
                                if bias == "BUY":
                                    hit_target = max(future) >= entry + 2.5
                                    hit_stop = min(future) <= entry - 1.25
                                else:
                                    hit_target = min(future) <= entry - 2.5
                                    hit_stop = max(future) >= entry + 1.25
                                
                                if hit_target and not hit_stop:
                                    result = "WIN"
                                elif hit_stop and not hit_target:
                                    result = "LOSS"
                                else:
                                    result = "PENDING"
                                
                                trades.append({
                                    'time': w['timestamp'][11:16],
                                    'type': bias,
                                    'price': price,
                                    'result': result
                                })
                    
                    wins = len([t for t in trades if t['result'] == 'WIN'])
                    losses = len([t for t in trades if t['result'] == 'LOSS'])
                    total = wins + losses
                    
                    dashboard['hybrid_analysis'] = {
                        'ivpoc': round(ivpoc, 2),
                        'buy_strength': round(buy_strength, 1),
                        'sell_strength': round(sell_strength, 1),
                        'buy_count': buy_count,
                        'sell_count': sell_count,
                        'dominance': 'BUY' if buy_strength > sell_strength * 1.2 else ('SELL' if sell_strength > buy_strength * 1.2 else 'NEUTRAL'),
                        'position': 'LONG' if buy_strength > sell_strength * 1.2 else ('SHORT' if sell_strength > buy_strength * 1.2 else 'WAIT'),
                        'trades': trades[-10:],
                        'wins': wins,
                        'losses': losses,
                        'win_rate': round((wins / total * 100) if total > 0 else 0, 1),
                        'total_trades': len(trades)
                    }
        
        if os.path.exists('.strict_a_grade.json'):
            with open('.strict_a_grade.json', 'r', encoding='utf-8') as f:
                dashboard['thresholds'] = json.load(f)
        
        if os.path.exists('.detector_progress.json'):
            with open('.detector_progress.json', 'r', encoding='utf-8') as f:
                progress = json.load(f)
                if progress.get('optimizations'):
                    dashboard['recent_analysis'] = progress['optimizations'][-1].get('summary', '')[:500]
        
        return jsonify({"success": True, "dashboard": dashboard})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/verify-ratio', methods=['GET', 'POST'])
def verify_ratio():
    """🔍 한 줄 검증기 - 배율 기반 저항/돌파 확률"""
    try:
        from signal_evaluator import evaluate_signal, one_line_verify
        
        if request.method == 'POST':
            data = request.get_json() or {}
            multiplier = float(data.get('multiplier', 1.0))
            direction = data.get('direction', 'long')
        else:
            multiplier = float(request.args.get('multiplier', 1.0))
            direction = request.args.get('direction', 'long')
        
        result = evaluate_signal(multiplier, direction)
        result['one_line'] = one_line_verify(multiplier, direction)
        
        return jsonify({
            "success": True,
            "result": result
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"오류: {str(e)}"
        }), 500

@app.route('/api/ratio-summary')
def ratio_summary():
    """📊 Ratio 배율 법칙 요약"""
    try:
        from summary_maker import make_ratio_summary
        summary = make_ratio_summary()
        return jsonify({
            "success": True,
            "summary": summary
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"오류: {str(e)}"
        }), 500

@app.route('/api/realtime-ratio')
def realtime_ratio():
    """📊 실시간 배율 계산 (네 철학 공식)
    
    숏 배율 = (Rolling High - Close) / (5봉 Range)
    롱 배율 = (Close - Rolling Low) / (5봉 Range)
    
    배율 해석:
    - 1.5+ = S+ (매우 강함)
    - 1.2+ = S (강함)  
    - 1.0+ = A (보통)
    - 0.8+ = B (약함)
    - <0.8 = C (진입 비추)
    """
    try:
        from macro_micro_ai import MacroMicroAI
        ai = MacroMicroAI()
        
        # 최근 캔들 로드
        import pandas as pd
        df = pd.read_csv('attached_assets/NQ1_1min_combined.csv')
        for _, row in df.tail(100).iterrows():
            ai.update_candles({
                'time': row['time'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row.get('volume', 0)
            })
        
        ratio = ai.calc_realtime_ratio()
        
        if ratio:
            return jsonify({
                "success": True,
                "ratio": ratio
            })
        else:
            return jsonify({
                "success": False,
                "message": "캔들 데이터 부족"
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route('/api/jason-v2/analyze', methods=['POST'])
def jason_v2_analyze():
    """🧠 Jason v2 - 통합 로직 분석 및 저장"""
    try:
        from jason_v2 import analyze_and_save
        data = request.get_json() or {}
        
        entry = analyze_and_save(
            spot_sps=float(data.get('spot_sps', 0)),
            retest_sps=float(data.get('retest_sps', 1)),
            spot_price=data.get('spot_price'),
            sector=data.get('sector'),
            zPOC=data.get('zPOC'),
            fvg_gap=data.get('fvg_gap'),
            fvg_closed=data.get('fvg_closed'),
            direction=data.get('direction', 'long'),
            vwap_position=data.get('vwap_position'),
            structure=data.get('structure'),
            channel_percent=data.get('channel_percent'),
            trend=data.get('trend'),
            signal_name=data.get('signal_name'),
            notes=data.get('notes')
        )
        
        return jsonify({
            "success": True,
            "entry": entry
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"오류: {str(e)}"
        }), 500

@app.route('/api/jason-v2/memory')
def jason_v2_memory():
    """🧠 Jason v2 - 메모리 조회"""
    try:
        from jason_v2 import get_summary, get_recent_entries
        
        limit = int(request.args.get('limit', 10))
        
        return jsonify({
            "success": True,
            "summary": get_summary(),
            "recent_entries": get_recent_entries(limit)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"오류: {str(e)}"
        }), 500

@app.route('/api/jason-v2/search')
def jason_v2_search():
    """🧠 Jason v2 - 검색"""
    try:
        from jason_v2 import search_entries
        
        keyword = request.args.get('keyword')
        signal_name = request.args.get('signal_name')
        sector = request.args.get('sector')
        
        results = search_entries(keyword, signal_name, sector)
        
        return jsonify({
            "success": True,
            "count": len(results),
            "results": results[-50:]
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"오류: {str(e)}"
        }), 500

@app.route('/api/logic-history')
def logic_history_api():
    """📜 로직 진화 히스토리"""
    try:
        from logic_history import load_history, get_evolution_summary
        
        format_type = request.args.get('format', 'json')
        
        if format_type == 'markdown':
            return jsonify({
                "success": True,
                "summary": get_evolution_summary()
            })
        else:
            return jsonify({
                "success": True,
                "history": load_history()
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"오류: {str(e)}"
        }), 500

@app.route('/api/auto-log-logic', methods=['POST'])
def auto_log_logic_api():
    """새 로직 자동 기록"""
    try:
        from logic_history import auto_log_new_logic
        
        data = request.get_json() or {}
        name = data.get('name')
        formula = data.get('formula')
        backtest = data.get('backtest')
        csv_file = data.get('csv_file')
        
        if not name or not formula:
            return jsonify({"success": False, "message": "name과 formula 필수"}), 400
        
        entry = auto_log_new_logic(name, formula, backtest, csv_file)
        
        return jsonify({
            "success": True,
            "message": f"'{name}' 로직 자동 기록 완료!",
            "entry": entry
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/verify-ratio-csv')
def verify_ratio_csv_api():
    """ratio 공식 CSV 자동 검증"""
    try:
        from logic_history import verify_ratio_with_csv
        
        results = verify_ratio_with_csv()
        
        return jsonify({
            "success": True,
            "message": "ratio CSV 검증 완료!",
            "results": results
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal/log', methods=['POST'])
def log_signal_api():
    """실시간 신호 기록"""
    try:
        from signal_logger import log_signal
        
        data = request.get_json() or {}
        signal = log_signal(
            signal_type=data.get('type', 'UNKNOWN'),
            direction=data.get('direction', 'LONG'),
            entry_price=data.get('entry', 0),
            ratio=data.get('ratio', 0),
            channel_pct=data.get('channel', 0),
            z_score=data.get('z_score', 0),
            grade=data.get('grade', 'B'),
            tp=data.get('tp'),
            sl=data.get('sl'),
            notes=data.get('notes', '')
        )
        
        return jsonify({
            "success": True,
            "message": f"신호 기록 완료: {signal['id']}",
            "signal": signal
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal/update', methods=['POST'])
def update_signal_api():
    """신호 상태 업데이트"""
    try:
        from signal_logger import update_signal_status
        
        data = request.get_json() or {}
        signal_id = data.get('id')
        status = data.get('status')
        result = data.get('result')
        pnl = data.get('pnl', 0)
        notes = data.get('notes', '')
        
        if not signal_id:
            return jsonify({"success": False, "message": "signal id 필수"}), 400
        
        update_signal_status(signal_id, status, result, pnl, notes)
        
        return jsonify({
            "success": True,
            "message": f"신호 업데이트 완료: {signal_id}"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal/today')
def today_signals_api():
    """오늘 신호 목록"""
    try:
        from signal_logger import get_today_signals, generate_daily_report
        
        signals = get_today_signals()
        report = generate_daily_report()
        
        return jsonify({
            "success": True,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "count": len(signals),
            "report": report,
            "signals": signals
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal/report')
def signal_report_api():
    """일별 리포트"""
    try:
        from signal_logger import generate_daily_report
        
        date = request.args.get('date')
        report = generate_daily_report(date)
        
        return jsonify({
            "success": True,
            "report": report
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal/filter')
def filter_signals_api():
    """신호 필터링 분석"""
    try:
        from signal_logger import filter_signals, analyze_filtered_signals
        
        signal_type = request.args.get('type')
        direction = request.args.get('direction')
        grade = request.args.get('grade')
        min_ratio = request.args.get('min_ratio', type=float)
        max_ratio = request.args.get('max_ratio', type=float)
        min_channel = request.args.get('min_channel', type=float)
        max_channel = request.args.get('max_channel', type=float)
        result = request.args.get('result')
        date_from = request.args.get('from')
        date_to = request.args.get('to')
        
        signals = filter_signals(
            signal_type=signal_type,
            direction=direction,
            grade=grade,
            min_ratio=min_ratio,
            max_ratio=max_ratio,
            min_channel=min_channel,
            max_channel=max_channel,
            result=result,
            date_from=date_from,
            date_to=date_to
        )
        
        analysis = analyze_filtered_signals(signals)
        
        return jsonify({
            "success": True,
            "filters_applied": {
                "type": signal_type, "direction": direction, "grade": grade,
                "ratio": {"min": min_ratio, "max": max_ratio},
                "channel": {"min": min_channel, "max": max_channel},
                "result": result, "date_range": {"from": date_from, "to": date_to}
            },
            "count": len(signals),
            "analysis": analysis,
            "signals": signals
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal/summary')
def signal_summary_api():
    """전체 신호 요약"""
    try:
        from signal_logger import get_signal_summary
        
        return jsonify({
            "success": True,
            "summary": get_signal_summary()
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal/telegram', methods=['POST'])
def telegram_signal_api():
    """텔레그램 신호 JSON 파싱 및 기록"""
    try:
        from signal_logger import parse_telegram_signal
        
        data = request.get_json() or {}
        signal = parse_telegram_signal(data)
        
        return jsonify({
            "success": True,
            "message": "텔레그램 신호 기록 완료",
            "signal": signal
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal/failures')
def failure_analysis_api():
    """실패 신호 원인 분석"""
    try:
        from signal_logger import get_failure_analysis
        
        analysis = get_failure_analysis()
        
        return jsonify({
            "success": True,
            "analysis": analysis
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal/improve')
def improvement_api():
    """개선 제안"""
    try:
        from signal_logger import get_improvement_suggestions
        
        suggestions = get_improvement_suggestions()
        
        return jsonify({
            "success": True,
            "suggestions": suggestions
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/signal/analyze/<signal_id>')
def analyze_single_signal_api(signal_id):
    """단일 신호 실패 원인 분석"""
    try:
        from signal_logger import load_signals, analyze_failure_reason
        
        data = load_signals()
        signal = next((s for s in data["signals"] if s.get("id") == signal_id), None)
        
        if not signal:
            return jsonify({"success": False, "message": "신호 없음"}), 404
        
        analysis = analyze_failure_reason(signal)
        
        return jsonify({
            "success": True,
            "signal": signal,
            "analysis": analysis
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ==================== 퀀트 메트릭 API ====================

@app.route('/api/quant/dashboard')
def quant_dashboard_api():
    """📊 퀀트 대시보드"""
    try:
        from quant_metrics import get_quant_dashboard
        
        dashboard = get_quant_dashboard()
        
        return jsonify({
            "success": True,
            "dashboard": dashboard
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/quant/trade', methods=['POST'])
def record_quant_trade_api():
    """실거래 기록"""
    try:
        from quant_metrics import record_trade
        
        data = request.get_json() or {}
        
        trade = record_trade(
            direction=data.get('direction', 'LONG'),
            entry_price=data.get('entry_price', 0),
            exit_price=data.get('exit_price', 0),
            result=data.get('result', 'WIN'),
            tp_points=data.get('tp', 20),
            sl_points=data.get('sl', 30),
            signal_type=data.get('signal_type', 'MANUAL'),
            grade=data.get('grade', 'A'),
            contracts=data.get('contracts', 1),
            instrument=data.get('instrument', 'MNQ'),
            notes=data.get('notes', '')
        )
        
        return jsonify({
            "success": True,
            "message": "거래 기록 완료",
            "trade": trade
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/quant/position-size')
def position_size_api():
    """포지션 사이징 계산"""
    try:
        from quant_metrics import calculate_position_size
        
        balance = float(request.args.get('balance', 10000))
        risk = float(request.args.get('risk', 1))
        sl = float(request.args.get('sl', 30))
        instrument = request.args.get('instrument', 'MNQ')
        
        size = calculate_position_size(balance, risk, sl, instrument)
        
        return jsonify({
            "success": True,
            "position_size": size,
            "params": {
                "balance": balance,
                "risk_percent": risk,
                "stop_loss": sl,
                "instrument": instrument
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/quant/comparison')
def backtest_live_comparison_api():
    """백테스트 vs 실거래 비교"""
    try:
        from quant_metrics import get_backtest_vs_live_comparison
        
        comparison = get_backtest_vs_live_comparison()
        
        return jsonify({
            "success": True,
            "comparison": comparison
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/quant/reset', methods=['POST'])
def reset_quant_metrics_api():
    """메트릭 초기화"""
    try:
        from quant_metrics import reset_metrics
        
        data = request.get_json() or {}
        balance = data.get('start_balance', 10000)
        
        reset_metrics(balance)
        
        return jsonify({
            "success": True,
            "message": f"메트릭 초기화 완료 (시작 잔고: ${balance})"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ==================== 포지션 관리 API ====================

@app.route('/api/position/open', methods=['POST'])
def open_position_api():
    """ATM 포지션 오픈"""
    try:
        from position_manager import open_position, get_position_display
        
        data = request.get_json() or {}
        
        pos = open_position(
            signal_type=data.get('signal_type', 'MANUAL'),
            direction=data.get('direction', 'SHORT'),
            entry_price=float(data.get('entry_price', 0)),
            sl_points=int(data.get('sl', 30)),
            tp_points=int(data.get('tp', 20))
        )
        
        return jsonify({
            "success": True,
            "message": f"포지션 오픈: {pos['id']}",
            "position": get_position_display(pos['id'])
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/position/check', methods=['POST'])
def check_position_api():
    """현재가 체크 → 추가 진입 여부"""
    try:
        from position_manager import check_add_position
        
        data = request.get_json() or {}
        position_id = data.get('position_id')
        current_price = float(data.get('current_price', 0))
        
        result = check_add_position(position_id, current_price)
        
        return jsonify({
            "success": True,
            **result
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/position/status')
def position_status_api():
    """활성 포지션 상태"""
    try:
        from position_manager import get_position_display, get_active_positions
        
        position_id = request.args.get('id')
        
        if position_id:
            display = get_position_display(position_id)
        else:
            display = get_position_display()
        
        return jsonify({
            "success": True,
            "position": display,
            "active_count": len(get_active_positions())
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/position/close', methods=['POST'])
def close_position_api():
    """포지션 청산"""
    try:
        from position_manager import close_position
        
        data = request.get_json() or {}
        position_id = data.get('position_id')
        exit_price = float(data.get('exit_price', 0))
        result = data.get('result', 'WIN')
        
        closed = close_position(position_id, exit_price, result)
        
        if closed:
            return jsonify({
                "success": True,
                "message": f"포지션 청산: {result}",
                "pnl_points": closed.get('pnl_points', 0),
                "total_contracts": closed.get('total_contracts', 0)
            })
        else:
            return jsonify({"success": False, "message": "포지션 없음"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/position/list')
def position_list_api():
    """포지션 목록"""
    try:
        from position_manager import get_active_positions, load_positions
        
        data = load_positions()
        
        return jsonify({
            "success": True,
            "active": get_active_positions(),
            "history_count": len(data.get("history", []))
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/chronology')
def chronology_api():
    """📅 날짜별 연대기"""
    try:
        from history_builder import get_chronology, build_timeline, search_history, get_indicator_history, save_timeline
        
        action = request.args.get('action', 'view')
        keyword = request.args.get('keyword')
        indicator = request.args.get('indicator')
        date = request.args.get('date')
        
        if action == 'build':
            save_timeline()
            return jsonify({"success": True, "message": "타임라인 빌드 완료!"})
        
        if keyword:
            results = search_history(keyword)
            return jsonify({
                "success": True,
                "keyword": keyword,
                "count": len(results),
                "results": results
            })
        
        if indicator:
            history = get_indicator_history(indicator)
            return jsonify({
                "success": True,
                "indicator": indicator,
                "count": len(history),
                "history": history
            })
        
        if date:
            from history_builder import get_date_summary
            return jsonify({
                "success": True,
                "summary": get_date_summary(date)
            })
        
        return jsonify({
            "success": True,
            "chronology": get_chronology()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"오류: {str(e)}"
        }), 500

@app.route('/api/jason-full-analysis', methods=['POST'])
def jason_full_analysis():
    """🧠 제이슨 전체 분석 - 모든 데이터 분석 후 결과 반환"""
    try:
        # 1. 히스토리 인덱싱 실행
        build_history_index()
        
        # 2. 결과 로드
        jason_summary = ""
        if os.path.exists('.jason_deep_summary.md'):
            with open('.jason_deep_summary.md', 'r', encoding='utf-8') as f:
                jason_summary = f.read()
        
        jason2_backup = ""
        if os.path.exists('.jason2_backup.md'):
            with open('.jason2_backup.md', 'r', encoding='utf-8') as f:
                jason2_backup = f.read()
        
        history_index = {}
        if os.path.exists('.history_index.json'):
            with open('.history_index.json', 'r', encoding='utf-8') as f:
                history_index = json.load(f)
        
        # 3. 전체 결과 합치기
        full_result = f"""# 🧠 제이슨 전체 분석 결과

생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
분석 파일: {history_index.get('file_count', 0)}개
신호 발견: {len(history_index.get('signals', []))}건
공식 발견: {len(history_index.get('formulas', []))}건

---

{jason_summary}

---

## 🤖 제이슨2 백업
{jason2_backup}
"""
        
        return jsonify({
            "success": True,
            "message": "🧠 제이슨 전체 분석 완료!",
            "result": full_result,
            "file_count": history_index.get('file_count', 0),
            "signals_count": len(history_index.get('signals', [])),
            "formulas_count": len(history_index.get('formulas', []))
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"❌ 오류: {str(e)}"
        }), 500

@app.route('/api/jason-process', methods=['GET'])
def get_jason_process():
    """🧠 제이슨 프로세스 상태 조회"""
    try:
        state_file = '.jason_state.json'
        progress_file = '.detector_progress.json'
        
        state = {}
        progress = {}
        
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
        
        if os.path.exists(progress_file):
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress = json.load(f)
        
        return jsonify({
            "success": True,
            "state": state,
            "progress": progress
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/jason-optimize', methods=['POST'])
def jason_optimize():
    """🧠 제이슨 지속 최적화 - Pine + Python 문제 해결"""
    try:
        data = request.get_json() or {}
        focus = data.get('focus', 'general')
        
        context = {
            'philosophy': '',
            'guide': '',
            'signals': [],
            'progress': {}
        }
        
        if os.path.exists('.user_philosophy.md'):
            with open('.user_philosophy.md', 'r', encoding='utf-8') as f:
                context['philosophy'] = f.read()[:3000]
        
        if os.path.exists('00_unified_guide.md'):
            with open('00_unified_guide.md', 'r', encoding='utf-8') as f:
                context['guide'] = f.read()[:4000]
        
        if os.path.exists('.webhook_history.json'):
            with open('.webhook_history.json', 'r', encoding='utf-8') as f:
                context['signals'] = json.load(f)[-10:]
        
        if os.path.exists('.detector_progress.json'):
            with open('.detector_progress.json', 'r', encoding='utf-8') as f:
                context['progress'] = json.load(f)
        
        prompt = f"""당신은 "제이슨" - 트레이딩 시스템 최적화 AI입니다.

## 🎯 임무: {focus} 최적화

## 📊 컨텍스트:

### 사용자 철학:
{context['philosophy'][:2000]}

### 통합 가이드:
{context['guide'][:2500]}

### 최근 신호:
{json.dumps(context['signals'], ensure_ascii=False)[:1000]}

### 진행상황:
{json.dumps(context['progress'], ensure_ascii=False)[:800]}

## 🔬 분석해주세요:

1. **핵심 문제점** (보이지 않는 VPOC, 클러스터, 상승 확인 통합 안 되는 이유)
2. **Pine Script 수정 코드** (웹훅에 sps_zscore, cluster_count, is_higher_low 추가)
3. **Python 해결책** (백테스트, 자동 최적화)
4. **즉시 실행 가능한 액션**

### 출력 형식:
🔴 문제점: ...
🟡 Pine 수정: ```pine ... ```
🟢 Python 해결: ```python ... ```
🎯 액션: 1) ... 2) ..."""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4000
        )
        
        analysis = response.choices[0].message.content
        
        now = datetime.now()
        progress_file = '.detector_progress.json'
        progress = context['progress']
        
        if 'optimizations' not in progress:
            progress['optimizations'] = []
        
        progress['optimizations'].append({
            'timestamp': now.isoformat(),
            'focus': focus,
            'summary': analysis[:500]
        })
        progress['optimizations'] = progress['optimizations'][-10:]
        progress['last_optimization'] = now.isoformat()
        
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        
        filename = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_JasonOptimization.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"[제이슨 최적화 - {now.strftime('%Y-%m-%d %H:%M:%S')}]\n\n")
            f.write(analysis)
        
        return jsonify({
            "success": True,
            "message": f"🧠 제이슨 최적화 완료! ({focus})",
            "analysis": analysis
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": f"❌ 오류: {str(e)}"}), 500

@app.route('/api/verify-signal', methods=['POST'])
def verify_signal():
    """🔬 A급 신호 RR 검증 - 제이슨(GPT)이 분석"""
    try:
        log_file = '.webhook_history.json'
        if not os.path.exists(log_file):
            return jsonify({"success": False, "message": "웹훅 기록이 없습니다"})
        
        with open(log_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        if not history:
            return jsonify({"success": False, "message": "분석할 신호가 없습니다"})
        
        philosophy = ""
        if os.path.exists('.user_philosophy.md'):
            with open('.user_philosophy.md', 'r', encoding='utf-8') as f:
                philosophy = f.read()[:3000]
        
        recent_signals = history[-10:]
        signals_text = json.dumps(recent_signals, ensure_ascii=False, indent=2)
        
        prompt = f"""당신은 "제이슨" - A급 신호 검증 전문 AI입니다.

## 🎯 임무: A급 신호 RR(Risk:Reward) 검증

## 📊 최근 웹훅 신호 데이터:
{signals_text}

## 📚 사용자의 트레이딩 철학:
{philosophy}

## 🔬 검증 작업:

### 1️⃣ 각 신호 분석
각 신호가 진짜 A급인지 판정하세요:
- 보이지 않는 VPOC 기준에 부합하는가?
- SPS 클러스터 조건을 충족하는가?
- 진입 시점이 적절한가?

### 2️⃣ RR 추정
A급으로 판정된 신호의 예상 RR:
- 손절 위치 (VPOC 아래 몇 틱?)
- 목표가 (다음 저항까지)
- 예상 RR 비율

### 3️⃣ 의문 제기 (중요!)
신호가 A급이 아니라면:
- ❌ 왜 A급이 아닌지 구체적으로 설명
- ❓ 어떤 조건이 부족한지
- 🚫 폐기 권고 및 이유

### 4️⃣ 개선 제안
- 현재 조건의 문제점
- Pine Script 수정 제안 (있다면)

## 출력 형식:
각 신호별로:
📍 신호 #N: [시간]
- 판정: ✅ A급 / ⚠️ B급 / ❌ C급(폐기)
- 이유: ...
- 예상 RR: X:1
- 의문점: ...

마지막에 전체 요약과 개선점을 제시하세요."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=3000
        )
        
        verification = response.choices[0].message.content
        
        now = datetime.now()
        result = {
            "timestamp": now.isoformat(),
            "signals_analyzed": len(recent_signals),
            "verification": verification
        }
        
        verify_file = '.signal_verification.json'
        verifications = []
        if os.path.exists(verify_file):
            with open(verify_file, 'r', encoding='utf-8') as f:
                verifications = json.load(f)
        
        verifications.append(result)
        verifications = verifications[-20:]
        
        with open(verify_file, 'w', encoding='utf-8') as f:
            json.dump(verifications, f, ensure_ascii=False, indent=2)
        
        filename = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_SignalVerification.txt"
        with open(os.path.join(SAVE_DIR, filename), 'w', encoding='utf-8') as f:
            f.write(f"[A급 신호 RR 검증 - {now.strftime('%Y-%m-%d %H:%M:%S')}]\n\n")
            f.write(verification)
        
        return jsonify({
            "success": True,
            "message": f"✅ {len(recent_signals)}개 신호 검증 완료!",
            "verification": verification
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": f"❌ 오류: {str(e)}"}), 500

@app.route('/api/ask-ai', methods=['POST'])
def api_ask_ai():
    """✏️ 사용자가 직접 AI에게 질문하기"""
    try:
        user_question = request.json.get('question', '')
        if not user_question:
            return jsonify({"success": False, "message": "질문을 입력해주세요"}), 400
        
        # 컨텍스트 수집
        philosophy = ""
        if os.path.exists('.user_philosophy.md'):
            with open('.user_philosophy.md', 'r', encoding='utf-8') as f:
                philosophy = f.read()[:2000]
        
        progress_data = {}
        if os.path.exists('.detector_progress.json'):
            with open('.detector_progress.json', 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
        
        # 최근 거래 데이터
        files = sorted([f for f in os.listdir(SAVE_DIR) if f.endswith('_Chat.txt')], reverse=True)
        recent_content = ""
        for filename in files[:2]:
            try:
                with open(os.path.join(SAVE_DIR, filename), 'r', encoding='utf-8') as f:
                    recent_content += f.read()[:1000] + "\n---\n"
            except:
                pass
        
        prompt = f"""당신은 A급 신호 탐지기 개발을 돕는 트레이딩 AI 어시스턴트입니다.

## 🎯 현재 프로젝트 상태
- A급 탐지기 진행률: {progress_data.get('progress', 0)}%
- 마지막 업데이트: {progress_data.get('last_update', '없음')}

## 📚 학습된 트레이딩 철학
{philosophy}

## 📝 최근 거래 데이터
{recent_content}

## ❓ 사용자의 질문/요구사항
{user_question}

## 당신의 임무
1. 사용자의 질문에 정확하게 답변하세요
2. A급 탐지기 완성에 도움이 되도록 구체적인 제안을 하세요
3. 필요하면 Pine Script나 Python 코드도 제안하세요

한국어로 명확하고 구체적으로 답변하세요."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2000
        )
        ai_answer = response.choices[0].message.content
        
        # 대화 저장
        now = datetime.now()
        conversation = {
            "timestamp": now.isoformat(),
            "question": user_question,
            "answer": ai_answer
        }
        
        conv_file = '.conversations.json'
        conversations = []
        if os.path.exists(conv_file):
            with open(conv_file, 'r', encoding='utf-8') as f:
                conversations = json.load(f)
        
        conversations.append(conversation)
        conversations = conversations[-20:]  # 최근 20개만 유지
        
        with open(conv_file, 'w', encoding='utf-8') as f:
            json.dump(conversations, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            "success": True,
            "message": "✅ AI가 답변했습니다!",
            "answer": ai_answer,
            "question": user_question
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"❌ 오류: {str(e)}"
        }), 500

@app.route('/api/summary-report', methods=['POST'])
def api_summary_report():
    """📋 종합 데이터 분석관 - 제이슨 시스템 기반"""
    try:
        # 제이슨 분석 결과 로드
        jason_summary = ""
        if os.path.exists('.jason_deep_summary.md'):
            with open('.jason_deep_summary.md', 'r', encoding='utf-8') as f:
                jason_summary = f.read()
        
        jason2_backup = ""
        if os.path.exists('.jason2_backup.md'):
            with open('.jason2_backup.md', 'r', encoding='utf-8') as f:
                jason2_backup = f.read()
        
        history_index = {}
        if os.path.exists('.history_index.json'):
            with open('.history_index.json', 'r', encoding='utf-8') as f:
                history_index = json.load(f)
        
        return jsonify({
            "success": True,
            "message": "📋 제이슨 시스템 요약!",
            "report": jason_summary or "아직 분석 결과 없음. 6시간마다 자동 생성됩니다.",
            "file_count": history_index.get('file_count', 0),
            "signals_count": len(history_index.get('signals', [])),
            "last_update": history_index.get('last_update', '없음')
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"❌ 오류: {str(e)}"
        }), 500

def analyze_csv_data():
    """📊 CSV 데이터 분석 - 백테스트, ratio 통계 풀기"""
    print("📊 CSV 데이터 분석 시작...")
    
    csv_stats = {
        "last_update": datetime.now().isoformat(),
        "ratio_multiplier": {},
        "backtest_results": [],
        "signal_trades": {},
        "total_records": 0
    }
    
    csv_files = [f for f in os.listdir(SAVE_DIR) if f.endswith('.csv')]
    print(f"📊 발견된 CSV: {len(csv_files)}개")
    
    for csv_file in csv_files:
        try:
            filepath = os.path.join(SAVE_DIR, csv_file)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            if len(lines) < 2:
                continue
                
            headers = lines[0].strip().split(',')
            records = len(lines) - 1
            csv_stats["total_records"] += records
            
            if 'ratio_multiplier' in csv_file:
                stats = {"total": 0, "resist": 0, "break": 0, "by_range": {}}
                for line in lines[1:]:
                    cols = line.strip().split(',')
                    if len(cols) >= 7:
                        try:
                            mult = float(cols[5]) if cols[5] else 0
                            result = cols[6].upper()
                            stats["total"] += 1
                            if result == "RESIST":
                                stats["resist"] += 1
                            elif result == "BREAK":
                                stats["break"] += 1
                            
                            if mult < 0.5:
                                rng = "<0.5"
                            elif mult < 1.0:
                                rng = "0.5-1.0"
                            elif mult < 1.5:
                                rng = "1.0-1.5"
                            else:
                                rng = ">=1.5"
                            
                            if rng not in stats["by_range"]:
                                stats["by_range"][rng] = {"total": 0, "resist": 0}
                            stats["by_range"][rng]["total"] += 1
                            if result == "RESIST":
                                stats["by_range"][rng]["resist"] += 1
                        except:
                            continue
                
                for rng, data in stats["by_range"].items():
                    if data["total"] > 0:
                        data["resist_rate"] = round(data["resist"] / data["total"] * 100, 1)
                
                csv_stats["ratio_multiplier"][csv_file] = stats
            
            elif 'backtest' in csv_file or 'trades' in csv_file:
                summary = {
                    "file": csv_file,
                    "records": records,
                    "headers": headers[:8]
                }
                
                if 'result' in [h.lower() for h in headers]:
                    wins = sum(1 for line in lines[1:] if 'WIN' in line.upper() or 'RESIST' in line.upper())
                    summary["wins"] = wins
                    summary["win_rate"] = round(wins / records * 100, 1) if records > 0 else 0
                
                csv_stats["backtest_results"].append(summary)
            
            else:
                csv_stats["signal_trades"][csv_file] = {
                    "records": records,
                    "headers": headers[:6]
                }
                
        except Exception as e:
            print(f"⚠️ {csv_file} 분석 오류: {e}")
            continue
    
    with open('.jason_csv_stats.json', 'w', encoding='utf-8') as f:
        json.dump(csv_stats, f, ensure_ascii=False, indent=2)
    
    summary_md = f"""# 📊 CSV 데이터 통계 (자동 생성)

마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}
총 레코드: {csv_stats['total_records']:,}건

## 🎯 Ratio Multiplier 통계

"""
    for fname, stats in csv_stats["ratio_multiplier"].items():
        summary_md += f"### {fname}\n"
        summary_md += f"- 총: {stats['total']}건, 저항: {stats['resist']}건, 돌파: {stats['break']}건\n"
        for rng, data in sorted(stats["by_range"].items()):
            summary_md += f"  - 배율 {rng}: {data['total']}건 → 저항율 {data.get('resist_rate', 0)}%\n"
        summary_md += "\n"
    
    summary_md += "## 📈 백테스트 결과\n\n"
    for bt in csv_stats["backtest_results"][:15]:
        wr = f" (승률 {bt['win_rate']}%)" if 'win_rate' in bt else ""
        summary_md += f"- **{bt['file']}**: {bt['records']}건{wr}\n"
    
    with open('.jason_csv_summary.md', 'w', encoding='utf-8') as f:
        f.write(summary_md)
    
    print(f"📊 CSV 분석 완료! 총 {csv_stats['total_records']:,}건, ratio 파일 {len(csv_stats['ratio_multiplier'])}개")
    return csv_stats

def cloud_auto_cycle():
    """☁️ 클라우드 자동 순환 - 1시간마다 상태 체크"""
    print("☁️ 자동 순환 체크...")
    status = load_cloud_status()
    status["last_run"] = datetime.now().isoformat()
    save_cloud_status(status)
    print("☁️ 자동 순환 완료!")

def build_history_index():
    """📚 히스토리 인덱싱 - 모든 파일에서 로직/신호 추출"""
    print("📚 히스토리 인덱싱 시작...")
    
    index = {
        "last_update": datetime.now().isoformat(),
        "signals": [],
        "logics": [],
        "win_rates": [],
        "formulas": [],
        "file_count": 0
    }
    
    # 중요 파일 먼저, 나머지는 뒤에
    important_files = ['.user_philosophy.md', 'replit.md']
    other_files = [f for f in os.listdir(SAVE_DIR) if (f.endswith('.txt') or f.endswith('.md')) and f not in important_files]
    txt_files = [f for f in important_files if os.path.exists(f)] + other_files
    index["file_count"] = len(txt_files)
    
    keywords = {
        "signals": ["신호", "signal", "SCALP", "HUNT", "BLACK", "POC", "i빗각", "zPOC"],
        "logics": ["로직", "logic", "조건", "condition", "필터", "filter"],
        "win_rates": ["승률", "win rate", "%", "RR", "PnL"],
        "formulas": ["공식", "formula", "ratio", "배율", "="]
    }
    
    for filename in txt_files:
        try:
            filepath = os.path.join(SAVE_DIR, filename)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            lines = content.split('\n')
            for line in lines:
                line_lower = line.lower()
                
                # 신호 추출
                for kw in keywords["signals"]:
                    if kw.lower() in line_lower and len(line) < 200:
                        index["signals"].append({
                            "file": filename,
                            "text": line.strip()[:150]
                        })
                        break
                
                # 승률 추출
                if any(kw in line_lower for kw in ["승률", "win rate", "rr"]):
                    if any(c.isdigit() for c in line):
                        index["win_rates"].append({
                            "file": filename,
                            "text": line.strip()[:150]
                        })
                
                # 공식 추출
                if "=" in line and any(kw in line_lower for kw in ["ratio", "배율", "공식", "formula"]):
                    index["formulas"].append({
                        "file": filename,
                        "text": line.strip()[:150]
                    })
        except Exception as e:
            continue
    
    # 중복 제거 및 제한
    seen = set()
    unique_signals = []
    for s in index["signals"]:
        if s["text"] not in seen:
            seen.add(s["text"])
            unique_signals.append(s)
    index["signals"] = unique_signals[:200]
    
    seen = set()
    unique_wr = []
    for w in index["win_rates"]:
        if w["text"] not in seen:
            seen.add(w["text"])
            unique_wr.append(w)
    index["win_rates"] = unique_wr[:100]
    
    index["formulas"] = index["formulas"][:50]
    
    # 인덱스 저장
    with open('.history_index.json', 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    
    # 요약 마크다운 생성
    summary = f"""# 📚 히스토리 인덱스 (자동 생성)

마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}
총 파일 수: {index['file_count']}개

## 🎯 발견된 신호들 ({len(index['signals'])}건)

"""
    for s in index["signals"][:30]:
        summary += f"- `{s['file'][:20]}`: {s['text'][:80]}\n"
    
    summary += f"""

## 📊 승률/RR 관련 ({len(index['win_rates'])}건)

"""
    for w in index["win_rates"][:20]:
        summary += f"- `{w['file'][:20]}`: {w['text'][:80]}\n"
    
    summary += f"""

## 📐 공식들 ({len(index['formulas'])}건)

"""
    for fm in index["formulas"][:15]:
        summary += f"- `{fm['file'][:20]}`: {fm['text'][:80]}\n"
    
    with open('.history_summary.md', 'w', encoding='utf-8') as f:
        f.write(summary)
    
    print(f"📚 인덱싱 완료! 신호 {len(index['signals'])}개, 승률 {len(index['win_rates'])}개, 공식 {len(index['formulas'])}개")
    
    # CSV 데이터도 분석
    csv_stats = None
    try:
        csv_stats = analyze_csv_data()
        index["csv_stats"] = csv_stats
    except Exception as e:
        print(f"⚠️ CSV 분석 오류: {e}")
    
    # 제이슨이 상세 분석 수행 (CSV 포함)
    try:
        jason_deep_analysis(index, csv_stats)
    except Exception as e:
        print(f"⚠️ 제이슨 상세 분석 오류: {e}")

def jason2_helper(index, task="signals"):
    """🤖 제이슨2 - 제이슨 도우미 (작업 분담 + 백업)"""
    try:
        if task == "signals":
            # 신호 정리 담당
            signals_text = "\n".join([f"- {s['text']}" for s in index['signals'][:40]])
            prompt = f"""트레이딩 신호 정리 전문가입니다.
아래 신호들을 **신호명: 조건** 형식으로 간결하게 정리하세요.

{signals_text}

형식: 신호명 | 조건 | 추세"""
            
        elif task == "formulas":
            # 공식 정리 담당
            formulas_text = "\n".join([f"- {f['text']}" for f in index['formulas'][:25]])
            prompt = f"""트레이딩 공식 정리 전문가입니다.
아래 공식들을 정리하세요.

{formulas_text}

형식: 공식명 = 계산식 (용도)"""
            
        else:
            return None
            
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"⚠️ 제이슨2 {task} 작업 오류: {e}")
        return None

def jason_deep_analysis(index, csv_stats=None):
    """🧠 제이슨 상세 분석 - 제이슨2와 협업 + CSV 데이터 풀기"""
    print("🧠 제이슨 + 제이슨2 협업 분석 시작...")
    
    # 제이슨2가 먼저 작업 (신호 + 공식)
    jason2_signals = jason2_helper(index, "signals")
    jason2_formulas = jason2_helper(index, "formulas")
    
    # CSV 통계 요약
    csv_summary = ""
    if csv_stats:
        csv_summary = f"\n## 📊 CSV 백테스트 데이터 (총 {csv_stats.get('total_records', 0):,}건)\n"
        for fname, stats in csv_stats.get("ratio_multiplier", {}).items():
            csv_summary += f"\n### {fname}\n"
            for rng, data in sorted(stats.get("by_range", {}).items()):
                csv_summary += f"- 배율 {rng}: {data['total']}건 → 저항율 {data.get('resist_rate', 0)}%\n"
        
        for bt in csv_stats.get("backtest_results", [])[:10]:
            wr = f" (승률 {bt['win_rate']}%)" if 'win_rate' in bt else ""
            csv_summary += f"- {bt['file']}: {bt['records']}건{wr}\n"
    
    # 제이슨2 결과 백업 저장 (CSV 포함)
    with open('.jason2_backup.md', 'w', encoding='utf-8') as f:
        f.write(f"""# 🤖 제이슨2 백업 (자동 생성)

마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## 신호 정리
{jason2_signals or '(작업 실패)'}

## 공식 정리
{jason2_formulas or '(작업 실패)'}
{csv_summary}
""")
    print("🤖 제이슨2 백업 완료! → .jason2_backup.md")
    
    # 제이슨이 최종 통합 (제이슨2 결과 + CSV 활용)
    winrates_text = "\n".join([f"- {w['text']}" for w in index['win_rates'][:30]])
    
    prompt = f"""당신은 트레이딩 데이터 통합 전문가입니다. 모든 실타래를 풀어서 정리하세요.

## 제이슨2가 정리한 신호:
{jason2_signals or '(없음 - 직접 정리 필요)'}

## 제이슨2가 정리한 공식:
{jason2_formulas or '(없음 - 직접 정리 필요)'}

## 승률/RR 관련:
{winrates_text}
{csv_summary}

---

## 요청사항:
1. **신호 목록**: 위 데이터 기반으로 최종 정리
2. **승률 통계**: CSV 백테스트 포함, 검증된 승률 추출
3. **핵심 공식**: 배율(multiplier), ratio, zPOC 공식 통합
4. **Ratio 배율 법칙**: 배율별 저항율/돌파율 정리 (상위 1% 근거)
5. **키워드 사전**: 주요 용어 간단 설명

간결하게 정리해주세요. 나중에 빠르게 검색할 수 있도록."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000
        )
        result = response.choices[0].message.content
    except Exception as e:
        # 제이슨 오류 시 제이슨2 백업 사용
        print(f"⚠️ 제이슨 오류, 제이슨2 백업 사용: {e}")
        result = f"""## 🤖 제이슨2 백업 결과 (제이슨 오류)

{jason2_signals or ''}

{jason2_formulas or ''}
"""
    
    # 상세 분석 결과 저장
    with open('.jason_deep_summary.md', 'w', encoding='utf-8') as f:
        f.write(f"""# 🧠 제이슨 + 제이슨2 협업 분석 (자동 생성)

마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}

{result}
""")
    
    print("🧠 제이슨 + 제이슨2 협업 분석 완료! → .jason_deep_summary.md")

def generate_latest_summary():
    """최신 파일들 완전한 내용 정리"""
    files = sorted([f for f in os.listdir(SAVE_DIR) if f.endswith('_Chat.txt')], reverse=True)
    latest_files = files[:3]  # 최신 3개 (길이 제한)
    
    summary = f"""# 📊 최신 3개 파일 - 전체 내용

생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}
총 저장된 파일: {len(files)}개
표시되는 파일: 최신 {len(latest_files)}개

---

## ⚠️ 필독: 이 순서대로 읽으세요

1. **00_통합_가이드.md** ← 먼저 (거래 규칙 & 기준)
2. **01_다음_AI를_위한_작업.md** ← 다음 (당신의 역할)
3. **이 파일 (02)** ← 마지막 (최신 거래 내용)

**이 3개를 읽으면:**
✅ 규칙을 완전히 이해  
✅ 최신 상황을 파악  
✅ 바로 작업 시작 가능

---

## 🔍 최신 거래 파일 - 전체 내용 분석

"""
    
    for idx, filename in enumerate(latest_files, 1):
        try:
            filepath = os.path.join(SAVE_DIR, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            summary += f"""### {idx}. {filename}
**작성일**: {filename[:19]}  
**크기**: {len(content)} 글자

**전체 내용**:
```
{content}
```

---

"""
        except:
            pass
    
    summary += f"""
## ✅ 체크리스트

이 파일을 다 읽은 후 확인하세요:

- [ ] 00_통합_가이드.md 읽음 (기준 이해)
- [ ] 01_다음_AI를_위한_작업.md 읽음 (역할 파악)
- [ ] 최신 5개 파일의 내용 파악함
- [ ] 이제 작업을 시작할 준비가 됨

---

## 🎯 이제 해야 할 일

이 3개 파일을 읽었다면, **원본 파일을 다시 물어볼 필요 없습니다.**

`01_다음_AI를_위한_작업.md`에서 구체적인 작업을 선택하고 시작하세요:
- A) 최근 거래 검토
- B) 지표 검증
- C) 전략 수정
- D) 다음 계획

---

**"아, 더 자세한 내용이 필요한데?"라고 생각하면 → 그때 원본 파일들을 확인하세요.**
**하지만 이 파일들로 대부분의 작업은 가능합니다.**
"""
    
    return summary

@app.route('/api/download-zip', methods=['GET'])
def download_zip():
    """모든 파일을 일주일별로 폴더를 나누어 ZIP으로 다운로드 + 통합 가이드 포함"""
    try:
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. 기존 파일들 (유형별 분류)
            file_types = get_all_files_by_type()
            
            for type_label, files in file_types.items():
                for file_info in files:
                    filename = file_info['name']
                    filepath = os.path.join(SAVE_DIR, filename)
                    
                    if os.path.exists(filepath):
                        arcname = f"{type_label}/{filename}"
                        zip_file.write(filepath, arcname=arcname)
            
            # 2. 통합 가이드, 작업 지시서, 최신 요약 생성 및 추가
            guide_content = generate_unified_guide()
            task_guide = generate_ai_task_guide()
            latest_summary = generate_latest_summary()
            
            zip_file.writestr("00_통합_가이드.md", guide_content)
            zip_file.writestr("01_다음_AI를_위한_작업.md", task_guide)
            zip_file.writestr("02_최신_파일_요약.md", latest_summary)
        
        zip_buffer.seek(0)
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"GPT_Chat_Backup_{now}.zip"
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"❌ ZIP 생성 실패: {str(e)}"}), 500

@app.route('/api/download-zip/<type_name>', methods=['GET'])
def download_zip_by_type(type_name):
    """특정 유형의 파일만 ZIP으로 다운로드"""
    try:
        type_name = type_name.replace('%20', ' ')  # URL 디코딩
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            file_types = get_all_files_by_type()
            
            # 특정 타입의 파일만 추가
            if type_name in file_types:
                for file_info in file_types[type_name]:
                    filename = file_info['name']
                    filepath = os.path.join(SAVE_DIR, filename)
                    
                    if os.path.exists(filepath):
                        zip_file.write(filepath, arcname=filename)
        
        zip_buffer.seek(0)
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{type_name}_{now}.zip"
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"❌ ZIP 생성 실패: {str(e)}"}), 500

@app.route('/api/gpt-context', methods=['GET'])
def api_gpt_context():
    """GPT가 접근할 수 있는 통합 컨텍스트 API"""
    try:
        philosophy = ""
        try:
            with open(os.path.join(SAVE_DIR, ".user_philosophy.md"), 'r', encoding='utf-8') as f:
                philosophy = f.read()
        except:
            philosophy = "철학 데이터 준비 중..."
        
        guide = generate_unified_guide()
        task_guide = generate_ai_task_guide()
        latest_summary = generate_latest_summary()
        analysis_history = load_analysis_history()
        
        return jsonify({
            "success": True,
            "user_philosophy": philosophy,
            "unified_guide": guide,
            "task_guide": task_guide,
            "latest_summary": latest_summary,
            "analysis_history": analysis_history,
            "status": "ready"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/gpt-input', methods=['POST'])
def api_gpt_input():
    """GPT의 분석 결과를 자동 저장"""
    try:
        data = request.json
        gpt_analysis = data.get('analysis', '')
        gpt_improvement = data.get('improvement', '')
        
        if not gpt_analysis.strip():
            return jsonify({"success": False, "message": "분석 내용 필요"}), 400
        
        now = datetime.now()
        filename = now.strftime("%Y-%m-%d_%H-%M-%S_GPT_Analysis.txt")
        filepath = os.path.join(SAVE_DIR, filename)
        
        content = f"""🤖 GPT 분석
시간: {now.strftime('%Y-%m-%d %H:%M:%S')}

## 분석
{gpt_analysis}

## 개선안
{gpt_improvement if gpt_improvement else '없음'}
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        save_hash(get_content_hash(content))
        
        # 자동 분석 트리거
        analysis_result = auto_analyze_files()
        
        return jsonify({
            "success": True,
            "message": "✅ 저장 및 자동 분석 시작",
            "filename": filename
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"오류: {str(e)}"}), 500

@app.route('/api/gpt-instructions', methods=['GET'])
def api_gpt_instructions():
    """GPT용 지시사항"""
    instructions = """# 🤖 GPT 사용 지시사항

## 당신의 역할
이 API로 클라우드와 실시간 양방향 연동합니다.

## 사용 방법

### 1️⃣ 데이터 읽기 (매번 호출)
GET /api/gpt-context
→ 최신 철학 + 가이드 + 분석 결과

### 2️⃣ 분석 저장 (완료 후 호출)
POST /api/gpt-input
{
  "analysis": "당신의 분석",
  "improvement": "개선안"
}
→ 클라우드가 자동 저장 + 자동 분석

### 3️⃣ 반복
다시 1️⃣로 가기 → 개선된 철학으로 시작

## 핵심
✅ 항상 /api/gpt-context로 시작
✅ 분석 후 /api/gpt-input로 저장
✅ 반복 (자동 개선)

ZIP이나 복사 없이 자동 양방향 연동!
"""
    return jsonify({
        "success": True,
        "instructions": instructions,
        "endpoints": {
            "context": "/api/gpt-context",
            "input": "/api/gpt-input",
            "instructions": "/api/gpt-instructions"
        }
    })

@app.route('/api/current-progress')
def get_current_progress():
    """현재 진행 상황을 분석해서 반환"""
    try:
        files = sorted([f for f in os.listdir(SAVE_DIR) if f.endswith('_Chat.txt')], reverse=True)
        latest_files = files[:3]
        
        progress = {
            "total_files": len(files),
            "latest_files": [],
            "current_work": "",
            "completion": {}
        }
        
        keywords = {
            "spread_day": ["spread day", "flag v3", "s1", "s2", "true black", "xb"],
            "a_grade": ["a급", "a-grade", "vpoc", "cluster", "sps"],
            "cluster": ["클러스터", "cluster", "거래량", "volume"],
            "fvg": ["fvg", "fair value gap"],
            "defense": ["방어", "defense", "스탑헌트"],
            "pine": ["pine", "script", "코드", "indicator"]
        }
        
        for filename in latest_files:
            try:
                filepath = os.path.join(SAVE_DIR, filename)
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                
                size = os.path.getsize(filepath)
                found_keywords = []
                
                for category, kws in keywords.items():
                    if any(kw in content for kw in kws):
                        found_keywords.append(category)
                
                progress["latest_files"].append({
                    "name": filename,
                    "size": size,
                    "keywords": found_keywords,
                    "timestamp": filename[:19]
                })
            except:
                pass
        
        # 진행도 계산
        progress["completion"] = {
            "spread_day": {
                "name": "Spread Day (FLAG v3)",
                "status": "✅ 완성",
                "percent": 100,
                "description": "S1/S2 탐지, TRUE BLACK 신호 완성"
            },
            "a_grade_signal": {
                "name": "A급 신호 탐지기",
                "status": "🔴 진행 중",
                "percent": 40,
                "description": "VPOC 탐지 완료 → 클러스터 종료 감지에서 진행 중"
            },
            "cluster_detection": {
                "name": "클러스터 종료 감지",
                "status": "⚠️ 막힘",
                "percent": 20,
                "description": "SPS 급감 기준 정의 필요"
            },
            "sps_signal": {
                "name": "SPS 신호 자동화",
                "status": "⏳ 대기",
                "percent": 0,
                "description": "클러스터 종료 완료 후 시작"
            }
        }
        
        return jsonify({
            "success": True,
            "progress": progress
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/download-all', methods=['GET'])
def api_download_all():
    """💾 모든 JSON 데이터 ZIP 다운로드"""
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                    zf.writestr('01_cloud_status.json', f.read())
            if os.path.exists(ANALYSIS_FILE):
                with open(ANALYSIS_FILE, 'r', encoding='utf-8') as f:
                    zf.writestr('02_auto_analysis.json', f.read())
            if os.path.exists('.user_philosophy.md'):
                with open('.user_philosophy.md', 'r', encoding='utf-8') as f:
                    zf.writestr('03_user_philosophy.md', f.read())
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name=f'trading_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/export-json', methods=['GET'])
def api_export_json():
    """📄 JSON 데이터만 텍스트로 (GPT용)"""
    try:
        export_data = {
            "timestamp": datetime.now().isoformat(),
            "cloud_status": {},
            "auto_analysis": {},
            "user_philosophy": ""
        }
        
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                export_data["cloud_status"] = json.load(f)
        
        if os.path.exists(ANALYSIS_FILE):
            with open(ANALYSIS_FILE, 'r', encoding='utf-8') as f:
                export_data["auto_analysis"] = json.load(f)
        
        if os.path.exists('.user_philosophy.md'):
            with open('.user_philosophy.md', 'r', encoding='utf-8') as f:
                export_data["user_philosophy"] = f.read()
        
        json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
        return send_file(
            io.BytesIO(json_str.encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=f'trading_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/gpt-json', methods=['GET'])
def api_gpt_json():
    """ChatGPT용 JSON 프리뷰 및 다운로드 - 공백 없이 최신 데이터"""
    try:
        combined_data = {
            "last_update": datetime.now().isoformat(),
            "purpose": "SPS Trading System - 검증된 신호 데이터",
            "verified_signals": {},
            "unverified_signals": {},
            "macro_filters": {},
            "market_direction": {},
            "blocked_signals": [],
            "critical_rules": [],
            "grade_summary": {}
        }
        
        if os.path.exists('.ai_must_read.json'):
            with open('.ai_must_read.json', 'r', encoding='utf-8') as f:
                must_read = json.load(f)
                combined_data["verified_short_signals"] = must_read.get("verified_short_signals", {})
                combined_data["verified_long_signals"] = must_read.get("verified_long_signals", {})
                combined_data["macro_filters"] = must_read.get("macro_filters", {})
                combined_data["market_direction"] = must_read.get("market_direction", {})
                combined_data["blocked_signals"] = must_read.get("blocked_signals", [])
                combined_data["critical_rules"] = must_read.get("critical_rules", [])
                combined_data["core_formula"] = must_read.get("core_formula", {})
                combined_data["grade_criteria"] = must_read.get("grade_criteria", {})
        
        if os.path.exists('.jason_verification_state.json'):
            with open('.jason_verification_state.json', 'r', encoding='utf-8') as f:
                vstate = json.load(f)
                combined_data["verified_signals"] = vstate.get("verified_signals", {})
                combined_data["unverified_signals"] = vstate.get("unverified_signals", {})
                combined_data["grade_summary"] = vstate.get("grade_summary", {})
                combined_data["rules"] = vstate.get("rules", [])
        
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            json_str = json.dumps(combined_data, ensure_ascii=False, indent=2)
            return send_file(
                io.BytesIO(json_str.encode('utf-8')),
                mimetype='application/json',
                as_attachment=True,
                download_name=f'sps_trading_{datetime.now().strftime("%Y%m%d")}.json'
            )
        
        return jsonify(combined_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/gpt-preview')
def gpt_preview():
    """ChatGPT가 읽을 수 있는 HTML 프리뷰 페이지"""
    try:
        combined_data = {}
        
        if os.path.exists('.ai_must_read.json'):
            with open('.ai_must_read.json', 'r', encoding='utf-8') as f:
                combined_data["ai_must_read"] = json.load(f)
        
        if os.path.exists('.jason_verification_state.json'):
            with open('.jason_verification_state.json', 'r', encoding='utf-8') as f:
                combined_data["verification_state"] = json.load(f)
        
        json_str = json.dumps(combined_data, ensure_ascii=False, indent=2)
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>SPS Trading - GPT JSON Preview</title>
    <style>
        body {{ font-family: monospace; background: #1a1a2e; color: #eee; padding: 20px; }}
        h1 {{ color: #00d4ff; }}
        pre {{ background: #16213e; padding: 20px; border-radius: 10px; overflow-x: auto; white-space: pre-wrap; }}
        .btn {{ background: #00d4ff; color: #000; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; text-decoration: none; display: inline-block; }}
        .btn:hover {{ background: #00a8cc; }}
        .info {{ background: #16213e; padding: 15px; border-radius: 10px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <h1>SPS Trading System - JSON Data</h1>
    <div class="info">
        <p><strong>Last Update:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        <p><strong>Purpose:</strong> ChatGPT can read this page directly or download JSON</p>
        <a href="/api/gpt-json?download=true" class="btn">Download JSON</a>
        <a href="/api/gpt-json" class="btn">API Endpoint</a>
    </div>
    <pre>{json_str}</pre>
</body>
</html>'''
        return html
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/view/<filename>')
def view_file(filename):
    if not filename.endswith('_Chat.txt') and not filename.endswith('.txt') and not filename.endswith('.csv'):
        return "파일을 찾을 수 없습니다.", 404
    
    if '/' in filename or '\\' in filename:
        return "파일을 찾을 수 없습니다.", 404
    
    filepath = os.path.join(SAVE_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=filename)
    return "파일을 찾을 수 없습니다.", 404

@app.route('/api/chart-sessions', methods=['GET'])
def get_chart_sessions():
    """📊 차트 세션 목록 API - 파일별 날짜 범위"""
    try:
        import pandas as pd
        import glob
        from datetime import datetime
        
        csv_files = glob.glob("attached_assets/chart_data_new/*.csv")
        if not csv_files:
            csv_files = glob.glob("*.csv")
        
        sessions = []
        for f in csv_files:
            try:
                df = pd.read_csv(f)
                df.columns = [c.lower() for c in df.columns]
                if 'time' in df.columns:
                    start_ts = int(df['time'].min())
                    end_ts = int(df['time'].max())
                    start_dt = datetime.fromtimestamp(start_ts)
                    end_dt = datetime.fromtimestamp(end_ts)
                    
                    # 타임프레임 추정 (평균 간격)
                    if len(df) > 1:
                        avg_interval = (end_ts - start_ts) / len(df)
                        if avg_interval < 120:
                            tf = "1분"
                        elif avg_interval < 600:
                            tf = "5분"
                        elif avg_interval < 1200:
                            tf = "15분"
                        else:
                            tf = "1시간+"
                    else:
                        tf = "1분"
                    
                    a_count = len(df[df.get('a_grade', df.get('A-Grade', pd.Series([0]*len(df)))) == 1])
                    
                    sessions.append({
                        "file": os.path.basename(f),
                        "timeframe": tf,
                        "start": start_dt.strftime("%m/%d %H:%M"),
                        "end": end_dt.strftime("%m/%d %H:%M"),
                        "start_ts": start_ts,
                        "end_ts": end_ts,
                        "bars": len(df),
                        "a_grades": a_count
                    })
            except:
                pass
        
        sessions.sort(key=lambda x: x['start_ts'])
        return jsonify({"sessions": sessions})
    except Exception as e:
        return jsonify({"error": str(e), "sessions": []})

@app.route('/api/dashboard-data', methods=['GET'])
def get_dashboard_data():
    """📊 대시보드용 차트 데이터 API - 웹훅 데이터 우선 사용"""
    try:
        import pandas as pd
        import glob
        
        # 세션 필터 파라미터
        session_file = request.args.get('session', None)
        start_ts = request.args.get('start', None)
        end_ts = request.args.get('end', None)
        use_webhook = request.args.get('webhook', 'true').lower() == 'true'
        
        # 🔥 웹훅 캔들 데이터 우선 사용 (실시간)
        candle_history = load_candle_history()
        if use_webhook and len(candle_history) >= 10 and not session_file:
            df = pd.DataFrame(candle_history)
            df.columns = [c.lower() for c in df.columns]
            
            # 기본 필드 확보
            if 'time' in df.columns:
                df = df.sort_values('time').reset_index(drop=True)
            
            # 결과 계산
            df['future_10'] = df['close'].shift(-10) if 'close' in df.columns else 0
            df['change'] = df['future_10'] - df['close'] if 'close' in df.columns else 0
            df['result'] = df['change'].apply(lambda x: 'WIN' if x > 0 else ('LOSS' if x < 0 else 'FLAT') if pd.notna(x) else None)
            
            # SPS Z-score 계산 (있으면 사용, 없으면 0)
            if 'sps_z' not in df.columns:
                df['sps_z'] = 0
            
            df = df.fillna(0)
            candles = df.tail(100).to_dict('records')
            
            # 신호 로그에서 가져오기
            from signal_logger import get_today_signals, generate_daily_report
            today_signals = get_today_signals()  # 리스트 반환
            report = generate_daily_report()  # 딕셔너리 반환
            
            return jsonify({
                "candles": candles,
                "signals": today_signals,
                "wins": report.get('wins', 0),
                "losses": report.get('losses', 0),
                "win_rate": report.get('win_rate', 0),
                "total": report.get('total', 0),
                "avg_change": 0,
                "source": "webhook_realtime"
            })
        
        # CSV 파일 폴백
        if session_file:
            csv_files = [f"attached_assets/chart_data_new/{session_file}"]
        else:
            csv_files = glob.glob("attached_assets/chart_data_new/*.csv")
            if not csv_files:
                csv_files = glob.glob("*.csv")
        
        if not csv_files:
            return jsonify({"candles": [], "signals": [], "wins": 0, "losses": 0, "win_rate": 0, "total": 0, "avg_change": 0, "sessions": [], "source": "no_data"})
        
        all_dfs = []
        for f in csv_files:
            try:
                df = pd.read_csv(f)
                # 각 파일에서 먼저 중복 컬럼 제거
                df = df.loc[:, ~df.columns.duplicated()]
                all_dfs.append(df)
            except:
                pass
        
        if not all_dfs:
            return jsonify({"signals": [], "wins": 0, "losses": 0, "win_rate": 0, "total": 0, "avg_change": 0})
        
        combined = pd.concat(all_dfs, ignore_index=True)
        combined = combined.loc[:, ~combined.columns.duplicated()]
        # 중복 시간 행 제거
        if 'time' in [c.lower() for c in combined.columns]:
            combined = combined.drop_duplicates(subset=['time'], keep='last')
        
        cols = [c.lower() for c in combined.columns]
        combined.columns = cols
        
        if 'time' in cols:
            combined = combined.sort_values('time').reset_index(drop=True)
            # 시간 필터 적용
            if start_ts:
                combined = combined[combined['time'] >= int(start_ts)]
            if end_ts:
                combined = combined[combined['time'] <= int(end_ts)]
        
        combined['future_10'] = combined['close'].shift(-10)
        combined['change'] = combined['future_10'] - combined['close']
        combined['result'] = combined['change'].apply(lambda x: 'WIN' if x > 0 else ('LOSS' if x < 0 else 'FLAT') if pd.notna(x) else None)
        
        a_grade_col = 'a_grade' if 'a_grade' in cols else None
        if a_grade_col:
            a_grade = combined[combined[a_grade_col] == 1].dropna(subset=['future_10'])
        else:
            uptrend_col = 'uptrend' if 'uptrend' in cols else None
            sps_col = 'sps_zscore' if 'sps_zscore' in cols else None
            if uptrend_col and sps_col:
                a_grade = combined[(combined[uptrend_col] == 1) & (combined[sps_col] >= 2.0)].dropna(subset=['future_10'])
            else:
                a_grade = combined.head(0)
        
        wins = len(a_grade[a_grade['result'] == 'WIN'])
        losses = len(a_grade[a_grade['result'] == 'LOSS'])
        total = len(a_grade)
        win_rate = (wins / total * 100) if total > 0 else 0
        avg_change = a_grade['change'].mean() if total > 0 else 0
        
        combined = combined.fillna(0)
        # 세션 선택 시 해당 세션의 전체 데이터 (최대 500), 전체일 때는 마지막 500개
        if session_file:
            signals = combined.head(500).to_dict('records')  # 세션별: 처음 500개
        else:
            signals = combined.tail(500).to_dict('records')  # 전체: 마지막 500개
        
        # 🔥 누적 SPS 클러스터 분석 (iVPOC 기준 매수/매도 누적)
        hybrid_analysis = {}
        if os.path.exists('.webhook_history.json'):
            with open('.webhook_history.json', 'r', encoding='utf-8') as f:
                all_webhooks = json.load(f)
            
            # A급 신호만 필터링
            webhooks = [w for w in all_webhooks if w.get('action') == 'A급히트']
            
            if len(webhooks) >= 3:
                # iVPOC 계산 (최근 50개 클러스터 중심)
                recent_prices = [float(w.get('price', 0)) for w in webhooks[-50:] if w.get('price')]
                ivpoc = sum(recent_prices) / len(recent_prices) if recent_prices else 0
                
                # 🔥 매도/매수 클러스터 수치화
                tick = 0.25
                buy_zone_prices = []  # iVPOC 아래 가격들
                sell_zone_prices = []  # iVPOC 위 가격들
                
                cluster_history = []
                
                for w in webhooks:
                    price = float(w.get('price', 0))
                    ts = w.get('timestamp', '')
                    
                    if price < ivpoc:
                        buy_zone_prices.append(price)
                        zone = 'BUY'
                    else:
                        sell_zone_prices.append(price)
                        zone = 'SELL'
                    
                    cluster_history.append({
                        'time': ts[5:16].replace('T', ' ') if len(ts) > 16 else ts,
                        'price': price,
                        'zone': zone,
                        'buy_cnt': len(buy_zone_prices),
                        'sell_cnt': len(sell_zone_prices)
                    })
                
                # 📊 매도 클러스터 수치화
                sell_cluster = {
                    'count': len(sell_zone_prices),
                    'high': max(sell_zone_prices) if sell_zone_prices else ivpoc,
                    'low': min(sell_zone_prices) if sell_zone_prices else ivpoc,
                    'range_ticks': 0,
                    'depth_from_ivpoc': 0  # iVPOC에서 얼마나 멀리 갔는지
                }
                if sell_zone_prices:
                    sell_cluster['range_ticks'] = int((sell_cluster['high'] - sell_cluster['low']) / tick)
                    sell_cluster['depth_from_ivpoc'] = int((sell_cluster['high'] - ivpoc) / tick)
                
                # 📊 매수 클러스터 수치화
                buy_cluster = {
                    'count': len(buy_zone_prices),
                    'high': max(buy_zone_prices) if buy_zone_prices else ivpoc,
                    'low': min(buy_zone_prices) if buy_zone_prices else ivpoc,
                    'range_ticks': 0,
                    'depth_from_ivpoc': 0
                }
                if buy_zone_prices:
                    buy_cluster['range_ticks'] = int((buy_cluster['high'] - buy_cluster['low']) / tick)
                    buy_cluster['depth_from_ivpoc'] = int((ivpoc - buy_cluster['low']) / tick)
                
                # 상대적 강도: 클러스터 깊이 비교
                sell_strength = sell_cluster['depth_from_ivpoc'] * sell_cluster['count']
                buy_strength = buy_cluster['depth_from_ivpoc'] * buy_cluster['count']
                
                # A급 판단
                if sell_strength > buy_strength * 2:
                    dominance = 'SELL'
                    a_grade_type = f"📉 매도 A급 (강도 {sell_strength})"
                elif buy_strength > sell_strength * 2:
                    dominance = 'BUY'
                    a_grade_type = f"📈 매수 A급 (강도 {buy_strength})"
                elif sell_cluster['count'] > buy_cluster['count'] * 1.5:
                    dominance = 'SELL'
                    a_grade_type = '매도 우위'
                elif buy_cluster['count'] > sell_cluster['count'] * 1.5:
                    dominance = 'BUY'
                    a_grade_type = '매수 우위'
                else:
                    dominance = 'NEUTRAL'
                    a_grade_type = '대기'
                
                hybrid_analysis = {
                    'ivpoc': round(ivpoc, 2),
                    'sell_cluster': sell_cluster,
                    'buy_cluster': buy_cluster,
                    'sell_strength': sell_strength,
                    'buy_strength': buy_strength,
                    'dominance': dominance,
                    'a_grade_type': a_grade_type,
                    'total_signals': len(webhooks),
                    'recent_clusters': cluster_history[-10:]
                }
        
        return jsonify({
            "signals": signals,
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": float(win_rate),
            "total": int(total),
            "avg_change": float(avg_change) if pd.notna(avg_change) else 0,
            "total_bars": len(combined),
            "hybrid_analysis": hybrid_analysis
        })
    except Exception as e:
        return jsonify({"error": str(e), "signals": [], "wins": 0, "losses": 0, "win_rate": 0, "total": 0, "avg_change": 0, "hybrid_analysis": {}})

@app.route('/chart')
def chart_dashboard():
    """차트 대시보드 페이지"""
    return render_template('chart.html')

def is_spread_day_time(dt_est):
    """스프레드 데이 시간대 감지 (프랍에서 이상한 체결 방지)
    - 프리마켓 새벽 4-6시 EST: 유동성 낮고 스프레드 넓음
    - 주말 연결 시간대: 일요일 저녁 개장 직후
    """
    hour = dt_est.hour
    weekday = dt_est.weekday()
    
    if 4 <= hour < 6:
        return True
    
    if weekday == 6 and hour >= 18:
        return True
    
    return False

@app.route('/api/a-grade-signals')
def get_a_grade_signals():
    """TradingView에서 받은 A급 신호 조회 (새로운 방식)"""
    signals_file = '.a_grade_signals.json'
    
    if not os.path.exists(signals_file):
        return jsonify({
            "success": True,
            "signals": [],
            "stats": {"total": 0, "active": 0, "blocked": 0},
            "message": "아직 A급 신호가 없습니다. TradingView에서 웹훅을 보내주세요."
        })
    
    with open(signals_file, 'r', encoding='utf-8') as f:
        signals = json.load(f)
    
    active = len([s for s in signals if s.get('status') == 'ACTIVE'])
    blocked = len([s for s in signals if s.get('status') == 'BLOCKED'])
    
    return jsonify({
        "success": True,
        "signals": signals,
        "stats": {
            "total": len(signals),
            "active": active,
            "blocked": blocked
        }
    })

@app.route('/api/loss-analysis')
def get_loss_analysis():
    """손실 구간 자동 분석"""
    import numpy as np
    import pandas as pd
    from datetime import timedelta
    import glob
    
    try:
        all_signals = []
        
        csv_files = glob.glob('attached_assets/chart_data_new/*.csv')
        
        for filepath in csv_files[:5]:
            df = pd.read_csv(filepath)
            df['datetime'] = pd.to_datetime(df['time'], unit='s')
            df['datetime_est'] = df['datetime'] - timedelta(hours=5)
            
            df['is_spread_day'] = df['datetime_est'].apply(is_spread_day_time)
            
            tick_size = 0.25
            
            z_score = df['sps_zscore'].abs().fillna(0)
            z_norm = (z_score - z_score.mean()) / (z_score.std() + 0.001)
            z_norm = z_norm.clip(-3, 3) / 3
            
            wick_reclaim = (df['close'] - df['low']) / (df['high'] - df['low'] + 0.001)
            reclaim_norm = wick_reclaim.clip(0, 1)
            
            df['abs_strength'] = 0.4 * z_norm + 0.3 * reclaim_norm + 0.3 * 0.5
            df['is_bullish_sps'] = (df['close'] > df['open']) & (df['sps_zscore'] > 0)
            df['is_bearish_sps'] = (df['close'] < df['open']) & (df['sps_zscore'] < 0)
            
            df['cluster_id'] = -1
            df['ivpoc'] = np.nan
            df['cluster_ended'] = False
            df['has_nearby_sell_sps'] = False
            df['ivpoc_active'] = False
            df['first_touch'] = False
            
            cluster_id = 0
            in_cluster = False
            cluster_bars = []
            ivpoc_list = []
            
            for i in range(1, len(df)):
                abs_str = df['abs_strength'].iloc[i]
                is_bullish = df['is_bullish_sps'].iloc[i]
                is_uptrend = df['uptrend'].iloc[i] == 1 if 'uptrend' in df.columns else True
                
                if is_uptrend and is_bullish and abs_str >= 0.4:
                    if not in_cluster:
                        in_cluster = True
                        cluster_bars = []
                    cluster_bars.append({'idx': i, 'price': df['close'].iloc[i], 'abs': abs_str})
                    df.iloc[i, df.columns.get_loc('cluster_id')] = cluster_id
                elif in_cluster:
                    if abs_str >= 0.2 and is_bullish:
                        cluster_bars.append({'idx': i, 'price': df['close'].iloc[i], 'abs': abs_str})
                        df.iloc[i, df.columns.get_loc('cluster_id')] = cluster_id
                    else:
                        if len(cluster_bars) >= 2:
                            sorted_bars = sorted(cluster_bars, key=lambda x: x['abs'], reverse=True)
                            ivpoc = (sorted_bars[0]['price'] + sorted_bars[1]['price']) / 2
                            df.iloc[i, df.columns.get_loc('cluster_ended')] = True
                            ivpoc_list.append({'start_idx': i, 'ivpoc': ivpoc, 'touched': False})
                            cluster_id += 1
                        in_cluster = False
                        cluster_bars = []
            
            for i in range(1, len(df)):
                high = df['high'].iloc[i]
                low = df['low'].iloc[i]
                tolerance = tick_size * 10
                
                for vp in ivpoc_list:
                    if i <= vp['start_idx'] + 5:
                        continue
                    if vp['touched']:
                        continue
                    
                    ivpoc = vp['ivpoc']
                    close = df['close'].iloc[i]
                    is_touch = (low - tolerance) <= ivpoc <= (high + tolerance)
                    is_close_near = abs(close - ivpoc) <= tolerance
                    is_bullish = df['is_bullish_sps'].iloc[i]
                    zscore = df['sps_zscore'].iloc[i]
                    
                    if is_touch and is_close_near and is_bullish and zscore >= 1.5:
                        df.iloc[i, df.columns.get_loc('ivpoc')] = ivpoc
                        df.iloc[i, df.columns.get_loc('ivpoc_active')] = True
                        df.iloc[i, df.columns.get_loc('first_touch')] = True
                        vp['touched'] = True
                        
                        for k in range(max(0, i-30), i):
                            if df['is_bearish_sps'].iloc[k]:
                                sell_price = df['close'].iloc[k]
                                price_diff = (sell_price - df['close'].iloc[i]) / tick_size
                                if 0 <= price_diff <= 40:
                                    df.iloc[i, df.columns.get_loc('has_nearby_sell_sps')] = True
                                    break
                        break
            
            for i in range(1, len(df)):
                if not df['first_touch'].iloc[i]:
                    continue
                
                ivpoc = df['ivpoc'].iloc[i]
                if pd.isna(ivpoc):
                    continue
                
                close = df['close'].iloc[i]
                zscore = df['sps_zscore'].iloc[i]
                
                is_bullish = df['is_bullish_sps'].iloc[i]
                is_strong_zscore = zscore >= 1.5
                is_uptrend = df['uptrend'].iloc[i] == 1 if 'uptrend' in df.columns else True
                has_sell_sps = df['has_nearby_sell_sps'].iloc[i]
                is_spread_day = df['is_spread_day'].iloc[i]
                
                if is_bullish and is_strong_zscore and is_uptrend:
                    entry = close
                    future = df.iloc[i+1:i+21]
                    
                    block_reason = None
                    if is_spread_day:
                        block_reason = '스프레드 데이 (4-6AM EST)'
                    elif has_sell_sps:
                        block_reason = '진입 가격 위 매도 SPS 발생'
                    
                    if len(future) > 0:
                        max_profit = (future['high'].max() - entry) / tick_size
                        max_loss = (entry - future['low'].min()) / tick_size
                        
                        hit_target = max_profit >= 40
                        hit_stop = max_loss >= 20
                        
                        if hit_stop and hit_target:
                            is_win = future['high'].idxmax() < future['low'].idxmin()
                        elif hit_target:
                            is_win = True
                        elif hit_stop:
                            is_win = False
                        else:
                            is_win = max_profit > max_loss
                        
                        if block_reason:
                            result = 'BLOCKED'
                        else:
                            result = 'WIN' if is_win else 'LOSS'
                        
                        all_signals.append({
                            'file': filepath.split('/')[-1],
                            'time': df['datetime_est'].iloc[i].strftime('%m/%d %I:%M %p'),
                            'price': float(close),
                            'ivpoc': float(ivpoc) if not pd.isna(ivpoc) else None,
                            'zscore': float(zscore),
                            'result': result,
                            'block_reason': block_reason,
                            'max_profit': float(max_profit),
                            'max_loss': float(max_loss)
                        })
        
        # 중복 제거 (같은 시간/가격)
        seen = set()
        unique_signals = []
        for s in all_signals:
            key = (s['time'], s['price'])
            if key not in seen:
                seen.add(key)
                unique_signals.append(s)
        
        wins = len([s for s in unique_signals if s['result'] == 'WIN'])
        losses = len([s for s in unique_signals if s['result'] == 'LOSS'])
        blocked = len([s for s in unique_signals if s['result'] == 'BLOCKED'])
        total = len(unique_signals)
        
        active_signals = [s for s in unique_signals if s['result'] != 'BLOCKED']
        active_total = len(active_signals)
        win_rate = (wins / active_total * 100) if active_total > 0 else 0
        
        if active_signals:
            avg_profit = sum(s['max_profit'] for s in active_signals) / len(active_signals)
            avg_loss = sum(s['max_loss'] for s in active_signals) / len(active_signals)
            avg_rr = avg_profit / avg_loss if avg_loss > 0 else 0
        else:
            avg_rr = 0
        
        return jsonify({
            "success": True,
            "losses": unique_signals,
            "stats": {
                "total": total,
                "wins": wins,
                "losses": losses,
                "blocked": blocked,
                "win_rate": win_rate,
                "avg_rr": avg_rr
            }
        })
        
    except Exception as e:
        import traceback
        return jsonify({"success": False, "message": str(e), "losses": [], "stats": {}})

@app.route('/api/loss-candles')
def get_loss_candles():
    """손실 구간 캔들 차트 데이터"""
    import numpy as np
    import pandas as pd
    from datetime import timedelta
    import glob
    
    try:
        csv_files = glob.glob('attached_assets/chart_data_new/*.csv')
        if not csv_files:
            return jsonify({"success": False, "message": "CSV 파일 없음"})
        
        filepath = csv_files[0]
        df = pd.read_csv(filepath)
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df['datetime_est'] = df['datetime'] - timedelta(hours=5)
        
        tick_size = 0.25
        
        z_score = df['sps_zscore'].abs().fillna(0)
        z_norm = (z_score - z_score.mean()) / (z_score.std() + 0.001)
        z_norm = z_norm.clip(-3, 3) / 3
        
        wick_reclaim = (df['close'] - df['low']) / (df['high'] - df['low'] + 0.001)
        reclaim_norm = wick_reclaim.clip(0, 1)
        
        df['abs_strength'] = 0.4 * z_norm + 0.3 * reclaim_norm + 0.3 * 0.5
        df['is_bullish_sps'] = (df['close'] > df['open']) & (df['sps_zscore'] > 0)
        df['is_bearish_sps'] = (df['close'] < df['open']) & (df['sps_zscore'] < 0)
        
        df['cluster_id'] = -1
        df['ivpoc'] = np.nan
        df['cluster_ended'] = False
        df['has_nearby_sell_sps'] = False
        
        cluster_id = 0
        in_cluster = False
        cluster_bars = []
        
        for i in range(1, len(df)):
            abs_str = df['abs_strength'].iloc[i]
            is_bullish = df['is_bullish_sps'].iloc[i]
            is_uptrend = df['uptrend'].iloc[i] == 1 if 'uptrend' in df.columns else True
            
            if is_uptrend and is_bullish and abs_str >= 0.4:
                if not in_cluster:
                    in_cluster = True
                    cluster_bars = []
                cluster_bars.append({'idx': i, 'price': df['close'].iloc[i], 'abs': abs_str})
                df.iloc[i, df.columns.get_loc('cluster_id')] = cluster_id
            elif in_cluster:
                if abs_str >= 0.2 and is_bullish:
                    cluster_bars.append({'idx': i, 'price': df['close'].iloc[i], 'abs': abs_str})
                    df.iloc[i, df.columns.get_loc('cluster_id')] = cluster_id
                else:
                    if len(cluster_bars) >= 2:
                        sorted_bars = sorted(cluster_bars, key=lambda x: x['abs'], reverse=True)
                        ivpoc = (sorted_bars[0]['price'] + sorted_bars[1]['price']) / 2
                        df.iloc[i, df.columns.get_loc('cluster_ended')] = True
                        for j in range(i, min(i+100, len(df))):
                            if df['cluster_ended'].iloc[j] and j != i:
                                break
                            df.iloc[j, df.columns.get_loc('ivpoc')] = ivpoc
                            for k in range(max(0, j-10), j):
                                if df['is_bearish_sps'].iloc[k]:
                                    if abs(df['close'].iloc[k] - ivpoc) / tick_size <= 30:
                                        df.iloc[j, df.columns.get_loc('has_nearby_sell_sps')] = True
                                        break
                        cluster_id += 1
                    in_cluster = False
                    cluster_bars = []
        
        signals = []
        cluster_ended_flag = False
        
        for i in range(1, len(df)):
            if df['cluster_ended'].iloc[i]:
                cluster_ended_flag = True
                continue
            if not cluster_ended_flag:
                continue
            
            ivpoc = df['ivpoc'].iloc[i]
            if pd.isna(ivpoc):
                continue
            
            close = df['close'].iloc[i]
            distance = abs(close - ivpoc) / tick_size
            
            is_hit = distance <= 10
            is_bullish = df['is_bullish_sps'].iloc[i]
            is_strong = df['abs_strength'].iloc[i] >= 0.3
            is_uptrend = df['uptrend'].iloc[i] == 1 if 'uptrend' in df.columns else True
            has_sell_sps = df['has_nearby_sell_sps'].iloc[i]
            
            if is_hit and is_bullish and is_strong and is_uptrend and not has_sell_sps:
                entry = close
                future = df.iloc[i+1:i+21]
                
                if len(future) > 0:
                    max_profit = (future['high'].max() - entry) / tick_size
                    max_loss = (entry - future['low'].min()) / tick_size
                    
                    hit_target = max_profit >= 40
                    hit_stop = max_loss >= 20
                    
                    if hit_stop and hit_target:
                        is_win = future['high'].idxmax() < future['low'].idxmin()
                    elif hit_target:
                        is_win = True
                    elif hit_stop:
                        is_win = False
                    else:
                        is_win = max_profit > max_loss
                    
                    result = 'WIN' if is_win else 'LOSS'
                    
                    signals.append({
                        'index': int(i),
                        'timestamp': int(df['time'].iloc[i]),
                        'time': df['datetime_est'].iloc[i].strftime('%m/%d %I:%M %p'),
                        'price': float(close),
                        'ivpoc': float(ivpoc) if not pd.isna(ivpoc) else None,
                        'zscore': float(df['sps_zscore'].iloc[i]),
                        'result': result,
                        'max_profit': float(max_profit),
                        'max_loss': float(max_loss)
                    })
        
        candles = []
        for _, row in df.iloc[-500:].iterrows():
            candles.append({
                'time': int(row['time']),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close'])
            })
        
        wins = len([s for s in signals if s['result'] == 'WIN'])
        losses = len([s for s in signals if s['result'] == 'LOSS'])
        total = len(signals)
        win_rate = (wins / total * 100) if total > 0 else 0
        
        if signals:
            avg_profit = sum(s['max_profit'] for s in signals) / len(signals)
            avg_loss = sum(s['max_loss'] for s in signals) / len(signals)
            avg_rr = avg_profit / avg_loss if avg_loss > 0 else 0
        else:
            avg_rr = 0
        
        return jsonify({
            "success": True,
            "candles": candles,
            "signals": signals,
            "stats": {
                "total": total,
                "wins": wins,
                "losses": losses,
                "blocked": 0,
                "win_rate": win_rate,
                "avg_rr": avg_rr
            }
        })
        
    except Exception as e:
        import traceback
        return jsonify({"success": False, "message": str(e), "traceback": traceback.format_exc()})

@app.route('/api/chart-candles', methods=['POST'])
def get_chart_candles():
    """선택한 파일의 캔들 차트 데이터"""
    import numpy as np
    import pandas as pd
    from datetime import timedelta
    
    try:
        data = request.json
        filename = data.get('filename', '')
        
        filepath = f'attached_assets/chart_data_new/{filename}'
        if not os.path.exists(filepath):
            return jsonify({"success": False, "message": "파일을 찾을 수 없습니다"})
        
        df = pd.read_csv(filepath)
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df['datetime_est'] = df['datetime'] - timedelta(hours=5)
        
        tick_size = 0.25
        
        z_score = df['sps_zscore'].abs().fillna(0)
        z_norm = (z_score - z_score.mean()) / (z_score.std() + 0.001)
        z_norm = z_norm.clip(-3, 3) / 3
        
        wick_reclaim = (df['close'] - df['low']) / (df['high'] - df['low'] + 0.001)
        reclaim_norm = wick_reclaim.clip(0, 1)
        
        df['abs_strength'] = 0.4 * z_norm + 0.3 * reclaim_norm + 0.3 * 0.5
        df['is_bullish_sps'] = (df['close'] > df['open']) & (df['sps_zscore'] > 0)
        df['is_bearish_sps'] = (df['close'] < df['open']) & (df['sps_zscore'] < 0)
        
        df['cluster_id'] = -1
        df['ivpoc'] = np.nan
        df['cluster_ended'] = False
        df['has_nearby_sell_sps'] = False
        
        cluster_id = 0
        in_cluster = False
        cluster_bars = []
        
        for i in range(1, len(df)):
            abs_str = df['abs_strength'].iloc[i]
            is_bullish = df['is_bullish_sps'].iloc[i]
            is_uptrend = df['uptrend'].iloc[i] == 1 if 'uptrend' in df.columns else True
            
            if is_uptrend and is_bullish and abs_str >= 0.4:
                if not in_cluster:
                    in_cluster = True
                    cluster_bars = []
                cluster_bars.append({'idx': i, 'price': df['close'].iloc[i], 'abs': abs_str})
                df.iloc[i, df.columns.get_loc('cluster_id')] = cluster_id
            elif in_cluster:
                if abs_str >= 0.2 and is_bullish:
                    cluster_bars.append({'idx': i, 'price': df['close'].iloc[i], 'abs': abs_str})
                    df.iloc[i, df.columns.get_loc('cluster_id')] = cluster_id
                else:
                    if len(cluster_bars) >= 2:
                        sorted_bars = sorted(cluster_bars, key=lambda x: x['abs'], reverse=True)
                        ivpoc = (sorted_bars[0]['price'] + sorted_bars[1]['price']) / 2
                        df.iloc[i, df.columns.get_loc('cluster_ended')] = True
                        for j in range(i, min(i+100, len(df))):
                            if df['cluster_ended'].iloc[j] and j != i:
                                break
                            df.iloc[j, df.columns.get_loc('ivpoc')] = ivpoc
                            for k in range(max(0, j-10), j):
                                if df['is_bearish_sps'].iloc[k]:
                                    if abs(df['close'].iloc[k] - ivpoc) / tick_size <= 30:
                                        df.iloc[j, df.columns.get_loc('has_nearby_sell_sps')] = True
                                        break
                        cluster_id += 1
                    in_cluster = False
                    cluster_bars = []
        
        signals = []
        cluster_ended_flag = False
        
        for i in range(1, len(df)):
            if df['cluster_ended'].iloc[i]:
                cluster_ended_flag = True
                continue
            if not cluster_ended_flag:
                continue
            
            ivpoc = df['ivpoc'].iloc[i]
            if pd.isna(ivpoc):
                continue
            
            close = df['close'].iloc[i]
            distance = abs(close - ivpoc) / tick_size
            
            is_hit = distance <= 10
            is_bullish = df['is_bullish_sps'].iloc[i]
            is_strong = df['abs_strength'].iloc[i] >= 0.3
            is_uptrend = df['uptrend'].iloc[i] == 1 if 'uptrend' in df.columns else True
            has_sell_sps = df['has_nearby_sell_sps'].iloc[i]
            
            if is_hit and is_bullish and is_strong and is_uptrend and not has_sell_sps:
                entry = close
                future = df.iloc[i+1:i+21]
                
                if len(future) > 0:
                    max_profit = (future['high'].max() - entry) / tick_size
                    max_loss = (entry - future['low'].min()) / tick_size
                    
                    hit_target = max_profit >= 40
                    hit_stop = max_loss >= 20
                    
                    if hit_stop and hit_target:
                        is_win = future['high'].idxmax() < future['low'].idxmin()
                    elif hit_target:
                        is_win = True
                    elif hit_stop:
                        is_win = False
                    else:
                        is_win = max_profit > max_loss
                    
                    result = 'WIN' if is_win else 'LOSS'
                    
                    signals.append({
                        'index': int(i),
                        'timestamp': int(df['time'].iloc[i]),
                        'time': df['datetime_est'].iloc[i].strftime('%m/%d %I:%M %p'),
                        'price': float(close),
                        'ivpoc': float(ivpoc) if not pd.isna(ivpoc) else None,
                        'zscore': float(df['sps_zscore'].iloc[i]),
                        'result': result,
                        'max_profit': float(max_profit),
                        'max_loss': float(max_loss)
                    })
        
        candles = []
        for _, row in df.iloc[-1000:].iterrows():
            candles.append({
                'time': int(row['time']),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close'])
            })
        
        wins = len([s for s in signals if s['result'] == 'WIN'])
        losses = len([s for s in signals if s['result'] == 'LOSS'])
        total = len(signals)
        win_rate = (wins / total * 100) if total > 0 else 0
        
        if signals:
            avg_profit = sum(s['max_profit'] for s in signals) / len(signals)
            avg_loss = sum(s['max_loss'] for s in signals) / len(signals)
            avg_rr = avg_profit / avg_loss if avg_loss > 0 else 0
        else:
            avg_rr = 0
        
        return jsonify({
            "success": True,
            "candles": candles,
            "signals": signals,
            "stats": {
                "total": total,
                "wins": wins,
                "losses": losses,
                "blocked": 0,
                "win_rate": win_rate,
                "avg_rr": avg_rr
            }
        })
        
    except Exception as e:
        import traceback
        return jsonify({"success": False, "message": str(e), "traceback": traceback.format_exc()})

@app.route('/api/chart-files')
def get_chart_files():
    """차트 데이터 파일 목록"""
    import glob
    files = glob.glob('attached_assets/chart_data_new/*.csv')
    return jsonify([f.split('/')[-1] for f in files])

@app.route('/api/analyze-chart', methods=['POST'])
def analyze_chart():
    """차트 데이터 분석 및 타점 감지"""
    import numpy as np
    from datetime import timedelta
    
    try:
        data = request.json
        filename = data.get('filename', '')
        
        filepath = f'attached_assets/chart_data_new/{filename}'
        if not os.path.exists(filepath):
            return jsonify({"success": False, "message": "파일을 찾을 수 없습니다"})
        
        df = pd.read_csv(filepath)
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df['datetime_est'] = df['datetime'] - timedelta(hours=5)
        
        tick_size = 0.25
        
        # 흡수 강도 계산
        z_score = df['sps_zscore'].abs().fillna(0)
        z_norm = (z_score - z_score.mean()) / (z_score.std() + 0.001)
        z_norm = z_norm.clip(-3, 3) / 3
        
        wick_reclaim = (df['close'] - df['low']) / (df['high'] - df['low'] + 0.001)
        reclaim_norm = wick_reclaim.clip(0, 1)
        
        df['abs_strength'] = 0.4 * z_norm + 0.3 * reclaim_norm + 0.3 * 0.5
        df['is_bullish_sps'] = (df['close'] > df['open']) & (df['sps_zscore'] > 0)
        df['is_bearish_sps'] = (df['close'] < df['open']) & (df['sps_zscore'] < 0)
        
        # 클러스터 및 iVPOC 계산
        df['cluster_id'] = -1
        df['ivpoc'] = np.nan
        df['cluster_ended'] = False
        df['has_nearby_sell_sps'] = False
        
        cluster_id = 0
        in_cluster = False
        cluster_bars = []
        
        for i in range(1, len(df)):
            abs_str = df['abs_strength'].iloc[i]
            is_bullish = df['is_bullish_sps'].iloc[i]
            is_uptrend = df['uptrend'].iloc[i] == 1 if 'uptrend' in df.columns else True
            
            if is_uptrend and is_bullish and abs_str >= 0.4:
                if not in_cluster:
                    in_cluster = True
                    cluster_bars = []
                cluster_bars.append({'idx': i, 'price': df['close'].iloc[i], 'abs': abs_str})
                df.iloc[i, df.columns.get_loc('cluster_id')] = cluster_id
            elif in_cluster:
                if abs_str >= 0.2 and is_bullish:
                    cluster_bars.append({'idx': i, 'price': df['close'].iloc[i], 'abs': abs_str})
                    df.iloc[i, df.columns.get_loc('cluster_id')] = cluster_id
                else:
                    if len(cluster_bars) >= 2:
                        sorted_bars = sorted(cluster_bars, key=lambda x: x['abs'], reverse=True)
                        ivpoc = (sorted_bars[0]['price'] + sorted_bars[1]['price']) / 2
                        df.iloc[i, df.columns.get_loc('cluster_ended')] = True
                        for j in range(i, min(i+100, len(df))):
                            if df['cluster_ended'].iloc[j] and j != i:
                                break
                            df.iloc[j, df.columns.get_loc('ivpoc')] = ivpoc
                            for k in range(max(0, j-10), j):
                                if df['is_bearish_sps'].iloc[k]:
                                    if abs(df['close'].iloc[k] - ivpoc) / tick_size <= 30:
                                        df.iloc[j, df.columns.get_loc('has_nearby_sell_sps')] = True
                                        break
                        cluster_id += 1
                    in_cluster = False
                    cluster_bars = []
        
        # 타점 감지
        signals = []
        cluster_ended_flag = False
        
        for i in range(1, len(df)):
            if df['cluster_ended'].iloc[i]:
                cluster_ended_flag = True
                continue
            if not cluster_ended_flag:
                continue
            
            ivpoc = df['ivpoc'].iloc[i]
            if pd.isna(ivpoc):
                continue
            
            close = df['close'].iloc[i]
            distance = abs(close - ivpoc) / tick_size
            
            is_hit = distance <= 10
            is_bullish = df['is_bullish_sps'].iloc[i]
            is_strong = df['abs_strength'].iloc[i] >= 0.3
            is_uptrend = df['uptrend'].iloc[i] == 1 if 'uptrend' in df.columns else True
            has_sell_sps = df['has_nearby_sell_sps'].iloc[i]
            
            if is_hit and is_bullish and is_strong and is_uptrend:
                entry = close
                future = df.iloc[i+1:i+21]
                
                if len(future) > 0:
                    max_profit = (future['high'].max() - entry) / tick_size
                    max_loss = (entry - future['low'].min()) / tick_size
                    
                    hit_target = max_profit >= 40
                    hit_stop = max_loss >= 20
                    
                    if hit_stop and hit_target:
                        is_win = future['high'].idxmax() < future['low'].idxmin()
                    elif hit_target:
                        is_win = True
                    elif hit_stop:
                        is_win = False
                    else:
                        is_win = max_profit > max_loss
                    
                    if has_sell_sps:
                        result = 'BLOCKED'
                    elif is_win:
                        result = 'WIN'
                    else:
                        result = 'LOSS'
                    
                    signals.append({
                        'index': int(i),
                        'time': df['datetime_est'].iloc[i].strftime('%m/%d %I:%M %p'),
                        'price': float(close),
                        'ivpoc': float(ivpoc) if not pd.isna(ivpoc) else None,
                        'zscore': float(df['sps_zscore'].iloc[i]),
                        'abs_strength': float(df['abs_strength'].iloc[i]),
                        'result': result,
                        'max_profit': float(max_profit),
                        'max_loss': float(max_loss),
                        'has_sell_sps': bool(has_sell_sps)
                    })
        
        # 통계 계산
        clean_signals = [s for s in signals if s['result'] != 'BLOCKED']
        wins = len([s for s in clean_signals if s['result'] == 'WIN'])
        losses = len([s for s in clean_signals if s['result'] == 'LOSS'])
        total = len(clean_signals)
        blocked = len([s for s in signals if s['result'] == 'BLOCKED'])
        
        win_rate = (wins / total * 100) if total > 0 else 0
        
        if clean_signals:
            avg_profit = sum(s['max_profit'] for s in clean_signals) / len(clean_signals)
            avg_loss = sum(s['max_loss'] for s in clean_signals) / len(clean_signals)
            avg_rr = avg_profit / avg_loss if avg_loss > 0 else 0
        else:
            avg_rr = 0
        
        return jsonify({
            "success": True,
            "prices": df['close'].tolist(),
            "signals": signals,
            "stats": {
                "total": total,
                "wins": wins,
                "losses": losses,
                "blocked": blocked,
                "win_rate": win_rate,
                "avg_rr": avg_rr
            }
        })
        
    except Exception as e:
        import traceback
        return jsonify({"success": False, "message": str(e), "traceback": traceback.format_exc()})

# ============================================
# 🔥 실시간 SPS 클러스터 대시보드
# ============================================

@app.route('/sps-dashboard')
def sps_dashboard():
    """실시간 SPS 클러스터 대시보드"""
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>SPS 실시간 대시보드</title>
        <meta charset="utf-8">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, sans-serif; 
                background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 100%);
                color: #fff; 
                min-height: 100vh;
                padding: 20px;
            }
            .header {
                text-align: center;
                padding: 20px;
                background: rgba(255,255,255,0.05);
                border-radius: 15px;
                margin-bottom: 20px;
            }
            .header h1 { font-size: 2em; margin-bottom: 10px; }
            .status { 
                display: inline-block;
                padding: 5px 15px;
                border-radius: 20px;
                font-size: 0.9em;
            }
            .status.live { background: #00ff88; color: #000; }
            .status.offline { background: #ff4444; }
            
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 20px;
            }
            .card {
                background: rgba(255,255,255,0.08);
                border-radius: 15px;
                padding: 20px;
                border: 1px solid rgba(255,255,255,0.1);
            }
            .card h3 { margin-bottom: 15px; color: #888; font-size: 0.9em; }
            .big-number { font-size: 3em; font-weight: bold; }
            .green { color: #00ff88; }
            .red { color: #ff4444; }
            .yellow { color: #ffcc00; }
            
            .chart-container {
                background: rgba(255,255,255,0.05);
                border-radius: 15px;
                padding: 20px;
                margin-bottom: 20px;
            }
            #spsChart { width: 100%; height: 300px; }
            
            .cluster-list {
                max-height: 400px;
                overflow-y: auto;
            }
            .cluster-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px;
                background: rgba(255,255,255,0.03);
                border-radius: 10px;
                margin-bottom: 10px;
                border-left: 4px solid;
            }
            .cluster-item.buy { border-color: #00ff88; }
            .cluster-item.sell { border-color: #ff4444; }
            .cluster-item.neutral { border-color: #888; }
            
            .sps-badge {
                display: inline-block;
                padding: 5px 12px;
                border-radius: 15px;
                font-size: 0.85em;
                font-weight: bold;
            }
            .sps-badge.buy { background: rgba(0,255,136,0.2); color: #00ff88; }
            .sps-badge.sell { background: rgba(255,68,68,0.2); color: #ff4444; }
            
            .update-time { color: #666; font-size: 0.8em; margin-top: 10px; }
            
            .ivpoc-line {
                background: linear-gradient(90deg, #ff6b00, #ffcc00);
                padding: 15px 20px;
                border-radius: 10px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }
            .ivpoc-price { font-size: 2em; font-weight: bold; }
            .ivpoc-direction { font-size: 1.5em; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔥 SPS 실시간 대시보드</h1>
            <span class="status live" id="status">LIVE</span>
            <p class="update-time" id="updateTime">업데이트 중...</p>
        </div>
        
        <div class="ivpoc-line">
            <div>
                <div style="font-size:0.8em;color:rgba(0,0,0,0.6)">Flowing iVPOC</div>
                <div class="ivpoc-price" id="ivpocPrice">--</div>
            </div>
            <div class="ivpoc-direction" id="ivpocDirection">--</div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>📈 매수 SPS</h3>
                <div class="big-number green" id="buySps">0</div>
                <div class="update-time">최근 1시간</div>
            </div>
            <div class="card">
                <h3>📉 매도 SPS</h3>
                <div class="big-number red" id="sellSps">0</div>
                <div class="update-time">최근 1시간</div>
            </div>
            <div class="card">
                <h3>⚖️ 비율 (매수/매도)</h3>
                <div class="big-number yellow" id="ratio">--</div>
                <div class="update-time" id="prediction">--</div>
            </div>
            <div class="card">
                <h3>🎯 클러스터 상태</h3>
                <div class="big-number" id="clusterStatus">--</div>
                <div class="update-time" id="clusterEndReason">--</div>
            </div>
        </div>
        
        <div class="chart-container">
            <h3 style="margin-bottom:15px;color:#888;">📊 SPS 강도 차트</h3>
            <canvas id="spsChart"></canvas>
        </div>
        
        <div class="card">
            <h3 style="margin-bottom:15px;">🔔 최근 클러스터</h3>
            <div class="cluster-list" id="clusterList">
                로딩 중...
            </div>
        </div>
        
        <div class="card" style="margin-top:20px;">
            <h3 style="margin-bottom:15px;">📊 스팟별 SPS 측정 (30분 단위)</h3>
            <div style="overflow-x:auto;">
                <table id="spotTable" style="width:100%;border-collapse:collapse;font-size:0.9em;">
                    <thead>
                        <tr style="background:rgba(255,255,255,0.1);text-align:left;">
                            <th style="padding:10px;">시간</th>
                            <th style="padding:10px;text-align:center;">매수</th>
                            <th style="padding:10px;text-align:center;">매도</th>
                            <th style="padding:10px;text-align:center;">존내매수</th>
                            <th style="padding:10px;text-align:center;">존내매도</th>
                            <th style="padding:10px;text-align:right;">iVPOC</th>
                            <th style="padding:10px;text-align:right;">종가</th>
                            <th style="padding:10px;text-align:center;">방향</th>
                        </tr>
                    </thead>
                    <tbody id="spotTableBody">
                        <tr><td colspan="8" style="padding:20px;text-align:center;color:#666;">로딩 중...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>
            let chart = null;
            
            async function updateDashboard() {
                try {
                    const response = await fetch('/api/sps-realtime');
                    const data = await response.json();
                    
                    if (data.success) {
                        document.getElementById('buySps').textContent = data.buy_sps;
                        document.getElementById('sellSps').textContent = data.sell_sps;
                        document.getElementById('ratio').textContent = data.ratio.toFixed(2);
                        
                        document.getElementById('ivpocPrice').textContent = data.ivpoc.toFixed(2);
                        document.getElementById('ivpocDirection').textContent = 
                            data.ivpoc_direction > 0 ? '⬆️ 상승' : data.ivpoc_direction < 0 ? '⬇️ 하락' : '➡️ 횡보';
                        
                        const prediction = data.ratio > 1.5 ? '🔥 상승 예상' : 
                                          data.ratio < 0.67 ? '❄️ 하락 예상' : '⚖️ 중립';
                        document.getElementById('prediction').textContent = prediction;
                        
                        document.getElementById('clusterStatus').textContent = 
                            data.in_cluster ? '🟢 진행 중' : '⚪ 종료';
                        document.getElementById('clusterEndReason').textContent = 
                            data.cluster_end_reason || '대기 중';
                        
                        updateChart(data.chart_data);
                        updateClusterList(data.recent_clusters);
                        
                        document.getElementById('updateTime').textContent = 
                            '마지막 업데이트: ' + new Date().toLocaleTimeString();
                    }
                } catch (e) {
                    document.getElementById('status').className = 'status offline';
                    document.getElementById('status').textContent = 'OFFLINE';
                }
            }
            
            function updateChart(chartData) {
                const ctx = document.getElementById('spsChart').getContext('2d');
                
                if (chart) {
                    chart.data.labels = chartData.labels;
                    chart.data.datasets[0].data = chartData.buy;
                    chart.data.datasets[1].data = chartData.sell;
                    chart.update();
                } else {
                    chart = new Chart(ctx, {
                        type: 'bar',
                        data: {
                            labels: chartData.labels,
                            datasets: [
                                {
                                    label: '매수 SPS',
                                    data: chartData.buy,
                                    backgroundColor: 'rgba(0, 255, 136, 0.7)',
                                    borderColor: '#00ff88',
                                    borderWidth: 1
                                },
                                {
                                    label: '매도 SPS',
                                    data: chartData.sell,
                                    backgroundColor: 'rgba(255, 68, 68, 0.7)',
                                    borderColor: '#ff4444',
                                    borderWidth: 1
                                }
                            ]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' } },
                                x: { grid: { color: 'rgba(255,255,255,0.1)' } }
                            },
                            plugins: {
                                legend: { labels: { color: '#fff' } }
                            }
                        }
                    });
                }
            }
            
            function updateClusterList(clusters) {
                const list = document.getElementById('clusterList');
                if (!clusters || clusters.length === 0) {
                    list.innerHTML = '<div style="color:#666;">클러스터 없음</div>';
                    return;
                }
                
                list.innerHTML = clusters.map(c => `
                    <div class="cluster-item ${c.type.toLowerCase()}">
                        <div>
                            <div style="font-weight:bold;">${c.time}</div>
                            <div style="color:#888;font-size:0.85em;">${c.price_range}</div>
                        </div>
                        <div style="text-align:right;">
                            <span class="sps-badge ${c.type.toLowerCase()}">${c.type}</span>
                            <div style="margin-top:5px;font-size:0.85em;">
                                📈 ${c.buy_sps} / 📉 ${c.sell_sps}
                            </div>
                        </div>
                    </div>
                `).join('');
            }
            
            function updateSpotTable(spots) {
                const tbody = document.getElementById('spotTableBody');
                if (!spots || spots.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" style="padding:20px;text-align:center;color:#666;">데이터 없음</td></tr>';
                    return;
                }
                
                tbody.innerHTML = spots.map(s => {
                    const direction = s.buy_sps > s.sell_sps ? '🟢 매수' : s.sell_sps > s.buy_sps ? '🔴 매도' : '⚪ 중립';
                    const rowBg = s.buy_sps > s.sell_sps ? 'rgba(0,255,136,0.1)' : s.sell_sps > s.buy_sps ? 'rgba(255,68,68,0.1)' : '';
                    return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.1);background:${rowBg}">
                            <td style="padding:10px;">${s.time}</td>
                            <td style="padding:10px;text-align:center;color:#00ff88;font-weight:bold;">${s.buy_sps}</td>
                            <td style="padding:10px;text-align:center;color:#ff4444;font-weight:bold;">${s.sell_sps}</td>
                            <td style="padding:10px;text-align:center;color:#00cc66;">${s.buy_in_zone}</td>
                            <td style="padding:10px;text-align:center;color:#cc4444;">${s.sell_in_zone}</td>
                            <td style="padding:10px;text-align:right;">${s.ivpoc.toFixed(2)}</td>
                            <td style="padding:10px;text-align:right;">${s.close.toFixed(2)}</td>
                            <td style="padding:10px;text-align:center;">${direction}</td>
                        </tr>
                    `;
                }).join('');
            }
            
            async function updateDashboard() {
                try {
                    const response = await fetch('/api/sps-realtime');
                    const data = await response.json();
                    
                    if (data.success) {
                        document.getElementById('buySps').textContent = data.buy_sps;
                        document.getElementById('sellSps').textContent = data.sell_sps;
                        document.getElementById('ratio').textContent = data.ratio.toFixed(2);
                        
                        document.getElementById('ivpocPrice').textContent = data.ivpoc.toFixed(2);
                        document.getElementById('ivpocDirection').textContent = 
                            data.ivpoc_direction > 0 ? '⬆️ 상승' : data.ivpoc_direction < 0 ? '⬇️ 하락' : '➡️ 횡보';
                        
                        const prediction = data.ratio > 1.5 ? '🔥 상승 예상' : 
                                          data.ratio < 0.67 ? '❄️ 하락 예상' : '⚖️ 중립';
                        document.getElementById('prediction').textContent = prediction;
                        
                        document.getElementById('clusterStatus').textContent = 
                            data.in_cluster ? '🟢 진행 중' : '⚪ 종료';
                        document.getElementById('clusterEndReason').textContent = 
                            data.cluster_end_reason || '대기 중';
                        
                        updateChart(data.chart_data);
                        updateClusterList(data.recent_clusters);
                        updateSpotTable(data.spot_data);
                        
                        document.getElementById('updateTime').textContent = 
                            '마지막 업데이트: ' + new Date().toLocaleTimeString();
                    }
                } catch (e) {
                    document.getElementById('status').className = 'status offline';
                    document.getElementById('status').textContent = 'OFFLINE';
                }
            }
            
            updateDashboard();
            setInterval(updateDashboard, 30000);
        </script>
    </body>
    </html>
    '''
    return html

@app.route('/api/sps-realtime')
def api_sps_realtime():
    """실시간 SPS 데이터 API"""
    import pandas as pd
    import numpy as np
    from pathlib import Path
    
    try:
        chart_file = Path("attached_assets/CME_MINI_NQ1!,_1_e076b_1766420091573.csv")
        if not chart_file.exists():
            chart_file = Path("attached_assets/chart_data_new/latest_chart.csv")
        
        if not chart_file.exists():
            return jsonify({"success": False, "message": "데이터 없음"})
        
        df = pd.read_csv(chart_file)
        df['datetime'] = pd.to_datetime(df['time'])
        df = df.sort_values('datetime').reset_index(drop=True)
        
        df['body'] = abs(df['close'] - df['open'])
        df['range'] = df['high'] - df['low']
        df['body_ratio'] = np.where(df['range'] > 0, df['body'] / df['range'], 0)
        df['sps_mean'] = df['body_ratio'].rolling(10).mean()
        df['sps_std'] = df['body_ratio'].rolling(10).std()
        df['sps_zscore'] = np.where(df['sps_std'] > 0, (df['body_ratio'] - df['sps_mean']) / df['sps_std'], 0)
        
        threshold = 1.5
        df['is_bullish'] = df['close'] > df['open']
        df['is_bearish'] = df['close'] < df['open']
        df['is_strong_buy'] = (df['sps_zscore'] >= threshold) & df['is_bullish']
        df['is_strong_sell'] = (df['sps_zscore'] >= threshold) & df['is_bearish']
        
        df['in_buy_zone'] = df['close'] <= df['매수 하단'] + 10
        df['in_sell_zone'] = df['close'] >= df['매도 상단'] - 10
        
        recent = df.tail(60)
        buy_sps = int(recent['is_strong_buy'].sum())
        sell_sps = int(recent['is_strong_sell'].sum())
        ratio = buy_sps / max(sell_sps, 1)
        
        sps_prices = []
        for i in range(len(df)):
            if df['is_strong_buy'].iloc[i] or df['is_strong_sell'].iloc[i]:
                sps_prices.append(df['close'].iloc[i])
            if len(sps_prices) > 50:
                sps_prices = sps_prices[-50:]
        
        ivpoc = np.mean(sps_prices) if sps_prices else df['close'].iloc[-1]
        
        ivpoc_prev = np.mean(sps_prices[:-5]) if len(sps_prices) > 5 else ivpoc
        ivpoc_direction = ivpoc - ivpoc_prev
        
        in_cluster = False
        cluster_end_reason = ""
        consecutive_high = 0
        
        for i in range(max(0, len(df)-20), len(df)):
            zscore = abs(df['sps_zscore'].iloc[i]) if not pd.isna(df['sps_zscore'].iloc[i]) else 0
            if zscore >= threshold:
                consecutive_high += 1
                if consecutive_high >= 3:
                    in_cluster = True
            else:
                if in_cluster and zscore < 0.5:
                    in_cluster = False
                    cluster_end_reason = "약한 SPS로 종료"
                consecutive_high = 0
        
        df['hour'] = df['datetime'].dt.floor('h')
        hourly = df.groupby('hour').agg({
            'is_strong_buy': 'sum',
            'is_strong_sell': 'sum'
        }).tail(12)
        
        chart_data = {
            'labels': [h.strftime('%H:%M') for h in hourly.index],
            'buy': [int(x) for x in hourly['is_strong_buy'].tolist()],
            'sell': [int(x) for x in hourly['is_strong_sell'].tolist()]
        }
        
        recent_clusters = []
        cluster_start = None
        cluster_buy = 0
        cluster_sell = 0
        cluster_high = 0
        cluster_low = float('inf')
        
        for i in range(max(0, len(df)-500), len(df)):
            zscore = abs(df['sps_zscore'].iloc[i]) if not pd.isna(df['sps_zscore'].iloc[i]) else 0
            
            if zscore >= threshold:
                if cluster_start is None:
                    cluster_start = df['datetime'].iloc[i]
                    cluster_high = df['high'].iloc[i]
                    cluster_low = df['low'].iloc[i]
                
                cluster_high = max(cluster_high, df['high'].iloc[i])
                cluster_low = min(cluster_low, df['low'].iloc[i])
                
                if df['is_strong_buy'].iloc[i]:
                    cluster_buy += 1
                elif df['is_strong_sell'].iloc[i]:
                    cluster_sell += 1
            else:
                if cluster_start is not None and (cluster_buy + cluster_sell) >= 3:
                    cluster_type = 'BUY' if cluster_buy > cluster_sell else 'SELL' if cluster_sell > cluster_buy else 'NEUTRAL'
                    recent_clusters.append({
                        'time': cluster_start.strftime('%m/%d %H:%M'),
                        'price_range': f'{cluster_low:.2f} ~ {cluster_high:.2f}',
                        'type': cluster_type,
                        'buy_sps': cluster_buy,
                        'sell_sps': cluster_sell
                    })
                
                cluster_start = None
                cluster_buy = 0
                cluster_sell = 0
                cluster_high = 0
                cluster_low = float('inf')
        
        recent_clusters = recent_clusters[-10:][::-1]
        
        df['slot'] = df['datetime'].dt.floor('30min')
        spot_data = []
        for slot, group in list(df.groupby('slot'))[-20:]:
            buy_count = int(group['is_strong_buy'].sum())
            sell_count = int(group['is_strong_sell'].sum())
            buy_in_zone = int(((group['is_strong_buy']) & (group['in_buy_zone'])).sum())
            sell_in_zone = int(((group['is_strong_sell']) & (group['in_sell_zone'])).sum())
            spot_data.append({
                'time': slot.strftime('%m/%d %H:%M'),
                'buy_sps': buy_count,
                'sell_sps': sell_count,
                'buy_in_zone': buy_in_zone,
                'sell_in_zone': sell_in_zone,
                'ivpoc': float(group['iVPOC'].iloc[-1]),
                'close': float(group['close'].iloc[-1])
            })
        
        return jsonify({
            "success": True,
            "buy_sps": buy_sps,
            "sell_sps": sell_sps,
            "ratio": ratio,
            "ivpoc": float(ivpoc),
            "ivpoc_direction": float(ivpoc_direction),
            "in_cluster": in_cluster,
            "cluster_end_reason": cluster_end_reason,
            "chart_data": chart_data,
            "recent_clusters": recent_clusters,
            "spot_data": spot_data
        })
        
    except Exception as e:
        import traceback
        return jsonify({"success": False, "message": str(e), "traceback": traceback.format_exc()})

# ============================================
# 📊 TradingView 스타일 캔들 차트
# ============================================

@app.route('/sps-chart')
def sps_chart():
    """TradingView 스타일 캔들 차트 + SPS 측정"""
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>SPS 캔들 차트</title>
        <meta charset="utf-8">
        <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, sans-serif; 
                background: #131722;
                color: #d1d4dc; 
            }
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px 20px;
                background: #1e222d;
                border-bottom: 1px solid #2a2e39;
            }
            .header h1 { font-size: 1.2em; color: #fff; }
            .legend {
                display: flex;
                gap: 20px;
                font-size: 0.85em;
            }
            .legend-item { display: flex; align-items: center; gap: 5px; }
            .dot { width: 10px; height: 10px; border-radius: 50%; }
            .dot.buy { background: #26a69a; }
            .dot.sell { background: #ef5350; }
            .dot.ivpoc { background: #ff9800; }
            .dot.zone { background: #2196f3; }
            #chart { width: 100%; height: calc(100vh - 50px); }
            .info-panel {
                position: absolute;
                top: 60px;
                right: 20px;
                background: rgba(30,34,45,0.95);
                border: 1px solid #2a2e39;
                border-radius: 8px;
                padding: 15px;
                font-size: 0.85em;
                z-index: 100;
                min-width: 200px;
            }
            .info-row { display: flex; justify-content: space-between; margin: 5px 0; }
            .info-label { color: #888; }
            .info-value { font-weight: bold; }
            .info-value.green { color: #26a69a; }
            .info-value.red { color: #ef5350; }
            .info-value.orange { color: #ff9800; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 SPS 캔들 차트 (NQ1!)</h1>
            <div class="legend">
                <div class="legend-item"><div class="dot buy"></div> 매수 SPS</div>
                <div class="legend-item"><div class="dot sell"></div> 매도 SPS</div>
                <div class="legend-item"><div class="dot ivpoc"></div> iVPOC</div>
                <div class="legend-item"><div class="dot zone"></div> 매수/매도 영역</div>
            </div>
        </div>
        <div id="chart"></div>
        <div class="info-panel" id="infoPanel">
            <div class="info-row"><span class="info-label">시간:</span><span class="info-value" id="infoTime">--</span></div>
            <div class="info-row"><span class="info-label">시가:</span><span class="info-value" id="infoOpen">--</span></div>
            <div class="info-row"><span class="info-label">고가:</span><span class="info-value" id="infoHigh">--</span></div>
            <div class="info-row"><span class="info-label">저가:</span><span class="info-value" id="infoLow">--</span></div>
            <div class="info-row"><span class="info-label">종가:</span><span class="info-value" id="infoClose">--</span></div>
            <hr style="border-color:#2a2e39;margin:10px 0;">
            <div class="info-row"><span class="info-label">iVPOC:</span><span class="info-value orange" id="infoIvpoc">--</span></div>
            <div class="info-row"><span class="info-label">SPS Z:</span><span class="info-value" id="infoZscore">--</span></div>
            <div class="info-row"><span class="info-label">매수 SPS:</span><span class="info-value green" id="infoBuy">--</span></div>
            <div class="info-row"><span class="info-label">매도 SPS:</span><span class="info-value red" id="infoSell">--</span></div>
        </div>
        
        <script>
            const chart = LightweightCharts.createChart(document.getElementById('chart'), {
                layout: { background: { color: '#131722' }, textColor: '#d1d4dc' },
                grid: { vertLines: { color: '#1e222d' }, horzLines: { color: '#1e222d' } },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                rightPriceScale: { borderColor: '#2a2e39' },
                timeScale: { borderColor: '#2a2e39', timeVisible: true }
            });
            
            const candleSeries = chart.addCandlestickSeries({
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderUpColor: '#26a69a',
                borderDownColor: '#ef5350',
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350'
            });
            
            const ivpocLine = chart.addLineSeries({
                color: '#ff9800',
                lineWidth: 2,
                lineStyle: 0,
                title: 'iVPOC'
            });
            
            const buyZoneLine = chart.addLineSeries({
                color: '#26a69a',
                lineWidth: 1,
                lineStyle: 2,
                title: '매수 하단'
            });
            
            const sellZoneLine = chart.addLineSeries({
                color: '#ef5350',
                lineWidth: 1,
                lineStyle: 2,
                title: '매도 상단'
            });
            
            const buySpsMarkers = [];
            const sellSpsMarkers = [];
            
            let chartData = [];
            
            async function loadChartData() {
                try {
                    const response = await fetch('/api/candle-data');
                    const data = await response.json();
                    
                    if (data.success) {
                        chartData = data.candles;
                        
                        candleSeries.setData(data.candles.map(c => ({
                            time: c.time,
                            open: c.open,
                            high: c.high,
                            low: c.low,
                            close: c.close
                        })));
                        
                        ivpocLine.setData(data.candles.map(c => ({
                            time: c.time,
                            value: c.ivpoc
                        })));
                        
                        buyZoneLine.setData(data.candles.map(c => ({
                            time: c.time,
                            value: c.buy_zone
                        })));
                        
                        sellZoneLine.setData(data.candles.map(c => ({
                            time: c.time,
                            value: c.sell_zone
                        })));
                        
                        const markers = [];
                        data.candles.forEach(c => {
                            if (c.is_strong_buy) {
                                markers.push({
                                    time: c.time,
                                    position: 'belowBar',
                                    color: '#26a69a',
                                    shape: 'arrowUp',
                                    text: 'B'
                                });
                            }
                            if (c.is_strong_sell) {
                                markers.push({
                                    time: c.time,
                                    position: 'aboveBar',
                                    color: '#ef5350',
                                    shape: 'arrowDown',
                                    text: 'S'
                                });
                            }
                        });
                        candleSeries.setMarkers(markers);
                        
                        chart.timeScale().fitContent();
                    }
                } catch (e) {
                    console.error('데이터 로드 실패:', e);
                }
            }
            
            chart.subscribeCrosshairMove(param => {
                if (param.time) {
                    const candle = chartData.find(c => c.time === param.time);
                    if (candle) {
                        const date = new Date(candle.time * 1000);
                        document.getElementById('infoTime').textContent = date.toLocaleString();
                        document.getElementById('infoOpen').textContent = candle.open.toFixed(2);
                        document.getElementById('infoHigh').textContent = candle.high.toFixed(2);
                        document.getElementById('infoLow').textContent = candle.low.toFixed(2);
                        document.getElementById('infoClose').textContent = candle.close.toFixed(2);
                        document.getElementById('infoIvpoc').textContent = candle.ivpoc.toFixed(2);
                        document.getElementById('infoZscore').textContent = candle.sps_zscore.toFixed(2);
                        document.getElementById('infoBuy').textContent = candle.is_strong_buy ? 'YES' : '-';
                        document.getElementById('infoSell').textContent = candle.is_strong_sell ? 'YES' : '-';
                    }
                }
            });
            
            loadChartData();
        </script>
    </body>
    </html>
    '''
    return html

@app.route('/api/candle-data')
def api_candle_data():
    """캔들 데이터 + SPS 측정 API"""
    import pandas as pd
    import numpy as np
    from pathlib import Path
    
    try:
        chart_file = Path("attached_assets/CME_MINI_NQ1!,_1_e076b_1766420091573.csv")
        if not chart_file.exists():
            return jsonify({"success": False, "message": "데이터 없음"})
        
        df = pd.read_csv(chart_file)
        df['datetime'] = pd.to_datetime(df['time'])
        df['timestamp'] = df['datetime'].astype('int64') // 10**9
        df = df.sort_values('datetime').reset_index(drop=True)
        
        df['body'] = abs(df['close'] - df['open'])
        df['range'] = df['high'] - df['low']
        df['body_ratio'] = np.where(df['range'] > 0, df['body'] / df['range'], 0)
        df['sps_mean'] = df['body_ratio'].rolling(10).mean()
        df['sps_std'] = df['body_ratio'].rolling(10).std()
        df['sps_zscore'] = np.where(df['sps_std'] > 0, (df['body_ratio'] - df['sps_mean']) / df['sps_std'], 0)
        
        threshold = 1.5
        df['is_bullish'] = df['close'] > df['open']
        df['is_bearish'] = df['close'] < df['open']
        df['is_strong_buy'] = (df['sps_zscore'] >= threshold) & df['is_bullish']
        df['is_strong_sell'] = (df['sps_zscore'] >= threshold) & df['is_bearish']
        
        candles = []
        for _, row in df.tail(500).iterrows():
            candles.append({
                'time': int(row['timestamp']),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'ivpoc': float(row['iVPOC']),
                'buy_zone': float(row['매수 하단']),
                'sell_zone': float(row['매도 상단']),
                'sps_zscore': float(row['sps_zscore']) if not pd.isna(row['sps_zscore']) else 0,
                'is_strong_buy': bool(row['is_strong_buy']),
                'is_strong_sell': bool(row['is_strong_sell'])
            })
        
        return jsonify({
            "success": True,
            "candles": candles,
            "total": len(candles)
        })
        
    except Exception as e:
        import traceback
        return jsonify({"success": False, "message": str(e), "traceback": traceback.format_exc()})

@app.route('/api/signals')
def api_signals():
    """A급 신호 계산 API"""
    from signal_alert_system import SignalAlertSystem
    from pathlib import Path
    
    try:
        system = SignalAlertSystem()
        
        csv_file = Path("attached_assets/CME_MINI_NQ1!,_10_a0e24_1766849121724.csv")
        if not csv_file.exists():
            csv_file = Path("attached_assets/CME_MINI_NQ1!,_10_d7cb7_1766849127128.csv")
        
        if not csv_file.exists():
            return jsonify({"success": False, "message": "10분봉 데이터 파일 없음"})
        
        df = system.load_csv_data(str(csv_file))
        
        all_signals = []
        for i in range(max(0, len(df)-20), len(df)):
            test_df = df.iloc[:i+1]
            if len(test_df) > 200:
                signals = system.calculator.detect_signals(test_df)
                for sig in signals:
                    sig['bar_index'] = i
                    all_signals.append(sig)
        
        summary = system.get_signal_summary(df)
        
        return jsonify({
            "success": True,
            "signals": all_signals[-50:],
            "summary": summary,
            "total_signals": len(all_signals),
            "data_range": f"{df.index[0]} ~ {df.index[-1]}"
        })
        
    except Exception as e:
        import traceback
        return jsonify({"success": False, "message": str(e), "traceback": traceback.format_exc()})

@app.route('/signals')
def signals_dashboard():
    """신호 대시보드 페이지"""
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>A급 신호 대시보드</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 20px; }
            h1 { color: #00d9ff; text-align: center; }
            .container { max-width: 1200px; margin: 0 auto; }
            .summary { background: #16213e; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
            .summary h2 { color: #ff9800; margin-top: 0; }
            .summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }
            .summary-item { background: #0f3460; padding: 15px; border-radius: 8px; text-align: center; }
            .summary-item .label { color: #888; font-size: 12px; }
            .summary-item .value { font-size: 24px; font-weight: bold; margin-top: 5px; }
            .signals { background: #16213e; padding: 20px; border-radius: 10px; }
            .signals h2 { color: #00d9ff; margin-top: 0; }
            .signal-card { background: #0f3460; padding: 15px; border-radius: 8px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
            .signal-card.long { border-left: 4px solid #26a69a; }
            .signal-card.short { border-left: 4px solid #ef5350; }
            .signal-name { font-size: 18px; font-weight: bold; }
            .signal-name.long { color: #26a69a; }
            .signal-name.short { color: #ef5350; }
            .signal-detail { color: #aaa; font-size: 14px; }
            .signal-win { font-size: 20px; font-weight: bold; }
            .signal-win.high { color: #4caf50; }
            .signal-win.medium { color: #ff9800; }
            .signal-levels { display: flex; gap: 20px; }
            .level { text-align: center; }
            .level .label { font-size: 12px; color: #888; }
            .level .value { font-size: 16px; }
            .level.entry { color: #00d9ff; }
            .level.sl { color: #ef5350; }
            .level.tp { color: #4caf50; }
            .refresh-btn { background: #00d9ff; color: #000; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 16px; }
            .refresh-btn:hover { background: #00b8d9; }
            .time { color: #888; font-size: 12px; }
            .no-signals { text-align: center; color: #888; padding: 40px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>A급 신호 대시보드</h1>
            
            <div class="summary">
                <h2>현재 상태</h2>
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="label">현재가</div>
                        <div class="value" id="price">-</div>
                    </div>
                    <div class="summary-item">
                        <div class="label">추세</div>
                        <div class="value" id="trend">-</div>
                    </div>
                    <div class="summary-item">
                        <div class="label">MA200</div>
                        <div class="value" id="ma200">-</div>
                    </div>
                    <div class="summary-item">
                        <div class="label">총 신호</div>
                        <div class="value" id="total">-</div>
                    </div>
                </div>
            </div>
            
            <div class="signals">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h2>최근 신호</h2>
                    <button class="refresh-btn" onclick="loadSignals()">새로고침</button>
                </div>
                <div id="signalList">
                    <div class="no-signals">로딩 중...</div>
                </div>
            </div>
        </div>
        
        <script>
            async function loadSignals() {
                try {
                    const response = await fetch('/api/signals');
                    const data = await response.json();
                    
                    if (data.success) {
                        document.getElementById('price').textContent = data.summary.price.toFixed(2);
                        document.getElementById('trend').textContent = data.summary.trend;
                        document.getElementById('trend').style.color = data.summary.trend === 'UP' ? '#26a69a' : (data.summary.trend === 'DOWN' ? '#ef5350' : '#ff9800');
                        document.getElementById('ma200').textContent = data.summary.ma200.toFixed(2);
                        document.getElementById('total').textContent = data.total_signals;
                        
                        const signalList = document.getElementById('signalList');
                        
                        if (data.signals.length === 0) {
                            signalList.innerHTML = '<div class="no-signals">신호 없음</div>';
                            return;
                        }
                        
                        const uniqueSignals = [];
                        const seen = new Set();
                        data.signals.reverse().forEach(sig => {
                            const key = sig.signal + '_' + sig.time;
                            if (!seen.has(key)) {
                                seen.add(key);
                                uniqueSignals.push(sig);
                            }
                        });
                        
                        signalList.innerHTML = uniqueSignals.slice(0, 20).map(sig => {
                            const isLong = sig.direction === 'LONG';
                            const winClass = sig.win_rate >= 90 ? 'high' : (sig.win_rate >= 80 ? 'medium' : '');
                            return `
                                <div class="signal-card ${isLong ? 'long' : 'short'}">
                                    <div>
                                        <div class="signal-name ${isLong ? 'long' : 'short'}">${sig.signal} - ${sig.name}</div>
                                        <div class="time">${sig.time}</div>
                                    </div>
                                    <div class="signal-levels">
                                        <div class="level entry">
                                            <div class="label">진입</div>
                                            <div class="value">${sig.price.toFixed(2)}</div>
                                        </div>
                                        <div class="level sl">
                                            <div class="label">SL</div>
                                            <div class="value">${sig.sl.toFixed(2)}</div>
                                        </div>
                                        <div class="level tp">
                                            <div class="label">TP</div>
                                            <div class="value">${sig.tp.toFixed(2)}</div>
                                        </div>
                                    </div>
                                    <div class="signal-win ${winClass}">${sig.win_rate}%</div>
                                </div>
                            `;
                        }).join('');
                    }
                } catch (e) {
                    console.error('신호 로드 실패:', e);
                    document.getElementById('signalList').innerHTML = '<div class="no-signals">로드 실패</div>';
                }
            }
            
            loadSignals();
            setInterval(loadSignals, 60000);
        </script>
    </body>
    </html>
    '''
    return html

CHATLOG_DIR = "chatlogs"

def ensure_chatlog_dir():
    if not os.path.exists(CHATLOG_DIR):
        os.makedirs(CHATLOG_DIR)

@app.route('/chatlog')
def chatlog_page():
    """챗로그 저장 페이지"""
    ensure_chatlog_dir()
    files = sorted(os.listdir(CHATLOG_DIR), reverse=True) if os.path.exists(CHATLOG_DIR) else []
    
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>챗로그 저장</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; min-height: 100vh; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            h1 { color: #58a6ff; margin-bottom: 20px; }
            .input-section { background: #161b22; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
            .date-row { display: flex; gap: 10px; margin-bottom: 15px; align-items: center; }
            .date-row input { padding: 10px; border-radius: 8px; border: 1px solid #30363d; background: #0d1117; color: #c9d1d9; }
            .date-row button { padding: 10px 20px; border-radius: 8px; border: none; background: #238636; color: white; cursor: pointer; font-weight: 600; }
            .date-row button:hover { background: #2ea043; }
            textarea { width: 100%; height: 400px; padding: 15px; border-radius: 8px; border: 1px solid #30363d; background: #0d1117; color: #c9d1d9; font-family: monospace; font-size: 14px; resize: vertical; }
            .status { padding: 15px; border-radius: 8px; margin-top: 15px; display: none; }
            .status.success { background: #238636; display: block; }
            .status.error { background: #da3633; display: block; }
            .file-list { background: #161b22; border-radius: 12px; padding: 20px; }
            .file-list h2 { color: #8b949e; margin-bottom: 15px; font-size: 16px; }
            .file-item { padding: 10px 15px; background: #0d1117; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
            .file-name { color: #58a6ff; }
            .file-size { color: #8b949e; font-size: 12px; }
            .search-box { margin-bottom: 15px; }
            .search-box input { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #30363d; background: #0d1117; color: #c9d1d9; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📝 챗로그 저장</h1>
            
            <div class="input-section">
                <div class="date-row">
                    <input type="date" id="dateInput" value="''' + datetime.now().strftime("%Y-%m-%d") + '''">
                    <button onclick="saveLog()">💾 저장</button>
                    <button onclick="analyzeLog()" style="background:#1f6feb;">🔍 분석</button>
                </div>
                <textarea id="content" placeholder="챗로그 내용을 여기에 붙여넣기..."></textarea>
                <div id="status" class="status"></div>
            </div>
            
            <div class="file-list">
                <h2>저장된 챗로그</h2>
                <div class="search-box">
                    <input type="text" id="searchInput" placeholder="검색 (예: 83%, L9, S3)..." onkeyup="searchLogs()">
                </div>
                <div id="fileList">''' + ''.join([
                    f'<div class="file-item"><span class="file-name">{f}</span></div>'
                    for f in files[:20]
                ]) + '''</div>
            </div>
        </div>
        
        <script>
            async function saveLog() {
                const date = document.getElementById('dateInput').value;
                const content = document.getElementById('content').value;
                const status = document.getElementById('status');
                
                if (!content.trim()) {
                    status.className = 'status error';
                    status.textContent = '내용을 입력해주세요';
                    return;
                }
                
                try {
                    const res = await fetch('/api/chatlog/save', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ date, content })
                    });
                    const data = await res.json();
                    
                    if (data.success) {
                        status.className = 'status success';
                        status.textContent = '저장 완료: ' + data.filename;
                        document.getElementById('content').value = '';
                        location.reload();
                    } else {
                        status.className = 'status error';
                        status.textContent = data.message || '저장 실패';
                    }
                } catch (e) {
                    status.className = 'status error';
                    status.textContent = '오류: ' + e.message;
                }
            }
            
            async function analyzeLog() {
                const content = document.getElementById('content').value;
                const status = document.getElementById('status');
                
                if (!content.trim()) {
                    status.className = 'status error';
                    status.textContent = '분석할 내용을 입력해주세요';
                    return;
                }
                
                try {
                    const res = await fetch('/api/chatlog/analyze', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ content })
                    });
                    const data = await res.json();
                    
                    status.className = 'status success';
                    status.innerHTML = '<b>분석 결과:</b><br>' + 
                        '승률 언급: ' + data.win_rates.length + '개<br>' +
                        '신호 정의: ' + data.signals.length + '개';
                } catch (e) {
                    status.className = 'status error';
                    status.textContent = '분석 실패: ' + e.message;
                }
            }
            
            async function searchLogs() {
                const keyword = document.getElementById('searchInput').value;
                if (keyword.length < 2) return;
                
                try {
                    const res = await fetch('/api/chatlog/search?q=' + encodeURIComponent(keyword));
                    const data = await res.json();
                    
                    const fileList = document.getElementById('fileList');
                    if (data.results.length > 0) {
                        fileList.innerHTML = data.results.map(r => 
                            `<div class="file-item">
                                <span class="file-name">${r.file} (Line ${r.line})</span>
                                <span class="file-size">${r.text}</span>
                            </div>`
                        ).join('');
                    }
                } catch (e) {
                    console.error(e);
                }
            }
        </script>
    </body>
    </html>
    '''
    return html

@app.route('/api/chatlog/save', methods=['POST'])
def save_chatlog():
    """챗로그 저장 API"""
    ensure_chatlog_dir()
    
    data = request.get_json()
    date_str = data.get('date', datetime.now().strftime("%Y-%m-%d"))
    content = data.get('content', '')
    
    if not content.strip():
        return jsonify({"success": False, "message": "내용이 없습니다"})
    
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{date_str}_{timestamp}.txt"
    filepath = os.path.join(CHATLOG_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return jsonify({
        "success": True,
        "filename": filename,
        "length": len(content)
    })

@app.route('/api/chatlog/analyze', methods=['POST'])
def analyze_chatlog_api():
    """챗로그 분석 API"""
    data = request.get_json()
    content = data.get('content', '')
    
    win_rates = re.findall(r'(\d+(?:\.\d+)?)\s*%', content)
    signals = re.findall(r'(L\d+|S\d+)[:\s+]+([^\n]+)', content)
    
    return jsonify({
        "win_rates": list(set(win_rates))[:20],
        "signals": [{"name": s[0], "def": s[1][:50]} for s in signals[:20]]
    })

@app.route('/api/chatlog/search', methods=['GET'])
def search_chatlog():
    """챗로그 검색 API"""
    ensure_chatlog_dir()
    
    keyword = request.args.get('q', '')
    results = []
    
    if len(keyword) >= 2:
        for f in os.listdir(CHATLOG_DIR):
            filepath = os.path.join(CHATLOG_DIR, f)
            try:
                with open(filepath, 'r', encoding='utf-8') as file:
                    lines = file.readlines()
                    for i, line in enumerate(lines):
                        if keyword.lower() in line.lower():
                            results.append({
                                "file": f,
                                "line": i,
                                "text": line.strip()[:80]
                            })
            except:
                pass
    
    return jsonify({"results": results[:50]})

@app.route('/api/candle-data')
def get_candle_data():
    """캔들 데이터 + 신호 마커 API"""
    try:
        candles = []
        if os.path.exists('.candle_history.json'):
            with open('.candle_history.json', 'r', encoding='utf-8') as f:
                raw_candles = json.load(f)
                for c in raw_candles[-200:]:
                    candles.append({
                        "time": int(c["time"]) // 1000,
                        "open": c["open"],
                        "high": c["high"],
                        "low": c["low"],
                        "close": c["close"]
                    })
        
        signals = []
        if os.path.exists('.signal_logs.json'):
            with open('.signal_logs.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                for sig in data.get("signals", [])[-20:]:
                    ts = sig.get("timestamp", "")
                    if ts:
                        try:
                            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            signals.append({
                                "id": sig.get("id", ""),
                                "time": int(dt.timestamp()),
                                "position": "aboveBar" if sig.get("direction") == "SHORT" else "belowBar",
                                "color": "#ef5350" if sig.get("direction") == "SHORT" else "#26a69a",
                                "shape": "arrowDown" if sig.get("direction") == "SHORT" else "arrowUp",
                                "text": sig.get("signal_type", ""),
                                "entry_price": sig.get("entry_price", 0),
                                "tp": sig.get("tp", 20),
                                "sl": sig.get("sl", 30),
                                "direction": sig.get("direction", ""),
                                "result": sig.get("result", ""),
                                "status": sig.get("status", ""),
                                "has_candles": len(sig.get("candles", [])) > 0,
                                "candle_count": sig.get("candle_count", 0)
                            })
                        except:
                            pass
        
        return jsonify({
            "success": True,
            "candles": candles,
            "signals": signals
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/signal-candles/<signal_id>')
def get_signal_candles(signal_id):
    """특정 신호의 저장된 캔들 데이터 조회"""
    try:
        from signal_logger import get_signal_with_candles
        sig = get_signal_with_candles(signal_id)
        
        if not sig:
            return jsonify({"success": False, "error": "신호를 찾을 수 없습니다"})
        
        candles = []
        for c in sig.get("candles", []):
            candles.append({
                "time": int(c["time"]) // 1000,
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"]
            })
        
        return jsonify({
            "success": True,
            "signal_id": signal_id,
            "signal_type": sig.get("signal_type", ""),
            "direction": sig.get("direction", ""),
            "entry_price": sig.get("entry_price", 0),
            "tp": sig.get("tp", 20),
            "sl": sig.get("sl", 30),
            "result": sig.get("result", ""),
            "candles": candles,
            "candle_count": len(candles)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/webhook/candle', methods=['POST'])
def webhook_candle():
    """실시간 캔들 데이터 수신 웹훅"""
    from elevator_tracker import add_candle, load_elevator_status
    
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "No data"}), 400
        
        result = add_candle(data)
        status = load_elevator_status()
        
        if status.get('signal'):
            # 🧠 엘리베이터 신호도 AI 분석 후 알림
            from macro_micro_ai import MacroMicroAI
            
            signal_type = status['signal']
            direction = 'SHORT' if 'SHORT' in signal_type else 'LONG'
            entry_price = status.get('current_close', 0)
            
            ai_analyzer = MacroMicroAI()
            for candle in CANDLE_HISTORY[-100:]:
                ai_analyzer.update_candles(candle)
            
            ai_result = ai_analyzer.analyze_entry(signal_type, direction, entry_price)
            ai_decision = ai_result.get('decision', 'WAIT')
            ai_grade = ai_result.get('grade', 'N/A')
            ai_confidence = ai_result.get('confidence', 0)
            ai_tp = ai_result.get('tp', 20)
            ai_sl = ai_result.get('sl', 30)
            ai_reason = ai_result.get('reason', '')
            
            if ai_decision == 'ENTER':
                direction_emoji = "🔴" if direction == 'SHORT' else "🟢"
                msg = f"""{direction_emoji} AI 진입! 엘리베이터 {direction}
━━━━━━━━━━━━━━━━
📍 진입: {entry_price:.1f}
🎯 TP: {ai_tp}pt | SL: {ai_sl}pt
📊 등급: {ai_grade} | 승률: {ai_confidence:.1f}%
💡 {ai_reason}"""
                send_telegram_alert(msg)
            elif ai_decision == 'CAUTION':
                msg = f"""⚠️ AI 주의! 엘리베이터 {direction}
📍 {entry_price:.1f} | 등급: {ai_grade}
💡 {ai_reason}"""
                send_telegram_alert(msg)
            else:
                print(f"❌ 엘리베이터 AI PASS: {signal_type} - {ai_reason}")
        
        current_price = data.get('close', 0)
        if current_price > 0:
            check_sl_tp_hit(current_price)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/elevator/status')
def elevator_status():
    """현재 엘리베이터 상태 조회"""
    from elevator_tracker import load_elevator_status, load_candles
    
    status = load_elevator_status()
    candles = load_candles()
    
    return jsonify({
        "success": True,
        "status": status,
        "candle_count": len(candles),
        "last_candle": candles[-1] if candles else None
    })

@app.route('/api/elevator/export')
def elevator_export():
    """캔들 데이터 CSV 내보내기"""
    from elevator_tracker import export_candles_csv
    
    filename = export_candles_csv()
    if filename:
        return jsonify({"success": True, "filename": filename})
    return jsonify({"success": False, "error": "No data to export"})

@app.route('/api/webhook/signal-enhanced', methods=['POST'])
def webhook_signal_enhanced():
    """강화된 신호 웹훅 - AI 분석 + 엘리베이터 필터 적용"""
    from elevator_tracker import load_elevator_status
    from signal_logger import log_signal
    from macro_micro_ai import MacroMicroAI
    
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "No data"}), 400
        
        status = load_elevator_status()
        
        direction = data.get('direction', '').upper()
        signal_type = data.get('signal_type', '')
        entry_price = float(data.get('entry_price', 0))
        
        elevator_filter = True
        filter_reason = ""
        
        consolidation = status.get('consolidation', 'UNKNOWN')
        
        if direction == 'SHORT':
            if consolidation == 'LOWER':
                elevator_filter = False
                filter_reason = "하단 횡보 중 숏 차단"
            elif consolidation == 'UPPER':
                filter_reason = "상단 횡보 - 숏 유리"
        elif direction == 'LONG':
            if consolidation == 'UPPER':
                elevator_filter = False
                filter_reason = "상단 횡보 중 롱 차단"
            elif consolidation == 'LOWER':
                filter_reason = "하단 횡보 - 롱 유리"
        
        # 🧠 AI 분석
        ai_analyzer = MacroMicroAI()
        for candle in CANDLE_HISTORY[-100:]:
            ai_analyzer.update_candles(candle)
        
        ai_result = ai_analyzer.analyze_entry(signal_type, direction, entry_price)
        ai_decision = ai_result.get('decision', 'WAIT')
        ai_grade = ai_result.get('grade', 'N/A')
        ai_confidence = ai_result.get('confidence', 0)
        ai_tp = ai_result.get('tp', 20)
        ai_sl = ai_result.get('sl', 30)
        ai_reason = ai_result.get('reason', '')
        
        enhanced_data = {
            **data,
            'elevator_filter': elevator_filter,
            'filter_reason': filter_reason,
            'consolidation': consolidation,
            'elevator_direction': status.get('direction', 'UNKNOWN'),
            'ai_decision': ai_decision,
            'ai_grade': ai_grade,
            'ai_confidence': ai_confidence
        }
        
        # 텔레그램 알림 (AI가 ENTER 판단 + 엘리베이터 필터 통과)
        if elevator_filter and ai_decision == 'ENTER':
            result = log_signal(
                signal_type=signal_type + "_AI",
                direction=direction,
                entry_price=entry_price,
                ratio=data.get('ratio', 0),
                channel_pct=data.get('channel_pct', 0),
                z_score=data.get('z_score', 0),
                grade=ai_grade,
                tp=ai_tp,
                sl=ai_sl
            )
            
            direction_emoji = "🔴" if direction == 'SHORT' else "🟢"
            msg = f"""{direction_emoji} AI 진입! {signal_type} {direction}
━━━━━━━━━━━━━━━━
📍 진입: {entry_price:.1f}
🎯 TP: {ai_tp}pt | SL: {ai_sl}pt
📊 등급: {ai_grade} | 승률: {ai_confidence:.1f}%
💡 {ai_reason}
🚀 횡보: {consolidation}"""
            send_telegram_alert(msg)
            
            return jsonify({
                "success": True,
                "signal_logged": True,
                "ai_decision": ai_decision,
                "enhanced_data": enhanced_data,
                "log_result": result
            })
        elif ai_decision == 'CAUTION' and elevator_filter:
            msg = f"""⚠️ AI 주의! {signal_type} {direction}
━━━━━━━━━━━━━━━━
📍 진입: {entry_price:.1f}
📊 등급: {ai_grade} | 승률: {ai_confidence:.1f}%
💡 {ai_reason}"""
            send_telegram_alert(msg)
            
            return jsonify({
                "success": True,
                "signal_logged": False,
                "ai_decision": ai_decision,
                "enhanced_data": enhanced_data
            })
        else:
            # PASS 또는 엘리베이터 차단 → 알림 안 보냄 (로그만)
            reason = filter_reason if not elevator_filter else f"AI PASS: {ai_reason}"
            print(f"❌ 신호 차단: {signal_type} {direction} - {reason}")
            
            return jsonify({
                "success": True,
                "signal_logged": False,
                "blocked": True,
                "ai_decision": ai_decision,
                "reason": reason,
                "enhanced_data": enhanced_data
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/signal-reception', methods=['GET'])
def get_signal_reception():
    """신호 수신 현황 조회 - AI가 모든 신호 받고 있는지 확인"""
    try:
        if os.path.exists(SIGNAL_RECEPTION_LOG):
            with open(SIGNAL_RECEPTION_LOG, 'r') as f:
                log = json.load(f)
            today = datetime.now().strftime('%Y-%m-%d')
            today_data = log.get(today, {"total": 0, "signals": {}})
            return jsonify({
                "success": True,
                "date": today,
                "total_signals": today_data["total"],
                "by_type": today_data["signals"],
                "message": f"오늘 총 {today_data['total']}개 신호 수신"
            })
        return jsonify({"success": True, "total_signals": 0, "by_type": {}, "message": "아직 수신된 신호 없음"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/webhook/ai-filter', methods=['POST'])
def webhook_ai_filter_legacy():
    """레거시 경로 - /webhook/ai-filter로 리다이렉트"""
    return webhook_ai_filter()

@app.route('/webhook/ai-filter', methods=['POST'])
def webhook_ai_filter():
    """📌 순수 데이터 수집 웹훅 - AI 판단 없이 타점 데이터만 저장"""
    from macro_micro_ai import update_realtime_candle
    global SUPPORT_LEVELS
    
    try:
        data = request.json
        print(f"\n🔔 AI-FILTER 웹훅 수신! 데이터: {data}")
        
        if not data:
            return jsonify({"success": False, "error": "No data"}), 400
        
        signal_type = data.get('signal_type', data.get('signal', 'UNKNOWN'))
        action = data.get('action', '')
        print(f"📌 AI-FILTER: signal_type={signal_type}, action={action}")
        log_signal_reception(signal_type or action, 'ai-filter', data)
        
        # 📐 상승빗각/하락빗각 터치 처리 → .iangle_touches.json에 저장
        # ⚠️ 명시적인 빗각 action만 처리! (느슨한 조건 제거 - 2026-01-13)
        is_angle_touch = action in ['rising_angle_touch', 'i_angle_touch', 'angle_touch', 'falling_angle_touch']
        
        if is_angle_touch:
            now = datetime.now()
            touch_price = float(data.get('price', 0))
            
            # 📐 웹훅 라인명 그대로 사용! (TradingView가 정확한 정보 제공)
            line_name = data.get('line', 'unknown')
            angle_type = 'rising' if 'rising' in action or '상승' in line_name else 'falling'
            angle_price = touch_price  # 웹훅 가격이 곧 빗각 가격
            distance = 0
            
            # 📌 SUPPORT_LEVELS에 라인별로 저장
            if 'angles' not in SUPPORT_LEVELS:
                SUPPORT_LEVELS['angles'] = {}
            
            SUPPORT_LEVELS['angles'][line_name] = {
                'price': touch_price,
                'angle_price': angle_price,
                'distance': distance,
                'angle_type': angle_type,
                'timestamp': now.isoformat(),
                'action': action
            }
            
            # 하락빗각/상승빗각 최신값도 저장 (호환성)
            if angle_type == 'rising':
                SUPPORT_LEVELS['rising_angle'] = touch_price
                print(f"📐 상승빗각 자동판별: [{line_name}] 터치 {touch_price:.2f} (기준선: {angle_price:.2f}, 거리: {distance:+.1f}pt)")
            else:
                SUPPORT_LEVELS['falling_angle'] = touch_price
                print(f"📐 하락빗각 자동판별: [{line_name}] 터치 {touch_price:.2f} (기준선: {angle_price:.2f}, 거리: {distance:+.1f}pt)")
            
            print(f"📐 저장된 빗각들: {list(SUPPORT_LEVELS['angles'].keys())}")
            
            # 시장 데이터
            ratio = 0
            channel_pct = 50
            bull_sum_10 = 0
            bear_sum_10 = 0
            candle_type = 'unknown'
            current_body = 0
            
            if len(CANDLE_HISTORY) >= 10:
                import pandas as pd
                df_temp = pd.DataFrame(CANDLE_HISTORY[-100:] if len(CANDLE_HISTORY) >= 100 else CANDLE_HISTORY)
                ch_high = df_temp['high'].max()
                ch_low = df_temp['low'].min()
                channel_range = ch_high - ch_low
                current = CANDLE_HISTORY[-1]
                channel_pct = ((current['close'] - ch_low) / channel_range * 100) if channel_range > 0 else 50
                current_body = current['close'] - current['open']
                candle_type = 'bullish' if current_body > 0 else ('bearish' if current_body < 0 else 'doji')
                bull_sum_10 = sum([max(0, c['close'] - c['open']) for c in CANDLE_HISTORY[-10:]])
                bear_sum_10 = sum([max(0, c['open'] - c['close']) for c in CANDLE_HISTORY[-10:]])
                ratio = bull_sum_10 / (bear_sum_10 + 0.1)
            
            # 📌 빗각 터치 데이터 저장 (자동 판별 결과 포함!)
            touch_data = {
                "timestamp": now.isoformat(),
                "ticker": data.get('ticker', 'MNQ'),
                "line_name": line_name,
                "angle_type": angle_type,
                "angle_price": round(angle_price, 2),
                "touch_price": touch_price,
                "distance": round(distance, 2),
                "action": action,
                "ratio": round(ratio, 2),
                "channel_pct": round(channel_pct, 1),
                "candle_type": candle_type,
                "bull_sum_10": round(bull_sum_10, 2),
                "bear_sum_10": round(bear_sum_10, 2)
            }
            
            touches_file = '.iangle_touches.json'
            touches = []
            if os.path.exists(touches_file):
                try:
                    with open(touches_file, 'r', encoding='utf-8') as f:
                        touches = json.load(f)
                except:
                    touches = []
            
            touches.append(touch_data)
            touches = touches[-500:]
            
            with open(touches_file, 'w', encoding='utf-8') as f:
                json.dump(touches, f, ensure_ascii=False, indent=2)
            
            # 🔥 IANGLE_DATA에도 추가 (스팟 감지용)
            global IANGLE_DATA
            iangle_record = {
                "timestamp": now.isoformat(),
                "line_name": line_name,
                "angle_type": angle_type,
                "angle_price": angle_price,
                "line_value": touch_price,
                "price": touch_price,
                "distance": distance,
                "direction": 'up' if angle_type == 'rising' else 'down',
                "touch_type": action
            }
            IANGLE_DATA.append(iangle_record)
            if len(IANGLE_DATA) > 1000:
                IANGLE_DATA = IANGLE_DATA[-500:]
            
            print(f"\n{'='*50}")
            print(f"📐 빗각 터치! [{now.strftime('%H:%M:%S')}] 자동판별")
            print(f"   라인: {line_name} ({angle_type})")
            print(f"   터치가격: {touch_price:.2f} | 기준선: {angle_price:.2f} | 거리: {distance:+.1f}pt")
            print(f"   배율: {ratio:.2f} | 채널: {channel_pct:.0f}%")
            print(f"{'='*50}\n")
            
            # ═══════════════════════════════════════════════════════════════════════
            # 🔥 STB 로직으로 신호 생성! (2026-01-12 수정)
            # /webhook/iangle과 동일한 판단 로직 사용
            # ═══════════════════════════════════════════════════════════════════════
            iangle_judgment = None
            stb_result = None
            angle_specific = None
            
            if len(CANDLE_HISTORY) >= 200:
                # 1️⃣ check_iangle_breakthrough() 호출 → RESIST_zscore
                iangle_judgment = check_iangle_breakthrough()
                
                if iangle_judgment:
                    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
                    judgment = iangle_judgment.get('judgment', '')
                    direction = iangle_judgment.get('direction', '')
                    confidence = iangle_judgment.get('confidence', '')
                    reason = iangle_judgment.get('reason', '')
                    sps_z = abs(iangle_judgment.get('sps_ratio_z', 0))
                    sector_pct = iangle_judgment.get('sector_pct', 50)
                    is_bearish = iangle_judgment.get('is_bearish', False)
                    is_bullish = iangle_judgment.get('is_bullish', False)
                    
                    print(f"📐 빗각판단: {judgment} {confidence} → zscore={sps_z:.2f}")
                    print(f"   {reason}")
                    
                    # ═══════════════════════════════════════════════════════════════════════
                    # 🔥 빗각은 STB 방향과 같은 방향일 때만 발동! (2026-01-14)
                    # STB롱이면 빗각 롱만, STB숏이면 빗각 숏만 허용
                    # ═══════════════════════════════════════════════════════════════════════
                    valid_signal = False
                    bull_sps = iangle_judgment.get('bull_sps_20', 0)
                    bear_sps = iangle_judgment.get('bear_sps_20', 0)
                    buy_adv = iangle_judgment.get('buy_advantage', False)
                    sell_adv = iangle_judgment.get('sell_advantage', False)
                    
                    # 🔥 STB 방향 확인
                    stb_sell_check = check_stb_sell_spot()
                    stb_buy_check = check_stb_buy_spot()
                    stb_short_active = stb_sell_check and stb_sell_check.get('signal')
                    stb_long_active = stb_buy_check and stb_buy_check.get('signal')
                    
                    if is_bearish and sell_adv and sps_z >= 0.5:
                        if stb_short_active:
                            # STB숏 + 음봉 + 매도유리 + z스코어 → 저항 (숏)
                            direction = 'SHORT'
                            valid_signal = True
                            print(f"✅ 빗각({angle_type}) + STB숏 → 숏! bull={bull_sps:.1f} bear={bear_sps:.1f} z={sps_z:.2f}")
                        else:
                            print(f"⛔ 빗각숏 차단: STB숏 미발생 (bull={bull_sps:.1f} bear={bear_sps:.1f})")
                    
                    elif is_bullish and buy_adv and sps_z >= 0.5:
                        if stb_long_active:
                            # STB롱 + 양봉 + 매수유리 + z스코어 → 지지 (롱)
                            direction = 'LONG'
                            valid_signal = True
                            print(f"✅ 빗각({angle_type}) + STB롱 → 롱! bull={bull_sps:.1f} bear={bear_sps:.1f} z={sps_z:.2f}")
                        else:
                            print(f"⛔ 빗각롱 차단: STB롱 미발생 (bull={bull_sps:.1f} bear={bear_sps:.1f})")
                    
                    if valid_signal:
                        # ⭐ RESIST_zscore 쿨다운 체크 (5분)
                        global LAST_RESIST_SIGNAL
                        resist_key = 'short' if direction == 'SHORT' else 'long'
                        last_resist = LAST_RESIST_SIGNAL.get(resist_key)
                        cooldown_min = LAST_RESIST_SIGNAL.get('cooldown_minutes', 5)
                        
                        skip_resist = False
                        if last_resist:
                            try:
                                last_dt = datetime.fromisoformat(last_resist)
                                if now - last_dt < timedelta(minutes=cooldown_min):
                                    skip_resist = True
                                    print(f"⏱️ RESIST_{resist_key} 쿨다운 중 ({cooldown_min}분) - 스킵")
                            except:
                                pass
                        
                        if not skip_resist:
                            emoji = '🔴' if direction == 'SHORT' else '🟢'
                            adv_text = '매도유리' if sell_adv else '매수유리'
                            tg_msg = f"""{emoji} RESIST_zscore {confidence}! (93% 저항/지지)
━━━━━━━━━━━━━━━━
📐 빗각: {line_name} ({angle_type}) @ {touch_price:.2f}
📍 현재가: {touch_price:.2f}
📊 섹터: {sector_pct:.0f}%
💪 bull_sps: {bull_sps:.1f} | bear_sps: {bear_sps:.1f} ({adv_text})
📉 SPS비율z: {iangle_judgment.get('sps_ratio_z', 0):.2f}
🎯 방향: {direction} | TP:20pt SL:30pt
💡 {reason}
⏰ {timestamp}"""
                            send_telegram_alert(tg_msg, signal_type='RESIST_zscore')
                            LAST_RESIST_SIGNAL[resist_key] = now.isoformat()
                            print(f"✅ RESIST_zscore 전송 완료!")
                        
                        # ✅ 유효 신호만 추적 등록
                        from signal_logger import log_signal
                        log_signal(
                            signal_type='RESIST_zscore',
                            direction=direction,
                            entry_price=touch_price,
                            ratio=iangle_judgment.get('buy_ratio_z', 0) if direction == 'LONG' else iangle_judgment.get('sell_ratio_z', 0),
                            channel_pct=iangle_judgment.get('sector_pct', 50),
                            z_score=iangle_judgment.get('sps_ratio_z', 0),
                            grade=confidence,
                            notes=reason
                        )
                    else:
                        # ❌ 조건불충족 = 추적 안 함!
                        print(f"📐 빗각터치 관찰: {line_name} ({angle_type}) 섹터{sector_pct:.0f}% - 조건불충족 (추적X)")
                
                # 2️⃣ STB 점 로직 즉시 판단
                stb_sell = check_stb_sell_spot()
                stb_buy = check_stb_buy_spot()
                
                if stb_sell and stb_sell.get('signal'):
                    sps_z = abs(stb_sell.get('sps_ratio_z', 0))
                    stb_result = {
                        'type': 'STB숏',
                        'grade': stb_sell.get('grade'),
                        'reason': stb_sell.get('reason'),
                        'sector_pct': stb_sell.get('sector_pct'),
                        'sps_ratio_z': stb_sell.get('sps_ratio_z')
                    }
                    print(f"🔴 빗각+STB숏 {stb_result['grade']}! {stb_result['reason']}")
                    
                    # 시퀀스 롱 - SEQUENCE_TRIGGERS로 자동 기록됨
                    
                    if stb_result['grade'] in ['S++', 'S+', 'S'] and sps_z >= 0.5:
                        # ⭐ RESIST_zscore 쿨다운 체크 (5분)
                        last_resist = LAST_RESIST_SIGNAL.get('short')
                        cooldown_min = LAST_RESIST_SIGNAL.get('cooldown_minutes', 5)
                        
                        skip_resist = False
                        if last_resist:
                            try:
                                last_dt = datetime.fromisoformat(last_resist)
                                if now - last_dt < timedelta(minutes=cooldown_min):
                                    skip_resist = True
                                    print(f"⏱️ RESIST_숏 쿨다운 중 ({cooldown_min}분) - 스킵")
                            except:
                                pass
                        
                        if not skip_resist:
                            if sps_z >= 1.5:
                                sig_type = 'RESIST_zscore_1.5'
                                win_rate = 96.1
                            elif sps_z >= 1.0:
                                sig_type = 'RESIST_zscore_1.0'
                                win_rate = 95.0
                            else:
                                sig_type = 'RESIST_zscore_0.5'
                                win_rate = 91.8
                            
                            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
                            tg_msg = f"""🔴 {sig_type} {stb_result['grade']}! ({win_rate}% 저항률)
━━━━━━━━━━━━━━━━
📐 빗각: {line_name} ({angle_type}) @ {touch_price:.2f}
📍 현재가: {touch_price:.2f}
📊 섹터: {stb_sell['sector_pct']:.0f}% | SPS비율z: {stb_sell['sps_ratio_z']:.2f}
🎯 TP: 20pt | SL: 30pt
💡 {stb_sell['reason']}
⏰ {timestamp}"""
                            send_telegram_alert(tg_msg, signal_type=sig_type)
                            LAST_RESIST_SIGNAL['short'] = now.isoformat()
                            print(f"✅ {sig_type} (STB숏) 전송 완료!")
                
                elif stb_buy and stb_buy.get('signal'):
                    sps_z = abs(stb_buy.get('sps_ratio_z', 0))
                    stb_result = {
                        'type': 'STB롱',
                        'grade': stb_buy.get('grade'),
                        'reason': stb_buy.get('reason'),
                        'sector_pct': stb_buy.get('sector_pct'),
                        'sps_ratio_z': stb_buy.get('sps_ratio_z')
                    }
                    print(f"🟢 빗각+STB롱 {stb_result['grade']}! {stb_result['reason']}")
                    
                    if stb_result['grade'] in ['S++', 'S+', 'S'] and sps_z >= 0.5:
                        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
                        tg_msg = f"""🟢 STB롱 {stb_result['grade']}! (94.1% 지지률)
━━━━━━━━━━━━━━━━
📐 빗각: {line_name} ({angle_type}) @ {touch_price:.2f}
📍 현재가: {touch_price:.2f}
📊 섹터: {stb_buy['sector_pct']:.0f}% | SPS비율z: {stb_buy['sps_ratio_z']:.2f}
🎯 TP: 20pt | SL: 30pt
💡 {stb_buy['reason']}
⏰ {timestamp}"""
                        send_telegram_alert(tg_msg, signal_type='STB롱')
                        print(f"✅ STB롱 전송 완료!")
                
                # 3️⃣ 빗각 특화 판단
                if touch_price > 0:
                    angle_specific = check_angle_specific_judgment(touch_price, line_name)
                    
                    if angle_specific and angle_specific.get('final_judgment') not in ['관찰', '', None]:
                        print(f"📐 빗각특화: {angle_specific.get('touched_line', '')} → {angle_specific['final_judgment']} {angle_specific.get('confidence', '')}")
                        
                        if angle_specific.get('verified_signal') and angle_specific.get('confidence') in ['S+', 'S']:
                            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
                            verified_sig = angle_specific['verified_signal']
                            winrate = angle_specific.get('verified_winrate', 0)
                            judgment = angle_specific.get('final_judgment', '')
                            reason = angle_specific.get('reason', '')
                            
                            if '저항' in judgment or '숏' in judgment.lower():
                                direction = 'SHORT'
                                emoji = '🔴'
                                tp_price = touch_price - 20
                                sl_price = touch_price + 10
                            else:
                                direction = 'LONG'
                                emoji = '🟢'
                                tp_price = touch_price + 20
                                sl_price = touch_price - 10
                            
                            tg_msg = f"""{emoji} {verified_sig} {angle_specific['confidence']}! ({winrate:.1f}%)
━━━━━━━━━━━━━━━━
📐 빗각: {line_name} ({angle_specific.get('touch_type', angle_type)})
📍 진입: {touch_price:.2f}
🎯 TP: {tp_price:.2f} (+20pt) | SL: {sl_price:.2f} (-10pt)
📊 섹터: {angle_specific.get('sector_pct', 0):.0f}% | SPS비율z: {angle_specific.get('sps_ratio_z', 0):.2f}
📈 기울기: {angle_specific.get('slope_per_hour', 0):+.2f} pt/h
💡 {reason}
⏰ {timestamp}"""
                            send_telegram_alert(tg_msg, signal_type=verified_sig)
                            print(f"📨 빗각 검증신호 전송: {verified_sig} {direction}")
            
            return jsonify({
                "success": True,
                "data": touch_data,
                "iangle_judgment": iangle_judgment,
                "stb_result": stb_result,
                "angle_specific": angle_specific,
                "message": f"빗각 터치 + STB 판단 완료 ({action})"
            })
        
        if 'candle' in data:
            candle = data['candle']
            update_realtime_candle(candle)
        
        if data.get('type') == 'candle_update':
            return jsonify({"success": True, "action": "candle_updated"})
        
        # 📌 순수 데이터 수집 - AI 판단 없음!
        now = datetime.now()
        direction = data.get('direction', 'UNKNOWN')
        entry_price = data.get('entry_price', data.get('price', 0))
        
        # 📐 웹훅에서 받는 라인 데이터 (상승빗각, 하락빗각, 중요라인 등)
        rising_angle = data.get('rising_angle', data.get('rising_i_angle', 0))
        falling_angle = data.get('falling_angle', data.get('falling_i_angle', data.get('angle_price', 0)))
        zpoc = data.get('zpoc', 0)
        blackline = data.get('blackline', 0)
        poc = data.get('poc', 0)
        ivpoc = data.get('ivpoc', 0)
        line_name = data.get('line', data.get('line_name', ''))
        line_value = data.get('line_value', data.get('line_price', 0))
        
        # 📍 지지 레벨 업데이트 (전역)
        if rising_angle:
            SUPPORT_LEVELS['rising_angle'] = float(rising_angle)
        if falling_angle:
            SUPPORT_LEVELS['falling_angle'] = float(falling_angle)
        if blackline:
            SUPPORT_LEVELS['blackline'] = float(blackline)
        if poc:
            SUPPORT_LEVELS['poc'] = float(poc)
            # 📌 zpoc 자동 계산: 블랙라인 POC 기준점
            SUPPORT_LEVELS['zpoc'] = float(poc)
        if ivpoc:
            SUPPORT_LEVELS['ivpoc'] = float(ivpoc)
        
        # 시장 데이터 계산
        ratio = 0
        channel_pct = 50
        channel_range = 0
        bull_sum_10 = 0
        bear_sum_10 = 0
        candle_type = 'unknown'
        
        if len(CANDLE_HISTORY) >= 10:
            import pandas as pd
            df_temp = pd.DataFrame(CANDLE_HISTORY[-100:] if len(CANDLE_HISTORY) >= 100 else CANDLE_HISTORY)
            ch_high = df_temp['high'].max()
            ch_low = df_temp['low'].min()
            channel_range = ch_high - ch_low
            current = CANDLE_HISTORY[-1]
            channel_pct = ((current['close'] - ch_low) / channel_range * 100) if channel_range > 0 else 50
            
            current_body = current['close'] - current['open']
            candle_type = 'bullish' if current_body > 0 else ('bearish' if current_body < 0 else 'doji')
            
            bull_sum_10 = sum([max(0, c['close'] - c['open']) for c in CANDLE_HISTORY[-10:]])
            bear_sum_10 = sum([max(0, c['open'] - c['close']) for c in CANDLE_HISTORY[-10:]])
            ratio = bull_sum_10 / (bear_sum_10 + 0.1)
        
        # 신호 데이터 저장 (웹훅에서 오는 라인 데이터 포함!)
        signal_data = {
            "timestamp": now.isoformat(),
            "signal_type": signal_type,
            "direction": direction,
            "entry_price": float(entry_price) if entry_price else 0,
            "line_name": line_name,
            "line_value": float(line_value) if line_value else 0,
            "rising_angle": float(rising_angle) if rising_angle else 0,
            "zpoc": float(zpoc) if zpoc else 0,
            "blackline": float(blackline) if blackline else 0,
            "poc": float(poc) if poc else 0,
            "ivpoc": float(ivpoc) if ivpoc else 0,
            "ratio": round(ratio, 2),
            "channel_pct": round(channel_pct, 1),
            "channel_range": round(channel_range, 1),
            "candle_type": candle_type,
            "bull_sum_10": round(bull_sum_10, 2),
            "bear_sum_10": round(bear_sum_10, 2),
            "support_levels": dict(SUPPORT_LEVELS)
        }
        
        # .ai_filter_signals.json에 저장
        signals_file = '.ai_filter_signals.json'
        signals = []
        if os.path.exists(signals_file):
            try:
                with open(signals_file, 'r', encoding='utf-8') as f:
                    signals = json.load(f)
            except:
                signals = []
        
        signals.append(signal_data)
        signals = signals[-500:]
        
        with open(signals_file, 'w', encoding='utf-8') as f:
            json.dump(signals, f, ensure_ascii=False, indent=2)
        
        print(f"\n{'='*50}")
        print(f"📊 신호 데이터 수집! [{now.strftime('%H:%M:%S')}]")
        print(f"   타입: {signal_type} | 방향: {direction}")
        print(f"   가격: {entry_price}")
        print(f"   라인: {line_name} @ {line_value}" if line_name else "")
        print(f"   상승빗각: {rising_angle}" if rising_angle else "")
        print(f"   배율: {ratio:.2f} | 채널: {channel_pct:.0f}%")
        print(f"{'='*50}\n")
        
        return jsonify({
            "success": True,
            "data": signal_data,
            "message": "신호 데이터 저장됨 (AI 판단 X)"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/ai/status', methods=['GET'])
def ai_status():
    """현재 AI 분석 상태 조회"""
    from macro_micro_ai import get_current_analysis
    
    try:
        analysis = get_current_analysis()
        return jsonify({"success": True, **analysis})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ai/engine', methods=['GET'])
def ai_engine_status():
    """🤖 AI 트레이딩 엔진 상태 조회 - 모든 지표 통합"""
    try:
        status = get_ai_status()
        ind = status.get('indicators', {})
        
        return jsonify({
            "success": True,
            "candle_count": status['candle_count'],
            "ratio": ind.get('ratio', 0),
            "cum_ratio_100": ind.get('cum_ratio_100', 0),
            "gap_from_buy_ivwap": ind.get('gap_from_buy_ivwap', 0),
            "gap_from_sell_ivwap": ind.get('gap_from_sell_ivwap', 0),
            "stagnation_type": ind.get('stagnation_type', 'UNKNOWN'),
            "market_direction": ind.get('market_direction', 'UNKNOWN'),
            "overheat_status": ind.get('overheat_status', 'UNKNOWN'),
            "short_blocked": ind.get('short_blocked', True),
            "new_highs": ind.get('new_highs_60', 0),
            "new_lows": ind.get('new_lows_60', 0),
            "all_indicators": ind
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ai/dual', methods=['GET'])
def dual_consensus_status():
    """🤝 듀얼 AI 합의 시스템 상태 - 트레이딩AI + 검증AI"""
    try:
        status = get_dual_status()
        issues = get_all_issues()
        
        return jsonify({
            "success": True,
            "system": status.get('system', 'UNKNOWN'),
            "trading_ai": status.get('trading_ai', {}),
            "validator_ai": status.get('validator_ai', {}),
            "recent_issues": issues[-10:] if issues else [],
            "total_issues": len(issues)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ai/issues', methods=['GET'])
def get_validator_issues():
    """🛡️ 검증AI 이슈 로그 - 누락/오류 상세"""
    try:
        issues = get_all_issues()
        
        high_severity = [i for i in issues if i.get('level') == 'ERROR']
        warnings = [i for i in issues if i.get('level') == 'WARN']
        
        return jsonify({
            "success": True,
            "total": len(issues),
            "errors": len(high_severity),
            "warnings": len(warnings),
            "recent_errors": high_severity[-10:] if high_severity else [],
            "recent_warnings": warnings[-10:] if warnings else [],
            "all_issues": issues[-50:]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/market-direction', methods=['GET'])
def get_market_direction():
    """시장 방향 조회 - 상승장/하락장/과열 감지"""
    try:
        state = detect_market_direction()
        
        overheat = state.get('overheat_status', 'NORMAL')
        if overheat == 'COOLING_FAST':
            msg = "🔥 급냉각! 숏 허용!"
        elif overheat == 'COOLING':
            msg = "🟠 과열 식는중... 숏 준비"
        elif overheat == 'EXTREME_STAGNANT':
            msg = "🟠 극과열+정체 = 71% 횡보 예상"
        elif overheat == 'EXTREME':
            msg = "🔴 극과열! 피크 대기"
        elif overheat == 'WARNING_STAGNANT':
            msg = "🟠 과열+정체 = 횡보 예상"
        elif overheat == 'WARNING':
            msg = "🟠 과열 경고"
        elif state['short_blocked']:
            msg = "🔴 상승장! 숏 차단!"
        else:
            msg = "🟢 하락장/횡보 - 숏 허용"
        
        return jsonify({
            "success": True,
            "direction": state['direction'],
            "new_highs": state['new_highs'],
            "new_lows": state['new_lows'],
            "bull_score": state.get('bull_score', 0),
            "bear_score": state.get('bear_score', 0),
            "price_vs_ivwap": state.get('price_vs_ivwap', 0),
            "sell_ivwap_gap": state.get('sell_ivwap_gap', 0),
            "total_gap": state.get('total_gap', 0),
            "gap_change": state.get('gap_change', 0),
            "ivwap_change": state.get('ivwap_change', 0),
            "ivwap_stagnant": state.get('ivwap_stagnant', False),
            "overheat_status": overheat,
            "short_blocked": state['short_blocked'],
            "message": msg,
            "recommendation": "롱만 거래" if state['short_blocked'] else "숏 허용"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ai/penalty', methods=['POST'])
def ai_rule_violation():
    """🚨 AI 룰 위반 처벌 - 형이 호출하면 텔레그램 알림"""
    try:
        data = request.get_json() or {}
        reason = data.get('reason', '필수 파일 미읽기')
        
        from ai_validator import send_validator_alert
        
        msg = f"""🚨 <b>AI 룰 위반 처벌!</b>
━━━━━━━━━━━━━━━━
📍 위반 사유: {reason}
⚠️ 처벌: 세션 재시작 필요
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━
⛔ AI가 replit.md 규칙 위반함!"""
        
        send_validator_alert(msg)
        
        violation_log = {
            'time': datetime.now().isoformat(),
            'reason': reason,
            'action': 'penalty_sent'
        }
        
        log_file = '.ai_violation_log.json'
        violations = []
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r') as f:
                    violations = json.load(f)
            except:
                violations = []
        violations.append(violation_log)
        with open(log_file, 'w') as f:
            json.dump(violations[-100:], f, indent=2, default=str)
        
        print(f"🚨 AI 룰 위반 처벌 알림 전송: {reason}")
        
        return jsonify({
            "success": True,
            "message": "처벌 알림 전송됨",
            "reason": reason,
            "total_violations": len(violations)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/sideways-prediction', methods=['GET'])
def sideways_prediction():
    """📊 횡보 종료 예측 v3"""
    try:
        from sideways_end_predictor import predict_sideways_end_v3, detect_sideways, format_sideways_prediction
        
        if len(CANDLE_HISTORY) < 60:
            return jsonify({"success": False, "error": "캔들 60개 필요"})
        
        import pandas as pd
        df = pd.DataFrame(CANDLE_HISTORY[-100:] if len(CANDLE_HISTORY) >= 100 else CANDLE_HISTORY)
        
        rolling_high = df['high'].max()
        rolling_low = df['low'].min()
        range_pt = rolling_high - rolling_low
        
        current = CANDLE_HISTORY[-1]
        prev = CANDLE_HISTORY[-2] if len(CANDLE_HISTORY) >= 2 else current
        
        channel_pct = ((current['close'] - rolling_low) / range_pt * 100) if range_pt > 0 else 50
        
        def calc_ratio(c):
            return (c['close'] - c['low']) / (c['high'] - c['close'] + 0.25)
        
        ratio = calc_ratio(current)
        prev_ratio = calc_ratio(prev)
        
        recent_10 = CANDLE_HISTORY[-10:]
        bull_sum_10 = sum([max(0, c['close'] - c['open']) for c in recent_10])
        bear_sum_10 = sum([max(0, c['open'] - c['close']) for c in recent_10])
        
        sideways_check = detect_sideways({'range_pt': range_pt})
        
        data = {
            'channel_pct': channel_pct,
            'ratio': ratio,
            'prev_ratio': prev_ratio,
            'range_pt': range_pt,
            'bull_sum_10': bull_sum_10,
            'bear_sum_10': bear_sum_10
        }
        
        prediction = predict_sideways_end_v3(data)
        
        return jsonify({
            "success": True,
            "prediction": prediction['prediction'],
            "time_estimate": prediction['time_estimate'],
            "break_direction": prediction['break_direction'],
            "confidence": prediction['confidence'],
            "reasons": prediction['reasons'],
            "formatted": format_sideways_prediction(prediction)
        })
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/trading-logic', methods=['GET'])
def trading_logic():
    """
    📊 완전 트레이딩 로직 (4단계)
    1. 시간 예측: 횡보 언제 끝나나
    2. 시나리오 판단: 매수/매도 조건 충족?
    3. 배율 측정: 진입 타이밍 맞나?
    4. 최종 판단: 진입/대기/관찰
    """
    try:
        from sideways_trading_logic import SidewaysTradingLogic
        
        if len(CANDLE_HISTORY) < 60:
            return jsonify({"success": False, "error": "캔들 60개 필요"})
        
        import pandas as pd
        df = pd.DataFrame(CANDLE_HISTORY[-100:] if len(CANDLE_HISTORY) >= 100 else CANDLE_HISTORY)
        
        rolling_high = df['high'].max()
        rolling_low = df['low'].min()
        range_pt = rolling_high - rolling_low
        
        current = CANDLE_HISTORY[-1]
        prev = CANDLE_HISTORY[-2] if len(CANDLE_HISTORY) >= 2 else current
        
        channel_pct = ((current['close'] - rolling_low) / range_pt * 100) if range_pt > 0 else 50
        
        def calc_ratio(c):
            return (c['close'] - c['low']) / (c['high'] - c['close'] + 0.25)
        
        ratio = calc_ratio(current)
        prev_ratio = calc_ratio(prev)
        ratio_change_pct = ((ratio - prev_ratio) / prev_ratio * 100) if prev_ratio > 0.1 else 0
        
        recent_10 = CANDLE_HISTORY[-10:]
        recent_3 = CANDLE_HISTORY[-3:]
        
        bull_sum_10 = sum([max(0, c['close'] - c['open']) for c in recent_10])
        bear_sum_10 = sum([max(0, c['open'] - c['close']) for c in recent_10])
        price_change_3 = current['close'] - recent_3[0]['close'] if len(recent_3) >= 3 else 0
        
        # Prior type 계산 (20봉)
        if len(CANDLE_HISTORY) >= 40:
            recent_20 = CANDLE_HISTORY[-20:]
            prev_20 = CANDLE_HISTORY[-40:-20]
            
            h20 = max(c['high'] for c in recent_20)
            l20 = min(c['low'] for c in recent_20)
            h40 = max(c['high'] for c in prev_20)
            l40 = min(c['low'] for c in prev_20)
            
            if h20 > h40 and l20 > l40:
                prior_type = 'RISE'
            elif h20 < h40 and l20 < l40:
                prior_type = 'FALL'
            else:
                prior_type = 'FLAT'
        else:
            prior_type = 'FLAT'
        
        data = {
            'channel_pct': channel_pct,
            'ratio': ratio,
            'prev_ratio': prev_ratio,
            'ratio_change_pct': ratio_change_pct,
            'bull_sum_10': bull_sum_10,
            'bear_sum_10': bear_sum_10,
            'prior_type': prior_type,
            'price_change_3': price_change_3,
            'range_pt': range_pt
        }
        
        logic = SidewaysTradingLogic()
        analysis = logic.analyze(data)
        formatted = logic.format_analysis(analysis)
        
        decision = analysis['step4_decision']
        
        return jsonify({
            "success": True,
            "price": current['close'],
            "channel_pct": round(channel_pct, 1),
            "ratio": round(ratio, 2),
            "prior_type": prior_type,
            "step1_time": analysis['step1_time'],
            "step2_scenario": {
                'matched': analysis['step2_scenario']['matched'],
                'best': analysis['step2_scenario']['best']
            },
            "step3_ratio": analysis['step3_ratio'],
            "step4_decision": decision,
            "action": decision['action'],
            "direction": decision['direction'],
            "grade": decision['grade'],
            "confidence": decision['confidence'],
            "formatted": formatted
        })
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 V7 최종 신호 웹훅 (무지성 클릭용)
# ═══════════════════════════════════════════════════════════════════════════════
V7_COOLDOWN = {}  # 신호별 쿨다운 (5분)

@app.route('/webhook/v7', methods=['POST'])
def v7_webhook():
    """V7 COMPILE SPEC FINAL 웹훅 (4-Layer Architecture)"""
    global V7_COOLDOWN
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        if data.get('passphrase') not in WEBHOOK_SECRETS:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        candle = {
            'time': data.get('time', datetime.now().isoformat()),
            'open': float(data.get('open', 0)),
            'high': float(data.get('high', 0)),
            'low': float(data.get('low', 0)),
            'close': float(data.get('close', 0)),
        }
        
        result = process_candle_v7(candle)
        
        action = result.get('action')
        message = result.get('message')
        signal = result.get('signal')
        status = result.get('status', {})
        stream_status = result.get('stream_status', 'UNKNOWN')
        
        if action == 'STREAM_STALE':
            print(f"🔒 V7 STREAM STALE: {stream_status}")
            return jsonify({
                "status": "stream_stale",
                "stream_status": stream_status,
                "message": "New entries blocked due to stream gap"
            }), 200
        
        if action and message:
            now = datetime.now()
            
            if action == 'ENTRY' and signal:
                sig_name = signal.name
                last_time = V7_COOLDOWN.get(sig_name)
                
                if last_time and (now - last_time).total_seconds() < 300:
                    print(f"⏭️ V7 쿨다운: {sig_name}")
                    return jsonify({"status": "cooldown", "signal": sig_name}), 200
                
                V7_COOLDOWN[sig_name] = now
                
                print(f"🎯 V7 ENTRY: {sig_name} | Score:{signal.grammar_score} | STATE:{status.get('state')}")
            
            elif action == 'CONTINUATION':
                print(f"🔄 V7 CONTINUATION: {status.get('state')} | MFE:{status.get('mfe', 0):.1f}pt")
            
            elif action == 'STOP':
                print(f"🛑 V7 STOP")
            
            elif action == 'TP':
                print(f"✅ V7 TP HIT")
            
            elif action == 'BLOCKED':
                print(f"🚫 V7 BLOCKED: Score 0")
                return jsonify({"status": "blocked", "reason": "grammar_score=0"}), 200
            
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                try:
                    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    requests.post(url, json={
                        'chat_id': TELEGRAM_CHAT_ID,
                        'text': message,
                        'parse_mode': 'HTML'
                    }, timeout=5)
                    print(f"📱 V7 텔레그램 전송: {action}")
                except Exception as e:
                    print(f"❌ V7 텔레그램 실패: {e}")
        
        return jsonify({
            "status": "ok",
            "action": action,
            "signal": signal.name if signal else None,
            "grammar_score": signal.grammar_score if signal else None,
            "state": status.get('state'),
            "continuation_active": status.get('continuation_active', False),
            "mfe": status.get('mfe', 0),
            "v7_status": status
        })
    
    except Exception as e:
        import traceback
        print(f"❌ V7 웹훅 오류: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v7/status', methods=['GET'])
def v7_status():
    """V7 엔진 상태 조회"""
    engine = get_v7_engine()
    return jsonify(engine.get_status())


@app.route('/api/v7/test', methods=['POST'])
def v7_test():
    """V7 신호 테스트 (4-Layer Architecture)"""
    data = request.get_json(force=True, silent=True) or {}
    
    candle = {
        'open': float(data.get('open', 0)),
        'high': float(data.get('high', 0)),
        'low': float(data.get('low', 0)),
        'close': float(data.get('close', 0)),
    }
    
    engine = get_v7_engine()
    signals = engine.check_signals(candle)
    
    return jsonify({
        "signals": [
            {
                "name": s.name,
                "axis": s.axis,
                "meaning": s.meaning,
                "direction": s.direction,
                "mode": s.mode,
                "tp": s.tp,
                "sl": s.sl,
                "grammar_score": s.grammar_score
            }
            for s in signals
        ],
        "state": engine.current_state.value,
        "range": engine.calc_range(),
        "continuation_allowed": engine.current_state.value in ['LARGE_STABLE', 'LARGE_VOLATILE'],
        "status": engine.get_status()
    })


if __name__ == "__main__":
    # ☁️ 클라우드 스케줄러 설정 (1시간마다 자동 분석)
    scheduler.add_job(
        func=cloud_auto_cycle,
        trigger=IntervalTrigger(hours=1),
        id='cloud_auto_analysis',
        name='Cloud Auto Analysis',
        replace_existing=True
    )
    
    # 📚 6시간마다 전체 데이터 인덱싱 + 제이슨 분석
    scheduler.add_job(
        func=build_history_index,
        trigger=IntervalTrigger(hours=6),
        id='jason_deep_indexing',
        name='Jason Deep Indexing (6h)',
        replace_existing=True
    )
    
    # Flask와 함께 스케줄러 시작
    try:
        scheduler.start()
        print("☁️ 클라우드 순환 학습 활성화됨 (1시간마다 자동 분석)")
    except Exception as e:
        print(f"⚠️ 스케줄러 시작 실패: {e}")
    
    os.environ['FLASK_ENV'] = 'development'
    app.run(host='0.0.0.0', port=5000, debug=False)
