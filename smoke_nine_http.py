"""Local real-model/OCR/worker HTTP smoke test using only video timestamp zero."""
import argparse,http.client,json,threading,time
from pathlib import Path
from http.server import ThreadingHTTPServer
from card_detector import cv2
from browser_capture import make_handler
from learned_detector import TableCardDetector
from table_observer import TableObservationService
from equity_service import EquityService


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('video',type=Path);args=parser.parse_args()
    cap=cv2.VideoCapture(str(args.video));ok,frame=cap.read();cap.release()
    if not ok:raise ValueError('Opening frame unavailable')
    payload=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,92])[1].tobytes()
    observer=TableObservationService();equity=EquityService();detector=TableCardDetector()
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(detector,'smoke-nine',observer,equity))
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
    try:
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            client.request('POST','/frame',payload,{'X-Capture-Token':'smoke-nine','X-Capture-Session':'nine-session','X-Equity-Seed':'2026'})
            response=client.getresponse();result=json.loads(response.read())
            if response.status!=200:raise RuntimeError(result)
            print(result['table_profile'],result['hand_cycle']['count'],result['opponents']['count'],result['equity']['status'],result.get('table_observation',{}).get('status'),flush=True)
            if result['equity'].get('complete') and result.get('table_observation',{}).get('status')=='ready':break
            time.sleep(.12)
        assert result['table_profile']=='pokerstars-nine'
        assert [c['card'] for c in result['player_hand']]==['KD','JS']
        assert result['opponents']['count']==6 and result['opponents']['max_opponents']==8
        assert result['hand_cycle']['count']==1
        assert result['equity'].get('complete') and result['equity']['street']=='preflop'
        assert len(result['table_observation']['seats'])==9
        assert result['table_observation']['pot']['value']==4250
        assert result['table_observation']['pot']['unit']=='CHIPS'
        path=Path('artifacts/nine-seat-125816/http-smoke.json');path.write_text(json.dumps(result,indent=2))
        print('HTTP smoke passed; result:',path)
    finally:
        client.close();server.shutdown();server.server_close();observer.close();equity.close();worker.join()


if __name__=='__main__':main()
