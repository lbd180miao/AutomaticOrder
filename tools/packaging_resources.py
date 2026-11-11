"""Allowlist deployment assets; never copy historical media or SDK captures."""
import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def copy_resources(destination):
    destination = Path(destination)
    source_root = (ROOT / 'media').resolve()
    required = set()
    with sqlite3.connect(destination / 'db.sqlite3') as db:
        for row in db.execute('SELECT standard_template_config, threshold_config FROM vision_visionrecipe'):
            for field in row:
                for value in strings(json.loads(field or '{}')):
                    normalized = value.replace('\\', '/')
                    if 'standard_masks/' not in normalized:
                        continue
                    relative = Path('standard_masks/' + normalized.split('standard_masks/', 1)[1])
                    source = (source_root / relative).resolve()
                    if not source.is_relative_to(source_root / 'standard_masks'):
                        raise ValueError(f'Invalid template path: {relative}')
                    if source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.bmp', '.json'}:
                        raise ValueError(f'Unsupported template resource: {relative}')
                    if not source.is_file():
                        raise FileNotFoundError(f'Required standard template missing: {relative}')
                    required.add(relative)
    media = destination / 'media'
    # Do not silently leave captures from a previous release in the output.
    if media.exists() and any(p.is_file() for p in media.rglob('*')):
        raise ValueError('Output media must be empty. Build into a new deployment directory.')
    manifest = []
    for relative in sorted(required):
        target = media / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, target)
        manifest.append({'path': 'media/' + relative.as_posix(), 'bytes': target.stat().st_size})
    (destination / 'resource-manifest.json').write_text(json.dumps({
        'policy': 'Only recipe-referenced standard templates; no history, captures, or point clouds.',
        'files': manifest,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Included {len(manifest)} standard template assets; no historical captures.')


if __name__ == '__main__':
    import sys
    copy_resources(sys.argv[1])
