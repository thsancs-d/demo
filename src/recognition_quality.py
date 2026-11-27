"""Auditable evidence checks; these are heuristics, not calibrated accuracy scores."""
import copy
import json
import math

from stages import get_stages
from visual_phase import normalize_phases

ACCURACY_PROMPT_VERSION = 'v8-grounded-evidence'
TEMPORAL_PROMPT_VERSION = 'v9-fixed-camera-temporal'
MIN_CONFIDENCE = 0.7
TEMPORAL_DIRECTIONS = {'advanced', 'unchanged', 'removed', 'unclear'}
TEMPORAL_TYPES = {'new_work', 'expanded', 'completed_surface', 'temporary_change', 'unknown'}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _box_iou(first, second):
    left = max(first[0], second[0]); top = max(first[1], second[1])
    right = min(first[2], second[2]); bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_first = (first[2] - first[0]) * (first[3] - first[1])
    area_second = (second[2] - second[0]) * (second[3] - second[1])
    union = area_first + area_second - intersection
    return intersection / union if union else 0.0


def evidence_history(history):
    """Exclude prior numeric estimates from the new model request, not from storage."""
    records = []
    for h in history:
        records.append({'date': h['date'], 'stages': [
            {k: row[k] for k in ('id', 'status', 'evidence', 'observed_date', 'source') if k in row}
            for row in h['stages']]})
    return {'baseline_date': history[0]['date'] if history else None,
            'previous_date': history[-1]['date'] if history else None, 'history': records}


def build_accuracy_prompt(context, history, current_date, roles):
    stages = '\n'.join(f"{s['id']} | {s['name']} | {s['hint']}" for s in get_stages('reservoir'))
    current = next(r['image_number'] for r in roles if r['role'] in ('current', 'current_and_baseline'))
    return f'''你是水库施工影像评估人员。先记录可见事实，再估算有证据的分项完成比例；允许无法估算。只输出 JSON。
【工程背景】{json.dumps(context, ensure_ascii=False)}
【本期日期】{current_date}。本期现场原图为图{current}。
【图片角色】{json.dumps(roles, ensure_ascii=False)}
【分项清单】
{stages}
【观察步骤】
1. 先区分堆石坝主体、混凝土泄槽/溢洪道、取放水结构、岸坡和临时设施。不要把泄槽当坝体。用本期原图中的位置、形状、材料描述部位，记录遮挡、模糊和画外范围。
2. 为每项填写 observation：image_number 必须是本期原图编号 {current}；bbox_xyxy 是本期原图上可见证据的 [左,上,右,下] 归一化坐标，各坐标0到1且框非空、尽量紧贴该分项，不要用整幅图片框代替部位框；visibility 为 clear/partial/not_visible；scope 为 full/partial/unknown，表示整个计划分项边界是否可辨认；basis 为 visible_extent/height_ratio/pixel_change/unknown。看不见时 observation 可为 null。框只定位证据，框面积不是工程量。不同分项必须分别框选，不能复制同一个框。
3. 百分比只估算可解释的完整分项范围。progress_estimate 为 null，或包含 percent、range_pct、scope_basis、completed_basis。两个依据须分别说明完整计划范围参照，以及已完成、未完成范围与比例推导。不能根据日期、工序阶段、设备数量或旧结果凑数。不得将高度、可见坝面面积或差分像素面积冒充填筑体积。没有设计范围参照时 scope=unknown，不编造分母。
4. 只有 visibility=clear、scope=full、basis=visible_extent，并有完整证据和 confidence>={MIN_CONFIDENCE} 时可给直接百分比。confidence 是未标定的判断信心，不是正确概率；不要为越过阈值而抬高它。施工中必须给有宽度的区间，百分比在区间内。局部/遮挡/低分辨率只描述可见事实，百分比为 null。0/100仅在完整范围有对应状态证据时使用；外观完成不代表隐蔽工程、防渗、压实或验收完成。
5. status 为 done/in_progress/not_started/unclear。隐蔽或画外项目不能因看不见而写 not_started；不能推断其全部完成。carry_previous 仅在本期不可见、status=unclear 时可为 true，引用原始观察日期；沿用不是本期观察。模型推断不得代替直接估算，inferred_stages 固定为空数组。
6. 首期独立建立基准，不默认从0开始。历史仅供核对，同一已完成部位只计一次，不把前期总值加到本期累计值。允许有依据的估算回落，不强制增长。程序按固定权重汇总；证据不全时保留区间，不自动按可见项目平均值外推，不输出总工程单值。
7. 差分图仅提示可能变化的位置；其坐标属于上一期，不能充当本期直接证据或套到本期原图。三维视差、天气、水位、植被和车辆变化不是施工增量。只在原图可独立核实且可对应时填写 changes；首期或无法对应时为空。
【历史证据（不是本期真值；旧数值估算已省略）】{json.dumps(evidence_history(history), ensure_ascii=False)}
【返回前自查】逐项核对图号与证据框、是否完整范围、坝体与泄槽是否混淆、百分比与状态/区间是否矛盾。矛盾或证据不足时保留事实，将 progress_estimate 置 null；不要修饰信心数值来强行输出。
【JSON结构】stages 必须覆盖全部分项且id唯一，每项含 id/status/evidence/confidence/observation/progress_estimate/carry_previous。inferred_stages=[]；changes 为包含 stage_id/where/what 的对象数组；risks 为字符串数组；summary 只概括可见事实和不能估算的原因，不编造总进度。无证据字段用 null，不输出 Markdown。'''


def filter_observations(raw, current_image_number):
    if not isinstance(raw, dict) or not isinstance(raw.get('stages'), list):
        raise ValueError('模型未返回有效 stages 数组')
    filtered = copy.deepcopy(raw)
    groups = {}
    for item in filtered['stages']:
        if isinstance(item, dict) and isinstance(item.get('id'), str):
            groups.setdefault(item['id'], []).append(item)
    normalized = {r['id']: r for r in normalize_phases(raw['stages'], 'reservoir')}
    # A model sometimes copies one broad box to several stages. That makes the
    # labels look complete while destroying part localization. Exact duplicate
    # boxes are rejected for all affected estimates. Nearby but distinct boxes
    # remain possible because adjacent dam structures can overlap visually.
    duplicate_box_ids = set()
    box_groups = {}
    for stage_id, items in groups.items():
        if len(items) != 1 or not isinstance(items[0].get('observation'), dict):
            continue
        box = items[0]['observation'].get('bbox_xyxy')
        if isinstance(box, list) and len(box) == 4 and all(_number(x) for x in box):
            box_groups.setdefault(tuple(box), []).append(stage_id)
    for ids in box_groups.values():
        if len(ids) > 1:
            duplicate_box_ids.update(ids)
    reviews = []
    for cfg in get_stages('reservoir'):
        items = groups.get(cfg['id'], [])
        row = normalized[cfg['id']]
        candidate = any(item.get('progress_estimate') is not None for item in items)
        reasons = []
        if len(items) != 1:
            reasons.append('分项缺失或重复')
        item = items[0] if len(items) == 1 else {}
        if cfg['id'] in duplicate_box_ids and item.get('progress_estimate') is not None:
            reasons.append('不同分项重复使用同一证据框')
        estimate = row['progress_estimate']
        if estimate is None:
            reasons.append('缺少有效百分比、状态或范围依据')
        confidence = row['confidence']
        if not _number(confidence) or confidence < MIN_CONFIDENCE:
            reasons.append('置信度不足或无效（筛选阈值未标定）')
        observation = item.get('observation')
        if not isinstance(observation, dict):
            reasons.append('缺少结构化本期证据')
        else:
            if type(observation.get('image_number')) is not int or observation['image_number'] != current_image_number:
                reasons.append('证据图号不是本期原图')
            box = observation.get('bbox_xyxy')
            if not (isinstance(box, list) and len(box) == 4 and all(_number(x) for x in box)
                    and 0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
                reasons.append('证据区域缺失、越界或为空')
            elif (box[2] - box[0]) * (box[3] - box[1]) >= 0.98:
                reasons.append('证据框几乎覆盖整幅图片，无法定位具体部位')
            if observation.get('visibility') != 'clear':
                reasons.append('本期可见证据不清晰或被遮挡')
            if observation.get('scope') != 'full':
                reasons.append('完整计划范围不可辨认')
            if observation.get('basis') != 'visible_extent':
                reasons.append('比例依据不是可解释的完整施工范围')
        if estimate and row['status'] == 'in_progress' and estimate['range_pct'][0] == estimate['range_pct'][1]:
            reasons.append('施工中影像估算不能使用零宽度区间')
        evidence_text = item.get('evidence') if isinstance(item.get('evidence'), str) else row.get('evidence') if isinstance(row.get('evidence'), str) else ''
        if estimate and cfg['id'] == 'dam_body':
            has_body = any(word in evidence_text for word in ('堆石', '填筑', '坝坡')) or ('坝体' in evidence_text and '坝体范围不可辨' not in evidence_text)
            has_spillway = any(word in evidence_text for word in ('溢洪道', '泄槽', '泄洪槽'))
            if has_spillway and not has_body:
                reasons.append('坝体证据疑似实际描述溢洪道或泄槽')
        if estimate and cfg['id'] == 'spillway':
            has_spillway = any(word in evidence_text for word in ('溢洪道', '泄槽', '泄洪槽', '进水渠', '消能'))
            has_body = any(word in evidence_text for word in ('坝体填筑', '堆石坝', '坝坡'))
            if has_body and not has_spillway:
                reasons.append('溢洪道证据疑似实际描述坝体填筑')
        if estimate and isinstance(observation, dict):
            box = observation.get('bbox_xyxy')
            if isinstance(box, list) and len(box) == 4 and all(_number(x) for x in box):
                if (box[2] - box[0]) * (box[3] - box[1]) >= 0.98:
                    reasons.append('证据框几乎覆盖整幅图片，无法定位具体部位')
        if reasons:
            for item in items:
                item['progress_estimate'] = None
                if candidate:
                    item['carry_previous'] = False
        reviews.append({'id': cfg['id'], 'name': cfg['name'], 'accepted': not reasons,
                        'had_estimate': candidate, 'reasons': reasons})
    # Unsupported inference is retained only in raw_model.json, never as current evidence.
    filtered['inferred_stages'] = []
    review = {'policy': ACCURACY_PROMPT_VERSION, 'min_confidence': MIN_CONFIDENCE,
              'threshold_calibrated': False,
              'accepted_estimates': sum(r['accepted'] for r in reviews),
              'rejected_estimates': sum(r['had_estimate'] and not r['accepted'] for r in reviews),
              'stages': reviews}
    return filtered, review


def build_temporal_prompt(context, history, current_date, roles):
    """Ask for same-region changes without turning image differences into quantity."""
    stages = '\n'.join(f"{s['id']} | {s['name']} | {s['hint']}" for s in get_stages('reservoir'))
    current = next(r['image_number'] for r in roles if r['role'] in ('current', 'current_and_baseline'))
    previous = next((r['image_number'] for r in roles
                     if r['role'] in ('previous', 'baseline_and_previous')), None)
    if previous is None:
        comparison = '本期没有上一期照片；temporal_changes 必须为空数组，只记录本期可见事实。'
    else:
        comparison = f'上一期原图为图{previous}，本期原图为图{current}；只比较两图同一画面区域。'
    return f'''你是固定镜头水库施工监测人员。目标是识别同一镜头不同时间的可见变化，不把变化面积换算成工程量。只输出JSON。
【工程背景】{json.dumps(context, ensure_ascii=False)}
【日期】本期 {current_date}。{comparison}
【图片角色】{json.dumps(roles, ensure_ascii=False)}
【分项】
{stages}
【规则】
1. 先确认两图是否是同一工程、同一大致观察方向。固定镜头仍可能有变焦、裁切、天气、季节、水位和三维视差；无法对应时所有 temporal_changes 为空并在 risks 说明。
2. 对每条变化，使用 stage_id、direction（advanced/unchanged/removed/unclear）、change_type（new_work/expanded/completed_surface/temporary_change/unknown）、evidence_image_numbers、bbox_xyxy、where、what、confidence、visibility、basis。evidence_image_numbers 必须同时包含上一期图号和本期图号；bbox_xyxy 是本期原图上的非空归一化框。visibility 只能 clear/partial/not_visible；basis 必须是 same_region_comparison。confidence 是未标定筛选值，不是正确概率。
3. 只有两期原图都能看见同一部位、变化内容具体且 confidence>={MIN_CONFIDENCE} 才记录事件。局部变化可以保留，但标 visibility=partial；看不清、只能由像素差推断、只看到机械/车辆/植被/天气变化时填 temporary_change 或 unknown，不写施工完成，direction 只能写 unchanged 或 unclear，不能写 advanced。隐蔽工程、灌浆、压实、验收和工程量体积不可由固定镜头证明。
4. direction 描述相对上一期的可见状态，不代表总工程进度。不要把框面积、变化像素、事件数量或时间间隔换算成百分比。绝对 progress_estimate 只有完整范围和直接证据都足够时才填写；证据不足写 null。程序不会因 temporal_changes 生成总工程百分比。
5. 分项状态仍为 done/in_progress/not_started/unclear；隐蔽工序不可因看不见写 not_started。第一期没有上一期，temporal_changes 必须为空。
【JSON结构】stages 覆盖全部分项，每项含 id/status/evidence/confidence/observation/progress_estimate/carry_previous。evidence 必须是当前分项可见事实的自然语言字符串，不能填写图号数组。observation 无直接定位框时为 null；有框时才使用含 image_number/bbox_xyxy/visibility/scope/basis 的对象。temporal_changes 为事件数组；changes 可为空或复制同一事件的简要文字；risks 为字符串数组；summary 只写可见事实。不要输出Markdown。
{comparison}
【返回前自查】每个事件的图号、框、方向、类型、置信度和同一区域依据都合法；不同部位不要合并；无法确认就删掉事件。'''


def filter_temporal_changes(raw, previous_image_number, current_image_number):
    """Validate same-region change events; never derive percentages from them."""
    if previous_image_number is None:
        return [], {'policy': TEMPORAL_PROMPT_VERSION, 'accepted_changes': 0,
                    'rejected_changes': 0, 'reasons': ['首期没有上一期图像']}
    if not isinstance(raw, dict) or not isinstance(raw.get('temporal_changes'), list):
        return [], {'policy': TEMPORAL_PROMPT_VERSION, 'accepted_changes': 0,
                    'rejected_changes': 0, 'reasons': ['缺少 temporal_changes 数组']}
    allowed = {s['id'] for s in get_stages('reservoir')}
    accepted, rejected = [], []
    keys = set()
    for event in raw['temporal_changes']:
        reasons = []
        if not isinstance(event, dict):
            rejected.append({'reasons': ['事件不是对象']}); continue
        sid = event.get('stage_id')
        if not isinstance(sid, str) or sid not in allowed:
            reasons.append('stage_id 无效')
        direction = event.get('direction')
        if not isinstance(direction, str) or direction not in TEMPORAL_DIRECTIONS:
            reasons.append('direction 无效')
        change_type = event.get('change_type')
        if not isinstance(change_type, str) or change_type not in TEMPORAL_TYPES:
            reasons.append('change_type 无效')
        if (isinstance(change_type, str) and change_type in {'temporary_change', 'unknown'}
                and direction == 'advanced'):
            reasons.append('临时或未知变化不能标记为 advanced')
        nums = event.get('evidence_image_numbers')
        if not (isinstance(nums, list) and len(nums) == 2 and all(type(x) is int for x in nums)
                and set(nums) == {previous_image_number, current_image_number}):
            reasons.append('证据图号必须同时包含上一期和本期原图')
        box = event.get('bbox_xyxy')
        if not (isinstance(box, list) and len(box) == 4 and all(_number(x) for x in box)
                and 0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
            reasons.append('本期证据框缺失、越界或为空')
        if not isinstance(event.get('where'), str) or not event['where'].strip(): reasons.append('缺少 where')
        if not isinstance(event.get('what'), str) or not event['what'].strip(): reasons.append('缺少 what')
        if not _number(event.get('confidence')) or not MIN_CONFIDENCE <= event['confidence'] <= 1:
            reasons.append('置信度不足或无效')
        if event.get('visibility') not in ('clear', 'partial'):
            reasons.append('缺少可见变化证据')
        if event.get('basis') != 'same_region_comparison': reasons.append('basis 不是同一区域比较')
        if reasons:
            rejected.append({'stage_id': sid if isinstance(sid, str) else None,
                             'reasons': reasons})
            continue
        key = (sid, direction, change_type, event['where'])
        if key in keys:
            rejected.append({'stage_id': sid, 'reasons': ['重复事件']})
            continue
        keys.add(key)
        accepted.append(copy.deepcopy(event))
    return accepted, {'policy': TEMPORAL_PROMPT_VERSION, 'accepted_changes': len(accepted),
                      'rejected_changes': len(rejected), 'reasons': rejected}


def normalize_temporal_response(raw):
    """Recover natural-language stage evidence when a model puts image refs there."""
    if not isinstance(raw, dict) or not isinstance(raw.get('stages'), list):
        return raw
    normalized = copy.deepcopy(raw)
    for stage in normalized['stages']:
        if not isinstance(stage, dict):
            continue
        evidence = stage.get('evidence')
        observation = stage.get('observation')
        if ((not isinstance(evidence, str) or not evidence.strip())
                and isinstance(observation, str) and observation.strip()):
            stage['evidence'] = observation.strip()
    return normalized
