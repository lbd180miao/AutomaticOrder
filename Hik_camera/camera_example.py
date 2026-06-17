#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海康威视相机 Camera 类示例

使用方法：
    python camera_example.py
"""

import time
import chg_hik


def example_context_manager_ip():
    """示例 1：使用上下文管理器 - IP 直连模式（推荐）"""
    print("=== 示例 1：上下文管理器 + IP 直连 ===\n")

    camera_ip = "169.254.213.253"
    pc_ip = "169.254.213.139"

    # 使用 with 语句自动管理相机打开和关闭
    with chg_hik.Camera(output_dir="images_fast") as cam:
        # 打开相机（耗时 ~2-3秒，只需一次）
        cam.open(camera_ip=camera_ip, pc_ip=pc_ip)

        # 连续拍照（每次只需 ~100-200ms）
        print("\n开始连续拍照...")
        for i in range(10):
            start = time.time()
            img_path = cam.capture()
            elapsed = time.time() - start
            print(f"  [{i+1}/10] 拍照耗时: {elapsed:.3f}秒 - 保存到: {img_path}")

    print("\n✓ 相机已自动关闭")


def example_context_manager_enum():
    """示例 2：使用上下文管理器 - 枚举模式"""
    print("\n=== 示例 2：上下文管理器 + 枚举模式 ===\n")

    # 使用 with 语句自动管理相机打开和关闭
    with chg_hik.Camera(output_dir="images_enum") as cam:
        # 打开相机（自动枚举第一个相机）
        cam.open()

        # 连续拍照
        print("\n开始连续拍照...")
        for i in range(5):
            start = time.time()
            img_path = cam.capture()
            elapsed = time.time() - start
            print(f"  [{i+1}/5] 拍照耗时: {elapsed:.3f}秒 - 保存到: {img_path}")

    print("\n✓ 相机已自动关闭")


def example_manual_control():
    """示例 3：手动控制（不使用上下文管理器）"""
    print("\n=== 示例 3：手动控制相机 ===\n")

    camera_ip = "169.254.213.253"
    pc_ip = "169.254.213.139"

    # 创建相机实例
    cam = chg_hik.Camera(
        output_dir="images_manual",
        format="JPEG",  # 使用 JPEG 格式
        quality=90      # 高质量
    )

    try:
        # 打开相机
        cam.open(camera_ip=camera_ip, pc_ip=pc_ip)

        # 拍照
        print("\n开始拍照...")
        for i in range(3):
            img_path = cam.capture()
            print(f"  ✓ 已保存: {img_path}")

    finally:
        # 手动关闭相机
        cam.close_camera()
        print("\n✓ 相机已关闭")


def example_format_comparison():
    """示例 4：不同格式对比"""
    print("\n=== 示例 4：不同图像格式对比 ===\n")

    camera_ip = "169.254.213.253"
    pc_ip = "169.254.213.139"

    formats = [
        ("PNG", 5),
        ("JPEG", 50),
        ("BMP", 0),
    ]

    for fmt, quality in formats:
        print(f"\n--- 测试 {fmt} 格式 ---")
        with chg_hik.Camera(output_dir=f"images_{fmt.lower()}", format=fmt, quality=quality) as cam:
            cam.open(camera_ip=camera_ip, pc_ip=pc_ip)

            start = time.time()
            img_path = cam.capture()
            elapsed = time.time() - start

            print(f"  格式: {fmt}, 质量: {quality}")
            print(f"  拍照耗时: {elapsed:.3f}秒")
            print(f"  保存到: {img_path}")


def example_high_speed_capture():
    """示例 5：高速连拍（100张）"""
    print("\n=== 示例 5：高速连拍测试 ===\n")

    camera_ip = "169.254.213.253"
    pc_ip = "169.254.213.139"
    num_images = 100

    with chg_hik.Camera(output_dir="images_burst") as cam:
        # 初始化
        print("初始化相机...")
        init_start = time.time()
        cam.open(camera_ip=camera_ip, pc_ip=pc_ip)
        init_time = time.time() - init_start
        print(f"✓ 初始化完成，耗时: {init_time:.2f}秒\n")

        # 连拍
        print(f"开始连拍 {num_images} 张...")
        capture_start = time.time()

        for i in range(num_images):
            cam.capture()
            if (i + 1) % 10 == 0:
                print(f"  已完成: {i+1}/{num_images}")

        capture_time = time.time() - capture_start

        print(f"\n✓ 连拍完成！")
        print(f"  总耗时: {capture_time:.2f}秒")
        print(f"  平均每张: {(capture_time/num_images)*1000:.0f}ms")
        print(f"  速度: {num_images/capture_time:.1f} 张/秒")


def example_comparison_old_vs_new():
    """示例 6：新旧 API 对比"""
    print("\n=== 示例 6：新旧 API 性能对比 ===\n")

    camera_ip = "169.254.213.253"
    pc_ip = "169.254.213.139"
    num_test = 5

    # 旧方式：每次都初始化和关闭
    print("【旧方式】每次调用 capture_images():")
    old_start = time.time()
    for i in range(num_test):
        result = chg_hik.capture_images(
            output_dir="images_old",
            camera_ip=camera_ip,
            pc_ip=pc_ip
        )
    old_time = time.time() - old_start
    print(f"  拍摄 {num_test} 张耗时: {old_time:.2f}秒")
    print(f"  平均每张: {old_time/num_test:.2f}秒\n")

    # 新方式：只初始化一次
    print("【新方式】使用 Camera 类:")
    new_start = time.time()
    with chg_hik.Camera(output_dir="images_new") as cam:
        cam.open(camera_ip=camera_ip, pc_ip=pc_ip)
        for i in range(num_test):
            cam.capture()
    new_time = time.time() - new_start
    print(f"  拍摄 {num_test} 张耗时: {new_time:.2f}秒")
    print(f"  平均每张: {new_time/num_test:.2f}秒\n")

    # 性能提升
    speedup = old_time / new_time
    time_saved = old_time - new_time
    print(f"【性能提升】")
    print(f"  速度提升: {speedup:.1f}x")
    print(f"  节省时间: {time_saved:.2f}秒")
    print(f"  效率提升: {((speedup-1)*100):.0f}%")


def example_manual_exposure_gain():
    """示例 7：手动设置曝光时间和增益"""
    print("\n=== 示例 7：手动设置曝光时间和增益 ===\n")

    camera_ip = "169.254.213.253"
    pc_ip = "169.254.213.139"

    # 创建配置
    config = chg_hik.CameraConfig()
    config.exposure_time = 149580  # 5000微秒 = 5毫秒
    config.gain = 10             # 12.5 dB

    print(f"相机配置：")
    print(f"  曝光时间: {config.exposure_time} μs ({config.exposure_time/1000:.1f} ms)")
    print(f"  增益值: {config.gain} dB\n")

    with chg_hik.Camera(output_dir="images_manual_params") as cam:
        # 打开相机
        cam.open(camera_ip=camera_ip, pc_ip=pc_ip)

        # 应用配置
        print("应用相机参数配置...")
        cam.configure(config)
        print("✓ 参数配置成功\n")

        # 拍照
        print("开始拍照...")
        img_path = cam.capture()
        print(f"  ✓ 已保存: {img_path}")

    print("\n✓ 完成")


def example_auto_exposure_gain():
    """示例 8：启用自动曝光和自动增益"""
    print("\n=== 示例 8：启用自动曝光和自动增益 ===\n")

    camera_ip = "169.254.213.253"
    pc_ip = "169.254.213.139"

    # 创建配置 - 启用自动模式
    config = chg_hik.CameraConfig()
    config.exposure_auto = True  # 自动曝光
    config.gain_auto = True      # 自动增益

    print(f"相机配置：")
    print(f"  自动曝光: {'开启' if config.exposure_auto else '关闭'}")
    print(f"  自动增益: {'开启' if config.gain_auto else '关闭'}\n")

    with chg_hik.Camera(output_dir="images_auto") as cam:
        # 打开相机
        cam.open(camera_ip=camera_ip, pc_ip=pc_ip)

        # 应用配置
        print("应用相机参数配置...")
        cam.configure(config)
        print("✓ 参数配置成功\n")

        # 拍照
        print("开始拍照...")
        for i in range(3):
            img_path = cam.capture()
            print(f"  ✓ 已保存: {img_path}")

    print("\n✓ 完成")


def example_mixed_mode():
    """示例 9：混合模式（手动曝光 + 自动增益）"""
    print("\n=== 示例 9：混合模式（手动曝光 + 自动增益）===\n")

    camera_ip = "169.254.213.253"
    pc_ip = "169.254.213.139"

    # 创建配置 - 混合模式
    config = chg_hik.CameraConfig()
    config.exposure_time = 8000.0  # 手动曝光 8ms
    config.gain_auto = True        # 自动增益

    print(f"相机配置（混合模式）：")
    print(f"  曝光时间: {config.exposure_time} μs (手动)")
    print(f"  自动增益: {'开启' if config.gain_auto else '关闭'}\n")

    with chg_hik.Camera(output_dir="images_mixed") as cam:
        # 打开相机
        cam.open(camera_ip=camera_ip, pc_ip=pc_ip)

        # 应用配置
        print("应用相机参数配置...")
        cam.configure(config)
        print("✓ 参数配置成功\n")

        # 拍照
        print("开始拍照...")
        for i in range(3):
            img_path = cam.capture()
            print(f"  ✓ 已保存: {img_path}")

    print("\n✓ 完成")


def example_compare_exposure_settings():
    """示例 10：对比不同曝光参数的效果"""
    print("\n=== 示例 10：对比不同曝光参数 ===\n")

    camera_ip = "169.254.213.253"
    pc_ip = "169.254.213.139"

    # 测试不同的曝光时间
    exposure_times = [
        1000.0,   # 1ms - 短曝光（快速运动）
        5000.0,   # 5ms - 中等曝光
        10000.0,  # 10ms - 长曝光（暗环境）
    ]

    for exp_time in exposure_times:
        print(f"\n--- 测试曝光时间: {exp_time/1000:.1f}ms ---")

        config = chg_hik.CameraConfig()
        config.exposure_time = exp_time
        config.gain = 10.0  # 固定增益

        with chg_hik.Camera(output_dir=f"images_exp_{int(exp_time)}") as cam:
            cam.open(camera_ip=camera_ip, pc_ip=pc_ip)
            cam.configure(config)

            img_path = cam.capture()
            print(f"  ✓ 已保存: {img_path}")

    print("\n✓ 对比测试完成")


def example_only_exposure():
    """示例 11：仅设置曝光时间（增益保持默认）"""
    print("\n=== 示例 11：仅设置曝光时间 ===\n")

    camera_ip = "169.254.213.253"
    pc_ip = "169.254.213.139"

    # 只设置曝光时间，增益保持默认
    config = chg_hik.CameraConfig()
    config.exposure_time = 6000.0  # 6ms

    print(f"相机配置：")
    print(f"  曝光时间: {config.exposure_time} μs")
    print(f"  增益: 保持默认值\n")

    with chg_hik.Camera(output_dir="images_exp_only") as cam:
        cam.open(camera_ip=camera_ip, pc_ip=pc_ip)
        cam.configure(config)

        print("开始拍照...")
        img_path = cam.capture()
        print(f"  ✓ 已保存: {img_path}")

    print("\n✓ 完成")


def main():
    """主函数"""
    print("=== 海康威视相机 Camera 类示例 ===\n")
    print("请选择示例：")
    print("1. 上下文管理器 + IP 直连（推荐）")
    print("2. 上下文管理器 + 枚举模式")
    print("3. 手动控制相机")
    print("4. 不同格式对比")
    print("5. 高速连拍测试（100张）")
    print("6. 新旧 API 性能对比")
    print("7. 手动设置曝光和增益 ⭐NEW")
    print("8. 启用自动曝光和增益 ⭐NEW")
    print("9. 混合模式（手动曝光+自动增益）⭐NEW")
    print("10. 对比不同曝光参数效果 ⭐NEW")
    print("11. 仅设置曝光时间 ⭐NEW")

    choice = input("\n请输入选项 (1-11，默认 1): ").strip()

    if not choice:
        choice = "1"

    if choice == "1":
        return example_context_manager_ip()
    elif choice == "2":
        return example_context_manager_enum()
    elif choice == "3":
        return example_manual_control()
    elif choice == "4":
        return example_format_comparison()
    elif choice == "5":
        return example_high_speed_capture()
    elif choice == "6":
        return example_comparison_old_vs_new()
    elif choice == "7":
        return example_manual_exposure_gain()
    elif choice == "8":
        return example_auto_exposure_gain()
    elif choice == "9":
        return example_mixed_mode()
    elif choice == "10":
        return example_compare_exposure_settings()
    elif choice == "11":
        return example_only_exposure()
    else:
        print("无效的选项，使用默认示例")
        return example_context_manager_ip()


if __name__ == "__main__":
    main()
