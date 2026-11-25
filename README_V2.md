# 水库建设进度识别 V2 — 实际影像配准优化

## Mac 使用（在项目目录）

已有项目：可直接将本版本 src/、tests/ 和 README_V2.md 覆盖/复制到原项目，原 `.env` 保留不变。若解压到新目录，需从原目录私下复制 `.env`（不要公开或提交）。`.env.example` 保留网关及模型名称，但不含密钥。本版本已包含两张照片，无需下载。

```bash
python3.12 -m pip install -r requirements.txt
python3.12 src/run_reservoir.py --before data/before.jpg --after data/after.jpg --out output/reservoir_v2 --cv-only
python3.12 src/run_reservoir.py --before data/before.jpg --after data/after.jpg --out output/reservoir_v2
open output/reservoir_v2
```

`--cv-only` 不调用模型。`--dry-run` 检查模型提示词和图像编码、不调用 API。`--fast` 尝试快速模式（由网关实际支持情况决定）。工程量仍需通过 `--quantities` 提供；视觉状态评分不等于实际完成率。

## 本次真实照片诊断

用户上传的旧结果：前图640×360，后图640×479；115个筛选匹配中仅6个内点（5.22%），虽重叠率99.47%，变换不可信。

新版以 SIFT、RootSIFT、AKAZE 三类描述子，结合双向 KNN 比率筛选（0.75/0.85/0.90），分别估计仿射及单应变换，共18种组合。检查至少12个内点、50%内点率、双图6%凸包覆盖、双向误差、投影几何、50%重叠。阈值为保守启发式，非工程测量标准。

实际照片在本次 OpenCV 4.13 环境中18种组合均被拒绝；最大内点数5。故不生成新差分图、不向 VLM 传递不可靠热力图；仍使用原始照片。详细结果见 `validation/real_pair_cv_quality.json`。每次运行使用独立 CV 子目录，避免上一次的图被误用。

配准成功后，重叠区内做直方图匹配，并排除 SSIM 窗口跨越变换边界的像素。差分仍可能含植被、光照和三维视差，不等于施工变化。当前未实现深度学习分割、三维正射纠正、无人机摄影测量或自动稳定地物分割。

## 人工控制点辅助（可选，不保证这组照片通过）

```bash
python3.12 src/pick_control_points.py --before data/before.jpg --after data/after.jpg --out config/control_points.json
python3.12 src/run_reservoir.py --before data/before.jpg --after data/after.jpg --control-points config/control_points.json --out output/reservoir_manual --cv-only
```

先在前图按顺序选14个稳定同名点，再在后图按相同顺序选择。默认前10个用于拟合、后4个为独立检查点。尽量选分散、未发生移动的固定混凝土转角、道路交叉口等，避免植被、水面、设备、土堆、施工新增部分。检查点必须独立；至少8个拟合内点、检查点误差不超过6像素、检查点覆盖至少6%。仅当几何指标通过才生成差分。若无足够稳定点或地形视差大，不应强行配准。交互选点需支持 matplotlib 的桌面 GUI，当前无桌面环境，未验证 Mac GUI 交互。

## 测试

```bash
python3.12 -m unittest discover -s tests -v
```

15 项测试在当前环境通过。包括原有10项测试、自动匹配正例、随机无关照片拒绝、退化变换拒绝、人工独立检查点、真实照片降级。OpenCV 版本与硬件差异可能影响候选指标。没有再次使用用户的 API 密钥发起在线调用，也没有重新生成模型报告。
