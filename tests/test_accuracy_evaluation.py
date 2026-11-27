"""Ground truth metrics must not confuse abstention, simulation, and real error."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def fixtures():
    labels = {'project': '测试水库', 'records': [
        dict(date=dt, stage_id='dam_body', metric='visual_completion_pct', percent=p,
             verified=True, source='人工复核记录：测试夹具', scope_basis='坝体可见填筑范围',
             image_sha256='a' * 64)
        for dt, p in [('2020-01', 40), ('2020-02', 60), ('2020-03', 80)]]}
    state = {'mode': 'live', 'context': {'project_name': '测试水库'}, 'history': [
        dict(date=dt, execution_mode='live', sha256='a' * 64, stages=[
            dict(id='dam_body', source='current_image', observed_date=dt,
                 progress_estimate=dict(percent=p, range_pct=[p-10, p+10]) if p is not None else None)])
        for dt, p in [('2020-01', 50), ('2020-02', 55), ('2020-03', None)]]}
    return labels, state


class TrackingEvaluationTests(unittest.TestCase):
    def evaluate(self, labels, state, tolerance_pp=10):
        from evaluate import evaluate_tracking
        return evaluate_tracking(labels, state, tolerance_pp)

    def test_metrics_include_abstention_coverage_and_hand_calculated_error(self):
        labels, state = fixtures()
        result = self.evaluate(labels, state)
        self.assertEqual(result['eligible_labels'], 3)
        self.assertEqual(result['predictions'], 2)
        self.assertEqual(result['abstentions'], 1)
        self.assertAlmostEqual(result['prediction_coverage_pct'], 66.67, places=2)
        self.assertEqual(result['mae_pp'], 7.5)
        self.assertEqual(result['bias_pp'], 2.5)
        self.assertEqual(result['within_tolerance_pct'], 100)
        self.assertEqual(result['interval_coverage_pct'], 100)
        self.assertEqual(result['mean_interval_width_pp'], 20)

    def test_only_explicitly_verified_labels_with_sources_and_matching_metric(self):
        for field, value in [('verified', False), ('verified', 1), ('source', ''),
                             ('metric', 'measured_volume_pct'), ('percent', True),
                             ('percent', float('nan')), ('percent', 101), ('scope_basis', '')]:
            with self.subTest(field=field, value=value):
                labels, state = fixtures()
                for label in labels['records']:
                    label[field] = value
                result = self.evaluate(labels, state)
                self.assertEqual(result['eligible_labels'], 0)
                self.assertIsNone(result['mae_pp'])
                self.assertIsNone(result['within_tolerance_pct'])

    def test_simulated_or_other_project_data_never_produces_metrics(self):
        labels, original = fixtures()
        for mode in ('offline_test', 'offline_replay', None):
            state = copy.deepcopy(original)
            state['mode'] = mode
            result = self.evaluate(labels, state)
            self.assertEqual(result['predictions'], 0)
            self.assertIsNone(result['mae_pp'])
        state = copy.deepcopy(original)
        state['context']['project_name'] = '另一工程'
        self.assertEqual(self.evaluate(labels, state)['predictions'], 0)

    def test_each_observation_must_be_live_current_and_for_the_labeled_photo(self):
        labels, state = fixtures()
        state['history'][0]['execution_mode'] = 'offline_test'
        state['history'][1]['sha256'] = 'b' * 64
        result = self.evaluate(labels, state)
        self.assertEqual(result['predictions'], 0)
        self.assertEqual(result['abstentions'], 3)
        self.assertIsNone(result['mae_pp'])
        labels, state = fixtures()
        state['history'][0]['stages'][0]['source'] = 'historical_only'
        state['history'][1]['stages'][0]['observed_date'] = '2020-01'
        self.assertEqual(self.evaluate(labels, state)['predictions'], 0)

    def test_invalid_estimates_do_not_bias_metrics(self):
        for estimate in (dict(percent=True, range_pct=[0, 100]),
                         dict(percent=50, range_pct=[60, 70]),
                         dict(percent=float('inf'), range_pct=[0, 100]),
                         dict(percent=50, range_pct=[0, 101]),
                         dict(percent=50, range_pct=[50, float('nan')])):
            with self.subTest(estimate=estimate):
                labels, state = fixtures()
                for h in state['history']:
                    h['stages'][0]['progress_estimate'] = estimate
                self.assertEqual(self.evaluate(labels, state)['predictions'], 0)

    def test_duplicate_labels_and_observation_dates_are_rejected(self):
        labels, state = fixtures()
        labels['records'].append(copy.deepcopy(labels['records'][0]))
        with self.assertRaises(ValueError):
            self.evaluate(labels, state)
        labels, state = fixtures()
        state['history'].append(copy.deepcopy(state['history'][0]))
        with self.assertRaises(ValueError):
            self.evaluate(labels, state)

    def test_missing_period_and_duplicate_stage_count_as_abstention(self):
        labels, state = fixtures()
        state['history'].pop(0)
        state['history'][0]['stages'].append(copy.deepcopy(state['history'][0]['stages'][0]))
        result = self.evaluate(labels, state)
        self.assertEqual(result['eligible_labels'], 3)
        self.assertEqual(result['predictions'], 0)
        self.assertEqual(result['prediction_coverage_pct'], 0)

    def test_empty_or_unverified_legacy_labels_do_not_fabricate_accuracy(self):
        _, state = fixtures()
        for labels in ({'project': '测试水库', 'records': []},
                       {'project': '测试水库', 'records': [{'month': '2020-01', 'dam_fill_percent': 100}]}):
            result = self.evaluate(labels, state)
            self.assertIsNone(result['mae_pp'])
            self.assertIsNone(result['prediction_coverage_pct'])
            self.assertIsNone(result['within_tolerance_pct'])

    def test_invalid_tolerance_rejected(self):
        labels, state = fixtures()
        for tolerance in (-1, True, float('nan'), float('inf')):
            with self.subTest(tolerance=tolerance), self.assertRaises(ValueError):
                self.evaluate(labels, state, tolerance)

    def test_history_cli_writes_metrics_for_verified_live_fixture(self):
        labels, state = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'labels.json').write_text(json.dumps(labels), encoding='utf-8')
            (root / 'history.json').write_text(json.dumps(state), encoding='utf-8')
            result = subprocess.run([
                sys.executable, str(ROOT / 'src/evaluate.py'), '--labels', str(root / 'labels.json'),
                '--history', str(root / 'history.json'), '--tolerance-pp', '5',
            ], text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['within_tolerance_pct'], 50)
            self.assertEqual(report['mae_pp'], 7.5)


if __name__ == '__main__':
    unittest.main()
