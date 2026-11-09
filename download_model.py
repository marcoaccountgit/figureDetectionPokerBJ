"""Download pinned ONNX weights; never upload images or execute remote code."""
import hashlib
import json
from pathlib import Path
import urllib.request

MODEL_DIR = Path(__file__).parent / 'models'


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def model_manifest(profile='general'):
    if profile not in ('general', 'pokerstars','pokerstars-nine','pokerstars-desktop-six'):
        raise ValueError(f'Unknown model profile: {profile}')
    filename = 'manifest.json' if profile == 'general' else f'{profile}.manifest.json'
    path = MODEL_DIR / filename
    if not path.is_file():
        raise RuntimeError(f'Modello del profilo {profile} non installato')
    return json.loads(path.read_text(encoding='utf-8'))


def verified_model_files(profile='general'):
    manifest = model_manifest(profile)
    files = []
    for spec in manifest['files']:
        path = MODEL_DIR / spec['local']
        if not path.is_file() or file_digest(path) != spec['sha256']:
            action = 'python download_model.py' if profile == 'general' else 'train_table_model.py con Python di training'
            raise RuntimeError(f'Modello mancante o non integro. Esegui: {action}')
        files.append(path)
    return files


def main():
    manifest = model_manifest()
    for spec in manifest['files']:
        destination = MODEL_DIR / spec['local']
        if destination.is_file() and file_digest(destination) == spec['sha256']:
            print(f'Gia verificato: {destination.name}')
            continue
        url = (f"https://huggingface.co/{manifest['repository']}/resolve/"
               f"{manifest['revision']}/{spec['remote']}")
        temporary = destination.with_suffix(destination.suffix + '.part')
        print(f'Scaricamento: {destination.name}', flush=True)
        try:
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if file_digest(temporary) != spec['sha256']:
                raise RuntimeError(f'Checksum non valido: {destination.name}')
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    print('Modello pronto. Inferenza locale; licenza dei pesi: AGPL-3.0.')


if __name__ == '__main__':
    main()
