"""Experimental center-surface estimation; never substitutes the outer ring.

Local Z is approximated by a*u+b*v+c within 0.35 detected radii. This is
a local approximation, not a calibrated mechanical model or precision claim.
"""
import json
from pathlib import Path
import cv2
import numpy as np
from . import rivet_test as rt


def estimate(cloud, candidate, ratio=.35):
    u, v, radius = (candidate[k] for k in ('u', 'v', 'radius_px'))
    if not np.isfinite([u,v,radius,ratio]).all() or radius <= 0 or not 0 < ratio <= .45:
        raise ValueError('中心表面实验仅允许0～0.45倍半径')
    if not (0 <= u < cloud.shape[1] and 0 <= v < cloud.shape[0]):
        raise ValueError('中心越界')
    rr = min(radius*ratio, candidate.get('sampling_radius_limit_px', radius))
    x0,x1 = max(0,int(u-rr)), min(cloud.shape[1],int(u+rr)+2)
    y0,y1 = max(0,int(v-rr)), min(cloud.shape[0],int(v+rr)+2)
    yy,xx = np.mgrid[y0:y1,x0:x1]
    p = cloud[y0:y1,x0:x1]
    mask = (xx-u)**2+(yy-v)**2 <= rr**2
    valid = mask & np.isfinite(p).all(2) & (p[...,2]>0)
    z = p[...,2][valid].astype(float)
    uv = np.c_[xx[valid]-u, yy[valid]-v].astype(float)
    out = {'status':'INSUFFICIENT_CENTER_DEPTH','radius_ratio':ratio,
           'sample_count':int(mask.sum()),'valid_count':len(z),
           'local_mean_z_mm':float(z.mean()) if len(z) else None,
           'candidate_center_z_mm':None,'reasons':[],
           'note':'实验候选：中心小邻域局部线性表面；未验证测量精度'}
    if len(z)<8:
        out['reasons'].append('中心有效点少于8个；不扩大到外环补点')
        return out
    design = np.c_[uv, np.ones(len(z))]
    keep = np.ones(len(z),bool)
    # Reject residual outliers, not raw Z: a real surface slope is not noise.
    for _ in range(4):
        if keep.sum()<8 or np.linalg.matrix_rank(design[keep])<3:
            out['reasons'].append('剔除后点数或空间维度不足')
            return out
        fit = np.linalg.lstsq(design[keep], z[keep], rcond=None)[0]
        residual = z-design@fit
        med = np.median(residual[keep])
        mad = np.median(np.abs(residual[keep]-med))
        new = np.abs(residual-med)<=max(1.,3*1.4826*mad)
        if np.array_equal(keep,new):
            break
        keep = new
    if keep.sum()<8 or np.linalg.matrix_rank(design[keep])<3:
        return out
    fit = np.linalg.lstsq(design[keep],z[keep],rcond=None)[0]
    residual = z[keep]-design[keep]@fit
    hull = cv2.convexHull(uv[keep].astype('float32'))
    surrounds_center = cv2.pointPolygonTest(hull,(0.,0.),False)>0
    cond = float(np.linalg.cond(design[keep]))
    loo = []
    ids = np.flatnonzero(keep)
    for index in ids:
        selected = ids[ids!=index]
        if np.linalg.matrix_rank(design[selected])==3:
            loo.append(float(np.linalg.lstsq(design[selected],z[selected],rcond=None)[0][2]))
    p90 = float(np.percentile(np.abs(residual),90))
    out.update(candidate_center_z_mm=float(fit[2]),gradient_mm_per_px=fit[:2].tolist(),
               inlier_count=int(keep.sum()),residual_p90_mm=p90,
               center_inside_support=surrounds_center,condition_number=cond,
               leave_one_out_center_span_mm=float(np.ptp(loo)) if loo else None)
    if not surrounds_center: out['reasons'].append('中心不在支持点凸包内部，会发生外推')
    if cond>10: out['reasons'].append('空间分布病态')
    if keep.mean()<.7: out['reasons'].append('剔除比例超过30%')
    if p90>2: out['reasons'].append('局部表面残差P90超过实验门限2 mm')
    out['status'] = 'REJECTED_MODEL' if out['reasons'] else 'EXPERIMENTAL_ONLY'
    return out


def compare():
    dest = rt.ROOT/'outputs'/'center_surface'
    dest.mkdir(parents=True,exist_ok=True)
    all_results=[]
    lines=['# 铆钉中心表面高度专项复查','',
           '用户明确目标为铆钉中心处的表面高度，不能用外环圆盘高度替代。原0.65r邻域Z均值是区域统计，不等同于中心表面高度。', '',
           '实验方法：只取中心0.35r邻域，拟合Z=a(u-u0)+b(v-v0)+c，在残差上剔除离群点。c等于把保留Z按局部斜率校正回中心后再取平均；禁止扩大到外环补点。局部线性假设对尖顶、凹坑和深度突变可能不成立。', '',
           '|样本|原0.65r筛选均值|最近中心像素Z|0.35r直接均值|0.35r拟合中心Z|有效点|残差P90|实验状态|',
           '|---|---|---|---|---|---|---|---|']
    fmt=lambda v:'—' if v is None else f'{v:.3f}'
    for folder in sorted(rt.DEFAULT_DATA.iterdir()):
        if not (folder/'Image.png').exists(): continue
        _,cloud,result=rt.analyze(folder)
        d=result['detection']
        if not d or result['status']=='AMBIGUOUS': continue
        u,v=d['u'],d['v']
        pixel=cloud[int(np.floor(v+.5)),int(np.floor(u+.5))]
        nearest=float(pixel[2]) if np.isfinite(pixel).all() and pixel[2]>0 else None
        m=estimate(cloud,d)
        shifts=[]
        for dv in [-1,0,1]:
            for du in [-1,0,1]:
                shifts.append({'du':du,'dv':dv,**estimate(cloud,{**d,'u':u+du,'v':v+dv})})
        vals=[q['candidate_center_z_mm'] for q in shifts if q['candidate_center_z_mm'] is not None]
        scales=[estimate(cloud,d,ratio) for ratio in [.25,.35,.45]]
        row={'sample':folder.name,'detection':d,'old_measurement':result['measurement'],
             'nearest_pixel_z_mm':nearest,'center_fit':m,'shifts':shifts,'scales':scales,
             'shift_span_mm':float(np.ptp(vals)) if vals else None,
             'shift_models_available':len(vals)}
        all_results.append(row)
        lines.append(f"|{folder.name}|{fmt(result['measurement'].get('z_mean_mm'))}|{fmt(nearest)}|"
                     f"{fmt(m['local_mean_z_mm'])}|{fmt(m['candidate_center_z_mm'])}|{m['valid_count']}/{m['sample_count']}|"
                     f"{fmt(m.get('residual_p90_mm'))}|{m['status']}|")
    lines+=['','所有高度和残差单位为mm。最近像素Z用于对照，不是亚像素中心真值。EXPERIMENTAL_ONLY只表示局部模型检查通过，不表示定位精度达标。', '',
            '|样本|中心±1px拟合Z跨度|可拟合次数/9|删除单点时中心Z跨度|中心被支持点包围|',
            '|---|---|---|---|---|']
    for row in all_results:
        m=row['center_fit']
        lines.append(f"|{row['sample']}|{fmt(row['shift_span_mm'])}|{row['shift_models_available']}/9|{fmt(m.get('leave_one_out_center_span_mm'))}|{m.get('center_inside_support')}|")
    lines+=['','偏移跨度包括被拒绝模型的诊断候选，不能用较小拟合残差代替中心定位不确定度。', '',
            '结论：中心和周边的深度梯度使区域平均偏离目标定义；缩小邻域仍存在缺失、梯度和对中心像素定位的敏感性。当前实验不能证明比原算法更准确，不自动替换主程序。', '',
            '下一步应先用独立二维中心标注验证定位，再使用固定姿态重复帧和中心表面三维真值检查偏差。对不同姿态数据直接跨帧平均会混入真实运动。', '',
            '复现：python center_surface.py。完整逐组模型、拒绝原因、采样半径对照和偏移测试见 comparison.json。']
    (dest/'comparison.json').write_text(json.dumps(all_results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (dest/'中心高度复查.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))


if __name__=='__main__':
    compare()
