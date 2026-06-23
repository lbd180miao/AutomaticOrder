"""
DM相机REST API测试客户端

使用说明:
1. 启动Django开发服务器: python manage.py runserver
2. 运行此脚本: python test_dm_camera_api.py
"""
import requests
import json
import time
from typing import Dict, Optional


class DMCameraAPIClient:
    """DM相机REST API客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.api_base = f"{base_url}/dm-camera/api"
    
    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """发送HTTP请求"""
        url = f"{self.api_base}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url)
            elif method.upper() == 'POST':
                response = requests.post(url, json=data)
            elif method.upper() in ['PUT', 'PATCH']:
                response = requests.put(url, json=data)
            elif method.upper() == 'DELETE':
                response = requests.delete(url)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")
            
            response.raise_for_status()
            result = response.json()
            
            if not result.get('success'):
                raise Exception(result.get('error', '未知错误'))
            
            return result.get('data', {})
        
        except requests.exceptions.ConnectionError:
            raise Exception("无法连接到服务器，请确保Django服务器正在运行")
        except requests.exceptions.HTTPError as e:
            raise Exception(f"HTTP错误: {e}")
        except Exception as e:
            raise Exception(f"请求失败: {str(e)}")
    
    def find_devices(self) -> Dict:
        """查找设备"""
        return self._request('GET', '/devices/find/')
    
    def connect(self, device_sn: Optional[str] = None, config_id: Optional[int] = None) -> Dict:
        """连接设备"""
        data = {}
        if device_sn:
            data['device_sn'] = device_sn
        if config_id:
            data['config_id'] = config_id
        return self._request('POST', '/connect/', data)
    
    def disconnect(self) -> Dict:
        """断开连接"""
        return self._request('POST', '/disconnect/')
    
    def get_status(self) -> Dict:
        """获取状态"""
        return self._request('GET', '/status/')
    
    def start_stream(self) -> Dict:
        """开启数据流"""
        return self._request('POST', '/stream/start/')
    
    def stop_stream(self) -> Dict:
        """停止数据流"""
        return self._request('POST', '/stream/stop/')
    
    def capture(self, frame_type: str = 'DEPTH', save_record: bool = True) -> Dict:
        """捕获一帧"""
        return self._request('POST', '/capture/', {
            'frame_type': frame_type,
            'save_record': save_record
        })
    
    def list_configs(self) -> Dict:
        """列出配置"""
        return self._request('GET', '/configs/')
    
    def get_config(self, config_id: int) -> Dict:
        """获取配置详情"""
        return self._request('GET', f'/configs/{config_id}/')
    
    def create_config(self, config_data: Dict) -> Dict:
        """创建配置"""
        return self._request('POST', '/configs/create/', config_data)
    
    def update_config(self, config_id: int, config_data: Dict) -> Dict:
        """更新配置"""
        return self._request('PUT', f'/configs/{config_id}/update/', config_data)
    
    def delete_config(self, config_id: int) -> Dict:
        """删除配置"""
        return self._request('DELETE', f'/configs/{config_id}/delete/')
    
    def list_captures(self, page: int = 1, page_size: int = 20, frame_type: Optional[str] = None) -> Dict:
        """列出采集记录"""
        params = f'?page={page}&page_size={page_size}'
        if frame_type:
            params += f'&frame_type={frame_type}'
        return self._request('GET', f'/captures/{params}')
    
    def get_capture(self, capture_id: int) -> Dict:
        """获取采集记录详情"""
        return self._request('GET', f'/captures/{capture_id}/')


def print_section(title: str):
    """打印章节标题"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print('='*60)


def print_success(message: str):
    """打印成功消息"""
    print(f"✓ {message}")


def print_error(message: str):
    """打印错误消息"""
    print(f"✗ {message}")


def print_info(label: str, value):
    """打印信息"""
    print(f"  {label}: {value}")


def test_api_workflow():
    """测试完整的API工作流"""
    
    print_section("DM相机REST API测试")
    
    client = DMCameraAPIClient()
    
    try:
        # 1. 查找设备
        print_section("1. 查找设备")
        devices_data = client.find_devices()
        devices = devices_data['devices']
        print_success(f"找到 {len(devices)} 个设备")
        for i, device in enumerate(devices, 1):
            print(f"\n  设备 {i}:")
            print_info("序列号", device['sn'])
            print_info("类型", device['type'])
            print_info("IP地址", device['ip'])
        
        if not devices:
            print_error("没有找到设备，测试终止")
            return
        
        # 2. 连接设备
        print_section("2. 连接设备")
        connect_result = client.connect()
        print_success("连接成功")
        print_info("设备序列号", connect_result['device_sn'])
        print_info("设备类型", connect_result['device_type'])
        print_info("设备IP", connect_result['device_ip'])
        print_info("使用配置", connect_result['config_name'])
        print_info("会话ID", connect_result['session_id'])
        
        # 3. 获取状态
        print_section("3. 获取状态")
        status = client.get_status()
        print_success("状态获取成功")
        print_info("已连接", status['connected'])
        print_info("采集中", status['streaming'])
        if status.get('session'):
            print_info("会话状态", status['session']['status'])
        
        # 4. 开启数据流
        print_section("4. 开启数据流")
        stream_result = client.start_stream()
        print_success("数据流已开启")
        print_info("状态", stream_result['status'])
        
        # 5. 捕获深度图
        print_section("5. 捕获深度图")
        depth_result = client.capture('DEPTH', True)
        print_success("深度图捕获成功")
        print_info("帧序号", depth_result['frame_index'])
        print_info("分辨率", f"{depth_result['width']}x{depth_result['height']}")
        if depth_result.get('temperature'):
            print_info("芯片温度", f"{depth_result['temperature']['chip']}°C")
        print_info("记录ID", depth_result['record_id'])
        if depth_result.get('preview_url'):
            print_info("预览图", depth_result['preview_url'])
        
        # 6. 捕获IR图
        print_section("6. 捕获IR图")
        ir_result = client.capture('IR', True)
        print_success("IR图捕获成功")
        print_info("帧序号", ir_result['frame_index'])
        print_info("记录ID", ir_result['record_id'])
        
        # 7. 批量捕获
        print_section("7. 批量捕获 (5帧)")
        capture_count = 5
        for i in range(capture_count):
            result = client.capture('DEPTH', True)
            print(f"  [{i+1}/{capture_count}] 帧#{result['frame_index']} 已捕获")
            time.sleep(0.1)
        print_success(f"批量捕获 {capture_count} 帧完成")
        
        # 8. 查看采集记录
        print_section("8. 查看采集记录")
        captures_data = client.list_captures(page=1, page_size=10)
        print_success(f"总记录数: {captures_data['total']}")
        print_info("当前页", f"{captures_data['page']}/{captures_data['total_pages']}")
        print("\n  最近的采集记录:")
        for record in captures_data['records'][:5]:
            print(f"    - ID:{record['id']} {record['frame_type']} "
                  f"{record['width']}x{record['height']} "
                  f"{record['captured_at']}")
        
        # 9. 查看配置列表
        print_section("9. 查看配置列表")
        configs_data = client.list_configs()
        configs = configs_data['configs']
        print_success(f"配置数量: {len(configs)}")
        for config in configs:
            print(f"\n  配置: {config['name']}")
            print_info("ID", config['id'])
            print_info("帧率", config['frame_rate'])
            print_info("曝光时间", config['exposure_time'])
            print_info("触发模式", config['trigger_mode'])
            print_info("激活状态", "是" if config['is_active'] else "否")
        
        # 10. 停止数据流
        print_section("10. 停止数据流")
        stop_result = client.stop_stream()
        print_success("数据流已停止")
        
        # 11. 断开连接
        print_section("11. 断开连接")
        disconnect_result = client.disconnect()
        print_success("设备已断开连接")
        
        # 测试总结
        print_section("测试完成")
        print_success("所有API测试通过!")
        print("\n提示: 可以通过以下方式查看采集的图像:")
        print("  1. Django Admin: http://localhost:8000/admin/")
        print("  2. 媒体文件目录: media/dm_camera/")
        print("  3. API端点: GET /dm-camera/api/captures/")
        
    except Exception as e:
        print_error(f"测试失败: {str(e)}")
        # 尝试清理
        try:
            client.disconnect()
        except:
            pass


def test_config_management():
    """测试配置管理API"""
    
    print_section("配置管理API测试")
    
    client = DMCameraAPIClient()
    
    try:
        # 创建新配置
        print_section("1. 创建新配置")
        new_config = {
            'name': 'API测试配置',
            'frame_rate': 15,
            'exposure_time': 800,
            'trigger_mode': 'ACTIVE',
            'confidence_filter_enable': True,
            'confidence_threshold': 20,
            'is_active': False
        }
        create_result = client.create_config(new_config)
        config_id = create_result['id']
        print_success(f"配置创建成功，ID: {config_id}")
        
        # 获取配置详情
        print_section("2. 获取配置详情")
        config = client.get_config(config_id)
        print_success("配置详情获取成功")
        print_info("名称", config['name'])
        print_info("帧率", config['frame_rate'])
        print_info("曝光时间", config['exposure_time'])
        
        # 更新配置
        print_section("3. 更新配置")
        update_data = {
            'frame_rate': 20,
            'exposure_time': 600
        }
        client.update_config(config_id, update_data)
        print_success("配置更新成功")
        
        # 验证更新
        updated_config = client.get_config(config_id)
        print_info("新帧率", updated_config['frame_rate'])
        print_info("新曝光时间", updated_config['exposure_time'])
        
        # 删除配置
        print_section("4. 删除配置")
        client.delete_config(config_id)
        print_success("配置删除成功")
        
        print_section("配置管理测试完成")
        print_success("所有配置管理API测试通过!")
        
    except Exception as e:
        print_error(f"测试失败: {str(e)}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='DM相机REST API测试客户端')
    parser.add_argument('--workflow', action='store_true', help='测试完整工作流')
    parser.add_argument('--config', action='store_true', help='测试配置管理')
    parser.add_argument('--all', action='store_true', help='运行所有测试')
    parser.add_argument('--url', default='http://localhost:8000', help='服务器URL')
    
    args = parser.parse_args()
    
    if args.all:
        test_api_workflow()
        test_config_management()
    elif args.workflow:
        test_api_workflow()
    elif args.config:
        test_config_management()
    else:
        # 默认运行工作流测试
        test_api_workflow()
