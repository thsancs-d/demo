"""交互式同名点选取（需桌面 GUI）。仅选择两期均未改变的固定地物。"""
import argparse
import json
from pathlib import Path
import cv2
import matplotlib.pyplot as plt


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--before',required=True);ap.add_argument('--after',required=True)
    ap.add_argument('--out',default='config/control_points.json')
    ap.add_argument('--fit',type=int,default=10);ap.add_argument('--check',type=int,default=4)
    a=ap.parse_args()
    if a.fit<8 or a.check<4: ap.error('至少8个拟合点和4个检查点')
    n=a.fit+a.check
    def pick(path,label):
        im=cv2.imread(path)
        if im is None: raise FileNotFoundError(path)
        h,w=im.shape[:2]; fig,ax=plt.subplots(figsize=(12,8));ax.imshow(cv2.cvtColor(im,cv2.COLOR_BGR2RGB))
        ax.set_title(f'{label}: click {n} landmarks in order (first {a.fit} fit, last {a.check} check)')
        print(f'{label}: 按顺序选 {n} 个同名点；前 {a.fit} 个拟合，后 {a.check} 个检查。右键撤销，按回车提前结束将取消。')
        pts=fig.ginput(n,timeout=0);plt.close(fig)
        if len(pts)!=n or any(not (0<=x<=w-1 and 0<=y<=h-1) for x,y in pts): raise ValueError('选点未完成或超出边界')
        return [[x/(w-1),y/(h-1)] for x,y in pts]
    before=pick(a.before,'BEFORE');after=pick(a.after,'AFTER')
    pairs=[[x,y] for x,y in zip(before,after)]
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'fit':pairs[:a.fit],'check':pairs[a.fit:]},indent=2),encoding='utf-8');print(out)
if __name__=='__main__': main()
