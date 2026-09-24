# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import os
import numpy as np
import cv2

import time

from numpy.lib.npyio import save
from IPython import embed
from Utils.Tools import *


def App():

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

    #PrintCaptureMode(devices[0])

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

    cap_opt = RVC.X1_CaptureOptions()
    ret,cap_opt = x.LoadCaptureOptionParameters()
    cap_opt.transform_to_camera = True

    # Set 2d and 3d exposure time. Capture with white light, range [11, 100]ms, others [3, 100]ms.
    exposure_time = 100
    cap_opt.exposure_time_2d = exposure_time
    cap_opt.exposure_time_3d = exposure_time

    cap_opt.filter_range = 0
    cap_opt.phase_filter_range = 0

    cap_opt.projector_brightness = 240
    cap_opt.light_contrast_threshold = 3

    # ROI Setting
    start_x = 10
    start_y = 10
    width = 200
    height = 200

    roi = RVC.ROI(start_x, start_y, width, height)

    # Get auto capture setting.exposure_time_3d,projector_brightness,
    # light_contrast_threshold will be adjusted automatically
    ret2, cap_opt = x.GetAutoCaptureSetting(cap_opt, roi)

    if ret2:
        print("get auto capture setting success!")
        print("auto exposure_time_2d: {} ms".format(cap_opt.exposure_time_2d))
        print("auto exposure_time_3d: {} ms".format(cap_opt.exposure_time_3d))
        print("auto projector_brightness: {}".format(cap_opt.projector_brightness))
        print("auto light_contrast_threshold: {}".format(cap_opt.light_contrast_threshold))
    else:
        print("get auto capture setting failed, custom setting will be used.")
        print(RVC.GetLastErrorMessage())

    # Capture a point map and a image.
    ret3 = x.Capture(cap_opt)

    # Create saving address of image and point map.
    save_address = "Data"
    TryCreateDir(save_address)

    if ret3 == True:
        print("RVC Camera capture successed!")

        # Get image data and image size.
        img = x.GetImage()
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
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        return 1

    # Close RVC Camera.
    x.Close()

    # Destroy RVC Camera.
    RVC.X1.Destroy(x)

    # Shutdown RVC System.
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
