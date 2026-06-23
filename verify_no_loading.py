#!/usr/bin/env python
"""
验证配方管理页面是否已移除Loading效果
检查recipe_management.html文件内容
"""

import re
from pathlib import Path

def verify_recipe_management():
    """验证配方管理页面"""
    print("=" * 60)
    print("验证配方管理页面 - Loading效果检查")
    print("=" * 60)
    
    file_path = Path("templates/vision/recipe_management.html")
    
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False
    
    content = file_path.read_text(encoding='utf-8')
    
    checks = []
    
    # 检查1: 是否有版本号 v1.2
    if 'v1.2' in content:
        print("✅ 检查1: 包含版本号 v1.2")
        checks.append(True)
    else:
        print("❌ 检查1: 未找到版本号 v1.2")
        checks.append(False)
    
    # 检查2: 是否有Toast样式
    if '.toast {' in content and 'slideInRight' in content:
        print("✅ 检查2: 包含Toast样式")
        checks.append(True)
    else:
        print("❌ 检查2: 未找到Toast样式")
        checks.append(False)
    
    # 检查3: showToast函数是否存在
    if 'function showToast(' in content:
        print("✅ 检查3: showToast函数已定义")
        checks.append(True)
    else:
        print("❌ 检查3: showToast函数未定义")
        checks.append(False)
    
    # 检查4: showLoading是否为空函数
    if re.search(r'function showLoading.*?{\s*//.*?不显示loading', content, re.DOTALL):
        print("✅ 检查4: showLoading已改为空函数")
        checks.append(True)
    else:
        print("❌ 检查4: showLoading仍在使用")
        checks.append(False)
    
    # 检查5: 是否还有alert调用
    alert_matches = re.findall(r'\balert\s*\(', content)
    if not alert_matches:
        print("✅ 检查5: 无alert调用")
        checks.append(True)
    else:
        print(f"❌ 检查5: 发现 {len(alert_matches)} 处alert调用")
        checks.append(False)
    
    # 检查6: 是否有Toast调用
    toast_matches = re.findall(r'showToast\s*\(', content)
    if len(toast_matches) >= 5:
        print(f"✅ 检查6: 发现 {len(toast_matches)} 处showToast调用")
        checks.append(True)
    else:
        print(f"⚠️  检查6: 仅发现 {len(toast_matches)} 处showToast调用（预期>=5）")
        checks.append(False)
    
    # 检查7: 删除配方函数
    if 'window.deleteRecipe' in content:
        delete_func = re.search(
            r'window\.deleteRecipe.*?};',
            content,
            re.DOTALL
        )
        if delete_func and 'showToast' in delete_func.group():
            print("✅ 检查7: deleteRecipe使用showToast")
            checks.append(True)
        else:
            print("❌ 检查7: deleteRecipe未使用showToast")
            checks.append(False)
    else:
        print("❌ 检查7: deleteRecipe函数未找到")
        checks.append(False)
    
    # 检查8: 保存配方函数
    if 'async function saveSelectedRecipe' in content:
        save_func = re.search(
            r'async function saveSelectedRecipe.*?}',
            content,
            re.DOTALL
        )
        if save_func and 'showToast' in save_func.group():
            print("✅ 检查8: saveSelectedRecipe使用showToast")
            checks.append(True)
        else:
            print("❌ 检查8: saveSelectedRecipe未使用showToast")
            checks.append(False)
    else:
        print("❌ 检查8: saveSelectedRecipe函数未找到")
        checks.append(False)
    
    # 检查9: Console日志
    if 'console.log' in content and 'Toast提示版本' in content:
        print("✅ 检查9: 包含版本识别日志")
        checks.append(True)
    else:
        print("❌ 检查9: 未找到版本识别日志")
        checks.append(False)
    
    # 总结
    print("\n" + "=" * 60)
    passed = sum(checks)
    total = len(checks)
    percentage = (passed / total) * 100
    
    print(f"检查结果: {passed}/{total} 通过 ({percentage:.1f}%)")
    
    if passed == total:
        print("✅✅✅ 所有检查通过！代码已正确更新！")
        print("\n📌 下一步：清除浏览器缓存")
        print("   1. 按 Ctrl + Shift + Delete")
        print("   2. 清除缓存的图像和文件")
        print("   3. 按 Ctrl + F5 强制刷新页面")
    else:
        print(f"⚠️  有 {total - passed} 项检查未通过")
        print("请检查代码是否正确更新")
    
    print("=" * 60)
    
    return passed == total

if __name__ == "__main__":
    success = verify_recipe_management()
    exit(0 if success else 1)
