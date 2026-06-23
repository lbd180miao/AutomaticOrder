"""
DM 3D深度相机集成检查工具

使用说明:
运行此脚本检查DM相机集成的所有必要组件是否正确配置
python check_dm_camera_setup.py
"""
import os
import sys
from pathlib import Path

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_success(msg):
    print(f"{Colors.GREEN}✓{Colors.END} {msg}")

def print_error(msg):
    print(f"{Colors.RED}✗{Colors.END} {msg}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠{Colors.END} {msg}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ{Colors.END} {msg}")

def print_section(title):
    print(f"\n{'='*60}")
    print(f"{Colors.BLUE}{title}{Colors.END}")
    print('='*60)

# 检查项
checks_passed = 0
checks_failed = 0
checks_warning = 0

def check_result(condition, success_msg, error_msg, warning=False):
    global checks_passed, checks_failed, checks_warning
    if condition:
        if warning:
            print_warning(success_msg)
            checks_warning += 1
        else:
            print_success(success_msg)
            checks_passed += 1
        return True
    else:
        print_error(error_msg)
        checks_failed += 1
        return False

# 主检查逻辑
def main():
    print_section("DM 3D深度相机集成检查")
    
    # 1. 检查项目根目录
    print_section("1. 检查项目结构")
    
    project_root = Path(__file__).parent
    print_info(f"项目根目录: {project_root}")
    
    # 检查关键目录
    dm_camera_app = project_root / 'apps' / 'dm_camera'
    check_result(
        dm_camera_app.exists(),
        "apps/dm_camera/ 目录存在",
        "apps/dm_camera/ 目录不存在"
    )
    
    # 检查关键文件
    key_files = [
        ('apps/dm_camera/__init__.py', 'DM相机应用初始化文件'),
        ('apps/dm_camera/apps.py', '应用配置文件'),
        ('apps/dm_camera/models.py', '数据模型文件'),
        ('apps/dm_camera/views.py', '视图文件'),
        ('apps/dm_camera/urls.py', 'URL配置文件'),
        ('apps/dm_camera/services.py', '服务层文件'),
        ('apps/dm_camera/sdk_wrapper.py', 'SDK包装器文件'),
        ('apps/dm_camera/admin.py', 'Admin配置文件'),
    ]
    
    for file_path, description in key_files:
        full_path = project_root / file_path
        check_result(
            full_path.exists(),
            f"{description}存在: {file_path}",
            f"{description}不存在: {file_path}"
        )
    
    # 2. 检查SDK
    print_section("2. 检查SDK文件")
    
    sdk_base = project_root.parent / 'DM-Host-Computer-SDK' / 'DM上位机&SDK' / 'SDK' / '1.2.3'
    print_info(f"SDK路径: {sdk_base}")
    
    check_result(
        sdk_base.exists(),
        "SDK基础目录存在",
        f"SDK基础目录不存在: {sdk_base}"
    )
    
    # 检查DLL
    dll_path = sdk_base / 'C' / 'lib' / 'windows' / 'x64' / 'dm_c_sdk.dll'
    check_result(
        dll_path.exists(),
        f"SDK DLL文件存在: {dll_path.name}",
        f"SDK DLL文件不存在: {dll_path}"
    )
    
    # 检查Python API
    python_api_path = sdk_base / 'Python' / 'API' / 'zh'
    check_result(
        python_api_path.exists(),
        "Python API目录存在",
        f"Python API目录不存在: {python_api_path}"
    )
    
    api_files = [
        'LW_DM_Api.py',
        'LW_DM_Type.py'
    ]
    
    for api_file in api_files:
        full_path = python_api_path / api_file
        check_result(
            full_path.exists(),
            f"Python API文件存在: {api_file}",
            f"Python API文件不存在: {api_file}"
        )
    
    # 3. 检查Django配置
    print_section("3. 检查Django配置")
    
    # 检查settings.py
    settings_file = project_root / 'AutomaticOrder' / 'settings.py'
    if settings_file.exists():
        print_success("settings.py存在")
        
        settings_content = settings_file.read_text(encoding='utf-8')
        
        check_result(
            'apps.dm_camera' in settings_content,
            "apps.dm_camera已添加到INSTALLED_APPS",
            "apps.dm_camera未添加到INSTALLED_APPS"
        )
        
        check_result(
            'DM_CAMERA' in settings_content,
            "DM_CAMERA配置已添加到settings",
            "DM_CAMERA配置未添加到settings",
            warning=True
        )
    else:
        print_error("settings.py不存在")
    
    # 检查urls.py
    urls_file = project_root / 'AutomaticOrder' / 'urls.py'
    if urls_file.exists():
        print_success("urls.py存在")
        
        urls_content = urls_file.read_text(encoding='utf-8')
        
        check_result(
            'dm-camera' in urls_content or 'dm_camera' in urls_content,
            "DM相机URL已添加到主URL配置",
            "DM相机URL未添加到主URL配置"
        )
    else:
        print_error("urls.py不存在")
    
    # 4. 检查数据库迁移
    print_section("4. 检查数据库迁移")
    
    migrations_dir = dm_camera_app / 'migrations'
    if migrations_dir.exists():
        print_success("migrations目录存在")
        
        migration_files = list(migrations_dir.glob('0*.py'))
        check_result(
            len(migration_files) > 0,
            f"找到 {len(migration_files)} 个迁移文件",
            "未找到迁移文件"
        )
    else:
        print_error("migrations目录不存在")
    
    # 检查数据库
    db_file = project_root / 'db.sqlite3'
    if db_file.exists():
        print_success("数据库文件存在")
        
        # 尝试检查表
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            
            tables = ['dm_camera_config', 'dm_camera_capture', 'dm_camera_session']
            for table in tables:
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                result = cursor.fetchone()
                check_result(
                    result is not None,
                    f"数据表 {table} 已创建",
                    f"数据表 {table} 未创建"
                )
            
            conn.close()
        except Exception as e:
            print_warning(f"无法检查数据库表: {e}")
    else:
        print_warning("数据库文件不存在（可能还未运行migrate）")
    
    # 5. 检查媒体目录
    print_section("5. 检查媒体目录")
    
    media_dir = project_root / 'media'
    check_result(
        media_dir.exists(),
        "media目录存在",
        "media目录不存在",
        warning=True
    )
    
    dm_camera_media = media_dir / 'dm_camera'
    check_result(
        dm_camera_media.exists() or True,  # 不存在也只是警告
        "media/dm_camera目录存在" if dm_camera_media.exists() else "media/dm_camera目录不存在（运行时会自动创建）",
        "",
        warning=not dm_camera_media.exists()
    )
    
    # 6. 检查模板
    print_section("6. 检查模板文件")
    
    templates_dir = project_root / 'templates'
    check_result(
        templates_dir.exists(),
        "templates目录存在",
        "templates目录不存在"
    )
    
    demo_template = templates_dir / 'dm_camera_demo.html'
    check_result(
        demo_template.exists(),
        "演示页面模板存在",
        "演示页面模板不存在",
        warning=True
    )
    
    # 7. 检查文档
    print_section("7. 检查文档文件")
    
    docs = [
        ('DM_CAMERA_README.md', '完整文档'),
        ('DM_CAMERA_QUICKSTART.md', '快速入门指南'),
        ('DM_CAMERA_INTEGRATION_SUMMARY.md', '集成总结'),
    ]
    
    for doc_file, description in docs:
        full_path = project_root / doc_file
        check_result(
            full_path.exists(),
            f"{description}存在: {doc_file}",
            f"{description}不存在: {doc_file}",
            warning=True
        )
    
    # 8. 检查测试脚本
    print_section("8. 检查测试脚本")
    
    test_scripts = [
        ('test_dm_camera.py', 'Python单元测试脚本'),
        ('test_dm_camera_api.py', 'REST API测试脚本'),
    ]
    
    for script_file, description in test_scripts:
        full_path = project_root / script_file
        check_result(
            full_path.exists(),
            f"{description}存在: {script_file}",
            f"{description}不存在: {script_file}",
            warning=True
        )
    
    # 9. 检查Python依赖
    print_section("9. 检查Python依赖")
    
    try:
        import django
        print_success(f"Django已安装 (版本: {django.get_version()})")
    except ImportError:
        print_error("Django未安装")
    
    try:
        import numpy
        print_success(f"numpy已安装 (版本: {numpy.__version__})")
    except ImportError:
        print_error("numpy未安装")
    
    try:
        import PIL
        print_success(f"Pillow已安装 (版本: {PIL.__version__})")
    except ImportError:
        print_error("Pillow未安装")
    
    try:
        import cv2
        print_success(f"opencv-python已安装 (版本: {cv2.__version__})")
    except ImportError:
        print_error("opencv-python未安装")
    
    try:
        import requests
        print_success(f"requests已安装 (版本: {requests.__version__})")
    except ImportError:
        print_warning("requests未安装（API测试需要）")
    
    # 10. 检查Python环境
    print_section("10. 检查Python环境")
    
    print_info(f"Python版本: {sys.version}")
    print_info(f"Python可执行文件: {sys.executable}")
    
    is_64bit = sys.maxsize > 2**32
    check_result(
        is_64bit,
        "Python是64位版本",
        "Python是32位版本（需要64位Python匹配x64 DLL）"
    )
    
    # 总结
    print_section("检查总结")
    
    total_checks = checks_passed + checks_failed + checks_warning
    
    print(f"\n总检查项: {total_checks}")
    print(f"{Colors.GREEN}通过: {checks_passed}{Colors.END}")
    print(f"{Colors.RED}失败: {checks_failed}{Colors.END}")
    print(f"{Colors.YELLOW}警告: {checks_warning}{Colors.END}")
    
    if checks_failed == 0:
        print(f"\n{Colors.GREEN}{'='*60}")
        print("🎉 所有关键检查项都已通过！")
        print("你可以开始使用DM 3D深度相机了。")
        print(f"{'='*60}{Colors.END}")
        
        print("\n下一步操作:")
        print("1. 连接DM相机硬件到网络")
        print("2. 运行测试: python test_dm_camera.py --test find")
        print("3. 启动服务: python manage.py runserver")
        print("4. 访问演示页面: http://localhost:8000/dm-camera/")
        
    elif checks_failed <= 3:
        print(f"\n{Colors.YELLOW}{'='*60}")
        print("⚠️  有少量问题需要解决")
        print("请检查上述失败的项目并修复")
        print(f"{'='*60}{Colors.END}")
        
    else:
        print(f"\n{Colors.RED}{'='*60}")
        print("❌ 发现多个问题，需要修复")
        print("请按照错误提示修复问题后重新运行此检查")
        print(f"{'='*60}{Colors.END}")
    
    return checks_failed == 0


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n检查被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}检查过程发生错误: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
