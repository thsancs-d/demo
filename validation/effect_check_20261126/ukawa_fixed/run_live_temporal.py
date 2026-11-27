"""Run V9 fixed-camera recognition on the held-out Ukawa fixed-view pair."""
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
VALIDATION = Path(__file__).resolve().parent
OUTPUT = ROOT / 'output/ukawa_fixed_temporal_live_20261126'
SOURCE = ROOT / 'output/ukawa_fixed_blind_live_v8_20261126/observations'
DATES = ('2020-04', '2020-07')


def main():
    if OUTPUT.exists():
        raise SystemExit(f'Refusing to overwrite {OUTPUT}')
    sys.path.insert(0, str(ROOT / 'src'))
    import progress_tracker

    status = {
        'version': 'v9-fixed-camera-temporal',
        'dataset': 'Niigata Prefecture Ukawa Dam fixed-view photo sequence',
        'model': os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-flash'),
        'execution_mode': 'live',
        'output': str(OUTPUT),
        'periods': [],
    }
    started = time.perf_counter()
    try:
        for date in DATES:
            progress_tracker.main([
                '--new-image', str(SOURCE / date / 'original.jpg'),
                '--date', date,
                '--context', str(VALIDATION / 'context.json'),
                '--fixed-camera', '--skip-cv', '--out', str(OUTPUT),
            ])
            state = json.loads((OUTPUT / 'history.json').read_text(encoding='utf-8'))
            entry = state['history'][-1]
            status['periods'].append({
                'date': date,
                'temporal_review': entry['temporal_review'],
                'temporal_changes': entry['temporal_changes'],
                'project_progress_pct': entry['overall']['project_progress_pct'],
                'coverage_pct': entry['overall']['current_coverage_pct'],
                'range_pct': entry['overall']['total_possible_range_pct'],
                'stages': [
                    {'id': stage['id'], 'status': stage['status'],
                     'confidence': stage['confidence'],
                     'progress_estimate': stage['progress_estimate']}
                    for stage in entry['stages']
                ],
            })
    except Exception as exc:
        message = str(exc)
        secret = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        if secret:
            message = message.replace(secret, '[redacted]')
        status.update(status='failed', error_type=type(exc).__name__, error=message[:1000])
    else:
        status['status'] = 'completed'
    status['elapsed_seconds'] = round(time.perf_counter() - started, 3)
    status['accuracy_validation'] = 'not_measurable_without_event_ground_truth'
    result = VALIDATION / 'live_temporal_results.json'
    result.write_text(json.dumps(status, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                      encoding='utf-8')
    print(json.dumps({key: value for key, value in status.items() if key != 'periods'},
                     ensure_ascii=False), flush=True)
    for period in status['periods']:
        print(json.dumps(period, ensure_ascii=False), flush=True)
    if status['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
