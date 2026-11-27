"""Run frozen V7 and current V8 on the same official fixed-view sample."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
IMAGES = [('data/before.jpg', '2020-04'), ('data/after.jpg', '2020-07')]
CONTEXT = Path(__file__).with_name('context.json')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('version', choices=('v7', 'v8'))
    args = parser.parse_args()
    if args.version == 'v7':
        snapshot = Path(__file__).resolve().parents[1] / 'v7_tracker_snapshot.py'
        spec = importlib.util.spec_from_file_location('ukawa_v7_tracker', snapshot)
        tracker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tracker)
        tracker.ROOT = ROOT
    else:
        sys.path.insert(0, str(ROOT / 'src'))
        import progress_tracker as tracker
    out = ROOT / 'output' / f'ukawa_fixed_blind_live_{args.version}_20261126'
    if out.exists():
        raise SystemExit(f'Refusing to overwrite {out}')
    started = time.perf_counter()
    status = {'version': args.version, 'model': 'deepseek-v4-flash',
              'dataset': 'New Niigata Prefecture Ukawa Dam fixed-view sequence',
              'execution_mode': 'live', 'output': str(out), 'periods': []}
    try:
        for image, dt in IMAGES:
            tracker.main(['--new-image', str(ROOT / image), '--date', dt,
                          '--out', str(out), '--context', str(CONTEXT)])
            state = json.loads((out / 'history.json').read_text(encoding='utf-8'))
            h = state['history'][-1]
            status['periods'].append({'date': dt,
                'project_progress_pct': h['overall']['project_progress_pct'],
                'coverage_pct': h['overall']['current_coverage_pct'],
                'range_pct': h['overall']['total_possible_range_pct'],
                'quality_review': h.get('quality_review'),
                'stages': [{'id': s['id'], 'status': s['status'], 'confidence': s['confidence'],
                            'progress_estimate': s['progress_estimate'], 'source': s['source']}
                           for s in h['stages']]})
    except Exception as exc:
        message = str(exc)
        secret = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        if secret:
            message = message.replace(secret, '[redacted]')
        status.update(status='failed', error_type=type(exc).__name__, error=message[:1000])
    else:
        status['status'] = 'completed'
    status['elapsed_seconds'] = round(time.perf_counter() - started, 3)
    result_path = Path(__file__).with_name(f'blind_{args.version}_live_results.json')
    result_path.write_text(json.dumps(status, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in status.items() if k != 'periods'}, ensure_ascii=False), flush=True)
    if status['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
