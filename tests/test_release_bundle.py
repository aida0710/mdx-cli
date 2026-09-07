"""Verify the distribution keeps the runtime and Unix links intact."""
import hashlib
import tarfile
import zipfile

import pytest

from scripts.package_release import package


@pytest.mark.parametrize('windows', [False, True])
def test_package_contains_runtime_and_matching_checksum(tmp_path, windows):
    bundle = tmp_path / 'mdx'
    (bundle / '_internal').mkdir(parents=True)
    executable = bundle / ('mdx.exe' if windows else 'mdx')
    executable.write_bytes(b'executable')
    executable.chmod(0o755)
    (bundle / '_internal' / 'library').write_bytes(b'library')
    if not windows:
        (bundle / '_internal' / 'alias').symlink_to('library')
    artifact = 'mdx-windows-x86_64' if windows else 'mdx-darwin-arm64'
    archive = package(artifact, tmp_path)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert (tmp_path / 'checksums.txt').read_text() == f'{digest}  {archive.name}\n'
    if windows:
        with zipfile.ZipFile(archive) as z:
            assert z.read('mdx/mdx.exe') == b'executable'
            assert z.read('mdx/_internal/library') == b'library'
    else:
        with tarfile.open(archive) as tar:
            assert tar.getmember('mdx/mdx').mode & 0o111
            assert tar.getmember('mdx/_internal/alias').issym()
            assert tar.getmember('mdx/_internal/alias').linkname == 'library'


def test_package_rejects_missing_runtime(tmp_path):
    (tmp_path / 'mdx').mkdir()
    (tmp_path / 'mdx' / 'mdx').touch()
    with pytest.raises(ValueError, match='complete'):
        package('mdx-darwin-arm64', tmp_path)
