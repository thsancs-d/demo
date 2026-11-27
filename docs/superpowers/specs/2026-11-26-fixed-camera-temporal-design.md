# 固定镜头时序识别设计

用户只有同一镜头不同时间的照片。本轮把目标从“单张照片估算整个分项百分比”扩展为“同一画面区域的可审计变化与阶段状态”。

## 方案与取舍

方案一是继续要求完整计划范围和工程百分比，结果会在宽景固定镜头上大量拒答；方案二是用差分像素直接换算工程量，容易把光照、季节、机械和土堆变化当施工量；方案三是固定镜头时序模式，要求同一坐标系的证据框、变化方向、变化类型和两期图片编号，同时保留百分比的严格条件。本轮选择方案三，因为它利用现有数据真正稳定的属性（同一观察方向和可比较区域），不虚构工程量。

## 行为

- 新增 `--fixed-camera`，使用 `v9-fixed-camera-temporal` 提示词和独立监测模式；旧 V7/V8 历史与默认入口不变。
- 模型先比较上一期和本期同一坐标区域，再输出 `temporal_changes`。每条变化包含 `stage_id`、`direction`（advanced/unchanged/removed/unclear）、`change_type`（new_work/expanded/completed_surface/temporary_change/unknown）、`evidence_image_numbers`、当前图归一化框、`where`、`what`、`confidence`、`visibility` 和 `basis=same_region_comparison`。
- 固定镜头可接受局部范围（partial），但必须有两期图片编号、非空框、可见证据和 same_region_comparison；低置信度、不在本期/上期、越界框、隐蔽工程声称或只凭像素变化的事件会被拒绝。
- `temporal_changes` 记录在每期 `progress.json` / `history.json` / `latest_report.md`，原始模型响应仍保留。第一期没有上一期时为空。
- 绝对百分比仍按 V8 证据条件过滤；固定镜头模式不按变化框面积、SSIM 像素比例或方向数量生成全工程百分比。报告明确区分“时序变化”和“完成率”。
- 旧历史刷新按其保存的版本和算法；固定镜头模式的 live/offline 历史只能在相同模式目录继续追加。

## 评估

没有工程量真值时，评估事件的方向和部位是否符合人工复核；不输出伪造 MAE。若以后提供标注，可按日期、stage_id、direction 和 evidence box 做事件精确率/召回率，并把未确认事件计为 abstention。

## 边界

固定镜头不等于严格像素配准；镜头变焦、裁切、云雾、季节、植被、水位和机械位置变化仍需列为风险。该模式不判断灌浆、压实、隐蔽工程、工程量体积或验收。
