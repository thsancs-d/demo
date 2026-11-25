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


def total_weight() -> int:
    return sum(s["weight"] for s in STAGES)


def compute_progress(vlm_stages: list[dict]) -> dict:
    """
    把模型给出的工序状态折算成加权进度。
    模型只负责"判断有没有看到"，算术由代码做——不让模型直接报百分比。

    同时给出两个数，避免"分母变了进度就跳"的错觉：
      progress_pct   — 只在可分判断的工序里算（乐观口径，回答"做的部分做到了几成"）
      progress_floor — 分母用全部权重，看不清按 0 计（保守口径，回答"整体至少完成了几成"）
    """
    by_id = {s["id"]: s for s in STAGES}
    counted = 0.0
    total_w = 0.0
    all_w = 0.0
    detail = []
    for item in vlm_stages:
        sid = item.get("id")
        cfg = by_id.get(sid)
        if not cfg:
            continue
        status = str(item.get("status", "unclear")).lower()
        factor = STATUS_FACTOR.get(status)
        all_w += cfg["weight"]
        if factor is None:
            detail.append({**item, "name": cfg["name"], "weight": cfg["weight"],
                           "visibility": cfg["visibility"], "counted": False})
            continue
        counted += cfg["weight"] * factor
        total_w += cfg["weight"]
        detail.append({**item, "name": cfg["name"], "weight": cfg["weight"],
                       "visibility": cfg["visibility"], "factor": factor,
                       "counted": True})

    tw = total_weight()
    return {
        "progress_pct": round(counted / total_w * 100.0, 1) if total_w else 0.0,
        "progress_floor": round(counted / tw * 100.0, 1) if tw else 0.0,
        "counted_weight": round(total_w, 1),
        "total_weight": tw,
        "stages": detail,
    }
