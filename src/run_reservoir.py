"""水库两期识别：多策略配准，不可靠时仅使用原图。"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from cpm_core import compare_photos, _parse_roi
from registration import RegistrationError


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--before', required=True)
    ap.add_argument('--after', required=True)
    ap.add_argument('--out', default='output/reservoir_v2')
    ap.add_argument('--before-date', default='前期')
    ap.add_argument('--after-date', default='后期')
    ap.add_argument('--roi', help='相对坐标 x,y,w,h（仅约束 CV 差分）')
    ap.add_argument('--quantities')
    ap.add_argument('--context')
    ap.add_argument('--response-file')
    ap.add_argument('--control-points', help='人工同名控制点 JSON（含独立检查点）')
    ap.add_argument('--skip-cv', action='store_true')
    ap.add_argument('--cv-only', action='store_true', help='仅运行 CV，不调用模型')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--fast', action='store_true')
    args = ap.parse_args()
    if args.roi: _parse_roi(args.roi, 10000, 10000)
    if args.skip_cv and (args.cv_only or args.control_points): ap.error('--skip-cv 与 --cv-only / --control-points 互斥')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # Each CV run gets a new folder to prevent stale difference images being reused.
    import tempfile
    cv_dir = Path(tempfile.mkdtemp(prefix='cv_', dir=out)) if not args.skip_cv else None
    cmd = [sys.executable, str(Path(__file__).with_name('vlm_report.py')), '--project-type', 'reservoir', '--before', args.before, '--after', args.after, '--out', str(out), '--before-date', args.before_date, '--after-date', args.after_date]
    info = {'used_diff': False, 'dry_run':args.dry_run, 'eligible_diff':False, 'reason': '用户跳过 CV' if args.skip_cv else '', 'cv_dir':str(cv_dir) if cv_dir else None}
    if cv_dir is not None:
        try:
            result = compare_photos(args.before, args.after, str(cv_dir), roi=args.roi, registration='auto', control_points=args.control_points)
        except RegistrationError as exc:
            info.update(reason=str(exc), registration=exc.diagnostics)
        except RuntimeError as exc:
            info['reason'] = str(exc)
        else:
            info.update(stats=result['stats'],registration=result['registration'],eligible_diff=True,reason='通过几何质量检查；差分仅作辅助，原图优先')
            if not args.cv_only:
                cmd += ['--diff', result['outputs']['ssim_heatmap']]
                info['used_diff']=not args.dry_run
    (out/'cv_quality.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    print('[CV]', info['reason'], flush=True)
    if args.cv_only:
        print('[CV-only] 未调用 API。',flush=True); return
    if args.quantities: cmd += ['--quantities', args.quantities]
    if args.context: cmd += ['--context', args.context]
    if args.response_file: cmd += ['--response-file', args.response_file]
    if args.dry_run: cmd += ['--dry-run']
    if args.fast: cmd += ['--fast']
    subprocess.run(cmd, check=True)

if __name__ == '__main__': main()
