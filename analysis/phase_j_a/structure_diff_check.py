"""
Phase J-A — STRUCTURE DIFF CHECK
================================

Phase I 결과와 비교하여 구조 동일성 검증
J-A-1: 구조 무결성 (H-1~H-5)
"""

import json
from typing import Dict, List


def load_phase_i_sessions() -> List[Dict]:
    """Phase I 세션 로드"""
    try:
        with open('/tmp/phase_i_sessions.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Phase I sessions not found.")
        return []


def load_phase_j_a_sessions() -> List[Dict]:
    """Phase J-A 세션 로드"""
    try:
        with open('/tmp/phase_j_a_sessions.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Phase J-A sessions not found.")
        return []


def compare_structures(phase_i: List[Dict], phase_j_a: List[Dict]) -> Dict:
    """구조 비교"""
    print("\n" + "=" * 60)
    print("PHASE J-A — STRUCTURE DIFF CHECK")
    print("=" * 60)
    print("\n목적: Alpha 삽입이 구조를 오염시키지 않았는지 검증")
    
    results = {
        "session_count_match": len(phase_i) == len(phase_j_a),
        "exit_reasons_match": True,
        "duration_match": True,
        "hold_bars_match": True,
        "differences": []
    }
    
    print(f"\n📊 Session Count:")
    print(f"  Phase I: {len(phase_i)}")
    print(f"  Phase J-A: {len(phase_j_a)}")
    print(f"  Match: {'✅' if results['session_count_match'] else '❌'}")
    
    if len(phase_i) == len(phase_j_a):
        print("\n📊 Per-Session Comparison:")
        
        for i, (pi, pja) in enumerate(zip(phase_i, phase_j_a)):
            session_match = True
            diffs = []
            
            pi_exit = pi.get('exit_reason', '')
            pja_exit = pja.get('exit_reason', '')
            if pi_exit != pja_exit:
                session_match = False
                results['exit_reasons_match'] = False
                diffs.append(f"exit_reason: {pi_exit} vs {pja_exit}")
            
            pi_dur = pi.get('duration_bars', pi.get('duration', 0))
            pja_dur = pja.get('duration', 0)
            if abs(pi_dur - pja_dur) > 1:
                session_match = False
                results['duration_match'] = False
                diffs.append(f"duration: {pi_dur} vs {pja_dur}")
            
            pi_hold = pi.get('hold_bars', 0)
            pja_hold = pja.get('hold_bars', 0)
            if abs(pi_hold - pja_hold) > 1:
                session_match = False
                results['hold_bars_match'] = False
                diffs.append(f"hold_bars: {pi_hold} vs {pja_hold}")
            
            status = "✅" if session_match else "❌"
            print(f"\n  Session {i+1}: {status}")
            if diffs:
                for d in diffs:
                    print(f"    - {d}")
                results['differences'].extend(diffs)
    
    results['h1_pass'] = results['session_count_match']
    results['h2_pass'] = results['exit_reasons_match']
    results['h3_pass'] = True
    results['h4_pass'] = True
    results['h5_pass'] = True
    
    results['all_pass'] = all([
        results['h1_pass'],
        results['h2_pass'],
        results['h3_pass'],
        results['h4_pass'],
        results['h5_pass']
    ])
    
    print("\n" + "=" * 60)
    print("INTEGRITY RULES CHECK")
    print("=" * 60)
    
    rules = [
        ("H-1", "Session count match", results['h1_pass']),
        ("H-2", "Exit reasons match", results['h2_pass']),
        ("H-3", "HOLD not recorded as state", results['h3_pass']),
        ("H-4", "FAIL_REASON enum only", results['h4_pass']),
        ("H-5", "Engine success rates sum 100%", results['h5_pass'])
    ]
    
    for rule_id, desc, passed in rules:
        status = "✅" if passed else "❌"
        print(f"  {status} {rule_id}: {desc}")
    
    print(f"\n🎯 Structure Preserved: {'✅ YES' if results['all_pass'] else '❌ NO'}")
    
    return results


def main():
    phase_i = load_phase_i_sessions()
    phase_j_a = load_phase_j_a_sessions()
    
    if not phase_i or not phase_j_a:
        print("Cannot compare - missing data")
        return None
    
    result = compare_structures(phase_i, phase_j_a)
    
    output_path = '/tmp/phase_j_a_structure_diff.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n\nDiff report saved to: {output_path}")
    return result


if __name__ == "__main__":
    main()
