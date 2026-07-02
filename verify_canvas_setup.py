#!/usr/bin/env python
"""
验证 Canvas 绘制 ROI 功能的文件完整性
"""

import os
import sys

def check_file(path, description):
    """检查文件是否存在"""
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"✅ {description}: {size:,} bytes")
        return True
    else:
        print(f"❌ {description}: 文件不存在！")
        return False

def check_content(path, keyword, description):
    """检查文件内容是否包含关键字"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            if keyword in content:
                print(f"✅ {description}: 包含 '{keyword}'")
                return True
            else:
                print(f"❌ {description}: 未找到 '{keyword}'")
                return False
    except Exception as e:
        print(f"❌ {description}: 读取失败 - {e}")
        return False

def main():
    print("=" * 70)
    print("Canvas 绘制 ROI 功能 - 文件完整性检查")
    print("=" * 70)
    print()
    
    checks = []
    
    # 1. 检查 JavaScript 文件
    print("📁 检查 JavaScript 文件...")
    checks.append(check_file(
        'static/vision/js/rack_location_canvas_roi.js',
        'Canvas ROI JavaScript 文件'
    ))
    print()
    
    # 2. 检查 HTML 模板
    print("📄 检查 HTML 模板...")
    checks.append(check_file(
        'templates/vision/rack_location_recipe_form.html',
        'HTML 模板文件'
    ))
    print()
    
    # 3. 检查关键元素
    print("🔍 检查 HTML 关键元素...")
    html_path = 'templates/vision/rack_location_recipe_form.html'
    checks.append(check_content(
        html_path,
        'rack-location-canvas',
        'Canvas 元素'
    ))
    checks.append(check_content(
        html_path,
        'btn-redraw-roi',
        '重画 ROI 按钮'
    ))
    checks.append(check_content(
        html_path,
        'rack_location_canvas_roi.js',
        'JS 文件引入'
    ))
    checks.append(check_content(
        html_path,
        'roi-coordinate-hint',
        'ROI 提示框'
    ))
    print()
    
    # 4. 检查 JavaScript 关键函数
    print("🔧 检查 JavaScript 关键函数...")
    js_path = 'static/vision/js/rack_location_canvas_roi.js'
    checks.append(check_content(
        js_path,
        'function pixelToCameraROI',
        '像素到相机坐标转换函数'
    ))
    checks.append(check_content(
        js_path,
        'async function transformCameraToRobot',
        '相机到机器人坐标转换函数'
    ))
    checks.append(check_content(
        js_path,
        'function onMouseDown',
        '鼠标事件处理函数'
    ))
    checks.append(check_content(
        js_path,
        'function clearROI',
        '清空 ROI 函数'
    ))
    print()
    
    # 5. 检查文档
    print("📚 检查文档...")
    checks.append(check_file(
        'Canvas绘制ROI功能说明.md',
        '功能说明文档'
    ))
    checks.append(check_file(
        'Canvas绘制ROI优化总结.md',
        '优化总结文档'
    ))
    checks.append(check_file(
        'Canvas功能测试指南.md',
        '测试指南文档'
    ))
    print()
    
    # 总结
    print("=" * 70)
    passed = sum(checks)
    total = len(checks)
    print(f"检查完成: {passed}/{total} 项通过")
    
    if passed == total:
        print("✅ 所有检查通过！Canvas 功能已正确安装。")
        print()
        print("下一步：")
        print("1. 启动 Django 服务器: python manage.py runserver")
        print("2. 打开浏览器访问页面")
        print("3. 清除浏览器缓存 (Ctrl+F5)")
        print("4. 按 F12 打开开发者工具查看 Console")
        print()
        return 0
    else:
        print(f"❌ 有 {total - passed} 项检查未通过，请检查上述错误。")
        return 1

if __name__ == '__main__':
    sys.exit(main())
