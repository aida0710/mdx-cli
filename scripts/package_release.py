"""Package a PyInstaller onedir bundle, preserving Unix executable bits and links."""

import argparse
import hashlib
import tarfile
import zipfile
from pathlib import Path


def package(artifact: str, dist: Path = Path('dist')) -> Path:
    bundle = dist / 'mdx'
    windows = artifact == 'mdx-windows-x86_64'
    executable = bundle / ('mdx.exe' if windows else 'mdx')
    if not executable.is_file() or not (bundle / '_internal').is_dir():
        raise ValueError('A complete PyInstaller onedir bundle is required')
    archive = dist / (artifact + ('.zip' if windows else '.tar.gz'))
    if windows:
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
            for path in sorted(bundle.rglob('*')):
                if path.is_file():
                    output.write(path, path.relative_to(dist))
    else:
        with tarfile.open(archive, 'w:gz') as output:
            output.add(bundle, arcname='mdx')
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    (dist / 'checksums.txt').write_text(f'{digest}  {archive.name}\n')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', choices=[
        'mdx-darwin-arm64', 'mdx-linux-x86_64', 'mdx-linux-arm64', 'mdx-windows-x86_64',
    ])
    print(package(parser.parse_args().artifact))
