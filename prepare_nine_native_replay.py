"""Compose unseen rank/suit combinations at the nine-seat native index size.

Only training glyphs and a training background are used. Holdout pixels are
never read by this builder. Existing dataset remains untouched.
"""
import json,random,shutil
from pathlib import Path
from PIL import Image,ImageDraw
from card_detector import cv2
from prepare_improvement_dataset import glyph_mask
from prepare_table_dataset import write_sample


def main():
    source=Path('artifacts/nine-seat-125816/dataset')
    output=Path('artifacts/nine-seat-125816/dataset-native')
    shutil.copytree(source,output)
    data=json.loads((source/'data.yaml').read_text());names=data['names']
    spec=json.loads(Path('datasets/nine-seat-125816.json').read_text())
    bank={'rank':{},'suit':{}}
    for path in sorted((source/'images/train').glob('real_*.jpg')):
        im=cv2.imread(str(path));h,w=im.shape[:2]
        for line in (source/'labels/train'/(path.stem+'.txt')).read_text().splitlines():
            index,cx,cy,bw,bh=map(float,line.split());code=names[int(index)]
            x,y=round((cx-bw/2)*w),round((cy-bh/2)*h)
            patch=im[y:round((cy+bh/2)*h),x:round((cx+bw/2)*w)]
            if patch.shape[0]<60:continue
            for kind,key,part in [('rank',code[:-1],patch[:35]),('suit',code[-1],patch[35:])]:
                bank[kind].setdefault(key,glyph_mask(part))
    background=Image.open(next((source/'images/train').glob('real_0030_30.0.jpg'))).convert('RGB')
    rng=random.Random(125816);inventory=[]
    for index,code in enumerate(names):
        for variant in range(8):
            image=background.copy();draw=ImageDraw.Draw(image)
            slot=variant%5;x=696+110*slot-650;y=397-360
            if variant>=5:x,y=(863 if variant%2 else 967)-650,723-360
            dx,dy=rng.choice([-1,0,1]),rng.choice([-1,0,1]);x+=dx;y+=dy
            draw.rounded_rectangle((x-4,y-5,x+94,y+132),radius=6,fill=(250,250,250),outline=(180,180,180))
            color=(175,12,25) if code[-1] in 'DH' else (8,10,12)
            rank=bank['rank'][code[:-1]];rh=31+variant%2;rw=round(rank.width*rh/rank.height)
            rank=rank.resize((min(29,rw),rh),Image.Resampling.NEAREST)
            suit=bank['suit'][code[-1]];sh=23;sw=round(suit.width*sh/suit.height)
            suit=suit.resize((min(26,sw),sh),Image.Resampling.NEAREST)
            image.paste(color,(x,y,x+rank.width,y+rh),rank)
            image.paste(color,(x,y+37,x+suit.width,y+37+sh),suit)
            label=[[index,(x+16.5)/image.width,(y+33)/image.height,33/image.width,66/image.height]]
            stem=f'native_{code}_{variant}'
            write_sample(output,'train',stem,cv2.cvtColor(__import__('numpy').array(image),cv2.COLOR_RGB2BGR),label)
            inventory.append(dict(file=stem,code=code))
    data['path']=str(output.resolve()).replace('\\','/')
    (output/'data.yaml').write_text(json.dumps(data,indent=2))
    manifest=json.loads((output/'manifest.json').read_text());manifest['native_synthetic']=inventory
    manifest['native_synthetic_frames']=len(inventory)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print('Native training replay:',len(inventory),'source ranks:',sorted(bank['rank']))


if __name__=='__main__':main()
