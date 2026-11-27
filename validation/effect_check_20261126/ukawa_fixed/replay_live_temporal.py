"""Re-run archived live model responses through fixed-camera validation offline."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
VALIDATION = Path(__file__).resolve().parent
LIVE_OUTPUT = ROOT / 'output/ukawa_fixed_temporal_live_20261126'
OUTPUT = ROOT / 'output/ukawa_fixed_temporal_replay_20261126'
RESULT = VALIDATION / 'live_temporal_replay_results.json'
DATES = ('2020-04', '2020-07')


def main():
    if OUTPUT.exists():
        raise SystemExit(f'Refusing to overwrite {OUTPUT}')

    with tempfile.TemporaryDirectory(prefix='ukawa_live_response_replay_') as temporary:
        responses = Path(temporary)
        for date in DATES:
            source = LIVE_OUTPUT / 'observations' / date / 'raw_model.json'
            shutil.copyfile(source, responses / f'{date}.json')

        for date in DATES:
            command = [
                sys.executable, str(ROOT / 'src/run_aigawa.py'),
                '--new-image', str(LIVE_OUTPUT / 'observations' / date / 'original.jpg'),
                '--date', date,
                '--context', str(VALIDATION / 'context.json'),
                '--responses', str(responses), '--fixed-camera', '--skip-cv',
                '--out', str(OUTPUT),
            ]
            subprocess.run(command, cwd=ROOT, check=True)

    state = json.loads((OUTPUT / 'history.json').read_text(encoding='utf-8'))
    first, second = state['history']
    raw_second = json.loads(
        (LIVE_OUTPUT / 'observations/2020-07/raw_model.json').read_text(encoding='utf-8'))
    stages = {stage['id']: stage for stage in second['stages']}
    assert first['temporal_changes'] == []
    assert len(second['temporal_changes']) == 2
    assert second['temporal_review']['rejected_changes'] == 1
    assert second['temporal_review']['reasons'][0]['reasons'] == [
        '临时或未知变化不能标记为 advanced']
    assert stages['dam_body']['status'] == 'in_progress'
    assert stages['dam_body']['evidence'] == raw_second['stages'][3]['observation']
    assert second['overall']['project_progress_pct'] is None

    result = {
        'validation_type': 'offline_replay_of_live_model_responses',
        'source_live_output': str(LIVE_OUTPUT),
        'replay_output': str(OUTPUT),
        'dates': list(DATES),
        'first_period_events': len(first['temporal_changes']),
        'second_period_accepted_events': len(second['temporal_changes']),
        'second_period_rejected_events': second['temporal_review']['rejected_changes'],
        'rejected_event_reasons': second['temporal_review']['reasons'],
        'stage_statuses': {stage['id']: stage['status'] for stage in second['stages']},
        'dam_body_evidence': stages['dam_body']['evidence'],
        'project_progress_pct': second['overall']['project_progress_pct'],
        'warning': 'Replay reuses actual live model responses but measures parser/policy behavior only, not event-label accuracy.',
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f'REPORT={OUTPUT / "latest_report.md"}')


if __name__ == '__main__':
    main()
