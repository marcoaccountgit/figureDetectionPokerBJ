"""Manual pixel transcription; split complete hands before learning references."""
import json
from pathlib import Path
from table_profiles import NINE_BACKS

OUT = Path('artifacts/nine-135641')


def reviewed_frames():
    rows = {}
    keys = list(NINE_BACKS)
    def add(times, hand, board='', hole='', seats=''):
        split = 'val' if hand in (3,8) else 'test' if hand in (7,12,13) else 'train'
        for t in times:
            rows[t] = dict(time=t,hand=hand,split=split,board=board.split(),hole=hole.split(),
                seats={key:i in [int(v) for v in seats.split()] for i,key in enumerate(keys)})
    # Seat order: TL, TR, UL, UR, ML, MR, LL, LR. Reviewed from backs sheets.
    add([0,5,10],1,'JS 4H 2D',seats='3 6 7')
    add([15,20,25,30,35],1,'JS 4H 2D 6H 7C',seats='3 6')
    add([45],2,hole='3H 3D',seats='0 1 2 3 4 5 6 7')
    add([50],2,hole='3H 3D',seats='1 3 4 5 6 7')
    add([55,60,65],2,hole='3H 3D',seats='3 4 5 6 7')
    add([75],3,hole='JD 10C',seats='0 1 2 3 5 6 7')
    add([80,85,90],3,hole='JD 10C',seats='0 2 3 5 6 7')
    add([95],3,hole='JD 10C',seats='0 2 6')
    add([100,105,110,115],3,'2D 9D 7C','JD 10C','6')
    add([120],3,'2D 9D 7C 4S','JD 10C','6')
    add([125],3,'2D 9D 7C 4S QC','JD 10C')
    add([135],4,seats='3')
    add([205],4,'9H 3D 7C',seats='4 7')
    add([215],4,'9H 3D 7C 6H 7H')
    add([220],5,seats='0 1 2 3 4 5 7')
    add([225],5,seats='0 1 2 3 5 7')
    add([240],5,seats='2 3 5 7')
    add([245],5,seats='2 5 7')
    add([250,255],5,seats='2 5 7')
    rows[250]['board']='QS JS QC'.split()
    rows[255]['board']='QS JS QC 8S 4C'.split()
    add([270,275],6,hole='QH 7C',seats='0 1 3 6 7')
    add([280,285,290],6,hole='QH 7C',seats='3 6 7')
    add([295],6,hole='QH 7C',seats='6')
    add([300,305],6,'3S AS 2H','QH 7C','6')
    add([310],6,'3S AS 2H',seats='6')
    add([320],7,hole='6D 5H',seats='0 1 3 4 6 7')
    add([325],7,hole='6D 5H',seats='0 3 4 6 7')
    add([340],7,seats='0 4 7')
    add([345,350,355],7,'9D 8S 10C',seats='0 4 7')
    add([360,365],7,'9D 8S 10C KC',seats='0 4 7')
    add([370],7,'9D 8S 10C KC 8D',seats='0 4 7')
    add([375],7,'9D 8S 10C KC 8D')
    add([380],8,hole='KH 10H',seats='1 2 3 4 6 7')
    add([385,395],8,hole='KH 10H',seats='2 3 4 6 7')
    add([400],8,hole='KH 10H',seats='2 4')
    add([405],8,'4H 6S 10C','KH 10H')
    add([410],8,'4H 6S 10C 2D 7S','KH 10H')
    add([415],9,hole='QH 6S',seats='1 2 3 6 7')
    add([425,430,435],9,hole='QH 6S',seats='1 3')
    add([440,445,450,455],9,'4H 3S KC','QH 6S','1 3')
    add([460,465,470,475,480,485,490],9,'4H 3S KC 2D','QH 6S','1 3')
    add([495,500,505,510],9,'4H 3S KC 2D 7S','QH 6S','1 3')
    add([515],9,'4H 3S KC 2D 7S')
    add([530],10,seats='1 2 3 5')
    add([550,555,565,570,575,580],10,'JS 8D 9S',seats='2 3')
    add([585],10,'JS 8D 9S',seats='2')
    add([590],11)
    add([595],11,seats='0 1 2 3 5 6 7')
    add([600],11,seats='1 3 5 6 7')
    add([605,610,615],11,seats='3 5 6 7')
    add([620],11,'KS 10H 4D',seats='6 7')
    add([625,630],11,'KS 10H 4D 6S JC',seats='6 7')
    add([640],12,hole='10C 4H',seats='0 1 3 5 7')
    add([645,650],12,hole='10C 4H',seats='3 5 7')
    add([660],12,hole='10C 4H',seats='7')
    add([665,670],12,'6S QC 6D','10C 4H','7')
    add([675],13)
    add([680],13,hole='10S 2S',seats='0 1 2 3 5 6 7')
    add([690,700,705],13,hole='10S 2S',seats='1 2 3 5 6 7')
    add([710,715],13,hole='10S 2S',seats='1 2 6')
    add([720,725],13,'6D KC 7H','10S 2S','1 2 6')
    add([730],13,'6D KC 7H 2D',seats='1 2')
    buttons={1:'lower_right',2:'hero',3:'lower_left',4:'upper_left',5:'upper_right',
             6:'lower_right',7:'hero',8:'lower_left',9:'upper_left',10:'top_right',
             11:'upper_right',12:'middle_right',13:'lower_right'}
    for row in rows.values():row['button']=buttons[row['hand']]
    rows[205]['button']='top_right'
    rows[215]['button']=None  # Showdown/transition, marker not visible.
    rows[675]['button']=None  # Deal animation, no marker visible yet.
    return sorted(rows.values(),key=lambda row:row['time'])


def main():
    baseline = json.loads((OUT/'baseline.json').read_text())
    rows = reviewed_frames()
    excluded = [f['time'] for f in baseline['frames'] if f['time'] not in {r['time'] for r in rows}]
    spec = dict(source=baseline['source'],sha256=baseline['sha256'],duration=baseline['duration'],
        frames=rows,excluded_times=excluded,
        protocol='Manual visual transcription of cards and all eight back positions; complete hands disjoint. Partial deals, overlays and transitions excluded from identity training and separately tested.')
    Path('datasets/nine-135641.json').write_text(json.dumps(spec,indent=2))
    by_time={f['time']:f for f in baseline['frames']}
    failures=[]
    for row in rows:
        before=by_time[row['time']]
        expected=row['board']+[None]*(5-len(row['board']))+row['hole']+[None]*(2-len(row['hole']))
        seat_errors=[dict(seat=s['seat'],actual=s['present'],expected=row['seats'].get(s['seat']),score=s['score'])
                     for s in before['seats'] if s['present']!=row['seats'].get(s['seat'])]
        if before['actual']!=expected or seat_errors or before['profile']!='pokerstars-nine':
            failures.append(dict(time=row['time'],split=row['split'],expected=expected,
                actual=before['actual'],seats=seat_errors,profile=before['profile']))
    (OUT/'baseline-errors.json').write_text(json.dumps(failures,indent=2))
    print(json.dumps(dict(reviewed=len(rows),excluded=len(excluded),error_frames=len(failures))))


if __name__=='__main__':
    main()
