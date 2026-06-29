"""调试tofconfig配置文件"""
import json
from pathlib import Path

# 读取并解密配置文件
config_path = Path('3d_SDK/tofconfig')

try:
    encoded = config_path.read_bytes()
    print(f"✓ 配置文件存在，大小: {len(encoded)} 字节")
    
    # 解密（XOR 0xFF）
    decoded_bytes = bytes(byte ^ 0xFF for byte in encoded)
    decoded_text = decoded_bytes.decode('utf-8')
    
    # 解析JSON
    data = json.loads(decoded_text)
    
    print("\n当前配置内容:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    
    # 检查关键参数
    print("\n关键参数检查:")
    print(f"  帧率 (fps_value): {data.get('fps_value')}")
    print(f"  曝光时间 (exposure_time): {data.get('exposure_time')}")
    print(f"  触发模式 (trigger_mode): {data.get('trigger_mode')}")
    print(f"  置信度滤波 (is_confidence_filtering): {data.get('is_confidence_filtering')}")
    print(f"  置信度阈值 (confidence_filter_value): {data.get('confidence_filter_value')}")
    print(f"  飞点滤波 (is_fly_filtering): {data.get('is_fly_filtering')}")
    print(f"  飞点阈值 (fly_filter_value): {data.get('fly_filter_value')}")
    print(f"  空间滤波 (is_spatial_filtering): {data.get('is_spatial_filtering')}")
    print(f"  空间阈值 (spatial_filter_value): {data.get('spatial_filter_value')}")
    
except Exception as e:
    print(f"✗ 错误: {e}")
