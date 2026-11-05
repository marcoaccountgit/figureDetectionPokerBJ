"""Evaluate current-frame and temporal readings on excluded video sequences."""
import argparse
import json
from pathlib import Path

from card_detector import cv2, np
from download_model import file_digest
from evaluate_improvement import load_profile
from evaluate_table_model import score_frame
from prepare_table_dataset import stable_indices
from temporal_cards import TemporalCards

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video_directory', type=Path)
    parser.add_argument('--model-dir', type=Path, default=ROOT / 'models')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/sequence-improvement/sequences')
    args = parser.parse_args()
    detector = load_profile(args.model_dir)
    rows, skipped = [], 0
    sources = []
    for annotation in ('table-211955.json', 'table-213508.json', 'table-213508-sequence.json'):
        spec_path = ROOT / 'datasets' / annotation
        spec = json.loads(spec_path.read_text())
        video = args.video_directory / spec['source']
        if file_digest(video) != spec['source_sha256']:
            raise ValueError('Recording differs from reviewed source')
        sources.append({'annotation': annotation, 'sha256': file_digest(spec_path),
                        'source_sha256': spec['source_sha256']})
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened() or [round(cap.get(3)), round(cap.get(4))] != spec['size']:
            cap.release()
            raise ValueError('Unexpected recording dimensions')
        fold = annotation.endswith('-sequence.json')
        sequences = [spec['frames']] if fold else [[e] for e in spec['frames']
                                                   if e['time'] > 300 and not ('213508' in annotation and e['time'] == 540)]
        try:
            for sequence in sequences:
                temporal = TemporalCards()
                packets = sequence if fold else [dict(sequence[0], time=round(sequence[0]['time']+offset, 1))
                                                 for offset in (-.4, -.2, 0, .2, .4)]
                if not fold:
                    cap.set(cv2.CAP_PROP_POS_MSEC, sequence[0]['time']*1000)
                    ok, reference = cap.read()
                    if not ok:
                        raise ValueError('Cannot decode reviewed reference')
                for i, entry in enumerate(packets):
                    cap.set(cv2.CAP_PROP_POS_MSEC, entry['time']*1000)
                    ok, frame = cap.read()
                    if not ok:
                        raise ValueError('Cannot decode sequence')
                    raw = detector.detect(frame)
                    confirmed = temporal.update(raw, entry['time'], frame.shape)
                    if not fold and not stable_indices(reference, frame, sequence[0], spec):
                        skipped += 1
                        continue
                    expected = [(code, box) for group in spec['index_boxes']
                                for code, box in zip(entry[group], spec['index_boxes'][group])]
                    rows.append({'source': video.name, 'sequence': 'fold' if fold else f'{annotation}-{sequence[0]["time"]}',
                                 'time': entry['time'], 'startup': i == 0, 'expected': len(expected),
                                 'raw': score_frame(expected, raw['cards']),
                                 'temporal': score_frame(expected, confirmed['cards']),
                                 'processing_ms': confirmed['processing_ms'],
                                 'temporal_processing_ms': confirmed['temporal']['processing_ms'],
                                 'confirmation_spans_ms': [c['confirmation_span_ms'] for c in confirmed['cards'] if c['accepted']]})
        finally:
            cap.release()
    summaries = {}
    for group, selected in (('all', rows), ('after_startup', [r for r in rows if not r['startup']]),
                            ('fold_empty', [r for r in rows if r['sequence'] == 'fold' and not r['expected']])):
        summaries[group] = {'frames': len(selected), 'expected': sum(r['expected'] for r in selected)}
        for mode in ('raw', 'temporal'):
            summaries[group][mode] = {key: sum(len(r[mode][key]) for r in selected)
                                      for key in ('correct', 'false_positive', 'missed')}
    report = {'protocol': 'Ten excluded suffix centres with stable +/-0.4s neighbours at5fps; independent new manual fold sequence. First frame pending by design. Suffixes observed in earlier development. No prediction-generated ground truth.',
              'manifest_sha256': file_digest(args.model_dir / 'pokerstars.manifest.json'),
              'sources': sources, 'skipped_unstable_frames': skipped,
              'summary': summaries,
              'processing_ms': {str(p): float(np.percentile([r['processing_ms'] for r in rows],p)) for p in (50,95)},
              'temporal_processing_ms_max': max(r['temporal_processing_ms'] for r in rows), 'cases': rows}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('sources','cases')}, indent=2))


if __name__ == '__main__':
    main()
