"""Exercise fixed-camera temporal storage with the Ukawa fixed-view photo pair."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
VALIDATION = Path(__file__).resolve().parent
OUTPUT = VALIDATION / 'offline_temporal_demo'
IMAGE_ROOT = ROOT / 'output/ukawa_fixed_blind_live_v8_20261126/observations'
DATES = ('2020-04', '2020-07')


def response(temporal_changes):
    return {
        'stages': [],
        'inferred_stages': [],
        'changes': [],
        'risks': ['离线模拟响应；变化事件不是人工标注或模型识别结果。'],
        'summary': '固定镜头离线时序流程验证。',
        'temporal_changes': temporal_changes,
    }


def main():
    if OUTPUT.exists():
        raise SystemExit(f'输出目录已存在，为避免覆盖而停止：{OUTPUT}')

    OUTPUT.mkdir()
    with tempfile.TemporaryDirectory(prefix='ukawa_temporal_responses_') as temporary:
        response_dir = Path(temporary)
        first, second = DATES
        (response_dir / f'{first}.json').write_text(
            json.dumps(response([]), ensure_ascii=False), encoding='utf-8')
        event = {
            'stage_id': 'dam_body',
            'direction': 'advanced',
            'change_type': 'expanded',
            'evidence_image_numbers': [1, 2],
            'bbox_xyxy': [0.32, 0.38, 0.62, 0.72],
            'where': '画面中央坝体区域（模拟输入）',
            'what': '同一观察区域的坝体范围扩大（模拟输入）',
            'confidence': 0.8,
            'visibility': 'partial',
            'basis': 'same_region_comparison',
        }
        (response_dir / f'{second}.json').write_text(
            json.dumps(response([event]), ensure_ascii=False), encoding='utf-8')

        for date in DATES:
            image = IMAGE_ROOT / date / 'original.jpg'
            command = [
                sys.executable, str(ROOT / 'src/run_aigawa.py'),
                '--new-image', str(image), '--date', date,
                '--context', str(VALIDATION / 'context.json'),
                '--responses', str(response_dir), '--fixed-camera', '--skip-cv',
                '--out', str(OUTPUT),
            ]
            subprocess.run(command, cwd=ROOT, check=True)

    state = json.loads((OUTPUT / 'history.json').read_text(encoding='utf-8'))
    history = state['history']
    assert len(history) == 2
    assert history[0]['temporal_changes'] == []
    assert history[1]['temporal_review']['accepted_changes'] == 1
    assert history[1]['temporal_changes'][0]['evidence_image_numbers'] == [1, 2]
    assert history[1]['overall']['project_progress_pct'] is None

    result = {
        'validation_type': 'synthetic_response_workflow_check',
        'dataset': 'Ukawa Dam fixed-view photos from 2020-04 and 2020-07',
        'images': [entry['image'] for entry in history],
        'first_period_change_count': len(history[0]['temporal_changes']),
        'second_period_accepted_changes': history[1]['temporal_review']['accepted_changes'],
        'second_period_change': history[1]['temporal_changes'][0],
        'project_progress_pct': history[1]['overall']['project_progress_pct'],
        'project_progress_method': history[1]['overall']['project_progress_method'],
        'warning': 'The event was supplied as synthetic offline input. This run verifies workflow behavior, not image recognition accuracy.',
    }
    (VALIDATION / 'offline_temporal_demo_results.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f'REPORT={OUTPUT / "latest_report.md"}')


if __name__ == '__main__':
    main()
