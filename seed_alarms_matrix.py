import os
import django
import random
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from django.utils import timezone
from apps.core.constants import AlarmLevel, AlarmSource, AlarmStatus
from apps.production.models import ProductionBatch, Rack, Product
from apps.alarms.models import Alarm, AlarmAction
from apps.alarms.services import AlarmService


def seed_comprehensive_alarms():
    now = timezone.now()
    
    # 确保有关联的料框和产品
    racks = list(Rack.objects.all())
    products = list(Product.objects.all())
    
    rack_1 = racks[0] if racks else None
    rack_2 = racks[1] if len(racks) > 1 else rack_1
    rack_3 = racks[2] if len(racks) > 2 else rack_1
    
    prod_1 = products[0] if products else None
    prod_2 = products[1] if len(products) > 1 else prod_1
    prod_3 = products[2] if len(products) > 2 else prod_1
    prod_4 = products[3] if len(products) > 3 else prod_1

    # 清空旧报警以重新构建标准场景数据集
    AlarmAction.objects.all().delete()
    Alarm.objects.all().delete()

    alarms_config = [
        # ═════════════════════════════════════════════════════════════════
        # 模块一：料框检测报警 (Rack Detection)
        # ═════════════════════════════════════════════════════════════════
        {
            'source': AlarmSource.RECIPE,
            'level': AlarmLevel.CRITICAL,
            'status': AlarmStatus.OPEN,
            'lock_workstation': True,
            'error_code': 'RECIPE_MEASUREMENT_OUT_OF_TOLERANCE',
            'scene': '场景二：料架定位补偿',
            'phase': 'WAIT_RECIPE_VERIFY',
            'message': '配方实测校验不通过：第 3 层实测层高超出 MES 配方容差范围',
            'rack': rack_1,
            'product': prod_1,
            'context': {
                'recipe_layer_height': 350.0,
                'measured_layer_height': 358.2,
                'height_diff': 8.2,
                'recipe_layer_spacing': 280.0,
                'measured_layer_spacing': 281.5,
                'recipe_tolerance_z': 5.0,
                'layer_no': 3,
                'judgment': 'NG_OUT_OF_TOLERANCE',
            },
            'occurrence_count': 3,
            'delta_minutes': 5,
        },
        {
            'source': AlarmSource.VISION,
            'level': AlarmLevel.CRITICAL,
            'status': AlarmStatus.OPEN,
            'lock_workstation': True,
            'error_code': 'DELTA_Z_OUT_OF_LIMITS',
            'scene': '场景二：料架定位补偿',
            'phase': 'WAIT_POSITION',
            'message': '3D 视觉料架定位 ΔZ 补偿值超限：实测 ΔZ = 18.50mm (安全允许极值 ±15.00mm)',
            'rack': rack_1,
            'product': prod_2,
            'context': {
                'delta_x': 2.15,
                'delta_y': -1.80,
                'delta_z': 18.50,
                'max_allowed_delta_z': 15.00,
                'confidence': 0.942,
                'reason': '料架放置严重倾斜或机械限位变形',
            },
            'occurrence_count': 2,
            'delta_minutes': 12,
        },
        {
            'source': AlarmSource.DEVICE,
            'level': AlarmLevel.CRITICAL,
            'status': AlarmStatus.ACKNOWLEDGED,
            'lock_workstation': True,
            'error_code': 'DEVICE_COMMUNICATION_FAILED',
            'scene': '场景一：料框到位',
            'phase': 'WAIT_RACK',
            'message': 'PLC 通信连接中断：DB100 就绪信号轮询超时，心跳丢失',
            'rack': rack_2,
            'product': None,
            'context': {
                'device': 'PLC (S7-1500)',
                'ip': '192.168.1.10',
                'port': 102,
                'offline_duration_sec': 180,
                'last_heartbeat': (now - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S'),
            },
            'occurrence_count': 4,
            'delta_minutes': 15,
            'operator_note': '已通知电气工程师王工排查交换机网口与 PLC 运行状态',
        },
        {
            'source': AlarmSource.MES,
            'level': AlarmLevel.ERROR,
            'status': AlarmStatus.OPEN,
            'lock_workstation': False,
            'error_code': 'MES_RECIPE_GET_FAILED',
            'scene': '场景一：料框到位',
            'phase': 'WAIT_RACK',
            'message': 'MES 接口配方参数获取失败：返回空配方或料框码未在 MES 登记',
            'rack': rack_2,
            'product': None,
            'context': {
                'action': 'GET_RACK_RECIPE',
                'rack_code': rack_2.rack_code if rack_2 else 'RACK-DEMO-002',
                'http_status': 404,
                'error': 'MES Response: Rack barcode not found in master database',
            },
            'occurrence_count': 1,
            'delta_minutes': 25,
        },
        {
            'source': AlarmSource.VISION,
            'level': AlarmLevel.ERROR,
            'status': AlarmStatus.OPEN,
            'lock_workstation': False,
            'error_code': 'VISION_3D_CAPTURE_FAILED',
            'scene': '场景二：料架定位补偿',
            'phase': 'WAIT_POSITION',
            'message': '3D 深度相机图像采集失败：点云数据缺失，无法提取料架特征边缘',
            'rack': rack_3,
            'product': None,
            'context': {
                'camera_type': 'DEPTH_CAMERA',
                'error_detail': 'Point cloud density below minimum threshold (valid points < 20%)',
                'exposure_time_ms': 150,
            },
            'occurrence_count': 1,
            'delta_minutes': 35,
        },

        # ═════════════════════════════════════════════════════════════════
        # 模块二：产品条码绑定报警 (Product Binding)
        # ═════════════════════════════════════════════════════════════════
        {
            'source': AlarmSource.SCANNER,
            'level': AlarmLevel.CRITICAL,
            'status': AlarmStatus.OPEN,
            'lock_workstation': True,
            'error_code': 'BARCODE_DUPLICATE_FLOW',
            'scene': '产品条码暂存',
            'phase': 'WAIT_PRODUCT',
            'message': f'产品条码冲突：条码 {prod_1.product_code if prod_1 else "P-20260820-0001"} 已存在未完成装箱流程',
            'rack': rack_1,
            'product': prod_1,
            'context': {
                'scanned_code': prod_1.product_code if prod_1 else 'P-20260820-0001',
                'conflict_state': 'BOXING',
                'reason': '重复扫码或前序工件未正常释放流程实例',
            },
            'occurrence_count': 2,
            'delta_minutes': 8,
        },
        {
            'source': AlarmSource.SCANNER,
            'level': AlarmLevel.ERROR,
            'status': AlarmStatus.OPEN,
            'lock_workstation': False,
            'error_code': 'BARCODE_FORMAT_INVALID',
            'scene': '产品条码暂存',
            'phase': 'WAIT_PRODUCT',
            'message': '产品条码格式校验失败：扫描读码内容不符合批次规则前缀校验',
            'rack': rack_1,
            'product': prod_2,
            'context': {
                'scanned_raw': 'ERR-INV-9999-XXXX',
                'expected_prefix': 'P-2026',
                'scanner_device': 'KEYENCE_SR_2000',
            },
            'occurrence_count': 1,
            'delta_minutes': 18,
        },
        {
            'source': AlarmSource.MES,
            'level': AlarmLevel.ERROR,
            'status': AlarmStatus.ACKNOWLEDGED,
            'lock_workstation': False,
            'error_code': 'MES_UPLOAD_FAILED',
            'scene': '产品条码暂存',
            'phase': 'WAIT_PRODUCT',
            'message': 'MES 单件条码绑定上传超时：HTTP 503 接口未响应，已自动进入待补传队列',
            'rack': rack_1,
            'product': prod_3,
            'context': {
                'action': 'UPLOAD_PRODUCT_BARCODE',
                'product_code': prod_3.product_code if prod_3 else 'P-20260820-0003',
                'http_status': 503,
                'error': 'Connection timeout after 3000ms. Local record stored for auto-retry.',
            },
            'occurrence_count': 3,
            'delta_minutes': 22,
            'operator_note': '网络波动，本地已安全落库，待 MES 服务恢复后自动补传',
        },
        {
            'source': AlarmSource.MES,
            'level': AlarmLevel.ERROR,
            'status': AlarmStatus.OPEN,
            'lock_workstation': False,
            'error_code': 'MES_BOXING_UPLOAD_FAILED',
            'scene': '场景四：装箱完成与上传',
            'phase': 'WAIT_BOXING',
            'message': '整框装箱完成上传 MES 失败：返回料框容量与批次装箱总数不一致',
            'rack': rack_2,
            'product': None,
            'context': {
                'action': 'UPLOAD_BOXING_RESULT',
                'rack_code': rack_2.rack_code if rack_2 else 'RACK-DEMO-002',
                'error': 'Quantity mismatch: expected 12, reported 10',
            },
            'occurrence_count': 1,
            'delta_minutes': 40,
        },

        # ═════════════════════════════════════════════════════════════════
        # 模块三：泡棉检测报警 (Foam Inspection)
        # ═════════════════════════════════════════════════════════════════
        {
            'source': AlarmSource.VISION,
            'level': AlarmLevel.CRITICAL,
            'status': AlarmStatus.OPEN,
            'lock_workstation': True,
            'error_code': 'FOAM_INSPECTION_NG',
            'scene': '场景三：泡棉检测',
            'phase': 'WAIT_FOAM',
            'message': '泡棉贴附视觉检测不合格：第 2 层第 4 件泡棉右上角缺失 (漏贴)',
            'rack': rack_1,
            'product': prod_4,
            'context': {
                'position_index': 8,
                'score': 38.5,
                'coverage_ratio': 18.2,
                'defect_type': '泡棉缺失',
                'offset_x_mm': 4.250,
                'offset_y_mm': -3.120,
                'is_present': False,
                'has_lifted_edge': False,
            },
            'occurrence_count': 1,
            'delta_minutes': 6,
        },
        {
            'source': AlarmSource.VISION,
            'level': AlarmLevel.CRITICAL,
            'status': AlarmStatus.OPEN,
            'lock_workstation': True,
            'error_code': 'FOAM_LIFTED_EDGE',
            'scene': '场景三：泡棉检测',
            'phase': 'WAIT_FOAM',
            'message': '泡棉贴附质量异常：边缘翘边严重 (高度差梯度突变 > 1.8mm)',
            'rack': rack_1,
            'product': prod_1,
            'context': {
                'position_index': 3,
                'score': 55.0,
                'coverage_ratio': 85.0,
                'defect_type': '严重翘边',
                'offset_x_mm': 0.850,
                'offset_y_mm': 0.420,
                'is_present': True,
                'has_lifted_edge': True,
            },
            'occurrence_count': 2,
            'delta_minutes': 14,
        },
        {
            'source': AlarmSource.VISION,
            'level': AlarmLevel.ERROR,
            'status': AlarmStatus.ACKNOWLEDGED,
            'lock_workstation': False,
            'error_code': 'FOAM_OFFSET_OUT_OF_TOLERANCE',
            'scene': '场景三：泡棉检测',
            'phase': 'WAIT_FOAM',
            'message': '泡棉贴附位置偏移超差：X 轴偏移 +3.85mm (容差门限 ±2.00mm)',
            'rack': rack_2,
            'product': prod_2,
            'context': {
                'position_index': 5,
                'score': 68.0,
                'coverage_ratio': 92.5,
                'defect_type': '位置偏移',
                'offset_x_mm': 3.850,
                'offset_y_mm': -0.450,
                'is_present': True,
                'has_lifted_edge': False,
            },
            'occurrence_count': 1,
            'delta_minutes': 28,
            'operator_note': '已通知装箱机器人工程师调整贴附吸盘气压与下压补偿量',
        },
    ]

    service = AlarmService()
    created_alarms = []

    for cfg in alarms_config:
        occur_time = now - timedelta(minutes=cfg['delta_minutes'])
        alarm = Alarm.objects.create(
            alarm_code=service._generate_code(),
            level=cfg['level'],
            source=cfg['source'],
            message=cfg['message'],
            product=cfg['product'],
            rack=cfg['rack'],
            status=cfg['status'],
            locked_workstation=cfg['lock_workstation'],
            error_code=cfg['error_code'],
            scene=cfg['scene'],
            phase=cfg['phase'],
            context=cfg['context'],
            occurrence_count=cfg['occurrence_count'],
            last_occurred_at=occur_time,
            created_at=occur_time - timedelta(minutes=5),
            acknowledged_at=occur_time if cfg['status'] == AlarmStatus.ACKNOWLEDGED else None,
            operator_note=cfg.get('operator_note', ''),
        )
        if cfg['status'] == AlarmStatus.ACKNOWLEDGED:
            AlarmAction.objects.create(
                alarm=alarm,
                action=AlarmAction.Action.ACKNOWLEDGE,
                operator='现场操作员-张工',
                note=cfg.get('operator_note', ''),
                created_at=occur_time,
            )
        created_alarms.append(alarm)

    # ═════════════════════════════════════════════════════════════════
    # 生成 10 条已关闭的历史报警 (Closed History)
    # ═════════════════════════════════════════════════════════════════
    closed_config = [
        ('RECIPE', 'RECIPE_MEASUREMENT_OUT_OF_TOLERANCE', '第1层层距超出容差范围', '更换标准料架，3D 重新测量层距进入 ±1.0mm 容差范围', '品质主管-李工', 2),
        ('VISION', 'FOAM_INSPECTION_NG', '第1层第2件泡棉漏贴', '人工补贴泡棉，触发固定相机二次复检判定 OK', '操作员-张工', 4),
        ('DEVICE', 'DEVICE_COMMUNICATION_FAILED', '2D 相机通信连接闪断', '重新插拔工业网线与相机 PoE 供电线，链路恢复在线', '电气工程师-刘工', 5),
        ('MES', 'MES_UPLOAD_FAILED', '单件产品条码上传 MES 报错', 'MES 接口服务重启后，通过工作台一键补传成功', '系统管理员', 8),
        ('SCANNER', 'BARCODE_FORMAT_INVALID', '激光打标二维码扫描模糊', '清洁打标窗口并调整激光聚焦焦距，复扫通过', '设备技术员-陈工', 12),
        ('VISION', 'DELTA_Z_OUT_OF_LIMITS', '3D 定位计算偏差超限', '清理定位支架异物，重新落座料架后定位成功', '操作员-王工', 16),
        ('WORKFLOW', 'LASER_MARKING_TIMEOUT', '激光打标机就绪信号超时', '打标机排风阀复位，重新发送打标触发信号', '设备技术员-陈工', 20),
        ('MES', 'MES_RECIPE_GET_FAILED', 'MES 配方编号未下发', '在 MES 系统手工触发工单同步，配方正常下发', '调度员-赵工', 24),
        ('VISION', 'FOAM_LIFTED_EDGE', '泡棉左下角微翘', '气缸压合工装清洁胶渍，复压后贴附平整', '操作员-张工', 30),
        ('DEVICE', 'SAFETY_CURTAIN_TRIGGERED', '装箱区安全光幕被遮挡停机', '操作人员离开危险区域，按下硬件复位按钮解锁', '安全员-孙工', 36),
    ]

    for source, err_code, msg, note, operator, hours_ago in closed_config:
        close_time = now - timedelta(hours=hours_ago)
        start_time = close_time - timedelta(minutes=random.randint(5, 25))
        ack_time = start_time + timedelta(minutes=random.randint(2, 6))

        alm = Alarm.objects.create(
            alarm_code=service._generate_code(),
            level=AlarmLevel.ERROR,
            source=source,
            message=msg,
            product=prod_1,
            rack=rack_1,
            status=AlarmStatus.CLOSED,
            locked_workstation=False,
            error_code=err_code,
            scene='工序历史记录',
            phase='COMPLETED',
            context={'resolution': note},
            occurrence_count=1,
            created_at=start_time,
            last_occurred_at=start_time,
            acknowledged_at=ack_time,
            closed_at=close_time,
            operator_note=note,
        )
        AlarmAction.objects.create(
            alarm=alm,
            action=AlarmAction.Action.ACKNOWLEDGE,
            operator=operator,
            note='确认故障并到场排查',
            created_at=ack_time,
        )
        AlarmAction.objects.create(
            alarm=alm,
            action=AlarmAction.Action.CLOSE,
            operator=operator,
            note=note,
            created_at=close_time,
        )

    print(f"成功生成 {len(created_alarms)} 条活跃标准报警与 10 条已关闭历史处置记录！")

if __name__ == '__main__':
    seed_comprehensive_alarms()
