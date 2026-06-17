#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海康威视相机采集 Python 示例

功能：
1. 枚举模式 - 自动搜索所有相机
2. IP 直连模式 - 指定 IP 地址直接连接
3. 多种图像格式 - PNG, JPEG, BMP, TIFF
4. 质量参数配置

注意：每次调用只拍摄一张照片

使用方法：
    python example.py
"""

import time
import chg_hik


def example_enumerate_mode():
    """示例 1：枚举模式 - 自动搜索所有相机"""
    start_time = time.time()
    print("=== 示例 1：枚举模式 ===\n")

    # 设置输出文件夹路径
    output_dir = "images"

    print(f"输出文件夹: {output_dir}\n")

    try:
        # 调用采集函数（不提供 camera_ip 和 pc_ip，自动使用枚举模式）
        result = chg_hik.capture_images(output_dir=output_dir)

        end_time = time.time()
        # 显示结果
        print("\n" + "=" * 50)
        print("采集结果:")
        print(f"  成功: {result['success']}")
        print(f"  找到相机数: {result.get('cameras_found', 'N/A')}")
        print(f"  成功初始化相机数: {result['cameras_initialized']}")
        print(f"  采集图片总数: {result['images_captured']}")
        print(f"  消息: {result['message']}")
        print(f"  耗时: {(end_time - start_time):.2f}秒")
        print("=" * 50)

        if result["success"]:
            print(f"\n✓ 采集成功！图片已保存到 '{output_dir}' 文件夹")
        else:
            print(f"\n✗ 采集失败: {result['message']}")

    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        return 1

    return 0


def example_direct_ip_mode():
    """示例 2：IP 直连模式 - 指定 IP 地址直接连接"""
    print("\n=== 示例 2：IP 直连模式 ===\n")

    # 相机的 IP 地址（请根据实际情况修改）
    camera_ip = "169.254.213.253"

    # PC 网卡的 IP 地址（请根据实际情况修改）
    pc_ip = "169.254.213.139"

    # 输出文件夹路径
    output_dir = "images_ip"

    print(f"相机 IP: {camera_ip}")
    print(f"PC 网卡 IP: {pc_ip}")
    print(f"输出文件夹: {output_dir}\n")

    try:
        # 调用采集函数（提供 camera_ip 和 pc_ip，自动使用 IP 直连模式）
        result = chg_hik.capture_images(
            output_dir=output_dir,
            camera_ip=camera_ip,
            pc_ip=pc_ip
        )

        # 显示结果
        print("\n" + "=" * 50)
        print("采集结果:")
        print(f"  成功: {result['success']}")
        print(f"  成功初始化相机数: {result['cameras_initialized']}")
        print(f"  采集图片总数: {result['images_captured']}")
        print(f"  消息: {result['message']}")
        print("=" * 50)

        if result["success"]:
            print(f"\n✓ 采集成功！图片已保存到 '{output_dir}' 文件夹")
        else:
            print(f"\n✗ 采集失败: {result['message']}")

    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        return 1

    return 0


def example_png():
    """示例 3：PNG 格式（无损压缩）"""
    print("\n=== 示例 3: PNG 格式 ===\n")

    result = chg_hik.capture_images(
        output_dir="images_png",
        format="PNG",
        quality=5  # PNG 质量: 0-9 (0=最快，9=最小文件)
    )

    print(f"\n结果: {result}")


def example_jpeg():
    """示例 4：JPEG 格式（有损压缩，适合照片）"""
    print("\n=== 示例 4: JPEG 格式 ===\n")

    result = chg_hik.capture_images(
        output_dir="images_jpeg",
        format="JPEG",  # 或 "JPG"
        quality=90  # JPEG 质量: 50-99 (值越高质量越好)
    )

    print(f"\n结果: {result}")


def example_bmp():
    """示例 5：BMP 格式（无压缩，文件较大）"""
    print("\n=== 示例 5: BMP 格式 ===\n")

    result = chg_hik.capture_images(
        output_dir="images_bmp",
        format="BMP",
        quality=0  # BMP 不使用质量参数
    )

    print(f"\n结果: {result}")


def example_ip_direct_jpeg():
    """示例 6：IP 直连 + JPEG 格式"""
    print("\n=== 示例 6: IP 直连 + JPEG 格式 ===\n")

    # 注意：需要替换为实际的相机 IP 和 PC IP
    camera_ip = "192.168.1.64"
    pc_ip = "192.168.1.100"

    result = chg_hik.capture_images(
        output_dir="images_ip_jpeg",
        format="JPEG",
        quality=85,
        camera_ip=camera_ip,
        pc_ip=pc_ip
    )

    print(f"\n结果: {result}")


def example_quality_comparison():
    """示例 7：质量对比（不同 JPEG 质量）"""
    print("\n=== 示例 7: JPEG 质量对比 ===\n")

    qualities = [50, 70, 90, 99]

    for quality in qualities:
        print(f"\n--- JPEG 质量: {quality} ---")
        result = chg_hik.capture_images(
            output_dir=f"images_jpeg_q{quality}",
            format="JPEG",
            quality=quality
        )
        print(f"采集状态: {'成功' if result['success'] else '失败'}")
        print(f"采集图片数: {result['images_captured']}")


def example_error_handling():
    """示例 8：错误处理"""
    print("\n=== 示例 8: 错误处理 ===\n")

    # 错误的格式名称
    try:
        result = chg_hik.capture_images(
            output_dir="test",
            format="GIF",  # 不支持的格式
            quality=5
        )
    except ValueError as e:
        print(f"✓ 捕获到预期的错误: {e}")

    # 错误的 JPEG 质量
    try:
        result = chg_hik.capture_images(
            output_dir="test",
            format="JPEG",
            quality=100  # 超出范围 (50-99)
        )
    except ValueError as e:
        print(f"✓ 捕获到预期的错误: {e}")

    # 错误的 PNG 质量
    try:
        result = chg_hik.capture_images(
            output_dir="test",
            format="PNG",
            quality=10  # 超出范围 (0-9)
        )
    except ValueError as e:
        print(f"✓ 捕获到预期的错误: {e}")

    # 参数不完整（只提供一个 IP）
    try:
        result = chg_hik.capture_images(
            output_dir="test",
            camera_ip="192.168.1.64"
            # 缺少 pc_ip
        )
    except ValueError as e:
        print(f"✓ 捕获到预期的错误: {e}")


def main():
    """主函数"""
    print("=== 海康威视相机采集 Python 示例 ===\n")
    print("请选择示例：")
    print("1. 枚举模式（自动搜索所有相机）")
    print("2. IP 直连模式（指定 IP 地址直接连接）")
    print("3. PNG 格式示例")
    print("4. JPEG 格式示例")
    print("5. BMP 格式示例")
    print("6. IP 直连 + JPEG 格式")
    print("7. JPEG 质量对比")
    print("8. 错误处理演示")

    choice = input("\n请输入选项 (1-8，默认 1): ").strip()

    if not choice:
        choice = "1"

    if choice == "1":
        return example_enumerate_mode()
    elif choice == "2":
        return example_direct_ip_mode()
    elif choice == "3":
        return example_png()
    elif choice == "4":
        return example_jpeg()
    elif choice == "5":
        return example_bmp()
    elif choice == "6":
        return example_ip_direct_jpeg()
    elif choice == "7":
        return example_quality_comparison()
    elif choice == "8":
        return example_error_handling()
    else:
        print("无效的选项，使用默认枚举模式")
        return example_enumerate_mode()


if __name__ == "__main__":
    exit(main())
