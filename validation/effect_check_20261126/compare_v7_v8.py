#!/usr/bin/env python3
"""Compare real V7/V8 functions on controlled synthetic model responses.

Run from the repository root:
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B \
    validation/effect_check_20261126/compare_v7_v8.py

The output path is created exclusively; pass a different --out to rerun without
overwriting an earlier result. No model API, environment file, or real accuracy
label is used. These cases verify filtering/aggregation behavior only.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'src'))
from progress_tracker import current_rows, estimate_breakdown, estimate_supported
from recognition_quality import filter_observations
from stages import get_stages


LABEL = 'synthetic_response_not_real_accuracy'


def base_response():
    return {
        'stages': [
            {
                'id': stage['id'],
                'status': 'in_progress',
                'evidence': '合成输入：本期画面中可定位的完整分项范围。',
                'confidence': 0.9,
                'observation': {
                    'image_number': 1,
                    'bbox_xyxy': [0.1, 0.2, 0.8, 0.9],
                    'visibility': 'clear',
                    'scope': 'full',
                    'basis': 'visible_extent',
                },
                'progress_estimate': {
                    'percent': 60,
                    'range_pct': [50, 70],
                    'scope_basis': '合成输入：完整计划边界。',
                    'completed_basis': '合成输入：完成与剩余范围可估算。',
                },
                'carry_previous': False,
            }
            for stage in get_stages('reservoir')
        ],
        'inferred_stages': [],
        'changes': [],
        'risks': [],
        'summary': '受控合成响应，仅验证规则行为，不代表真实影像识别准确率。',
    }


def make_case(case_id):
    raw = base_response()
    for stage in raw['stages']:
        observation = stage['observation']
        if case_id == 'low_confidence_all':
            stage['confidence'] = 0.1
        elif case_id == 'wrong_image_number_all':
            observation['image_number'] = 2
        elif case_id == 'partial_visibility_all':
            observation['visibility'] = 'partial'
        elif case_id == 'unknown_scope_all':
            observation['scope'] = 'unknown'
        elif case_id == 'invalid_bbox_all':
            observation['bbox_xyxy'] = [0.1, 0.2, 0.1, 0.9]
        elif case_id == 'zero_width_interval_all':
            stage['progress_estimate']['range_pct'] = [60, 60]
        elif case_id == 'dam_foundation_estimate_missing' and stage['id'] == 'dam_foundation':
            stage['progress_estimate'] = None
    return raw


def run_case(case_id, description):
    raw = make_case(case_id)
    original = copy.deepcopy(raw)
    old_rows = current_rows(raw, None, '2026-11-26')
    old_overall = estimate_breakdown(old_rows, raw['inferred_stages'])
    filtered, review = filter_observations(raw, current_image_number=1)
    new_rows = current_rows(filtered, None, '2026-11-26')
    new_overall = estimate_supported(new_rows)
    assert raw == original, 'Filtering mutated the original response'
    old_retained = sum(row['progress_estimate'] is not None for row in old_rows)
    new_retained = sum(row['progress_estimate'] is not None for row in new_rows)
    assert old_overall['project_progress_pct'] == 60
    assert new_overall['extrapolated_stages'] == []
    if case_id == 'valid_all':
        assert new_overall['project_progress_pct'] == 60
        assert new_overall['current_coverage_pct'] == 100
        assert new_overall['total_possible_range_pct'] == [50, 70]
        assert review['accepted_estimates'] == 8
        assert review['rejected_estimates'] == 0
    elif case_id == 'dam_foundation_estimate_missing':
        assert new_overall['project_progress_pct'] is None
        assert old_overall['current_coverage_pct'] == new_overall['current_coverage_pct'] == 90
        assert new_overall['total_possible_range_pct'] == [45, 73]
        assert old_overall['extrapolated_stages'][0]['id'] == 'dam_foundation'
        assert old_overall['extrapolated_stages'][0]['weight'] == 10
        assert review['accepted_estimates'] == 7
        assert review['rejected_estimates'] == 0
    else:
        assert new_overall['project_progress_pct'] is None
        assert new_overall['current_coverage_pct'] == 0
        assert new_overall['total_possible_range_pct'] == [0, 100]
        assert review['accepted_estimates'] == 0
        assert review['rejected_estimates'] == 8
    return {
        'case_id': case_id,
        'description': description,
        'evidence_type': LABEL,
        'input': raw,
        'v7': {
            'function_path': 'current_rows(raw, None, date) -> estimate_breakdown(rows, [])',
            'overall': old_overall,
            'retained_current_estimates': old_retained,
            'quality_filter_applied': False,
            'quality_rejected_estimates': None,
        },
        'v8': {
            'function_path': 'filter_observations(raw, 1) -> current_rows(filtered, None, date) -> estimate_supported(rows)',
            'overall': new_overall,
            'retained_current_estimates': new_retained,
            'quality_filter_applied': True,
            'quality_review': review,
        },
        'assertions_passed': True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path(__file__).with_name('controlled_v7_v8_results.json'))
    args = parser.parse_args()
    descriptions = [
        ('valid_all', '全部8项满足证据规则，60%，区间50–70%。'),
        ('low_confidence_all', '全部8项置信度从0.9降至0.1。'),
        ('wrong_image_number_all', '全部8项证据图号为2，本期图号为1。'),
        ('partial_visibility_all', '全部8项可见性改为partial。'),
        ('unknown_scope_all', '全部8项完整计划范围改为unknown。'),
        ('invalid_bbox_all', '全部8项证据框宽度为0。'),
        ('zero_width_interval_all', '全部8项施工中估算区间改为[60,60]。'),
        ('dam_foundation_estimate_missing', '仅将权重10%的坝基分项估算置空，其余7项不变。'),
    ]
    stages = get_stages('reservoir')
    assert len(stages) == 8 and sum(stage['weight'] for stage in stages) == 100
    results = [run_case(case_id, description) for case_id, description in descriptions]
    report = {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'evidence_type': LABEL,
        'purpose': '验证实际代码的证据筛选、区间汇总和停止外推行为；不评估视觉模型准确率。',
        'model_api_used': False,
        'ground_truth_available': False,
        'accuracy_metric_computed': False,
        'v7_label_means': '当前代码中保留的V7汇总路径；不是重新运行历史V7视觉模型。',
        'v8_label_means': '当前代码的V8证据筛选与汇总路径；没有调用视觉模型。',
        'total_cases': len(results),
        'all_case_assertions_passed': all(result['assertions_passed'] for result in results),
        'source_sha256': {
            filename: hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
            for filename in ('src/progress_tracker.py', 'src/recognition_quality.py', 'src/visual_phase.py', 'src/stages.py')
        },
        'stage_weights': [{'id': stage['id'], 'weight': stage['weight']} for stage in stages],
        'cases': results,
    }
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(f'Created {args.out.resolve()}')
    for result in results:
        old = result['v7']['overall']
        new = result['v8']['overall']
        review = result['v8']['quality_review']
        print(f"{result['case_id']}: V7 total={old['project_progress_pct']}, "
              f"V8 total={new['project_progress_pct']}, "
              f"coverage={new['current_coverage_pct']}, range={new['total_possible_range_pct']}, "
              f"accepted={review['accepted_estimates']}, rejected={review['rejected_estimates']}")
    print(f'{len(results)}/{len(results)} controlled behavior assertions passed; {LABEL}')


if __name__ == '__main__':
    main()
