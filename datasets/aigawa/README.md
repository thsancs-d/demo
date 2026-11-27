# 安威川大坝四期数据

源文件：用户上传的850×850四宫格。

- original_crops：425×425 原始四图，保留日期。
- images：425×345，统一裁掉顶部80像素，移除日期/编号；默认识别输入，无生成内容。
- enhanced：1275×1035，Lanczos 插值及轻度锐化，未恢复真实缺失信息。
- ai_restored：1254×1254，AI生成式修复，可能改变施工细节，仅供展示，不用于验证。
- labels.json：日期与历史标签。仅坝体填筑完成节点有此前查得的记录支持，本轮未独立核实，其他百分比未知；不能据此宣称识别准确率提升。

在项目根目录执行：

```bash
.venv/bin/python src/run_aigawa.py --all --cv-only
.venv/bin/python src/run_aigawa.py --all --responses tests/fixtures/aigawa_responses_v8 --out output/aigawa_v8_offline_demo
.venv/bin/python src/run_aigawa.py --all --out output/aigawa_v8
```

`--all` 将四期逐次导入累计监测；`--all --cv-only` 只诊断相邻三组。第二条命令使用人工模拟响应，包括虚构百分比和证据框，不调用模型；第三条命令使用已配置的模型服务。无参数时仍对比 2019-06 与 2022-02。后续追加或刷新保持相同 `--out`；保留原项目 `.env`。`--all` 跳过已完成日期，`--refresh-only` 不重新识别；要用 V8 重跑旧照片，请使用新的输出目录。

准确率评估需另填 [核实标签模板](../../config/aigawa_accuracy_labels.example.json)。模板中的 `percent=null`、`verified=false` 表示尚无核实真值；照片 SHA-256 对应 `images/` 中的默认裁切图。标注者须确认来源和 `visual_completion_pct` 分项范围，不能将填筑体积、整体工程进度或模拟百分比混为同一口径。评估命令与限制见 [README_V8.md](../../README_V8.md)。
