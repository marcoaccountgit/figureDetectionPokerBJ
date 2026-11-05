"""Local visual extraction of PokerStars positions, actions and amounts.

Reads observations only: never recommends, chooses or executes poker actions.
"""
import json
from copy import deepcopy
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
from time import monotonic

from card_detector import cv2, np

ROOT = Path(__file__).resolve().parent
CLOCKWISE = ('top','upper_right','lower_right','hero','lower_left','upper_left')
NAME_REGIONS = {
    'top': (710,145,950,250), 'upper_right': (1270,310,1510,425),
    'lower_right': (1270,580,1510,685), 'hero': (810,695,1080,820),
    'lower_left': (250,580,495,685), 'upper_left': (250,310,495,425),
}
BET_REGIONS = {
    'top': (820,255,915,310), 'upper_right': (1150,335,1225,395),
    'lower_right': (1100,595,1225,665), 'hero': (905,640,1050,690),
    'lower_left': (545,595,650,665), 'upper_left': (545,335,650,395),
}
SEAT_CENTRES = {'top': (880,195), 'upper_right': (1400,365),
                'lower_right': (1400,620), 'hero': (950,755),
                'lower_left': (365,620), 'upper_left': (365,365)}


class WindowsOCR:
    """Persistent native OCR worker, with bounded waits and no image uploads."""
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('OCR nativo disponibile su Windows; usare un backend OCR compatibile su altri sistemi')
        self.directory = tempfile.TemporaryDirectory(prefix='poker-table-ocr-')
        self.responses = queue.Queue()
        self.sequence = 0
        self.process = subprocess.Popen(
            ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'windows_ocr_worker.ps1')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
        self.reader = threading.Thread(target=self._read,daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            try:
                self.responses.put(json.loads(line))
            except json.JSONDecodeError:
                self.responses.put({'error':'Risposta OCR Windows non valida'})
        self.responses.put({'error':'Il processo OCR Windows si e chiuso'})

    def recognize(self, image):
        for previous in Path(self.directory.name).glob('*.png'):
            try:
                previous.unlink()
            except PermissionError:
                pass
        self.sequence += 1
        path = Path(self.directory.name)/f'observation-{self.sequence}.png'
        if not cv2.imwrite(str(path),image):
            raise RuntimeError('Impossibile preparare immagine OCR')
        self.process.stdin.write(json.dumps({'path':str(path)})+'\n')
        self.process.stdin.flush()
        try:
            result = self.responses.get(timeout=25)
        except queue.Empty:
            self.process.kill()
            raise RuntimeError('Timeout OCR Windows') from None
        if result.get('error'):
            raise RuntimeError(result['error'])
        return result

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.reader.join(timeout=1)
        self.directory.cleanup()


def canonical_frame(frame):
    return cv2.resize(frame,(1762,round(frame.shape[0]*1762/frame.shape[1])))


def ocr_mosaic(frame):
    """Enlarge text regions; keep offered buttons separate from performed actions."""
    image = canonical_frame(frame)
    regions = [(f'seat:{key}',box,3) for key,box in NAME_REGIONS.items()]
    regions += [(f'bet:{key}',box,3) for key,box in BET_REGIONS.items()]
    regions += [('pot',(790,315,985,393),3)]
    regions += [(f'option:{i}',(245*i,835,245*(i+1),1010),2) for i in range(3)]
    regions += [('collected_pot',(850,550,1010,610),3)]
    mosaic = np.full((2340,2400,3),255,np.uint8)
    placements = []
    for index,(key,(x,y,right,bottom),scale) in enumerate(regions):
        tile_x,tile_y = (index%3)*800+25,(index//3)*390+20
        crop = image[y:min(bottom,image.shape[0]),x:right]
        if not crop.size:
            continue
        if key.startswith(('option:','bet:')) or key=='collected_pot':
            _,s,v = cv2.split(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV))
            mask = ((s < 100) & (v > 120)).astype(np.uint8)*255
            text = 255-cv2.resize(mask,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
        else:
            gray = cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
            text = np.full_like(gray,255)
            splits = (0,round(gray.shape[0]*.55),gray.shape[0]) if key.startswith('seat:') else (0,gray.shape[0])
            for start,end in zip(splits,splits[1:]):
                _,text[start:end] = cv2.threshold(gray[start:end],0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
        height,width = text.shape
        ink = 255-text
        lines_mask = (cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(100,1))) |
                      cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,120))))
        text[lines_mask > 0] = 255
        mosaic[tile_y:tile_y+height,tile_x:tile_x+width] = cv2.cvtColor(text,cv2.COLOR_GRAY2BGR)
        placements.append(dict(key=key,x=tile_x,y=tile_y,width=width,height=height))
    return mosaic,placements


def group_ocr(result, placements):
    grouped = {p['key']:[] for p in placements}
    for line in result.get('lines',[]):
        by_region = {}
        for word in line.get('words',[]):
            x,y = word['x']+word['width']/2,word['y']+word['height']/2
            for p in placements:
                if p['x'] <= x < p['x']+p['width'] and p['y'] <= y < p['y']+p['height']:
                    by_region.setdefault(p['key'],[]).append(word)
                    break
        for key,words in by_region.items():
            grouped[key].append(' '.join(w['text'] for w in sorted(words,key=lambda w:w['x'])))
    return grouped


def parse_amount(text):
    """Require an explicit unit; do not guess chips or complete truncated numbers."""
    text = re.sub(r'\s+','',text).upper().replace('€','EUR')
    text = re.sub(r'^[IL](?=[O.,\dB8])','1',text)
    text = re.sub(r'^O(?=[.,B8])','0',text)
    text = re.sub(r'(?<=\d)O(?=[\d.,B8]|$)','0',text)
    match = re.fullmatch(r'(\d+(?:[.,]\d+)?)(BB|B8|8B|88|EUR)',text)
    if not match:
        return None
    return dict(value=float(match[1].replace(',','.')),unit='EUR' if match[2]=='EUR' else 'BB',raw=text)


ACTION_WORDS = {'check':'check','fold':'fold','passa':'fold','vedi':'call','call':'call',
                'puntata':'bet','punta':'bet','bet':'bet','rilancia':'raise','raise':'raise',
                'all-in':'all_in','allin':'all_in','all in':'all_in'}


def parse_action(text):
    normalized = re.sub(r'\s+',' ',text.strip().lower())
    for word,action in sorted(ACTION_WORDS.items(),key=lambda p:-len(p[0])):
        if normalized == word or normalized.startswith(word+' '):
            return action
    return None


def positions_from_button(button, dealt):
    """Assign positions from seats dealt into the hand, never the remaining count."""
    if button not in dealt or len(dealt) < 2 or len(set(dealt)) != len(dealt):
        return {}
    order = [CLOCKWISE[(CLOCKWISE.index(button)+i)%6] for i in range(6)]
    order = [seat for seat in order if seat in dealt]
    labels = {2:['BTN/SB','BB'],3:['BTN','SB','BB'],4:['BTN','SB','BB','UTG'],
              5:['BTN','SB','BB','UTG','CO'],6:['BTN','SB','BB','UTG','HJ','CO']}[len(order)]
    return dict(zip(order,labels))


def yellow_action_glyph(canonical, seat):
    x,y,right,bottom = NAME_REGIONS[seat]
    # All-in is displayed on the stack line rather than the name line.
    header = canonical[y:bottom,x:right]
    hue,saturation,value = cv2.split(cv2.cvtColor(header,cv2.COLOR_BGR2HSV))
    mask = ((hue >= 20)&(hue <= 40)&(saturation > 100)&(value > 120)).astype(np.uint8)
    count,labels,stats,_ = cv2.connectedComponentsWithStats(mask,8)
    clean = np.zeros_like(mask)
    for index in range(1,count):
        if stats[index,cv2.CC_STAT_AREA] >= 6:
            clean[labels==index] = 1
    points = cv2.findNonZero(clean)
    if points is None or clean.sum() < 25:
        return None
    x,y,width,height = cv2.boundingRect(points)
    return clean[y:y+height,x:x+width]*255


class ActionTemplates:
    def __init__(self):
        self.references = []
        for path in sorted((ROOT/'assets/table-observer/actions').glob('*.png')):
            mask = cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
            self.references.append((path.stem,mask.shape[1]/mask.shape[0],cv2.resize(mask,(192,40)) > 100))

    def classify(self, glyph):
        if glyph is None:
            return None
        aspect = glyph.shape[1]/glyph.shape[0]
        sample = cv2.resize(glyph,(192,40)) > 100
        scores = []
        for name,reference_aspect,reference in self.references:
            if not .7 <= aspect/reference_aspect <= 1.4:
                continue
            score = float(2*np.sum(sample & reference)/(sample.sum()+reference.sum()))
            scores.append((score,name))
        scores.sort(reverse=True)
        if scores and scores[0][0] >= .85 and (len(scores)==1 or scores[0][0]-scores[1][0] >= .08):
            return dict(action=scores[0][1],score=round(scores[0][0],4))
        return None


class TableVisualReader:
    def __init__(self, ocr):
        self.ocr = ocr
        template = cv2.imread(str(ROOT/'assets/table-observer/dealer-button.png'))
        if template is None:
            raise RuntimeError('Riferimento del bottone mancante')
        self.button_template = cv2.cvtColor(template,cv2.COLOR_BGR2GRAY)
        self.action_templates = ActionTemplates()

    def dealer_button(self, frame):
        image = canonical_frame(frame)
        if image.shape[0] < 840:
            return dict(seat=None,score=0)
        roi = cv2.cvtColor(image[150:840],cv2.COLOR_BGR2GRAY)
        _,score,_,location = cv2.minMaxLoc(cv2.matchTemplate(roi,self.button_template,cv2.TM_CCOEFF_NORMED))
        x,y = location[0]+20,location[1]+150+19
        key = min(SEAT_CENTRES,key=lambda k:(SEAT_CENTRES[k][0]-x)**2+(SEAT_CENTRES[k][1]-y)**2)
        return dict(seat=key if score >= .75 else None,score=round(score,4))

    def read(self, frame):
        mosaic,placements = ocr_mosaic(frame)
        canonical = canonical_frame(frame)
        result = self.ocr.recognize(mosaic)
        grouped = group_ocr(result,placements)
        seats = []
        for key in CLOCKWISE:
            lines = grouped.get('seat:'+key,[])
            bets = grouped.get('bet:'+key,[])
            stack = next((v for line in reversed(lines) if (v:=parse_amount(line))),None)
            glyph = yellow_action_glyph(canonical,key)
            yellow_label = glyph is not None
            action = next((a for line in lines if (a:=parse_action(line))),None) if yellow_label else None
            template_action = self.action_templates.classify(glyph)
            if template_action:
                action = template_action['action'] if action in (None,template_action['action']) else None
            name = next((line for line in lines if not parse_amount(line) and not (action and parse_action(line))
                         and not any(term in line.lower() for term in ('sit out','libero','posto'))),None)
            seats.append(dict(seat=key,name=name,action=action,stack=stack,
                              wager=next((v for line in bets if (v:=parse_amount(line))),None),
                              empty=any('libero' in line.lower() for line in lines),
                              sit_out='sit out' in ' '.join(lines).lower(),raw_text=lines,raw_wager=bets,
                              yellow_action_label=yellow_label,action_template=template_action))
        pot = contribution = None
        for line in grouped.get('pot',[]):
            match = re.match(r'(?i)\s*(pot|contributo)\s*[:;]?\s*(.*)',line)
            if match:
                if match[1].lower()=='pot':
                    pot = parse_amount(match[2])
                else:
                    contribution = parse_amount(match[2])
        options = []
        for key,lines in grouped.items():
            if not key.startswith('option:'):
                continue
            actions = [(line,parse_action(line)) for line in lines if parse_action(line)]
            amounts = [value for line in lines if (value:=parse_amount(line))]
            for line,action in actions:
                options.append(dict(text=line,action=action,
                                    amount=amounts[0] if len(actions)==1 and len(amounts)==1 else None))
        collected_values = [value for line in grouped.get('collected_pot',[]) if (value:=parse_amount(line))]
        collected_pot = collected_values[0] if len(collected_values)==1 else None
        return dict(button=self.dealer_button(frame),seats=seats,pot=pot,contribution=contribution,
                    collected_pot=collected_pot,raw_collected_pot=grouped.get('collected_pot',[]),
                    available_actions=options,ocr_language=result.get('language'),raw_pot=grouped.get('pot',[]))


def amount_key(value):
    return (value['value'],value['unit']) if value else None


class TableStateTracker:
    """Keep confirmed observations and a deduplicated log of displayed actions.

    Missing/transient labels are not reconstructed as if they were observed.
    Counts/positions are frozen to the observed deal, not changed after folds.
    """
    def __init__(self):
        self.hand_id = None
        self.candidates = {}
        self.events = []
        self.last_actions = {}
        self.names = {}
        self.dealt = []
        self.last_timestamp = None
        self.closed = False
        self.deal_complete = False
        self.event_sequence = 0
        self.hand_button = None
        self.street_pots = {}
        self.highest_street = 0

    def confirm(self, key, value, timestamp):
        if value is None:
            self.candidates.pop(key,None)
            return None
        signature = json.dumps(value,sort_keys=True)
        old = self.candidates.get(key)
        if old is None or old['signature'] != signature:
            self.candidates[key] = dict(signature=signature,samples=1,since=timestamp)
            return None
        old['samples'] += 1
        return value if old['samples'] >= 2 and timestamp-old['since'] >= .1 else None

    def update(self, observation, context, timestamp):
        hand_id = context.get('hand_id',0)
        street = context.get('street','unknown')
        if hand_id != self.hand_id:
            self.hand_id = hand_id
            self.candidates.clear()
            self.events = []
            self.last_actions.clear()
            self.dealt = list(context.get('dealt_seats',[]))
            self.closed = False
            self.deal_complete = False
            self.event_sequence = 0
            self.hand_button = None
            self.street_pots = {}
            self.highest_street = 0
        if self.last_timestamp is not None and (timestamp <= self.last_timestamp or timestamp-self.last_timestamp > 2):
            self.candidates.clear()
        self.last_timestamp = timestamp
        if context.get('ended') or (hand_id > 0 and not context.get('active',True)):
            self.closed = True
        button = self.confirm('button',observation['button']['seat'],timestamp)
        if self.hand_button is None and hand_id > 0 and context.get('active') and button:
            self.hand_button = button
        same_deal = self.hand_button is None or button is None or button == self.hand_button
        estimated_positions = positions_from_button(button,self.dealt) if button else {}
        # Only a complete captured deal can make SB/BB/etc authoritative.
        position_complete = bool(button) and (self.deal_complete or bool(context.get('deal_complete')))
        if not same_deal:
            estimated_positions = {}
            position_complete = False
        rows = []
        for row in observation['seats']:
            key = row['seat']
            name = self.confirm(key+':name',row['name'],timestamp)
            if name:
                self.names[key] = name
            stack = self.confirm(key+':stack',amount_key(row['stack']),timestamp)
            wager = self.confirm(key+':wager',amount_key(row['wager']),timestamp)
            action = self.confirm(key+':action',row['action'],timestamp)
            empty = self.confirm(key+':empty',row['empty'],timestamp) is True
            sit_out = self.confirm(key+':sit_out',row['sit_out'],timestamp) is True
            if name and not row['action'] and not row.get('yellow_action_label',False):
                self.last_actions.pop(key,None)
            if action and (not self.closed or (key=='hero' and action=='fold')) and self.last_actions.get(key) != action:
                self.event_sequence += 1
                self.events.append(dict(index=self.event_sequence,hand_id=hand_id,street=street,
                                        seat=key,action=action,amount=row['wager'] if wager and action not in ('check','fold') else None,
                                        amount_kind=('not_applicable' if action in ('check','fold') else
                                                     'street_total' if wager else None),
                                        captured_at=timestamp,source='displayed_action_label'))
                self.events = self.events[-100:]
                self.last_actions[key] = action
            elif action and wager and action not in ('check','fold'):
                previous = next((event for event in reversed(self.events) if event['seat']==key),None)
                if previous and previous['action']==action and previous['amount'] is None:
                    previous['amount'],previous['amount_kind'] = row['wager'],'street_total'
            # A confirmed different label/amount re-arms the next event; plain
            # OCR loss does not, to avoid duplicate events after a missed read.
            rows.append(dict(row,name=name or self.names.get(key),
                             stack=row['stack'] if stack else None,
                             wager=row['wager'] if wager else None,
                             action=action,empty=empty,sit_out=sit_out,
                             position=(estimated_positions.get(key) if position_complete else
                                       'BTN' if key==button else None),
                             position_estimate=estimated_positions.get(key)))
        if button and same_deal and street=='preflop' and self.dealt and all(row['seat'] in self.dealt or row['empty'] or row['sit_out'] for row in rows):
            self.deal_complete = True
            position_complete = True
            for row in rows:
                row['position'] = estimated_positions.get(row['seat'])
        pot = self.confirm('pot',amount_key(observation['pot']),timestamp)
        contribution = self.confirm('contribution',amount_key(observation['contribution']),timestamp)
        collected = self.confirm('collected_pot',amount_key(observation.get('collected_pot')),timestamp)
        confirmed_street = self.confirm('street',street if street in ('preflop','flop','turn','river') else None,timestamp)
        can_record = (hand_id > 0 and same_deal and
                      (context.get('active',True) or (button is not None and button==self.hand_button)))
        street_order = {'flop':1,'turn':2,'river':3}.get(confirmed_street,0)
        if can_record and street_order and street_order >= self.highest_street:
            self.highest_street = street_order
            record = self.street_pots.setdefault(confirmed_street,dict(first_total=None,first_collected=None,
                                                                      last_total=None,last_collected=None))
            for kind,valid,value in [('total',pot,observation['pot']),
                                     ('collected',collected,observation.get('collected_pot'))]:
                if valid:
                    if record['first_'+kind] is None:
                        record['first_'+kind] = deepcopy(value)
                        record['first_'+kind+'_at'] = timestamp
                    record['last_'+kind] = deepcopy(value)
                    record['last_'+kind+'_at'] = timestamp
        return dict(status='ready',hand_id=hand_id,street=street,button=button,
                    button_score=observation['button']['score'],positions_complete=position_complete,
                    seats=rows,pot=observation['pot'] if pot else None,
                    contribution=observation['contribution'] if contribution else None,
                    collected_pot=observation.get('collected_pot') if collected else None,
                    street_pots=deepcopy(self.street_pots),
                    available_actions=observation['available_actions'],events=deepcopy(self.events),
                    history_complete=False,
                    ocr_language=observation['ocr_language'],
                    observation_policy='No inferred actions from offered buttons, absent cards or missing OCR; amounts require explicit units.')


class TableObservationService:
    """OCR in the background; at most one pending frame, never block capture."""
    def __init__(self, reader_factory=None, interval=.4):
        self.reader_factory = reader_factory or (lambda:TableVisualReader(WindowsOCR()))
        self.interval = interval
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.stop_event = threading.Event()
        self.pending = None
        self.scope = None
        self.desired_hand = None
        self.latest = dict(status='starting')
        self.last_submit = -float('inf')
        self.completed = 0
        self.reader = None
        self.thread = threading.Thread(target=self._run,daemon=True,name='poker-table-observer')
        self.thread.start()

    def submit(self, frame, context):
        now = monotonic()
        scope = (context['capture_session'],tuple(context['viewport']))
        with self.lock:
            if scope != self.scope or context.get('hand_id') != self.desired_hand:
                self.latest = dict(status='pending',hand_id=context.get('hand_id'))
                self.last_submit = -float('inf')
                self.scope, self.desired_hand = scope, context.get('hand_id')
            if now-self.last_submit >= self.interval:
                self.pending = (scope,frame.copy(),dict(context),now)
                self.last_submit = now
                self.wake.set()
            result = dict(self.latest)
            if result['status']=='ready':
                result['age_ms'] = round((now-self.completed)*1000)
                if now-self.completed > 2:
                    result['status'] = 'stale'
            return result

    def _run(self):
        tracker = TableStateTracker()
        previous_scope = None
        try:
            while not self.stop_event.is_set():
                self.wake.wait()
                self.wake.clear()
                if self.stop_event.is_set():
                    break
                with self.lock:
                    request,self.pending = self.pending,None
                if request is None:
                    continue
                scope,frame,context,timestamp = request
                if scope != previous_scope:
                    tracker = TableStateTracker()
                    previous_scope = scope
                try:
                    if self.reader is None:
                        self.reader = self.reader_factory()
                    observation = self.reader.read(frame)
                    result = tracker.update(observation,context,timestamp)
                    result['ocr_processing_ms'] = round((monotonic()-timestamp)*1000)
                except Exception as error:
                    result = dict(status='error',error=str(error),hand_id=context.get('hand_id'))
                with self.lock:
                    if scope == self.scope and context.get('hand_id') == self.desired_hand:
                        self.latest = result
                        self.completed = timestamp
        finally:
            if self.reader and hasattr(self.reader,'ocr'):
                self.reader.ocr.close()

    def close(self):
        self.stop_event.set()
        self.wake.set()
        if self.reader and hasattr(self.reader,'ocr') and self.reader.ocr.process.poll() is None:
            self.reader.ocr.process.kill()
        self.thread.join(timeout=4)
