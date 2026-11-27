# 四期离线模拟响应

> 此目录保留旧 V7 响应，用于兼容性测试；缺少 V8 要求的结构化本期证据，在当前默认流程中其百分比会被筛除。当前离线演示请使用 [aigawa_responses_v8](../aigawa_responses_v8/README.md) 和独立目录 `output/aigawa_v8_offline_demo`。下文命令保留供旧响应检查，不代表能重现 V7 默认算法。

这些 JSON 是人工编写的测试输入，不是模型对水库照片的识别结果，也不代表实际施工进度。每个响应都在证据、风险和摘要中保留模拟标记。

四期各分项统一设为 20%、45%、40%、80%，范围为该值上下各 10 个百分点。第三期刻意回落，用来验证累计进度允许估算修正。该统一取值仅便于独立核算加权结果，不是工程估算方法。

在项目根目录执行：

```bash
.venv/bin/python src/run_aigawa.py --all --responses tests/fixtures/aigawa_responses --out output/aigawa_offline_demo
```

程序运行真实图片配准，使用此目录的 JSON 替代模型请求，输出均标注 `offline_test`。不要将此输出目录用于正式识别。
