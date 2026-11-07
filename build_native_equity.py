"""Build the optional Rust equity library with the installed Rust toolchain."""
from pathlib import Path
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parent
    cargo = shutil.which('cargo')
    if cargo is None:
        raise SystemExit('Cargo non trovato. Installare Rust, poi rieseguire questo script.')
    subprocess.run([cargo, 'build', '--release', '--offline',
                    '--manifest-path', str(root / 'native/equity/Cargo.toml'),
                    '--target-dir', str(root / 'native/equity/target')], check=True, cwd=root)
    from native_equity import library_path, load_native
    if load_native() is None:
        raise SystemExit('Compilazione completata, ma la libreria Rust non si carica in questo Python.')
    print(f'Motore Rust pronto (singolo core): {library_path()}')


if __name__ == '__main__':
    main()
