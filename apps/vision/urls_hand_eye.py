"""
手眼标定模块路由
"""
from django.urls import path
from . import views_hand_eye

urlpatterns = [
    # 手眼标定管理页面
    path('hand-eye/', views_hand_eye.hand_eye_page, name='hand_eye_page'),
    
    # 手眼标定 CRUD
    path('api/hand-eye/calibrations/', views_hand_eye.list_calibrations, name='list_calibrations'),
    path('api/hand-eye/calibrations/create/', views_hand_eye.create_calibration, name='create_calibration'),
    path('api/hand-eye/calibrations/<int:calibration_id>/', views_hand_eye.get_calibration, name='get_calibration'),
    path('api/hand-eye/calibrations/<int:calibration_id>/update/', views_hand_eye.update_calibration, name='update_calibration'),
    path('api/hand-eye/calibrations/<int:calibration_id>/delete/', views_hand_eye.delete_calibration, name='delete_calibration'),
    
    # 标定样本管理
    path('api/hand-eye/calibrations/<int:calibration_id>/samples/', views_hand_eye.list_samples, name='list_samples'),
    path('api/hand-eye/calibrations/<int:calibration_id>/samples/add/', views_hand_eye.add_sample, name='add_sample'),
    path('api/hand-eye/samples/<int:sample_id>/delete/', views_hand_eye.delete_sample, name='delete_sample'),
    path('api/hand-eye/calibrations/<int:calibration_id>/samples/clear/', views_hand_eye.clear_samples, name='clear_samples'),
    
    # 标定计算和激活
    path('api/hand-eye/calibrations/<int:calibration_id>/compute/', views_hand_eye.compute_calibration, name='compute_calibration'),
    path('api/hand-eye/calibrations/<int:calibration_id>/activate/', views_hand_eye.activate_calibration, name='activate_calibration'),
    
    # 标定验证
    path('api/hand-eye/calibrations/<int:calibration_id>/verify/', views_hand_eye.verify_calibration, name='verify_calibration'),
    path('api/hand-eye/calibrations/<int:calibration_id>/verifications/', views_hand_eye.list_verifications, name='list_verifications'),
    
    # 导入导出
    path('api/hand-eye/calibrations/<int:calibration_id>/export/', views_hand_eye.export_calibration, name='export_calibration'),
    path('api/hand-eye/calibrations/import/', views_hand_eye.import_calibration, name='import_calibration'),
    
    # 辅助接口
    path('api/hand-eye/robot-pose/', views_hand_eye.get_robot_pose, name='get_robot_pose'),
    path('api/hand-eye/transform-test/', views_hand_eye.test_transform, name='test_transform'),
    path('api/hand-eye/compute-delta/', views_hand_eye.compute_delta, name='compute_delta'),

    # 坐标 ROI 转换（从 coordinates app 迁移，供配方页面 transform-roi 功能使用）
    path('api/coord/transform-roi/', views_hand_eye.api_coord_transform_roi, name='api_coord_transform_roi'),
]
