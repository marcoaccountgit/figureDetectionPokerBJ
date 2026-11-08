"""Paired before/after evaluation on annotated frames decoded from a real video."""
import argparse
import importlib.util
import json
import statistics
from pathlib import Path
from time import perf_counter

from card_detector import cv2
from capture_alignment import CaptureAligner
from learned_detector import LearnedCardDetector
from table_layout import arrange_table


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--widths', default='960,1280')
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--reviewed-frames', type=Path, help='Previously decoded frames of this same video')
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location('baseline_card_detector', args.baseline)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    models = {'before': module.LearnedCardDetector('pokerstars-nine'),
              'after': LearnedCardDetector('pokerstars-nine')}
    annotations = json.loads(Path('datasets/desktop-200950.json').read_text())
    cap = cv2.VideoCapture(str(args.video))
    samples = []
    try:
        for entry in annotations['frames']:
            if not 0 <= entry['time'] < annotations['max_time_exclusive']:
                raise ValueError('Timestamp outside reviewed interval')
            if args.reviewed_frames:
                frame = cv2.imread(str(args.reviewed_frames / f"{entry['time']:04d}.jpg"))
                ok = frame is not None
            else:
                cap.set(cv2.CAP_PROP_POS_MSEC, entry['time']*1000)
                ok, frame = cap.read()
            if not ok:
                raise ValueError(f"Cannot decode {entry['time']}")
            for width in map(int, args.widths.split(',')):
                image = cv2.resize(frame, (width, round(frame.shape[0]*width/frame.shape[1])))
                aligner = CaptureAligner(); game, _ = aligner.align(image)
                expected = entry['board']+[None]*(5-len(entry['board']))+entry['hole']+[None]*(2-len(entry['hole']))
                samples.append((game, entry, width, aligner.profile, expected))
            print(f"Prepared {entry['time']}s", flush=True)
    finally:
        cap.release()
    # Exclude initialization and alternate order to reduce CPU-load/order bias.
    for model in models.values(): model.detect(samples[0][0])
    rows = []
    for repeat in range(args.repeats):
        for index, (game, entry, width, profile, expected) in enumerate(samples):
            row = dict(time=entry['time'], split=entry['split'], width=width, repeat=repeat, expected=expected)
            for name in (('before','after') if (index+repeat)%2 == 0 else ('after','before')):
                start = perf_counter(); result = models[name].detect(game)
                elapsed = (perf_counter()-start)*1000
                result['table_profile'] = profile
                arranged = arrange_table(result, game.shape)
                actual = [c['card'] for c in arranged['board']+arranged['player_hand']]
                row[name] = dict(actual=actual, ms=elapsed, retries=result.get('uncertain_retries',0))
            rows.append(row)
            if (index+1)%12 == 0:
                print(f'Pass {repeat+1}: {index+1}/{len(samples)}',flush=True)
        print(f'Completed pass {repeat+1}/{args.repeats}', flush=True)
    summary = {}
    for name in models:
        times = sorted(r[name]['ms'] for r in rows)
        evaluated = [r for r in rows if r['repeat']==0]
        summary[name] = dict(mean_ms=statistics.mean(times), median_ms=statistics.median(times),
            p95_ms=times[min(len(times)-1, int(len(times)*.95))],
            visible=sum(c is not None for r in evaluated for c in r['expected']),
            visible_correct=sum(a==e and e is not None for r in evaluated for a,e in zip(r[name]['actual'],r['expected'])),
            wrong_accepted=sum(a is not None and a!=e for r in evaluated for a,e in zip(r[name]['actual'],r['expected'])),
            exact_frames=sum(r[name]['actual']==r['expected'] for r in evaluated), frames=len(evaluated),
            retries=sum(r[name]['retries'] for r in rows))
        summary[name]['mean_ms_by_pass'] = [statistics.mean(r[name]['ms'] for r in rows if r['repeat']==i)
                                           for i in range(args.repeats)]
        holdout = [r for r in evaluated if r['split'] in ('val','test')]
        summary[name]['holdout'] = dict(frames=len(holdout),
            visible=sum(e is not None for r in holdout for e in r['expected']),
            visible_correct=sum(a==e and e is not None for r in holdout for a,e in zip(r[name]['actual'],r['expected'])),
            wrong_accepted=sum(a is not None and a!=e for r in holdout for a,e in zip(r[name]['actual'],r['expected'])))
    report = dict(video=str(args.video), reviewed_frames=str(args.reviewed_frames) if args.reviewed_frames else None,
        reviewed_interval_seconds=[0,annotations['max_time_exclusive']],
        caveat='Reviewed samples from an already used video; includes training frames, not independent full-video accuracy. Timing excludes decoding/alignment and includes all retries.',
        summary=summary, rows=rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(summary,indent=2),flush=True)


if __name__ == '__main__': main()
