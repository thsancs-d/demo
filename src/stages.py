"""
工序清单与权重配置。

这是整个方案里唯一需要"按项目定制"的东西：
不同工程（住宅/厂房/市政）的工序和权重完全不同，改这里就行，不用动代码。

weight 是该项在总进度里的占比权重，全部加起来建议 = 100。
"""

from __future__ import annotations

# 状态 -> 折算系数（用于算进度）
STATUS_FACTOR = {
    "done": 1.0,
    "in_progress": 0.5,
    "not_started": 0.0,
    # unclear 不参与分母，避免模型看不清就把进度拉低
}

STAGES: list[dict] = [
    {"id": "earthwork", "name": "土方开挖与基坑支护", "weight": 5,
     "visibility": "exterior",
     "hint": "看基坑轮廓、边坡支护、降水井、土方堆放"},
    {"id": "foundation", "name": "基础与地下室结构", "weight": 12,
     "visibility": "exterior",
     "hint": "看筏板/承台、地下室墙体顶板、地下层数"},
    {"id": "structure", "name": "主体结构（楼板/柱/剪力墙）", "weight": 35,
     "visibility": "exterior",
     "hint": "数楼层数、看模板支撑、钢筋绑扎、混凝土浇筑面、爬模/铝模"},
    {"id": "masonry", "name": "砌体与二次结构", "weight": 10,
     "visibility": "interior",
     "hint": "看填充墙、构造柱、过梁、圈梁"},
    {"id": "roof", "name": "屋面与防水", "weight": 5,
     "visibility": "exterior",
     "hint": "看屋面找坡层、防水卷材、女儿墙、出屋面结构"},
    {"id": "facade", "name": "外立面（幕墙/门窗/涂料）", "weight": 12,
     "visibility": "exterior",
     "hint": "看玻璃幕墙龙骨与板块、窗框安装、外墙涂料/面砖"},
    {"id": "mep", "name": "机电安装（水/电/暖通）", "weight": 13,
     "visibility": "interior",
     "hint": "看立管、桥架、风管、屋面设备基础、机房"},
    {"id": "finishing", "name": "室内装修", "weight": 6,
     "visibility": "interior",
     "hint": "看隔墙、吊顶、地面找平、公共区域装修"},
    {"id": "landscape", "name": "室外总平与景观", "weight": 2,
     "visibility": "exterior",
     "hint": "看道路硬化、绿化、围挡拆除、场地清理"},
]


from reservoir_stages import RESERVOIR_STAGES

PROFILES = {"building": STAGES, "reservoir": RESERVOIR_STAGES}


def get_stages(project_type="building"):
    return PROFILES[project_type]


def total_weight(project_type="building"):
    return sum(s["weight"] for s in get_stages(project_type))


def normalize_stages(items, project_type="building"):
    """未知、缺失、重复冲突、无证据的状态统一降为 unclear。"""
    if not isinstance(items, list):
        raise ValueError("stages 必须是数组")
    grouped = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            grouped.setdefault(item["id"], []).append(item)
    result = []
    for cfg in get_stages(project_type):
        sid = cfg["id"]
        entries = grouped.get(sid, [])
        item = entries[0] if len(entries) == 1 else {}
        status = item.get("status", "unclear")
        evidence = item.get("evidence", "")
        confidence = item.get("confidence")
        if not isinstance(status, str) or status not in (*STATUS_FACTOR, "unclear") or not isinstance(evidence, str) or not evidence.strip():
            status = "unclear"
            evidence = "缺少有效可见证据，或工序缺失/重复"
        if status == "not_started" and cfg["visibility"] != "exterior":
            status = "unclear"
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            confidence = None
        result.append(dict(id=sid, status=status, evidence=evidence, confidence=confidence))
    return result


def compute_progress(vlm_stages, project_type="building"):
    """工序状态评分，不是实测工程完成率或数学意义的下限。"""
    counted = total_w = 0.0
    detail = []
    for item, cfg in zip(normalize_stages(vlm_stages, project_type), get_stages(project_type)):
        factor = STATUS_FACTOR.get(item["status"])
        if factor is not None:
            counted += cfg["weight"] * factor
            total_w += cfg["weight"]
        detail.append({**item, "name": cfg["name"], "weight": cfg["weight"],
                       "visibility": cfg["visibility"], "counted": factor is not None,
                       "factor": factor})
    tw = total_weight(project_type)
    return {"progress_pct": round(counted / total_w * 100, 1) if total_w else None,
            "progress_floor": round(counted / tw * 100, 1) if tw else None,
            "counted_weight": total_w, "total_weight": tw,
            "metric_type": "visual_stage_score", "stages": detail}
