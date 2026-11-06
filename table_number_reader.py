"""Training-only glyph templates for explicit integer chip labels in nine-seat UI."""
from pathlib import Path
from card_detector import cv2,np


def number_glyphs(crop,bet=False):
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    threshold,_=cv2.threshold(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    mask=((hsv[:,:,1]<100)&(hsv[:,:,2]>max(70,min(145,threshold)))).astype(np.uint8)
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
    glyphs=[]
    for i in range(1,count):
        x,y,w,h,area=stats[i]
        if area<8 or h<10:continue
        if bet and h>26:continue
        if h>crop.shape[0]*.95 or w>h*1.5:continue
        glyphs.append((x,y,w,h,(labels[y:y+h,x:x+w]==i).astype(np.uint8)))
    if not glyphs:return []
    if bet:
        # Ignore fragments of chip rims above/below the line of amount digits.
        glyphs=max(([g for g in glyphs if abs((g[1]+g[3]/2)-(c[1]+c[3]/2))<=c[3]*.3]
                    for c in glyphs),key=lambda group:(len(group),sum(g[2]*g[3] for g in group)))
    maximum=max(g[3] for g in glyphs)
    return [g for g in sorted(glyphs,key=lambda g:g[0]) if g[3]>=maximum*.7]


def normalized_digit(mask):
    h,w=mask.shape;scale=min(20/w,28/h)
    resized=cv2.resize(mask,(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv2.INTER_NEAREST)
    out=np.zeros((32,24),np.uint8)
    x=(24-resized.shape[1])//2;y=(32-resized.shape[0])//2
    out[y:y+resized.shape[0],x:x+resized.shape[1]]=resized
    return out


class ChipNumberReader:
    def __init__(self,folder=None):
        folder=Path(folder) if folder else Path(__file__).parent/'assets/table-nine/digits'
        self.templates={}
        for path in folder.glob('*.png'):
            self.templates.setdefault(path.stem.split('_')[0],[]).append(cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)>0)

    def read(self,crop,bet=False):
        if len(self.templates)!=10:return None
        glyphs=number_glyphs(crop,bet)
        if not glyphs or len(glyphs)>12:return None
        digits=[];confidence=1.
        for _,_,_,_,mask in glyphs:
            sample=normalized_digit(mask)>0
            scores=[]
            for digit,refs in self.templates.items():
                score=max(2*(sample&ref).sum()/max(1,sample.sum()+ref.sum()) for ref in refs)
                scores.append((score,digit))
            scores.sort(reverse=True)
            if scores[0][0]<.91 or scores[0][0]-scores[1][0]<.06:return None
            digits.append(scores[0][1]);confidence=min(confidence,float(scores[0][0]))
        return dict(value=int(''.join(digits)),unit='CHIPS',raw=''.join(digits),
                    source='reviewed_digit_templates',confidence=round(confidence,4))
