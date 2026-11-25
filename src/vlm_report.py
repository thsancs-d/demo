"""
调用视觉大模型（DeepSeek V4.1 Flash / deepseek-flash）解读两期照片，输出进度报告。

用法：
    # 首次：把 key 填进 .env
    python src/vlm_report.py --before 前期.jpg --after 后期.jpg --out output/A

    # 可选：把 CV 差分结果一起喂进去（推荐，能明显提升定位准确率）
    python src/vlm_report.py --before a.jpg --after b.jpg --out output/A \
        --diff output/A/xxx_07_change_grid.png

    # 只检查提示词和图片负载，不真正调用（不花钱）
    python src/vlm_report.py --before a.jpg --after b.jpg --out output/A --dry-run

设计原则：
    房建保留原工序状态评价；水库按可解释的施工范围估算前后期完成百分比。
    实际工程量进度独立计算，不将影像估算当作实测。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time

import cv2


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stages import PROFILES, get_stages, compute_progress, normalize_stages
from visual_phase import phase_prompt, normalize_phases, compute_phase_progress
from quantity_progress import calculate_quantities  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path: str = os.path.join(ROOT, ".env")) -> None:
    """极简 .env 解析，不引入额外依赖。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def encode_image(path: str, max_edge: int = 1536, quality: int = 88) -> str:
    """读图 -> 等比缩放 -> JPEG -> base64 data URL。"""
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"读不到图片: {path}")
    h, w = img.shape[:2]
    scale = min(1.0, max_edge / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError(f"图片编码失败: {path}")
    b64 = base64.b64encode(buf.tobytes()).decode()
    return f"data:image/jpeg;base64,{b64}"


def build_prompt(before_date: str, after_date: str, has_diff: bool,
                 aligned: bool = True, project_type: str = "building", context: dict | None = None) -> str:
    STAGES = get_stages(project_type)
    ext = [s for s in STAGES if s.get("visibility") == "exterior"]
    hid = [s for s in STAGES if s.get("visibility") != "exterior"]

    def fmt(items):
        return "\n".join(
            f'- id="{s["id"]}"  {s["name"]}（权重{s["weight"]}）  '
            f'观察要点：{s["hint"]}' for s in items)

    stage_lines = (
        "【A. 外露工序 —— 从外部/高位视角通常可以直接看到】\n"
        + fmt(ext)
        + "\n\n【B. 隐蔽工序 —— 可能被遮挡、埋藏或位于水下，外部视角往往看不到】\n"
        + fmt(hid))

    after_desc = (
        f"【图2】后期现场照片（{after_date}），已由算法透视变换对齐到图1的视角，"
        f"可直接逐区域对比"
        if aligned else
        f"【图2】后期现场照片（{after_date}），拍摄视角可能与图1存在差异，"
        f"请先自行判断两张照片的对应关系再作比较")

    diff_desc = (
        "\n第三张图是算法生成的差分热力图：红色/橙色区块表示两个时期之间像素变化最大的位置。"
        "热力图位于前期照片坐标系；若图2未对齐，不得直接套用热力图坐标。它只用来帮你定位“哪里变了”，不代表那里一定完成了某道工序，判断仍要以照片本身为准。\n"
        if has_diff else "")

    domain = "水库水工建筑物" if project_type == "reservoir" else "房屋建筑"
    extra = ("水库专项规则：先判断是否同一工程，并区分同一场地与同一机位；未经可靠配准，不得断言同一视角。区分坝型，水位变化、天气、植被、车辆和临时土堆不是完工证据。即使差分通过几何检查，山地三维视差仍可能存在；只报告能在两图独立辨认的施工变化，不把像素差异当工程量。"
             "仅凭坝体外观不能判定防渗、灌浆、压实度、蓄水验收或运行安全。围堰拆除可能是正常转换。"
             "局部施工完成不能代表整个分项完成；不适用或无法确认范围的工序写 unclear。"
             "明确无法比较时 changes 留空，在 risks 写明原因。" if project_type == "reservoir" else "")
    prompt = f"""你是{domain}施工进度影像评估专家。现在给你同一工程在不同日期的现场照片。
{extra}

【图1】前期现场照片（{before_date}）
{after_desc}
{diff_desc}
请完成两件事：
1. 判断【后期照片】中下列每道工序的完成状态；
2. 指出从前期到后期，画面里具体新增了什么。

工序清单：
{stage_lines}

status 只能取这四个值之一：
  done         — 有足够可见证据表明该工序外观整体完成（不代表验收）
  in_progress  — 正在施工中，能看到该工序的作业面/材料/半成品
  not_started  — 有明确可见的未开工证据（仅缺少痕迹不够）
  unclear      — 视线被遮挡、分辨率不足或不在画面内，无法判断

硬性要求（务必遵守）：
- 只依据画面可见证据，绝对不要推测或编造。
- 判断不了就写 unclear，这是允许的，不要为了凑数硬猜。
{ "- 施工进度百分比按文末水库专项格式输出。" if project_type == "reservoir" else "- 不要输出任何百分比数字，进度由程序计算。" }
- evidence 里必须写明画面位置和可见特征。
- 判断 A 类外露工序时：仅在工序适用且应观察的完整区域可见，有明确未开工证据时才可判 not_started；否则 unclear。
- 判断 B 类隐蔽工序时：严禁写 not_started。被遮挡、看不见内部，一律写 unclear。
  不要因为"整体还在结构施工阶段，所以装修应该没开始"这类推测而下结论，那是推测不是观察。
- 如果两张图不是同一工程或视角差异过大导致无法对应，在 risks 里明确指出。

只输出一个 JSON 对象，不要任何解释文字、不要 markdown 代码块，格式如下：
{{
  "stages": [
    {{"id": "工序id", "status": "done|in_progress|not_started|unclear",
      "evidence": "画面位置 + 可见特征", "confidence": 0.0}}
  ],
  "changes": [
    {{"where": "画面位置", "what": "新增/变化的具体内容", "stage_id": "对应工序id"}}
  ],
  "risks": ["值得注意的问题，没有就给空数组"],
  "summary": "一句话概括本期进展"
}}"""

    return prompt + ("\n\n" + phase_prompt(context) if project_type == "reservoir" else "")

def parse_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def normalize_vlm(vlm, project_type):
    if not isinstance(vlm, dict):
        raise ValueError("模型响应必须为 JSON 对象")
    stages = normalize_stages(vlm.get("stages", []), project_type)
    if project_type == "reservoir":
        stages = normalize_phases(vlm.get("stages", []), project_type)
    ids = {s["id"] for s in stages}
    changes = vlm.get("changes", [])
    risks = vlm.get("risks", [])
    return {"stages": stages,
            "changes": [c for c in changes if isinstance(c, dict) and isinstance(c.get("stage_id"), str) and c["stage_id"] in ids and all(isinstance(c.get(k), str) for k in ("where", "what"))] if isinstance(changes, list) else [],
            "risks": [r for r in risks if isinstance(r, str)] if isinstance(risks, list) else [],
            "summary": vlm.get("summary", "") if isinstance(vlm.get("summary"), str) else ""}


def format_pct(value):
    return f"{value:g}%" if value is not None else "无法估算"


def format_range(band):
    return f"{band[0]:g}%–{band[1]:g}%" if band is not None else "无法估算"


def format_estimate(est):
    return f"{format_pct(est['percent'])}（{format_range(est['range_pct'])}）" if est is not None else "无法估算"


def render_reservoir_report(vlm, prog, meta):
    b,a=prog['before'],prog['after']
    lines=['# 水库施工进度报告', f"前期：{meta['before_date']}；后期：{meta['after_date']}；模型：{meta['model']}；执行方式：{meta.get('execution_mode','未知')}", '', '## 施工进度百分比（影像估算）', '', '| 指标 | 前期 | 后期 |','|---|---|---|',f"| 大坝主体施工 | {format_estimate(prog['dam_before'])} | {format_estimate(prog['dam_after'])} |",f"| 可估算分项加权进度 | {format_pct(b['estimated_assessable_progress_pct'])} | {format_pct(a['estimated_assessable_progress_pct'])} |",f"| 全工程估算进度 | {format_pct(b['estimated_total_progress_pct'])} | {format_pct(a['estimated_total_progress_pct'])} |",f"| 全工程可能范围（含未知项） | {format_range(b['overall_possible_range_pct'])} | {format_range(a['overall_possible_range_pct'])} |",f"| 已估算分项权重 | {b['assessed_weight']}/{b['total_weight']} | {a['assessed_weight']}/{a['total_weight']} |",'']
    q=prog.get('quantity_progress'); lines.append(f"**实际工程量进度：{format_pct(q['progress_pct'])}**（用户提供工程量，未独立核实）" if q else '**实际工程量进度：未提供工程量，无法计算。**')
    lines += ['', '以上百分比是基于可见施工范围的估算，不是状态分数，也不是实际工程量完成比例。权重为示例配置；全工程范围按未知项0–100%计算，是条件范围而非统计置信区间。可估算分项可能随时期变化。',f"共同可估算工序的加权变化：{prog['common_progress_delta_pp']} 个百分点；共同权重 {prog['common_weight']}。" if prog['common_progress_delta_pp'] is not None else '共同可估算工序不足，无法比较增量。','', '## 分项施工进度', '| 工序 | 前期估计 | 后期估计 | 权重 | 范围和估算依据 |','|---|---|---|---|---|']
    for r in prog['stages']:
        def basis(est,evidence):
            return (est['scope_basis']+'；'+est['completed_basis']) if est else evidence
        ev=('前：'+basis(r['before_progress_estimate'],r['before_evidence'])+' / 后：'+basis(r['progress_estimate'],r['evidence'])).replace('|','/').replace('\n',' ')
        lines.append(f"| {r['name']} | {format_estimate(r['before_progress_estimate'])} | {format_estimate(r['progress_estimate'])} | {r['weight']} | {ev} |")
    lines += ['', '## 本期新增内容', *[f"- {c['where']}：{c['what']}" for c in vlm.get('changes',[])], '', '## 风险与提示', *[f'- {r}' for r in vlm.get('risks',[])], '', vlm.get('summary','')]
    return '\n'.join(lines)+'\n'


def render_report(vlm: dict, prog: dict, meta: dict) -> str:
    if prog.get("metric_type") == "image_estimated_completion_pct_v3":
        return render_reservoir_report(vlm, prog, meta)
    rows = ["| 工序 | 状态 | 权重 | 证据 | 置信度 |", "|---|---|---|---|---|"]
    label = {"done": "已完成", "in_progress": "进行中",
             "not_started": "未开始", "unclear": "看不清"}
    for s in prog["stages"]:
        raw = next((x for x in vlm.get("stages", [])
                    if x.get("id") == s.get("id")), {})
        rows.append(
            f"| {s['name']} | {label.get(raw.get('status', 'unclear'), '—')} "
            f"| {s['weight']} | {str(raw.get('evidence', '')).replace('|', '/')} "
            f"| {raw.get('confidence', '')} |")

    changes = "\n".join(
        f"- **{c.get('where', '')}**：{c.get('what', '')}"
        for c in vlm.get("changes", [])) or "- 未识别出明确的新增内容"
    risks = "\n".join(f"- {r}" for r in vlm.get("risks", [])) or "- 无"

    score = f"{prog['progress_pct']}%" if prog['progress_pct'] is not None else "无法判断"
    scoring_note = '进行中按0.5折算'
    quantity = prog.get("quantity_progress")
    q_text = f"**工程量加权进度：{quantity['progress_pct']}%**（用户提供数据，未独立核实）" if quantity else "**实际工程量进度：未提供工程量，无法计算。**"
    return f"""# 施工进度影像评估报告

**工程类型**：{meta.get('project_type', 'building')}

**前期照片**：{meta['before']}（{meta['before_date']}）
**后期照片**：{meta['after']}（{meta['after_date']}）
**模型**：{meta['model']}　**生成时间**：{meta['time']}

## 结论

**可见工序状态评分：{score}**（{scoring_note}）
**全权重状态评分：{prog['progress_floor']} / 100**（未知按0计；不是实际进度下限）

{q_text}

可判断权重 {prog['counted_weight']} / {prog['total_weight']}。
可判断权重占比反映影像覆盖程度；必要时补拍近景或增加机位。

{vlm.get('summary', '')}

## 逐项判断

{chr(10).join(rows)}

## 本期新增内容

{changes}

## 风险与提示

{risks}

---
> 视觉状态评分不是实测工程完成率；工程量进度仅来自用户输入。不能替代现场实测与监理签认。
"""


def call_model(client, model: str, content: list[dict], think: bool):
    """
    调用模型，返回 (response, 实际生效的参数说明)。

    关思考模式实测：网关支持 reasoning_effort="none"，也支持
    thinking={"type":"disabled"}；enable_thinking 会被静默忽略。
    这里做逐级降级，保证换网关/换模型也能跑。
    """
    from openai import APIConnectionError
    base = dict(model=model, messages=[{"role": "user", "content": content}])
    opts: list[tuple[str, dict]] = []
    if not think:
        opts.append(('reasoning_effort="none"', {"reasoning_effort": "none"}))
        opts.append(('thinking=disabled', {"extra_body": {"thinking": {"type": "disabled"}}}))
    opts.append(("默认(带思考)", {}))

    last_err: Exception | None = None
    for label, opt in opts:
        for use_rf in (True, False):
            kw = {**base, **opt}
            if use_rf:
                kw["response_format"] = {"type": "json_object"}
            try:
                resp = client.chat.completions.create(**kw)
                note = label + ("+json_mode" if use_rf else "")
                return resp, note
            except Exception as e:                      # noqa: BLE001
                last_err = e
                if isinstance(e, APIConnectionError):
                    raise
                # 该参数组不被支持 -> 换下一组
                if getattr(e, "status_code", None) not in (400, 422) and not isinstance(e, TypeError):
                    raise
                continue
    raise last_err if last_err else RuntimeError("调用失败")


def main() -> None:
    ap = argparse.ArgumentParser(description="视觉模型解读施工照片")
    ap.add_argument("--project-type", choices=PROFILES, default="building")
    ap.add_argument("--context", help="工程名称、坝型等背景 JSON（不含进度真值）")
    ap.add_argument("--response-file", help="离线回放模型 JSON，不调用 API")
    ap.add_argument("--quantities", help="经人工核实的工程量 JSON")
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--out", default="output/vlm")
    ap.add_argument("--diff", default=None, help="CV 差分图（可选，推荐）")
    ap.add_argument("--after-aligned", default=None,
                    help="对齐后的后期图（推荐传，来自 run_compare 的 02_after_aligned.png）")
    ap.add_argument("--before-date", default="前期")
    ap.add_argument("--after-date", default="后期")
    ap.add_argument("--max-edge", type=int, default=1536)
    ap.add_argument("--fast", action="store_true",
                    help="关闭思考模式（快约4倍、省约12倍，但判定稳定性明显下降）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    quantity = None
    if args.quantities:
        with open(args.quantities, encoding="utf-8") as f:
            quantity = calculate_quantities(json.load(f), args.project_type)
    load_env()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")

    context = None
    if args.context:
        with open(args.context, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data,dict): raise ValueError('context 必须为对象')
        context = {k:v for k,v in data.items() if k in ('project_name','dam_type','scope_note') and isinstance(v,str)}
    prompt = build_prompt(args.before_date, args.after_date, bool(args.diff),
                          aligned=bool(args.after_aligned), project_type=args.project_type, context=context)
    img2_path = args.after_aligned or args.after

    content: list[dict] = [{"type": "text", "text": prompt},
                           {"type": "text", "text": "【图1】前期照片："},
                           {"type": "image_url",
                            "image_url": {"url": encode_image(args.before, args.max_edge),
                                          "detail": "high"}},
                           {"type": "text", "text": "【图2】后期照片："},
                           {"type": "image_url",
                            "image_url": {"url": encode_image(img2_path, args.max_edge),
                                          "detail": "high"}}]
    if args.diff:
        content.append({"type": "text", "text": "【图3】差分热力图（红色=变化区域）："})
        content.append({"type": "image_url",
                        "image_url": {"url": encode_image(args.diff, args.max_edge),
                                      "detail": "high"}})

    payload_mb = sum(len(c["image_url"]["url"]) for c in content
                     if c["type"] == "image_url") / 1024 / 1024
    print(f"[准备] 模型={model}  图片={3 if args.diff else 2} 张  "
          f"base64 负载≈{payload_mb:.1f}MB")

    if args.dry_run:
        print("[dry-run] 提示词预览：\n" + "-" * 60)
        print(prompt[:1200] + "\n...(略)")
        print("-" * 60)
        print("[dry-run] 未调用 API。")
        return

    if not api_key and not args.response_file:
        print("\n[错误] .env 里的 DEEPSEEK_API_KEY 还是空的。")
        print(f"       请编辑 {os.path.join(ROOT, '.env')} 填入你的 key 后重试。")
        sys.exit(2)

    t0 = time.time()
    resp = None
    if args.response_file:
        with open(args.response_file, encoding='utf-8') as f:
            saved = json.load(f)
        raw_vlm = saved.get('raw_vlm', saved) if isinstance(saved,dict) else saved
        used = '离线回放（未调用 API）'
    else:
        from openai import OpenAI, APIConnectionError
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=120, max_retries=1)
        try:
            resp, used = call_model(client, model, content, think=not args.fast)
        except APIConnectionError:
            print('[错误] 无法连接 API 网关；检查网络、DNS 和服务地址。', file=sys.stderr)
            sys.exit(3)
        raw_vlm = parse_json(resp.choices[0].message.content or '')
    print(f'[调用] {used}')
    vlm = normalize_vlm(raw_vlm, args.project_type)
    prog = (compute_phase_progress(vlm['stages'], args.project_type) if args.project_type == 'reservoir'
            else compute_progress(vlm['stages'], args.project_type))
    prog["quantity_progress"] = quantity
    os.makedirs(args.out, exist_ok=True)
    meta = {
        "project_type": args.project_type,
        "before": os.path.basename(args.before),
        "after": os.path.basename(img2_path),
        "before_date": args.before_date, "after_date": args.after_date,
        "model": model if resp is not None else "offline_replay",
        "context": context,
        "execution_mode": "live" if resp is not None else "offline_replay",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(os.path.join(args.out, "vlm_raw.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "vlm": vlm, "progress": prog, "raw_vlm": raw_vlm},
                  f, ensure_ascii=False, indent=2)

    with open(os.path.join(args.out, "prompt.txt"), "w", encoding="utf-8") as f:
        f.write(prompt)
    md = render_report(vlm, prog, meta)
    rp = os.path.join(args.out, "report.md")
    with open(rp, "w", encoding="utf-8") as f:
        f.write(md)

    u = resp.usage if resp is not None else None
    print(f"\n[完成] 耗时 {time.time() - t0:.1f}s  "
          f"tokens 入/出 = {getattr(u, 'prompt_tokens', '?')}"
          f"/{getattr(u, 'completion_tokens', '?')}")
    if prog.get('metric_type') == 'image_estimated_completion_pct_v3':
        print(f"[结果] 大坝主体施工进度（影像估算）：{format_estimate(prog['dam_before'])} → {format_estimate(prog['dam_after'])}")
        a=prog['after']; print(f"[结果] 全工程估算进度：{format_pct(a['estimated_total_progress_pct'])}；可能范围：{format_range(a['overall_possible_range_pct'])}")
        print(f"[结果] 可估算分项加权进度：{format_pct(a['estimated_assessable_progress_pct'])}；覆盖权重 {a['assessed_weight']}/{a['total_weight']}")
        print(f"[结果] 实际工程量进度：{format_pct(quantity['progress_pct']) if quantity else '未提供工程量，无法计算'}")
    else:
        print(f"[结果] 可见状态评分 {prog['progress_pct']} / 100 (全权重评分 {prog['progress_floor']} / 100)  (可判断权重 {prog['counted_weight']}/{prog['total_weight']})")
    print(f"[报告] {rp}")
    print(f"[原始] {os.path.join(args.out, 'vlm_raw.json')}")
    print("\n" + "-" * 60)
    print(vlm.get("summary", ""))


if __name__ == "__main__":
    main()
