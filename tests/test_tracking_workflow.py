"""Regression coverage for local history, recovery, and audited CLI workflows."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RESPONSES = ROOT / 'tests/fixtures/aigawa_responses_v8'
sys.path.insert(0, str(ROOT / 'src'))

from progress_tracker import atomic_json, digest


class StorageTests(unittest.TestCase):
    def test_failed_serialization_preserves_existing_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'history.json'
            path.write_text('{"history": []}', encoding='utf-8')
            with self.assertRaises(ValueError):
                atomic_json(path, {'invalid': float('nan')})
            self.assertEqual(path.read_text(encoding='utf-8'), '{"history": []}')
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_failed_replace_preserves_existing_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'history.json'
            path.write_text('{"history": []}', encoding='utf-8')
            with patch('progress_tracker.os.replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    atomic_json(path, {'history': [1]})
            self.assertEqual(path.read_text(encoding='utf-8'), '{"history": []}')
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_digest_streams_large_files(self):
        data = b'photo-bytes\x00\xff' * 200_000
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'image.bin'
            path.write_bytes(data)
            # A whole-file read regresses memory use for large original photos.
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('whole-file read')):
                self.assertEqual(digest(path), hashlib.sha256(data).hexdigest())


class TrackingWorkflowTests(unittest.TestCase):
    def run_cli(self, *args, check=True):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'src/run_aigawa.py'), *map(str, args)],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_equals_form_routes_new_image_to_tracking(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            responses = folder / 'responses'
            responses.mkdir()
            (responses / '2019-06.json').write_text('{"stages": []}', encoding='utf-8')
            out = folder / 'tracking'

            self.run_cli(
                f'--new-image={ROOT / "datasets/aigawa/images/2019-06.png"}',
                '--date=2019-06', f'--responses={responses}', '--skip-cv', f'--out={out}',
            )

            state = json.loads((out / 'history.json').read_text(encoding='utf-8'))
            self.assertEqual(state['mode'], 'offline_test')
            self.assertEqual([h['date'] for h in state['history']], ['2019-06'])

    def test_default_help_exposes_tracking_and_pairwise_modes(self):
        result = self.run_cli('--help')
        for option in ('--new-image', '--refresh-only', '--responses', '--out', '--cv-only'):
            self.assertIn(option, result.stdout)

    def test_four_periods_audit_resume_and_refresh_with_real_cv(self):
        dates = ['2019-06', '2020-04', '2021-01', '2022-02']
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            responses = folder / 'responses'
            shutil.copytree(RESPONSES, responses)
            out = folder / 'tracking'

            self.run_cli('--all', '--responses', responses, '--out', out)

            state = json.loads((out / 'history.json').read_text(encoding='utf-8'))
            self.assertEqual(state['mode'], 'offline_test')
            self.assertEqual([h['date'] for h in state['history']], dates)
            self.assertEqual([h['overall']['project_progress_pct'] for h in state['history']], [20, 45, 40, 80])
            self.assertEqual([h['overall']['project_progress_delta_pp'] for h in state['history']], [None, 25, -5, 40])
            self.assertEqual(state['history'][-1]['overall']['baseline_progress_delta_pp'], 60)
            expected_roles = [
                ['current_and_baseline'], ['baseline_and_previous', 'current'],
                ['baseline', 'previous', 'current'], ['baseline', 'previous', 'current'],
            ]
            for i, observation in enumerate(state['history']):
                period = out / 'observations' / observation['date']
                manifest = json.loads((period / 'request_manifest.json').read_text(encoding='utf-8'))
                roles = expected_roles[i].copy()
                if observation['cv']['eligible_diff']:
                    roles.append('ssim_previous_to_current')
                    self.assertTrue(observation['cv']['registration']['selected']['accepted'])
                elif i:
                    # A failed registration must be explicit, never silently replaced by a heatmap.
                    self.assertNotEqual(observation['cv']['reason'], '跳过CV')
                self.assertEqual([image['role'] for image in manifest['images']], roles)
                self.assertEqual([image['image_number'] for image in manifest['images']], list(range(1, len(roles) + 1)))
                self.assertEqual(manifest['execution_mode'], 'offline_test')
                self.assertEqual(manifest['prompt_version'], 'v8-grounded-evidence')
                self.assertEqual(observation['quality_review']['accepted_estimates'], 8)
                self.assertNotIn('estimated_project_pct', json.dumps(manifest['history_context']))
                self.assertEqual(manifest['prompt_sha256'], digest(period / 'prompt.txt'))
                self.assertEqual([h['date'] for h in manifest['history_context']['history']], dates[:i])
                for image in manifest['images']:
                    self.assertEqual(image['sha256'], digest(out / image['file']))
                self.assertEqual(observation['sha256'], digest(out / observation['image']))
                self.assertEqual(json.loads((period / 'progress.json').read_text(encoding='utf-8')), observation)
            self.assertEqual(json.loads((out / 'latest_progress.json').read_text(encoding='utf-8')), state['history'][-1])
            self.assertIn('模拟数据', (out / 'latest_report.md').read_text(encoding='utf-8'))
            self.assertTrue((out / 'latest_progress.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
            history = (out / 'history.json').read_bytes()
            archive = {p.relative_to(out): digest(p) for p in (out / 'observations').rglob('*') if p.is_file()}
            shutil.rmtree(responses)

            resumed = self.run_cli('--all', '--responses', responses, '--out', out)

            self.assertEqual(resumed.stdout.count('[跳过]'), 4)
            self.assertEqual((out / 'history.json').read_bytes(), history)
            self.assertEqual({p.relative_to(out): digest(p) for p in (out / 'observations').rglob('*') if p.is_file()}, archive)
            (out / 'latest_progress.png').unlink()

            self.run_cli('--refresh-only', '--out', out)

            self.assertEqual((out / 'history.json').read_bytes(), history)
            self.assertEqual((out / 'history.v4.backup.json').read_bytes(), history)
            self.assertTrue((out / 'latest_progress.png').is_file())
            self.assertFalse((out / '.update.lock').exists())

    def test_modified_baseline_blocks_append_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'tracking'
            for dt in ('2019-06', '2020-04'):
                self.run_cli('--new-image', ROOT / f'datasets/aigawa/images/{dt}.png',
                             '--date', dt, '--responses', RESPONSES, '--skip-cv', '--out', out)
            history = (out / 'history.json').read_bytes()
            state = json.loads(history)
            shutil.copyfile(ROOT / 'datasets/aigawa/images/2022-02.png', out / state['history'][0]['image'])

            result = self.run_cli('--new-image', ROOT / 'datasets/aigawa/images/2021-01.png',
                                  '--date', '2021-01', '--responses', RESPONSES,
                                  '--skip-cv', '--out', out, check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('历史原图已修改', result.stdout + result.stderr)
            self.assertEqual((out / 'history.json').read_bytes(), history)
            self.assertFalse((out / '.update.lock').exists())

    def test_fixed_camera_temporal_mode_isolated_and_auditable(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            responses = folder / 'responses'
            responses.mkdir()
            first = json.loads((RESPONSES / '2019-06.json').read_text(encoding='utf-8'))
            first['temporal_changes'] = []
            second = json.loads((RESPONSES / '2020-04.json').read_text(encoding='utf-8'))
            for sample in (first, second):
                for stage in sample['stages']:
                    stage['progress_estimate'] = None
            second['temporal_changes'] = [dict(
                stage_id='spillway', direction='advanced', change_type='expanded',
                evidence_image_numbers=[1, 2], bbox_xyxy=[.1, .2, .4, .6], where='右侧泄槽',
                what='同一画面区域新增成型段', confidence=.8, visibility='partial',
                basis='same_region_comparison')]
            (responses / '2019-06.json').write_text(json.dumps(first), encoding='utf-8')
            (responses / '2020-04.json').write_text(json.dumps(second), encoding='utf-8')
            out = folder / 'tracking'
            first_run = self.run_cli('--new-image', ROOT / 'datasets/aigawa/images/2019-06.png',
                                     '--date', '2019-06', '--responses', responses, '--skip-cv',
                                     '--fixed-camera', '--out', out)
            second_run = self.run_cli('--new-image', ROOT / 'datasets/aigawa/images/2020-04.png',
                                      '--date', '2020-04', '--responses', responses, '--skip-cv',
                                      '--fixed-camera', '--out', out)
            self.assertIn('[本期识别结果]', first_run.stdout)
            self.assertIn('首期没有上一期图像', first_run.stdout)
            self.assertIn('[本期识别结果]', second_run.stdout)
            self.assertIn('[固定镜头变化]', second_run.stdout)
            self.assertIn('同一画面区域新增成型段', second_run.stdout)
            self.assertIn('大坝主体：', second_run.stdout)
            state = json.loads((out / 'history.json').read_text(encoding='utf-8'))
            self.assertEqual(state['mode'], 'offline_test_fixed_camera')
            self.assertEqual(state['history'][0]['temporal_changes'], [])
            self.assertEqual(state['history'][1]['temporal_changes'][0]['direction'], 'advanced')
            self.assertEqual(state['history'][1]['temporal_review']['accepted_changes'], 1)
            prompt = (out / 'observations/2020-04/prompt.txt').read_text(encoding='utf-8')
            self.assertIn('上一期原图为图1，本期原图为图2', prompt)
            self.assertIsNone(state['history'][1]['overall']['project_progress_pct'])
            report = (out / 'latest_report.md').read_text(encoding='utf-8')
            self.assertIn('固定镜头时序变化', report)
            self.assertIn('同一画面区域新增成型段', report)

            original = (out / 'history.json').read_bytes()
            self.run_cli('--refresh-only', '--out', out)
            self.assertEqual((out / 'history.json').read_bytes(), original)
            mixed = self.run_cli('--new-image', ROOT / 'datasets/aigawa/images/2021-01.png',
                                 '--date', '2021-01', '--responses', responses,
                                 '--skip-cv', '--out', out, check=False)
            self.assertNotEqual(mixed.returncode, 0)
            self.assertIn('运行模式不一致', mixed.stderr)
            self.assertEqual((out / 'history.json').read_bytes(), original)

    def test_offline_refresh_inherits_saved_mode_without_response_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            responses = folder / 'responses'
            responses.mkdir()
            (responses / '2019-06.json').write_text('{"stages": []}', encoding='utf-8')
            out = folder / 'tracking'
            self.run_cli(
                '--new-image', ROOT / 'datasets/aigawa/images/2019-06.png',
                '--date', '2019-06', '--responses', responses,
                '--skip-cv', '--out', out,
            )
            original = (out / 'history.json').read_bytes()
            (responses / '2019-06.json').unlink()
            responses.rmdir()
            (out / 'latest_progress.png').unlink()

            result = self.run_cli('--refresh-only', '--out', out)

            self.assertIn('未调用 API', result.stdout)
            self.assertEqual((out / 'history.json').read_bytes(), original)
            self.assertEqual((out / 'history.v4.backup.json').read_bytes(), original)
            self.assertTrue((out / 'latest_progress.png').is_file())
            self.assertIn('模拟数据', (out / 'latest_report.md').read_text(encoding='utf-8'))
            self.assertFalse((out / '.update.lock').exists())

    def test_new_live_observation_cannot_mix_with_offline_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            context = json.loads((ROOT / 'config/aigawa_context.json').read_text(encoding='utf-8'))
            context = {k: v for k, v in context.items() if k in ('project_name', 'dam_type', 'scope_note')}
            state = dict(version=1, context=context, mode='offline_test', history=[])
            atomic_json(out / 'history.json', state)
            original = (out / 'history.json').read_bytes()

            result = self.run_cli('--all', '--out', out, check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('运行模式不一致', result.stdout + result.stderr)
            self.assertEqual((out / 'history.json').read_bytes(), original)
            self.assertFalse((out / '.update.lock').exists())


if __name__ == '__main__':
    unittest.main()
