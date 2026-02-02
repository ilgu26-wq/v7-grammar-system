"""
EXP-GRAMMAR-ROBUST-01: Grammar Robustness & Distortion Suite
=============================================================

실험 구성:
  1. RAW-COMP: 원본 vs 문법 비교
  2. DIST-1: 문장 구조 셔플
  3. DIST-2: 축 제거 Ablation
  4. DIST-3: 시간 왜곡

목적: 문법이 데이터 분포·시간·구조를 비틀어도 살아남는지 검증
"""

import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import random

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import load_signals, classify_storm_coordinate


def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df = df.drop_duplicates(subset=['time'], keep='first')
    df = df.set_index('time').sort_index()
    return df


def calc_revisit_anchor(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> bool:
    if idx < lookback:
        return False
    window = chart_df.iloc[idx-lookback:idx]
    current = chart_df.iloc[idx]
    prev_high = window['high'].max()
    prev_low = window['low'].min()
    return current['high'] >= prev_high * 0.99 or current['low'] <= prev_low * 1.01


def calc_e_dir(chart_df: pd.DataFrame, idx: int) -> str:
    if idx < 1:
        return 'DOWN'
    current = chart_df.iloc[idx]
    delta = current['close'] - current['open']
    return 'UP' if delta > 0 else 'DOWN'


def calc_t_commit(chart_df: pd.DataFrame, idx: int, threshold: float = 15) -> str:
    if idx + 15 >= len(chart_df):
        return 'DELAYED'
    entry = chart_df.iloc[idx]['close']
    for i in range(1, 16):
        bar = chart_df.iloc[idx + i]
        if abs(bar['high'] - entry) >= threshold or abs(entry - bar['low']) >= threshold:
            return 'FAST' if i <= 5 else 'DELAYED'
    return 'DELAYED'


def calc_path(chart_df: pd.DataFrame, idx: int, window: int = 10) -> str:
    if idx + window >= len(chart_df):
        return 'STAIR'
    entry = chart_df.iloc[idx]['close']
    bars = chart_df.iloc[idx+1:idx+1+window]
    prices = [bars.iloc[i]['close'] - entry for i in range(len(bars))]
    max_drawdown = 0
    peak = prices[0]
    for p in prices:
        if p > peak:
            peak = p
        max_drawdown = max(max_drawdown, abs(peak - p))
    return 'V' if max_drawdown >= 10 else 'STAIR'


def calc_e_resp(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> str:
    if idx < lookback:
        return 'RELEASE'
    window = chart_df.iloc[idx-lookback:idx]
    consecutive_fails = 0
    for i in range(1, len(window)):
        prev_range = window['high'].iloc[i-1] - window['low'].iloc[i-1]
        if prev_range < 1:
            continue
        current_close = window['close'].iloc[i]
        prev_low = window['low'].iloc[i-1]
        recovery_threshold = prev_low + prev_range * 0.4
        if current_close < recovery_threshold:
            consecutive_fails += 1
        else:
            consecutive_fails = 0
    rfc = consecutive_fails >= 1
    recent = window.iloc[-lookback//2:]
    past = window.iloc[:lookback//2]
    recent_avg = (recent['high'] - recent['low']).mean()
    past_avg = (past['high'] - past['low']).mean()
    eda = recent_avg / past_avg if past_avg > 0.1 else 1.0
    if rfc and eda <= 0.85:
        return 'ABSORB'
    return 'RELEASE'


def calc_daa(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> bool:
    if idx < lookback:
        return False
    window = chart_df.iloc[idx-lookback:idx]
    consecutive_fails = 0
    for i in range(1, len(window)):
        prev_range = window['high'].iloc[i-1] - window['low'].iloc[i-1]
        if prev_range < 1:
            continue
        current_close = window['close'].iloc[i]
        prev_low = window['low'].iloc[i-1]
        recovery_threshold = prev_low + prev_range * 0.4
        if current_close < recovery_threshold:
            consecutive_fails += 1
        else:
            consecutive_fails = 0
    rfc = consecutive_fails >= 1
    recent = window.iloc[-lookback//2:]
    past = window.iloc[:lookback//2]
    recent_range = recent['high'].max() - recent['low'].min()
    past_range = past['high'].max() - past['low'].min()
    bcr = recent_range / past_range if past_range > 0.5 else 1.0
    bcr_ok = bcr <= 0.8
    recent_avg = (recent['high'] - recent['low']).mean()
    past_avg = (past['high'] - past['low']).mean()
    eda = recent_avg / past_avg if past_avg > 0.1 else 1.0
    eda_ok = eda <= 0.85
    return rfc and bcr_ok and eda_ok


def analyze_session(chart_df: pd.DataFrame, idx: int, 
                     session_length: int = 30, absorb_k: int = 3) -> Dict:
    if idx + session_length >= len(chart_df):
        return None
    
    result = {
        'absorb_reached': False,
        'daa_approached': False,
        't_e_resp_flip': None,
        't_absorb': None,
        'gap': None,
        'mae': 0
    }
    
    entry = chart_df.iloc[idx]['close']
    absorb_count = 0
    
    for i in range(1, session_length + 1):
        bar_idx = idx + i
        if bar_idx >= len(chart_df):
            break
        
        bar = chart_df.iloc[bar_idx]
        result['mae'] = max(result['mae'], entry - bar['low'])
        
        e_resp = calc_e_resp(chart_df, bar_idx)
        
        if result['t_e_resp_flip'] is None and e_resp == 'RELEASE':
            result['t_e_resp_flip'] = i
        
        if e_resp == 'ABSORB':
            absorb_count += 1
            if absorb_count >= absorb_k and result['t_absorb'] is None:
                result['t_absorb'] = i
                result['absorb_reached'] = True
        else:
            absorb_count = 0
        
        if calc_daa(chart_df, bar_idx):
            result['daa_approached'] = True
    
    if result['t_e_resp_flip'] and result['t_absorb']:
        result['gap'] = result['t_absorb'] - result['t_e_resp_flip']
    
    return result


def run_raw_comp_experiment(signals: List, chart_df: pd.DataFrame) -> Dict:
    """EXP-GRAMMAR-RAW-COMP-01: 원본 vs 문법 비교"""
    print("\n" + "="*70)
    print("EXP-GRAMMAR-RAW-COMP-01: Raw vs Grammar Comparison")
    print("="*70)
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    storm_in_signals = [s for s in signals if classify_storm_coordinate(s) == "STORM_IN"]
    
    raw_sessions = []
    grammar_sessions = []
    
    for s in storm_in_signals:
        ts = s.get('ts')
        if not ts:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        try:
            idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        except:
            continue
        
        if idx < 20 or idx + 35 >= len(chart_df):
            continue
        
        session = analyze_session(chart_df, idx)
        if session is None:
            continue
        
        raw_sessions.append(session)
        
        if calc_revisit_anchor(chart_df, idx):
            grammar_sessions.append(session)
    
    raw_absorb = sum(1 for s in raw_sessions if s['absorb_reached']) / len(raw_sessions) * 100
    raw_daa = sum(1 for s in raw_sessions if s['daa_approached']) / len(raw_sessions) * 100
    raw_mae = np.mean([s['mae'] for s in raw_sessions])
    
    gram_absorb = sum(1 for s in grammar_sessions if s['absorb_reached']) / len(grammar_sessions) * 100
    gram_daa = sum(1 for s in grammar_sessions if s['daa_approached']) / len(grammar_sessions) * 100
    gram_mae = np.mean([s['mae'] for s in grammar_sessions])
    
    print(f"\n| Metric | Raw (N={len(raw_sessions)}) | Grammar (N={len(grammar_sessions)}) | Δ |")
    print("|--------|-----|---------|---|")
    print(f"| P(Absorb) | {raw_absorb:.1f}% | {gram_absorb:.1f}% | {gram_absorb - raw_absorb:+.1f}pp |")
    print(f"| P(DAA) | {raw_daa:.1f}% | {gram_daa:.1f}% | {gram_daa - raw_daa:+.1f}pp |")
    print(f"| Avg MAE | {raw_mae:.1f}pt | {gram_mae:.1f}pt | {gram_mae - raw_mae:+.1f}pt |")
    
    grammar_improves = (raw_absorb - gram_absorb >= 10) or (raw_daa - gram_daa >= 10)
    print(f"\nGrammar adds structural info: {'✅ YES' if grammar_improves else '⚠️ MARGINAL'}")
    
    return {
        'raw_n': len(raw_sessions),
        'grammar_n': len(grammar_sessions),
        'raw_absorb': raw_absorb,
        'grammar_absorb': gram_absorb,
        'raw_daa': raw_daa,
        'grammar_daa': gram_daa,
        'pass': grammar_improves
    }


def run_shuffle_experiment(signals: List, chart_df: pd.DataFrame) -> Dict:
    """DIST-1: 문장 구조 셔플"""
    print("\n" + "="*70)
    print("DIST-1: Sentence Structure Shuffle")
    print("="*70)
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    storm_in_signals = [s for s in signals if classify_storm_coordinate(s) == "STORM_IN"]
    
    original_data = []
    
    for s in storm_in_signals:
        ts = s.get('ts')
        if not ts:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        try:
            idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        except:
            continue
        
        if idx < 20 or idx + 35 >= len(chart_df):
            continue
        
        if not calc_revisit_anchor(chart_df, idx):
            continue
        
        e_dir = calc_e_dir(chart_df, idx)
        t_commit = calc_t_commit(chart_df, idx)
        path = calc_path(chart_df, idx)
        
        session = analyze_session(chart_df, idx)
        if session is None:
            continue
        
        original_data.append({
            'idx': idx,
            'e_dir': e_dir,
            't_commit': t_commit,
            'path': path,
            'session': session
        })
    
    sentence_groups = defaultdict(list)
    for d in original_data:
        sent = f"⟨{d['e_dir']},{d['t_commit']},{d['path']}⟩"
        sentence_groups[sent].append(d)
    
    original_flip_before = []
    for sent, data in sentence_groups.items():
        if len(data) < 5:
            continue
        flip_before = sum(1 for d in data 
                         if d['session']['t_e_resp_flip'] and d['session']['t_absorb']
                         and d['session']['t_e_resp_flip'] < d['session']['t_absorb'])
        total = sum(1 for d in data if d['session']['t_e_resp_flip'] and d['session']['t_absorb'])
        if total > 0:
            original_flip_before.append(flip_before / total * 100)
    
    avg_original = np.mean(original_flip_before) if original_flip_before else 0
    
    shuffled_labels = []
    for d in original_data:
        shuffled_labels.append({
            'e_dir': d['e_dir'],
            't_commit': d['t_commit'],
            'path': d['path']
        })
    random.shuffle(shuffled_labels)
    
    for i, d in enumerate(original_data):
        d['shuffled_e_dir'] = shuffled_labels[i]['e_dir']
        d['shuffled_t_commit'] = shuffled_labels[i]['t_commit']
        d['shuffled_path'] = shuffled_labels[i]['path']
    
    shuffled_groups = defaultdict(list)
    for d in original_data:
        sent = f"⟨{d['shuffled_e_dir']},{d['shuffled_t_commit']},{d['shuffled_path']}⟩"
        shuffled_groups[sent].append(d)
    
    shuffled_flip_before = []
    for sent, data in shuffled_groups.items():
        if len(data) < 5:
            continue
        flip_before = sum(1 for d in data 
                         if d['session']['t_e_resp_flip'] and d['session']['t_absorb']
                         and d['session']['t_e_resp_flip'] < d['session']['t_absorb'])
        total = sum(1 for d in data if d['session']['t_e_resp_flip'] and d['session']['t_absorb'])
        if total > 0:
            shuffled_flip_before.append(flip_before / total * 100)
    
    avg_shuffled = np.mean(shuffled_flip_before) if shuffled_flip_before else 0
    
    original_variance = np.std(original_flip_before) if len(original_flip_before) > 1 else 0
    shuffled_variance = np.std(shuffled_flip_before) if len(shuffled_flip_before) > 1 else 0
    
    print(f"\n| Condition | Avg P(Flip<Absorb) | Std Dev |")
    print("|-----------|-------------------|---------|")
    print(f"| Original | {avg_original:.1f}% | {original_variance:.1f} |")
    print(f"| Shuffled | {avg_shuffled:.1f}% | {shuffled_variance:.1f} |")
    print(f"| Δ | {avg_shuffled - avg_original:+.1f}pp | {shuffled_variance - original_variance:+.1f} |")
    
    structure_essential = shuffled_variance > original_variance * 1.5 or avg_original - avg_shuffled >= 10
    print(f"\nGrammar structure essential: {'✅ YES' if structure_essential else '⚠️ NO'}")
    
    return {
        'original_avg': avg_original,
        'shuffled_avg': avg_shuffled,
        'original_std': original_variance,
        'shuffled_std': shuffled_variance,
        'pass': structure_essential
    }


def run_ablation_experiment(signals: List, chart_df: pd.DataFrame) -> Dict:
    """DIST-2: 축 제거 Ablation"""
    print("\n" + "="*70)
    print("DIST-2: Axis Ablation Experiment")
    print("="*70)
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    storm_in_signals = [s for s in signals if classify_storm_coordinate(s) == "STORM_IN"]
    
    data = []
    
    for s in storm_in_signals:
        ts = s.get('ts')
        if not ts:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        try:
            idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        except:
            continue
        
        if idx < 20 or idx + 35 >= len(chart_df):
            continue
        
        if not calc_revisit_anchor(chart_df, idx):
            continue
        
        e_dir = calc_e_dir(chart_df, idx)
        t_commit = calc_t_commit(chart_df, idx)
        path = calc_path(chart_df, idx)
        
        session = analyze_session(chart_df, idx)
        if session is None:
            continue
        
        data.append({
            'e_dir': e_dir,
            't_commit': t_commit,
            'path': path,
            'session': session
        })
    
    def calc_terminal_consistency(data_list, group_key_fn):
        groups = defaultdict(list)
        for d in data_list:
            key = group_key_fn(d)
            groups[key].append(d)
        
        flip_rates = []
        for key, group in groups.items():
            if len(group) < 5:
                continue
            flip_before = sum(1 for d in group 
                             if d['session']['t_e_resp_flip'] and d['session']['t_absorb']
                             and d['session']['t_e_resp_flip'] < d['session']['t_absorb'])
            total = sum(1 for d in group if d['session']['t_e_resp_flip'] and d['session']['t_absorb'])
            if total > 0:
                flip_rates.append(flip_before / total * 100)
        
        return np.mean(flip_rates) if flip_rates else 0, np.std(flip_rates) if len(flip_rates) > 1 else 0
    
    full_avg, full_std = calc_terminal_consistency(
        data, lambda d: f"⟨{d['e_dir']},{d['t_commit']},{d['path']}⟩")
    
    no_edir_avg, no_edir_std = calc_terminal_consistency(
        data, lambda d: f"⟨*,{d['t_commit']},{d['path']}⟩")
    
    no_tcommit_avg, no_tcommit_std = calc_terminal_consistency(
        data, lambda d: f"⟨{d['e_dir']},*,{d['path']}⟩")
    
    no_path_avg, no_path_std = calc_terminal_consistency(
        data, lambda d: f"⟨{d['e_dir']},{d['t_commit']},*⟩")
    
    print(f"\n| Variant | Avg P(Flip<Absorb) | Std Dev |")
    print("|---------|-------------------|---------|")
    print(f"| Full Grammar | {full_avg:.1f}% | {full_std:.1f} |")
    print(f"| -E_DIR | {no_edir_avg:.1f}% | {no_edir_std:.1f} |")
    print(f"| -T_COMMIT | {no_tcommit_avg:.1f}% | {no_tcommit_std:.1f} |")
    print(f"| -PATH | {no_path_avg:.1f}% | {no_path_std:.1f} |")
    
    axes_essential = []
    if no_edir_std > full_std * 1.3 or abs(no_edir_avg - full_avg) > 5:
        axes_essential.append('E_DIR')
    if no_tcommit_std > full_std * 1.3 or abs(no_tcommit_avg - full_avg) > 5:
        axes_essential.append('T_COMMIT')
    if no_path_std > full_std * 1.3 or abs(no_path_avg - full_avg) > 5:
        axes_essential.append('PATH')
    
    print(f"\nEssential axes: {axes_essential if axes_essential else 'None (Grammar may be overfit)'}")
    
    return {
        'full_avg': full_avg,
        'no_edir_avg': no_edir_avg,
        'no_tcommit_avg': no_tcommit_avg,
        'no_path_avg': no_path_avg,
        'essential_axes': axes_essential,
        'pass': len(axes_essential) >= 1
    }


def run_timing_distortion_experiment(signals: List, chart_df: pd.DataFrame) -> Dict:
    """DIST-3: 시간 왜곡"""
    print("\n" + "="*70)
    print("DIST-3: Timing Distortion Experiment")
    print("="*70)
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    storm_in_signals = [s for s in signals if classify_storm_coordinate(s) == "STORM_IN"]
    
    data = []
    
    for s in storm_in_signals:
        ts = s.get('ts')
        if not ts:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        try:
            idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        except:
            continue
        
        if idx < 20 or idx + 35 >= len(chart_df):
            continue
        
        if not calc_revisit_anchor(chart_df, idx):
            continue
        
        session = analyze_session(chart_df, idx)
        if session is None:
            continue
        
        if session['t_e_resp_flip'] and session['t_absorb']:
            data.append(session)
    
    original_flip_before = sum(1 for d in data if d['t_e_resp_flip'] < d['t_absorb'])
    original_rate = original_flip_before / len(data) * 100 if data else 0
    
    results = {'original': original_rate}
    
    for k in [3, 5]:
        distorted_flip_before = 0
        for d in data:
            distorted_flip = d['t_e_resp_flip'] + random.randint(-k, k)
            if distorted_flip < d['t_absorb']:
                distorted_flip_before += 1
        distorted_rate = distorted_flip_before / len(data) * 100 if data else 0
        results[f'k={k}'] = distorted_rate
    
    print(f"\n| Condition | P(Flip<Absorb) |")
    print("|-----------|---------------|")
    print(f"| Original | {results['original']:.1f}% |")
    print(f"| Distorted k=3 | {results['k=3']:.1f}% |")
    print(f"| Distorted k=5 | {results['k=5']:.1f}% |")
    
    robust = results['k=5'] >= 80
    print(f"\nGrammar is state-based (timing-robust): {'✅ YES' if robust else '⚠️ NO'}")
    
    return {
        'original': results['original'],
        'k3': results['k=3'],
        'k5': results['k=5'],
        'pass': robust
    }


def run_exp_grammar_robust_01():
    """EXP-GRAMMAR-ROBUST-01 전체 실행"""
    print("="*70)
    print("EXP-GRAMMAR-ROBUST-01: Grammar Robustness & Distortion Suite")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    raw_comp = run_raw_comp_experiment(signals, chart_df)
    shuffle = run_shuffle_experiment(signals, chart_df)
    ablation = run_ablation_experiment(signals, chart_df)
    timing = run_timing_distortion_experiment(signals, chart_df)
    
    print("\n" + "="*70)
    print("FINAL ROBUSTNESS VERDICT")
    print("="*70)
    
    tests = [
        ('RAW-COMP (Grammar adds info)', raw_comp['pass']),
        ('DIST-1 (Structure essential)', shuffle['pass']),
        ('DIST-2 (Axes essential)', ablation['pass']),
        ('DIST-3 (Timing robust)', timing['pass'])
    ]
    
    passed = sum(1 for _, p in tests if p)
    
    print("\n| Test | Result |")
    print("|------|--------|")
    for name, result in tests:
        print(f"| {name} | {'✅ PASS' if result else '❌ FAIL'} |")
    
    print(f"\nTotal: {passed}/4 passed")
    
    if passed >= 4:
        verdict = "✅ GRAMMAR LOCK - All tests passed"
    elif passed >= 3:
        verdict = "⚠️ GRAMMAR VALID - Most tests passed"
    else:
        verdict = "❌ GRAMMAR OVERFIT - Needs refinement"
    
    print(f"\n{verdict}")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_GRAMMAR_ROBUST_01',
        'raw_comp': raw_comp,
        'shuffle': shuffle,
        'ablation': ablation,
        'timing': timing,
        'passed': passed,
        'verdict': verdict
    }
    
    output_path = 'v7-grammar-system/analysis/phase_o/exp_grammar_robust_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_grammar_robust_01()
