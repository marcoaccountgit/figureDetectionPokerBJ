"""Cheap occupancy checks before rerunning card identity recognition."""
from card_detector import cv2, np
from opponent_detector import SEATS
from table_profiles import is_desktop, desktop_layout


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
    slot always requests recognition, including repeated attempts after an OCR
    miss. Missing/occluded faces and possible showdowns also request recognition.
    """
    info = dict(inference_skipped=False, locked_slots=len(memory.cards))
    if not active or not all(('player_hand', slot) in memory.cards for slot in range(2)):
        return True, dict(info, reason='hand_not_confirmed')
    if len(presence) != 2 or not all(s.get('present') is True for s in presence):
        return True, dict(info, reason='hand_presence_changed')
    board = {slot for group, slot in memory.cards if group == 'board'}
    if len(board) not in (0, 3, 4, 5) or board != set(range(len(board))):
        return True, dict(info, reason='board_confirmation_pending')
    x, step, y = (654, 101, 395) if is_desktop(profile) else (615, 116, 441)
    # A fast deal can happen between scans: the hero never appears empty.
    # Require exposed felt across the entire old board, not one OCR miss.
    if len(board) >= 3:
        cleared = True
        scale = frame.shape[1] / 1762
        for slot in sorted(board):
            cx = x + step * slot
            left, top, right, bottom = [round(v * scale) for v in (cx - 24, y - 30, cx + 26, y + 35)]
            patch = frame[top:bottom, left:right]
            if patch.shape[:2] != (bottom-top, right-left) or not patch.size:
                cleared = False
                break
            h, s, v = cv2.split(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV))
            felt = np.mean((h > 30) & (h < 100) & (s > 65) & (v > 35))
            if felt < .6 or np.mean((s < 85) & (v > 170)) > .08:
                cleared = False
                break
        if cleared:
            return True, dict(info, reason='board_cleared', board_cleared=True)
    for slot in range(5):
        cx = x + step * slot
        white = white_fraction(frame, (cx - 24, y - 30, cx + 26, y + 35))
        if white is None or (slot in board and white < .20):
            return True, dict(info, reason='board_presence_changed')
        if slot not in board and white >= .20:
            return True, dict(info, reason='new_board_card', new_slot=slot)
    # Keep reading exposed opponent cards at showdown, even with a locked river.
    boxes = desktop_layout(profile)['backs'].values() if is_desktop(profile) else [s[2] for s in SEATS]
    for box in boxes:
        white = white_fraction(frame, box)
        if white is not None and white >= .25:
            return True, dict(info, reason='possible_opponent_showdown')
    return False, dict(info, inference_skipped=True, reason='confirmed_slots_unchanged')
