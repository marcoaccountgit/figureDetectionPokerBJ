"""Prepare manually reviewed browser-capture frames with native FFmpeg decoding.

Browser recordings can change coded resolution mid-stream. Decode each reviewed
timestamp at its native size, remove only black side margins, and scale the game
uniformly to the existing table profile. Predictions are never used as labels.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess

from card_detector import cv2, np
from download_model import file_digest
from prepare_table_dataset import annotations_for, stable_indices, write_sample


def canonical_frame(frame):
    columns = np.flatnonzero((frame.max(axis=2) > 20).sum(axis=0) > frame.shape[0] * .1)
    if not len(columns):
        raise ValueError('Empty capture: no game content')
    image = frame[:, columns[0]:columns[-1]+1]
    height = round(image.shape[0] * 1762 / image.shape[1])
    if height > 1100 or height < 840:
        raise ValueError('Unexpected game proportions; review capture alignment')
    image = cv2.resize(image, (1762, height))
    canvas = np.zeros((1100, 1762, 3), np.uint8)
    canvas[:height] = image
    return canvas


def read_frame(ffmpeg, video, timestamp):
    output = subprocess.run(
        [str(ffmpeg), '-nostdin', '-hide_banner', '-loglevel', 'error',
         '-ss', str(timestamp), '-i', str(video), '-frames:v', '1',
         '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'],
        check=True, capture_output=True, timeout=60).stdout
    frame = cv2.imdecode(np.frombuffer(output, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f'Cannot decode capture at {timestamp}')
    return canonical_frame(frame)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--annotations', type=Path, required=True)
    parser.add_argument('--replay', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path)
    args = parser.parse_args()
    ffmpeg = args.ffmpeg or shutil.which('ffmpeg')
    if not ffmpeg:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    spec = json.loads(args.annotations.read_text())
    if file_digest(args.video) != spec['source_sha256']:
        raise ValueError('Capture differs from manually reviewed source')
    hands = {}
    for entry in spec['frames']:
        if entry['split'] not in ('train', 'val', 'test'):
            raise ValueError('Unknown split')
        if hands.setdefault(entry['hand'], entry['split']) != entry['split']:
            raise ValueError('A hand crosses dataset splits')
    data = json.loads((args.replay / 'data.yaml').read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    for kind in ('images', 'labels'):
        for split in ('train', 'val', 'test'):
            shutil.copytree(args.replay / kind / split, args.output / kind / split)
    reviewed = args.output / 'reviewed'
    reviewed.mkdir()
    inventory, skipped = [], 0
    x1, y1, x2, y2 = spec['crop']
    for entry in spec['frames']:
        reference = read_frame(ffmpeg, args.video, entry['time'])
        labels = annotations_for(entry, spec, data['names'])
        # Lossless full frames are retained for end-to-end evaluation, including
        # potential false detections outside the training crop.
        cv2.imwrite(str(reviewed / f"{entry['time']}.png"), reference)
        offsets = (-.4, -.2, 0, .2, .4) if entry['split'] == 'train' else (0,)
        for offset in offsets:
            t = round(entry['time'] + offset, 1)
            frame = reference if offset == 0 else read_frame(ffmpeg, args.video, t)
            if offset and not stable_indices(reference, frame, entry, spec):
                skipped += 1
                continue
            stem = f'capture10_{t:.1f}'
            write_sample(args.output, entry['split'], stem, frame[y1:y2, x1:x2], labels)
            inventory.append(dict(file=stem, time=t, hand=entry['hand'],
                                  split=entry['split'], codes=entry['board']+entry['hole']))
    data['path'] = args.output.resolve().as_posix()
    (args.output / 'data.yaml').write_text(json.dumps(data, indent=2))
    manifest = dict(source=args.video.name, source_sha256=spec['source_sha256'],
                    annotations_sha256=file_digest(args.annotations),
                    replay_manifest_sha256=file_digest(args.replay / 'manifest.json'),
                    protocol='Manually reviewed capture; splits by hand. Native FFmpeg decode, black side margins removed, uniform game scaling to 1762px. Stable neighbours only in training. Original replay and splits retained.',
                    added_frames_by_split=dict(Counter(e['split'] for e in inventory)),
                    skipped_unstable_neighbours=skipped, real=inventory)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k != 'real'}, indent=2))


if __name__ == '__main__':
    main()
