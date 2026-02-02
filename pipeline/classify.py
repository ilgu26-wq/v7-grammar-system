"""
STRUCTURE CLASSIFICATION PIPELINE v1.0
Classify - 구조 선언 (사후 집계 기반)
"""
from collections import defaultdict

def assign_structure_type(theta_label, stb_index, delta_bucket):
    """
    사후 집계 기반 구조 선언
    
    ⚠️ 이 함수는 집계 단계에서만 호출
    ⚠️ ENTRY 시점에 호출 금지
    """
    if theta_label is not None and theta_label >= 3 and stb_index == "first":
        return "IGNITION"
    
    if theta_label == 1 and stb_index == "re-entry":
        return "ENTRY"
    
    if theta_label == 0 and delta_bucket == "LOW":
        return "DEATH"
    
    return "UNKNOWN"

def aggregate_by_structure(trades):
    """
    구조 단위로 집계
    
    Returns:
        dict: {structure_key: {N, wins, WR, structure_type}}
    """
    groups = defaultdict(lambda: {'trades': [], 'wins': 0, 'losses': 0})
    
    for t in trades:
        key = (
            t.get('direction', 'UNK'),
            t.get('delta_bucket', 'N/A'),
            t.get('STB_index', 'N/A'),
            t.get('theta_label'),
        )
        groups[key]['trades'].append(t)
        if t.get('result') == 'WIN':
            groups[key]['wins'] += 1
        else:
            groups[key]['losses'] += 1
    
    summary = []
    for key, data in groups.items():
        direction, delta_bucket, stb_index, theta_label = key
        n = len(data['trades'])
        wins = data['wins']
        wr = wins / n * 100 if n > 0 else 0
        
        structure_type = assign_structure_type(theta_label, stb_index, delta_bucket)
        
        summary.append({
            'direction': direction,
            'delta_bucket': delta_bucket,
            'STB_index': stb_index,
            'theta_label': theta_label,
            'N': n,
            'wins': wins,
            'WR': round(wr, 1),
            'structure_type': structure_type,
        })
    
    summary.sort(key=lambda x: (-x['N']))
    return summary

if __name__ == "__main__":
    from loaders import load_all_sources
    
    trades = load_all_sources()
    summary = aggregate_by_structure(trades)
    
    print("\n" + "="*70)
    print("STRUCTURE CLASSIFICATION SUMMARY")
    print("="*70)
    
    print(f"\n{'Direction':<8} {'Delta':<10} {'STB':<10} {'θ':>3} {'N':>5} {'WR':>6} {'Type':<10}")
    print("-"*60)
    
    for s in summary[:30]:
        theta_str = str(s['theta_label']) if s['theta_label'] is not None else 'N/A'
        print(f"{s['direction']:<8} {s['delta_bucket']:<10} {s['STB_index']:<10} {theta_str:>3} {s['N']:>5} {s['WR']:>5.1f}% {s['structure_type']:<10}")
