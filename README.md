> **当前版本 V8：** 从 [START_HERE.md](START_HERE.md) 开始。累计监测使用 `src/run_aigawa.py --all` 或 `--new-image`，新增本期证据筛选和准确率评估入口；详细口径见 [README_V8.md](README_V8.md)。无参数入口仍保留旧双图比较行为。尚未用核实标签验证真实识别准确率是否提升。

# 工程进度识别（房建 / 水库）

基于 SIFT / RootSIFT / AKAZE 配准、SSIM 差分和视觉模型，支持房建双图比较、水库双图比较及水库累计施工进度监测。算法支持 Python 3.10+；当前环境使用 Python 3.12 验证。

## 安装

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

以下命令在项目根目录执行；Windows 将 `.venv/bin/python` 替换为 `.venv\Scripts\python.exe`。已有虚拟环境可直接使用，无需重建。

覆盖更新时保留现有 `.env` 和历史输出；不需要修改密钥即可运行离线测试。`.env.example` 提供网关和模型配置示例，线上服务须支持 `image_url` 多模态输入及 OpenAI 兼容接口。本轮仅做离线验证，未调用模型服务。正式运行会向配置的服务发送照片。

## V8 累计监测

先用随项目提供的模拟响应跑通四期流程（不调用模型）：

```bash
.venv/bin/python src/run_aigawa.py --all --responses tests/fixtures/aigawa_responses_v8 --out output/aigawa_v8_offline_demo
.venv/bin/python src/run_aigawa.py --refresh-only --out output/aigawa_v8_offline_demo
```

该命令使用四期真实裁切照片及人工编写的模拟响应，测试配准、请求清单、证据筛选、进度计算和图表。百分比、证据框和范围依据均为测试输入，不是照片识别结果；正式监测使用另一输出目录。

配置模型后，执行完整四期识别或逐次追加：

```bash
.venv/bin/python src/run_aigawa.py --all --out output/aigawa_v8
.venv/bin/python src/run_aigawa.py --new-image data/new.jpg --date 2022-03-01 --out output/aigawa_v8
.venv/bin/python src/run_aigawa.py --refresh-only --out output/aigawa_v8
.venv/bin/python src/run_aigawa.py --help
```

同一工程的后续操作使用同一个 `--out`。已完成日期自动跳过；要用 V8 重新识别旧照片，请使用尚未存在的新输出目录，例如 `output/aigawa_v8`。`--refresh-only` 只重建报表，V5/V6/V7 记录保留各自原有算法，不会重新调用模型。离线历史刷新也不需要原响应文件。

V8 仅接受指向本期原图、证据框有效、范围完整且清晰可见的分项百分比；置信度门槛 0.7 是未标定筛选规则，不代表 70% 准确率。未知分项不自动推断或按均值外推。只有全部分项均有合格的本期直接估算时才给总工程单值，否则报告已估算分项内部完成率和总工程可能区间。证据框符合格式并不能证明识别内容正确；更严格的筛选可能增加无法估算的结果。

每期保存原图、提示词、图片 SHA-256、请求清单和原始响应 `raw_model.json`；`history.json` 与 `latest_progress.json` 包含 `quality_review`，`latest_report.md` 显示拒绝原因。`latest_progress.png` 为最新图表。

## 固定镜头时序监测

只有同一镜头的不同日期照片时，可逐期运行固定镜头模式。第一张照片建立基准，从第二张起比较两期同一画面区域；事件记录包含日期图号、变化方向、分项和证据框。它不会根据变化面积生成总体进度百分比。

```bash
.venv/bin/python src/run_aigawa.py --new-image data/2025-01.jpg --date 2025-01-01 --fixed-camera --out output/site_fixed_camera
.venv/bin/python src/run_aigawa.py --new-image data/2025-02.jpg --date 2025-02-01 --fixed-camera --out output/site_fixed_camera
.venv/bin/python src/run_aigawa.py --refresh-only --out output/site_fixed_camera
```

从第一期开始，每次都使用 `--fixed-camera` 和同一个 `--out` 目录。模型可以记录同一区域的可见变化；视角、季节、植被、水位、天气和机械变动仍需人工复核。局部变化不代表整个分项完成，固定镜头不能确认压实、灌浆、隐蔽工程或验收。详细输出字段、限制和鵜川坝测试记录见 [README_FIXED_CAMERA.md](README_FIXED_CAMERA.md)。

## 验证真实识别误差

将 `config/aigawa_accuracy_labels.example.json` 复制为 `config/aigawa_accuracy_labels.json`，逐项填入经人工核实的百分比、来源和范围依据，再将对应记录的 `verified` 设为 `true`。模板中的百分比为 `null`、`verified=false`，不能直接用于计分。标签须与模型的 `visual_completion_pct` 分项口径一致；工程量、模拟响应和未核实的完成节点不能替代它。

```bash
.venv/bin/python src/evaluate.py --history output/aigawa_v8/history.json --labels config/aigawa_accuracy_labels.json --tolerance-pp 10
```

评估只统计同一工程的线上、本期直接估算，输出 MAE、偏差、误差阈值内比例、区间覆盖率、平均区间宽度和预测覆盖率。误差指标须与预测覆盖率一起看，避免把拒绝更多估算误认为精度更高。没有核实标签或有效预测时，不生成误差成绩；模拟历史不计分。现有四期资料只有一个未独立核实的填筑完成节点，尚不足以证明准确率提升。标签字段和兼容性说明见 [README_V8.md](README_V8.md)。

## 水库一键识别

准备同一水库、相近视角的前后期照片（已包含四期安威川照片），最好同一机位、焦距和光照。先免费检查流程（不调用模型）：

```bash
.venv/bin/python src/run_reservoir.py --before data/before.jpg --after data/after.jpg --out output/reservoir/period01 --dry-run
```

正式运行：

```bash
.venv/bin/python src/run_reservoir.py --before data/before.jpg --after data/after.jpg --out output/reservoir/period01 --before-date 2026-08-01 --after-date 2026-09-01
```

参数：`--roi 0.1,0.2,0.8,0.6` 仅限制 CV 差分区域；`--skip-cv` 跳过配准；`--fast` 尝试关闭模型思考；`--quantities config/reservoir_quantities.json` 可选，须使用经核实的数据。建议每期使用新的输出目录，避免旧报告与新运行混淆。若配准失败或内点数<12、内点率<50%、重叠率<50%，不传差分图给模型；这只是示例质量门槛，不代表精确配准。模型始终使用原始前后照片。热力图在前期图坐标系，红/橙表示较大变化。

也可直接使用原入口：

```bash
.venv/bin/python src/vlm_report.py --project-type reservoir --before data/before.jpg --after data/after.jpg --out output/reservoir/period01
.venv/bin/python src/vlm_report.py --before data/building_before.jpg --after data/building_after.jpg --out output/building/period01
```

原 `run_compare.py`、`batch_validate.sh` 仍在；后者依赖原项目外部房建样本和 Windows 虚拟环境路径，不是水库批处理入口。

## 输出

- `cv_quality.json`：配准是否足以传差分图及指标（仅一键入口）。
- `cv/`：原图、配准图、并排图、重叠掩码、热力图、变化框、网格和 `result.json`（配准成功时）。
- `report.md`：施工工序、影像估算百分比、证据、新增变化、风险、工程量进度（如有）。
- `vlm_raw.json`：原始解析响应 `raw_vlm`、标准化 `vlm`、`meta` 和 `progress`（水库 V3 使用新的进度字段，旧房建字段保留）。

多期汇总：每期放在同一工程专属目录下，使用真实 ISO 日期；不要混合不同水库。

```bash
.venv/bin/python src/summarize.py output/reservoir --project-type reservoir
```

## 工序及进度

`src/reservoir_stages.py` 定义 8 类水库工序及示例权重。`done/in_progress/not_started/unclear` 为可见状态；隐蔽工序不得因看不见而判未开工。不适用或无法确定范围按 unclear。重复、缺失、非法工序状态降为 unclear。水库 V3 使用 `progress.before` / `progress.after` 中的估算百分比及范围，`progress.dam_before` / `progress.dam_after` 为坝体专项估算。详见 README_V3.md；房建旧状态评分逻辑保留。

`config/reservoir_quantities.example.json` 为虚构工程量示例，复制并改为实际数据后再使用。每个分项权重由合同/WBS确定，必须覆盖全部工序、总和100；单位统一，计划量为正，实际量非负。不适用项可用权重0并填正的占位计划量及0实际量；超计划量按100%计入并标记。若分项包含不同单位的工程量，应先依据批准的统计规则换算或进一步拆分工序，不能直接加总。工程量与影像进度估算独立，模型不估算土石方体积。蓄水安全、灌浆质量、压实度、隐蔽工程和验收须现场核实。

## 源码与测试

- `cpm_core.py` / `run_compare.py`：原图像配准和差分；修复 SSIM 负值映射、热力图颜色及 ROI 越界校验。
- `stages.py` / `reservoir_stages.py`：工程类型配置及统一状态校验。
- `vlm_report.py`：工程类型提示词、模型调用及报告。
- `quantity_progress.py`：用户提供工程量的加权进度。
- `run_reservoir.py`：一键串联，按配准质量选择差分输入。
- `summarize.py`：按工程类型和有效日期汇总。
- `progress_tracker.py` / `recognition_quality.py`：累计监测、本期证据筛选与逐项拒绝记录。
- `evaluate.py`：核实标签与线上累计分项估算对比；保留旧双图评估入口。

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src tests
```

测试覆盖合成纹理及真实水库照片配准、模拟响应的四期累计流程、证据筛选、评估计分限制、请求清单校验、断点续跑、旧历史兼容、离线刷新、历史照片篡改检查及写入失败清理。本轮未调用线上模型，也未测得真实识别准确率。CV 的单应矩阵无法保证三维地形的严格对应，建议固定机位或先用正射影像配准；需要真实工程量时结合测量、设计资料及监理记录。


## 真实水库测试样本

参见 [data/README.md](data/README.md)，运行 `.venv/bin/python src/download_samples.py` 自动下载。


## 安威川四期数据
见 [datasets/aigawa/README.md](datasets/aigawa/README.md)。`--all` 导入四期累计监测；`--all --cv-only` 诊断相邻三组，不调用模型；无参数时仍执行首尾双图比较。
