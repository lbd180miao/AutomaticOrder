"""Enhanced repeatability diagnostics for rack locator."""
import numpy as np
from scipy.spatial import cKDTree


def analyze_point_cloud_stability(cloud1, cloud2, roi):
    """
    Compare two point clouds in the same ROI to identify sources of variance.
    
    Returns metrics:
    - point_count_change: difference in valid points
    - depth_noise_mm: standard deviation of depth changes
    - systematic_shift_mm: median XYZ shift
    - surface_coverage: percentage of overlapping area
    """
    x, y, w, h = [int(roi[k]) for k in ('x', 'y', 'w', 'h')]
    
    patch1 = cloud1[y:y+h, x:x+w]
    patch2 = cloud2[y:y+h, x:x+w]
    
    valid1 = np.isfinite(patch1).all(axis=2) & (patch1[:, :, 2] > 0)
    valid2 = np.isfinite(patch2).all(axis=2) & (patch2[:, :, 2] > 0)
    
    overlap = valid1 & valid2
    
    if overlap.sum() < 10:
        return {'error': 'Insufficient overlap'}
    
    diff = patch2[overlap] - patch1[overlap]
    
    # Systematic shift (median to ignore outliers)
    systematic_shift = np.median(diff, axis=0)
    
    # Random noise (MAD after removing systematic shift)
    deviations = diff - systematic_shift
    mad = np.median(np.abs(deviations), axis=0)
    noise_std = 1.4826 * mad  # Convert MAD to std
    
    return {
        'point_count_1': int(valid1.sum()),
        'point_count_2': int(valid2.sum()),
        'overlap_count': int(overlap.sum()),
        'coverage_ratio': float(overlap.sum() / max(valid1.sum(), valid2.sum())),
        'systematic_shift_mm': systematic_shift.tolist(),
        'noise_std_mm': noise_std.tolist(),
        'depth_noise_mm': float(noise_std[2]),
        'max_abs_shift_mm': float(np.max(np.abs(diff), axis=0).max())
    }


def diagnose_axis_repeatability(axis1, axis2):
    """
    Compare two fitted axes to quantify repeatability issues.
    
    Returns:
    - position_shift_mm: distance between axis points
    - angular_drift_deg: angle between directions
    - quality_change: change in variance ratio
    """
    p1, p2 = np.array(axis1['point']), np.array(axis2['point'])
    u1, u2 = np.array(axis1['direction']), np.array(axis2['direction'])
    
    # Normalize directions
    u1 = u1 / np.linalg.norm(u1)
    u2 = u2 / np.linalg.norm(u2)
    
    # Position shift (perpendicular distance between parallel lines)
    position_diff = p2 - p1
    # Project onto perpendicular plane
    parallel_component = (position_diff @ u1) * u1
    perpendicular_shift = position_diff - parallel_component
    
    # Angular drift
    angle = np.arccos(np.clip(abs(u1 @ u2), 0, 1))
    
    return {
        'total_position_shift_mm': float(np.linalg.norm(position_diff)),
        'perpendicular_shift_mm': float(np.linalg.norm(perpendicular_shift)),
        'parallel_shift_mm': float(abs(position_diff @ u1)),
        'angular_drift_deg': float(np.degrees(angle)),
        'quality_ratio_1': float(axis1['axis_variance_ratio']),
        'quality_ratio_2': float(axis2['axis_variance_ratio']),
        'linearity_1': float(axis1['linearity']),
        'linearity_2': float(axis2['linearity']),
        'rms_change_mm': float(axis2['rms_mm'] - axis1['rms_mm'])
    }


def suggest_improvements(diagnostics):
    """
    Provide actionable suggestions based on diagnostics.
    """
    suggestions = []
    
    for name, metrics in diagnostics.items():
        if 'error' in metrics:
            suggestions.append(f"{name}: {metrics['error']} - 重新框选或调整相机位置")
            continue
        
        if metrics.get('coverage_ratio', 1) < 0.7:
            suggestions.append(f"{name}: 点云覆盖率仅 {metrics['coverage_ratio']*100:.1f}%，可能存在遮挡或深度缺失")
        
        if metrics.get('depth_noise_mm', 0) > 1.0:
            suggestions.append(f"{name}: 深度噪声 {metrics['depth_noise_mm']:.2f}mm 较大，检查相机曝光和环境光")
        
        systematic = metrics.get('systematic_shift_mm', [0, 0, 0])
        if max(abs(x) for x in systematic) > 2.0:
            suggestions.append(f"{name}: 系统性位移 {[f'{x:.2f}' for x in systematic]} mm，料架可能发生物理移动")
        
        if metrics.get('angular_drift_deg', 0) > 0.5:
            suggestions.append(f"{name}: 角度漂移 {metrics['angular_drift_deg']:.3f}°，轴线拟合不稳定")
        
        if metrics.get('quality_ratio_1', 10) < MIN_AXIS_VARIANCE_RATIO:
            suggestions.append(f"{name}: 方差比低，ROI 可能包含多个构件或背景，建议缩小框选范围")
    
    return suggestions


def generate_repeatability_report(service, recipe, result_ids):
    """
    Generate comprehensive repeatability report from multiple measurements.
    
    Args:
        service: RackLocationService instance
        recipe: RackLocationRecipe instance
        result_ids: list of RackLocationResult IDs to compare
    
    Returns:
        Dictionary with detailed diagnostics and suggestions
    """
    from .models import RackLocationResult
    
    records = {r.pk: r for r in RackLocationResult.objects.filter(pk__in=result_ids, recipe=recipe)}
    
    if len(records) < 2:
        return {'error': 'Need at least 2 results for comparison'}
    
    reference_id = result_ids[0]
    ref_record = records[reference_id]
    ref_cloud = service._load_workbench_pointcloud(ref_record.raw_data_path)
    rois = ref_record.result_data.get('local_template_rois', {})
    
    report = {
        'recipe_id': recipe.pk,
        'reference_result_id': reference_id,
        'comparison_count': len(result_ids) - 1,
        'point_cloud_diagnostics': {},
        'axis_diagnostics': {},
        'frame_diagnostics': {},
        'suggestions': []
    }
    
    for result_id in result_ids[1:]:
        record = records[result_id]
        cloud = service._load_workbench_pointcloud(record.raw_data_path)
        
        # Point cloud level comparison
        for name, roi in rois.items():
            key = f"{result_id}_{name}"
            report['point_cloud_diagnostics'][key] = analyze_point_cloud_stability(ref_cloud, cloud, roi)
        
        # Axis level comparison
        ref_axes = ref_record.result_data.get('axes', {})
        cur_axes = record.result_data.get('axes', {})
        
        for name in ['plane1', 'plane2', 'plane3']:
            if name in ref_axes and name in cur_axes:
                key = f"{result_id}_{name}"
                report['axis_diagnostics'][key] = diagnose_axis_repeatability(ref_axes[name], cur_axes[name])
        
        # Frame level comparison (A/B groups)
        ref_groups = ref_record.result_data.get('robot_groups', {})
        cur_groups = record.result_data.get('robot_groups', {})
        
        for group in ['A', 'B']:
            if group in ref_groups and group in cur_groups:
                key = f"{result_id}_{group}"
                ref_pose = ref_groups[group]['pose6d']
                cur_pose = cur_groups[group]['pose6d']
                report['frame_diagnostics'][key] = {
                    'translation_error_mm': {
                        'x': cur_pose['x'] - ref_pose['x'],
                        'y': cur_pose['y'] - ref_pose['y'],
                        'z': cur_pose['z'] - ref_pose['z']
                    },
                    'rotation_error_deg': {
                        'rx': cur_pose['rx'] - ref_pose['rx'],
                        'ry': cur_pose['ry'] - ref_pose['ry'],
                        'rz': cur_pose['rz'] - ref_pose['rz']
                    }
                }
    
    # Generate suggestions
    report['suggestions'] = suggest_improvements(report['point_cloud_diagnostics'])
    report['suggestions'].extend(suggest_improvements(report['axis_diagnostics']))
    
    return report


# Compatibility
MIN_AXIS_VARIANCE_RATIO = 1.5
