"""Regression coverage for local history, recovery, and audited CLI workflows."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
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
