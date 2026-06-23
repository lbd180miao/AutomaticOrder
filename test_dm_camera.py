"""
DM 3D深度相机测试脚本

使用说明:
1. 确保已运行数据库迁移: python manage.py migrate
2. 确保DM相机已连接到网络
3. 运行测试: python test_dm_camera.py
"""
import os
import sys
import django

# 设置Django环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.dm_camera.services import DMCameraService
from apps.dm_camera.sdk_wrapper import DMCameraException
from apps.dm_camera.models import DMCameraConfig, DMCaptureRecord


def test_find_devices():
    """测试1: 查找设备"""
    print("\n" + "="*50)
    print("测试1: 查找设备")
    print("="*50)
    
    try:
        service = DMCameraService()
        devices = service.find_devices()
        
        print(f"✓ 找到 {len(devices)} 个设备:")
        for i, device in enumerate(devices, 1):
            print(f"  设备 {i}:")
            print(f"    序列号: {device['sn']}")
            print(f"    类型: {device['type']}")
            print(f"    IP地址: {device['ip']}")
            print(f"    本地IP: {device['local_ip']}")
        
        return True
    except DMCameraException as e:
        print(f"✗ 查找设备失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 异常: {e}")
        return False


def test_connect_disconnect():
    """测试2: 连接和断开设备"""
    print("\n" + "="*50)
    print("测试2: 连接和断开设备")
    print("="*50)
    
    try:
        service = DMCameraService()
        
        # 连接
        print("正在连接设备...")
        result = service.connect()
        print(f"✓ 连接成功:")
        print(f"  设备序列号: {result['device_sn']}")
        print(f"  设备类型: {result['device_type']}")
        print(f"  设备IP: {result['device_ip']}")
        print(f"  使用配置: {result['config_name']}")
        print(f"  会话ID: {result['session_id']}")
        
        # 获取状态
        status = service.get_status()
        print(f"✓ 设备状态:")
        print(f"  已连接: {status['connected']}")
        print(f"  采集中: {status['streaming']}")
        
        # 断开
        print("正在断开设备...")
        service.disconnect()
        print("✓ 断开成功")
        
        return True
    except DMCameraException as e:
        print(f"✗ 操作失败: {e}")
        service.disconnect()
        return False
    except Exception as e:
        print(f"✗ 异常: {e}")
        service.disconnect()
        return False


def test_stream_control():
    """测试3: 数据流控制"""
    print("\n" + "="*50)
    print("测试3: 数据流控制")
    print("="*50)
    
    try:
        service = DMCameraService()
        
        # 连接
        print("正在连接设备...")
        service.connect()
        print("✓ 连接成功")
        
        # 开启数据流
        print("正在开启数据流...")
        service.start_stream()
        print("✓ 数据流已开启")
        
        status = service.get_status()
        print(f"  采集状态: {status['streaming']}")
        
        # 停止数据流
        print("正在停止数据流...")
        service.stop_stream()
        print("✓ 数据流已停止")
        
        # 断开
        service.disconnect()
        print("✓ 已断开连接")
        
        return True
    except DMCameraException as e:
        print(f"✗ 操作失败: {e}")
        service.disconnect()
        return False
    except Exception as e:
        print(f"✗ 异常: {e}")
        service.disconnect()
        return False


def test_capture():
    """测试4: 捕获数据"""
    print("\n" + "="*50)
    print("测试4: 捕获深度图和IR图")
    print("="*50)
    
    try:
        service = DMCameraService()
        
        # 连接并开启数据流
        print("正在连接设备...")
        service.connect()
        print("✓ 连接成功")
        
        print("正在开启数据流...")
        service.start_stream()
        print("✓ 数据流已开启")
        
        # 捕获深度图
        print("\n捕获深度图...")
        depth_result = service.capture(frame_type='DEPTH', save_record=True)
        print(f"✓ 深度图捕获成功:")
        print(f"  帧序号: {depth_result['frame_index']}")
        print(f"  分辨率: {depth_result['width']}x{depth_result['height']}")
        print(f"  芯片温度: {depth_result['temperature']['chip']}°C")
        print(f"  激光器1温度: {depth_result['temperature']['laser1']}°C")
        print(f"  激光器2温度: {depth_result['temperature']['laser2']}°C")
        print(f"  记录ID: {depth_result['record_id']}")
        if depth_result.get('preview_url'):
            print(f"  预览图: {depth_result['preview_url']}")
        
        # 捕获IR图
        print("\n捕获IR图...")
        ir_result = service.capture(frame_type='IR', save_record=True)
        print(f"✓ IR图捕获成功:")
        print(f"  帧序号: {ir_result['frame_index']}")
        print(f"  分辨率: {ir_result['width']}x{ir_result['height']}")
        print(f"  记录ID: {ir_result['record_id']}")
        if ir_result.get('preview_url'):
            print(f"  预览图: {ir_result['preview_url']}")
        
        # 停止并断开
        service.stop_stream()
        service.disconnect()
        print("\n✓ 测试完成")
        
        return True
    except DMCameraException as e:
        print(f"✗ 捕获失败: {e}")
        service.disconnect()
        return False
    except Exception as e:
        print(f"✗ 异常: {e}")
        service.disconnect()
        return False


def test_batch_capture():
    """测试5: 批量捕获"""
    print("\n" + "="*50)
    print("测试5: 批量捕获 (10帧)")
    print("="*50)
    
    try:
        service = DMCameraService()
        
        # 连接并开启数据流
        print("正在连接设备...")
        service.connect()
        print("✓ 连接成功")
        
        print("正在开启数据流...")
        service.start_stream()
        print("✓ 数据流已开启")
        
        # 批量捕获
        capture_count = 10
        print(f"\n开始批量捕获 {capture_count} 帧...")
        
        results = []
        for i in range(capture_count):
            result = service.capture(frame_type='DEPTH', save_record=True)
            results.append(result)
            print(f"  [{i+1}/{capture_count}] 帧#{result['frame_index']} - 温度:{result['temperature']['chip']:.1f}°C")
        
        print(f"\n✓ 批量捕获完成，共 {len(results)} 帧")
        
        # 停止并断开
        service.stop_stream()
        service.disconnect()
        
        return True
    except DMCameraException as e:
        print(f"✗ 批量捕获失败: {e}")
        service.disconnect()
        return False
    except Exception as e:
        print(f"✗ 异常: {e}")
        service.disconnect()
        return False


def test_database_records():
    """测试6: 检查数据库记录"""
    print("\n" + "="*50)
    print("测试6: 检查数据库记录")
    print("="*50)
    
    try:
        # 检查配置
        configs = DMCameraConfig.objects.all()
        print(f"✓ 配置数量: {configs.count()}")
        for config in configs:
            print(f"  - {config.name} ({'激活' if config.is_active else '未激活'})")
        
        # 检查采集记录
        records = DMCaptureRecord.objects.all().order_by('-captured_at')[:10]
        print(f"\n✓ 最近10条采集记录:")
        for record in records:
            print(f"  - ID:{record.id} {record.frame_type} {record.width}x{record.height} "
                  f"温度:{record.temperature_chip}°C {record.captured_at.strftime('%Y-%m-%d %H:%M:%S')}")
        
        total_records = DMCaptureRecord.objects.count()
        print(f"\n总采集记录数: {total_records}")
        
        return True
    except Exception as e:
        print(f"✗ 查询失败: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("DM 3D深度相机集成测试")
    print("="*60)
    
    tests = [
        ("查找设备", test_find_devices),
        ("连接断开", test_connect_disconnect),
        ("数据流控制", test_stream_control),
        ("捕获数据", test_capture),
        ("批量捕获", test_batch_capture),
        ("数据库记录", test_database_records),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except KeyboardInterrupt:
            print("\n\n测试被用户中断")
            break
        except Exception as e:
            print(f"\n✗ 测试 '{test_name}' 发生异常: {e}")
            results[test_name] = False
    
    # 显示测试总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status} - {test_name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过!")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='DM 3D深度相机测试脚本')
    parser.add_argument('--test', type=str, choices=['find', 'connect', 'stream', 'capture', 'batch', 'db'],
                       help='运行指定的测试')
    
    args = parser.parse_args()
    
    if args.test:
        # 运行指定测试
        test_map = {
            'find': test_find_devices,
            'connect': test_connect_disconnect,
            'stream': test_stream_control,
            'capture': test_capture,
            'batch': test_batch_capture,
            'db': test_database_records,
        }
        test_map[args.test]()
    else:
        # 运行所有测试
        run_all_tests()
