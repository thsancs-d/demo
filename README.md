> **V3 更新：** 请优先阅读 [README_V3.md](README_V3.md)。水库输出前后期施工进度百分比估算，取消状态分数；V2 配准功能保留。

# 工程进度识别（房建 / 水库）

基于原 demo 的 SIFT + RANSAC + SSIM 双图差分与视觉大模型识别，新增水库工程模式。原房建默认入口保留。Python 3.10+。

## 安装

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
```

本交付包不含 `.env` 或密钥；覆盖更新时保留现有 `.env`。`.env.example` 保留网关 `https://hub.thinvent.com/v1` 和模型 `deepseek-v4-flash`。实际服务须支持 `image_url` 多模态输入及 OpenAI 兼容接口；尚未进行线上联调。不要提交 `.env` 或分享包含该文件的交付包。照片会发送至所配置的模型服务，请确认有上传权限。

## 水库一键识别

准备同一水库、相近视角的前后期照片（已包含四期安威川照片），最好同一机位、焦距和光照。先免费检查流程（不调用模型）：

```bash
python src/run_reservoir.py --before data/before.jpg --after data/after.jpg --out output/reservoir/period01 --dry-run
```

正式运行：

```bash
python src/run_reservoir.py --before data/before.jpg --after data/after.jpg --out output/reservoir/period01 --before-date 2026-08-01 --after-date 2026-09-01
```

参数：`--roi 0.1,0.2,0.8,0.6` 仅限制 CV 差分区域；`--skip-cv` 跳过配准；`--fast` 尝试关闭模型思考；`--quantities config/reservoir_quantities.json` 可选，须使用经核实的数据。建议每期使用新的输出目录，避免旧报告与新运行混淆。若配准失败或内点数<12、内点率<50%、重叠率<50%，不传差分图给模型；这只是示例质量门槛，不代表精确配准。模型始终使用原始前后照片。热力图在前期图坐标系，红/橙表示较大变化。

也可直接使用原入口：

```bash
python src/vlm_report.py --project-type reservoir --before data/before.jpg --after data/after.jpg --out output/reservoir/period01
python src/vlm_report.py --before data/building_before.jpg --after data/building_after.jpg --out output/building/period01
```

原 `run_compare.py`、`batch_validate.sh` 仍在；后者依赖原项目外部房建样本和 Windows 虚拟环境路径，不是水库批处理入口。

## 输出

- `cv_quality.json`：配准是否足以传差分图及指标（仅一键入口）。
- `cv/`：原图、配准图、并排图、重叠掩码、热力图、变化框、网格和 `result.json`（配准成功时）。
- `report.md`：施工工序、影像估算百分比、证据、新增变化、风险、工程量进度（如有）。
- `vlm_raw.json`：原始解析响应 `raw_vlm`、标准化 `vlm`、`meta` 和 `progress`（水库 V3 使用新的进度字段，旧房建字段保留）。

多期汇总：每期放在同一工程专属目录下，使用真实 ISO 日期；不要混合不同水库。

```bash
python src/summarize.py output/reservoir --project-type reservoir
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

```bash
python -m unittest discover -s tests -v
```

测试使用合成纹理图片及模拟 JSON；未使用真实水库照片或真实 API。CV 的单应矩阵无法保证三维地形的严格对应，建议固定机位或先用正射影像配准；需要真实工程量时结合测量、设计资料及监理记录。


## 真实水库测试样本

参见 [data/README.md](data/README.md)，运行 `python src/download_samples.py` 自动下载。


## 安威川四期数据
见 `datasets/aigawa/README.md`。运行 `python3.12 src/run_aigawa.py`；仅CV用 `--cv-only`；相邻三期用 `--all`。
