"""Download pinned ONNX weights; never upload images or execute remote code."""
import hashlib
import json
from pathlib import Path
import urllib.request

MODEL_DIR = Path(__file__).parent / 'models'


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verified_model_files():
    manifest = json.loads((MODEL_DIR / 'manifest.json').read_text(encoding='utf-8'))
    files = []
    for spec in manifest['files']:
        path = MODEL_DIR / spec['local']
        if not path.is_file() or file_digest(path) != spec['sha256']:
            raise RuntimeError('Modello mancante o non integro. Esegui: python download_model.py')
        files.append(path)
    return files


def main():
    manifest = json.loads((MODEL_DIR / 'manifest.json').read_text(encoding='utf-8'))
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
