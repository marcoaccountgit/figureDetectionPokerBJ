"""Reproducible local timings; no latency or precision guarantees."""
import argparse
import json
from pathlib import Path
from poker_equity import PROFILES, calculate_equity


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full',action='store_true',help='Include 50k and 250k profiles')
    args=parser.parse_args()
    reports=[]
    for profile,n in PROFILES.items():
        if not args.full and profile!='FAST': continue
        for opponents in (1,3,5):
            for board in ([],['2s','7d','Jh'],['2s','7d','Jh','Tc','9c']):
                result=calculate_equity(['As','Kh'],board,opponents,n,random_seed=2026)
                report=dict(profile=profile,opponents=opponents,street=result['street'],
                            method=result['method'],samples=result['simulations'],
                            milliseconds=result['processing_ms'],equity=result['metrics']['equity'])
                reports.append(report)
                print(json.dumps(report),flush=True)
    path=Path('artifacts/equity-benchmark.json')
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(reports,indent=2),encoding='utf-8')


if __name__=='__main__': main()
