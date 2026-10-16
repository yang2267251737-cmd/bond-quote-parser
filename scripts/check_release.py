"""Check an explicit release manifest; do not embed real secrets in this script."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_FILES = (
    '.gitignore', 'README.md', 'config.json', 'quote_parser.py',
    'examples/demo.txt', 'tests/test_parser.py',
    'docs/confidentiality.md', 'scripts/check_release.py',
    'PRODUCT.md', 'DESIGN.md', 'app.py', 'structured_parser.py', '启动软件.cmd',
    'web/index.html', 'web/app.css', 'web/app.js',
    'examples/software_demo.txt', 'tests/test_app.py', 'tests/test_structured_parser.py',
)


def check() -> list[str]:
    errors = []
    for name in RELEASE_FILES:
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            errors.append(f'Missing or unexpected file: {name}')
            continue
        content = path.read_text(encoding='utf-8')
        if '\x00' in content:
            errors.append(f'Binary content in release file: {name}')
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    if config.get('contact_directory') != {}:
        errors.append('Release contact_directory must be empty')
    for key, value in config.get('institution_aliases', {}).items():
        if not key.startswith('示例') or not value.startswith('示例'):
            errors.append('Release aliases must use explicitly fictional institutions')
    if '虚构测试数据' not in (ROOT / 'README.md').read_text(encoding='utf-8'):
        errors.append('README must identify fictional test data')
    if not (ROOT / '.git').is_dir():
        errors.append('Run this check from an initialized standalone Git repository')
        return errors
    try:
        tracked = subprocess.check_output(
            ['git', '-C', str(ROOT), 'ls-files', '-z'],
            stderr=subprocess.PIPE,
        ).decode('utf-8').split('\0')
        unexpected = set(filter(None, tracked)) - set(RELEASE_FILES)
        errors.extend(f'Unexpected tracked/staged path: {path}' for path in sorted(unexpected))
        for name in RELEASE_FILES:
            ignored = subprocess.run(
                ['git', '-C', str(ROOT), 'check-ignore', '--quiet', '--no-index', '--', name],
                capture_output=True,
            )
            if ignored.returncode == 0:
                errors.append(f'Release file is unexpectedly ignored: {name}')
            elif ignored.returncode != 1:
                errors.append(f'Could not verify Git ignore rules: {name}')
    except (OSError, subprocess.CalledProcessError):
        errors.append('Could not inspect Git index')
    return errors


if __name__ == '__main__':
    problems = check()
    if problems:
        print('\n'.join(problems))
        raise SystemExit(1)
    print(f'Release manifest checked: {len(RELEASE_FILES)} files. Human content review is still required.')
