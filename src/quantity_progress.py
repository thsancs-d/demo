"""由人工核实的实际工程量计算加权进度，独立于视觉评分。"""
import math
from stages import get_stages


def calculate_quantities(data, project_type='reservoir'):
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        raise ValueError('工程量配置需要 items 数组')
    expected = {s['id'] for s in get_stages(project_type)}
    seen = set()
    detail = []
    for item in data['items']:
        if not isinstance(item, dict):
            raise ValueError('工程量条目须为对象')
        sid = item.get('id')
        if not isinstance(sid, str) or sid not in expected or sid in seen:
            raise ValueError(f'未知或重复工序: {sid}')
        seen.add(sid)
        weight, planned, actual = (item.get(k) for k in ('weight', 'planned', 'actual'))
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (weight, planned, actual)):
            raise ValueError(f'{sid}: 权重和工程量必须为有限数字')
        if weight < 0 or planned <= 0 or actual < 0 or not isinstance(item.get('unit'), str) or not item['unit'].strip():
            raise ValueError(f'{sid}: 权重、工程量或单位无效')
        detail.append({**item, 'completion_pct': round(min(actual / planned, 1)*100, 2), 'over_plan': actual > planned})
    if seen != expected or not math.isclose(sum(i['weight'] for i in detail), 100, abs_tol=1e-6):
        raise ValueError('须包含全部工序且权重之和为100；不适用项可设权重0')
    return {'progress_pct': round(sum(i['weight'] * min(i['actual']/i['planned'], 1) for i in detail), 2), 'items': detail, 'metric_type': 'user_supplied_quantity_progress'}
