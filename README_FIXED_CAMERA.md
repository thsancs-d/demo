# 固定镜头施工时序监测

## 网页工作台

网页视觉层借鉴了 [ColorlibHQ/bootstrap-templates 的 Bedrock 模板](https://github.com/ColorlibHQ/bootstrap-templates)，该模板按 MIT License 发布。当前页面只复用其工程监测布局语言和配色，照片、接口、识别框、分项状态和任务逻辑均来自本项目。

从项目根目录启动完整前后端页面：

```bash
.venv/bin/python src/run_web.py --port 8765
```

浏览器打开 `http://127.0.0.1:8765`。首页默认展示安威川四期原始照片（2019-06、2020-04、2021-01、2022-02）、整体建设情况和 8 个坝体施工分项。点选日期可切换该期判读，点击变化卡片可定位本期照片中的证据框。上传入口支持 2–8 张同一镜头的不同日期照片，后台调用现有固定镜头识别流程并在页面显示任务进度与结果。鵜川两期固定镜头实例仍保存在 `output/ukawa_fixed_temporal_replay_20261126`。

历史实例使用已保存的模型响应，并按当前证据规则复核。新上传需要 `.env` 中配置 `DEEPSEEK_API_KEY`。当图片证据不足时，整体进度显示“证据不足”，不会把未知分项外推为完成率；可见区域变化也不会换算成工程量。

固定机位照片适合核对同一画面区域随时间出现的可见变化。系统以第一期照片建立基准，后续每期比较上一期和本期原图，并保存通过结构校验的变化事件。事件框只定位本期原图中的部位，不能换算工程量或总体进度。

## 运行

从第一期开始，每次使用 `--fixed-camera`，同一工程继续使用同一个输出目录：

```bash
.venv/bin/python src/run_aigawa.py --new-image data/2025-01.jpg --date 2025-01-01 --fixed-camera --out output/site_fixed_camera
.venv/bin/python src/run_aigawa.py --new-image data/2025-02.jpg --date 2025-02-01 --fixed-camera --out output/site_fixed_camera
.venv/bin/python src/run_aigawa.py --refresh-only --out output/site_fixed_camera
```

每次命令都会直接在终端打印 `[本期识别结果]`、各分项状态、时序变化和拒绝原因，不需要打开报告文件。报告和图表仍会同步保存到输出目录。

第一期的 `temporal_changes` 为空。之后的事件保存上一期与本期图片编号、分项、方向、变化类型、可见性、证据框和自然语言描述。每期原图、模型提示词、原始模型响应、筛选记录和最终报告都保存在输出目录中。刷新只重建报告和图表。

时序变化与 V8 的绝对分项百分比是两种输出。任何一条变化都不能自动提升总进度；除非全部分项的本期范围证据都通过 V8 规则，汇总的总进度保持未知。临时设施、车辆、植被、天气和水位变动不得描述为工程推进。模型给出的方向与置信度仍需人工核对。

该模式不能从外观确认压实、灌浆、隐蔽工程、机电调试、验收或三维工程量。镜头轻微偏转、变焦、裁切、视差、阴影和季节变化可能影响事件定位与描述。

## 鵜川坝固定视角测试

测试使用新潟县鵜川坝官方月报所列的2020年4月和7月定点照片，按下游侧上空观察方向配对运行。图片来源为[2020年4月月报](https://www.pref.niigata.lg.jp/site/kashiwazaki-seibi/r-2-4kouzinoyousu.html)和[2020年7月月报](https://www.pref.niigata.lg.jp/site/kashiwazaki-seibi/r-2-7kouzinoyousu.html)。两图属于同一固定观察序列，但不是像素级完全相同构图。

实际模型识别在2020年7月返回3条事件：坝体填筑面扩大、右侧混凝土槽局部延伸、临时设施增加。两条施工变化事件通过筛选。离线重放同一份原始模型响应时，系统拒绝了临时设施增加事件，因为它被标为 `advanced`；坝体和混凝土槽事件保留。首期无事件，两期总工程进度都为空，数值覆盖率为0%。

月报文字支持当年填筑施工正在推进这一阶段事实，但没有提供可用于事件精确率、召回率或百分比 MAE 的逐项人工标签。上述运行证明模型和时序筛选流程能给出可审查的同区域变化记录，不构成识别准确率提升的量化证明。结果、原始运行入口和离线重放分别见[实际推理记录](validation/effect_check_20261126/ukawa_fixed/live_temporal_results.json)、[重放筛选结果](validation/effect_check_20261126/ukawa_fixed/live_temporal_replay_results.json)和[测试脚本](validation/effect_check_20261126/ukawa_fixed/run_live_temporal.py)。
