"""Remove identical same-class glyphs from an isolated candidate's reference bank."""
import argparse, json
from pathlib import Path
from card_detector import cv2

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate',type=Path);args=p.parse_args()
    candidate=args.candidate.resolve()
    root=Path(__file__).resolve().parent/'artifacts'
    if not candidate.is_relative_to(root):raise ValueError('Only isolated artifacts candidates are supported')
    bank=candidate/'pokerstars-nine-symbols'
    seen={};removed=[]
    files=sorted(bank.rglob('*.png'))
    for path in files:
        image=cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
        if image is None:raise ValueError(f'Unreadable glyph {path}')
        key=(path.parent.name,path.stem.split('_')[0],image.shape,(image>0).tobytes())
        if key in seen:
            removed.append(dict(file=str(path.relative_to(candidate)),duplicate_of=str(seen[key].relative_to(candidate))))
            path.unlink()
        else:seen[key]=path
    report=dict(before=len(files),after=len(seen),removed=removed,
        protocol='Exact binary glyph equality within the SAME class. Max correlation and class margins are unchanged.')
    (candidate/'symbol-deduplication.json').write_text(json.dumps(report,indent=2))
    manifest_path=candidate/'pokerstars-nine.manifest.json'
    manifest=json.loads(manifest_path.read_text())
    manifest['symbol_reference_deduplication']={k:report[k] for k in ('before','after','protocol')}
    manifest_path.write_text(json.dumps(manifest,indent=2))
    print('Symbol templates:',len(files),'->',len(seen),flush=True)

if __name__=='__main__':main()
