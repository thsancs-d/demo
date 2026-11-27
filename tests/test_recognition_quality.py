"""V8 must withhold unsupported percentages without rewriting legacy history."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from progress_tracker import current_rows, update_estimates


def response(confidence=0.9, image_number=1):
    ids = ('preparation', 'dam_foundation', 'diversion', 'dam_body', 'spillway',
           'intake_outlet', 'electromechanical', 'ancillary')
    return {'stages': [dict(
        id=sid, status='in_progress', evidence='测试：本期画面中可定位的完整分项范围',
        confidence=confidence,
        observation=dict(image_number=image_number, bbox_xyxy=[0.04 + i * 0.01, 0.2, 0.8 - i * 0.01, 0.9],
                         visibility='clear', scope='full', basis='visible_extent'),
        progress_estimate=dict(percent=60, range_pct=[50, 70],
                               scope_basis='测试：完整计划边界', completed_basis='测试：完成与剩余范围'),
    ) for i, sid in enumerate(ids)], 'inferred_stages': [], 'changes': [], 'risks': [], 'summary': '模拟响应'}


class AccuracyWorkflowTests(unittest.TestCase):
    def test_low_confidence_percentages_do_not_enter_new_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = root / 'responses'
            responses.mkdir()
            (responses / '2019-06.json').write_text(json.dumps(response(0.1)), encoding='utf-8')
            out = root / 'tracking'
            run = subprocess.run([
                sys.executable, str(ROOT / 'src/run_aigawa.py'), '--new-image',
                str(ROOT / 'datasets/aigawa/images/2019-06.png'), '--date', '2019-06',
                '--responses', str(responses), '--skip-cv', '--out', str(out),
            ], cwd=ROOT, text=True, capture_output=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            saved = json.loads((out / 'history.json').read_text(encoding='utf-8'))['history'][0]
            self.assertIsNone(saved['overall']['project_progress_pct'])
            self.assertEqual(saved['overall']['current_coverage_pct'], 0)
            self.assertTrue(all(r['progress_estimate'] is None for r in saved['stages']))
            self.assertEqual(saved['quality_review']['rejected_estimates'], 8)
            self.assertIn('置信度', (out / 'latest_report.md').read_text(encoding='utf-8'))
            raw = json.loads((out / 'observations/2019-06/raw_model.json').read_text(encoding='utf-8'))
            self.assertEqual(raw['stages'][0]['progress_estimate']['percent'], 60)


class EvidenceFilterTests(unittest.TestCase):
    def filtered(self, raw, image_number=1):
        from recognition_quality import filter_observations
        return filter_observations(raw, image_number)

    def test_valid_evidence_is_preserved_without_mutating_response(self):
        raw = response()
        original = copy.deepcopy(raw)
        filtered, review = self.filtered(raw)
        self.assertEqual(raw, original)
        self.assertEqual(filtered['stages'][3]['progress_estimate']['percent'], 60)
        self.assertEqual(review['accepted_estimates'], 8)
        self.assertEqual(review['rejected_estimates'], 0)

    def test_wrong_image_including_boolean_cannot_be_current_evidence(self):
        for image_number in (2, 3, True, 1.0, None):
            with self.subTest(image_number=image_number):
                filtered, review = self.filtered(response(image_number=image_number))
                self.assertTrue(all(r['progress_estimate'] is None for r in filtered['stages']))
                self.assertEqual(review['rejected_estimates'], 8)

    def test_invalid_or_low_confidence_is_rejected(self):
        for confidence in (0.69, None, True, float('nan'), float('inf'), 1.1):
            with self.subTest(confidence=confidence):
                filtered, _ = self.filtered(response(confidence))
                self.assertIsNone(filtered['stages'][3]['progress_estimate'])
        filtered, _ = self.filtered(response(0.7))
        self.assertEqual(filtered['stages'][3]['progress_estimate']['percent'], 60)

    def test_local_or_unseen_scope_and_wrong_measurement_basis_are_rejected(self):
        for key, value in [('visibility', 'partial'), ('visibility', 'not_visible'),
                           ('scope', 'partial'), ('scope', 'unknown'),
                           ('basis', 'height_ratio'), ('basis', 'pixel_change')]:
            with self.subTest(key=key, value=value):
                raw = response()
                raw['stages'][3]['observation'][key] = value
                filtered, review = self.filtered(raw)
                self.assertIsNone(filtered['stages'][3]['progress_estimate'])
                self.assertEqual(review['accepted_estimates'], 7)

    def test_missing_or_invalid_boxes_are_rejected(self):
        for box in (None, [0, 0, 0, 1], [-0.1, 0, 1, 1], [0, 0, 1.1, 1],
                    [0, 0, True, 1], [0, 0, float('nan'), 1], [0, 0, 1]):
            with self.subTest(box=box):
                raw = response()
                raw['stages'][3]['observation']['bbox_xyxy'] = box
                filtered, _ = self.filtered(raw)
                self.assertIsNone(filtered['stages'][3]['progress_estimate'])
        raw = response()
        del raw['stages'][3]['observation']
        filtered, _ = self.filtered(raw)
        self.assertIsNone(filtered['stages'][3]['progress_estimate'])

    def test_false_precision_and_duplicate_stages_cannot_pass_review(self):
        raw = response()
        raw['stages'][3]['progress_estimate']['range_pct'] = [60, 60]
        filtered, _ = self.filtered(raw)
        self.assertIsNone(filtered['stages'][3]['progress_estimate'])
        raw = response()
        raw['stages'].append(copy.deepcopy(raw['stages'][3]))
        filtered, review = self.filtered(raw)
        self.assertEqual(review['accepted_estimates'], 7)
        self.assertTrue(all(r['progress_estimate'] is None for r in filtered['stages'] if r['id'] == 'dam_body'))

    def test_identical_evidence_boxes_are_rejected_for_ambiguous_parts(self):
        raw = response()
        shared = raw['stages'][0]['observation']['bbox_xyxy']
        for stage in raw['stages']:
            stage['observation']['bbox_xyxy'] = list(shared)
        filtered, review = self.filtered(raw)
        self.assertEqual(review['accepted_estimates'], 0)
        self.assertEqual(review['rejected_estimates'], 8)
        self.assertTrue(all(stage['progress_estimate'] is None for stage in filtered['stages']))
        raw = response()
        raw['stages'][1]['observation']['bbox_xyxy'] = list(raw['stages'][0]['observation']['bbox_xyxy'])
        filtered, review = self.filtered(raw)
        self.assertEqual(review['accepted_estimates'], 6)
        self.assertIsNone(filtered['stages'][0]['progress_estimate'])
        self.assertIsNone(filtered['stages'][1]['progress_estimate'])
        self.assertEqual(filtered['stages'][2]['progress_estimate']['percent'], 60)

    def test_dam_body_and_spillway_semantic_conflicts_are_rejected(self):
        raw = response()
        raw['stages'][3]['evidence'] = '右侧混凝土泄槽和溢洪道成型面可见，坝体范围不可辨。'
        filtered, review = self.filtered(raw)
        self.assertIsNone(filtered['stages'][3]['progress_estimate'])
        raw = response()
        raw['stages'][4]['evidence'] = '中央堆石坝体填筑面和坝坡可见。'
        filtered, review = self.filtered(raw)
        self.assertIsNone(filtered['stages'][4]['progress_estimate'])

    def test_history_retains_evidence_but_does_not_anchor_numeric_estimates(self):
        from recognition_quality import evidence_history
        history = [dict(date='2020-01', stages=current_rows(response(), None, '2020-01'),
                        overall={'project_progress_pct': 88.123456}, changes=[])]
        result = evidence_history(history)
        encoded = json.dumps(result)
        self.assertNotIn('88.123456', encoded)
        self.assertNotIn('percent', encoded)
        self.assertNotIn('range_pct', encoded)
        self.assertEqual(result['history'][0]['date'], '2020-01')
        self.assertEqual(result['history'][0]['stages'][3]['source'], 'current_image')
        self.assertEqual(result['history'][0]['stages'][3]['evidence'], '测试：本期画面中可定位的完整分项范围')

    def test_v8_withholds_total_for_missing_stages_and_legacy_keeps_extrapolation(self):
        rows = current_rows(response(), None, '2020-01')
        rows[1].update(progress_estimate=None, source='unknown', observed_date=None)
        old = dict(date='2020-01', stages=copy.deepcopy(rows), prompt_version='v7-cumulative-evidence')
        new = dict(date='2020-02', stages=copy.deepcopy(rows), prompt_version='v8-grounded-evidence')
        update_estimates({'history': [old, new]})
        self.assertEqual(old['overall']['project_progress_pct'], 60)
        self.assertIsNone(new['overall']['project_progress_pct'])
        self.assertEqual(new['overall']['assessed_only_pct'], 60)
        self.assertEqual(new['overall']['total_possible_range_pct'], [45, 73])
        self.assertEqual(new['overall']['extrapolated_stages'], [])
        self.assertTrue(new['overall']['previous_method_changed'])

    def test_fixed_camera_refresh_keeps_v8_strict_percentage_policy(self):
        from recognition_quality import TEMPORAL_PROMPT_VERSION
        rows = current_rows(response(), None, '2020-01')
        rows[1].update(progress_estimate=None, source='unknown', observed_date=None)
        history = [dict(date='2020-01', stages=rows,
                        prompt_version=TEMPORAL_PROMPT_VERSION)]

        update_estimates({'history': history})

        self.assertIsNone(history[0]['overall']['project_progress_pct'])
        self.assertEqual(history[0]['overall']['project_progress_method'], 'insufficient_evidence')
        self.assertEqual(history[0]['overall']['extrapolated_stages'], [])

    def test_same_method_name_still_marks_policy_transition(self):
        rows = current_rows(response(), None, '2020-01')
        history = [dict(date='2020-01', stages=rows, prompt_version='v7-cumulative-evidence'),
                   dict(date='2020-02', stages=rows, prompt_version='v8-grounded-evidence')]
        update_estimates({'history': history})
        self.assertEqual(history[-1]['overall']['project_progress_pct'], 60)
        self.assertTrue(history[-1]['overall']['previous_method_changed'])

    def test_temporal_changes_require_both_images_same_region_and_unique_event(self):
        from recognition_quality import filter_temporal_changes
        event = dict(stage_id='spillway', direction='advanced', change_type='new_work',
                     evidence_image_numbers=[2, 3], bbox_xyxy=[.1, .2, .4, .6],
                     where='右侧泄槽', what='同一区域新增成型混凝土段', confidence=.8,
                     visibility='partial', basis='same_region_comparison')
        accepted, review = filter_temporal_changes({'temporal_changes': [event, copy.deepcopy(event)]}, 2, 3)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(review['accepted_changes'], 1)
        self.assertEqual(review['rejected_changes'], 1)

    def test_temporal_changes_reject_wrong_images_boxes_and_pixel_only_basis(self):
        from recognition_quality import filter_temporal_changes
        base = dict(stage_id='dam_body', direction='advanced', change_type='expanded',
                    evidence_image_numbers=[1, 3], bbox_xyxy=[.1, .2, .4, .6],
                    where='坝体', what='同一区域扩大', confidence=.8,
                    visibility='clear', basis='pixel_change')
        accepted, review = filter_temporal_changes({'temporal_changes': [base]}, 2, 3)
        self.assertEqual(accepted, [])
        self.assertEqual(review['rejected_changes'], 1)

    def test_temporal_first_period_is_empty(self):
        from recognition_quality import filter_temporal_changes
        accepted, review = filter_temporal_changes({'temporal_changes': [{'stage_id': 'dam_body'}]}, None, 1)
        self.assertEqual(accepted, [])
        self.assertEqual(review['accepted_changes'], 0)

    def test_temporal_unseen_invalid_and_nonfinite_events_are_rejected_individually(self):
        from recognition_quality import filter_temporal_changes
        event = dict(stage_id='spillway', direction='advanced', change_type='new_work',
                     evidence_image_numbers=[1, 2], bbox_xyxy=[.1, .2, .4, .6],
                     where='右侧泄槽', what='同一区域新增成型段', confidence=.8,
                     visibility='partial', basis='same_region_comparison')
        invalid_values = [
            ('visibility', 'not_visible'), ('confidence', 1.1),
            ('confidence', .69), ('confidence', float('nan')),
            ('bbox_xyxy', [.1, .2, float('nan'), .6]),
            ('direction', []), ('change_type', {}), ('stage_id', []),
            ('where', []), ('visibility', []),
        ]
        for key, value in invalid_values:
            with self.subTest(key=key, value=value):
                invalid = {**event, key: value}
                accepted, review = filter_temporal_changes(
                    {'temporal_changes': [invalid, event]}, 1, 2)
                self.assertEqual(accepted, [event])
                self.assertEqual(review['rejected_changes'], 1)

    def test_temporal_text_observation_recovers_string_evidence_without_mutating_raw(self):
        from recognition_quality import normalize_temporal_response
        raw = {'stages': [{
            'id': 'dam_body', 'status': 'in_progress', 'evidence': [1, 2],
            'observation': '本期画面可见坝体填筑面扩大。', 'confidence': 0.86,
            'progress_estimate': None,
        }]}

        normalized = normalize_temporal_response(raw)

        self.assertEqual(normalized['stages'][0]['evidence'], '本期画面可见坝体填筑面扩大。')
        self.assertEqual(raw['stages'][0]['evidence'], [1, 2])
        self.assertEqual(normalized['stages'][0]['observation'], '本期画面可见坝体填筑面扩大。')

    def test_temporary_or_unknown_event_cannot_claim_advanced_direction(self):
        from recognition_quality import filter_temporal_changes
        event = dict(stage_id='preparation', direction='advanced', change_type='temporary_change',
                     evidence_image_numbers=[1, 2], bbox_xyxy=[.1, .2, .4, .6],
                     where='施工场地', what='临时设备增加', confidence=.8,
                     visibility='partial', basis='same_region_comparison')

        accepted, review = filter_temporal_changes({'temporal_changes': [event]}, 1, 2)

        self.assertEqual(accepted, [])
        self.assertEqual(review['rejected_changes'], 1)


if __name__ == '__main__':
    unittest.main()
