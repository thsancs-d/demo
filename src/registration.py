"""Reservoir registration: conservative multi-model matching and audited control points."""
from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np


class RegistrationError(RuntimeError):
    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


def _project(points, H):
    return cv2.perspectiveTransform(np.asarray(points, np.float32).reshape(-1, 1, 2), H).reshape(-1, 2)


def _coverage(points, shape):
    return float(cv2.contourArea(cv2.convexHull(np.asarray(points, np.float32)))) / (shape[0]*shape[1]) if len(points)>=3 else 0.0


def evaluate(H, mask, src, dst, ref_shape, mov_shape, threshold, name, model, min_inliers=12):
    """Reject a degenerate or poorly supported transform even if overlap is high."""
    count = len(src)
    d = dict(method=name, model=model, matches=count, inliers=0, inlier_ratio=0.0, accepted=False, reasons=[])
    why = d['reasons']
    if H is None or mask is None or not np.isfinite(H).all():
        why.append('无有效变换'); return d
    sel = np.asarray(mask).ravel().astype(bool)
    if len(sel)!=count:
        why.append('内点掩膜长度错误'); return d
    s,t = src[sel],dst[sel]
    n=len(s); ratio=n/max(1,count)
    d.update(inliers=n,inlier_ratio=round(ratio,4),ref_coverage=round(_coverage(t,ref_shape),4),mov_coverage=round(_coverage(s,mov_shape),4))
    if n<min_inliers: why.append('内点数不足')
    if ratio<.5: why.append('内点率不足')
    if min(d['ref_coverage'],d['mov_coverage'])<.06: why.append('内点空间覆盖不足')
    if n<4: return d
    h,w=ref_shape[:2]; mh,mw=mov_shape[:2]
    corners=np.float32([[0,0],[mw-1,0],[mw-1,mh-1],[0,mh-1]])
    try:
        inv=np.linalg.inv(H)
        # A projective horizon cannot cross the source image.
        denom=np.c_[corners,np.ones(4)]@H[2]
        if np.min(np.abs(denom))<1e-8 or np.any(np.sign(denom)!=np.sign(denom[0])):
            why.append('投影地平线穿过图像'); return d
        poly=_project(corners,H)
        if not np.isfinite(poly).all() or np.max(np.abs(poly))>10*max(h,w):
            why.append('投影边界异常'); return d
        area=cv2.contourArea(poly,oriented=True)/(w*h)
        if not cv2.isContourConvex(poly) or not .2<=area<=5:
            why.append('投影形状、方向或面积异常'); return d
        f=np.linalg.norm(_project(s,H)-t,axis=1)
        b=np.linalg.norm(_project(t,inv)-s,axis=1)*max(h,w)/max(mh,mw)
        err=np.maximum(f,b)
        d['median_error_px']=round(float(np.median(err)),3)
        d['p90_error_px']=round(float(np.percentile(err,90)),3)
        if np.median(err)>threshold or np.percentile(err,90)>2*threshold: why.append('双向重投影误差过大')
        overlap=cv2.warpPerspective(np.ones((mh,mw),np.uint8),H,(w,h),flags=cv2.INTER_NEAREST).mean()
        d['overlap_ratio']=round(float(overlap),4)
        if overlap<.5: why.append('重叠率不足')
    except (cv2.error,np.linalg.LinAlgError,ValueError):
        why.append('变换数值不稳定')
    d['accepted']=not why
    return d


def register(ref,mov,nfeatures=6000,threshold=3.0):
    diagnostics=[]; candidates=[]
    sift_features = None  # Raw features are shared only within this registration.
    for name in ('SIFT','RootSIFT','AKAZE'):
        factory_name = 'AKAZE_create' if name == 'AKAZE' else 'SIFT_create'
        factory = getattr(cv2, factory_name, None)
        if not callable(factory):
            diagnostics.append(dict(method=name, accepted=False, reasons=[f'当前 OpenCV 缺少 {factory_name}，跳过该策略']))
            continue
        try:
            if name != 'AKAZE' and sift_features is not None:
                kr,dr,km,dm = sift_features
            else:
                detector = factory(threshold=.0005) if name == 'AKAZE' else factory(nfeatures=nfeatures, contrastThreshold=.015)
                kr,dr=detector.detectAndCompute(ref,None); km,dm=detector.detectAndCompute(mov,None)
                if name != 'AKAZE':
                    sift_features = kr,dr,km,dm
        except (cv2.error, AttributeError, NotImplementedError) as exc:
            diagnostics.append(dict(method=name, accepted=False, reasons=[f'{factory_name} 不可用：{exc}']))
            continue
        if dr is None or dm is None or min(len(dr),len(dm))<2:
            diagnostics.append(dict(method=name,accepted=False,reasons=['特征不足'])); continue
        if name=='RootSIFT':
            dr=np.sqrt(dr/(dr.sum(axis=1,keepdims=True)+1e-7)); dm=np.sqrt(dm/(dm.sum(axis=1,keepdims=True)+1e-7))
        bf=cv2.BFMatcher(cv2.NORM_HAMMING if name=='AKAZE' else cv2.NORM_L2)
        forward=bf.knnMatch(dm,dr,k=2); reverse=bf.knnMatch(dr,dm,k=2)
        for ratio in (.75,.85,.9):
            back={p[0].queryIdx:p[0].trainIdx for p in reverse if len(p)==2 and p[0].distance<ratio*p[1].distance}
            matches=[p[0] for p in forward if len(p)==2 and p[0].distance<ratio*p[1].distance and back.get(p[0].trainIdx)==p[0].queryIdx]
            s=np.float32([km[m.queryIdx].pt for m in matches]).reshape(-1,2); t=np.float32([kr[m.trainIdx].pt for m in matches]).reshape(-1,2)
            for model in ('affine','homography'):
                H=mask=None
                if len(matches)>=4:
                    try:
                        if model=='affine':
                            A,mask=cv2.estimateAffine2D(s,t,ransacReprojThreshold=threshold,maxIters=5000)
                            if A is not None: H=np.vstack([A,[0,0,1]])
                        else: H,mask=cv2.findHomography(s,t,cv2.USAC_MAGSAC,threshold,maxIters=5000)
                    except cv2.error: pass
                d=evaluate(H,mask,s,t,ref.shape,mov.shape,threshold,name,model)
                d['ratio_test']=ratio; diagnostics.append(d)
                if d['accepted']:
                    rank=(d['inliers']*min(d['ref_coverage'],d['mov_coverage']),-d['median_error_px'],model=='affine')
                    candidates.append((rank,H,mask,len(kr),len(km),len(forward),len(matches),d))
    if not candidates:
        raise RegistrationError('多策略配准均未通过质量检查；保留原图，不生成新差分图', {'candidates':diagnostics})
    _,H,mask,kr,km,raw,kept,d=max(candidates,key=lambda x:x[0])
    return H,mask,kr,km,raw,kept,d['inlier_ratio'],{'selected':d,'candidates':diagnostics}


def manual_register(path,ref,mov,threshold=3.0):
    """Normalized paired points, independent check points; no automatic approval."""
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    def read(key):
        arr=np.asarray(data[key],dtype=np.float32)
        if arr.ndim!=3 or arr.shape[1:]!=(2,2) or not np.isfinite(arr).all() or np.any(arr<0) or np.any(arr>1):
            raise ValueError(f'{key} 必须为 [[前图x,y],[后图x,y]] 的归一化点对列表')
        dst=arr[:,0,:]*np.float32([ref.shape[1]-1,ref.shape[0]-1]); src=arr[:,1,:]*np.float32([mov.shape[1]-1,mov.shape[0]-1])
        if len(np.unique(dst,axis=0))!=len(dst) or len(np.unique(src,axis=0))!=len(src): raise ValueError('控制点不可重复')
        return src,dst
    s,t=read('fit'); cs,ct=read('check')
    if len(s)<8 or len(cs)<4: raise ValueError('至少8个拟合点及4个独立检查点')
    if min(np.linalg.norm(cs[:,None]-s[None,:],axis=2).min(),np.linalg.norm(ct[:,None]-t[None,:],axis=2).min())<threshold: raise ValueError('检查点必须独立于拟合点')
    H,mask=cv2.findHomography(s,t,cv2.USAC_MAGSAC,threshold)
    d=evaluate(H,mask,s,t,ref.shape,mov.shape,threshold,'manual','homography',min_inliers=8)
    if d['accepted']:
        e=np.linalg.norm(_project(cs,H)-ct,axis=1)
        d['check_max_error_px']=round(float(e.max()),3)
        d['check_coverage']=round(_coverage(ct,ref.shape),4)
        if e.max()>2*threshold or d['check_coverage']<.06:
            d['accepted']=False;d['reasons'].append('独立检查点误差过大或覆盖不足')
    if not d['accepted']: raise RegistrationError('手动控制点未通过质量检查；保留原图',{'candidates':[d]})
    return H,mask,0,0,len(s),len(s),d['inlier_ratio'],{'selected':d,'candidates':[d]}
