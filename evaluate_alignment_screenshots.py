"""Reproduce supplied alignment/card previews through the real HTTP pipeline.

Repeated stills and a simulated slow clock test registration/confirmation,
not the accuracy of an unseen continuous video.
"""
import argparse
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
from unittest.mock import patch

from browser_capture import make_handler
from card_detector import cv2
from learned_detector import LearnedCardDetector


def evaluate(directory):
    server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(LearnedCardDetector(profile='pokerstars'),'screenshot-check'))
    worker = threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    client = http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=15)
    cases = []
    try:
        with patch('browser_capture.perf_counter',side_effect=[i*.08 for i in range(1000)]):
            for name,box,repeats in [('190551',(162,399,1085,874),5),('190655',(200,381,1123,856),8),
                                     ('192703',(210,319,1133,794),5),('192744',(152,234,1075,677),5),
                                     ('155720',(28,239,1376,896),5),('162911',(175,412,1098,887),5),
                                     ('203254',(215,299,1138,774),5)]:
                source = directory/f'Screenshot 2026-11-05 {name}.png'
                frame = cv2.imread(str(source))
                if frame is None:
                    raise RuntimeError(f'Screenshot mancante: {source}')
                x,y,right,bottom = box
                frame = frame[y:bottom,x:right]
                encoded = cv2.imencode('.png',frame)[1].tobytes()
                trace = []
                for _ in range(repeats):
                    client.request('POST','/frame',encoded,{'X-Capture-Token':'screenshot-check','X-Capture-Session':'layout-transition'})
                    response = client.getresponse()
                    body = response.read()
                    if response.status != 200:
                        raise RuntimeError(body.decode())
                    result = json.loads(body)
                    trace.append(dict(viewport=result['capture_alignment']['viewport'],
                                      hand=[s['card'] for s in result['player_hand']],
                                      board=[s['card'] for s in result['board']]))
                expected_hand = {'190551':['10C','QS'],'190655':[None,None],
                                 '192703':['2D','3C'],'192744':['4C','AS'],
                                 '155720':['4S','7H'],'162911':['3S','4C'],'203254':['KS','JD']}[name]
                expected_board = ['5C','3D','9C','6S',None] if name=='190655' else [None]*5
                cases.append(dict(source=source.name,preview_crop=box,trace=trace,
                                  exact=trace[-1]['hand']==expected_hand and trace[-1]['board']==expected_board))
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        worker.join()
    return dict(protocol='Extracted screenshot previews, repeated as stills. HTTP pipeline with simulated 560ms cycles confirms five consecutive readings beyond the old two-second window; not a continuous-video benchmark.',cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots-dir',type=Path,default=Path.home()/'Pictures/Screenshots')
    parser.add_argument('--output',type=Path,default=Path('artifacts/alignment-1905/screenshots-http.json'))
    args = parser.parse_args()
    report = evaluate(args.screenshots_dir)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    for case in report['cases']:
        print(case['source'],json.dumps(case['trace'][-1]),'OK' if case['exact'] else 'FAILED')
    if not all(c['exact'] for c in report['cases']):
        raise SystemExit(1)


if __name__=='__main__':
    main()
