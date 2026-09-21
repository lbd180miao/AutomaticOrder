#!/usr/bin/env python
"""
离线评测脚本 — 3D 料架定位算法

用途：对 media/dm_camera/captures/ 下的真实 .npy 点云文件执行算法
      并与人工标注基准比对，输出偏差统计、重复精度和失败检出率。

使用方法：
    python offline_eval.py                          # 用 MOCK 点云，快速冒烟
    python offline_eval.py --npy-dir media/dm_camera/captures --recipe-id 1 --layer 2
    python offline_eval.py --help

输出：
    - 控制台表格：每帧的 X/Y/Z 实测值、偏差、置信度、是否成功
    - offline_eval_report.json：可用于 CI 或进一步分析
    - 如指定 --baseline-json，与人工基准计算 MAE/RMSE

退化模式标志：
    --inject-outlier-pct   注入百分比离群点（0=关闭）
    --tilt-deg             对支撑面施加倾斜（0=关闭）

Requirements: Section 6.1（离线评测集 + 指标）
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ── Django bootstrap ────────────────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
import django; django.setup()  # noqa: E402

import numpy as np  # noqa: E402

from apps.vision.rack_3d.processors import PointCloudProcessor  # noqa: E402
from apps.vision.rack_3d.algorithms import PositioningAlgorithm  # noqa: E402
from apps.vision.rack_3d.config import load_config               # noqa: E402
from apps.vision.rack_3d.providers import (                      # noqa: E402
    MockDepthCameraProvider, MockHandEyeProvider, MockRobotPoseProvider,
)


# ── CLI ─────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description='离线评测：3D 料架定位算法')
    p.add_argument('--npy-dir', default=None,
                   help='包含 .npy 点云文件的目录（相机坐标系，H×W×3 或 N×3）')
    p.add_argument('--recipe-id', type=int, default=None,
                   help='数据库配方 ID（用于加载 ROI；为空时用 MOCK ROI）')
    p.add_argument('--layer', type=int, default=2,
                   help='层号（默认 2）')
    p.add_argument('--baseline-json', default=None,
                   help='人工标注基准文件路径（JSON，{filename: {x,y,z}}）')
    p.add_argument('--config-json', default=None,
                   help='算法参数覆盖（JSON 字符串）')
    p.add_argument('--inject-outlier-pct', type=float, default=0.0,
                   help='注入离群点百分比（0~100，0=关闭）')
    p.add_argument('--tilt-deg', type=float, default=0.0,
                   help='对支撑面点云施加倾斜（度，0=关闭）')
    p.add_argument('--output', default='offline_eval_report.json',
                   help='输出报告文件路径')
    p.add_argument('--use-mock', action='store_true',
                   help='忽略 --npy-dir，用 MockDepthCameraProvider 生成合成点云')
    p.add_argument('--mock-count', type=int, default=10,
                   help='MOCK 模式下生成帧数（默认 10）')
    return p.parse_args()


# ── 点云加载 ────────────────────────────────────────────────────────────────
def load_npy_files(npy_dir: Path):
    files = sorted(npy_dir.rglob('*.npy'))
    if not files:
        print(f'[WARN] 未在 {npy_dir} 找到任何 .npy 文件')
    return files


def load_as_camera_cloud(path: Path) -> np.ndarray:
    """从 .npy 加载点云，归一化为 (N,3) float64。"""
    data = np.load(path, allow_pickle=False).astype(np.float64)
    if data.ndim == 3:
        data = data.reshape(-1, 3)
    if data.ndim == 1:
        data = data.reshape(-1, 3)
    mask = np.isfinite(data).all(axis=1) & (np.abs(data).sum(axis=1) > 1e-6)
    return data[mask]


# ── ROI 构造 ─────────────────────────────────────────────────────────────────
def get_mock_rois_in_robot_coords(layer_no: int):
    """返回 MOCK 环境下在机器人基坐标系中的三个 ROI。"""
    from apps.vision.rack_3d.tests.test_services import ROIS, LAYER
    from apps.vision.models import ROI3DType
    if layer_no != LAYER:
        print(f'[WARN] MOCK ROI 仅针对第 {LAYER} 层标定，但请求的是第 {layer_no} 层')
    roi_map = {}
    role_map = {
        ROI3DType.SUPPORT_PLANE: 'support',
        ROI3DType.FRONT_EDGE: 'edge',
        ROI3DType.PILLAR: 'pillar',
    }
    for roi_type, bounds in ROIS.items():
        role = role_map[roi_type]
        roi_map[role] = {k: float(v) for k, v in bounds.items()}
    return roi_map


def get_db_rois(recipe_id: int, layer_no: int):
    """从数据库加载 ROI（需 Django ORM）。"""
    from apps.vision.models import RackLocationROI3DEnhanced
    _ROLE_MAP = {'SUPPORT_PLANE': 'support', 'FRONT_EDGE': 'edge',
                 'PILLAR': 'pillar', 'SIDE_EDGE': 'pillar'}
    qs = RackLocationROI3DEnhanced.objects.filter(
        recipe_id=recipe_id, layer_no=layer_no, enabled=True
    ).order_by('priority', 'id')
    roi_map = {}
    for roi in qs:
        role = _ROLE_MAP.get(roi.roi_type)
        if role and role not in roi_map:
            roi_map[role] = {
                'x_min': float(roi.x_min), 'x_max': float(roi.x_max),
                'y_min': float(roi.y_min), 'y_max': float(roi.y_max),
                'z_min': float(roi.z_min), 'z_max': float(roi.z_max),
            }
    return roi_map


# ── 离群点注入 ──────────────────────────────────────────────────────────────
def inject_outliers(cloud: np.ndarray, pct: float, rng: np.random.Generator) -> np.ndarray:
    if pct <= 0:
        return cloud
    n = max(1, int(len(cloud) * pct / 100))
    center = cloud.mean(axis=0)
    outliers = rng.uniform(-500, 500, (n, 3)) + center
    return np.vstack([cloud, outliers])


# ── 单帧评测 ─────────────────────────────────────────────────────────────────
def eval_one_frame(
    camera_cloud: np.ndarray,
    T_fc: np.ndarray,
    T_bf: np.ndarray,
    rois: dict,
    algo: PositioningAlgorithm,
    proc: PointCloudProcessor,
    config: dict,
    inject_outlier_pct: float = 0.0,
    rng: np.random.Generator = None,
) -> dict:
    """对单帧点云执行完整定位链路，返回结果字典。"""
    if rng is None:
        rng = np.random.default_rng(0)

    result = {'is_success': False, 'error': None,
              'x_actual': None, 'y_actual': None, 'z_actual': None,
              'confidence': 0.0, 'point_count': 0,
              'x_confidence': 0.0, 'y_confidence': 0.0, 'z_confidence': 0.0}
    try:
        robot_cloud = proc.transform_to_robot_coords(camera_cloud, T_fc, T_bf)
        robot_cloud = inject_outliers(robot_cloud, inject_outlier_pct, rng)
        result['point_count'] = len(robot_cloud)

        crops = {}
        for role, bounds in rois.items():
            cropped = proc.crop_roi(robot_cloud, **bounds)
            if len(cropped) < config['min_roi_points']:
                raise ValueError(f'{role}: ROI 点数不足 ({len(cropped)})')
            cropped = proc.filter_outliers(cropped, config['nb_neighbors'], config['std_ratio'])
            if len(cropped) > config['downsample_threshold']:
                cropped = proc.downsample(cropped, config['voxel_size_mm'])
            crops[role] = cropped

        support = rois['support']
        ref_xy = [(support['x_min'] + support['x_max']) / 2,
                  (support['y_min'] + support['y_max']) / 2]

        z_det = algo.detect_support_plane(crops['support'], reference_xy=ref_xy)
        y_det = algo.detect_front_edge(crops['edge'])
        x_det = algo.detect_pillar(crops['pillar'])

        result.update({
            'is_success': True,
            'x_actual': x_det['x_actual'],
            'y_actual': y_det['y_actual'],
            'z_actual': z_det['z_actual'],
            'x_confidence': x_det['confidence'],
            'y_confidence': y_det['confidence'],
            'z_confidence': z_det['confidence'],
            'confidence': min(x_det['confidence'], y_det['confidence'], z_det['confidence']),
            'plane_rms_mm': z_det.get('plane_rms_mm'),
            'inlier_ratio': z_det.get('inlier_ratio'),
            'normal_angle_deg': z_det.get('normal_angle_deg'),
            'peak_ratio_y': y_det.get('peak_ratio'),
            'peak_ratio_x': x_det.get('peak_ratio'),
        })
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    return result


# ── 统计汇总 ─────────────────────────────────────────────────────────────────
def compute_stats(results: list, baseline: dict, filenames: list) -> dict:
    """计算偏差统计、重复精度等指标。"""
    success = [r for r in results if r['is_success']]
    failures = [r for r in results if not r['is_success']]

    stats = {
        'total': len(results),
        'success': len(success),
        'failures': len(failures),
        'failure_rate': len(failures) / max(len(results), 1),
    }

    if not success:
        return stats

    # 重复精度（同帧集的 STD）
    for axis in 'xyz':
        vals = [r[f'{axis}_actual'] for r in success if r[f'{axis}_actual'] is not None]
        if vals:
            arr = np.array(vals)
            stats[f'{axis}_mean'] = float(arr.mean())
            stats[f'{axis}_std'] = float(arr.std())
            stats[f'{axis}_min'] = float(arr.min())
            stats[f'{axis}_max'] = float(arr.max())
            stats[f'{axis}_range'] = float(arr.max() - arr.min())

    # 与基准对比
    if baseline:
        errors = {'x': [], 'y': [], 'z': []}
        for fname, r in zip(filenames, results):
            key = Path(fname).name
            if r['is_success'] and key in baseline:
                ref = baseline[key]
                for axis in 'xyz':
                    if f'{axis}_actual' in r and r[f'{axis}_actual'] is not None:
                        errors[axis].append(abs(r[f'{axis}_actual'] - ref[axis]))
        for axis in 'xyz':
            if errors[axis]:
                arr = np.array(errors[axis])
                stats[f'{axis}_mae_mm'] = float(arr.mean())
                stats[f'{axis}_rmse_mm'] = float(np.sqrt((arr ** 2).mean()))
                stats[f'{axis}_max_err_mm'] = float(arr.max())

    # 置信度统计
    conf = [r['confidence'] for r in success]
    stats['confidence_mean'] = float(np.mean(conf))
    stats['confidence_min'] = float(np.min(conf))

    return stats


# ── 打印表格 ─────────────────────────────────────────────────────────────────
def print_table(results: list, filenames: list):
    header = f"{'#':>4}  {'文件名':<40}  {'OK':>3}  {'X':>8}  {'Y':>8}  {'Z':>8}  {'Conf':>6}  {'错误'}"
    print(header)
    print('-' * len(header))
    for i, (fname, r) in enumerate(zip(filenames, results)):
        name = Path(fname).name[:40]
        ok = 'OK' if r['is_success'] else 'NG'
        x = f"{r['x_actual']:.2f}" if r['x_actual'] is not None else '  N/A  '
        y = f"{r['y_actual']:.2f}" if r['y_actual'] is not None else '  N/A  '
        z = f"{r['z_actual']:.2f}" if r['z_actual'] is not None else '  N/A  '
        conf = f"{r['confidence']:.3f}" if r['is_success'] else '  ---  '
        err = (r.get('error') or '')[:60]
        print(f"{i+1:>4}  {name:<40}  {ok:>3}  {x:>8}  {y:>8}  {z:>8}  {conf:>6}  {err}")


# ── 主入口 ───────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    # 配置
    config_override = json.loads(args.config_json) if args.config_json else {}
    config = load_config(config_override if config_override else None)

    # 手眼/位姿矩阵（MOCK 固定值）
    he_provider = MockHandEyeProvider()
    pose_provider = MockRobotPoseProvider()
    T_fc = he_provider.get_hand_eye_matrix()
    T_bf = pose_provider.get_robot_pose_matrix(args.layer)

    # ROI
    if args.recipe_id:
        rois = get_db_rois(args.recipe_id, args.layer)
        if not rois:
            print(f'[ERROR] 数据库中未找到配方 {args.recipe_id} 第 {args.layer} 层的 ROI', file=sys.stderr)
            sys.exit(1)
    else:
        rois = get_mock_rois_in_robot_coords(args.layer)

    # 处理器 / 算法
    proc = PointCloudProcessor()
    algo = PositioningAlgorithm(config)
    rng = np.random.default_rng(0)

    # 读取点云
    if args.use_mock or not args.npy_dir:
        print(f'[INFO] 使用 MOCK 合成点云，共 {args.mock_count} 帧')
        mock_provider = MockDepthCameraProvider()
        camera_clouds = []
        filenames = []
        for i in range(args.mock_count):
            pc = mock_provider.capture_pointcloud()
            data = np.asarray(pc['data'], dtype=np.float64)
            if data.ndim == 3:
                data = data.reshape(-1, 3)
            camera_clouds.append(data)
            filenames.append(f'mock_frame_{i:03d}.npy')
    else:
        npy_dir = Path(args.npy_dir)
        if not npy_dir.exists():
            print(f'[ERROR] 目录不存在: {npy_dir}', file=sys.stderr)
            sys.exit(1)
        npy_files = load_npy_files(npy_dir)
        print(f'[INFO] 找到 {len(npy_files)} 个 .npy 文件')
        camera_clouds = [load_as_camera_cloud(f) for f in npy_files]
        filenames = [str(f) for f in npy_files]

    # 基准
    baseline = {}
    if args.baseline_json:
        with open(args.baseline_json, 'r', encoding='utf-8') as f:
            baseline = json.load(f)

    # 评测
    print(f'\n[INFO] 开始评测（总帧数={len(camera_clouds)}, '
          f'离群点={args.inject_outlier_pct}%, 倾斜={args.tilt_deg}°）\n')
    results = []
    t0 = time.perf_counter()
    for cloud in camera_clouds:
        r = eval_one_frame(
            cloud, T_fc, T_bf, rois, algo, proc, config,
            inject_outlier_pct=args.inject_outlier_pct,
            rng=rng,
        )
        results.append(r)
    elapsed = time.perf_counter() - t0

    # 输出
    print_table(results, filenames)
    stats = compute_stats(results, baseline, filenames)

    print('\n── 汇总统计 ──────────────────────────────────────')
    print(f'  总帧数:       {stats["total"]}')
    print(f'  成功:         {stats["success"]}')
    print(f'  失败:         {stats["failures"]}  ({stats["failure_rate"]*100:.1f}%)')
    for axis in 'xyz':
        if f'{axis}_mean' in stats:
            print(f'  {axis.upper()} 均值/标准差:  {stats[f"{axis}_mean"]:.3f} ± {stats[f"{axis}_std"]:.3f} mm'
                  f'  (范围 {stats[f"{axis}_range"]:.3f} mm)')
    if 'x_mae_mm' in stats:
        print(f'\n── 与基准对比 (MAE / RMSE / MaxErr mm) ──────────')
        for axis in 'xyz':
            if f'{axis}_mae_mm' in stats:
                print(f'  {axis.upper()}:  MAE={stats[f"{axis}_mae_mm"]:.3f}  '
                      f'RMSE={stats[f"{axis}_rmse_mm"]:.3f}  '
                      f'Max={stats[f"{axis}_max_err_mm"]:.3f}')
    print(f'\n  置信度均值/最低:  {stats.get("confidence_mean", 0):.3f} / {stats.get("confidence_min", 0):.3f}')
    print(f'  总耗时:       {elapsed:.2f}s  ({elapsed/max(len(results),1)*1000:.1f}ms/帧)')
    print('─' * 50)

    # 保存报告
    report = {
        'args': vars(args),
        'stats': stats,
        'results': [
            {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
             for k, v in r.items()}
            for r in results
        ],
        'filenames': filenames,
    }
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'[INFO] 报告已保存至 {args.output}')

    # CI 退出码：失败率 > 50% 时返回非零
    if stats['failure_rate'] > 0.5:
        print('[WARN] 失败率超过 50%，评测不通过')
        sys.exit(2)


if __name__ == '__main__':
    main()
