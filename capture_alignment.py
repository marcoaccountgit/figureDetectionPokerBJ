"""Remove near-black browser side bars before applying the calibrated model."""
from pathlib import Path
from card_detector import cv2, np


def align_capture(frame):
    height, width = frame.shape[:2]
    active = np.flatnonzero((frame.max(axis=2) > 32).mean(axis=0) > .15)
    if not len(active):
        raise ValueError('La scheda acquisita e nera: controlla la sorgente.')
    left, right = int(active[0]), int(active[-1])+1
    # Only remove actual side bars, never a large portion of the scene.
    if right-left < width*.65:
        raise ValueError('Area del gioco troppo stretta: controlla la scheda acquisita.')
    if left < 3:
        left = 0
    if width-right < 3:
        right = width
    return frame[:, left:right], (left, 0, right, height)


def extract_viewport(frame,viewport):
    left,top,right,bottom=viewport;h,w=frame.shape[:2]
    image=frame[max(0,top):min(h,bottom),max(0,left):min(w,right)]
    if not image.size:raise ValueError('Il tavolo rilevato è fuori dalla sorgente acquisita')
    return cv2.copyMakeBorder(image,max(0,-top),max(0,bottom-h),max(0,-left),max(0,right-w),
                             cv2.BORDER_CONSTANT,value=0)


class CaptureAligner:
    """Stabilize side bars and register vertical layout shifts to player HUD edges.

    Anchors are card-independent: one HUD edge while cards are exposed, one
    while folded. Small font/layout differences are left alone. A changed
    offset needs three agreeing frames before replacing an established one.
    """
    def __init__(self):
        root = Path(__file__).parent/'assets/alignment'
        self.anchors = []
        for name,box,search_x,threshold in (
                ('player-open-edge',(1042,691,1094,827),(1015,1120),.8),
                ('player-folded-edge',(700,706,742,831),(675,775),.86)):
            image = cv2.imread(str(root/(name+'.png')),cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise RuntimeError('Riferimento di allineamento mancante: '+name)
            self.anchors.append((image,box,search_x,threshold))
        self.bounds = None
        self.source_shape = None
        self.offset = None
        self.pending_offset = None
        self.pending_samples = 0
        self.last_anchor = None
        self.profile = 'pokerstars'
        self.desktop_viewport=None
        self.desktop_shape=None
        self.desktop_pending=None
        self.desktop_samples=0
        self.alignment_ready=True

    def vertical_offset(self, image):
        scale = image.shape[1]/1762
        gray = cv2.cvtColor(cv2.resize(image,(1762,round(image.shape[0]/scale))),cv2.COLOR_BGR2GRAY)
        candidates = []
        for template,box,(left,right),threshold in self.anchors:
            search = gray[450:min(1050,gray.shape[0]),left:right]
            if search.shape[0] < template.shape[0]:
                continue
            _,score,_,location = cv2.minMaxLoc(cv2.matchTemplate(search,template,cv2.TM_CCOEFF_NORMED))
            if score < threshold or abs(location[0]+left-box[0]) > 12:
                continue
            offset = location[1]+450-box[1]
            candidates.append((score,0 if abs(offset)<=16 else offset))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        if len(candidates)>1 and abs(candidates[0][1]-candidates[1][1])>16:
            return None
        return candidates[0]

    def align(self, frame):
        from table_profiles import nine_layout_anchor, NINE,is_desktop,desktop_table_viewport,desktop_seat_profile
        raw_nine = nine_layout_anchor(frame)
        registration=desktop_table_viewport(frame)
        self.alignment_ready=True
        if registration is not None:
            viewport,score=registration
            width=frame.shape[1]
            needs_registration=(raw_nine is None or abs((viewport[2]-viewport[0])/width-1)>.06
                                or abs(viewport[0])>width*.03 or abs(viewport[1])>width*.03)
            if needs_registration:
                shape=frame.shape[:2]
                if self.desktop_viewport is None or shape!=self.desktop_shape:
                    self.desktop_viewport,self.desktop_shape=viewport,shape
                elif max(abs(a-b) for a,b in zip(viewport,self.desktop_viewport))>4:
                    if self.desktop_pending is not None and max(abs(a-b) for a,b in zip(viewport,self.desktop_pending))<=4:
                        self.desktop_samples+=1
                    else:self.desktop_pending,self.desktop_samples=viewport,1
                    if self.desktop_samples>=3:
                        self.desktop_viewport=viewport;self.desktop_pending=None;self.desktop_samples=0
                    else:self.alignment_ready=False
                else:self.desktop_pending=None;self.desktop_samples=0
                viewport=self.desktop_viewport
                game=extract_viewport(frame,viewport)
                self.profile=desktop_seat_profile(game,self.profile)
                self.last_anchor=dict(score=round(score,4),method='table_rail',registered=self.alignment_ready)
                return game,viewport
        if is_desktop(self.profile) and registration is None and raw_nine is None:
            # A lost reference must not silently route desktop pixels to browser
            # coordinates. Keep only the preview; discard analysis until reacquired.
            self.alignment_ready=False
            self.last_anchor=dict(method='table_rail',registered=False,reason='reference_lost')
            viewport=self.desktop_viewport or (0,0,frame.shape[1],frame.shape[0])
            return extract_viewport(frame,viewport),viewport
        if raw_nine is not None:
            # Dark desktop-client wallpaper is content, not a browser side bar.
            viewport = (0,0,frame.shape[1],frame.shape[0])
        else:
            _,viewport = align_capture(frame)
        left,_,right,height = viewport
        shape = frame.shape[:2]
        if self.bounds and self.source_shape == shape:
            old_left,old_right = self.bounds
            if abs(left-old_left)<=3 and abs(right-old_right)<=3:
                left,right = self.bounds
        self.bounds,self.source_shape = (left,right),shape
        horizontal = frame[:,left:right]
        anchor = nine_layout_anchor(horizontal)
        if anchor is not None:
            self.profile = desktop_seat_profile(horizontal,self.profile) if registration is not None else NINE
        else:
            anchor = self.vertical_offset(horizontal)
            if anchor is not None:
                self.profile = 'pokerstars'
        if anchor is not None:
            score,offset = anchor
            self.last_anchor = dict(score=round(score,4),reference_offset_y=offset)
            if self.offset is None:
                self.offset = offset
            elif abs(offset-self.offset)<=4:
                self.pending_offset,self.pending_samples = None,0
            else:
                if self.pending_offset is None or abs(offset-self.pending_offset)>4:
                    self.pending_offset,self.pending_samples = offset,1
                else:
                    self.pending_samples += 1
                if self.pending_samples >= 3:
                    self.offset = self.pending_offset
                    self.pending_offset,self.pending_samples = None,0
        else:
            self.pending_offset,self.pending_samples = None,0
        top = round((self.offset or 0)*(right-left)/1762)
        bottom = max(height,top+round((right-left)*840/1762))
        image=extract_viewport(frame,(left,top,right,bottom))
        return image,(left,top,right,bottom)


def restore_coordinates(result, viewport, source_shape):
    left, top, right, bottom = viewport

    def restore(item):
        item = dict(item)
        if item.get('bbox') is not None:
            item['bbox'] = [v+(left if i%2 == 0 else top) for i,v in enumerate(item['bbox'])]
        if item.get('polygon') is not None:
            item['polygon'] = [[x+left,y+top] for x,y in item['polygon']]
        return item

    result = dict(result)
    for field in ('cards', 'raw_cards', 'board', 'player_hand'):
        if field in result:
            result[field] = [restore(item) for item in result[field]]
    if 'opponents' in result:
        result['opponents'] = dict(result['opponents'], seats=[restore(item) for item in result['opponents']['seats']])
    result['capture_alignment'] = {'viewport': list(viewport),
                                   'source_size': [source_shape[1], source_shape[0]],
                                   'game_size': [right-left, bottom-top]}
    return result
