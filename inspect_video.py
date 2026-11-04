"""Create timestamped contact sheets without uploading the recording."""
import argparse
from pathlib import Path
from card_detector import cv2
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('--step', type=float, default=60)
    parser.add_argument('--output', default='artifacts/inspection')
    args = parser.parse_args()
    if not 0 < args.step < float('inf'):
        parser.error('step must be finite and greater than zero')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit('Cannot open video')
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    print({'width': cap.get(3), 'height': cap.get(4), 'fps': fps, 'duration': duration})
    tiles = []
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if ok:
            cv2.imwrite(str(out / f'{int(t):04d}.jpg'), frame)
            thumb = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            thumb.thumbnail((480, 300))
            tile = Image.new('RGB', (480, 325), '#222222')
            tile.paste(thumb, (0, 25))
            ImageDraw.Draw(tile).text((8, 5), f'{int(t)//60:02d}:{int(t)%60:02d}', fill='white')
            tiles.append(tile)
        t += args.step
    cap.release()
    for start in range(0, len(tiles), 12):
        group = tiles[start:start + 12]
        sheet = Image.new('RGB', (480 * 3, 325 * ((len(group) + 2) // 3)))
        for i, tile in enumerate(group):
            sheet.paste(tile, ((i % 3) * 480, (i // 3) * 325))
        sheet.save(out / f'sheet-{start//12:02d}.jpg')


if __name__ == '__main__':
    main()
