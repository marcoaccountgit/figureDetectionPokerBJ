"""Reproducible local timings; no latency or precision guarantees."""
import argparse
import json
from pathlib import Path
from statistics import median
from poker_equity import PROFILES, calculate_equity


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full',action='store_true',help='Include 50k and 250k profiles')
    parser.add_argument('--backend',choices=('auto','python','rust'),default='auto')
    parser.add_argument('--compare',action='store_true',help='Compare Python and Rust on identical scenarios')
    parser.add_argument('--repeats',type=int,default=1)
    args=parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    reports=[]
    for profile,n in PROFILES.items():
        if not args.full and profile!='FAST': continue
        for opponents in (1,3,5,8):
            for board in ([],['2s','7d','Jh'],['2s','7d','Jh','Tc'],['2s','7d','Jh','Tc','9c']):
                for backend in (('python','rust') if args.compare else (args.backend,)):
                    results=[calculate_equity(['As','Kh'],board,opponents,n,random_seed=2026,backend=backend)
                             for _ in range(args.repeats)]
                    result=results[-1]
                    report=dict(profile=profile,opponents=opponents,street=result['street'],
                                backend=result['backend'],requested_backend=backend,
                                method=result['method'],samples=result['simulations'],
                                milliseconds=median(r['processing_ms'] for r in results),
                                repeat_milliseconds=[r['processing_ms'] for r in results],
                                equity=result['metrics']['equity'])
                    reports.append(report)
                    print(json.dumps(report),flush=True)
    path=Path('artifacts/equity-benchmark.json')
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(reports,indent=2),encoding='utf-8')


if __name__=='__main__': main()
