"""快速验证泡棉检测修复的脚本

使用方法:
python test_foam_fix.py path/to/no_foam_image.jpg

此脚本会:
1. 加载你的无泡棉图片
2. 运行修复后的检测算法
3. 显示检测结果（应该是"泡棉缺失"）
"""
import sys
import cv2
import os
import django

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.vision.algorithms.foam_inspector import FoamInspector


def test_foam_detection(image_path):
    """测试泡棉检测"""
    # 读取图片
    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ 无法读取图片: {image_path}")
        return False
    
    print(f"✓ 已读取图片: {image.shape[1]}x{image.shape[0]} 像素")
    
    # 创建检测器
    inspector = FoamInspector(simulate=False)
    
    # 配置检测参数（70%覆盖率阈值）
    config = {
        'coverage_threshold': 0.70,
        'score_threshold': 0.8,
        'max_offset_px': 30,
    }
    
    print("\n开始检测...")
    print(f"配置: 覆盖率阈值={config['coverage_threshold']*100}%")
    
    # 执行检测
    result = inspector.inspect(
        position_index=0,
        inspection_config=config,
        image=image,
        camera_image_path=image_path,
        simulated_pass=True  # 此参数在真实图像模式下被忽略
    )
    
    # 显示结果
    print("\n" + "="*60)
    print("检测结果:")
    print("="*60)
    print(f"泡棉存在 (is_present): {result['is_present']}")
    print(f"位置对齐 (is_aligned): {result['is_aligned']}")
    print(f"边缘起翘 (has_lifted_edge): {result['has_lifted_edge']}")
    print(f"缺陷类型 (defect_type): {result['defect_type']}")
    print(f"综合评分 (score): {result['score']:.2f}")
    print(f"覆盖率 (coverage_ratio): {result['coverage_ratio']:.2%}")
    print(f"最终判定 (is_passed): {'✅ 合格' if result['is_passed'] else '❌ 不合格'}")
    print("="*60)
    
    # 显示结果图路径
    print(f"\n原始图片已保存: {result['original_image']}")
    print(f"结果图片已保存: {result['result_image']}")
    
    # 如果有侧面详情（使用配方ROI时）
    if 'sides' in result:
        print("\n侧面检测详情:")
        for side, data in result['sides'].items():
            print(f"  {side}: 存在={data['is_present']}, 覆盖率={data['coverage_ratio']:.2%}")
    
    # 验证预期结果
    print("\n验证:")
    if image_path and 'no_foam' in image_path.lower():
        # 如果文件名包含 no_foam，应该检测为不合格
        expected = False
        actual = result['is_passed']
        if actual == expected:
            print(f"✅ 正确! 无泡棉图片被正确识别为不合格")
            return True
        else:
            print(f"❌ 错误! 无泡棉图片被误判为合格")
            return False
    else:
        print(f"ℹ️  请检查结果是否符合实际情况")
        return True


def main():
    if len(sys.argv) < 2:
        print("使用方法: python test_foam_fix.py <图片路径>")
        print("\n示例:")
        print("  python test_foam_fix.py no_foam_bumper.jpg")
        print("  python test_foam_fix.py media/temp_uploads/test_image.jpg")
        return
    
    image_path = sys.argv[1]
    
    if not os.path.exists(image_path):
        print(f"❌ 文件不存在: {image_path}")
        return
    
    success = test_foam_detection(image_path)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
