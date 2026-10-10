"""ROI quality checker and automatic optimization."""
import numpy as np
from scipy.spatial import cKDTree
from scipy.cluster.hierarchy import linkage, fcluster


def analyze_roi_quality(points, roi_name=''):
    """
    Analyze point cloud quality within an ROI and provide actionable feedback.
    
    Returns:
    - quality_score: 0-100, higher is better
    - issues: list of detected problems
    - suggestions: list of actionable improvements
    """
    points = np.asarray(points, dtype=float)
    
    if len(points) < 50:
        return {
            'quality_score': 0,
            'issues': ['点数过少（< 50）'],
            'suggestions': ['扩大 ROI 范围或检查相机深度覆盖']
        }
    
    issues = []
    suggestions = []
    
    # Check 1: Point density uniformity
    tree = cKDTree(points)
    distances = tree.query(points, k=min(10, len(points)))[0][:, 1:].mean(1)
    density_std = distances.std() / distances.mean()
    
    if density_std > 0.5:
        issues.append(f'点密度不均匀（变异系数 {density_std:.2f}）')
        suggestions.append('ROI 可能包含多个分离的构件，建议缩小范围')
    
    # Check 2: Spatial span (should be elongated for axis fitting)
    center = points.mean(0)
    cov = np.cov((points - center).T)
    eigenvalues = np.linalg.eigvalsh(cov)
    
    if eigenvalues[-1] < 100:  # < 10mm std in longest direction
        issues.append(f'空间跨度过小（主方向标准差 {np.sqrt(eigenvalues[-1]):.1f}mm）')
        suggestions.append('ROI 太小，应该包含构件的较长段（至少 100mm）')
    
    variance_ratio = eigenvalues[-1] / max(eigenvalues[-2], 1e-6)
    
    if variance_ratio < 3:
        issues.append(f'形状不够狭长（方差比 {variance_ratio:.2f} < 3）')
        suggestions.append('ROI 应该沿着单一构件轴线延伸，避免包含垂直相交的构件')
    
    # Check 3: Multimodal distribution (multiple components)
    if len(points) > 100:
        # Sample for clustering
        sample = points[::max(1, len(points)//500)]
        if len(sample) > 10:
            Z = linkage(sample, method='ward')
            clusters = fcluster(Z, t=50, criterion='distance')  # 50mm threshold
            n_clusters = len(np.unique(clusters))
            
            if n_clusters > 2:
                issues.append(f'检测到多个分离簇（{n_clusters} 个）')
                suggestions.append('ROI 包含多个不连续构件，建议分开框选')
    
    # Check 4: Fit quality preview
    centered = points - center
    values, vectors = np.linalg.eigh(cov)
    direction = vectors[:, -1]
    residuals = np.linalg.norm(np.cross(centered, direction), axis=1)
    rms = np.sqrt(np.mean(residuals**2))
    
    if rms > 30:
        issues.append(f'拟合误差过大（RMS {rms:.1f}mm）')
        suggestions.append('点云可能包含弯曲构件或背景噪声，建议重新框选平直段')
    
    # Check 5: Depth quality
    depth_values = points[:, 2]
    if depth_values.std() > 100:
        issues.append(f'深度变化过大（σ={depth_values.std():.1f}mm）')
        suggestions.append('可能包含前后分离的多个表面，检查 ROI 是否框选了遮挡区域')
    
    # Calculate overall quality score
    score = 100
    score -= min(30, density_std * 40)  # -0 to -30
    score -= max(0, 20 - variance_ratio * 5)  # -0 to -20
    score -= min(30, rms / 3)  # -0 to -30
    score -= min(20, (n_clusters - 1) * 10) if len(points) > 100 else 0  # -0 to -20
    
    quality_score = max(0, score)
    
    return {
        'roi_name': roi_name,
        'quality_score': quality_score,
        'point_count': len(points),
        'variance_ratio': float(variance_ratio),
        'rms_mm': float(rms),
        'linearity': float(1 - eigenvalues[-2] / eigenvalues[-1]),
        'density_uniformity': float(1 / (1 + density_std)),
        'issues': issues,
        'suggestions': suggestions
    }


def suggest_roi_shrink(points, current_box, target_quality=0.9):
    """
    Suggest tighter AABB based on removing outliers.
    
    Returns:
    - optimized_box: new AABB parameters
    - improvement: expected quality improvement
    """
    points = np.asarray(points, dtype=float)
    
    if len(points) < 100:
        return {'error': 'Too few points for optimization'}
    
    # Fit axis
    center = points.mean(0)
    cov = np.cov((points - center).T)
    values, vectors = np.linalg.eigh(cov)
    direction = vectors[:, -1]
    
    # Remove points with large perpendicular distance
    residuals = np.linalg.norm(np.cross(points - center, direction), axis=1)
    threshold = np.percentile(residuals, 80)
    inliers = points[residuals <= threshold]
    
    if len(inliers) < 50:
        return {'error': 'Optimization would remove too many points'}
    
    # Compute new AABB
    margin = 5  # 5mm safety margin
    lo = inliers.min(0) - margin
    hi = inliers.max(0) + margin
    
    optimized_box = {
        f'{axis}{end}': float(val[i])
        for i, axis in enumerate('XYZ')
        for end, val in [('min', lo), ('max', hi)]
    }
    
    # Re-analyze quality
    old_quality = analyze_roi_quality(points, 'original')
    new_quality = analyze_roi_quality(inliers, 'optimized')
    
    return {
        'optimized_box': optimized_box,
        'old_quality_score': old_quality['quality_score'],
        'new_quality_score': new_quality['quality_score'],
        'improvement': new_quality['quality_score'] - old_quality['quality_score'],
        'points_removed': len(points) - len(inliers),
        'points_kept': len(inliers),
        'recommendation': 'ACCEPT' if new_quality['quality_score'] > 70 else 'REJECT'
    }


def batch_analyze_recipe_rois(service, recipe, pointcloud_token):
    """
    Analyze all three ROIs for a recipe and generate comprehensive report.
    """
    from . import rack_spatial as spatial
    
    cloud = service._load_workbench_pointcloud(pointcloud_token)
    rois = recipe.roi_config.get('spatial_rois', {})
    
    if not all(name in rois for name in spatial.NAMES):
        return {'error': 'Recipe missing required ROIs'}
    
    regions = spatial.extract(cloud, rois)
    
    report = {
        'recipe_id': recipe.pk,
        'pointcloud_token': pointcloud_token,
        'roi_quality': {},
        'optimization_suggestions': {},
        'overall_score': 0,
        'critical_issues': []
    }
    
    total_score = 0
    
    for name in spatial.NAMES:
        points = regions[name]
        
        # Analyze current quality
        quality = analyze_roi_quality(points, name)
        report['roi_quality'][name] = quality
        total_score += quality['quality_score']
        
        if quality['quality_score'] < 50:
            report['critical_issues'].append(f"{name}: 质量分数过低 ({quality['quality_score']:.0f}/100)")
        
        # Suggest optimization
        if quality['quality_score'] < 80:
            opt = suggest_roi_shrink(points, rois[name])
            if 'error' not in opt:
                report['optimization_suggestions'][name] = opt
    
    report['overall_score'] = total_score / 3
    
    return report


def print_roi_report(report):
    """Pretty-print ROI quality report."""
    print("\n" + "="*60)
    print(f"ROI Quality Report for Recipe #{report['recipe_id']}")
    print("="*60)
    
    print(f"\n综合质量评分: {report['overall_score']:.1f}/100")
    
    if report['critical_issues']:
        print("\n⚠️  严重问题:")
        for issue in report['critical_issues']:
            print(f"  • {issue}")
    
    print("\n各 ROI 详细分析:\n")
    
    for name, quality in report['roi_quality'].items():
        label = {'plane1': 'Π1 顶部横梁', 'plane2': 'Π2 左侧立柱', 'plane3': 'Π3 底部横梁'}[name]
        print(f"【{label}】")
        print(f"  质量评分: {quality['quality_score']:.1f}/100")
        print(f"  点数: {quality['point_count']}")
        print(f"  方差比: {quality['variance_ratio']:.2f}")
        print(f"  RMS 误差: {quality['rms_mm']:.1f} mm")
        print(f"  线性度: {quality['linearity']:.3f}")
        
        if quality['issues']:
            print("  问题:")
            for issue in quality['issues']:
                print(f"    ✗ {issue}")
        
        if quality['suggestions']:
            print("  建议:")
            for suggestion in quality['suggestions']:
                print(f"    → {suggestion}")
        
        # Optimization suggestion
        if name in report['optimization_suggestions']:
            opt = report['optimization_suggestions'][name]
            print(f"\n  🔧 自动优化建议:")
            print(f"    质量提升: {opt['old_quality_score']:.0f} → {opt['new_quality_score']:.0f}")
            print(f"    移除点数: {opt['points_removed']} ({opt['points_removed']*100//(opt['points_kept']+opt['points_removed'])}%)")
            print(f"    建议: {opt['recommendation']}")
        
        print()
    
    print("="*60 + "\n")
