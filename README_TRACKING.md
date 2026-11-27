# V4 累计施工进度监测

> 本文保留 V4 的历史口径。当前入口、离线示例和验证结果请使用 [START_HERE.md](START_HERE.md) 与 [README_V7.md](README_V7.md)。

直接覆盖 V2 安威川或 V3 项目；保留 `.env`、原有照片和数据。不包含密钥。

```sh
python3.12 src/run_aigawa.py --all
```

四期依次作为新增照片导入，首期独立估算基准，不默认归零。每期传入基准图、上一期原图（若与基准相同不重复）、当前原图、历次分项记录及可靠的上一期差分图（可选）。已成功日期不会重复调用；中途失败时重跑可从失败日期继续。不同日期不得使用同一文件。使用同一监测目录时保持工程背景不变。

后续只新增一张图即可：

```sh
python3.12 src/run_aigawa.py --new-image data/new.jpg --date 2022-03-01
```

日期需晚于最新一期。默认输出 `output/aigawa_tracking/`，可用 `--out` 指定独立目录。不同工程请同时提供 `--context config/project_context.json`，只包含 project_name、dam_type、scope_note；不放进度真值。`--skip-cv` 可跳过 CV；`--fast` 尝试关闭思考。旧 `--all --cv-only`、`--all --dry-run` 保留原两图诊断行为，不写累计进度。

## 输出

- `history.json`：累计记录及每期源图哈希。
- `observations/日期/`：独立保存本期图片、提示词、配准诊断、模型原始结果与分项进度。
- `latest_progress.png`：最新原图、分项完成百分比、总工程趋势及不确定区间。
- `latest_progress.json` / `latest_report.md`：最新工程进度及证据。

## 总工程进度口径

固定分项权重为示例权重。所有分项有合理估计时，`total_estimate_pct = sum(w_i * p_i)/sum(w_i)`。不全时，输出全工程可能区间：未知或仅有历史证据的分项采用0–100%范围。`total_reference_pct` 为该区间中点，仅用于情景参考，不是识别结论；完全没有当前证据时不生成中点参考。历史观察可以保留并注明证据日期，不能冒充本期观测。没有强制单调或按变化面积计分。实际工程量与影像估计分开：`--quantities-dir config/period_quantities` 读取与当前日期同名的 JSON，格式沿用 config 中工程量样例（完整工序、权重和计划/实际工程量）。

## 测试

`python3.12 -m unittest discover -s tests -q`。本次31项测试通过；四期离线端到端流程通过，CV相邻三组中两组通过；续跑跳过四个已完成日期。离线使用模拟模型响应，非实际百分比。API网关在本次环境DNS解析失败，线上多图识别未验证。不要把模拟数据或区间中点作为实际工程完成率。
