# V7 快速开始

完整项目含四期施工照片。更新原项目时保留 `.env` 和 `output/`；本包不含 API 密钥。详细说明见 README_V7.md。

独立目录逐期测试（不覆盖旧结果）：

```bash
python3.12 src/run_aigawa.py --new-image datasets/aigawa/images/2019-06.png --date 2019-06 --out output/aigawa_v7
python3.12 src/run_aigawa.py --new-image datasets/aigawa/images/2020-04.png --date 2020-04 --out output/aigawa_v7
python3.12 src/run_aigawa.py --new-image datasets/aigawa/images/2021-01.png --date 2021-01 --out output/aigawa_v7
python3.12 src/run_aigawa.py --new-image datasets/aigawa/images/2022-02.png --date 2022-02 --out output/aigawa_v7
open output/aigawa_v7/latest_progress.png
```

也可使用 `--all --out output/aigawa_v7`。每期均保存请求清单；使用相同输出目录以继承历史。
