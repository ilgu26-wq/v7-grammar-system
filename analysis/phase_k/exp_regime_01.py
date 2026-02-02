"""
EXP-REGIME-01: Conditional Direction Collapse
=============================================

가설:
  Storm-IN에서 방향 분포는 Regime에 조건부로 붕괴된다
  
  P(Direction | Storm-IN) → 불안정
  P(Direction | Storm-IN, Regime) → 안정

설계:
  1. Storm-IN 고정
  2. Regime = HTF Trend (30분봉 기준)
  3. 비교: Regime=UP vs Regime=DOWN에서의 방향 분포
"""

import json
import os
import sys
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import (
    load_signals,
    classify_storm_coordinate,
)


def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df = df.drop_duplicates(subset=['time'], keep='first')
    df = df.set_index('time').sort_index()
    return df


def get_htf_regime(chart_df: pd.DataFrame, ts: str, lookback: int = 30) -> str:
    """
    HTF Trend Regime 계산 (30분 = 30바 MA 방향)
    """
    try:
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        
        if idx < lookback:
            return 'UNKNOWN'
        
        window = chart_df.iloc[idx-lookback:idx]
        
        if len(window) < lookback:
            return 'UNKNOWN'
        
        start_price = window['close'].iloc[0]
        end_price = window['close'].iloc[-1]
        
        diff = end_price - start_price
        threshold = 10  # 10포인트 이상 변화시
        
        if diff > threshold:
            return 'UP'
        elif diff < -threshold:
            return 'DOWN'
        else:
            return 'FLAT'
    except:
        return 'UNKNOWN'


def get_direction_from_chart(chart_df: pd.DataFrame, 
                              entry_ts: str, 
                              entry_price: float,
                              lookahead: int = 5) -> Optional[str]:
    """Bar1 이후 N bars의 가격 변화로 방향 판정"""
    try:
        ts = pd.to_datetime(entry_ts)
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        
        idx = chart_df.index.get_indexer([ts], method='nearest')[0]
        
        if idx < 0 or idx + lookahead >= len(chart_df):
            return None
        
        future = chart_df.iloc[idx+1:idx+1+lookahead]
        
        if len(future) < lookahead:
            return None
        
        max_up = future['high'].max() - entry_price
        max_down = entry_price - future['low'].min()
        
        if max_up > max_down and max_up > 5:
            return 'UP'
        elif max_down > max_up and max_down > 5:
            return 'DOWN'
        else:
            return 'NEUTRAL'
    except:
        return None


def calc_skew(directions: List[str]) -> float:
    up = sum(1 for d in directions if d == 'UP')
    down = sum(1 for d in directions if d == 'DOWN')
    total = up + down
    if total == 0:
        return 0
    return (up / total - 0.5) * 200


def run_exp_regime_01():
    """EXP-REGIME-01 실행"""
    print("="*70)
    print("EXP-REGIME-01: Conditional Direction Collapse")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\n가설: Storm-IN에서 방향 분포는 Regime에 조건부로 안정된다")
    print("-"*70)
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    print(f"Total signals: {len(signals)}")
    print(f"Chart data: {len(chart_df)} bars ({chart_start} to {chart_end})")
    
    qualified = [s for s in signals 
                 if classify_storm_coordinate(s) == "STORM_IN"
                 and s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.3]
    
    print(f"Storm-IN qualified: {len(qualified)}")
    
    data = []
    
    for s in qualified:
        ts = s.get('ts')
        entry_price = s.get('entry_price')
        
        if not ts or not entry_price:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        direction = get_direction_from_chart(chart_df, ts, entry_price)
        regime = get_htf_regime(chart_df, ts)
        
        if direction and regime != 'UNKNOWN':
            data.append({
                'ts': ts,
                'direction': direction,
                'regime': regime
            })
    
    print(f"Matched with chart & regime: {len(data)}")
    
    if len(data) < 30:
        print("\n⚠️ Insufficient data")
        return None
    
    print("\n" + "="*70)
    print("REGIME-CONDITIONAL DIRECTION ANALYSIS")
    print("="*70)
    
    all_dirs = [d['direction'] for d in data if d['direction'] != 'NEUTRAL']
    overall_skew = calc_skew(all_dirs)
    
    print(f"\n전체 Storm-IN (Regime 무시):")
    print(f"  N = {len(all_dirs)}, Skew = {overall_skew:+.1f}pp")
    
    regime_up_dirs = [d['direction'] for d in data 
                      if d['regime'] == 'UP' and d['direction'] != 'NEUTRAL']
    regime_down_dirs = [d['direction'] for d in data 
                        if d['regime'] == 'DOWN' and d['direction'] != 'NEUTRAL']
    regime_flat_dirs = [d['direction'] for d in data 
                        if d['regime'] == 'FLAT' and d['direction'] != 'NEUTRAL']
    
    up_skew = calc_skew(regime_up_dirs) if regime_up_dirs else 0
    down_skew = calc_skew(regime_down_dirs) if regime_down_dirs else 0
    flat_skew = calc_skew(regime_flat_dirs) if regime_flat_dirs else 0
    
    print(f"\nRegime=UP일 때:")
    print(f"  N = {len(regime_up_dirs)}, Skew = {up_skew:+.1f}pp")
    up_count = sum(1 for d in regime_up_dirs if d == 'UP')
    down_count = sum(1 for d in regime_up_dirs if d == 'DOWN')
    print(f"  UP: {up_count}, DOWN: {down_count}")
    
    print(f"\nRegime=DOWN일 때:")
    print(f"  N = {len(regime_down_dirs)}, Skew = {down_skew:+.1f}pp")
    up_count = sum(1 for d in regime_down_dirs if d == 'UP')
    down_count = sum(1 for d in regime_down_dirs if d == 'DOWN')
    print(f"  UP: {up_count}, DOWN: {down_count}")
    
    print(f"\nRegime=FLAT일 때:")
    print(f"  N = {len(regime_flat_dirs)}, Skew = {flat_skew:+.1f}pp")
    
    print("\n" + "="*70)
    print("VERDICT")
    print("="*70)
    
    h1_up = len(regime_up_dirs) >= 10 and up_skew >= 15
    h1_down = len(regime_down_dirs) >= 10 and down_skew <= -15
    
    print(f"\nH1 조건 검사:")
    print(f"  Regime=UP → UP Skew ≥ +15pp: {up_skew:+.1f}pp {'✅' if h1_up else '❌'}")
    print(f"  Regime=DOWN → DOWN Skew ≤ -15pp: {down_skew:+.1f}pp {'✅' if h1_down else '❌'}")
    
    if h1_up and h1_down:
        verdict = "H1 ACCEPTED"
        interpretation = """
Storm-IN에서 방향 분포는 Regime 조건부로 안정된다.

→ Regime=UP일 때 → UP 방향 우세
→ Regime=DOWN일 때 → DOWN 방향 우세

결론:
  [Regime] → 방향 부호 결정
      ↓
  [Storm-IN] → 비대칭 분포 활성화
      ↓
  [미시 플래그] → 방향 강조/가속
"""
    elif h1_up or h1_down:
        verdict = "H1 PARTIAL"
        interpretation = f"""
한 방향에서만 안정됨:
  Regime=UP 안정: {'✅' if h1_up else '❌'}
  Regime=DOWN 안정: {'✅' if h1_down else '❌'}

→ 비대칭 대칭성 불완전
"""
    else:
        verdict = "H0 RETAINED"
        interpretation = """
조건부에서도 Skew 불안정.

→ Regime 정의가 부적절하거나
→ 더 상위 차원 변수 필요
"""
    
    print(f"\nVerdict: {verdict}")
    print(interpretation)
    
    result = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_REGIME_01',
        'matched_count': len(data),
        'overall_skew': overall_skew,
        'regime_analysis': {
            'UP': {'n': len(regime_up_dirs), 'skew': up_skew},
            'DOWN': {'n': len(regime_down_dirs), 'skew': down_skew},
            'FLAT': {'n': len(regime_flat_dirs), 'skew': flat_skew}
        },
        'h1_up_pass': h1_up,
        'h1_down_pass': h1_down,
        'verdict': verdict
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/exp_regime_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return result


if __name__ == "__main__":
    run_exp_regime_01()
