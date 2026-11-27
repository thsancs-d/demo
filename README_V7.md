# V7 累计施工进度：历史证据与请求审计

> 本文保留 V7 历史行为及当时的验证记录。当前新观察默认使用 V8，见 [README_V8.md](README_V8.md) 与 [START_HERE.md](START_HERE.md)。刷新 V7 历史仍使用原算法；使用 V8 重新识别须新建输出目录。下文旧模拟响应缺少 V8 的结构化证据，不再用于当前版本的入门演示。

## 使用
保留原 `.env` 和 `output/`。累计入口为 `src/run_aigawa.py --all` / `--new-image`；无参数时保留旧双图行为。以下命令使用项目虚拟环境。旧 V6 历史继续使用分项加权算法，V5 及以前保留旧算法；不会因版本升级而改写旧进度方法。

- `.venv/bin/python src/run_aigawa.py --all --out output/aigawa_v7`：独立目录完整识别（首次运行四次 API 调用）。
- `.venv/bin/python src/run_aigawa.py --new-image data/new.jpg --date 2022-03-01 --out output/aigawa_v7`：同一目录追加一期（日期必须晚于已有最新期）。
- `.venv/bin/python src/run_aigawa.py --refresh-only --out output/aigawa_v7`：从已有历史生成报表，不调用 API；离线模拟历史同样支持，无需原响应文件。
- `.venv/bin/python src/run_aigawa.py --all --responses tests/fixtures/aigawa_responses --out output/aigawa_offline_demo`：使用人工模拟响应验证流程，不调用 API。该目录不可混入正式结果。
- `.venv/bin/python src/run_aigawa.py --help`：查看累计监测与双图诊断参数，支持 `--new-image=路径` 写法。

## 输入和输出
首期发送原图，第二期去重发送基准兼上期图及本期图，其后发送基准、上期、本期原图。CV 通过才额外附加 SSIM 差分图。图像前的标签、提示词中的编号和请求清单均使用同一角色列表。历史 JSON 包含各期总进度、区间、覆盖率、方法、分项证据与推断、外推记录；历史不是当前答案，不强制单调，不提供未来标签。旧照片归档的 SHA-256 校验可阻止错误替换。

每期 `observations/<日期>/prompt.txt` 保存实际提示文本，`request_manifest.json` 保存图片编号、角色、路径、散列和历史输入（不含 API 密钥或 base64 图像）；线上 `model_response.txt` 保存解析前响应文本。`history.json`、`latest_progress.json` 与最新报告含基准进度、上期进度和两种差值。比较的是估算变化，不是实测新增量。不同估算方法之间的差值标记为方法变化。

权重仍为示例权重。直接观察、推断和外推分开记录；覆盖低于 70% 时仍可能无单值。无法从照片验证隐蔽工程或真实工程量。生成式修复图片不用于默认识别。

## 验证
2026-11-26：60 项单元/集成测试通过；编译与依赖兼容性检查通过。四期真实裁切照片配合离线模拟响应验证了请求清单、CV 配准、累计输出、图表、断点跳过及刷新。相邻三组中两组通过几何检查，一组安全回退到原图；原图归档被修改时追加操作会报错并保留已有历史。

同一配准调用中的 SIFT / RootSIFT 复用原始特征，保持质量门槛不变。三组照片合计耗时的九次交替测量中位数由 0.364 秒降至 0.263 秒，减少约 28%；变换矩阵与诊断一致。这是本机小尺寸样本的结果，不代表线上请求或任意图片都能获得同等提升。详细数据见 [性能记录](validation/optimization_2026-11-26_benchmark.json)。

本轮没有调用线上模型，未验证识别准确率。日志和离线图表中的百分比均为人工模拟值，不是实测或 AI 识别结果。测试命令与演示步骤见 [START_HERE.md](START_HERE.md)，完整结果见 [验证记录](validation/optimization_2026-11-26.md)。
