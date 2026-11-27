"""Web boundary tests: actual upload handling and offline CLI, no paid API calls."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def picture(color):
    data = io.BytesIO()
    Image.new('RGB', (160, 120), color).save(data, format='PNG')
    return data.getvalue()


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-no-network'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def client(self, runner=None):
        from web_app import create_app
        app = create_app(Path(self.temp.name), **({'run_command': runner} if runner else {}))
        client = TestClient(app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def upload(self, client, dates=None, images=None):
        return client.post('/api/jobs', data={
            'project_name': '测试水库', 'dam_type': '岩石填筑坝',
            'dates': json.dumps(dates or ['2019-06-01', '2020-04-01']),
        }, files=[('photos', (f'photo{i}.png', data, 'image/png'))
                  for i, data in enumerate(images or [picture('red'), picture('blue')])])

    def wait_job(self, client, job_id):
        until = time.monotonic() + 35
        while time.monotonic() < until:
            result = client.get('/api/jobs/' + job_id).json()
            if result['status'] in ('succeeded', 'failed'):
                return result
            time.sleep(.04)
        self.fail('job did not finish')

    def test_demo_preserves_unknown_progress_and_serves_originals(self):
        client = self.client()
        response = client.get('/api/demo')
        self.assertEqual(response.status_code, 200)
        demo = response.json()
        self.assertEqual(demo['source'], 'historical_replay')
        self.assertEqual(len(demo['history']), 4)
        latest = demo['history'][-1]
        self.assertIsNone(latest['overall']['project_progress_pct'])
        self.assertIsInstance(latest['construction_overview']['overall']['display_progress_pct'], float)
        self.assertIsInstance(latest['temporal_changes'], list)
        self.assertEqual(latest['construction_overview']['overall']['status'], 'estimated')
        self.assertEqual(latest['construction_overview']['overall']['construction_state'], 'visible_work_in_progress_partial')
        self.assertEqual(latest['construction_overview']['overall']['status_coverage_pct'], 65.0)
        self.assertEqual(latest['construction_overview']['overall']['active_stage_weight_pct'], 65.0)
        parts = latest['construction_overview']['parts']
        self.assertEqual(len(parts), 8)
        self.assertEqual(parts[0]['name'], '施工准备与临时道路')
        self.assertIn(parts[0]['status'], ('in_progress', 'unclear', 'completed', 'not_started'))
        self.assertIn('evidence', parts[0])
        self.assertIsInstance(parts[0]['observation']['bbox_xyxy'], list)
        self.assertEqual(len(parts[0]['observation']['bbox_xyxy']), 4)
        self.assertEqual(client.get(latest['image_url']).status_code, 200)
        self.assertEqual(client.get('/api/demo/photos/99').status_code, 404)
        self.assertEqual(client.get('/.env').status_code, 404)

    def test_rejects_invalid_content_dates_and_duplicates_without_jobs(self):
        client = self.client()
        for dates, images in [
            (['2020-01-01', '2020-01-01'], None),
            (['2020-02-30', '2020-04-01'], None),
            (['2020-01-01'], None),
            (None, [b'not an image', picture('blue')]),
            (None, [picture('red'), picture('red')]),
        ]:
            with self.subTest(dates=dates):
                self.assertEqual(self.upload(client, dates, images).status_code, 400)
        self.assertEqual(client.get('/api/jobs').json(), [])

    def test_cross_origin_submission_rejected(self):
        client = self.client()
        response = client.post('/api/jobs', headers={'Origin': 'https://unrelated.example'})
        self.assertEqual(response.status_code, 403)

    def test_missing_credentials_is_actionable_and_creates_no_job(self):
        client = self.client()
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': ''}):
            self.assertFalse(client.get('/api/status').json()['model_configured'])
            response = self.upload(client)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(client.get('/api/jobs').json(), [])

    def test_upload_runs_actual_pipeline_sorts_dates_and_survives_restart(self):
        # Only replace external model I/O by adding the existing response fixture.
        def offline_command(command, **kwargs):
            dt = command[command.index('--date') + 1]
            command[command.index('--date') + 1] = dt[:7]
            return subprocess.run(command + ['--responses', str(ROOT / 'tests/fixtures/aigawa_responses_v8')], **kwargs)
        client = self.client(offline_command)
        response = self.upload(client, ['2020-04-01', '2019-06-01'])
        self.assertEqual(response.status_code, 202, response.text)
        job_id = response.json()['id']
        result = self.wait_job(client, job_id)
        self.assertEqual(result['status'], 'succeeded', result)
        self.assertEqual(result['completed'], 2)
        result = client.get(f'/api/jobs/{job_id}/result').json()
        self.assertEqual([h['date'] for h in result['history']], ['2019-06', '2020-04'])
        self.assertEqual(result['history'][0]['temporal_changes'], [])
        self.assertEqual(client.get(result['history'][1]['image_url']).status_code, 200)
        self.assertEqual(client.get(f'/api/jobs/{job_id}/photos/../../.env').status_code, 404)
        self.assertEqual(self.client().get(f'/api/jobs/{job_id}').json()['status'], 'succeeded')

    def test_failure_is_safe_and_retryable(self):
        def failing(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, stdout='SECRET_KEY=do-not-send-to-browser')
        client = self.client(failing)
        job_id = self.upload(client).json()['id']
        result = self.wait_job(client, job_id)
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('SECRET_KEY', json.dumps(result))
        self.assertEqual(client.get(f'/api/jobs/{job_id}/result').status_code, 409)
        self.assertEqual(client.post(f'/api/jobs/{job_id}/retry').status_code, 202)
        self.assertEqual(self.wait_job(client, job_id)['attempt'], 2)


if __name__ == '__main__':
    unittest.main()
