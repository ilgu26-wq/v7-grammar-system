"""
Phase J-C′ — DC AXIS COMPARISON TEST
=====================================

목적: "Alpha가 특정 환경에서만 유효하다"는 사실이 DC 축에서도 반복되는가?

비교 축: DC Regime (DC_BEARISH / DC_NEUTRAL / DC_BULLISH)

예상 결과:
- VOL과 동일한 패턴 → 지형 확정
- 부분 유사 → Alpha 조건 세분화
- 무관 → VOL이 핵심 축으로 확정

어느 쪽이 나와도 실패 없음
"""

import json
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Dict
from datetime import datetime
from collections import defaultdict
import io
import sys

sys.path.insert(0, '/home/runner/workspace/v7-grammar-system/analysis/phase_j_b')

from alpha_gated_force import AlphaGatedForceAnalyzer


def load_force_data() -> List[Dict]:
    """Force 데이터 로드"""
    force_path = '/home/runner/workspace/v7-grammar-system/experiments/force_readings.json'
    with open(force_path, 'r') as f:
        force_data = json.load(f)
    
    candles = []
    for rec in force_data:
        price = rec.get('mid_price', 0)
        if price > 0:
            force_ratio = rec.get('force_ratio_20', 1.0)
            force_value = (force_ratio - 1.0) * 100
            
            candle = {
                'time': rec['ts'],
                'open': price - 2,
                'high': price + 10,
                'low': price - 10,
                'close': price,
                'volume': 1000,
                'force_raw': force_value,
                'force_ratio': force_ratio,
                'dc_pre': rec.get('dc_pre', 0.5),
                'avg_delta': rec.get('avg_delta', 0)
            }
            candles.append(candle)
    
    return candles


def slice_by_dc(candles: List[Dict]) -> Dict[str, List[Dict]]:
    """DC 축 기준 데이터 분할"""
    slices = {
        "DC_BEARISH": [],
        "DC_NEUTRAL": [],
        "DC_BULLISH": [],
        "ALL": candles.copy()
    }
    
    for candle in candles:
        dc = candle.get('dc_pre', 0.5)
        
        if dc < 0.4:
            slices["DC_BEARISH"].append(candle)
        elif dc > 0.6:
            slices["DC_BULLISH"].append(candle)
        else:
            slices["DC_NEUTRAL"].append(candle)
    
    return slices


def analyze_slice(name: str, candles: List[Dict]) -> Dict:
    """단일 분포 구간 분석"""
    if len(candles) < 100:
        return {
            "name": name,
            "candles": len(candles),
            "sessions": 0,
            "force_created": 0,
            "force_gated": 0,
            "gate_rate": 0,
            "exit_reasons": {}
        }
    
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    analyzer = AlphaGatedForceAnalyzer(enable_alpha_gate=True)
    sessions = analyzer.analyze(candles)
    
    sys.stdout = old_stdout
    
    exit_reasons = defaultdict(int)
    for s in sessions:
        exit_reasons[s.exit_reason] += 1
    
    force_gated = sum(1 for s in sessions if s.force_gated)
    gate_rate = force_gated / len(sessions) if sessions else 0
    
    return {
        "name": name,
        "candles": len(candles),
        "sessions": len(sessions),
        "force_created": sum(1 for s in sessions if s.force_created),
        "force_gated": force_gated,
        "gate_rate": gate_rate,
        "exit_reasons": dict(exit_reasons)
    }


def compare_with_vol_results() -> Dict:
    """VOL 축 결과와 비교"""
    vol_results = {
        "VOL_LOW": 0.60,
        "VOL_MID": 0.25,
        "VOL_HIGH": 0.00
    }
    return vol_results


def run_phase_j_c_prime():
    """Phase J-C' 전체 실행"""
    print("=" * 70)
    print("PHASE J-C′ — DC AXIS COMPARISON TEST")
    print("=" * 70)
    print(f"\nAnalysis Time: {datetime.now().isoformat()}")
    print("\n목적: Alpha가 DC 축에서도 VOL과 동일한 패턴을 보이는가?")
    
    print("\n" + "=" * 70)
    print("STEP 1: LOAD AND SLICE BY DC")
    print("=" * 70)
    
    candles = load_force_data()
    print(f"Loaded {len(candles)} candles")
    
    slices = slice_by_dc(candles)
    
    print("\n📊 DC Distribution:")
    for name, data in slices.items():
        pct = len(data) / len(candles) * 100
        print(f"  {name}: {len(data)} candles ({pct:.1f}%)")
    
    print("\n" + "=" * 70)
    print("STEP 2: ANALYZE EACH DC SLICE")
    print("=" * 70)
    
    dc_results = {}
    for name, slice_candles in slices.items():
        print(f"\nAnalyzing {name}...")
        result = analyze_slice(name, slice_candles)
        dc_results[name] = result
        print(f"  Sessions: {result['sessions']}, Gated: {result['force_gated']}, Rate: {result['gate_rate']*100:.1f}%")
    
    print("\n" + "=" * 70)
    print("STEP 3: COMPARE WITH VOL RESULTS")
    print("=" * 70)
    
    vol_results = compare_with_vol_results()
    
    print("\n📊 Gate Rate Comparison:")
    print(f"{'Axis':<15} {'Slice':<15} {'Gate Rate':>10}")
    print("-" * 40)
    
    for name, rate in vol_results.items():
        print(f"{'VOL':<15} {name:<15} {rate*100:>10.1f}%")
    
    print("-" * 40)
    
    for name, result in dc_results.items():
        if name != "ALL":
            print(f"{'DC':<15} {name:<15} {result['gate_rate']*100:>10.1f}%")
    
    print("\n" + "=" * 70)
    print("STEP 4: PATTERN ANALYSIS")
    print("=" * 70)
    
    vol_spread = 0.60 - 0.00
    
    dc_rates = [r['gate_rate'] for name, r in dc_results.items() if name != "ALL" and r['sessions'] > 0]
    dc_spread = max(dc_rates) - min(dc_rates) if dc_rates else 0
    
    print(f"\n📊 Spread Analysis:")
    print(f"  VOL Spread: {vol_spread*100:.1f}%")
    print(f"  DC Spread: {dc_spread*100:.1f}%")
    
    if dc_spread < 0.2:
        pattern = "DC_UNIFORM"
        interpretation = "Alpha Gate는 DC와 무관 → VOL이 핵심 축"
    elif dc_spread > 0.4:
        pattern = "DC_SIMILAR"
        interpretation = "Alpha Gate가 DC에서도 차별화 → 다축 조건 필요"
    else:
        pattern = "DC_PARTIAL"
        interpretation = "DC 부분 유사 → VOL 우선, DC 보조"
    
    print(f"\n🎯 Pattern: {pattern}")
    print(f"   해석: {interpretation}")
    
    final_report = {
        "analysis_time": datetime.now().isoformat(),
        "phase": "J-C'",
        "purpose": "DC AXIS COMPARISON TEST",
        "dc_results": dc_results,
        "vol_reference": vol_results,
        "spreads": {
            "vol": vol_spread,
            "dc": dc_spread
        },
        "pattern": pattern,
        "interpretation": interpretation,
        "conclusion": generate_conclusion(pattern, dc_spread, vol_spread)
    }
    
    print_final_summary(final_report)
    
    report_path = '/tmp/phase_j_c_prime_report.json'
    with open(report_path, 'w') as f:
        json.dump(final_report, f, indent=2, default=str)
    
    print(f"\n📄 Report saved to: {report_path}")
    
    return final_report


def generate_conclusion(pattern: str, dc_spread: float, vol_spread: float) -> str:
    if pattern == "DC_UNIFORM":
        return """
✅ DC 축은 Alpha Gate와 무관

VOL이 Alpha의 핵심 조건축으로 확정됨:
- VOL_LOW/MID: Alpha 활성
- VOL_HIGH: Alpha 비활성

DC는 Alpha 조건에 영향 없음
→ 단일 축 조건부 Gate 확정
→ 프로덕션 설계 단순화 가능
"""
    elif pattern == "DC_SIMILAR":
        return """
⚠️ DC 축도 Alpha Gate에 영향

다축 조건 필요:
- VOL + DC 조합 조건 검토
- 조건 복잡도 증가

추가 분석 필요
"""
    else:
        return """
🔶 DC 축 부분 유사

권장 전략:
- VOL을 1차 조건으로 유지
- DC는 보조 지표로 고려
- 단순성 우선 → VOL 단독 사용 권장
"""


def print_final_summary(report: Dict):
    """최종 요약"""
    print("\n" + "=" * 70)
    print("PHASE J-C′ — FINAL SUMMARY")
    print("=" * 70)
    
    print(f"\n📊 DC Gate Rates:")
    for name, result in report['dc_results'].items():
        if name != "ALL":
            print(f"  {name}: {result['gate_rate']*100:.1f}%")
    
    print(f"\n📊 Spread Comparison:")
    print(f"  VOL Spread: {report['spreads']['vol']*100:.1f}%")
    print(f"  DC Spread: {report['spreads']['dc']*100:.1f}%")
    
    print(f"\n🎯 Pattern: {report['pattern']}")
    print(report['conclusion'])


if __name__ == "__main__":
    run_phase_j_c_prime()
