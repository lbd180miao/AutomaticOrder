"""修复tofconfig配置文件 - 将空间滤波阈值从2改为5"""
import json
from pathlib import Path

config_path = Path('3d_SDK/tofconfig')

# 读取并解密
encoded = config_path.read_bytes()
decoded_bytes = bytes(byte ^ 0xFF for byte in encoded)
decoded_text = decoded_bytes.decode('utf-8')
data = json.loads(decoded_text)

print("修改前:")
print(f"  is_spatial_filtering: {data['is_spatial_filtering']}")
print(f"  spatial_filter_value: {data['spatial_filter_value']}")

# 修复：将空间滤波阈值从2改为5（SDK最小值要求）
data['spatial_filter_value'] = 5

print("\n修改后:")
print(f"  is_spatial_filtering: {data['is_spatial_filtering']}")
print(f"  spatial_filter_value: {data['spatial_filter_value']}")

# 保存（加密）
updated_text = json.dumps(data, ensure_ascii=False, indent=2)
updated_bytes = updated_text.encode('utf-8')
encrypted_bytes = bytes(byte ^ 0xFF for byte in updated_bytes)

# 备份原文件
backup_path = config_path.with_suffix('.backup')
config_path.rename(backup_path)
print(f"\n✓ 原配置已备份到: {backup_path}")

# 写入新配置
config_path.write_bytes(encrypted_bytes)
print(f"✓ 新配置已保存到: {config_path}")
