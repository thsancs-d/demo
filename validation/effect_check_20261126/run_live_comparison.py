"""Run one frozen version against the original dataset; never print credentials."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('version', choices=('v7', 'v8'))
    args = parser.parse_args()
    out = ROOT / 'output' / f'aigawa_effect_live_{args.version}_20261126'
    if out.exists():
        raise SystemExit(f'Refusing to overwrite {out}')
    if args.version == 'v7':
        snapshot = Path(__file__).with_name('v7_tracker_snapshot.py')
        spec = importlib.util.spec_from_file_location('effect_v7_tracker', snapshot)
        tracker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tracker)
        tracker.ROOT = ROOT
    else:
        import progress_tracker as tracker
    started = time.perf_counter()
    result = {'version': args.version, 'dataset': 'datasets/aigawa/images',
              'execution_mode': 'live', 'output': str(out)}
    try:
        tracker.main(['--all', '--out', str(out)])
        result['status'] = 'completed'
    except Exception as exc:
        message = str(exc)
        secret = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        if secret:
            message = message.replace(secret, '[redacted]')
        result.update(status='failed', error_type=type(exc).__name__,
                      http_status=getattr(exc, 'status_code', None), error=message[:1000])
    result['elapsed_seconds'] = round(time.perf_counter() - started, 3)
    Path(__file__).with_name(f'{args.version}_live_status.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if result['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
