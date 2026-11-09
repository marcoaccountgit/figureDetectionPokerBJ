"""Cheap occupancy checks before rerunning card identity recognition."""
from card_detector import cv2, np
from table_profiles import is_desktop, NINE_HERO


def white_fraction(frame, box):
    scale = frame.shape[1] / 1762
    left, top, right, bottom = [round(v * scale) for v in box]
    if left < 0 or top < 0 or right > frame.shape[1] or bottom > frame.shape[0]:
        return None
    patch = frame[top:bottom, left:right]
    if not patch.size:
        return None
    _, saturation, value = cv2.split(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV))
    return float(np.mean((saturation < 85) & (value > 170)))


def card_inference_needed(frame, memory, active, presence, profile):
    """Only skip recognition inside a confirmed hand with complete known slots.

    These checks detect card faces, not ranks or suits. An unknown white board
    slot always requests recognition, including repeated attempts after a miss.
    Ambiguous presence does not invalidate a confirmed identity. The hand
    counter, rather than rank recognition, handles disappearance and new deals.
    """
    info = dict(inference_skipped=False, locked_slots=len(memory.cards))
    hero_returned = not active and any(s.get('present') is True for s in presence)
    board = {slot for group, slot in memory.cards if group == 'board'}
    x, step, y = (654, 101, 395) if is_desktop(profile) else (615, 116, 441)
    # A fast deal can happen between scans: the hero never appears empty.
    # A missing turn/river also proves a street reset if the next flop was
    # already dealt between scans. Occlusion must never count as exposed felt.
    if len(board) >= 3:
        cleared_slots = set()
        scale = frame.shape[1] / 1762
        for slot in sorted(board):
            cx = x + step * slot
            left, top, right, bottom = [round(v * scale) for v in (cx - 24, y - 30, cx + 26, y + 35)]
            patch = frame[top:bottom, left:right]
            if patch.shape[:2] != (bottom-top, right-left) or not patch.size:
                continue
            h, s, v = cv2.split(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV))
            felt = np.mean((h > 30) & (h < 100) & (s > 65) & (v > 35))
            if felt >= .6 and np.mean((s < 85) & (v > 170)) <= .08:
                cleared_slots.add(slot)
        if cleared_slots == board or any(slot >= 3 for slot in cleared_slots):
            return True, dict(info, reason='board_cleared', board_cleared=True)
    if hero_returned or (active and not all(('player_hand', slot) in memory.cards for slot in range(2))):
        return True, dict(info, reason='hand_not_confirmed')
    if not active and not memory.cards:
        return True, dict(info, reason='hand_not_confirmed')
    for slot in range(5):
        cx = x + step * slot
        white = white_fraction(frame, (cx - 24, y - 30, cx + 26, y + 35))
        if slot not in board and white is not None and white >= .20:
            return True, dict(info, reason='new_board_card', new_slot=slot)
    return False, dict(info, inference_skipped=True, reason='confirmed_slots_unchanged')


def unconfirmed_card_frame(frame, memory, active, profile, cache_info):
    """Expose only unlocked hero/board slots to the identity recognizer.

    Occupancy, alignment and opponent analysis still use the original image.
    A new cycle must read the original image even before old memory is cleared.
    """
    if not memory.cards or cache_info.get('board_cleared') or (not active and cache_info.get('reason') == 'hand_not_confirmed'):
        return frame
    image = np.zeros_like(frame)
    scale = frame.shape[1] / 1762
    desktop = is_desktop(profile)
    x, step, y = (654, 101, 395) if desktop else (615, 116, 441)
    boxes = [('board', slot, (x + step*slot - 46, y - 65,
                              x + step*slot + 46, y + 65)) for slot in range(5)]
    hero = NINE_HERO if desktop else ((648,650,686,746), (688,662,736,760))
    for slot, (left, top, right, bottom) in enumerate(hero):
        # Partition adjacent hero indices so an unknown slot cannot expose a
        # known neighbour. Allow the client's vertical winning-card animation.
        left_bound = (hero[slot-1][2] + left)/2 if slot else left-20
        right_bound = (right + hero[slot+1][0])/2 if slot+1 < len(hero) else right+20
        boxes.append(('player_hand', slot, (left_bound, top-65, right_bound, bottom+65)))
    for group, slot, box in boxes:
        if (group, slot) in memory.cards:
            continue
        left, top, right, bottom = [round(v*scale) for v in box]
        left, top = max(0,left), max(0,top)
        right, bottom = min(frame.shape[1],right), min(frame.shape[0],bottom)
        image[top:bottom,left:right] = frame[top:bottom,left:right]
    return image
