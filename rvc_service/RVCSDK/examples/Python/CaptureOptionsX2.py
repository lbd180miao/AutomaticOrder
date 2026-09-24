# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import os
import numpy as np
import cv2
from Utils.Tools import *


def App():
    # Initialize RVC system
    RVC.SystemInit()

    # Choose RVC Camera type (USB, GigE or All)
    opt = RVC.SystemListDeviceTypeEnum.All

    # Scan all RVC Camera devices
    ret, devices = RVC.SystemListDevices(opt)
    print("RVC Camera devices number:", len(devices))

    # Find whether any RVC Camera is connected or not
    if len(devices) == 0:
        print("Can not find any RVC Camera!")
        RVC.SystemShutdown()
        exit(1)    
    if devices[0].IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        exit(1)    
    # Create and open RVC Camera
    device = devices[0]
    x2 = RVC.X2.Create(device)
    x2.Open()
    if x2.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x2)
        RVC.SystemShutdown()
        exit(1)

    ret, info = device.GetDeviceInfo()
    camera_id = RVC.CameraID_Left
    if info.support_extra:
        camera_id = RVC.CameraID_Extra
    print(info.name + "-" + info.sn)

    # Print ExposureTime Range
    _, exp_range_min, exp_range_max = x2.GetExposureTimeRange()
    print("ExposureTime Range:[{}, {}]".format(exp_range_min, exp_range_max))

    # Modify Capture Options and Capture
    options = RVC.X2_CaptureOptions()
    ret = False
    ret,options = x2.LoadCaptureOptionParameters()


    # Print Capture Options
    print("打印拍摄参数")

    # P and I series supports the following modes:
    # CaptureMode_Normal
    # CaptureMode_Fast
    # CaptureMode_AntiInterReflection
        
    # G series supports the following modes:
    # CaptureMode_Ultra
    # CaptureMode_AntiInterReflection
        
    # M series supports the following modes:
    # CaptureMode_Ultra
    # CaptureMode_AntiInterReflection
    # CaptureMode_SwingLineScan
    # CaptureMode_FixedLineScan
        
    # Note:The CaptureMode_Robust has been deprecated. You can achieve the same effect by setting the
    # 'scan_times' parameter.
         

    str_capture_mode = ""
    if options.capture_mode == RVC.CaptureMode_Fast:
        str_capture_mode = "快速模式"
    elif options.capture_mode == RVC.CaptureMode_Normal:
        str_capture_mode = "标准模式"
    elif options.capture_mode == RVC.CaptureMode_Ultra:
        str_capture_mode = "高精度模式"
    elif options.capture_mode == RVC.CaptureMode_AntiInterReflection:
        str_capture_mode = "抗多次反射模式"
    elif options.capture_mode == RVC.CaptureMode_SwingLineScan:
        str_capture_mode = "摆动线扫模式"
    elif options.capture_mode == RVC.CaptureMode_FixedLineScan:
        str_capture_mode = "固定线扫模式"
        
    print("拍摄模式--[capture_mode] = " + str_capture_mode)

    # Parameters related to 2D Capture
    print("2D 曝光时间--[exposure_time_2d] = " + str(options.exposure_time_2d))
    print("2D 增益--[gain_2d] = " + str(options.gain_2d))
    print("2D Gamma--[gamma_2d] = " + str(options.gamma_2d))
    print("2D 拍摄是否使用光机--[use_projector_capturing_2d_image] = " + str(options.use_projector_capturing_2d_image))

    print("3D采集中拍摄2D图--[enable_2d_in_capture] = " + str(options.enable_2d_in_capture))
    print("3D 曝光时间--[exposure_time_3d] = " + str(options.exposure_time_3d))
    print("3D 增益--[gain_3d] = " + str(options.gain_3d))
    print("3D Gamma--[gamma_3d] = " + str(options.gamma_3d))
    print("光强对比度阈值--[light_contrast_threshold] = " + str(options.light_contrast_threshold))
    print("投影亮度--[projector_brightness] = " + str(options.projector_brightness))

    # Note:Only the G and M series support the 'scan_times' parameter.
    print("扫描次数[G/M系列相机]--[scan_times] =" + str(options.scan_times))

    # Note:Only M series support the 'line_scanner_*' and 'correspond2d' parameters.
    print("线扫时间--[line_scanner_scan_time_ms] =" + str(options.line_scanner_scan_time_ms))
    print("线扫单行曝光时间--[line_scanner_exposure_time_us] =" + str(options.line_scanner_exposure_time_us))
    print("线扫最小距离--[line_scanner_min_distance] =" + str(options.line_scanner_min_distance))
    print("线扫最大距离--[line_scanner_max_distance] =" + str(options.line_scanner_max_distance))
    print("线扫亮度阈值--[line_scanner_brightness_threshold] =" + str(options.line_scanner_brightness_threshold))
    print("固定线扫激光线位置--[line_scanner_laser_position] =" + str(options.line_scanner_laser_position))
    print("点云是否与2D图对齐--[correspond2d] =" + str(options.correspond2d))
    print("触发模式--[trigger_mode] =" + str(options.trigger_mode))
    print("编码器触发间隔--[encoder_trigger_interval] =" + str(options.encoder_trigger_interval))

    # Currently supported HDR modes include:
    # CaptureMode_Normal
    # CaptureMode_Fast
    # CaptureMode_Ultra
    # CaptureMode_AntiInterReflection
         
    print("HDR 次数--[hdr_exposure_times] = " + str(options.hdr_exposure_times))
    print("HDR 曝光(0,1,2)--[hdr_exposuretime_content_0] = " + str(options.GetHDRExposureTimeContent(0)))
    print("HDR 曝光(0,1,2)--[hdr_exposuretime_content_1] = " + str(options.GetHDRExposureTimeContent(1)))
    print("HDR 曝光(0,1,2)--[hdr_exposuretime_content_2] = " + str(options.GetHDRExposureTimeContent(2)))

    print("HDR 增益(0,1,2)--[hdr_hdr_gain_3d_0] = " + str(options.GetHDRGainContent(0)))
    print("HDR 增益(0,1,2)--[hdr_hdr_gain_3d_1] = " + str(options.GetHDRGainContent(1)))
    print("HDR 增益(0,1,2)--[hdr_hdr_gain_3d_2] = " + str(options.GetHDRGainContent(2)))

    print("HDR 投影亮度(0,1,2)--[hdr_projector_brightness_0] = " + str(options.GetHDRProjectorBrightnessContent(0)))
    print("HDR 投影亮度(0,1,2)--[hdr_projector_brightness_1] = " + str(options.GetHDRProjectorBrightnessContent(1)))
    print("HDR 投影亮度(0,1,2)--[hdr_projector_brightness_2] = " + str(options.GetHDRProjectorBrightnessContent(2)))
    
    # Note:Only the G and M series support the 'hdr_scan_times' parameter.
    print("HDR 扫描次数(0,1,2)--[hdr_scan_times_0] = " + str(options.GetHDRScanTimesContent(0)))
    print("HDR 扫描次数(0,1,2)--[hdr_scan_times_1] = " + str(options.GetHDRScanTimesContent(1)))
    print("HDR 扫描次数(0,1,2)--[hdr_scan_times_2] = " + str(options.GetHDRScanTimesContent(2)))

    print("是否使用自动聚类去噪--[use_auto_noise_removal] =" + str(options.use_auto_noise_removal))
    print("置信度去噪阈值--[confidence_threshold] =" + str(options.confidence_threshold))
    print("线扫置信度--[line_scanner_confidence] =" + str(options.line_scanner_confidence))
    print("聚类降噪距离阈值--[noise_removal_distance] =" + str(options.noise_removal_distance))
    print("聚类降噪有效点数阈值--[noise_removal_point_number] =" + str(options.noise_removal_point_number))
    print("反射去噪阈值--[reflection_filter_threshold] =" + str(options.reflection_filter_threshold))
    print("高斯平滑--[smooth_sigma] =" + str(options.smooth_sigma))
    print("下采样距离(m)--[downsample_distance] =" + str(options.downsample_distance))
    print("是否计算法向量--[calc_normal] =" + str(options.calc_normal))
    print("计算法向量距离--[calc_normal_radius] =" + str(options.calc_normal_radius))
    print("点云补全--[pointcloud_completion] = " + str(options.pointcloud_completion))


    print("ROI(x,y,w,h)--[roi_x] =" + str(options.roi.x))
    print("ROI(x,y,w,h)--[roi_y] =" + str(options.roi.y))
    print("ROI(x,y,w,h)--[roi_w] =" + str(options.roi.width))
    print("ROI(x,y,w,h)--[roi_h] =" + str(options.roi.height))
    print("z向截断最小值--[truncate_z_min] =" + str(options.truncate_z_min))
    print("z向截断最大值--[truncate_z_max] =" + str(options.truncate_z_max))      
    

    # Method 1, use default options and modify options
    # options = RVC.X2_CaptureOptions()
    # todo:modify options
    # ret = x2.Capture(options)

    # Method 2, load Options From Camera and modify options
    # ret,options = x2.LoadCaptureOptionParameters()
    # todo:modify options
    # ret = x2.Capture(options)

    # *********
    # Method 3, use the internal parameters of the camera.
    # We suggest adjusting the camera parameters By RVC Manager.
    # Then, when we use SDK, we directly use the parameters inside the camera.
    ret = x2.Capture()

    # Method 4 , Load Options From File and Capture.
    # If you need to capture multiple scenes, their parameters are different.
    # You can save these parameters as different configuration files  By RVC Manager and then import the files before capture.
    # ret = x2.LoadSettingFromFile("file.json")
    # ret = x2.Capture()

    if ret:
        print("RVC Camera capture successed!")
    else:
        print("RVC Camera capture failed!")
        print(RVC.GetLastErrorMessage())
        x2.Close()
        RVC.X2.Destroy(x2)
        RVC.SystemShutdown()
        return 1

    # Data Process
    save_address = "Data"
    TryCreateDir(save_address)
    save_address += "/" + info.sn
    TryCreateDir(save_address)
    save_address += "/x2"
    TryCreateDir(save_address)

    img = x2.GetImage(camera_id)
    pm = x2.GetPointMap()

    pm.Save(save_address + "/pointmap.ply", RVC.PointMapUnitEnum.Millimeter, True)
    pm.SaveWithImage(save_address + "/pointmap_color.ply", img, RVC.PointMapUnitEnum.Millimeter, True)
    img.SaveImage(save_address + "/image.png")

    # numpy extension
    img_np = np.array(img, copy=False)
    pm_np = np.array(pm, copy=False).reshape(-1, 3)
    size = img_np.size

    # Release
    x2.Close()
    RVC.X2.Destroy(x2)
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
