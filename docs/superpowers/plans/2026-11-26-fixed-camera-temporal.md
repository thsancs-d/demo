# Fixed Camera Temporal Recognition Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在只有同一镜头不同时间照片时，输出可审计的区域变化和阶段状态，减少对绝对工程百分比的错误依赖。

**Architecture:** 在 `recognition_quality.py` 增加固定镜头提示词与时序事件校验；`progress_tracker.py` 增加 `--fixed-camera` 模式、版本化状态、事件报告；`run_aigawa.py` 透传入口。百分比筛选保持 V8 规则，事件单独记录。

**Tech Stack:** 现有 Python 3.12、OpenCV、unittest，无新增依赖。

**Spec:** `docs/superpowers/specs/2026-11-26-fixed-camera-temporal-design.md`

## Global Constraints

- 同一目录不能混合默认 V8 与固定镜头模式。
- 不把变化框面积、SSIM 或事件数量换算成工程量百分比。
- 第一张照片无上一期，temporal_changes 必须为空。
- 不读取 .env 以外的真值，不调用外部 API 进行测试夹具验证。
- 旧历史刷新保持原版本算法。

## Review Focus

- 首期、第二期及三期以上图片编号必须对应角色清单中的上一期和本期。
- 事件重复分项、无效框、不可见证据、非法方向/类型和 NaN 不能进入 history.json。
- 固定镜头模式不能因为 `temporal_changes` 生成总工程百分比。
- 默认 V8 和固定镜头模式不能混写同一目录或改变旧历史。
- 模型只描述临时机械/植被变化时，报告必须保留类型和风险，不能写成完成施工。

## Tasks

- [x] 1. 为 `filter_temporal_changes(raw, previous_image_number, current_image_number)` 写失败测试并实现；验证合法局部变化、错误图号/框/方向/重复项/低置信度及首期为空。
- [x] 2. 为固定镜头提示词、CLI 参数和模式隔离写失败测试；接入 `v9-fixed-camera-temporal`、`temporal_changes` 保存和报告，保留 V8 百分比筛选。
- [x] 3. 添加两期离线固定镜头夹具和真实文件工作流测试；确认第一期为空、第二期事件可审计、百分比仍不由事件生成、刷新和断点跳过保持一致。
- [x] 4. 用鵜川官方定点照片做一次中性上下文线上对照；运行完整测试、编译检查、图表/报告检查，记录事件输出和未验证范围。

## Execution ledger

- Ruling: 用户明确只有同一镜头不同时间照片，选择时序事件模式而不是继续强迫完整工程百分比；绝对百分比仍严格保留。
- Pre-flight: 现有 V8 过滤器和 history 结构可复用；新增字段只附加于固定镜头版本，不迁移或改写旧输出。
- Ruling: 首期历史图像同时作为上一期图像，时序图号按提示中的角色列表计算；原实现只认独立 `previous` 角色会让第二期候选事件全部被筛掉。成本若判断错误，事件图号可能与模型输入不一致；回归测试核对了首个续期的实际图号。
- Ruling: V9 刷新沿用 V8 的严格本期百分比规则；否则刷新可能把部分覆盖扩展成总进度。成本若判断错误，旧版算法不适用于 V9；测试验证 V9 部分缺项时总进度保持未知。
- Ruling: 当 V9 响应将自然语言观察放在 `observation`、将图号数组误放在 `evidence` 时，保留原始响应，并将文字用于展示阶段证据；不据此接受数值估算。成本若判断错误，阶段文字可能不是模型想表达的证据字段；原始 JSON 仍完整可查，且百分比筛选仍因缺少结构化定位框而拒绝估值。
- Ruling: `temporary_change` 或 `unknown` 事件不能标记为 `advanced`。成本若判断错误，确实包含施工推进的模糊事件会被拒绝；这类事件会报告具体冲突原因供人工复核。
- Verification: 鵜川 2020-04/2020-07 中性上下文实图推理提出3条事件；用同一份线上原始响应离线重放后，保留2条施工变化、拒绝1条方向冲突的临时设施变化；总进度未知、百分比覆盖率0%。这验证了时序事件流程和筛选行为，没有逐事件人工标签，不能计算准确率。
- Verification: `.venv/bin/python -m unittest discover -s tests -v` 88/88通过；`compileall`通过；四份文档的本地链接、代码围栏及两个 JSON 结果文件检查通过；复核了固定点照片并排图和重放报告。
