"""Incremental reservoir monitoring: immutable baseline, one new observation per update."""
import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from datetime import date

from stages import get_stages
from visual_phase import normalize_phases
from vlm_report import encode_image, call_model, parse_json, load_env
from quantity_progress import calculate_quantities

ROOT = Path(__file__).resolve().parents[1]
DATES = ('2019-06', '2020-04', '2021-01', '2022-02')
VERSION = 1


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic_json(path, obj):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as f:
            temporary = Path(f.name)
            json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def date_key(s):
    if not re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?', s):
        raise ValueError('日期须为 YYYY-MM 或 YYYY-MM-DD')
    return date.fromisoformat(s + '-01' if len(s) == 7 else s)


def clean_context(obj):
    return {k: v for k,v in obj.items() if k in ('project_name','dam_type','scope_note') and isinstance(v,str)}


PROMPT_VERSION = 'v7-cumulative-evidence'
BREAKDOWN_VERSIONS = {'v6-evidence-first', PROMPT_VERSION}


def history_context(history):
    """All prior dates and estimates, explicitly separated from current evidence."""
    def summary(h):
        a = h.get('overall') or {}
        return {'date': h['date'], 'estimated_project_pct': a.get('project_progress_pct'),
                'range_pct': a.get('total_possible_range_pct'),
                'method': a.get('project_progress_method'),
                'current_coverage_pct': a.get('current_coverage_pct'),
                'prompt_version': h.get('prompt_version', 'legacy'),
                'supplied_quantity_pct': (h.get('quantity_progress') or {}).get('progress_pct')}
    return {'baseline': summary(history[0]) if history else None,
            'previous': summary(history[-1]) if history else None,
            'history': [{**summary(h),
                         'stages': [{k:r[k] for k in ('id','status','evidence','progress_estimate','observed_date','source') if k in r} for r in h['stages']],
                         'inferred_stages': (h.get('overall') or {}).get('inferred_stages', []),
                         'extrapolated_stages': (h.get('overall') or {}).get('extrapolated_stages', []),
                         'changes': h.get('changes', [])} for h in history]}


def image_roles(history, current_date, diff=False):
    roles = []
    if history:
        roles.append({'role': 'baseline_and_previous' if len(history)==1 else 'baseline', 'date': history[0]['date']})
        if len(history)>1:
            roles.append({'role': 'previous', 'date': history[-1]['date']})
    roles.append({'role': 'current' if history else 'current_and_baseline', 'date': current_date})
    if diff:
        roles.append({'role': 'ssim_previous_to_current', 'date': current_date, 'reference_date': history[-1]['date'] if history else None})
    return [dict(image_number=i, **r) for i,r in enumerate(roles,1)]


def build_update_prompt(context, history, current_date, diff=False):
    prev = history[-1] if history else None
    prior = history_context(history)
    stages = '\n'.join(f"{s['id']} | {s['name']} | 权重 {s['weight']}% | {s['hint']}" for s in get_stages('reservoir'))
    return f'''你是水利工程施工计量与影像监测专家。任务是估算当前水库全部工程及各分项的累计施工完成百分比，不是状态评分、置信度或验收结论。只输出符合下述结构的JSON。
【工程背景】{json.dumps(context,ensure_ascii=False)}。当前观察日期：{current_date}。
【固定计量口径】以下权重是工程分项在总工程中的占比（示例权重，非合同清单），不是施工完成百分比。每个部位只能计入一个分项，不得重复计量；各期保持同一分母及同一工程范围。
{stages}
【图像输入】{'第一张照片建立基准；基准进度不等于0%，须独立估算。' if not prev else '第一张为永久基准；若基准与上一期不同，另有上一期原图；最后一张现场原图为本期新增照片。先独立分析本期图，再与上一期及基准比较。历史结果只供核查，不是答案；不得为保持增长而修改当前判断。'}
{'另有上一期坐标系的SSIM差分图；只用于辅助定位，必须回到原图核实，不得把热力图面积作为完成率或套用到未对齐的本期图。' if diff else '本期没有可靠差分图，只依据原图及可核查历史证据。'}
【图片编号与角色】{json.dumps(image_roles(history,current_date,diff),ensure_ascii=False)}。图像标签紧邻对应图像；第一期为同一张当前图与基准图，第二期基准和上一期合并，不重复上传。历史中其他日期可能只有文字记录，没有对应图片。
【累计更新规则】先独立估算本期分项，再分别与基准和上一期核对。历史总进度、分项百分比、推断和外推均明确标为旧估算，不是本期答案、不得当作实测量或本期证据。实际录入工程量只属于其记录日期。累计进度的分母始终是整个计划工程，而非基准至今新增工程；同一已完成部位只计一次，不把前期总值加上本期累计值。历史证据只支持原日期的状态；本期遮挡时可引用原始证据日期并说明推断假设，不得把连续沿用的推断说成新的独立观察。若估计下降或与历史冲突，说明是观察变化、范围修正还是无法判定；不人为强制增长。总进度及相对基准/上一期的差值由程序计算，模型不输出独立总百分比。第一期没有历史，不推断本期新增量。
【分析顺序】
1. 先区分实际工程部位：堆石坝主体、混凝土溢洪道及泄槽、取放水建筑物、岸坡、道路和临时设施。已知坝型用于区分结构，不是进度证据。不能把泄槽当成混凝土坝体。指出位置、形状、材料、可见边界以及遮挡情况。机位或视差无法对应时，不作精确变化量比较。
2. 对每一分项明确整个计划范围（分母）、已完成的计划工作范围（分子，包含明确属于本分项的临时工程）、尚未完成范围及估算方法。正在作业、机械增加、临建增加、土堆、水位、光照和植被变化不等于已完成计划工程量增加。土石坝应区分高度、面积和体积；不能用坝面可见面积或填筑高度比例冒充体积完成率。溢洪道区分开挖、结构成型、剩余结构及安装；仅完成局部不等于整条完成。没有可辨认计划边界或可靠参照时，不编造分母。
3. 对有本期直接证据且足以估算整个分项范围的工程，给出 progress_estimate（percent、range_pct、scope_basis、completed_basis），并说明估算所依据的可见范围和剩余部分。不使用固定阶段对应的百分比；不要为了凑数而取整、固定增量或给出虚假精度。0或100仅在完整范围与对应状态有证据时使用。外观完成不代表隐蔽工程、防渗、压实、验收或安全完成。
4. 对本期不可见或范围证据不足的工程，progress_estimate 必须为 null，status 允许为 unclear 或符合可见状态的其他值。若仅能沿用历史观察，设置 carry_previous=true 且 status=unclear，并注明遮挡原因。只有存在独立的历史证据或明确工序依赖时，才可在 inferred_stages 中给该分项一个推断百分比和宽范围，列出具体证据、推断假设及限制。工序先后只能支持合理范围，不能自动证明隐蔽工程全部完成。无依据则不列入 inferred_stages。不得给已直接估算分项重复填推断值。
5. 按固定权重由程序计算总工程累计进度：各分项完成百分比乘权重后求和。不要另外输出凭整体印象给出的总百分比；不要照抄上期值。没有证据的分项保留未知，程序如需外推将单独标明假设。历史模型结果可能有误，允许有依据地纠正；变化描述须区分实际施工变化与估算修正。
【历史观察：基准总进度、上一期总进度及全部历史分项（仅供核查，非真值）】{json.dumps(prior,ensure_ascii=False)}
【输出规范】stages 覆盖全部分项id，每项只出现一次。status 只能是 done、in_progress、not_started、unclear；隐蔽项目不能因不可见写 not_started。confidence 是对判断的信心（0到1），不是进度。progress_estimate 为 null 或对象，percent 必须在 range_pct 内。inferred_stages 仅包含有依据的未直接估算分项；没有则为空数组。changes 只写图中可核实变化，注明参照时点和部位；首期或无法比较时为空。risks 列出遮挡、尺度/机位差异、分母不确定、未见工程等限制。summary 简洁概括本期事实，不编造总进度。
JSON字段模板（尖括号表示实际值占位，不得照抄；以下没有示例进度数字）：
{{"stages":[{{"id":"<分项id>","status":"<状态>","evidence":"<可见部位、已完成及未完成范围>","confidence":<数值>,"progress_estimate":{{"percent":<估算值>,"range_pct":[<下限>,<上限>],"scope_basis":"<完整计划范围依据>","completed_basis":"<已完成及剩余范围、比例推导>"}},"carry_previous":false}}],"inferred_stages":[{{"id":"<未直接估算分项id>","percent":<推断值>,"range_pct":[<下限>,<上限>],"basis":"<历史证据或工序依赖>","assumption":"<假设与局限>"}}],"changes":[{{"stage_id":"<分项id>","where":"<部位>","what":"<相对上一期或基准的变化>"}}],"risks":[],"summary":"<本期概述>"}}。没有依据的 progress_estimate 必须直接写 null；输出合法 JSON，不要包含占位符或 Markdown。'''


def current_rows(raw, previous, current_date):
    if not isinstance(raw,dict) or not isinstance(raw.get('stages'),list):
        raise ValueError('模型未返回有效 stages 数组')
    normalized = normalize_phases(raw['stages'],'reservoir')
    old = {r['id']:r for r in previous['stages']} if previous else {}
    groups = {}
    for r in raw['stages']:
        if isinstance(r,dict) and isinstance(r.get('id'),str): groups.setdefault(r['id'],[]).append(r)
    result = []
    for cfg, r in zip(get_stages('reservoir'), normalized):
        items = groups.get(r['id'],[])
        source = items[0] if len(items)==1 else {}
        est = r['progress_estimate']
        row = dict(id=r['id'],name=cfg['name'],weight=cfg['weight'],status=r['status'],evidence=r['evidence'],confidence=r['confidence'],progress_estimate=est, observed_date=current_date if est else None,source='current_image' if est else 'unknown')
        prior = old.get(r['id'],{})
        if (est is None and r['status']=='unclear' and source.get('carry_previous') is True and prior.get('progress_estimate') is not None):
            row.update(progress_estimate=copy.deepcopy(prior['progress_estimate']),observed_date=prior['observed_date'],source='historical_only')
        result.append(row)
    return result


def aggregate(rows):
    tw=sum(r['weight'] for r in rows)
    current=[r for r in rows if r['source']=='current_image' and r['progress_estimate'] is not None]
    historical=[r for r in rows if r['source']=='historical_only' and r['progress_estimate'] is not None]
    cw=sum(r['weight'] for r in current); hw=sum(r['weight'] for r in historical)
    p=sum(r['weight']*r['progress_estimate']['percent'] for r in current)/tw
    lo=sum(r['weight']*r['progress_estimate']['range_pct'][0] for r in current)/tw
    hi=(sum(r['weight']*r['progress_estimate']['range_pct'][1] for r in current)+(tw-cw)*100)/tw
    # Unknown or stale items have full uncertainty; no automatic assumption of zero, midpoint or monotonicity.
    return dict(total_estimate_pct=round(p,2) if cw==tw else None,
                total_possible_range_pct=[round(lo,2),round(hi,2)],
                total_reference_pct=round((lo+hi)/2,2) if 0<cw<tw else None,
                current_coverage_pct=round(cw/tw*100,2),historical_coverage_pct=round(hw/tw*100,2),
                assessed_only_pct=round(p*tw/cw,2) if cw else None)



# A display estimate is separate from the strict all-stage estimate. This
# threshold is a configurable engineering heuristic, not a calibrated accuracy metric.
MIN_ESTIMATE_COVERAGE = 70.0


def estimate_overall(rows, raw=None):
    a = aggregate(rows)
    coverage = a['current_coverage_pct']
    full = a['total_estimate_pct']
    candidate = raw.get('overall_estimate') if isinstance(raw, dict) else None
    a.update(project_progress_pct=None, project_progress_method='insufficient_evidence',
             project_progress_basis='本期可估算工程权重不足，不能给出可靠单值。',
             assumed_weight_pct=round(100-coverage,2))
    if full is not None:
        a.update(project_progress_pct=full, project_progress_method='all_stage_weighted',
                 project_progress_basis='全部分项均有本期估算，按固定工程权重汇总。')
    elif coverage >= MIN_ESTIMATE_COVERAGE:
        lo, hi = a['total_possible_range_pct']
        v = candidate.get('percent') if isinstance(candidate,dict) else None
        basis = candidate.get('basis') if isinstance(candidate,dict) else None
        assumptions = candidate.get('unknown_assumptions') if isinstance(candidate,dict) else None
        if (isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
            and lo<=v<=hi and isinstance(basis,str) and basis.strip()
            and isinstance(assumptions,str) and assumptions.strip()):
            a.update(project_progress_pct=round(v,2),project_progress_method='model_overall',
                     project_progress_basis='模型整体估算：'+basis.strip()+'；不可见分项假设：'+assumptions.strip())
        else:
            a.update(project_progress_pct=a['assessed_only_pct'],project_progress_method='coverage_extrapolation',
                     project_progress_basis='按本期有依据的分项加权完成率外推整个工程；假设其余工程平均完成比例相同。该假设未验证，非实际工程量。')
    return a


def estimate_breakdown(rows, inferred=None):
    """V6: calculate from item percentages; retain broad unknown bounds and explicit assumptions."""
    a = aggregate(rows)
    coverage = a['current_coverage_pct']
    full = a['total_estimate_pct']
    a.update(project_progress_pct=None, project_progress_method='insufficient_evidence',
             project_progress_basis='本期可估算工程权重不足，不能给出可靠单值。',
             assumed_weight_pct=round(100-coverage,2), inferred_stages=[], extrapolated_stages=[])
    if full is not None:
        a.update(project_progress_pct=full, project_progress_method='all_stage_weighted',
                 project_progress_basis='全部分项均有本期估算，按固定工程权重汇总。')
        return a
    # Keep V5's minimum coverage requirement; inferred values never count as observed coverage.
    if coverage < MIN_ESTIMATE_COVERAGE:
        return a
    missing = {r['id']:r for r in rows if r['source']!='current_image' or r['progress_estimate'] is None}
    groups = {}
    for item in inferred if isinstance(inferred,list) else []:
        if isinstance(item,dict) and isinstance(item.get('id'),str):
            groups.setdefault(item['id'],[]).append(item)
    def num(v):
        return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
    accepted = []
    for sid, r in missing.items():
        items = groups.get(sid,[])
        if len(items)!=1: continue
        x=items[0]; v=x.get('percent'); bounds=x.get('range_pct'); basis=x.get('basis'); assumption=x.get('assumption')
        if not (num(v) and isinstance(bounds,list) and len(bounds)==2 and all(num(z) for z in bounds)
                and 0<=bounds[0]<=v<=bounds[1]<=100 and bounds[0]<bounds[1]
                and isinstance(basis,str) and basis.strip() and isinstance(assumption,str) and assumption.strip()): continue
        accepted.append(dict(id=sid,name=r['name'],weight=r['weight'],percent=v,range_pct=bounds,basis=basis.strip(),assumption=assumption.strip()))
    known = [r for r in rows if r['id'] not in missing]
    tw = sum(r['weight'] for r in rows)
    total = sum(r['weight']*r['progress_estimate']['percent'] for r in known)
    total += sum(r['weight']*r['percent'] for r in accepted)
    inferred_ids = {r['id'] for r in accepted}
    remainder = [r for sid,r in missing.items() if sid not in inferred_ids]
    # Explicit fallback assumption, not claimed to be a visual observation or model inference.
    fallback = a['assessed_only_pct']
    total += sum(r['weight']*fallback for r in remainder)
    desc = ['按固定工程权重逐项汇总本期可见估算及有依据的推断；不采用模型独立给出的总数。']
    desc.extend(f"{r['name']}推断{r['percent']:g}%：{r['basis']}；假设：{r['assumption']}" for r in accepted)
    if remainder:
        desc.append('其余分项（'+ '、'.join(r['name'] for r in remainder)+f'）按本期可见分项加权平均{fallback:g}%外推；此为未验证的统一假设，不是实际观察。')
    a.update(project_progress_pct=round(total/tw,2),
             project_progress_method='stage_inference_extrapolation' if accepted and remainder else 'stage_inference_weighted' if accepted else 'coverage_extrapolation',
             project_progress_basis='；'.join(desc),inferred_stages=accepted,
             extrapolated_stages=[dict(id=r['id'],name=r['name'],weight=r['weight'],percent=fallback) for r in remainder])
    return a


def update_estimates(state):
    """Migrate stored V4 observations without a new model request."""
    previous = None
    baseline = None
    previous_method = None
    for index, h in enumerate(state['history']):
        h['overall'] = (estimate_breakdown(h['stages'],h.get('model_inferred_stages')) if h.get('prompt_version') in BREAKDOWN_VERSIONS else estimate_overall(h['stages'], {'overall_estimate':h.get('model_overall_estimate')}))
        a = h['overall']; v=a['project_progress_pct']
        a['previous_project_progress_pct'] = previous
        a['project_progress_delta_pp'] = round(v-previous,2) if v is not None and previous is not None else None
        if index == 0: baseline = v
        a['baseline_project_progress_pct'] = baseline
        a['baseline_progress_delta_pp'] = round(v-baseline,2) if v is not None and baseline is not None else None
        a['previous_method_changed'] = previous_method is not None and previous_method != a['project_progress_method']
        previous_method = a['project_progress_method']
        previous = v


def method_label(a):
    return {'all_stage_weighted':'全分项加权', 'model_overall':'模型整体估算（含推断）',
            'coverage_extrapolation':'可见分项加权外推（含假设）',
            'stage_inference_weighted':'分项加权（含逐项推断）', 'stage_inference_extrapolation':'分项加权（含逐项推断及外推）',
            'insufficient_evidence':'证据不足'}.get(a.get('project_progress_method'),'未知')


def print_progress(h):
    a=h['overall']; q=h.get('quantity_progress'); delta=a['project_progress_delta_pp']
    print(f"[总工程施工进度（估算）] {fmt(a['project_progress_pct'])}",flush=True)
    print(f"[上期进度] {fmt(a['previous_project_progress_pct'])}；[本期变化] {f'{delta:+.1f} 个百分点' if delta is not None else '无可比上期'}",flush=True)
    base_delta = a.get('baseline_progress_delta_pp')
    print(f"[基准进度] {fmt(a.get('baseline_project_progress_pct'))}；[累计估算变化] {f'{base_delta:+.1f} 个百分点' if base_delta is not None else '未知'}",flush=True)
    if a.get('previous_method_changed'): print('[提示] 前后期估算方法不同，差值仅为估算变化',flush=True)
    print(f"[估算方式] {method_label(a)}；[本期覆盖] {fmt(a['current_coverage_pct'])}；[未直接估算权重] {fmt(a['assumed_weight_pct'])}",flush=True)
    print(f"[提示词版本] {h.get('prompt_version','V5 或更早')}",flush=True)
    print(f"[可能范围] {band(a['total_possible_range_pct'])}；[实际工程量] {fmt(q['progress_pct']) if q else '未提供'}",flush=True)


def fmt(v): return '未知' if v is None else f'{v:.1f}%'


def band(v): return f'{v[0]:.1f}%–{v[1]:.1f}%'


def report(h, history):
    a=h['overall']; q=h.get('quantity_progress'); prev=history[-2] if len(history)>1 else None
    lines=['# 水库累计施工进度报告'+('（模拟数据，非实际识别）' if h['execution_mode']=='offline_test' else ''),f"基准：{history[0]['date']}；最新：{h['date']}；共 {len(history)} 期；模式：{h['execution_mode']}", '',f"- 总工程施工进度（估算）：{fmt(a['project_progress_pct'])}",f"- 提示词版本：{h.get('prompt_version','V5 或更早')}",f"- 估算方式：{method_label(a)}；{a['project_progress_basis']}",f"- 未直接估算的权重：{fmt(a['assumed_weight_pct'])}",f"- 上期进度：{fmt(a['previous_project_progress_pct'])}；本期变化（百分点）：{a['project_progress_delta_pp'] if a['project_progress_delta_pp'] is not None else '—'}",f"- 总工程可能进度区间：{band(a['total_possible_range_pct'])}",f"- 实际工程量总进度：{fmt(q['progress_pct']) if q else '未提供完整工程量'}",f"- 本期可估算权重：{fmt(a['current_coverage_pct'])}；仅有历史记录权重：{fmt(a['historical_coverage_pct'])}",f"- 已估算分项内部加权完成率（非总工程）：{fmt(a['assessed_only_pct'])}", '','总工程权重为示例值。未知或仅有历史记录的分项按0–100%不确定区间计入总范围；单值估算方法可能随证据变化，跨期差值仅为估算变化，不是实际工程量增量。影像估算不等同实测工程量。','', '| 分项 | 权重 | 最新百分比 | 证据日期 | 来源 | 较上期变化 |','|---|---:|---:|---|---|---:|']
    lines.insert(4, f"- 基准进度：{fmt(a.get('baseline_project_progress_pct'))}；较基准估算变化（百分点）：{a.get('baseline_progress_delta_pp')}")
    if a.get('previous_method_changed'): lines.insert(5, '- 注意：与上期估算方法不同，差值不等同实际新增工程量。')
    old={r['id']:r for r in prev['stages']} if prev else {}
    for r in h['stages']:
        e=r['progress_estimate']; b=old.get(r['id'],{}); pe=b.get('progress_estimate')
        delta=f"{e['percent']-pe['percent']:+.1f} pp" if e and pe and r['source']==b.get('source')=='current_image' else '—'
        lines.append(f"| {r['name']} | {r['weight']}% | {fmt(e['percent']) if e else '未知'} | {r['observed_date'] or '—'} | {r['source']} | {delta} |")
    for label,key in [('推断分项（非本期直接观察）','inferred_stages'),('外推分项（统一假设）','extrapolated_stages')]:
        if a.get(key):
            lines += ['', '## '+label]
            for item in a[key]:
                lines.append(f"- {item['name']}：{fmt(item['percent'])}；权重 {item['weight']}%" + (f"；依据：{item['basis']}；假设：{item['assumption']}" if key=='inferred_stages' else '；假设与直接可估算分项平均完成比例相同。'))
    lines += ['', '## 可见证据', *[f"- {r['name']}：{r['evidence']}"+(f"；范围依据：{r['progress_estimate']['scope_basis']}；完成依据：{r['progress_estimate']['completed_basis']}" if r['progress_estimate'] else '') for r in h['stages']], '', '## 本期变化', *[f"- {c.get('where','')}：{c.get('what','')}" for c in h['changes']], '', '## 风险', *['- '+r for r in h['risks']], '', h['summary']]
    return '\n'.join(lines)+'\n'


def render_chart(out, state):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import matplotlib.image as mpimg
    fonts={f.name for f in fm.fontManager.ttflist}
    family=next((f for f in ['PingFang SC','Heiti SC','Noto Sans CJK SC','Arial Unicode MS'] if f in fonts),None)
    if not family:
        # Font cache may predate system CJK fonts. Resolve an installed font without shipping fonts.
        try:
            import subprocess
            fpath=subprocess.check_output(['fc-match','-f','%{file}','Noto Sans CJK SC'],text=True).strip()
            if fpath and Path(fpath).exists() and 'cjk' in fpath.lower():
                fm.fontManager.addfont(fpath); family=fm.FontProperties(fname=fpath).get_name()
        except (OSError,subprocess.SubprocessError,RuntimeError): pass
    if family: plt.rcParams['font.family']=family
    plt.rcParams['axes.unicode_minus']=False
    h=state['history'][-1]; a=h['overall']; hist=state['history']; q=h.get('quantity_progress')
    fig=plt.figure(figsize=(14,10),facecolor='#f4f7fa',layout='constrained')
    grid=fig.add_gridspec(3,2,height_ratios=[.22,1,.72]); header=fig.add_subplot(grid[0,:]); header.axis('off')
    if family:
        title=f"{'模拟数据 · ' if h['execution_mode']=='offline_test' else ''}最新施工进度 | {h['date']}  ·  总工程估算 {fmt(a['project_progress_pct'])}  ·  区间 {band(a['total_possible_range_pct'])}"
        subtitle=f"{method_label(a)} | 基准 {hist[0]['date']} | 本期可估算权重 {fmt(a['current_coverage_pct'])} | 实际工程量 {fmt(q['progress_pct']) if q else '未提供'} | {h['execution_mode']}"
    else:
        title=f"{'SIMULATED DATA | ' if h['execution_mode']=='offline_test' else ''}Latest progress | {h['date']} | Total estimate {fmt(a['project_progress_pct'])} | Range {band(a['total_possible_range_pct'])}"
        subtitle=f"Method: {a['project_progress_method']} | Baseline {hist[0]['date']} | Current coverage {a['current_coverage_pct']}% | Quantity {q['progress_pct'] if q else 'N/A'} | {h['execution_mode']}"
    header.text(0,.75,title,fontsize=17,weight='bold',color='#18364a'); header.text(0,.15,subtitle,fontsize=11,color='#526777')
    ax=fig.add_subplot(grid[1,0]); ax.imshow(mpimg.imread(out/h['image'])); ax.axis('off'); ax.set_title('最新现场照片（原图）' if family else 'Latest original observation')
    ax=fig.add_subplot(grid[1,1]); rows=h['stages']; ys=list(range(len(rows))); ax.set_yticks(ys, [r['name'] if family else r['id'] for r in rows]); ax.invert_yaxis(); ax.set_xlim(0,112); ax.set_xticks([0,25,50,75,100]); ax.set_xlabel('%'); ax.grid(axis='x',alpha=.18)
    for i,r in enumerate(rows):
        e=r['progress_estimate']; historical=r['source']=='historical_only'
        if e:
            v=e['percent']; lo,hi=e['range_pct']; ax.barh(i,v,color='#94a3b8' if historical else '#168b8a',height=.55); ax.errorbar(v,i,xerr=[[v-lo],[hi-v]],fmt='none',ecolor='#234353',capsize=3); ax.text(min(hi+3,103),i,f'{v:g}%'+('*' if historical else ''),va='center',fontsize=9)
        else: ax.text(2,i,'未知' if family else 'N/A',va='center',color='#7b8794')
    ax.set_title('分项完成百分比（*历史观察）' if family else 'Stage completion (*historical observation)')
    ax=fig.add_subplot(grid[2,:]); xs=list(range(len(hist))); low=[x['overall']['total_possible_range_pct'][0] for x in hist]; high=[x['overall']['total_possible_range_pct'][1] for x in hist]; ax.fill_between(xs,low,high,color='#168b8a',alpha=.18,label='总工程可能区间' if family else 'Possible total range'); ax.plot(xs,[x['overall']['project_progress_pct'] if x['overall']['project_progress_pct'] is not None else float('nan') for x in hist],'-o',color='#168b8a',label='总工程估算（含推断）' if family else 'Total estimate (incl. inference)'); ax.plot(xs,[x['quantity_progress']['progress_pct'] if x.get('quantity_progress') else float('nan') for x in hist],'-s',color='#cf7725',label='实际工程量（录入）' if family else 'Supplied quantity progress'); ax.set_xticks(xs,[x['date'] for x in hist],rotation=30 if len(xs)>8 else 0); ax.set_ylim(0,100); ax.set_ylabel('%'); ax.grid(alpha=.2); ax.legend(loc='upper left'); ax.set_title('累计施工进度趋势（不强制单调）' if family else 'Progress history (not forced monotonic)')
    path=out/'latest_progress.png'; tmp=out/'latest_progress.tmp.png'; fig.savefig(tmp,dpi=135); plt.close(fig); os.replace(tmp,path)


def refresh(out,state):
    update_estimates(state)
    h=state['history'][-1]
    atomic_json(out/'latest_progress.json',h)
    (out/'latest_report.md').write_text(report(h,state['history']),encoding='utf-8')
    render_chart(out,state)


def update(out,state,image,dt,args,context):
    date_key(dt); history=state['history']; image=Path(image).resolve(); fingerprint=digest(image)
    existing=next((h for h in history if h['date']==dt),None)
    if existing:
        if existing['sha256']!=fingerprint: raise ValueError(f'{dt} 已有不同照片；请使用新监测目录或明确重建。')
        print(f'[跳过] {dt} 已完成'); return False
    if history and date_key(dt)<=date_key(history[-1]['date']): raise ValueError('新照片日期必须晚于最新一期')
    if any(h['sha256']==fingerprint for h in history): raise ValueError('重复照片，不能作为新一期')
    prev=history[-1] if history else None
    # Store independent original bytes (no AI reconstruction). Decode first.
    new_encoded=encode_image(str(image)); folder=out/'observations'/dt; folder.mkdir(parents=True,exist_ok=True); imgpath=folder/('original'+image.suffix.lower()); shutil.copyfile(image,imgpath)
    cvinfo={'eligible_diff':False,'reason':'首期建立基准' if not prev else '跳过CV'}; diff=None
    if prev and not args.skip_cv:
        from cpm_core import compare_photos
        from registration import RegistrationError
        cvdir=Path(tempfile.mkdtemp(prefix='cv_',dir=folder))
        try:
            res=compare_photos(str(out/prev['image']),str(imgpath),str(cvdir),registration='auto'); diff=res['outputs']['ssim_heatmap']; cvinfo={'eligible_diff':True,'reason':'通过几何检查，差分仅辅助','registration':res['registration']}
        except (RegistrationError,RuntimeError) as e:
            cvinfo={'eligible_diff':False,'reason':str(e)}
    print('[CV]',cvinfo['reason'],flush=True)
    prompt=build_update_prompt(context,history,dt,bool(diff))
    roles=image_roles(history,dt,bool(diff)); content=[{'type':'text','text':prompt}]
    role_names={'baseline_and_previous':'永久基准兼上一期照片','baseline':'永久基准照片','previous':'上一期照片',
                'current':'本期新增现场照片','current_and_baseline':'本期照片兼永久基准','ssim_previous_to_current':'上一期与本期SSIM差分（仅供参考）'}
    records={h['date']:h for h in history}
    manifest=[]
    for r in roles:
        role=r['role']
        if role=='ssim_previous_to_current':
            path=Path(diff); encoded=encode_image(str(path))
        elif role in ('current','current_and_baseline'):
            path=imgpath; encoded=new_encoded
        else:
            rec=records[r['date']]; path=out/rec['image']
            if digest(path)!=rec['sha256']: raise ValueError(f"历史原图已修改：{rec['date']}，请恢复原图")
            encoded=encode_image(str(path))
        label=f"图{r['image_number']}：{role_names[role]} {r['date']}"
        content.extend([{'type':'text','text':label},{'type':'image_url','image_url':{'url':encoded,'detail':'high'}}])
        manifest.append({**r,'label':label,'file':str(path.relative_to(out)),'sha256':digest(path),
                         'encoded_sha256':hashlib.sha256(encoded.encode()).hexdigest()})
    (folder/'prompt.txt').write_text(prompt,encoding='utf-8'); atomic_json(folder/'cv_quality.json',cvinfo)
    atomic_json(folder/'request_manifest.json',{'prompt_version':PROMPT_VERSION,'prompt_file':'prompt.txt',
                 'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(), 'images':manifest,
                 'history_context':history_context(history),'execution_mode':'offline_test' if args.responses else 'live'})
    if args.responses:
        raw=read_json(Path(args.responses)/(dt+'.json')); raw=raw.get('raw_vlm',raw); mode='offline_test'; model='offline_test'
    else:
        from openai import OpenAI
        load_env(); key=os.environ.get('DEEPSEEK_API_KEY','').strip(); model=os.environ.get('DEEPSEEK_MODEL','deepseek-v4-flash')
        if not key: raise ValueError('请保留原项目 .env，DEEPSEEK_API_KEY 未配置')
        client=OpenAI(api_key=key,base_url=os.environ.get('DEEPSEEK_BASE_URL','https://api.deepseek.com/v1'),timeout=120,max_retries=1)
        print(f'[调用] {model}，{sum(c["type"]=="image_url" for c in content)}张图片，历史 {len(history)} 期',flush=True)
        response,note=call_model(client,model,content,think=not args.fast); text=response.choices[0].message.content or ''; (folder/'model_response.txt').write_text(text,encoding='utf-8'); raw=parse_json(text); mode='live'; print('[完成]',note,flush=True)
    rows=current_rows(raw,prev,dt); overall=estimate_breakdown(rows,raw.get('inferred_stages'))
    quantity=None
    if args.quantities_dir:
        qp=Path(args.quantities_dir)/(dt+'.json')
        if qp.exists(): quantity=calculate_quantities(read_json(qp),'reservoir')
    h=dict(date=dt,image=str(imgpath.relative_to(out)),sha256=fingerprint,execution_mode=mode,model=model,stages=rows,overall=overall,quantity_progress=quantity,prompt_version=PROMPT_VERSION,model_inferred_stages=raw.get('inferred_stages'),cv=cvinfo,changes=[c for c in raw.get('changes',[]) if isinstance(c,dict)] if isinstance(raw.get('changes'),list) else [],risks=[r for r in raw.get('risks',[]) if isinstance(r,str)] if isinstance(raw.get('risks'),list) else [],summary=raw.get('summary','') if isinstance(raw.get('summary'),str) else '')
    atomic_json(folder/'raw_model.json',raw)
    history.append(h); update_estimates(state)
    atomic_json(folder/'progress.json',h); atomic_json(out/'history.json',state); refresh(out,state)
    print_progress(h)
    print('[最新进度图]',out/'latest_progress.png',flush=True)
    return True


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--refresh-only',action='store_true',help='仅从已保存历史重新生成总工程进度和图表，不调用API'); p.add_argument('--all',action='store_true',help='依次导入安威川四期，已完成期自动跳过'); p.add_argument('--new-image'); p.add_argument('--date'); p.add_argument('--out',default=str(ROOT/'output/aigawa_tracking')); p.add_argument('--context',default=str(ROOT/'config/aigawa_context.json')); p.add_argument('--skip-cv',action='store_true'); p.add_argument('--fast',action='store_true'); p.add_argument('--enhanced',action='store_true'); p.add_argument('--responses',help='仅离线测试：日期.json目录；独立输出路径'); p.add_argument('--quantities-dir',help='按日期提供实际工程量 日期.json'); args=p.parse_args(argv)
    if sum([args.all,bool(args.new_image),args.refresh_only])!=1 or (args.new_image and not args.date) or (not args.new_image and args.date): p.error('使用 --all、--refresh-only 或 --new-image 图片 --date 日期')
    if args.responses and Path(args.out).resolve()==(ROOT/'output/aigawa_tracking').resolve(): p.error('离线测试必须使用独立 --out')
    context=clean_context(read_json(args.context)); out=Path(args.out).resolve(); out.mkdir(parents=True,exist_ok=True); mode='offline_test' if args.responses else 'live'
    # Lock per project to prevent concurrent updates from overwriting history.
    lock=out/'.update.lock'
    try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError: p.error('监测目录正在更新；若确认上次进程已退出，可删除 .update.lock 后重试')
    try:
        os.close(fd); path=out/'history.json'; state=read_json(path) if path.exists() else dict(version=VERSION,context=context,mode=mode,history=[])
        # Refresh consumes stored observations only; it does not select a model mode.
        if args.refresh_only:
            mode = state['mode']
        if state['version']!=VERSION or state['context']!=context or state['mode']!=mode: raise ValueError('监测目录版本、工程背景或运行模式不一致；请使用新目录')
        if args.refresh_only:
            if not state['history']: raise ValueError('无历史记录可刷新')
            backup=out/'history.v4.backup.json'
            if not backup.exists(): shutil.copyfile(path,backup)
            refresh(out,state); atomic_json(path,state)
            print('[离线刷新] 未调用 API')
            print_progress(state['history'][-1]); print('[最新进度图]',out/'latest_progress.png'); return
        update_estimates(state)
        folder=ROOT/'datasets/aigawa'/('enhanced' if args.enhanced else 'images'); jobs=[(folder/(d+'.png'),d) for d in DATES] if args.all else [(args.new_image,args.date)]
        changed = False
        for img,dt in jobs:
            changed = update(out,state,img,dt,args,context) or changed
        # Each committed update already wrote the current chart/report; avoid rendering twice.
        if state['history'] and not changed:
            refresh(out,state); atomic_json(path,state)
    finally: lock.unlink(missing_ok=True)

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('[错误]',str(e),file=sys.stderr); sys.exit(1)
