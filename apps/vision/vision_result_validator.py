"""Independent depth-geometry gates used only by the dual-point rack path."""
import cv2
import numpy as np

from .algorithms.rack_dual_point import LocalizationError, camera_ray, number, require
from .algorithms.robust_rack_geometry import robust_plane


def crop_space(cloud, bounds, *, positive_depth=True):
    box = np.asarray(bounds, float)
    require(box.shape == (2, 3) and np.isfinite(box).all() and np.all(box[0] < box[1]),
            'INVALID_CONFIG', '2d_3d_validation', '独立三维取证区域无效')
    p = np.asarray(cloud, float).reshape(-1, 3)
    depth = p[:, 2] > 0 if positive_depth else np.any(p != 0, axis=1)
    return p[np.isfinite(p).all(axis=1) & depth & np.all((p >= box[0]) & (p <= box[1]), axis=1)]


def project_camera(points, model):
    camera_ray([0., 0.], model)  # shared calibration validation
    p = np.asarray(points, float)
    require(np.isfinite(p).all() and np.all(p[:, 2] > 0), 'PROJECTION_FAILED', '2d_3d_validation', '三维棱边不在相机前方')
    k = np.asarray(model['K'], float)
    if model['type'] == 'opencv':
        uv, _ = cv2.projectPoints(p, np.zeros(3), np.zeros(3), k, np.asarray(model['distortion'], float))
        return uv.reshape(-1, 2)
    homogeneous = p @ k.T
    return homogeneous[:, :2]/homogeneous[:, 2:]


class VisionResultValidator:
    """Fit a physical beam edge from depth alone, then compare its projection.

    The full camera cloud and calibrated 3D face boxes are the ONLY fit inputs.
    Neither the measured 2D line nor its ray/plane intersections seed the fit.
    A lone front plane has no independently observable edge and is insufficient.
    """

    @staticmethod
    def _face(cloud, region, quality):
        points = crop_space(cloud, region['boundsMm'])
        try:
            plane, support = robust_plane(points, threshold_mm=number(quality['ransac_mm'], 'ransac_mm'),
                min_points=max(3, int(number(quality['min_points'], 'min_points'))),
                iterations=int(number(quality['iterations'], 'iterations')))
        except ValueError as exc:
            raise LocalizationError('INDEPENDENT_GEOMETRY_FAILED', '2d_3d_validation', str(exc)) from exc
        normal = np.asarray(region['normal'], float)
        require(normal.shape == (3,) and np.isfinite(normal).all() and np.linalg.norm(normal) > 1e-8,
                'INVALID_CONFIG', '2d_3d_validation', '独立参考表面法向量无效')
        angle = np.degrees(np.arccos(np.clip(abs(normal @ plane['normal'])/np.linalg.norm(normal), 0, 1)))
        require(plane['inlier_ratio'] >= number(quality['min_inlier_ratio'], 'min_inlier_ratio')
                and plane['rms_mm'] <= number(quality['max_residual_mm'], 'max_residual_mm')
                and plane['eigenvalue_ratio'] <= number(quality['max_eigenvalue_ratio'], 'max_eigenvalue_ratio')
                and angle <= number(region['normalToleranceDeg'], 'normalToleranceDeg'),
                'INDEPENDENT_GEOMETRY_QUALITY', '2d_3d_validation', '独立三维表面质量/法向不合格')
        return plane, support

    def validate_beam(self, cloud_camera, line, roi, recovered, model, config):
        require(isinstance(config, dict) and config.get('model') == 'two_face_edge',
                'CONSISTENCY_EVIDENCE_MISSING', '2d_3d_validation', '需要独立三维表面/实体棱边证据，单平面射线回投不能用于自证')
        require(config.get('edgeSide') == roi['edgeSide'], 'EDGE_IDENTITY_MISMATCH',
                '2d_3d_validation', '独立三维棱边与二维所选边缘身份不一致')
        main, main_points = self._face(cloud_camera, config['frontFace'], config['fit'])
        sides = config['sideFaces']
        require(len(sides) == (2 if roi['edgeMode'] == 'center' else 1),
                'CONSISTENCY_EVIDENCE_MISSING', '2d_3d_validation', '中心线需要两条独立实体棱边')
        edges, planes = [], [main]
        for region in sides:
            side, side_points = self._face(cloud_camera, region, config['fit'])
            planes.append(side)
            n1, n2 = np.array(main['normal']), np.array(side['normal'])
            axis = np.cross(n1, n2)
            require(np.linalg.norm(axis) >= number(config['minPlaneSine'], 'minPlaneSine'),
                    'INDEPENDENT_PLANES_PARALLEL', '2d_3d_validation', '相邻表面近似平行')
            axis /= np.linalg.norm(axis)
            pivot = (main_points.mean(0)+side_points.mean(0))/2
            origin = np.linalg.solve(np.vstack([n1, n2, axis]), [-main['offset'], -side['offset'], axis @ pivot])
            ranges = [((p-origin) @ axis).min() for p in (main_points, side_points)], [((p-origin) @ axis).max() for p in (main_points, side_points)]
            low, high = max(ranges[0]), min(ranges[1])
            require(high-low >= number(config['minSpanMm'], 'minSpanMm'),
                    'INDEPENDENT_EDGE_SPAN', '2d_3d_validation', '独立棱边有效支撑长度不足')
            for points in (main_points, side_points):
                transverse = points-origin-np.outer((points-origin) @ axis, axis)
                require(np.min(np.linalg.norm(transverse, axis=1)) <= number(config['maxSupportGapMm'], 'maxSupportGapMm'),
                        'INDEPENDENT_EDGE_EXTRAPOLATION', '2d_3d_validation', '实体棱边距离实测表面过远')
            edge = origin+np.linspace(low, high, 32)[:, None]*axis
            uv = project_camera(edge, model)
            uv = uv[np.argsort(uv[:, 0])]
            require(np.all(np.diff(uv[:, 0]) > 0), 'INDEPENDENT_EDGE_ORIENTATION', '2d_3d_validation', '横杆投影方向无效')
            edges.append(uv)
        # For a two-edge image center, average projected y at the same x; do not
        # assume that projecting a 3D midpoint commutes with perspective division.
        low, high = max(e[0, 0] for e in edges), min(e[-1, 0] for e in edges)
        low, high = max(low, line['roi'][0]), min(high, line['roi'][2]-1)
        require(high-low >= number(config['minSpanPx'], 'minSpanPx'),
                'INDEPENDENT_EDGE_SPAN', '2d_3d_validation', '三维棱边与二维测量段的重叠长度不足')
        x = np.linspace(low, high, 32)
        projected_y = np.asarray([np.interp(x, e[:, 0], e[:, 1]) for e in edges])
        if len(edges) == 2:
            width = np.abs(projected_y[0]-projected_y[1])
            require(np.all(width > 0) and np.all(np.abs(width-number(roi['expectedWidth'], 'expectedWidth'))
                    <= number(roi['widthTolerance'], 'widthTolerance')),
                    'INDEPENDENT_EDGE_WIDTH', '2d_3d_validation', '两条独立三维棱边的投影宽度与示教身份不符')
        uv = np.column_stack([x, projected_y.mean(axis=0)])
        abc = np.asarray(line['line_abc'], float)
        distance = np.abs(uv @ abc[:2]+abc[2])/np.linalg.norm(abc[:2])
        rms, maximum = float(np.sqrt(np.mean(distance**2))), float(distance.max())
        direction = uv[-1]-uv[0]
        tangent = np.array([abc[1], -abc[0]])
        angle = float(np.degrees(np.arccos(np.clip(abs(direction @ tangent)/(np.linalg.norm(direction)*np.linalg.norm(tangent)), 0, 1))))
        surface_distance = abs(np.dot(main['normal'], recovered['xyz'])+main['offset'])
        surface_angle = np.degrees(np.arccos(np.clip(abs(np.dot(main['normal'], recovered['plane']['normal'])), 0, 1)))
        metrics = {'rms_px': rms, 'max_px': maximum, 'angle_deg': angle,
                   'surface_distance_mm': float(surface_distance), 'surface_angle_deg': float(surface_angle),
                   'projected_edge': uv.tolist(), 'independent_planes': planes,
                   'source': 'camera_cloud_3d_face_boxes', 'success': False}
        ok = (rms <= number(config['maxRmsPx'], 'maxRmsPx')
              and maximum <= number(config['maxDistancePx'], 'maxDistancePx')
              and angle <= number(config['maxAngleDeg'], 'maxAngleDeg')
              and surface_distance <= number(config['maxSurfaceDistanceMm'], 'maxSurfaceDistanceMm')
              and surface_angle <= number(config['maxSurfaceAngleDeg'], 'maxSurfaceAngleDeg'))
        if not ok:
            exc = LocalizationError('TWO_D_THREE_D_MISMATCH', '2d_3d_validation',
                                    f'独立三维棱边不一致: RMS={rms:.3f}px, max={maximum:.3f}px, angle={angle:.3f}deg, surface={surface_distance:.3f}mm')
            exc.metrics = metrics
            raise exc
        return {**metrics, 'success': True}
