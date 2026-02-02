"""
OPA Sensor Replay - 과거 데이터로 센서 물리학 수집
체결/판단 없이 순수 OPA_SIGNAL만 기록
"""

import os
import sys
import csv
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from paper_mode_engine import PaperModeEngine


def parse_datetime(ts_str: str) -> datetime:
    """타임스탬프 파싱"""
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except:
        return datetime.now()


def get_session(dt: datetime) -> str:
    """RTH/ETH 세션 구분 (EST 기준)"""
    hour = dt.hour
    if 9 <= hour < 16:
        return "RTH"
    return "ETH"


def replay_candles(csv_path: str, limit: int = None):
    """과거 캔들 리플레이 - OPA_SIGNAL 수집"""
    
    engine = PaperModeEngine()
    engine.mode = "REPLAY"
    
    raw_log_path = os.path.join(os.path.dirname(__file__), 'opa_signal_raw.jsonl')
    if os.path.exists(raw_log_path):
        os.remove(raw_log_path)
        print(f"[REPLAY] 기존 로그 삭제: {raw_log_path}")
    
    processed = 0
    signals_found = 0
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            if limit and processed >= limit:
                break
            
            try:
                bar = {
                    'time': row['time'],
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close'])
                }
                
                dt = parse_datetime(row['time'])
                engine.state['timestamp'] = row['time']
                engine.state['session'] = get_session(dt)
                
                before_count = len(engine.opa_signals)
                engine.on_bar(bar)
                after_count = len(engine.opa_signals)
                
                if after_count > before_count:
                    signals_found += 1
                
                processed += 1
                
                if processed % 1000 == 0:
                    print(f"[REPLAY] {processed} bars 처리, {signals_found} signals 발견")
                    
            except Exception as e:
                print(f"[ERROR] Row {processed}: {e}")
                continue
    
    print(f"\n{'='*60}")
    print(f"[REPLAY 완료]")
    print(f"  처리 bars: {processed}")
    print(f"  발견 signals: {signals_found}")
    print(f"  발생률: {signals_found/processed*100:.2f}%" if processed else "N/A")
    print(f"{'='*60}")
    
    engine.save_signal_log()
    
    return engine


def analyze_raw_signals(log_path: str = None):
    """무판단 리포트 생성"""
    if log_path is None:
        log_path = os.path.join(os.path.dirname(__file__), 'opa_signal_raw.jsonl')
    
    if not os.path.exists(log_path):
        print(f"[ERROR] 로그 파일 없음: {log_path}")
        return
    
    signals = []
    with open(log_path, 'r') as f:
        for line in f:
            if line.strip():
                signals.append(json.loads(line))
    
    if not signals:
        print("[ERROR] 신호 데이터 없음")
        return
    
    print(f"\n{'='*60}")
    print(f"OPA_SIGNAL 무판단 리포트 v1.0")
    print(f"N = {len(signals)}")
    print(f"{'='*60}")
    
    long_count = sum(1 for s in signals if s['direction'] == 'LONG')
    short_count = sum(1 for s in signals if s['direction'] == 'SHORT')
    
    print(f"\n[방향 분포]")
    print(f"  LONG:  {long_count} ({long_count/len(signals)*100:.1f}%)")
    print(f"  SHORT: {short_count} ({short_count/len(signals)*100:.1f}%)")
    
    rth_count = sum(1 for s in signals if s.get('session') == 'RTH')
    eth_count = sum(1 for s in signals if s.get('session') == 'ETH')
    
    print(f"\n[세션 분포]")
    print(f"  RTH: {rth_count} ({rth_count/len(signals)*100:.1f}%)")
    print(f"  ETH: {eth_count} ({eth_count/len(signals)*100:.1f}%)")
    
    avg_deltas = [s['avg_delta'] for s in signals]
    delta_changes = [s['delta_change'] for s in signals]
    channel_pcts = [s['channel_pct'] for s in signals]
    
    print(f"\n[avg_delta 분포]")
    print(f"  min:  {min(avg_deltas):.4f}")
    print(f"  max:  {max(avg_deltas):.4f}")
    print(f"  mean: {sum(avg_deltas)/len(avg_deltas):.4f}")
    
    print(f"\n[delta_change 분포]")
    print(f"  min:  {min(delta_changes):.4f}")
    print(f"  max:  {max(delta_changes):.4f}")
    print(f"  mean: {sum(delta_changes)/len(delta_changes):.4f}")
    
    print(f"\n[channel_pct 분포]")
    low = sum(1 for c in channel_pcts if c < 20)
    mid = sum(1 for c in channel_pcts if 20 <= c <= 80)
    high = sum(1 for c in channel_pcts if c > 80)
    print(f"  저점권(<20%): {low} ({low/len(signals)*100:.1f}%)")
    print(f"  중간(20-80%): {mid} ({mid/len(signals)*100:.1f}%)")
    print(f"  고점권(>80%): {high} ({high/len(signals)*100:.1f}%)")
    
    print(f"\n{'='*60}")
    print(f"[가드레일] ENTRY/TP/SL/수익 단어 금지 - 센서 물리학만")
    print(f"{'='*60}")
    
    return signals


if __name__ == "__main__":
    csv_path = "../../../attached_assets/chart_data_new/latest_chart.csv"
    
    if not os.path.exists(csv_path):
        csv_path = "attached_assets/chart_data_new/latest_chart.csv"
    
    print(f"[REPLAY] 데이터 경로: {csv_path}")
    
    engine = replay_candles(csv_path)
    
    analyze_raw_signals()
