# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import os
import numpy as np
from Utils.Tools import *

def UseX1():
    # Initialize RVC system.
    RVC.SystemInit()

    # Choose RVC Camera type (USB, GigE or All)
    opt = RVC.SystemListDeviceTypeEnum.All

    # Scan all RVC Camera devices.
    ret, devices = RVC.SystemListDevices(opt)
    print("RVC Camera devices number:%d" % len(devices))

    # Find whether any RVC Camera is connected or not.
    if len(devices) == 0:
        print("Can not find any RVC Camera!")
        RVC.SystemShutdown()
        return 1
    print("devices size = %d" % len(devices))
    if devices[0].IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        return 1
    # Create a RVC Camera and choose use left side camera.
    x = RVC.X1.Create(devices[0], RVC.CameraID_Left)

    # Test RVC Camera is valid or not.
    if x.IsValid() == True:
        print("RVC Camera is valid!")
    else:
        print("RVC Camera is not valid!")
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        return 1

    # Open RVC Camera.
    ret1 = x.Open()

    # Test RVC Camera is opened or not.
    if x.IsOpen() == True:
        print("RVC Camera is opened!")
    else:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X1.")
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        return 1
    
    # Print ExposureTime Range
    _, exp_range_min, exp_range_max = x.GetExposureTimeRange()
    print("ExposureTime Range:[{}, {}]".format(exp_range_min, exp_range_max))

    # Save CaptureOptions
    x1_save_opts = RVC.X1_CaptureOptions()
    x1_save_opts.exposure_time_3d = 20
    x1_save_opts.exposure_time_2d = 21
    x.SaveCaptureOptionParameters(x1_save_opts)

    # Load CaptureOptions
    ret, x1_opts= x.LoadCaptureOptionParameters()
    PrintCaptureOptionX1(x1_opts)

    # Close RVC Camera.
    x.Close()

    # Destroy RVC Camera.
    RVC.X1.Destroy(x)

    # Shutdown RVC System.
    RVC.SystemShutdown()

    return 0


def UseX2():
    # Initialize RVC system.
    RVC.SystemInit()

    # Choose RVC Camera type (USB, GigE or All)
    opt = RVC.SystemListDeviceTypeEnum.All

    # Scan all RVC Camera devices.
    ret, devices = RVC.SystemListDevices(opt)
    print("RVC Camera devices number:%d" % len(devices))

    # Find whether any RVC Camera is connected or not.
    if len(devices) == 0:
        print("Can not find any RVC Camera!")
        RVC.SystemShutdown()
        return 1
    print("devices size = %d" % len(devices))
    if devices[0].IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        return 1
    # Create a RVC Camera
    x = RVC.X2.Create(devices[0])

    # Test RVC Camera is valid or not
    if x.IsValid() == False:
        print("RVC Camera is not valid!")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)
        
    #PrintCaptureMode(devices[0])

    # Open RVC Camera
    ret1 = x.Open()

    # Test RVC Camera is opened or not
    if x.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)

    ret, info = devices[0].GetDeviceInfo()
    camera_id = RVC.CameraID_Left
    if info.support_extra:
        camera_id = RVC.CameraID_Extra
        
    # Set capture parameters
    cap_opt = RVC.X2_CaptureOptions()
    # Transform point map's coordinate to camera
    cap_opt.transform_to_camera = camera_id
    # Set camera exposure time (3~100) ms
    cap_opt.exposure_time_2d = 20
    cap_opt.exposure_time_3d = 20
    # range in [0, 10]. the default value is 3. The contrast of point less than this value will be treat * as invalid point and be removed.
    cap_opt.light_contrast_threshold = 2
    # Set projector color, defult is RVC.ProjectorColor_Blue
    cap_opt.projector_color = RVC.ProjectorColor_Blue
    x.SaveCaptureOptionParameters(cap_opt)

    # Load CaptureOptions
    ret, x2_opts= x.LoadCaptureOptionParameters()
    PrintCaptureOptionX2(x2_opts)

    # Close RVC Camera.
    x.Close()

    # Destroy RVC Camera.
    RVC.X2.Destroy(x)

    # Shutdown RVC System.
    RVC.SystemShutdown()

    return 0

if __name__ == "__main__":
    UseX1()
    UseX2()
