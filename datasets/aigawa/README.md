# 安威川大坝四期数据

源文件：用户上传的850×850四宫格。

- original_crops：425×425 原始四图，保留日期。
- images：425×345，统一裁掉顶部80像素，移除日期/编号；默认识别输入，无生成内容。
- enhanced：1275×1035，Lanczos 插值及轻度锐化，未恢复真实缺失信息。
- ai_restored：1254×1254，AI生成式修复，可能改变施工细节，仅供展示，不用于验证。
- labels.json：日期与标签。仅坝体填筑完成节点有此前查得的记录支持，其他百分比未知。

在项目根目录执行：

```bash
python3.12 src/run_aigawa.py --cv-only
python3.12 src/run_aigawa.py
python3.12 src/run_aigawa.py --all
```

默认对比2019-06与2022-02；--all运行相邻三期。保留原项目 .env，压缩包不含密钥。
