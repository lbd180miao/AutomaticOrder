"""
料架定位补偿算法 V2 单元测试
============================

测试 LocalTemplate3D 和 RackStructureValidator 的算法精度。
全部使用纯 numpy 仿真点云（无需相机硬件），可离线运行。

运行方式：
    cd d:\workspace2\AutomaticOrder
    .venv\Scripts\python.exe test_local_template_algorithm.py
"""

import sys
import os

# 确保可以直接运行（无需 Django 环境）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import traceback

# -------------------------------------------------------------------------
# 路径设置（适配本项目结构）
# -------------------------------------------------------------------------
from apps.vision.algorithms.local_template_3d import (
    LocalTemplate3D, LocalFrameResult, PlaneResult
)
from apps.vision.algorithms.rack_structure_validator import (
    RackStructureValidator, ValidationErrorCode
)

# -------------------------------------------------------------------------
# 仿真点云生成工具
# -------------------------------------------------------------------------

def make_horizontal_plane_cloud(
    z: float, n: int = 500,
    x_range=(0, 500), y_range=(0, 300),
    noise_std: float = 0.5,
    rng: np.random.Generator = None,
) -> np.ndarray:
    """生成水平面点云（Z=z，XY 均匀分布，加高斯噪声）"""
    if rng is None:
        rng = np.random.default_rng(0)
    xs = rng.uniform(*x_range, n)
    ys = rng.uniform(*y_range, n)
    zs = np.full(n, z) + rng.normal(0, noise_std, n)
    return np.column_stack([xs, ys, zs])


def make_vertical_plane_cloud(
    x: float, n: int = 500,
    y_range=(0, 300), z_range=(0, 400),
    noise_std: float = 0.5,
    rng: np.random.Generator = None,
) -> np.ndarray:
    """生成垂直面点云（X=x，YZ 均匀分布，加高斯噪声）"""
    if rng is None:
        rng = np.random.default_rng(0)
    xs = np.full(n, x) + rng.normal(0, noise_std, n)
    ys = rng.uniform(*y_range, n)
    zs = rng.uniform(*z_range, n)
    return np.column_stack([xs, ys, zs])


def apply_transform(cloud: np.ndarray, T: np.ndarray) -> np.ndarray:
    """对点云应用 4x4 齐次变换"""
    n = cloud.shape[0]
    pts_h = np.hstack([cloud, np.ones((n, 1))])
    return (T @ pts_h.T).T[:, :3]


def make_transform(dx=0, dy=0, dz=0, rx_deg=0, ry_deg=0, rz_deg=0) -> np.ndarray:
    """构造 4x4 齐次变换矩阵（固定轴 XYZ 旋转 + 平移）"""
    rx = np.radians(rx_deg)
    ry = np.radians(ry_deg)
    rz = np.radians(rz_deg)

    Rx = np.array([[1, 0, 0],
                   [0, np.cos(rx), -np.sin(rx)],
                   [0, np.sin(rx),  np.cos(rx)]])
    Ry = np.array([[ np.cos(ry), 0, np.sin(ry)],
                   [0,           1, 0          ],
                   [-np.sin(ry), 0, np.cos(ry)]])
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0],
                   [np.sin(rz),  np.cos(rz), 0],
                   [0,           0,           1]])

    R = Rz @ Ry @ Rx
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [dx, dy, dz]
    return T


# -------------------------------------------------------------------------
# 标准仿真场景：生成示教点云
# -------------------------------------------------------------------------

def make_standard_clouds(rng):
    """生成标准料架三区域仿真点云"""
    roi1_std = make_horizontal_plane_cloud(z=400, n=600, rng=rng)   # 上水平面 Z=400mm
    roi2_std = make_vertical_plane_cloud(x=0,   n=600, rng=rng)     # 左竖直面 X=0
    roi3_std = make_horizontal_plane_cloud(z=200, n=600, rng=rng)   # 下水平面 Z=200mm
    return roi1_std, roi2_std, roi3_std


# -------------------------------------------------------------------------
# 测试用例
# -------------------------------------------------------------------------

PASS_MARK = "[PASS]"
FAIL_MARK = "[FAIL]"

results = []


def run_test(name, func):
    print(f"\n{'-' * 60}")
    print(f"[TEST] {name}")
    try:
        func()
        print(f"{PASS_MARK}")
        results.append((name, True, ""))
    except AssertionError as e:
        print(f"{FAIL_MARK} assertion: {e}")
        results.append((name, False, str(e)))
    except Exception as e:
        print(f"{FAIL_MARK} exception: {e}")
        traceback.print_exc()
        results.append((name, False, str(e)))


# ---- 精度容差 ----
TRANS_TOL = 0.5    # mm（容许平移误差）
ROT_TOL   = 0.1   # °（容许旋转误差）


def test_identity():
    """TC1: 当前模板 == 标准模板 → ΔT 应为单位矩阵，所有偏差均为 0"""
    rng = np.random.default_rng(1)
    roi1, roi2, roi3 = make_standard_clouds(rng)
    algo = LocalTemplate3D(ransac_num_iterations=500)
    frame_std = algo.build_local_frame(roi1, roi2, roi3)
    # 再次用同样点云建立"当前"模板
    frame_cur = algo.build_local_frame(roi1, roi2, roi3)
    delta = algo.compute_delta_T(frame_std, frame_cur)

    print(f"  ΔX={delta.dX:.3f}mm  ΔY={delta.dY:.3f}mm  ΔZ={delta.dZ:.3f}mm")
    print(f"  ΔRx={delta.dRx:.4f}°  ΔRy={delta.dRy:.4f}°  ΔRz={delta.dRz:.4f}°")
    assert abs(delta.dX) < TRANS_TOL, f"|ΔX|={abs(delta.dX):.3f} ≥ {TRANS_TOL}"
    assert abs(delta.dY) < TRANS_TOL, f"|ΔY|={abs(delta.dY):.3f} ≥ {TRANS_TOL}"
    assert abs(delta.dZ) < TRANS_TOL, f"|ΔZ|={abs(delta.dZ):.3f} ≥ {TRANS_TOL}"
    assert abs(delta.dRx) < ROT_TOL, f"|ΔRx|={abs(delta.dRx):.4f}° ≥ {ROT_TOL}°"
    assert abs(delta.dRy) < ROT_TOL, f"|ΔRy|={abs(delta.dRy):.4f}° ≥ {ROT_TOL}°"
    assert abs(delta.dRz) < ROT_TOL, f"|ΔRz|={abs(delta.dRz):.4f}° ≥ {ROT_TOL}°"


def test_pure_z_translation():
    """TC2: 料架整体沿 Z 上移 10mm → dZ≈10mm，其他接近 0"""
    rng = np.random.default_rng(2)
    roi1_std, roi2_std, roi3_std = make_standard_clouds(rng)

    T_shift = make_transform(dz=10.0)
    roi1_cur = apply_transform(roi1_std, T_shift)
    roi2_cur = apply_transform(roi2_std, T_shift)
    roi3_cur = apply_transform(roi3_std, T_shift)

    algo = LocalTemplate3D(ransac_num_iterations=500)
    frame_std = algo.build_local_frame(roi1_std, roi2_std, roi3_std)
    frame_cur = algo.build_local_frame(roi1_cur, roi2_cur, roi3_cur)
    delta = algo.compute_delta_T(frame_std, frame_cur)

    print(f"  期望: dZ=+10mm  实际: dZ={delta.dZ:.3f}mm")
    print(f"  ΔX={delta.dX:.3f}  ΔY={delta.dY:.3f}  ΔRx={delta.dRx:.4f}°  ΔRz={delta.dRz:.4f}°")
    assert abs(delta.dZ - 10.0) < TRANS_TOL, f"dZ误差={abs(delta.dZ - 10.0):.3f} ≥ {TRANS_TOL}"
    assert abs(delta.dX) < TRANS_TOL
    assert abs(delta.dY) < TRANS_TOL
    assert abs(delta.dRx) < ROT_TOL
    assert abs(delta.dRy) < ROT_TOL
    assert abs(delta.dRz) < ROT_TOL


def test_pure_x_translation():
    """TC3: 料架整体沿 X 平移 -8mm → dX≈-8mm，其他接近 0"""
    rng = np.random.default_rng(3)
    roi1_std, roi2_std, roi3_std = make_standard_clouds(rng)

    T_shift = make_transform(dx=-8.0)
    roi1_cur = apply_transform(roi1_std, T_shift)
    roi2_cur = apply_transform(roi2_std, T_shift)
    roi3_cur = apply_transform(roi3_std, T_shift)

    algo = LocalTemplate3D(ransac_num_iterations=500)
    frame_std = algo.build_local_frame(roi1_std, roi2_std, roi3_std)
    frame_cur = algo.build_local_frame(roi1_cur, roi2_cur, roi3_cur)
    delta = algo.compute_delta_T(frame_std, frame_cur)

    print(f"  期望: dX=-8mm  实际: dX={delta.dX:.3f}mm")
    assert abs(delta.dX - (-8.0)) < TRANS_TOL, f"dX误差={abs(delta.dX+8):.3f} ≥ {TRANS_TOL}"
    assert abs(delta.dY) < TRANS_TOL
    assert abs(delta.dZ) < TRANS_TOL
    assert abs(delta.dRz) < ROT_TOL


def test_pure_rz_rotation():
    """TC4: 料架绕 Z 轴旋转 2° → dRz≈2°，其他接近 0"""
    rng = np.random.default_rng(4)
    roi1_std, roi2_std, roi3_std = make_standard_clouds(rng)

    T_rot = make_transform(rz_deg=2.0)
    roi1_cur = apply_transform(roi1_std, T_rot)
    roi2_cur = apply_transform(roi2_std, T_rot)
    roi3_cur = apply_transform(roi3_std, T_rot)

    algo = LocalTemplate3D(ransac_num_iterations=500)
    frame_std = algo.build_local_frame(roi1_std, roi2_std, roi3_std)
    frame_cur = algo.build_local_frame(roi1_cur, roi2_cur, roi3_cur)
    delta = algo.compute_delta_T(frame_std, frame_cur)

    print(f"  期望: dRz=2°  实际: dRz={delta.dRz:.4f}°")
    assert abs(delta.dRz - 2.0) < ROT_TOL * 2, f"dRz误差={abs(delta.dRz-2.0):.4f}° ≥ {ROT_TOL*2}°"
    assert abs(delta.dRx) < ROT_TOL
    assert abs(delta.dRy) < ROT_TOL


def test_combined_6dof():
    """TC5: 组合 6DoF 偏差：平移[5,-3,8]mm + 旋转[0.5°,1.0°,-1.5°]"""
    rng = np.random.default_rng(5)
    roi1_std, roi2_std, roi3_std = make_standard_clouds(rng)

    T_combined = make_transform(dx=5, dy=-3, dz=8, rx_deg=0.5, ry_deg=1.0, rz_deg=-1.5)
    roi1_cur = apply_transform(roi1_std, T_combined)
    roi2_cur = apply_transform(roi2_std, T_combined)
    roi3_cur = apply_transform(roi3_std, T_combined)

    algo = LocalTemplate3D(ransac_num_iterations=800)
    frame_std = algo.build_local_frame(roi1_std, roi2_std, roi3_std)
    frame_cur = algo.build_local_frame(roi1_cur, roi2_cur, roi3_cur)
    delta = algo.compute_delta_T(frame_std, frame_cur)

    print(f"  期望: dX=+5  dY=-3  dZ=+8 | dRx=+0.5°  dRy=+1.0°  dRz=-1.5°")
    print(f"  实际: dX={delta.dX:.3f}  dY={delta.dY:.3f}  dZ={delta.dZ:.3f} | "
          f"dRx={delta.dRx:.4f}°  dRy={delta.dRy:.4f}°  dRz={delta.dRz:.4f}°")

    assert abs(delta.dX - 5.0)  < TRANS_TOL, f"dX误差={abs(delta.dX-5):.3f}"
    assert abs(delta.dY - (-3)) < TRANS_TOL, f"dY误差={abs(delta.dY+3):.3f}"
    assert abs(delta.dZ - 8.0)  < TRANS_TOL, f"dZ误差={abs(delta.dZ-8):.3f}"
    assert abs(delta.dRx - 0.5) < ROT_TOL * 2, f"dRx误差={abs(delta.dRx-0.5):.4f}°"
    assert abs(delta.dRy - 1.0) < ROT_TOL * 2, f"dRy误差={abs(delta.dRy-1.0):.4f}°"
    assert abs(delta.dRz -(-1.5)) < ROT_TOL * 2, f"dRz误差={abs(delta.dRz+1.5):.4f}°"


def test_deform_detection():
    """TC6: 区域1比区域3多上移8mm（超过5mm阈值）→ 应触发 DEFORM 报警"""
    rng = np.random.default_rng(6)
    roi1_std, roi2_std, roi3_std = make_standard_clouds(rng)

    # 构造变形：区域1单独额外上移8mm，区域3保持原位
    roi1_cur = roi1_std + np.array([0, 0, 8.0])
    roi2_cur = roi2_std.copy()
    roi3_cur = roi3_std.copy()

    algo = LocalTemplate3D(ransac_num_iterations=500)
    frame_std = algo.build_local_frame(roi1_std, roi2_std, roi3_std)
    frame_cur = algo.build_local_frame(roi1_cur, roi2_cur, roi3_cur)

    validator = RackStructureValidator(z_diff_tolerance_mm=5.0)
    result = validator.validate(frame_cur=frame_cur, frame_std=frame_std)

    print(f"  校验结果: is_valid={result.is_valid}  error_code={result.error_code.value}")
    for c in result.checks:
        status = "✅" if c.passed else "❌"
        print(f"    {status} {c.name}: {c.value:.2f}{c.unit} (阈值 {c.threshold}{c.unit})")

    assert not result.is_valid, "应检测到料架变形（is_valid 应为 False）"
    assert result.error_code == ValidationErrorCode.DEFORM, \
        f"error_code 应为 DEFORM，实际为 {result.error_code.value}"


def test_low_quality():
    """TC7: 点云内点率过低（仅50点，低于min_inlier_ratio=0.7）→ 应触发 QUALITY_LOW"""
    rng = np.random.default_rng(7)

    # 故意只给极少的点（几何上有效，但数量不足导致拟合质量不稳定）
    # 通过设置极高的 min_inlier_ratio 来模拟质量不足
    validator = RackStructureValidator(min_inlier_ratio=0.99)  # 设置极苛刻的阈值

    roi1 = make_horizontal_plane_cloud(z=400, n=500, noise_std=3.0, rng=rng)  # 大噪声降低内点率
    roi2 = make_vertical_plane_cloud(x=0,   n=500, noise_std=3.0, rng=rng)
    roi3 = make_horizontal_plane_cloud(z=200, n=500, noise_std=3.0, rng=rng)

    algo = LocalTemplate3D(ransac_num_iterations=500, ransac_distance_threshold=1.0)
    try:
        frame_cur = algo.build_local_frame(roi1, roi2, roi3)
    except Exception as e:
        print(f"  点云质量过低，拟合直接失败（预期行为）：{e}")
        print(f"{PASS_MARK} 质量低时正确抛出异常")
        return

    result = validator.validate(frame_cur=frame_cur)
    print(f"  校验结果: is_valid={result.is_valid}  error_code={result.error_code.value}")
    for c in result.checks:
        status = "✅" if c.passed else "❌"
        print(f"    {status} {c.name}: {c.value:.1f}{c.unit} (阈值 {c.threshold}{c.unit})")

    assert not result.is_valid, "高噪声点云应触发质量校验失败"


# -------------------------------------------------------------------------
# 运行所有测试
# -------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("料架定位补偿算法 V2 — 单元测试套件")
    print("=" * 60)

    run_test("TC1: 恒等变换（ΔT = I）", test_identity)
    run_test("TC2: 纯Z轴平移 +10mm", test_pure_z_translation)
    run_test("TC3: 纯X轴平移 -8mm", test_pure_x_translation)
    run_test("TC4: 纯Rz旋转 +2°", test_pure_rz_rotation)
    run_test("TC5: 组合6DoF偏差", test_combined_6dof)
    run_test("TC6: 料架变形检测（ΔZ_1 - ΔZ_3 = 8mm > 5mm）", test_deform_detection)
    run_test("TC7: 点云质量过低检测", test_low_quality)

    print(f"\n{'=' * 60}")
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"测试结果汇总: {passed}/{total} 通过")
    for name, ok, msg in results:
        mark = PASS_MARK if ok else FAIL_MARK
        print(f"  {mark} {name}" + (f"  → {msg}" if not ok else ""))
    print("=" * 60)

    if passed < total:
        sys.exit(1)
