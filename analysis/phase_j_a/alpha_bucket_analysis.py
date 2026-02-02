"""
Phase J-A — ALPHA BUCKET ANALYSIS
=================================

버킷별 분포 비교
J-A-2: FAIL_REASON 불변성 검증
J-A-3: 전이 언어 불변성 검증
"""

import json
import numpy as np
from typing import Dict, List
from collections import defaultdict


def load_sessions() -> List[Dict]:
    """세션 로드"""
    try:
        with open('/tmp/phase_j_a_sessions.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Sessions not found. Run inject_alpha_readonly.py first.")
        return []


def analyze_by_bucket(sessions: List[Dict]) -> Dict:
    """버킷별 분석"""
    print("\n" + "=" * 60)
    print("PHASE J-A — ALPHA BUCKET ANALYSIS")
    print("=" * 60)
    
    buckets = {"LOW": [], "MID": [], "HIGH": []}
    
    for s in sessions:
        bucket = s.get('alpha_bucket', 'MID')
        buckets[bucket].append(s)
    
    print("\n📊 Bucket Distribution:")
    for bucket, items in buckets.items():
        print(f"  {bucket}: {len(items)} sessions")
    
    print("\n📊 Exit Reason by Bucket:")
    exit_by_bucket = {}
    
    for bucket, items in buckets.items():
        exit_reasons = defaultdict(int)
        for s in items:
            reason = s.get('exit_reason', 'UNKNOWN')
            exit_reasons[reason] += 1
        exit_by_bucket[bucket] = dict(exit_reasons)
        
        print(f"\n  {bucket}:")
        for reason, count in exit_reasons.items():
            pct = count / len(items) * 100 if items else 0
            print(f"    {reason}: {count} ({pct:.1f}%)")
    
    print("\n📊 Session Metrics by Bucket:")
    metrics_by_bucket = {}
    
    for bucket, items in buckets.items():
        if items:
            durations = [s.get('duration', 0) for s in items]
            hold_bars = [s.get('hold_bars', 0) for s in items]
            forces = [s.get('force_accumulated', 0) for s in items]
            force_created = sum(1 for s in items if s.get('force_created'))
            
            metrics = {
                "count": len(items),
                "avg_duration": np.mean(durations),
                "avg_hold_bars": np.mean(hold_bars),
                "avg_force": np.mean(forces),
                "force_created_rate": force_created / len(items) * 100
            }
            metrics_by_bucket[bucket] = metrics
            
            print(f"\n  {bucket}:")
            print(f"    Count: {metrics['count']}")
            print(f"    Avg Duration: {metrics['avg_duration']:.1f}")
            print(f"    Avg HOLD bars: {metrics['avg_hold_bars']:.1f}")
            print(f"    Avg Force: {metrics['avg_force']:.1f}")
            print(f"    Force Created Rate: {metrics['force_created_rate']:.1f}%")
    
    return {
        "bucket_counts": {b: len(items) for b, items in buckets.items()},
        "exit_by_bucket": exit_by_bucket,
        "metrics_by_bucket": metrics_by_bucket
    }


def check_distribution_stability(sessions: List[Dict]) -> Dict:
    """분포 안정성 검증 (J-A-2, J-A-3)"""
    print("\n" + "=" * 60)
    print("DISTRIBUTION STABILITY CHECK")
    print("=" * 60)
    
    buckets = {"LOW": [], "MID": [], "HIGH": []}
    for s in sessions:
        bucket = s.get('alpha_bucket', 'MID')
        buckets[bucket].append(s)
    
    all_exit_reasons = set()
    for s in sessions:
        all_exit_reasons.add(s.get('exit_reason', 'UNKNOWN'))
    
    exit_distributions = {}
    for bucket, items in buckets.items():
        if items:
            dist = {}
            for reason in all_exit_reasons:
                count = sum(1 for s in items if s.get('exit_reason') == reason)
                dist[reason] = count / len(items)
            exit_distributions[bucket] = dist
    
    print("\n📊 Exit Reason Proportions:")
    print(f"{'Reason':<25} {'LOW':>10} {'MID':>10} {'HIGH':>10}")
    print("-" * 55)
    
    max_diff = 0
    for reason in sorted(all_exit_reasons):
        low = exit_distributions.get('LOW', {}).get(reason, 0) * 100
        mid = exit_distributions.get('MID', {}).get(reason, 0) * 100
        high = exit_distributions.get('HIGH', {}).get(reason, 0) * 100
        
        values = [v for v in [low, mid, high] if v > 0]
        if values:
            diff = max(values) - min(values)
            max_diff = max(max_diff, diff)
        
        print(f"{reason:<25} {low:>9.1f}% {mid:>9.1f}% {high:>9.1f}%")
    
    threshold = 30.0
    is_stable = max_diff < threshold
    
    print(f"\n{'='*55}")
    print(f"Max Difference: {max_diff:.1f}%")
    print(f"Threshold: {threshold}%")
    print(f"Stability: {'✅ STABLE' if is_stable else '❌ UNSTABLE'}")
    
    return {
        "exit_distributions": exit_distributions,
        "max_difference": max_diff,
        "is_stable": is_stable
    }


def main():
    sessions = load_sessions()
    if not sessions:
        return None
    
    bucket_analysis = analyze_by_bucket(sessions)
    stability = check_distribution_stability(sessions)
    
    result = {
        "bucket_analysis": bucket_analysis,
        "stability_check": stability
    }
    
    output_path = '/tmp/phase_j_a_bucket_analysis.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n\nAnalysis saved to: {output_path}")
    return result


if __name__ == "__main__":
    main()
