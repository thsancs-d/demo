# V8 快速开始

项目包含四期安威川施工照片。更新时保留现有 `.env` 和 `output/`。以下命令在项目根目录执行，使用项目 `.venv`；Windows 将 `.venv/bin/python` 替换为 `.venv\Scripts\python.exe`。

## 1. 安装（已有可用环境可跳过）

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 2. 离线体验，无需密钥

```bash
.venv/bin/python src/run_aigawa.py --all --responses tests/fixtures/aigawa_responses_v8 --out output/aigawa_v8_offline_demo
open output/aigawa_v8_offline_demo/latest_progress.png
```

`open` 是 macOS 命令，也可直接打开输出文件。这里的图片是真实照片，响应、百分比、证据框和范围依据均为人工编写的测试数据；图表和报告标注“模拟数据”。第三期的测试百分比刻意下降，以验证系统不强制进度单调增长。这些结果不用于准确率评估。

## 3. 正式识别

先配置现有 `.env` 中的模型服务。以下命令首次完整运行会调用模型四次；正式结果使用独立目录：

```bash
.venv/bin/python src/run_aigawa.py --all --out output/aigawa_v8
open output/aigawa_v8/latest_progress.png
```

也可逐期添加照片。新日期必须晚于已有最新日期，同一工程始终使用相同 `--out`：

```bash
.venv/bin/python src/run_aigawa.py --new-image data/new.jpg --date 2022-03-01 --out output/aigawa_v8
```

如果只有同一镜头的多期照片，可从第一期起使用固定镜头时序模式；每次都加 `--fixed-camera` 并沿用同一个输出目录：

```bash
.venv/bin/python src/run_aigawa.py --new-image data/2025-01.jpg --date 2025-01-01 --fixed-camera --out output/site_fixed_camera
.venv/bin/python src/run_aigawa.py --new-image data/2025-02.jpg --date 2025-02-01 --fixed-camera --out output/site_fixed_camera
```

该模式报告同一画面区域的施工变化，不以变化面积计算总体进度百分比。细节与鵜川坝固定视角验证记录见 [README_FIXED_CAMERA.md](README_FIXED_CAMERA.md)。

V8 会检查本期证据框、完整范围、可见性、比例依据和置信度。0.7 的置信度门槛是未标定筛选规则，不代表 70% 准确率。没有全部分项的合格本期直接估算时，总进度显示为空，同时保留已估算分项完成率和总工程可能区间；请查看报告中的“证据检查”原因。

## 4. 续跑和刷新

重复执行原 `--all` 命令会跳过已完成日期；失败日期及后续日期继续处理。要用 V8 重新识别旧照片，必须换用尚未使用的新目录，例如 `output/aigawa_v8`。刷新不会重新识别，也不会把 V5/V6/V7 历史改成 V8 结果。只重建图表与报告时，无论历史来自线上还是离线，都无需模型或原响应目录：

```bash
.venv/bin/python src/run_aigawa.py --refresh-only --out output/aigawa_v8
# 离线演示目录的刷新：
.venv/bin/python src/run_aigawa.py --refresh-only --out output/aigawa_v8_offline_demo
```

最新结果是 `latest_progress.png`、`latest_report.md` 和 `latest_progress.json`；`history.json` 保存累计记录和 `quality_review`，`observations/日期/request_manifest.json` 保存请求审计信息，`raw_model.json` 保留该期原始响应。

## 5. 用核实标签评估

复制 `config/aigawa_accuracy_labels.example.json` 为 `config/aigawa_accuracy_labels.json`。模板没有真值；需要人工填写对应日期、分项的百分比和来源，核对 `scope_basis` 与 `visual_completion_pct` 影像口径一致后，才将 `verified` 设为 `true`。模板已填默认四张照片的 SHA-256，换图时须重新核对。

```bash
.venv/bin/python src/evaluate.py --history output/aigawa_v8/history.json --labels config/aigawa_accuracy_labels.json --tolerance-pp 10
```

只对同一工程的线上本期直接估算计分；模拟数据或没有核实标签时不生成误差成绩。输出 MAE、偏差、阈值内比例、区间覆盖率、平均区间宽度及预测覆盖率。务必同时查看预测覆盖率：拒绝更多估算可能降低已输出样本的误差，却不能单独证明整体准确率改善。本轮没有调用线上模型，现有标签也不足以验证准确率提升。

## 6. 检查与参数

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python src/run_aigawa.py --help
.venv/bin/python src/run_aigawa.py --all --cv-only
```

`--all` 是四期累计监测；`--all --cv-only` 和 `--all --dry-run` 是相邻三组诊断；无参数运行仍使用旧双图入口。详细规则、标签字段及兼容性见 [README_V8.md](README_V8.md)。
