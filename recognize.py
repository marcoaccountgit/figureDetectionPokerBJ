"""Recognize cards in images, recordings, desktop captures, or a webcam."""
import argparse
import json
from pathlib import Path
from time import perf_counter, sleep
from datetime import datetime
from card_detector import Detector, annotate, cv2, np


def positive(value):
    number = float(value)
    if not np.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('must be finite and greater than zero')
    return number


def video_frames(path, start, duration, sample_fps):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f'Cannot open video: {path}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        raise ValueError('Invalid video frame rate')
    first = round(start * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    index = first
    next_time = start
    try:
        while duration is None or index / fps < start + duration:
            if not cap.grab():
                break
            timestamp = index / fps
            if timestamp + 1e-7 >= next_time:
                ok, frame = cap.retrieve()
                if not ok:
                    raise RuntimeError(f'Cannot decode frame at {timestamp:.3f}s')
                yield timestamp, frame
                next_time = timestamp + 1 / sample_fps
            index += 1
    finally:
        cap.release()


def screen_frames(bbox, sample_fps, duration):
    from PIL import ImageGrab
    start = perf_counter()
    while duration is None or perf_counter() - start < duration:
        cycle = perf_counter()
        rgb = np.array(ImageGrab.grab(bbox=tuple(bbox) if bbox else None))
        yield cycle - start, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        sleep(max(0, 1 / sample_fps - (perf_counter() - cycle)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--video', type=Path)
    source.add_argument('--image', type=Path)
    source.add_argument('--screen', action='store_true')
    source.add_argument('--camera', type=int, metavar='INDEX', help='Webcam index, usually 0')
    parser.add_argument('--card-layout', choices=('corner', 'casino'), default='corner',
                        help='Template webcam detector: ordinary corner index or casino card face')
    parser.add_argument('--detector', choices=('model', 'templates'),
                        help='Default: trained model for webcam, templates for other sources')
    parser.add_argument('--profile', choices=('general', 'pokerstars'), default='general',
                        help='Trained model profile; pokerstars uses its calibrated table crop')
    parser.add_argument('--temporal', action=argparse.BooleanOptionalAction, default=None,
                        help='Confirm across frames; default on for PokerStars streams at >=2 fps')
    parser.add_argument('--preview', action=argparse.BooleanOptionalAction, default=None,
                        help='Live window; enabled by default for webcam')
    parser.add_argument('--bbox', nargs=4, type=int, metavar=('LEFT', 'TOP', 'RIGHT', 'BOTTOM'))
    parser.add_argument('--select-region', action='store_true', help='Select the game area from a screenshot before capture')
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--duration', type=positive)
    parser.add_argument('--fps', type=positive, default=10)
    parser.add_argument('--output', type=Path, default=Path('artifacts/run'))
    parser.add_argument('--save-every', type=int, help='JPEG interval; default 0 for webcam, 100 otherwise')
    args = parser.parse_args()
    is_camera = args.camera is not None
    if args.save_every is None:
        args.save_every = 0 if is_camera else 100
    if is_camera and args.camera < 0:
        parser.error('camera index must be nonnegative')
    if not np.isfinite(args.start) or args.start < 0 or args.save_every < 0:
        parser.error('start and save-every must be nonnegative')
    if args.bbox and (not args.screen or args.bbox[2] <= args.bbox[0] or args.bbox[3] <= args.bbox[1]):
        parser.error('bbox requires --screen and positive dimensions')
    if args.select_region:
        if not args.screen or args.bbox:
            parser.error('--select-region requires --screen and cannot be combined with --bbox')
        from preview import select_screen_region
        try:
            args.bbox = select_screen_region()
        except (RuntimeError, OSError) as error:
            parser.exit(1, str(error) + '\n')
        if args.bbox is None:
            return
    detector_mode = args.detector or ('model' if is_camera else 'templates')
    if args.profile != 'general' and detector_mode != 'model':
        parser.error('--profile pokerstars requires --detector model')
    temporal_enabled = args.temporal if args.temporal is not None else (
        detector_mode == 'model' and args.profile == 'pokerstars' and not args.image and args.fps >= 2)
    if temporal_enabled and (args.image or detector_mode != 'model' or args.fps < 2):
        parser.error('--temporal requires a model stream and --fps >= 2')
    temporal = None
    if temporal_enabled:
        from temporal_cards import TemporalCards
        temporal = TemporalCards()
    try:
        if detector_mode == 'model':
            from learned_detector import LearnedCardDetector
            detector = LearnedCardDetector(profile=args.profile)
        elif is_camera:
            from webcam import CameraDetector
            detector = CameraDetector(layout=args.card_layout)
        else:
            detector = Detector()
    except (RuntimeError, ValueError, OSError, cv2.error) as error:
        parser.exit(1, str(error) + '\n')
    if is_camera:
        args.output = args.output / datetime.now().strftime('session-%Y%m%d-%H%M%S-%f')
    args.output.mkdir(parents=True, exist_ok=True)
    if is_camera:
        print(f'Risultati webcam: {args.output.resolve()}', flush=True)
    if args.image:
        image = cv2.imread(str(args.image))
        if image is None:
            parser.error(f'Cannot read image: {args.image}')
        frames = iter([(0, image)])
    elif args.video:
        frames = video_frames(args.video, args.start, args.duration, args.fps)
    elif is_camera:
        from webcam import camera_frames
        frames = camera_frames(args.camera, args.fps, args.duration)
    else:
        frames = screen_frames(args.bbox, args.fps, args.duration)
    preview = None
    if args.preview is True or (args.preview is None and is_camera):
        from preview import LivePreview
        try:
            preview = LivePreview()
        except RuntimeError as error:
            parser.exit(1, str(error) + '\n')
    timings, accepted, counts = [], 0, {'digital': 0, 'physical': 0}
    scene_counts = {}
    interrupted = False
    failure = None
    begin = perf_counter()
    try:
        with (args.output / 'detections.jsonl').open('w', encoding='utf-8') as stream:
            for i, (timestamp, frame) in enumerate(frames):
                result = detector.detect(frame)
                if temporal:
                    result = temporal.update(result, timestamp, frame.shape)
                result['timestamp_s'] = round(timestamp, 4)
                stream.write(json.dumps(result, allow_nan=False) + '\n')
                stream.flush()
                timings.append(result['processing_ms'])
                scene_counts[result['scene']] = scene_counts.get(result['scene'], 0) + 1
                for card in result['cards']:
                    if card['accepted']:
                        accepted += 1
                        counts[card['domain']] += 1
                if preview:
                    keep_running = preview.show(frame, result)
                    if preview.save_requested:
                        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
                        stem = args.output / f'snapshot-{stamp}'
                        if not cv2.imwrite(str(stem) + '-raw.png', frame):
                            raise OSError('Impossibile salvare il fotogramma originale')
                        if not cv2.imwrite(str(stem) + '-annotated.jpg', annotate(frame, result)):
                            raise OSError('Impossibile salvare il fotogramma annotato')
                        Path(str(stem) + '.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
                        preview.save_requested = False
                        preview.saved(stem.name)
                    if not keep_running:
                        break
                if args.image or (args.save_every and i % args.save_every == 0):
                    cv2.imwrite(str(args.output / f'frame-{timestamp:010.3f}.jpg'), annotate(frame, result))
                if i % 100 == 0:
                    print(f'{timestamp:.1f}s: {result["scene"]}, {len(result["cards"])} candidates, '
                          f'{result["processing_ms"]:.1f} ms', flush=True)
    except KeyboardInterrupt:
        interrupted = True
    except (RuntimeError, OSError, ValueError) as error:
        failure = str(error)
    finally:
        if hasattr(frames, 'close'):
            frames.close()
        if preview:
            preview.close()
    summary = {'frames': len(timings), 'accepted_appearances': accepted, 'by_domain': counts,
               'scenes': scene_counts, 'interrupted': interrupted,
               'source': 'camera' if is_camera else 'image' if args.image else 'video' if args.video else 'screen',
               'detector': detector_mode,
               'profile': args.profile if detector_mode == 'model' else None,
               'temporal_confirmation': temporal_enabled,
               'detection_kind': 'card_index' if detector_mode == 'model' else 'card',
               'error': failure,
               'wall_seconds': round(perf_counter() - begin, 3),
               'processing_ms': {str(p): round(float(np.percentile(timings, p)), 3)
                                 for p in (50, 95, 99)} if timings else {},
               'note': 'Processing time excludes capture/decode and sampling wait; counts are appearances, not unique cards.'}
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    if failure:
        raise SystemExit(failure)
    if not timings:
        raise SystemExit('No frames processed; check the input and start time')


if __name__ == '__main__':
    main()
