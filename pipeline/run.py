"""
STRUCTURE CLASSIFICATION PIPELINE v1.0
Run - 전수 분류 실행
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loaders import load_all_sources
from classify import aggregate_by_structure

def main():
    print("="*70)
    print("STRUCTURE CLASSIFICATION PIPELINE v1.0")
    print("="*70)
    
    trades = load_all_sources()
    print(f"\nTotal trades: {len(trades)}")
    
    summary = aggregate_by_structure(trades)
    
    print("\n" + "="*70)
    print("STRUCTURE SUMMARY (Top 30)")
    print("="*70)
    
    print(f"\n{'Direction':<8} {'Delta':<10} {'STB':<10} {'θ':>3} {'N':>5} {'WR':>6} {'Type':<10}")
    print("-"*65)
    
    for s in summary[:30]:
        theta_str = str(s['theta_label']) if s['theta_label'] is not None else 'N/A'
        print(f"{s['direction']:<8} {s['delta_bucket']:<10} {s['STB_index']:<10} {theta_str:>3} {s['N']:>5} {s['WR']:>5.1f}% {s['structure_type']:<10}")
    
    ignition = [s for s in summary if s['structure_type'] == 'IGNITION']
    entry = [s for s in summary if s['structure_type'] == 'ENTRY']
    death = [s for s in summary if s['structure_type'] == 'DEATH']
    unknown = [s for s in summary if s['structure_type'] == 'UNKNOWN']
    
    print("\n" + "="*70)
    print("STRUCTURE TYPE DISTRIBUTION")
    print("="*70)
    print(f"IGNITION: {len(ignition)} groups, {sum(s['N'] for s in ignition)} trades")
    print(f"ENTRY:    {len(entry)} groups, {sum(s['N'] for s in entry)} trades")
    print(f"DEATH:    {len(death)} groups, {sum(s['N'] for s in death)} trades")
    print(f"UNKNOWN:  {len(unknown)} groups, {sum(s['N'] for s in unknown)} trades")
    
    output = {
        'total_trades': len(trades),
        'structures': summary,
        'distribution': {
            'IGNITION': sum(s['N'] for s in ignition),
            'ENTRY': sum(s['N'] for s in entry),
            'DEATH': sum(s['N'] for s in death),
            'UNKNOWN': sum(s['N'] for s in unknown),
        }
    }
    
    output_path = 'v7-grammar-system/pipeline/structure_summary.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to {output_path}")
    
    return output

if __name__ == "__main__":
    main()
