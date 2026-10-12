"""Offline-only entry point: python -m apps.vision.rack_dual_point_offline --help."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

import cv2
import numpy as np

from .algorithms.rack_dual_point import (
    VERSION, compensation, frame_contract, locate, teach_reference,
)
from .rack_dual_point_quality import cloud_forensics, acceptance_report


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_package(path):
    path = Path(path)
    image_path = path/'image2d.png'
    image = cv2.imdecode(np.fromfile(image_path, np.uint8), cv2.IMREAD_COLOR) if image_path.is_file() else None
    def array(name):
        return np.load(path/name, allow_pickle=False) if (path/name).is_file() else None
    return {'image': image, 'cloud': array('pointcloud.npy'),
            'metadata': read_json(path/'metadata.json') if (path/'metadata.json').is_file() else {},
            'config': read_json(path/'roi_config.json') if (path/'roi_config.json').is_file() else {},
            'hand_eye': array('hand_eye_matrix.npy'), 'robot_pose': array('robot_pose_matrix.npy'),
            'pixel_index_map': array('pixel_index_map.npy')}


def audit_package(package):
    cloud, image, metadata = package['cloud'], package['image'], package['metadata']
    blockers = []
    if image is None:
        blockers.append('缺少 image2d.png 原始图像')
    if cloud is None:
        blockers.append('缺少 pointcloud.npy')
    c = metadata.get('dual_point_contract', {})
    checks = {
        'mapping_verified': '缺少经验证的像素配准说明；相同宽高不能证明对应关系',
        'camera_model': '缺少与原图对应的成像模型/内参',
        'frame_id': '缺少图像与点云同步采集帧标识',
        'pose_synchronized': '缺少该采集帧同步机器人位姿证明',
        'calibration_verified': '缺少有效手眼标定确认及矩阵方向定义',
    }
    for field, message in checks.items():
        if field == 'pose_synchronized' and c.get('transform_mode') in ('fixed_camera', 'robot_base'):
            continue
        if not c.get(field):
            blockers.append(message)
    if c:
        try:
            frame_contract(metadata, package['hand_eye'], package['robot_pose'])
        except (ValueError, KeyError, TypeError) as exc:
            blockers.append(f'帧契约验证失败: {exc}')
    config = package['config'].get('dual_point', package['config'])
    if len(config.get('rois', [])) != 4:
        blockers.append('未配置对应两根横杆及立柱的四个 ROI；旧三平面 ROI 不自动迁移')
    identity = package['hand_eye'] is not None and package['hand_eye'].shape == (4, 4) and np.allclose(package['hand_eye'], np.eye(4))
    if identity and not c.get('calibration_verified'):
        blockers.append('hand_eye_matrix.npy 为单位阵，不能视为已完成现场标定')
    return {'image_shape': list(image.shape) if image is not None else None,
            'cloud_shape': list(cloud.shape) if cloud is not None else None,
            'cloud_dtype': str(cloud.dtype) if cloud is not None else None,
            'recorded_unit': metadata.get('camera', {}).get('pointcloud_unit'),
            'finite_nonzero_points': int(np.count_nonzero(np.isfinite(cloud).all(axis=-1) &
                                        np.any(cloud != 0, axis=-1))) if cloud is not None else 0,
            'hand_eye_is_identity': bool(identity), 'blockers': blockers}


def preview(image, result, reference=None):
    output = image.copy()
    colors = [(0, 220, 255), (255, 180, 0), (60, 220, 60), (220, 80, 220)]
    for line, color in zip(result.get('lines', []), colors):
        x0, y0, x1, y1 = line['roi']
        cv2.rectangle(output, (x0, y0), (x1, y1), color, 2)
        for x, y in line['edge_points']:
            cv2.circle(output, (round(x), round(y)), 2, color, -1)
        a, b, c = line['line_abc']
        if abs(b) > abs(a):
            first, last = (x0, round((-a*x0-c)/b)), (x1, round((-a*x1-c)/b))
        else:
            first, last = (round((-b*y0-c)/a), y0), (round((-b*y1-c)/a), y1)
        cv2.line(output, first, last, color, 2)
    for index, pixel in enumerate(result.get('pixels', [])):
        point = tuple(round(x) for x in pixel)
        cv2.drawMarker(output, point, (0, 0, 255), cv2.MARKER_CROSS, 24, 2)
        cv2.putText(output, f'P{index+1}', (point[0]+8, point[1]-8), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 255), 2)
    if reference:
        for pixel in reference.get('pixels', []):
            cv2.drawMarker(output, tuple(round(x) for x in pixel), (255, 255, 0), cv2.MARKER_TILTED_CROSS, 24, 2)
    label = '3D OK - OFFLINE ONLY' if result.get('success') else result.get('errorCode', 'BLOCKED')
    cv2.putText(output, label, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 255), 2)
    return output


def evaluate(path, output, config=None, reference=None, forensics_only=False):
    package = load_package(path)
    if config is not None:
        package['config'] = config
    audit = audit_package(package)
    selected = package['config'].get('dual_point', package['config'])
    # Always run this before invoking any grey-image detector.
    audit['pointcloud_forensics'] = cloud_forensics(package['cloud'],
        package['metadata'].get('camera', {}).get('pointcloud_unit'),
        selected.get('forensics', {}).get('regions'))
    if forensics_only:
        result = {'success': False, 'forensics_complete': True, 'compensation_valid': False,
                  'stage': 'before_2d', 'errorCode': 'FORENSICS_ONLY', 'errorMessage': '已完成点云取证，未运行二维检测或生产定位'}
    elif 'rois' not in selected:
        result = {'success': False, 'compensation_valid': False, 'errorCode': 'FOUR_ROIS_REQUIRED',
                  'errorMessage': '缺少双交点四 ROI 配置；请依据原图示教，不能复用三平面 ROI', 'stage': 'configuration'}
    else:
        result = locate(package['image'], package['cloud'], selected, package['metadata'],
                        package['hand_eye'], package['robot_pose'], package['pixel_index_map'])
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output/'result.json', {'audit': audit, 'result': result, 'offline_only': True})
    if package['image'] is not None:
        ok, encoded = cv2.imencode('.png', preview(package['image'], result, reference))
        if not ok:
            raise OSError('预览图编码失败')
        encoded.tofile(output/'preview.png')
    return result, selected, audit


def main(argv=None):
    parser = argparse.ArgumentParser(description='四 ROI 双交点离线定位/双帧差分；不连接相机或 PLC')
    parser.add_argument('package', type=Path, nargs='?', help='单帧目录；双帧时作为 teach 目录')
    parser.add_argument('--run', type=Path, help='生产帧目录（离线比较）')
    parser.add_argument('--config', type=Path, help='独立四 ROI 配置，不修改原始数据包')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--forensics-only', action='store_true', help='只做点云取证，完全不运行二维定位')
    parser.add_argument('--study', type=Path, help='固定架重复采集及均衡交叉 GR&R 实测 JSON')
    args = parser.parse_args(argv)
    if not args.package and not args.study:
        parser.error('需要数据包目录或 --study')
    if args.run and not args.package:
        parser.error('--run 需要示教数据包目录')
    try:
        for source in (args.package, args.run):
            if source and (args.output.resolve() == source.resolve() or source.resolve() in args.output.resolve().parents):
                raise ValueError('输出必须位于原始数据包之外')
        config = read_json(args.config) if args.config else None
        if args.study:
            study_result = acceptance_report(read_json(args.study))
            atomic_json(args.output/'acceptance_report.json', study_result)
            if not args.package:
                print(json.dumps({'report': str(args.output/'acceptance_report.json'), 'production_accepted': False}))
                return 0
        first, selected, audit = evaluate(args.package, args.output/'teach' if args.run else args.output, config,
                                          forensics_only=args.forensics_only)
        report = {'algorithm_version': VERSION, 'offline_only': True, 'plc_publish_allowed': False,
                  'success': first['success'], 'audit': audit, 'result': first}
        if first['success']:
            atomic_json(args.output/'teach_reference.json', teach_reference(first))
        if args.run:
            second, _, run_audit = evaluate(args.run, args.output/'run', config, first, args.forensics_only)
            report['run_audit'] = run_audit
            report['run_result'] = second
            if first['success']:
                report['compensation'] = compensation(second, teach_reference(first), selected)
            else:
                report['compensation'] = {'success': False, 'compensation_valid': False,
                    'plc_publish_allowed': False, 'errorCode': 'TEACH_FAILED', 'stage': 'teach',
                    'errorMessage': '示教三维定位未通过，禁止输出补偿值'}
            report['success'] = report['compensation']['success']
        atomic_json(args.output/'report.json', report)
        print(json.dumps({'success': report['success'], 'report': str(args.output/'report.json'),
                          'blockers': audit['blockers']}, ensure_ascii=False))
        return 0 if report['success'] or args.forensics_only else 2
    except (OSError, ValueError, TypeError, KeyError) as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        # No fabricated fallback inputs, offsets or success status.
        print(json.dumps({'success': False, 'errorCode': 'PACKAGE_ERROR', 'errorMessage': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
