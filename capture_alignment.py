"""Remove near-black browser side bars before applying the calibrated model."""
from card_detector import np


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
