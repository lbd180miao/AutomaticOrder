"""
PLC补偿值写入服务

负责将补偿值写入到PLC，供机器人使用
"""
import logging
from typing import Dict, Optional
from datetime import datetime

from apps.devices.services import DeviceService
from apps.alarms.services import AlarmService
from apps.core.constants import AlarmSource, AlarmLevel

from .models import RackLocationResult
from .compensation_calculator import CompensationData
from .compensation_service import CompensationService

logger = logging.getLogger(__name__)


class PLCCompensationWriter:
    """PLC补偿值写入器"""
    
    def __init__(self, compensation_service: Optional[CompensationService] = None):
        """初始化PLC写入器"""
        self.device_service = DeviceService()
        self.compensation_service = compensation_service or CompensationService()
        self.alarm_service = AlarmService()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def write_compensation_to_plc(
        self,
        compensation: CompensationData,
        layer_no: int,
        position_no: Optional[int] = None,
        rack_side: str = 'BOTH',
        recipe_id: Optional[int] = None,
        result_id: Optional[int] = None,
        validate: bool = True
    ) -> Dict:
        """
        写入补偿值到PLC
        
        Args:
            compensation: 补偿值数据
            layer_no: 层号
            position_no: 位置号
            rack_side: 料架侧面
            recipe_id: 配方ID
            result_id: 结果ID
            validate: 是否验证
            
        Returns:
            写入结果字典
        """
        self.logger.info(
            f"准备写入补偿值到PLC: 层={layer_no}, "
            f"X={compensation.compensation_x:.2f}mm, "
            f"Y={compensation.compensation_y:.2f}mm, "
            f"Z={compensation.compensation_z:.2f}mm"
        )
        
        # 验证补偿值
        if validate and not compensation.is_valid:
            error_msg = f"补偿值无效，拒绝写入PLC: {compensation.validation_message}"
            self.logger.warning(error_msg)
            
            if result_id:
                self._update_result_plc_status(result_id, 'REJECTED', error_msg)
            
            return {
                'success': False,
                'rejected': True,
                'error': error_msg
            }
        
        # 准备PLC数据
        plc_payload = {
            'task_kind': 'RACK_3D_LOCATION',
            'side': rack_side,
            'position_no': position_no or 1,
            'layer_no': layer_no,
            'locate_ok': compensation.is_valid,
            'offset_x': round(compensation.compensation_x, 2),
            'offset_y': round(compensation.compensation_y, 2),
            'offset_z': round(compensation.compensation_z, 2),
            'offset_rz': round(compensation.compensation_rz, 3),
            'confidence': round((
                compensation.confidence_x + 
                compensation.confidence_y + 
                compensation.confidence_z
            ) / 3, 3),
            'compensation_valid': compensation.is_valid,
            'timestamp': datetime.now().isoformat()
        }
        
        # 写入PLC（模拟模式）
        try:
            # TODO: 实现实际PLC写入
            warning_msg = "PLC适配器未实现，跳过实际写入（模拟模式）"
            self.logger.warning(warning_msg)
            
            if result_id:
                self._update_result_plc_status(
                    result_id, 
                    'SIMULATED', 
                    warning_msg,
                    plc_payload
                )
            
            return {
                'success': True,
                'simulated': True,
                'message': warning_msg,
                'plc_payload': plc_payload,
                'written_at': datetime.now().isoformat()
            }
        
        except Exception as e:
            error_msg = f"写入PLC异常: {str(e)}"
            self.logger.exception(error_msg)
            
            if result_id:
                self._update_result_plc_status(result_id, 'ERROR', error_msg)
            
            return {
                'success': False,
                'error': error_msg
            }
    
    def write_compensation_from_result(
        self,
        result_id: int,
        validate: bool = True,
        revalidate: bool = True
    ) -> Dict:
        """从定位结果读取补偿值并写入PLC"""
        try:
            result = RackLocationResult.objects.select_related('recipe', 'rack').get(id=result_id)
            
            if not result.is_success:
                error_msg = "定位失败，无法写入补偿值"
                self._update_result_plc_status(result_id, 'SKIPPED', error_msg)
                return {
                    'success': False,
                    'skipped': True,
                    'error': error_msg
                }
            
            # 获取补偿值
            compensation_dict = self.compensation_service.get_compensation_from_result(result_id)
            
            if not compensation_dict:
                error_msg = "未找到补偿值数据"
                self._update_result_plc_status(result_id, 'ERROR', error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
            
            # 重建CompensationData对象
            compensation = CompensationData(
                compensation_x=compensation_dict['compensation_x'],
                compensation_y=compensation_dict['compensation_y'],
                compensation_z=compensation_dict['compensation_z'],
                compensation_rz=compensation_dict.get('compensation_rz', 0.0),
                confidence_x=compensation_dict['confidence_x'],
                confidence_y=compensation_dict['confidence_y'],
                confidence_z=compensation_dict['confidence_z'],
                is_valid=compensation_dict['is_valid'],
                validation_message=compensation_dict.get('validation_message', '')
            )
            
            # 写入PLC
            return self.write_compensation_to_plc(
                compensation=compensation,
                layer_no=result.layer_no,
                position_no=result.position_no,
                rack_side=result.side,
                recipe_id=result.recipe_id,
                result_id=result_id,
                validate=validate
            )
        
        except RackLocationResult.DoesNotExist:
            error_msg = f"定位结果不存在: ID={result_id}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
        
        except Exception as e:
            error_msg = f"处理定位结果失败: {str(e)}"
            self.logger.exception(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
    
    def batch_write_compensations_for_recipe(
        self,
        recipe_id: int,
        layers: Optional[list] = None,
        validate: bool = True
    ) -> Dict:
        """批量写入配方所有层的补偿值"""
        from .models import RackLocationRecipe
        
        try:
            recipe = RackLocationRecipe.objects.get(id=recipe_id)
            
            if layers is None:
                layers = list(range(1, recipe.layer_count + 1))
            
            results = {}
            success_count = 0
            failed_count = 0
            
            for layer_no in layers:
                latest_result = RackLocationResult.objects.filter(
                    recipe_id=recipe_id,
                    layer_no=layer_no,
                    is_success=True
                ).order_by('-created_at').first()
                
                if latest_result:
                    write_result = self.write_compensation_from_result(
                        result_id=latest_result.id,
                        validate=validate
                    )
                    
                    results[layer_no] = write_result
                    
                    if write_result.get('success'):
                        success_count += 1
                    else:
                        failed_count += 1
                else:
                    results[layer_no] = {
                        'success': False,
                        'error': '无定位结果'
                    }
                    failed_count += 1
            
            return {
                'success': failed_count == 0,
                'total': len(layers),
                'success_count': success_count,
                'failed_count': failed_count,
                'results': results,
                'message': f'批量写入完成: {success_count}成功, {failed_count}失败'
            }
        
        except RackLocationRecipe.DoesNotExist:
            error_msg = f"配方不存在: ID={recipe_id}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
        
        except Exception as e:
            error_msg = f"批量写入失败: {str(e)}"
            self.logger.exception(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
    
    def _update_result_plc_status(
        self,
        result_id: int,
        status: str,
        error_message: Optional[str] = None,
        plc_payload: Optional[Dict] = None
    ):
        """更新结果的PLC写入状态"""
        try:
            result = RackLocationResult.objects.get(id=result_id)
            
            result.plc_write_status = status
            result.plc_error_message = error_message or ''
            
            if plc_payload:
                if not result.result_data:
                    result.result_data = {}
                result.result_data['plc_payload'] = plc_payload
                result.plc_written_at = datetime.now()
            
            result.save(update_fields=[
                'plc_write_status', 
                'plc_error_message', 
                'result_data',
                'plc_written_at',
                'updated_at'
            ])
            
        except RackLocationResult.DoesNotExist:
            self.logger.error(f"结果不存在: ID={result_id}")
        except Exception as e:
            self.logger.exception(f"更新PLC状态失败: {e}")
