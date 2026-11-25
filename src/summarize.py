"""
汇总多组验证结果：按"后期照片日期"排序，输出时间线表并检查进度是否单调递增。

用法：python src/summarize.py [output 目录]
"""

from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHORT = {"done": "已完成", "in_progress": "进行中",
         "not_started": "未开始", "unclear": "看不清"}
STAGE_ORDER = ["earthwork", "foundation", "structure", "masonry", "roof",
               "facade", "mep", "finishing", "landscape"]


def collect(out_root: str) -> list[dict]:
    rows = []
    for f in glob.glob(os.path.join(out_root, "*", "vlm_raw.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:                               # noqa: BLE001
            continue
        meta, vlm, prog = d.get("meta", {}), d.get("vlm", {}), d.get("progress", {})
        rows.append({
            "dir": os.path.basename(os.path.dirname(f)),
            "before_date": meta.get("before_date", ""),
            "after_date": meta.get("after_date", ""),
            "progress": prog.get("progress_pct"),
            "floor": prog.get("progress_floor"),
            "counted": prog.get("counted_weight"),
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


def main() -> None:
    out_root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "output")
    rows = collect(out_root)
    if not rows:
        print("没找到结果。先跑 batch_validate.sh。")
        return

    print("=" * 78)
    print(" 时间线验证（按后期照片日期排序）")
    print("=" * 78)
    print(f"{'后期日期':12s}{'区间':26s}{'进度':>7s}{'下限':>7s}{'可判权重':>9s}{'新增':>5s}")
    for r in rows:
        span = f"{r['before_date']}~{r['after_date']}"
        p = f"{r['progress']:.1f}%" if r["progress"] is not None else "-"
        fl = f"{r['floor']:.1f}%" if r["floor"] is not None else "-"
        print(f"{r['after_date']:12s}{span:26s}{p:>7s}{fl:>7s}"
              f"{str(r['counted']):>9s}{r['changes']:>5d}")

    print("\n单调性检查（越晚的照片，进度应越高）:")
    vals = [(r["after_date"], r["progress"]) for r in rows
            if r["progress"] is not None]
    ok = True
    for (d1, v1), (d2, v2) in zip(vals, vals[1:]):
        flag = "OK " if v2 >= v1 else "下降"
        if v2 < v1:
            ok = False
        print(f"  {d1} {v1:.1f}%  ->  {d2} {v2:.1f}%   {flag} "
              f"({v2 - v1:+.1f})")
    print(f"\n 结论：{'单调递增，通过' if ok else '存在倒退，需检查'}")

    print("\n工序状态矩阵:")
    hdr = f"{'工序':12s}" + "".join(f"{r['after_date'][5:]:>12s}" for r in rows)
    print(hdr)
    for sid in STAGE_ORDER:
        line = f"{sid:12s}"
        for r in rows:
            st = SHORT.get(r["statuses"].get(sid), "-")
            line += f"{st:>12s}"
        print(line)

    md = ["# 多组样本验证汇总\n",
          "| 后期日期 | 区间 | 进度 | 保守下限 | 可判权重 | 新增条目 |",
          "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['after_date']} | {r['before_date']}~{r['after_date']} "
                  f"| {r['progress']}% | {r['floor']}% | {r['counted']} "
                  f"| {r['changes']} |")
    md.append(f"\n**单调性**：{'通过' if ok else '存在倒退'}\n")
    md.append("## 各组摘要\n")
    for r in rows:
        md.append(f"- **{r['after_date']}**：{r['summary']}")
    p = os.path.join(out_root, "summary.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\n汇总已写入 {p}")


if __name__ == "__main__":
    main()
