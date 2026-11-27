# V8 四期离线模拟响应

本目录 JSON 是人工编写的协议测试输入。照片是真实裁切图，但响应中的百分比、证据框、可见性、完整范围及依据均为虚构测试数据，不是模型识别或人工核实的施工真值。框符合格式不表示框内确有对应工序。

四期各分项统一设为 20%、45%、40%、80%，区间为上下各 10 个百分点，置信度统一为 0.8；这些值仅便于核算，0.8 不表示准确率。第三期刻意回落，验证不强制进度单调增长。`observation.image_number` 对应各期请求中的本期原图，其他结构化字段用于验证 V8 的采纳流程。

在项目根目录执行：

```bash
.venv/bin/python src/run_aigawa.py --all --responses tests/fixtures/aigawa_responses_v8 --out output/aigawa_v8_offline_demo
.venv/bin/python src/run_aigawa.py --refresh-only --out output/aigawa_v8_offline_demo
```

程序运行真实图片配准，以本目录 JSON 替代模型请求。输出标注 `offline_test` 和“模拟数据”，不会调用线上模型，累计评估也不会为其计分。请使用独立输出目录；`--all` 会跳过已有日期，不能用于覆盖旧观察。

旧响应保留在 [aigawa_responses](../aigawa_responses/README.md) 用于兼容性测试。V8 的证据限制、真实标签要求和正式运行命令见 [README_V8.md](../../../README_V8.md)。
