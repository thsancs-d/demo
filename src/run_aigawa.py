"""安威川四期照片：默认使用原图裁切，不使用生成式修复图。"""
import argparse
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
DATES = ("2019-06", "2020-04", "2021-01", "2022-02")
def main():
    # --all now means persistent one-image-at-a-time tracking; diagnostic commands retain old pairwise behavior.
    options = {arg.partition('=')[0] for arg in sys.argv[1:]}
    if options.intersection(('--all','--new-image','--refresh-only')) and not options.intersection(('--cv-only','--dry-run')):
        from progress_tracker import main as track
        return track(sys.argv[1:])
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", choices=DATES, default=DATES[0])
    p.add_argument("--after", choices=DATES, default=DATES[-1])
    p.add_argument("--all", action="store_true", help="累计导入四期；配合 --cv-only / --dry-run 时诊断相邻三组")
    p.add_argument("--cv-only", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--fast", action="store_true")
    p.add_argument("--enhanced", action="store_true", help="使用非生成式插值锐化图；默认原始裁切")
    if options.intersection(('-h', '--help')):
        from progress_tracker import build_parser
        print('双图比较 / CV 诊断（无参数时保留双图比较行为）：')
        p.print_help()
        print('\n累计监测（使用 --all、--new-image 或 --refresh-only）：')
        build_parser().print_help()
        return
    a = p.parse_args()
    if not a.all and a.before >= a.after: p.error("前期必须早于后期")
    pairs = list(zip(DATES, DATES[1:])) if a.all else [(a.before, a.after)]
    folder = ROOT / "datasets/aigawa" / ("enhanced" if a.enhanced else "images")
    for before, after in pairs:
        out = ROOT / "output/aigawa_v3" / (before + "_to_" + after + ("_enhanced" if a.enhanced else ""))
        cmd = [sys.executable, str(ROOT / "src/run_reservoir.py"), "--before", str(folder / (before + ".png")), "--after", str(folder / (after + ".png")), "--before-date", before, "--after-date", after, "--out", str(out), "--context", str(ROOT / "config/aigawa_context.json")]
        for opt in ("cv_only", "dry_run", "fast"):
            if getattr(a,opt): cmd.append("--" + opt.replace("_", "-"))
        subprocess.run(cmd, cwd=ROOT, check=True)
    if not (a.cv_only or a.dry_run):
        subprocess.run([sys.executable, str(ROOT / 'src/summarize.py'), str(ROOT / 'output/aigawa_v3'), '--project-type','reservoir'], cwd=ROOT,check=True)
if __name__ == "__main__": main()
