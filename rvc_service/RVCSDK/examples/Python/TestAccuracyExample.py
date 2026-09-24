# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import os
import numpy as np
import cv2
from Utils.Tools import *


def App():
    # Initialize RVC X system.
    RVC.SystemInit()

    # Find Device

    # Method 1,Find device by index.
    ret, devices = RVC.SystemListDevices(RVC.SystemListDeviceTypeEnum.All)
    if len(devices) == 0:
        print("Can not find any Device!")
        RVC.SystemShutdown()
        return -1
    device = devices[0]
    
    if devices[0].IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        return 1
    # Method 2,Find device by sn.
    # This is the most recommended method when you have multiple cameras.
    # device = RVC.SystemFindDevice("P2GM353W002")

    if not device.IsValid():
        print("Device is not valid!")
        RVC.SystemShutdown()
        return

    # Create and Open
    x2 = RVC.X2.Create(device)
    ret = x2.Open()
    if x2.IsOpen() == True:
        print("RVC Camera is opened!")
    else:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x2)
        RVC.SystemShutdown()
        return 1
    
    ret, info = device.GetDeviceInfo()
    print(info.name + "-" + info.sn)
    camera_id = RVC.CameraID_Left
    if info.support_extra:
        camera_id = RVC.CameraID_Extra
        
    # Capture
    ret = x2.Capture()
    if ret:
        print("Capture successed!")
    else:
        print("Capture failed!")
        print(RVC.GetLastErrorMessage())
        x2.Close()
        RVC.X2.Destroy(x2)
        RVC.SystemShutdown()
        return -1

    img = x2.GetImage(camera_id)
    pm = x2.GetPointMap()
    ret, camera_intrinsics, camera_distortion = x2.GetIntrinsicParameters(camera_id)
    caliboard_pattern_size_width = 4
    caliboard_pattern_size_height = 11
    # Reference value(m): A1:0.112 A2:0.08 A3:0.056 A4:*0.04 A5:0.028 A6:0.02 A7:0.014 A8:0.01 A9:0.007 A10:0.0048
    caliboard_circle_center_standard_3d_distance_step = 0.04
    ret, circle_center_2d, circle_center_3d, measuring_distance, error_percentage = RVC.TestAccuracy(
        img, pm, camera_intrinsics, camera_distortion, caliboard_pattern_size_width, caliboard_pattern_size_height, caliboard_circle_center_standard_3d_distance_step)
    if ret != 0:
        print("TestAccuracy failed with error code: " + str(ret))
        x2.Close()
        RVC.X2.Destroy(x2)
        RVC.SystemShutdown()
        return -1

    circle_test_num = caliboard_pattern_size_height // 2
    true_distance = caliboard_circle_center_standard_3d_distance_step * circle_test_num
    print("measuring_distance: ", measuring_distance, "m")
    print("true_distance: ", true_distance, "m")
    print("error_percentage: ", error_percentage, "%")

    save_address = "Data"
    TryCreateDir(save_address)
    save_address += "/" + info.sn
    TryCreateDir(save_address)
    save_address += "/x2"
    TryCreateDir(save_address)

    pm.Save(save_address + "/pointmap.ply",
            RVC.PointMapUnitEnum.Millimeter, True)
    pm.SaveWithImage(save_address + "/pointmap_color.ply",
                     img, RVC.PointMapUnitEnum.Millimeter, True)
    img.SaveImage(save_address + "/image.png")

    # Release
    x2.Close()
    RVC.X2.Destroy(x2)
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
