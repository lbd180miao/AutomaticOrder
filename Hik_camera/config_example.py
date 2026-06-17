#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CameraConfig 配置示例 - 快速入门

演示如何使用 CameraConfig 来设置相机的曝光时间和增益参数
"""

import chg_hik


def simple_example():
    """最简单的示例 - 设置曝光和增益"""
    print("=== 快速示例：设置曝光时间和增益 ===\n")

    # 1. 创建配置对象
    config = chg_hik.CameraConfig()

    # 2. 设置参数
    config.exposure_time = 5000.0  # 曝光时间 5000μs = 5ms
    config.gain = 12.5             # 增益 12.5dB

    print(f"配置参数：")
    print(f"  曝光时间: {config.exposure_time} μs")
    print(f"  增益值: {config.gain} dB\n")

    # 3. 使用相机
    with chg_hik.Camera(output_dir="images") as cam:
        # 打开相机（根据你的实际情况修改IP地址）
        cam.open(camera_ip="192.168.1.64", pc_ip="192.168.1.100")

        # 应用配置
        cam.configure(config)
        print("✓ 参数已配置\n")

        # 拍照
        img_path = cam.capture()
        print(f"✓ 照片已保存: {img_path}")


def example_auto_mode():
    """示例：启用自动曝光和自动增益"""
    print("\n=== 示例：启用自动模式 ===\n")

    config = chg_hik.CameraConfig()
    config.exposure_auto = True  # 自动曝光
    config.gain_auto = True      # 自动增益

    print("配置：自动曝光 + 自动增益\n")

    with chg_hik.Camera(output_dir="images") as cam:
        cam.open(camera_ip="192.168.1.64", pc_ip="192.168.1.100")
        cam.configure(config)

        img_path = cam.capture()
        print(f"✓ 照片已保存: {img_path}")


def example_only_exposure():
    """示例：只设置曝光时间"""
    print("\n=== 示例：只设置曝光时间 ===\n")

    config = chg_hik.CameraConfig()
    config.exposure_time = 8000.0  # 只设置曝光，增益保持默认

    print(f"配置：曝光时间 = {config.exposure_time} μs\n")

    with chg_hik.Camera(output_dir="images") as cam:
        cam.open(camera_ip="192.168.1.64", pc_ip="192.168.1.100")
        cam.configure(config)

        img_path = cam.capture()
        print(f"✓ 照片已保存: {img_path}")


def example_dynamic_config():
    """示例：动态调整参数"""
    print("\n=== 示例：动态调整参数 ===\n")

    with chg_hik.Camera(output_dir="images_dynamic") as cam:
        cam.open(camera_ip="192.168.1.64", pc_ip="192.168.1.100")

        # 测试不同的曝光时间
        exposure_times = [3000.0, 6000.0, 9000.0]

        for i, exp_time in enumerate(exposure_times, 1):
            config = chg_hik.CameraConfig()
            config.exposure_time = exp_time
            config.gain = 10.0

            cam.configure(config)
            print(f"[{i}/3] 曝光={exp_time/1000:.1f}ms, 增益=10dB")

            img_path = cam.capture()
            print(f"  ✓ 已保存: {img_path}\n")


if __name__ == "__main__":
    print("=" * 60)
    print("CameraConfig 快速入门示例")
    print("=" * 60)
    print("\n注意：请修改代码中的 camera_ip 和 pc_ip 为你的实际IP地址\n")

    # 运行简单示例
    simple_example()

    # 如需查看更多示例，取消下面的注释：
    # example_auto_mode()
    # example_only_exposure()
    # example_dynamic_config()

    print("\n" + "=" * 60)
    print("提示：更多示例请查看 camera_example.py")
    print("=" * 60)
