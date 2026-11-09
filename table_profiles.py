"""Reviewed geometry for the two independent PokerStars table graphics."""
from functools import lru_cache
from pathlib import Path
from card_detector import cv2

ROOT=Path(__file__).resolve().parent
NINE='pokerstars-nine'
DESKTOP_SIX='pokerstars-desktop-six'
NINE_ORDER=('top_left','top_right','upper_right','middle_right','lower_right',
            'hero','lower_left','middle_left','upper_left')


def canonical_box(box):
    return tuple(round(v*1762/1918) for v in box)


NINE_NAMES={key:canonical_box(box) for key,box in {
    'top_left':(535,135,744,231),'top_right':(1185,135,1380,231),
    'upper_left':(238,243,444,340),'upper_right':(1465,243,1673,340),
    'middle_left':(175,462,384,560),'middle_right':(1530,462,1745,560),
    'lower_left':(337,690,544,788),'lower_right':(1385,690,1590,788),
    'hero':(804,791,1015,889)}.items()}
NINE_BETS={key:canonical_box(box) for key,box in {
    'top_left':(735,276,990,325),'top_right':(958,244,1250,294),
    'upper_left':(527,344,805,396),'upper_right':(1125,306,1400,359),
    'middle_left':(485,516,810,575),'middle_right':(1115,516,1430,575),
    'lower_left':(589,598,818,652),'lower_right':(1070,598,1320,652),
    'hero':(825,648,1020,700)}.items()}
NINE_CENTRES={key:((box[0]+box[2])/2,(box[1]+box[3])/2) for key,box in NINE_NAMES.items()}
NINE_BACKS={key:canonical_box(box) for key,box in {
    'top_left':(582,78,806,143),'top_right':(1112,78,1340,143),
    'upper_left':(287,184,517,249),'upper_right':(1405,184,1635,249),
    'middle_left':(220,403,451,470),'middle_right':(1472,403,1702,470),
    'lower_left':(377,628,608,701),'lower_right':(1315,628,1545,701)}.items()}
NINE_HERO=[canonical_box(box) for box in ((862,722,896,786),(966,722,1000,786))]


def is_desktop(profile):
    return profile in (NINE,DESKTOP_SIX)


SIX_NAMES={key:canonical_box(box) for key,box in {
    'top':(800,135,1008,231),'upper_left':(238,243,444,340),
    'upper_right':(1465,243,1673,340),'lower_left':(195,582,405,688),
    'lower_right':(1516,582,1724,688),'hero':(915,791,1135,915)}.items()}
SIX_BACKS={key:canonical_box(box) for key,box in {
    'top':(844,78,1075,145),'upper_left':(287,184,517,249),
    # Six-seat backs extend left of the nine-seat search region. Keep both
    # white card borders inside the ROI at small desktop-window sizes.
    'upper_right':(1370,184,1665,249),'lower_left':(210,525,475,615),
    'lower_right':(1440,525,1710,615)}.items()}
SIX_BETS={key:canonical_box(box) for key,box in {
    'top':(825,250,1130,325),'upper_left':(527,344,805,396),
    'upper_right':(1125,306,1400,405),'lower_left':(480,525,810,652),
    'lower_right':(1080,525,1430,652),'hero':(825,648,1020,700)}.items()}


def desktop_layout(profile):
    if profile==DESKTOP_SIX:
        return dict(names=SIX_NAMES,backs=SIX_BACKS,bets=SIX_BETS,
                    order=('top','upper_right','lower_right','hero','lower_left','upper_left'),
                    centres={k:((b[0]+b[2])/2,(b[1]+b[3])/2) for k,b in SIX_NAMES.items()})
    return dict(names=NINE_NAMES,backs=NINE_BACKS,bets=NINE_BETS,order=NINE_ORDER,centres=NINE_CENTRES)


def desktop_stack_box(profile,seat):
    x,y,right,bottom=desktop_layout(profile)['names'][seat]
    # The six-seat hero HUD has extra space below the stack. A halfway split
    # of that taller box cuts the top off digits and the "All-in" label.
    fraction=.42 if profile==DESKTOP_SIX and seat=='hero' else .53
    return x,round(y+(bottom-y)*fraction),right,bottom


@lru_cache(maxsize=1)
def desktop_six_hud_edges():
    return [cv2.imread(str(ROOT/'assets/table-desktop-six'/name),cv2.IMREAD_GRAYSCALE)
            for name in ('top-hud-edge.png','top-hud-edge-active.png','top-hud-edge-focus.png')]


def desktop_seat_profile(frame, previous=None):
    native=cv2.resize(frame,(1918,round(frame.shape[0]*1918/frame.shape[1])))
    roi=native[145:225,875:1005]
    # A centred capsule HUD distinguishes the six-seat desktop table from the
    # two separated upper HUDs of the nine-seat table, independently of names.
    if roi.shape[:2]!=(80,130):return NINE
    # Two separated top capsules are stronger evidence than a spurious
    # six-seat edge match against a dimmed all-in avatar or action highlight.
    left=native[145:225,535:744];right=native[145:225,1185:1380]
    if ((left.max(axis=2)<32).mean()>.35 and (right.max(axis=2)<32).mean()>.35):
        return NINE
    if (roi.max(axis=2)<32).mean()>.55:return DESKTOP_SIX
    # Action highlights brighten the capsule. Its curved edge remains a
    # geometric reference even when an absolute darkness test fails.
    gray=cv2.cvtColor(native,cv2.COLOR_BGR2GRAY)
    search=gray[110:255,762:862]
    for reference in desktop_six_hud_edges():
        if reference is not None and search.shape[0]>=reference.shape[0] and search.shape[1]>=reference.shape[1]:
            if cv2.minMaxLoc(cv2.matchTemplate(search,reference,cv2.TM_CCOEFF_NORMED))[1]>=.6:
                return DESKTOP_SIX
    if previous==DESKTOP_SIX:
        # Waiting/seat-change animations can hide every opponent HUD. Do not
        # infer a larger table from the absence of the central capsule.
        left=native[145:225,535:744];right=native[145:225,1185:1380]
        if not ((left.max(axis=2)<32).mean()>.35 and (right.max(axis=2)<32).mean()>.35):
            return previous
    return NINE


@lru_cache(maxsize=1)
def desktop_rail():
    return cv2.imread(str(ROOT/'assets/table-nine/rail-anchor.png'),cv2.IMREAD_GRAYSCALE)


@lru_cache(maxsize=1)
def desktop_alternative_rails():
    return [(cv2.imread(str(ROOT/'assets/table-nine'/('rail-'+name+'.png')),cv2.IMREAD_GRAYSCALE),point)
            for name,point in (('upper-left',(600,285)),('upper-right',(1120,245)),
                               ('lower-left',(700,735)),('lower-right',(1100,730)))]


def _match_desktop_rail(gray,template,point,estimated,cx,cy):
    from card_detector import np
    if template is None:return None
    ax,ay=point;best=None
    for factor in np.linspace(.85,1.15,31):
        scale=estimated*float(factor)
        tw,th=round(template.shape[1]*scale),round(template.shape[0]*scale)
        if min(tw,th)<5:continue
        expected_x=cx+(ax-959)*scale;expected_y=cy+(ay-515.5)*scale
        pad=round(20*scale)+5
        left=max(0,round(expected_x-pad));top=max(0,round(expected_y-pad))
        right=min(gray.shape[1],round(expected_x+tw+pad));bottom=min(gray.shape[0],round(expected_y+th+pad))
        search=gray[top:bottom,left:right]
        if search.shape[0]<th or search.shape[1]<tw:continue
        ref=cv2.resize(template,(tw,th),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR)
        _,score,_,location=cv2.minMaxLoc(cv2.matchTemplate(search,ref,cv2.TM_CCOEFF_NORMED))
        if best is None or score>best[0]:best=(score,scale,left+location[0],top+location[1])
    if best is None:return None
    score,scale,anchor_x,anchor_y=best
    left=round(anchor_x-ax*scale);top=round(anchor_y-ay*scale)
    return (left,top,left+round(1918*scale),top+round(1198*scale)),float(score)


def desktop_table_viewport(frame):
    """Register table artwork, not toolbar size or CSS preview dimensions."""
    from card_detector import np
    template=desktop_rail()
    if template is None:return None
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(35,80,35),(95,255,255))
    # Green avatars can touch the felt through a thin bridge and enlarge its
    # bounding box by an entire seat. Remove these narrow connections before
    # estimating rail scale; identities and names play no part in registration.
    kernel=max(3,round(frame.shape[1]*.015))
    if kernel%2==0:kernel+=1
    initial_contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if initial_contours:
        _,_,felt_width,felt_height=cv2.boundingRect(max(initial_contours,key=cv2.contourArea))
        if felt_width/felt_height>2.3:
            mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(kernel,kernel)))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:return None
    contour=max(contours,key=cv2.contourArea)
    x,y,w,h=cv2.boundingRect(contour);area=cv2.contourArea(contour)
    if area<frame.shape[0]*frame.shape[1]*.035 or not 1.6<w/h<2.6 or not .5<area/(w*h)<.88:return None
    estimated=w/1112;cx=x+w/2;cy=y+h/2
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    primary=_match_desktop_rail(gray,template,(875,230),estimated,cx,cy)
    if primary is not None and primary[1]>=.88:return primary
    # A central HUD or chip stack can cover the primary rail. Require two
    # independent alternative patches to agree before accepting a new pose.
    candidates=[]
    for reference,point in desktop_alternative_rails():
        match=_match_desktop_rail(gray,reference,point,estimated,cx,cy)
        if match is not None and match[1]>=.9:candidates.append(match)
    tolerance=max(8,frame.shape[1]*.025)
    for candidate in sorted(candidates,key=lambda c:c[1],reverse=True):
        if any(other is not candidate and max(abs(a-b) for a,b in zip(candidate[0],other[0]))<=tolerance
               for other in candidates):return candidate
    return None


@lru_cache(maxsize=1)
def nine_header():
    return cv2.imread(str(ROOT/'assets/table-nine/header.png'),cv2.IMREAD_GRAYSCALE)


def nine_layout_anchor(frame):
    template=nine_header()
    if template is None:return None
    gray=cv2.cvtColor(cv2.resize(frame,(1762,round(frame.shape[0]*1762/frame.shape[1]))),cv2.COLOR_BGR2GRAY)
    search=gray[:min(190,gray.shape[0]),120:min(460,gray.shape[1])]
    if search.shape[0]<template.shape[0] or search.shape[1]<template.shape[1]:return None
    _,score,_,location=cv2.minMaxLoc(cv2.matchTemplate(search,template,cv2.TM_CCOEFF_NORMED))
    # The client inserts an extra toolbar icon without moving the table.
    if score<.88 or abs(location[0]+120-170)>80:return None
    return float(score),location[1]-31
