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
    x = RVC.X2.Create(device)
    x.Open()
    if x.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)

    ret, info = device.GetDeviceInfo()
    camera_id = RVC.CameraID_Left
    if info.support_extra:
        camera_id = RVC.CameraID_Extra
    
    # Print ExposureTime Range
    _, exp_range_min, exp_range_max = x.GetExposureTimeRange()
    print("ExposureTime Range:[{}, {}]".format(exp_range_min, exp_range_max))

    # Create saving address of image and point map.
    save_address = "Data"
    TryCreateDir(save_address)

    # capture option
    cap_opt = RVC.X2_CaptureOptions()
    cap_opt.exposure_time_2d = 50

    # Reset camera timestamp to zero (optional, establishes a time base for frame timestamps)
    x.ResetTimestamp()

    # X2 Capture 2D
    ret2 = x.Capture2D(camera_id, cap_opt)
    if ret2 == True:
        print("Capture 2D success!")
        img = x.GetImage(camera_id)
        # Image timestamp: frame acquisition time in microseconds (us), relative to ResetTimestamp()
        timestamp_us = img.GetTimestamp()
        print("Image timestamp(us):", timestamp_us)
        # Save image
        if img.SaveImage(save_address + "/image.png"):
            print("Save image successed!")
        else:
            print("Save image failed!")
    else:
        print("Capture 2D failed!")
        print(RVC.GetLastErrorMessage())
        
    # X2 Capture 3D
    ret3 = x.Capture()
    if ret3 == True:
        print("RVC Camera capture successed!")

        # Get image data and image size.
        img = x.GetImage(camera_id)
        width = img.GetSize().cols
        height = img.GetSize().rows

        # Save image
        if img.SaveImage(save_address + "/image.png"):
            print("Save image successed!")
        else:
            print("Save image failed!")

        # Save point map (m) to file.
        if x.GetPointMap().Save("Data/test.ply", RVC.PointMapUnitEnum.Meter):
            print("Save point map successed!")
        else:
            print("Save point map failed!")
    else:
        print("RVC Camera capture failed!")
        print(RVC.GetLastErrorMessage())
        x.Close()
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        return 1

    # Close RVC Camera.
    x.Close()

    # Destroy RVC Camera.
    RVC.X2.Destroy(x)

    # Shutdown RVC System.
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
