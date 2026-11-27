# Recognition Accuracy Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; implement inline and perform one independent final review.

**Goal:** 为新增累计识别增加可审计证据约束，并建立不会混入模拟数据的准确率评估。

**Architecture:** `recognition_quality.py` 负责 V8 提示词、历史去数值与证据筛选；`progress_tracker.py` 负责版本化汇总和报告；`evaluate.py` 扩展累计历史评估而保留旧函数。

**Tech Stack:** 现有 Python 3.12/OpenCV/unittest，无新增依赖。

**Spec:** `docs/superpowers/specs/2026-11-26-recognition-accuracy-design.md`

## Global Constraints

- 不调用线上模型、不读取 .env、不覆盖旧输出。
- 旧 V5/V6/V7 重新刷新保留原计算口径。
- 证据筛选阈值 0.7 是工程默认值，不是标定准确率。
- 当前目录不是 Git 仓库，保留本地修改，执行进度记入本文件。

## Review Focus

- 旧历史与新增 V8 混合时，不能把旧外推伪装为当前直接观察。
- 布尔值、NaN、非法框/图片编号、重复分项与缺失字段不能进入数字汇总。
- 无真值、仅模拟数据、重复标签及照片散列不符不能产生准确率。
- 低预测覆盖率必须与误差指标一起展示，不能只展示答对比例。
- 数值历史去除不能导致请求清单与实际提示不一致。

## Tasks

- [x] 1. 写失败测试复现低置信度、缺失/错误证据定位、局部范围、伪精确区间进入累计汇总；实现 `filter_observations(raw, current_image_number)`，返回保留原始结构的副本及拒绝原因；仅新 V8 使用。验证命令：`.venv/bin/python -m unittest discover -s tests -p test_recognition_quality.py -v`。
- [x] 2. 测试旧历史算法、V8 无均值外推、版本变化提示与数值历史去除；接入新提示词、quality_review 记录和报告。新增 V8 夹具及真实 CLI 集成验证。运行现有完整测试防止破坏旧双图和累计入口。
- [x] 3. 为累计评估先写失败测试：live 与已核实标签产生手算 MAE；模拟、缺标签、历史沿用、非法值、重复记录和哈希不匹配不产生假成绩；扩展 `evaluate_tracking(labels,state,tolerance_pp=10)`，新增 `--history` CLI。模板真值保持 null/verified=false。
- [x] 4. 完成新旧测试、编译、独立离线输出、图表检查、文档与审查。记录未做线上准确率验证。

## Execution ledger

- Ruling: 用户要求进一步优化，按现有工程中的累计进度口径直接实现局部可逆改进；方案与阈值是实现者选择，不代表用户已指定模型或标定指标。
- Pre-flight: V8 使用新版本常量；旧 `PROMPT_VERSION`/V7 函数保留用于旧历史；新增提示与实际清单使用同一证据历史函数。
- Task 1–2: complete；失败测试复现后实现，10 项证据/集成测试通过；旧函数和历史算法保留，新请求统一使用 V8；四期工作流使用明确的 V8 模拟夹具。
- Task 3: complete；累计 CLI 与指标先失败后通过，10 项评估测试通过；真实标签模板四期均保持空真值、未核实，照片哈希核对一致。
- Task 4: complete；最终 80/80 测试（7.530秒），compileall 通过；两组独立离线输出、旧 V7 副本刷新字节一致、模拟历史不计分均验证；全未知图表经目视检查，边缘行显示已修复。
- Final review: 独立审查无核心正确性/回归问题；18 项独立测试通过。文档由独立子任务更新，主任务已逐项复核。
- Final: minor (deferred): NaN 等非标准模型数值会在严格 JSON 归档时中止该期；安全拒绝，不写入无效进度，但未提供部分恢复。
- Final: minor (deferred): 手工损坏历史的 stages:null 在评估时产生 TypeError，错误提示尚不友好，不产生假成绩。
- 实测记录：`validation/accuracy_v8_2026-11-26.md`。真实模型准确率尚未测量，不能由规则测试或模拟结果推断提升。
