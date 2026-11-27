"""Evaluate verified visual stage labels against live tracking or legacy reports."""
import argparse,json
import math
import re
from pathlib import Path
from datetime import date

from stages import get_stages

def evaluate(labels, reports):
    truth = {r['month']:r for r in labels['records'] if r.get('dam_fill_percent') == 100}
    rows=[]
    for report in reports:
        meta=report.get('meta',{}); month=meta.get('after_date')
        if month not in truth or meta.get('execution_mode')!='live': continue
        if (meta.get('context') or {}).get('project_name') != labels.get('project'): continue
        dam=next((r for r in report.get('progress',{}).get('stages',[]) if r.get('id')=='dam_body'),{})
        est=dam.get('progress_estimate'); phase=dam.get('phase','unclear')
        value=est['percent'] if est else None
        verdict='无法估算' if value is None else '与填筑完成标签一致' if value==100 else '与填筑完成标签不一致（需复核）'
        rows.append({'date':month,'label':'坝体填筑完成','label_percent':100,'predicted_visual_percent':value,'predicted_range_pct':est['range_pct'] if est else None,'endpoint_difference_pp':round(value-100,2) if value is not None else None,'predicted_phase':phase,'verdict':verdict,'note':'仅验证坝体填筑完成节点；不能用外观估计验证体积误差或全水库进度。'})
    return rows

def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _date_valid(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?', value):
        return False
    try:
        date.fromisoformat(value + '-01' if len(value) == 7 else value)
    except ValueError:
        return False
    return True


def evaluate_tracking(labels, state, tolerance_pp=10):
    """MAE is conditional on predictions; coverage includes withheld/missing results."""
    if not _number(tolerance_pp) or tolerance_pp < 0:
        raise ValueError('误差阈值须为非负有限数值（百分点）')
    if not isinstance(labels, dict) or not isinstance(labels.get('records'), list):
        raise ValueError('标签必须包含 records 数组')
    if not isinstance(state, dict) or not isinstance(state.get('history'), list):
        raise ValueError('历史必须包含 history 数组')
    result = dict(metric='visual_completion_pct', tolerance_pp=tolerance_pp,
                  eligible_labels=0, excluded_labels=0, predictions=0, abstentions=0,
                  prediction_coverage_pct=None, mae_pp=None, bias_pp=None,
                  within_tolerance_pct=None, interval_coverage_pct=None,
                  mean_interval_width_pp=None, comparisons=[], notes=[
                      '误差与阈值内比例仅针对已给出预测的样本，须同时查看预测覆盖率。',
                      '标签来源及分项口径由标注者核验；本程序不验证来源真实性。'])
    project = labels.get('project')
    context = state.get('context') or {}
    if not isinstance(project, str) or not project.strip() or not isinstance(context, dict) or context.get('project_name') != project:
        result['notes'].append('工程名称不匹配，未计算成绩。')
        return result
    if state.get('mode') != 'live':
        result['notes'].append('仅评价线上识别历史；模拟、回放或未标明模式的数据不计成绩。')
        return result
    allowed_ids = {s['id'] for s in get_stages('reservoir')}
    verified = []
    keys = set()
    for label in labels['records']:
        if not isinstance(label, dict):
            result['excluded_labels'] += 1
            continue
        dt = label.get('date'); sid = label.get('stage_id'); value = label.get('percent')
        fingerprint = label.get('image_sha256')
        valid = (label.get('verified') is True and label.get('metric') == 'visual_completion_pct'
                 and _date_valid(dt) and isinstance(sid, str) and sid in allowed_ids
                 and _number(value) and 0 <= value <= 100
                 and all(isinstance(label.get(k), str) and label[k].strip() for k in ('source', 'scope_basis'))
                 and (fingerprint is None or (isinstance(fingerprint, str) and re.fullmatch(r'[0-9a-f]{64}', fingerprint))))
        if not valid:
            result['excluded_labels'] += 1
            continue
        if (dt, sid) in keys:
            raise ValueError(f'重复真值标签：{dt} / {sid}')
        keys.add((dt, sid)); verified.append(label)
    observations = {}
    for h in state['history']:
        if not isinstance(h, dict) or not _date_valid(h.get('date')):
            raise ValueError('历史观察缺少有效日期')
        if h['date'] in observations:
            raise ValueError(f"历史日期重复：{h['date']}")
        observations[h['date']] = h
    errors, hits, widths = [], [], []
    for label in verified:
        dt = label['date']; sid = label['stage_id']; h = observations.get(dt)
        row = dict(date=dt, stage_id=sid, truth_pct=label['percent'], source=label['source'],
                   scope_basis=label['scope_basis'], predicted_pct=None, error_pp=None,
                   range_pct=None, reason=None)
        estimate = None
        if not h:
            row['reason'] = '缺少对应日期观察'
        elif h.get('execution_mode') != 'live':
            row['reason'] = '该期不是线上识别'
        elif label.get('image_sha256') and label['image_sha256'] != h.get('sha256'):
            row['reason'] = '照片 SHA-256 与真值不匹配'
        else:
            items = [s for s in h.get('stages', []) if isinstance(s, dict) and s.get('id') == sid]
            if len(items) != 1:
                row['reason'] = '分项缺失或重复'
            elif items[0].get('source') != 'current_image' or items[0].get('observed_date') != dt:
                row['reason'] = '不是本期直接估算'
            else:
                estimate = items[0].get('progress_estimate')
                value = estimate.get('percent') if isinstance(estimate, dict) else None
                bounds = estimate.get('range_pct') if isinstance(estimate, dict) else None
                if not (_number(value) and isinstance(bounds, list) and len(bounds) == 2
                        and all(_number(x) for x in bounds) and 0 <= bounds[0] <= value <= bounds[1] <= 100):
                    estimate = None
                    row['reason'] = '无法估算或估算格式无效'
        if estimate:
            value, bounds = estimate['percent'], estimate['range_pct']
            error = value - label['percent']
            errors.append(error); hits.append(bounds[0] <= label['percent'] <= bounds[1]); widths.append(bounds[1] - bounds[0])
            row.update(predicted_pct=value, error_pp=round(error, 4), range_pct=bounds)
        result['comparisons'].append(row)
    total, count = len(verified), len(errors)
    result.update(eligible_labels=total, predictions=count, abstentions=total-count,
                  prediction_coverage_pct=round(count/total*100, 2) if total else None)
    if count:
        result.update(mae_pp=round(sum(abs(e) for e in errors)/count, 4),
                      bias_pp=round(sum(errors)/count, 4),
                      within_tolerance_pct=round(sum(abs(e) <= tolerance_pp for e in errors)/count*100, 2),
                      interval_coverage_pct=round(sum(hits)/count*100, 2),
                      mean_interval_width_pp=round(sum(widths)/count, 4))
    else:
        result['notes'].append('没有可计分的已核实标签与有效线上预测，不生成准确率。')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--labels', default='datasets/aigawa/labels.json')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--reports', help='旧双图 vlm_raw.json 所在父目录')
    group.add_argument('--history', help='累计监测 history.json；只评价 live 数据')
    p.add_argument('--tolerance-pp', type=float, default=10, help='误差阈值，单位为百分点，默认10')
    a = p.parse_args()
    labels = json.loads(Path(a.labels).read_text(encoding='utf-8'))
    if a.history:
        try:
            state = json.loads(Path(a.history).read_text(encoding='utf-8'))
            result = evaluate_tracking(labels, state, a.tolerance_pp)
        except ValueError as exc:
            p.error(str(exc))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return
    root = Path(a.reports or 'output/aigawa_v3')
    rows=evaluate(labels,[json.loads(f.read_text(encoding='utf-8')) for f in sorted(root.glob('*/vlm_raw.json'))])
    print(json.dumps(rows,ensure_ascii=False,indent=2))
    if not rows: print('尚无可比较的线上报告；不生成虚假准确率。')
if __name__=='__main__':main()
