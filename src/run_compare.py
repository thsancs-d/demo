"""
用法：
    python src/run_compare.py --before 前期.jpg --after 后期.jpg --out output/xxx
    python src/run_compare.py --before a.jpg --after b.jpg --out output/x \
        --roi 0.05,0.0,0.55,0.85 --detect-new-edges

参数说明：
    --max-width 2000      长边超过此值等比缩小（0 = 不缩放）
    --roi x,y,w,h         只比对这块区域，用相对比例（0~1）。强烈建议对建筑主体开
    --detect-new-edges    额外检测"后期新增的结构边缘"（楼板/柱/墙）
    --ssim-win N          SSIM 窗口，默认按图宽自适应；调大更稳但定位更粗
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cpm_core import compare_photos  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="施工进度双图差分")
    ap.add_argument("--before", required=True, help="前期照片")
    ap.add_argument("--after", required=True, help="后期照片")
    ap.add_argument("--out", default="output/result", help="输出目录")
    ap.add_argument("--max-width", type=int, default=2000)
    ap.add_argument("--keep-ratio", type=float, default=0.15)
    ap.add_argument("--min-area-ratio", type=float, default=0.0015)
    ap.add_argument("--grid-cell", type=int, default=96)
    ap.add_argument("--cell-thresh", type=float, default=0.25)
    ap.add_argument("--ssim-win", type=int, default=0)
    ap.add_argument("--roi", default=None, help="相对比例 x,y,w,h")
    ap.add_argument("--detect-new-edges", action="store_true")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    t0 = time.time()
    try:
        r = compare_photos(
            args.before, args.after, args.out,
            max_width=args.max_width, keep_ratio=args.keep_ratio,
            min_area_ratio=args.min_area_ratio, grid_cell=args.grid_cell,
            cell_thresh=args.cell_thresh, ssim_win=args.ssim_win,
            roi=args.roi, detect_new_edges=args.detect_new_edges,
            tag=args.tag,
        )
    except Exception as e:                              # noqa: BLE001
        print(f"\n[失败] {e}")
        sys.exit(1)

    s = r["stats"]
    print("\n" + "=" * 64)
    print(" 对齐 + 差分完成")
    print("=" * 64)
    print(f"  图片尺寸        {s['before_size']} / {s['after_size']}")
    print(f"  SIFT 关键点     {s['ref_keypoints']} / {s['mov_keypoints']}")
    print(f"  匹配 -> 内点    {s['raw_matches']} -> {s['kept_matches']} -> "
          f"{s['ransac_inliers']}  (内点率 {s['inlier_ratio']:.1%})")
    print(f"  重叠区占比      {s['overlap_ratio']:.1%}")
    print(f"  比对范围        {'ROI ' + str(s['roi']) if s['roi'] else '全图'}")
    print(f"  平均 SSIM       {s['mean_ssim']:.4f}   (1 = 没变化)")
    print(f"  显著差异像素    {s['changed_pixel_ratio']:.2%}")
    print(f"  差异区域        {s['changed_regions']} 个 / 变化网格 "
          f"{s['changed_cells']} 个")
    if s["new_edge_ratio"] is not None:
        print(f"  新增结构边缘    {s['new_edge_ratio']:.2%}")
    print("-" * 64)
    for k, v in r["outputs"].items():
        print(f"  {k:16s} {v}")
    print(f"  {'json':16s} {os.path.join(args.out, 'result.json')}")
    print(f"\n  耗时 {time.time() - t0:.1f}s")
    if r["regions"]:
        print("\n  最大的 5 个变化区域:")
        for reg in r["regions"][:5]:
            print(f"    bbox={reg['bbox']}  area={reg['area_px']}px  "
                  f"ssim={reg['mean_ssim']}  填充率={reg['fill_ratio']}")
    print()


if __name__ == "__main__":
    main()
