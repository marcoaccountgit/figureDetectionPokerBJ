"""Extract labelled digit templates only from the opening TRAIN frame."""
import argparse,json
from pathlib import Path
from card_detector import cv2
from table_profiles import NINE_NAMES
from table_number_reader import number_glyphs,normalized_digit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video',type=Path);args=parser.parse_args()
    cap=cv2.VideoCapture(str(args.video));ok,im=cap.read();cap.release()
    if not ok:raise ValueError('Training frame unavailable')
    image=cv2.resize(im,(1762,round(im.shape[0]*1762/im.shape[1])))
    known={'top_left':'16310','upper_left':'66082','upper_right':'48627',
           'middle_left':'49202','middle_right':'28227','lower_left':'53872',
           'lower_right':'15000','hero':'19500'}
    out=Path('assets/table-nine/digits');out.mkdir(parents=True,exist_ok=True);inventory=[]
    for seat,value in known.items():
        x,y,r,b=NINE_NAMES[seat];crop=image[round(y+(b-y)*.53):b,x:r]
        glyphs=number_glyphs(crop)
        if len(glyphs)!=len(value):raise ValueError(f'Unexpected glyph count {seat}: {len(glyphs)} != {value}')
        for i,(digit,g) in enumerate(zip(value,glyphs)):
            filename=f'{digit}_{seat}_{i}.png';cv2.imwrite(str(out/filename),normalized_digit(g[4])*255)
            inventory.append(dict(file=filename,seat=seat,time=0,label=digit))
    (out/'provenance.json').write_text(json.dumps(dict(source=args.video.name,split='train',frames=[0],templates=inventory),indent=2))
    print('Training glyphs:',len(inventory),'classes:',len({x['label'] for x in inventory}))
    # Amount labels use a second font. All source timestamps are TRAIN hands.
    out=Path('assets/table-nine/amount-digits');out.mkdir(parents=True,exist_ok=True);inventory=[]
    cap=cv2.VideoCapture(str(args.video))
    for t,value,y1,y2 in [(0,'4250',318,354),(30,'13500',318,354),(60,'118391',318,354),(150,'2750',350,394),(330,'4016',350,394)]:
        cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,image=cap.read()
        if not ok:raise ValueError('Amount training frame unavailable')
        for width in (1918,1762):
            scale=width/1918;resized=cv2.resize(image,(width,round(image.shape[0]*scale)))
            crop=resized[round(y1*scale):round(y2*scale),round(835*scale):round(1130*scale)]
            glyphs=number_glyphs(crop)
            if len(glyphs)<len(value):raise ValueError(f'Amount glyph count mismatch: {t}')
            glyphs=glyphs[-len(value):]
            for i,(digit,g) in enumerate(zip(value,glyphs)):
                filename=f'{digit}_{t}_{width}_{i}.png';cv2.imwrite(str(out/filename),normalized_digit(g[4])*255)
                inventory.append(dict(file=filename,time=t,label=digit))
    from table_profiles import NINE_BETS
    from table_observer import chip_amount_label
    for t,values in [(0,{'top_left':'1500','upper_left':'500','middle_left':'500','middle_right':'250','lower_left':'500','lower_right':'500','hero':'500'}),
                     (60,{'upper_left':'51872','lower_left':'51872'})]:
        cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,image=cap.read()
        if not ok:raise ValueError('Bet training frame unavailable')
        image=cv2.resize(image,(1762,round(image.shape[0]*1762/image.shape[1])))
        for seat,value in values.items():
            x,y,r,b=NINE_BETS[seat];crop=chip_amount_label(image[y:b,x:r])
            if crop is None:continue
            glyphs=number_glyphs(crop,bet=True)
            if len(glyphs)!=len(value):continue
            for i,(digit,g) in enumerate(zip(value,glyphs)):
                filename=f'{digit}_bet{t}_{seat}_{i}.png';cv2.imwrite(str(out/filename),normalized_digit(g[4])*255)
                inventory.append(dict(file=filename,time=t,label=digit,seat=seat))
    cap.release()
    (out/'provenance.json').write_text(json.dumps(dict(source=args.video.name,split='train',frames=[0,30,60,150,330],templates=inventory),indent=2))
    print('Amount glyphs:',len(inventory),'classes:',len({x['label'] for x in inventory}))


if __name__=='__main__':main()
