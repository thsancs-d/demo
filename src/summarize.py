"""
汇总多组验证结果：按"后期照片日期"排序，输出时间线表并检查进度是否单调递增。

用法：python src/summarize.py [output 目录]
"""

from __future__ import annotations

import argparse
from datetime import date
from stages import PROFILES, get_stages
import glob
import re
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHORT = {"done": "已完成", "in_progress": "进行中",
         "not_started": "未开始", "unclear": "看不清"}
STAGE_ORDER = ["earthwork", "foundation", "structure", "masonry", "roof",
               "facade", "mep", "finishing", "landscape"]


def collect(out_root: str, project_type="building") -> list[dict]:
    rows = []
    for f in glob.glob(os.path.join(out_root, "*", "vlm_raw.json")):
        try:
            with open(f, encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:                               # noqa: BLE001
            continue
        meta, vlm, prog = d.get("meta", {}), d.get("vlm", {}), d.get("progress", {})
        if meta.get("project_type", "building") != project_type:
            continue
        try:
            value = meta.get("after_date", "")
            date.fromisoformat(value + "-01" if re.fullmatch(r"\d{4}-\d{2}", value) else value)
        except (ValueError, TypeError):
            continue
        rows.append({
            "metric_type": prog.get("metric_type", "visual_stage_score"),
            "estimate": prog,
            "execution_mode": meta.get("execution_mode", "live"),
            "dir": os.path.basename(os.path.dirname(f)),
            "before_date": meta.get("before_date", ""),
            "after_date": meta.get("after_date", ""),
            "progress": prog.get("progress_pct"),
            "floor": prog.get("progress_floor"),
            "counted": prog.get("counted_weight"),
            "phase": {s.get("id"): s.get("phase", "unclear") for s in vlm.get("stages", [])},
            "range": prog.get("visual_score_range"),
            "comparable_delta": prog.get("comparable_delta_score"),
            "comparable_weight": prog.get("comparable_weight"),
            "statuses": {s.get("id"): s.get("status") for s in vlm.get("stages", [])},
            "conf": {s.get("id"): s.get("confidence") for s in vlm.get("stages", [])},
            "changes": len(vlm.get("changes", [])),
            "risks": len(vlm.get("risks", [])),
            "summary": vlm.get("summary", ""),
        })
    # 只保留有日期的、且能解析的
    rows = [r for r in rows if r["after_date"]]
    rows.sort(key=lambda r: r["after_date"])
    return rows


def summarize_reservoir(rows, out_root):
    from vlm_report import format_pct, format_range, format_estimate
    rows=[r for r in rows if r['metric_type']=='image_estimated_completion_pct_v3' and r['execution_mode']=='live']
    if not rows:
        print('尚无新版线上识别结果。'); return
    md=['# 水库多期施工进度（影像估算）','','| 日期区间 | 大坝前期 | 大坝后期 | 后期全工程估计 | 全工程可能范围 | 可估算分项加权进度 | 覆盖权重 |','|---|---|---|---|---|---|---|']
    for r in rows:
        p=r['estimate']; a=p['after']
        md.append(f"| {r['before_date']} → {r['after_date']} | {format_estimate(p['dam_before'])} | {format_estimate(p['dam_after'])} | {format_pct(a['estimated_total_progress_pct'])} | {format_range(a['overall_possible_range_pct'])} | {format_pct(a['estimated_assessable_progress_pct'])} | {a['assessed_weight']}/{a['total_weight']} |")
    md += ['', '## 分项百分比（后期）', '| 日期 | '+' | '.join(s['name'] for s in get_stages('reservoir'))+' |','|---'*(len(get_stages('reservoir'))+1)+'|']
    for r in rows:
        m={x['id']:x.get('progress_estimate') for x in r['estimate']['stages']}
        md.append('| '+r['after_date']+' | '+' | '.join(format_estimate(m.get(s['id'])) for s in get_stages('reservoir'))+' |')
    md += ['', '不同期的覆盖范围可能不同。影像估算不等于真实工程量。重复出现的同一日期可能具有不同估算值，不强制单调上升。']
    text='\n'.join(md); print(text)
    with open(os.path.join(out_root,'summary_reservoir.md'),'w',encoding='utf-8') as f: f.write(text+'\n')


def main() -> None:
    ap = argparse.ArgumentParser(description="同一工程多期视觉状态评分汇总")
    ap.add_argument("out_root", nargs="?", default=os.path.join(ROOT, "output"))
    ap.add_argument("--project-type", choices=PROFILES, default="building")
    args = ap.parse_args()
    out_root = args.out_root
    rows = collect(out_root, args.project_type)
    if args.project_type == 'reservoir':
        return summarize_reservoir(rows, out_root)
    if not rows:
        print("没找到该工程类型且有有效日期的报告。请先运行识别。")
        return

    print("=" * 78)
    print(" 时间线验证（按后期照片日期排序）")
    print("=" * 78)
    print(f"{'后期日期':12s}{'区间':26s}{'状态评分':>7s}{'全权重':>7s}{'可判权重':>9s}{'新增':>5s}")
    for r in rows:
        span = f"{r['before_date']}~{r['after_date']}"
        p = f"{r['progress']:.1f}" if r["progress"] is not None else "-"
        fl = f"{r['floor']:.1f}" if r["floor"] is not None else "-"
        print(f"{r['after_date']:12s}{span:26s}{p:>7s}{fl:>7s}"
              f"{str(r['counted']):>9s}{r['changes']:>5d}")

    print("\n状态评分变化检查（视角/覆盖率不同可导致下降，不代表实际进度倒退）:")
    vals = [(r["after_date"], r["progress"]) for r in rows
            if r["progress"] is not None]
    ok = True
    for (d1, v1), (d2, v2) in zip(vals, vals[1:]):
        flag = "OK " if v2 >= v1 else "下降"
        if v2 < v1:
            ok = False
        print(f"  {d1} {v1:.1f}  ->  {d2} {v2:.1f}   {flag} "
              f"({v2 - v1:+.1f})")
    verdict = "有效评分不足两期" if len(vals) < 2 else ("评分未下降" if ok else "评分下降，需人工复核")
    print(f"\n 结论：{verdict}")

    print("\n工序状态矩阵:")
    hdr = f"{'工序':12s}" + "".join(f"{r['after_date'][5:]:>12s}" for r in rows)
    print(hdr)
    for sid in (s["id"] for s in get_stages(args.project_type)):
        line = f"{sid:12s}"
        for r in rows:
            st = SHORT.get(r["statuses"].get(sid), "-")
            line += f"{st:>12s}"
        print(line)

    md = ["# 多组样本验证汇总\n",
          "| 后期日期 | 区间 | 可见状态评分 | 全权重评分 | 可判权重 | 新增条目 |",
          "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['after_date']} | {r['before_date']}~{r['after_date']} "
                  f"| {r['progress']} | {r['floor']} | {r['counted']} "
                  f"| {r['changes']} |")
    md.append(f"\n**状态评分变化**：{verdict}（不代表实际工程量进度）\n")
    md.append("## 各组摘要\n")
    for r in rows:
        md.append(f"- **{r['after_date']}**：{r['summary']}")
    p = os.path.join(out_root, "summary.md" if args.project_type == "building" else "summary_reservoir.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\n汇总已写入 {p}")


if __name__ == "__main__":
    main()
