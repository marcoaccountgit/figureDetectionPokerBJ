"""Check explicitly reviewed financial/action fields in the new desktop video."""
import json
from pathlib import Path
from card_detector import cv2
from table_observer import WindowsOCR,TableVisualReader
from table_profiles import DESKTOP_SIX

CASES={0:dict(pot=700,contribution=200,hero_stack=11400),
 165:dict(pot=1000,contribution=200,hero_stack=8767,actions={'top':'check'}),
 240:dict(pot=1365,contribution=672,collected_pot=1365,hero_stack=9218),
 450:dict(pot=756,contribution=200,collected_pot=756,hero_stack=7583,actions={'upper_left':'fold','upper_right':'fold'}),
 705:dict(pot=22587,contribution=6372,actions={'hero':'all_in','lower_right':'all_in'})}

def main():
 root=Path(__file__).resolve().parent;ocr=WindowsOCR();reader=TableVisualReader(ocr,DESKTOP_SIX);rows=[];errors=[];correct=total=0
 try:
  for t,expected in CASES.items():
   f=cv2.imread(str(root/'artifacts/desktop-200950/review'/f'{t:04d}.jpg'))
   result=reader.read(f);seats={s['seat']:s for s in result['seats']}
   for key,wanted in expected.items():
    if key=='actions':
     checks=[(key+'.'+seat,seats[seat]['action'],value) for seat,value in wanted.items()]
    else:
     value=seats['hero']['stack'] if key=='hero_stack' else result.get(key)
     checks=[(key,value['value'] if value else None,wanted)]
    for key,actual,wanted in checks:
     total+=1;correct+=actual==wanted
     if actual!=wanted:errors.append(dict(time=t,field=key,actual=actual,expected=wanted))
   rows.append(dict(time=t,expected=expected,result=result));print(t,correct,total,flush=True)
 finally:ocr.close()
 (root/'artifacts/desktop-200950/observations.json').write_text(json.dumps(dict(correct=correct,total=total,errors=errors,frames=rows),indent=2))
 print(json.dumps(dict(correct=correct,total=total,errors=errors),indent=2))

if __name__=='__main__':main()
