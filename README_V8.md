# V8 累计监测：证据筛选与真实误差评估

V8 为新累计观察增加本期证据要求，并提供核实标签的评估入口。目标是减少缺乏依据的百分比，让无法估算和拒绝原因可以检查。本轮没有调用线上模型，也没有测得真实识别准确率；规则检查通过不证明模型已认对部位或比例。

## 运行与旧历史

以下命令在项目根目录执行；Windows 将 `.venv/bin/python` 替换为 `.venv\Scripts\python.exe`。保留现有 `.env` 和历史输出。先用模拟响应验证流程：

```bash
.venv/bin/python src/run_aigawa.py --all --responses tests/fixtures/aigawa_responses_v8 --out output/aigawa_v8_offline_demo
.venv/bin/python src/run_aigawa.py --refresh-only --out output/aigawa_v8_offline_demo
```

照片为真实裁切图，响应中的百分比、证据框、可见性及范围依据均为人工测试输入。图表和报告标注模拟数据，评估程序不为其计分。

配置模型服务后，使用新的正式输出目录；首次完整运行四期会发起四次模型请求：

```bash
.venv/bin/python src/run_aigawa.py --all --out output/aigawa_v8
.venv/bin/python src/run_aigawa.py --new-image data/new.jpg --date 2022-03-01 --out output/aigawa_v8
.venv/bin/python src/run_aigawa.py --refresh-only --out output/aigawa_v8
```

后续追加与刷新使用同一个 `--out`，新照片日期须晚于已有最新期。`--all` 会跳过已完成日期，所以要用 V8 重新识别旧照片，必须选择尚未使用的输出目录。`--refresh-only` 仅从已有历史生成结果，V5/V6/V7 记录维持各自原算法。旧目录中新增观察使用 V8，跨版本差值会提示口径变化，即使两期的汇总方法名相同也会提示；差值仍只是估算变化。

无参数运行 `src/run_aigawa.py` 保留旧双图比较；`--all --cv-only` 和 `--all --dry-run` 为相邻三组诊断。这些入口不等于 V8 累计识别。

## 本期百分比的采纳条件

新观察的 `prompt_version` 为 `v8-grounded-evidence`。每个分项仍需合法状态、证据文本、百分比和区间，以及完整范围依据 `scope_basis`、完成比例依据 `completed_basis`。额外要求如下：

| 字段 | 要求 |
|---|---|
| `observation.image_number` | 对应请求清单中的本期原图，不能使用历史图或差分图编号 |
| `observation.bbox_xyxy` | `[左, 上, 右, 下]` 归一化坐标，每项在 0–1 内，宽高均大于 0 |
| `observation.visibility` | `clear`，证据清晰可见 |
| `observation.scope` | `full`，完整计划分项范围可辨认 |
| `observation.basis` | `visible_extent`，比例来自可解释的施工范围 |
| `confidence` | 至少 0.7；这是未标定的筛选阈值，不是正确概率或 70% 准确率 |
| 施工中分项的 `range_pct` | 必须有宽度，百分比须在区间内 |

证据不足时保留可见事实，百分比为空；缺项、重复分项、图号错误、越界或空框、遮挡、范围不明、低置信度、无效估算均会留下拒绝原因。高度比例、框面积或差分像素不能冒充工程完成率或填筑体积。隐蔽或画外工序不能仅因看不见就判断未开工或已完成。

这些检查只能筛选输出是否满足证据协议。模型仍可能给错证据框、误认坝体与泄槽，或错误声称范围完整；它们不能替代人工复核，也不能验证隐蔽工程、压实度或验收情况。

## 总进度与历史证据

V8 不采纳模型推断来补齐本期直接观察，也不按已知分项均值外推未知分项。只有全部分项通过本期直接证据筛选，才按示例权重给出总工程单值。否则 `project_progress_pct` 为空，报告保留：

- `assessed_only_pct`：已估算分项内部的加权完成率，不是全工程完成率；没有可估算分项时也为空。
- `current_coverage_pct`：本期直接估算覆盖的工程权重，不是识别准确率。
- `total_possible_range_pct`：全工程可能区间，未知或仅有历史记录的分项按 0–100% 不确定范围计入。

本期不可见且状态为 `unclear` 时可保留标明来源日期的历史观察，但它不计入本期直接覆盖。总进度因此可能比旧版本更常为空，区间也可能更宽。应结合预测覆盖率判断真实效果，不能仅因拒绝了更多输出就认定精度更高。

新的历史提示只选取分项标识、状态、证据、观察日期与来源，省略旧的结构化百分比、区间及总进度。完整数值历史仍保存在 `history.json`。证据文字本身可能含数字，这项调整只是减轻旧估算的锚定影响，不能保证完全消除锚定。历史不作为本期真值，不强制进度单调增长。

输入仍使用原始照片，CV 质量门槛和模型接口不变。首期发送本期原图；第二期合并基准与上期角色；此后发送基准、上期、本期原图。CV 通过时才附加差分图，差分只提示可能变化区域，不能代替本期原图证据。生成式修复图不用于默认识别。

## 查看输出和拒绝原因

- `history.json`、`latest_progress.json`、每期 `progress.json`：观察、汇总、版本和 `quality_review`。后者记录筛选阈值、是否标定、采纳和拒绝的数量及逐项原因。
- `latest_report.md`：进度口径、已估算分项、区间和中文“证据检查”说明；`latest_progress.png` 为最新图表。
- `observations/<日期>/raw_model.json`：筛选前的原始解析响应，未采纳的百分比和推断仍可回看；线上运行另存 `model_response.txt`。
- 每期 `prompt.txt`、`request_manifest.json`、原图和 SHA-256：用于核对实际提示、图号、角色、历史输入和照片。原图被替换后追加会报错。

## 用核实标签评估误差

先复制 `config/aigawa_accuracy_labels.example.json` 为自己的 `config/aigawa_accuracy_labels.json`。模板预填四期日期、坝体分项和默认照片的真实 SHA-256；`percent=null`、`verified=false`、空来源表示尚无核实真值。可添加其他分项，但每个日期与分项组合须唯一。

| 标签字段 | 填写要求 |
|---|---|
| `project` | 与历史中的 `context.project_name` 完全一致 |
| `date`、`stage_id` | 对应观察日期及合法水库分项；日期用 `YYYY-MM` 或 `YYYY-MM-DD` |
| `metric` | `visual_completion_pct`，与识别采用相同的影像分项完成率口径 |
| `percent` | 经人工核实的 0–100 数值，不得从模型或模拟响应复制为真值 |
| `verified` | 仅在完成核实后设为 `true` |
| `source`、`scope_basis` | 非空来源与范围说明；标注者负责确认来源真实性及与识别口径一致 |
| `image_sha256` | 可选，建议保留；填写时须与对应观察原图一致，换图后须重新核对 |

运行：

```bash
.venv/bin/python src/evaluate.py --history output/aigawa_v8/history.json --labels config/aigawa_accuracy_labels.json --tolerance-pp 10
```

只对同一工程的 `live` 历史计分，标签须经核实，预测须来自相同日期、相同分项的本期直接估算。历史沿用值、模拟响应、照片散列不匹配或缺失预测不会被当作有效预测。程序检查字段和匹配关系，不能自动核实标签来源或判断两段范围描述语义相同。

结果输出以下指标：

| 指标 | 含义 |
|---|---|
| `mae_pp` | 已输出预测的平均绝对误差，单位为百分点 |
| `bias_pp` | 预测减真值的平均偏差；正值表示平均偏高 |
| `within_tolerance_pct` | 已输出预测中，绝对误差不超过阈值的比例；默认阈值为 10 个百分点 |
| `interval_coverage_pct` | 已输出预测中，区间包含真值的比例 |
| `mean_interval_width_pp` | 已输出预测的平均区间宽度；须与区间覆盖率一起看 |
| `prediction_coverage_pct` | 有有效预测的核实标签数占全部合格标签数的比例 |

同时查看 `eligible_labels`、`predictions`、`abstentions` 和逐项 `comparisons`。误差指标仅针对已输出预测；预测覆盖率显示有多少合格样本未得到可计分结果。没有合格标签或有效预测时，误差指标为 `null`；模拟历史不会产生成绩。旧双图 `--reports` 入口仍保留，但不能替代这项核实标签评估。

现有 `datasets/aigawa/labels.json` 只有一个此前查得、尚未独立核实的填筑完成节点，其他月份百分比未知，不能据此宣称 V8 比旧版本更准确。需要对同一组照片、同一组核实标签比较新旧线上结果，同时报告误差、区间和预测覆盖率；影像分项完成率也不能替代实测工程量或全水库验收进度。
