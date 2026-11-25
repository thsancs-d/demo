"""Photo-based completion percentage estimates, not ordinal scores or measured quantities."""
import math
from stages import get_stages, normalize_stages, total_weight

PHASES = {'not_started':'未开工','early':'施工初期','middle':'施工中期','late':'施工中后期','near_complete':'接近完成','visually_complete':'外观完成'}
COMPAT = {'not_started': {'not_started'}, 'in_progress': {'early','middle','late','near_complete'}, 'done': {'visually_complete'}, 'unclear': set()}


def phase_prompt(context=None):
    context = context or {}
    known = '\n'.join(f'{label}：{context[k]}' for k,label in [('project_name','工程名称'),('dam_type','已知坝型'),('scope_note','已知工序范围')] if context.get(k))
    return f'''【水库施工进度百分比专项要求】
{known or '工程坝型未知，不可强猜。'}
已知坝型仅为结构分类背景，不是进度证据。土石坝的混凝土泄槽、消力池、进水口等不可当作混凝土坝体；仅看到混凝土施工、临建或开挖，不代表坝体正在填筑。不得将坝面成型等同于防渗、压实、验收或全水库完工。
目标是估算施工完成百分比，而不是工序状态打分。对每道工序分别估算前期与后期完成百分比（0—100）；百分比是以该分项整个计划范围为分母、以已完成的施工范围为分子的影像近似估算，不是实测工程量，不是变化像素面积，不是置信度，不是阶段固定分数。
例如坝体填筑须依据可辨认的最终坝顶、坝肩范围、已成型坝体、尚未填筑范围等，说明如何估算相对于整个坝体填筑范围的完成比例；不得用填筑高程比例冒充体积比例。溢洪道须比较完整设计线路范围与已施工部分。只有存在可解释的整体范围参考、能合理判断完成部分和未完成部分时才给百分比，否则为 null。只看到局部不得外推整个工序；不能估算全工程不等于不能估算单个分项。禁止把施工中统一设为50%，禁止用固定阶段对应百分比。0和100只在对应状态及完整范围明确时使用。对隐蔽工序无法确认的范围必须为 null。不得使用时间先后强制上升。
每个 stages 元素保留 id/status/evidence/confidence（后期），并新增 before_status、before_evidence。可选 phase、before_phase，取 not_started/early/middle/late/near_complete/visually_complete/unclear，仅用于文字描述，不参与计算。
新增 progress_estimate 和 before_progress_estimate（后期和前期各自独立），格式为 null 或对象：{{"percent": 数字, "range_pct": [下限,上限], "scope_basis": "完整计划范围的可辨认参考", "completed_basis": "已完成范围的可见证据及估算比例的理由"}}。percent 必须位于区间中，区间表达不确定性。每项必须有具体范围依据，不得用阶段名称代替。没有足够依据填 null，禁止随意编造百分比。两期不可对应时 changes 留空。
输出仍为一个 JSON 对象。由程序汇总分项百分比；不得在 summary 中编造全工程完成率。'''


def _number(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)


def _estimate(value, status):
    if status=='unclear' or not isinstance(value,dict): return None
    p=value.get('percent'); band=value.get('range_pct'); scope=value.get('scope_basis'); done=value.get('completed_basis')
    if not (_number(p) and isinstance(band,list) and len(band)==2 and all(_number(x) for x in band) and 0<=band[0]<=p<=band[1]<=100): return None
    if not all(isinstance(x,str) and x.strip() for x in (scope,done)): return None
    if status=='done' and p!=100: return None
    if status=='not_started' and p!=0: return None
    if status=='in_progress' and not 0<p<100: return None
    return dict(percent=p,range_pct=band,scope_basis=scope.strip(),completed_basis=done.strip())


def normalize_phases(raw, project_type='reservoir'):
    base=normalize_stages(raw,project_type)
    groups={}
    for item in raw:
        if isinstance(item,dict) and isinstance(item.get('id'),str): groups.setdefault(item['id'],[]).append(item)
    for item,cfg in zip(base,get_stages(project_type)):
        matches=groups.get(item['id'],[]); src=matches[0] if len(matches)==1 else {}
        phase=src.get('phase'); bs=src.get('before_status'); bp=src.get('before_phase'); be=src.get('before_evidence')
        if (not isinstance(bs,str) or bs not in COMPAT or not isinstance(be,str) or not be.strip() or (bs=='not_started' and cfg['visibility']!='exterior')): bs,be='unclear','前期证据不足'
        item.update(phase=phase if isinstance(phase,str) and phase in COMPAT[item['status']] else 'unclear',before_status=bs,before_evidence=be,before_phase=bp if isinstance(bp,str) and bp in COMPAT[bs] else 'unclear',progress_estimate=_estimate(src.get('progress_estimate'),item['status']),before_progress_estimate=_estimate(src.get('before_progress_estimate'),bs))
    return base


def _aggregate(rows,key,tw):
    known=[r for r in rows if r[key] is not None]; w=sum(r['weight'] for r in known)
    p=sum(r['weight']*r[key]['percent'] for r in known)
    lo=sum(r['weight']*r[key]['range_pct'][0] for r in known); hi=sum(r['weight']*r[key]['range_pct'][1] for r in known)
    return dict(estimated_total_progress_pct=round(p/tw,2) if w==tw and tw else None,
                estimated_assessable_progress_pct=round(p/w,2) if w else None,
                assessable_range_pct=[round(lo/w,2),round(hi/w,2)] if w else None,
                overall_possible_range_pct=[round(lo/tw,2),round((hi+(tw-w)*100)/tw,2)] if tw else None,
                assessed_weight=w,total_weight=tw)


def compute_phase_progress(items,project_type='reservoir'):
    rows=[{**item,'name':cfg['name'],'weight':cfg['weight'],'visibility':cfg['visibility']} for item,cfg in zip(normalize_phases(items,project_type),get_stages(project_type))]
    tw=total_weight(project_type); before=_aggregate(rows,'before_progress_estimate',tw); after=_aggregate(rows,'progress_estimate',tw)
    common=[r for r in rows if r['progress_estimate'] is not None and r['before_progress_estimate'] is not None]; cw=sum(r['weight'] for r in common)
    delta=sum(r['weight']*(r['progress_estimate']['percent']-r['before_progress_estimate']['percent']) for r in common)
    dam=next((r for r in rows if r['id']=='dam_body'),{})
    return dict(metric_type='image_estimated_completion_pct_v3',before=before,after=after,dam_before=dam.get('before_progress_estimate'),dam_after=dam.get('progress_estimate'),common_weight=cw,common_progress_delta_pp=round(delta/cw,2) if cw else None,stages=rows)
