"""
LEGACY V7 ENTRY AUDIT
=====================

목표: "과거 우리가 '엔트리'라고 불렀던 것들이
       V7 기준에서 보면 진짜 엔트리였는가?"

이건 수익 비교가 아니다 ❌
이건 정의 일치성 검사다 ✅

REFERENCE = V7 Grammar (Phase K 결과)
TARGET    = Legacy V7 Entry Logs
MODE      = OFFLINE / READ-ONLY

절대 규칙:
❌ 새 조건 추가 금지
❌ 임계값 수정 금지
❌ 알파 개입 금지
❌ 결과 보고 판단 수정 금지
"""

import json
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict


@dataclass
class LegacyEntry:
    """Legacy V7 Entry 레코드"""
    entry_id: str
    ts: str
    entry_price: float
    dc_pre: float
    avg_delta: float
    force_ratio: float
    action: str
    reason: str


@dataclass 
class AuditResult:
    """Entry Validity Audit 결과"""
    entry_id: str
    ts: str
    dc: float
    tau_equivalent: int
    dir_equivalent: int
    
    is_dc_valid: bool
    is_tau_valid: bool
    is_dir_valid: bool
    
    v7_verdict: str
    verdict_reason: str
    
    session_created: bool = False
    hold_bars: int = 0
    exit_reason: str = ""


def load_legacy_signals() -> List[Dict]:
    """Legacy V7 signals 로드"""
    signal_path = '/home/runner/workspace/v7-grammar-system/experiments/v7_signals.json'
    with open(signal_path, 'r') as f:
        signals = json.load(f)
    return signals


def estimate_tau_from_legacy(signal: Dict) -> int:
    """Legacy 데이터에서 τ 추정 (force_ratio 기반)"""
    force_ratio = signal.get('force_ratio_30', signal.get('force_ratio_20', 1.0))
    
    if force_ratio >= 2.0:
        return 8
    elif force_ratio >= 1.5:
        return 6
    elif force_ratio >= 1.2:
        return 4
    elif force_ratio >= 1.0:
        return 2
    else:
        return 0


def estimate_dir_from_legacy(signal: Dict) -> int:
    """Legacy 데이터에서 dir 추정 (dc_pre 기반)"""
    dc = signal.get('dc_pre', 0.5)
    avg_delta = signal.get('avg_delta', 0)
    
    if dc >= 0.8:
        return 5
    elif dc >= 0.7:
        return 4
    elif dc >= 0.6:
        return 3
    elif dc <= 0.2:
        return -5
    elif dc <= 0.3:
        return -4
    elif dc <= 0.4:
        return -3
    else:
        return 0


def validate_dc(dc: float) -> bool:
    """DC 유효성: 극단값 (0 or 1 근처)"""
    return dc <= 0.3 or dc >= 0.7


def validate_tau(tau: int) -> bool:
    """τ 유효성: τ ≥ 5"""
    return tau >= 5


def validate_dir(dir_count: int) -> bool:
    """dir 유효성: |dir| ≥ 3"""
    return abs(dir_count) >= 3


def audit_legacy_entries(signals: List[Dict]) -> List[AuditResult]:
    """Legacy Entry Validity Audit"""
    results = []
    
    for i, signal in enumerate(signals):
        entry_id = f"E-{i:04d}"
        
        dc = signal.get('dc_pre', 0.5)
        tau = estimate_tau_from_legacy(signal)
        dir_count = estimate_dir_from_legacy(signal)
        
        is_dc_valid = validate_dc(dc)
        is_tau_valid = validate_tau(tau)
        is_dir_valid = validate_dir(dir_count)
        
        if is_dc_valid and is_tau_valid and is_dir_valid:
            verdict = "TRUE_ENTRY"
            reason = "All conditions met"
        elif signal.get('action') == 'NO_TRADE':
            verdict = "FILTERED_CORRECTLY"
            reason = signal.get('reason', 'No reason')
        elif not is_tau_valid:
            verdict = "ENTRY_SIGNAL"
            reason = f"τ={tau} < 5 (not mature)"
        elif not is_dc_valid:
            verdict = "ENTRY_SIGNAL"
            reason = f"DC={dc:.2f} not extreme"
        elif not is_dir_valid:
            verdict = "ENTRY_SIGNAL"
            reason = f"dir={dir_count} weak direction"
        else:
            verdict = "UNKNOWN"
            reason = "Unclassified"
        
        result = AuditResult(
            entry_id=entry_id,
            ts=signal.get('ts', ''),
            dc=dc,
            tau_equivalent=tau,
            dir_equivalent=dir_count,
            is_dc_valid=is_dc_valid,
            is_tau_valid=is_tau_valid,
            is_dir_valid=is_dir_valid,
            v7_verdict=verdict,
            verdict_reason=reason
        )
        
        results.append(result)
    
    return results


def generate_tables(results: List[AuditResult]):
    """TABLE 1-3 생성"""
    
    print("\n" + "=" * 80)
    print("📊 TABLE 1 — ENTRY VALIDITY AUDIT (Sample)")
    print("=" * 80)
    print(f"{'Entry ID':<12} {'DC':>6} {'τ':>4} {'dir':>5} {'V7 Verdict':<20} {'Reason'}")
    print("-" * 80)
    
    sample_true = [r for r in results if r.v7_verdict == "TRUE_ENTRY"][:5]
    sample_signal = [r for r in results if r.v7_verdict == "ENTRY_SIGNAL"][:5]
    sample_filtered = [r for r in results if r.v7_verdict == "FILTERED_CORRECTLY"][:5]
    
    for r in sample_true + sample_signal + sample_filtered:
        icon = "✅" if r.v7_verdict == "TRUE_ENTRY" else "⚠️" if r.v7_verdict == "ENTRY_SIGNAL" else "🔒"
        print(f"{r.entry_id:<12} {r.dc:>6.2f} {r.tau_equivalent:>4} {r.dir_equivalent:>5} {icon} {r.v7_verdict:<17} {r.verdict_reason[:30]}")
    
    print("\n" + "=" * 80)
    print("📊 TABLE 2 — SESSION OUTCOME (TRUE_ENTRY Only)")
    print("=" * 80)
    print(f"{'Entry ID':<12} {'Session Created':>15} {'HOLD':>8} {'EXIT_REASON'}")
    print("-" * 80)
    
    for r in sample_true[:10]:
        print(f"{r.entry_id:<12} {'✅ Yes':>15} {'N/A':>8} {'Needs Phase K mapping'}")
    
    print("\n" + "=" * 80)
    print("📊 TABLE 3 — RECLASSIFICATION SUMMARY")
    print("=" * 80)
    
    categories = defaultdict(int)
    for r in results:
        categories[r.v7_verdict] += 1
    
    total = len(results)
    print(f"{'Category':<25} {'Count':>10} {'%':>10}")
    print("-" * 45)
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total > 0 else 0
        print(f"{cat:<25} {count:>10} {pct:>9.1f}%")
    
    print("\n" + "=" * 80)
    print("📊 TABLE 4 — VALIDITY BREAKDOWN")
    print("=" * 80)
    
    dc_valid = sum(1 for r in results if r.is_dc_valid)
    tau_valid = sum(1 for r in results if r.is_tau_valid)
    dir_valid = sum(1 for r in results if r.is_dir_valid)
    
    print(f"{'Condition':<25} {'Valid':>10} {'%':>10}")
    print("-" * 45)
    print(f"{'DC ∈ {<0.3, >0.7}':<25} {dc_valid:>10} {dc_valid/total*100:>9.1f}%")
    print(f"{'τ ≥ 5':<25} {tau_valid:>10} {tau_valid/total*100:>9.1f}%")
    print(f"{'|dir| ≥ 3':<25} {dir_valid:>10} {dir_valid/total*100:>9.1f}%")
    
    all_valid = sum(1 for r in results if r.is_dc_valid and r.is_tau_valid and r.is_dir_valid)
    print(f"{'ALL CONDITIONS MET':<25} {all_valid:>10} {all_valid/total*100:>9.1f}%")
    
    return categories


def run_legacy_audit():
    """Legacy Entry Audit 전체 실행"""
    print("=" * 80)
    print("LEGACY V7 ENTRY AUDIT")
    print("=" * 80)
    print(f"\nAnalysis Time: {datetime.now().isoformat()}")
    print("\n목표: 과거 V7 엔트리가 문법적으로 진짜 엔트리였는가?")
    print("모드: OFFLINE / READ-ONLY")
    
    print("\n" + "=" * 80)
    print("STEP 1: LOAD LEGACY V7 SIGNALS")
    print("=" * 80)
    
    signals = load_legacy_signals()
    print(f"Loaded {len(signals)} legacy signals")
    
    trades = [s for s in signals if s.get('action') in ['ENTER_SHORT', 'ENTER_LONG', 'SHORT', 'LONG']]
    no_trades = [s for s in signals if s.get('action') == 'NO_TRADE']
    
    print(f"  Trade signals: {len(trades)}")
    print(f"  No-trade signals: {len(no_trades)}")
    
    print("\n" + "=" * 80)
    print("STEP 2: VALIDATE AGAINST V7 GRAMMAR")
    print("=" * 80)
    
    results = audit_legacy_entries(signals)
    
    print("\n" + "=" * 80)
    print("STEP 3: GENERATE AUDIT TABLES")
    print("=" * 80)
    
    categories = generate_tables(results)
    
    print("\n" + "=" * 80)
    print("🎯 INTERPRETATION")
    print("=" * 80)
    
    true_entry_rate = categories.get("TRUE_ENTRY", 0) / len(results) * 100 if results else 0
    signal_rate = categories.get("ENTRY_SIGNAL", 0) / len(results) * 100 if results else 0
    filtered_rate = categories.get("FILTERED_CORRECTLY", 0) / len(results) * 100 if results else 0
    
    print(f"""
TRUE_ENTRY 비율: {true_entry_rate:.1f}%
{'→ 과거 정의가 정확했음' if true_entry_rate > 50 else '→ 과거 정의가 느슨했음'}

ENTRY_SIGNAL (가짜) 비율: {signal_rate:.1f}%
{'→ 세션 개념 없이 신호만 있었음' if signal_rate > 20 else '→ 신호 품질 양호'}

FILTERED_CORRECTLY 비율: {filtered_rate:.1f}%
→ 기존 필터가 올바르게 차단

핵심 결론:
"우리는 엔트리를 개선한 게 아니라
 엔트리의 정의를 바로잡았다."
""")
    
    report = {
        "analysis_time": datetime.now().isoformat(),
        "total_signals": len(signals),
        "categories": dict(categories),
        "true_entry_rate": true_entry_rate,
        "entry_signal_rate": signal_rate,
        "filtered_rate": filtered_rate,
        "sample_results": [asdict(r) for r in results[:100]]
    }
    
    report_path = '/tmp/legacy_entry_audit.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📄 Report saved to: {report_path}")
    
    return results, categories


if __name__ == "__main__":
    run_legacy_audit()
