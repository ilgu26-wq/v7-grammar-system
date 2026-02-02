"""
STRUCTURE CLASSIFICATION PIPELINE v1.0
Loaders - 소스별 데이터 로딩
"""
import json
import csv
import os

def bucketize(x):
    if x is None:
        return "N/A"
    try:
        x = float(x)
    except:
        return "N/A"
    if x < 0.5:
        return "LOW"
    if x < 1.0:
        return "MID"
    if x < 1.5:
        return "HIGH"
    return "EXTREME"

def infer_stb(t):
    """
    v1.2: 시퀀스 기반 STB_index는 load_paper_mode에서 계산
    이 함수는 fallback으로만 사용
    """
    return t.get('STB_index_computed', 'N/A')

def load_paper_mode(json_path, window_minutes=30):
    """
    v1.2: 시간 간격 기반 STB 시퀀스 계산
    """
    from datetime import datetime
    from collections import defaultdict
    
    with open(json_path) as f:
        data = json.load(f)
    
    trades = [t for t in data.get('trades', []) if t.get('result') is not None]
    
    def parse_time(t):
        entry_time = t.get('entry_time', '')
        try:
            return datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
        except:
            return None
    
    for t in trades:
        t['dt'] = parse_time(t)
    
    trades = [t for t in trades if t.get('dt')]
    trades.sort(key=lambda x: x['dt'])
    
    seq_id = 0
    last_time = None
    last_direction = None
    
    for t in trades:
        direction = t.get('direction')
        current_time = t['dt']
        
        if last_time is None:
            seq_id = 1
        else:
            dt_minutes = (current_time - last_time).total_seconds() / 60
            if dt_minutes > window_minutes or direction != last_direction:
                seq_id += 1
        
        t['stb_seq_id'] = seq_id
        last_time = current_time
        last_direction = direction
    
    seq_order = defaultdict(int)
    for t in trades:
        sid = t['stb_seq_id']
        t['STB_index_computed'] = 'first' if seq_order[sid] == 0 else 're-entry'
        seq_order[sid] += 1
    
    rows = []
    for t in trades:
        rows.append({
            "trade_uid": f"paper_mode::{t.get('trade_id', len(rows))}",
            "source": "paper_mode",
            "direction": t.get("direction", "SHORT"),
            "delta_bucket": bucketize(t.get("delta_at_entry")),
            "STATE": t.get("STATE"),
            "STB_index": t.get('STB_index_computed', 'N/A'),
            "theta_label": t.get("theta_label", 0),
            "signal_code": t.get("signal_code"),
            "result": "WIN" if (t.get("pnl") or 0) > 0 else "LOSS",
        })
    
    return rows

def load_csv_backtest(csv_path, source_name):
    if not os.path.exists(csv_path):
        return []
    
    rows = []
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            direction = row.get('direction', row.get('signal', 'SHORT'))
            if 'short' in str(direction).lower() or direction.startswith('S'):
                direction = 'SHORT'
            elif 'long' in str(direction).lower() or direction.startswith('L'):
                direction = 'LONG'
            else:
                direction = 'SHORT'
            
            outcome = row.get('outcome', row.get('result', row.get('is_win', '')))
            if str(outcome).lower() in ['win', 'true', '1', 'tp']:
                result = 'WIN'
            else:
                result = 'LOSS'
            
            delta = row.get('delta_at_entry', row.get('ratio', None))
            
            signal = row.get('signal', row.get('signal_type', row.get('code', None)))
            
            rows.append({
                "trade_uid": f"{source_name}::{i}",
                "source": source_name,
                "direction": direction,
                "delta_bucket": bucketize(delta),
                "STATE": None,
                "STB_index": "N/A",
                "theta_label": None,
                "signal_code": signal,
                "result": result,
            })
    
    return rows

def load_all_sources():
    all_rows = []
    
    paper_path = 'v7-grammar-system/opa/paper_mode_logs_theta.json'
    if os.path.exists(paper_path):
        rows = load_paper_mode(paper_path)
        all_rows.extend(rows)
        print(f"Loaded {len(rows)} from paper_mode")
    
    csv_sources = [
        ('backtest_results.csv', 'csv_backtest'),
        ('sps_backtest_results.csv', 'sps_backtest'),
        ('w_hunt_trades.csv', 'w_hunt'),
    ]
    
    for path, name in csv_sources:
        if os.path.exists(path):
            rows = load_csv_backtest(path, name)
            all_rows.extend(rows)
            print(f"Loaded {len(rows)} from {name}")
    
    return all_rows

if __name__ == "__main__":
    rows = load_all_sources()
    print(f"\nTotal: {len(rows)} trades loaded")
