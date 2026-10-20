"""Generate two catalog import documents offline. Does not register, run or authorize anything."""
import argparse
import json
from pathlib import Path
import re


def registration(image, context):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise ValueError('Supply the immutable image ID from docker image inspect')
    if context not in ('prefix', 'full'):
        raise ValueError('Unknown context policy')
    return dict(protocol_version=1, name='MiniFix', version=f'{context}-v1', adapter='process',
        process=dict(protocol_version=1, image=image,
            argv=['python', '-I', '/agent/minifix.py', '--context', context], trace=False,
            model_policy=dict(provider='dashscope', model='qwen-plus', temperature=0.0,
                max_output_tokens=2048, max_calls=1, max_request_bytes=65536,
                max_messages=2, request_timeout_seconds=60, token_enforcement='advisory')),
        declared_capabilities=['execution'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    documents = {context: registration(args.image, context) for context in ('prefix', 'full')}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for context, document in documents.items():
        path = args.output_dir / f'minifix-{context}-v1.json'
        with path.open('x', encoding='utf-8') as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
        print(path.resolve())


if __name__ == '__main__':
    main()
