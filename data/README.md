# 鵜川大坝测试影像（真实工程公开资料）

前期：2020年4月，下游上空定点航拍。
https://www.pref.niigata.lg.jp/uploaded/image/146468.jpg
来源：https://www.pref.niigata.lg.jp/site/kashiwazaki-seibi/r-2-4kouzinoyousu.html

后期：2020年7月，下游上空定点航拍。
https://www.pref.niigata.lg.jp/uploaded/image/153976.jpg
来源：https://www.pref.niigata.lg.jp/site/kashiwazaki-seibi/r-2-7kouzinoyousu.html

原图大小、构图和季节不同，配准效果需实际验证。照片不能作为真实工程量或验收结论。版权及使用条件以新潟县政府网站为准。

在项目根目录执行：

```bash
pip install -r requirements.txt
python src/download_samples.py
python src/run_reservoir.py --before data/before.jpg --after data/after.jpg --out output/reservoir --dry-run
python src/run_reservoir.py --before data/before.jpg --after data/after.jpg --out output/reservoir
```

若自动下载失败，请从上面的原图链接分别另存为 data/before.jpg 和 data/after.jpg。
本版本包含用户上传的两张实际照片，无需重新下载。自动配准未达到几何质量门槛，原图识别已由用户在本地跑通。密钥不随包分发。
