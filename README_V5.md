# V5：总工程施工进度单值及离线刷新

## 已经完成 V4 四期识别的用户

在原 demo-main 目录覆盖本更新包的 src 文件（保留 .env、datasets 和 output）。

```bash
python3.12 src/run_aigawa.py --refresh-only
open output/aigawa_tracking/latest_progress.png
```

离线刷新读取已有 history.json 的分项百分比，不调用 API、不重新配准。首次刷新保留 history.v4.backup.json。重新生成 latest_report.md、latest_progress.json、latest_progress.png 和 history.json 的汇总字段。原始响应和各期原始记录不变。

继续增加照片仍使用 --new-image ... --date ...；首次运行可使用 --all。

## 总进度算法

- 全部工程分项有当前估算：固定权重加权。
- 本期可估算权重达到 70%：优先使用新提示词返回的总体估算（必须有依据、未知项假设，且位于分项可能区间内）；若无合格总体估算（包括 V4 历史），按可见分项的加权平均完成率外推全部工程，即假设未观测部分平均完成率相同。这是未验证的外推，不是识别出的隐蔽工程量，也不是区间中点。
- 覆盖不足 70% 时不强行输出总工程单值。70% 是示例业务阈值，不是经校准的准确率保证。
- 继续保留未知工程的完整不确定范围和示例权重说明。历史趋势可能混合不同估算方式，变化不是实测工程量变化。
- JSON 新增 overall.project_progress_pct、project_progress_method、project_progress_basis、assumed_weight_pct、previous_project_progress_pct、project_progress_delta_pp；原 total_estimate_pct 严格口径保留。
- 已有四期真实响应仅在用户电脑上；本包不含这些响应。测试数据是模拟响应，不代表工程真实完成率。
