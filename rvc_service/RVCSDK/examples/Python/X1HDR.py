# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import numpy as np
import cv2
import os
from Utils.Tools import *


def App():

    # Initialize RVC system.
    RVC.SystemInit()

    # Choose RVC Camera type (USB, GigE or All)
    opt = RVC.SystemListDeviceTypeEnum.All

    # Scan all RVC Camera devices.
    ret, devices = RVC.SystemListDevices(opt)

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

    # Set capture parameters.
    cap_opt = RVC.X1_CaptureOptions()
    ret,cap_opt = x.LoadCaptureOptionParameters()

    # Set HDR exposure times [0, 2, 3]. 0 presents not use hdr. 2 and 3 presents hdr times.
    # Capture with white light, range [11, 100]ms, others [3, 100]ms.
    cap_opt.hdr_exposure_times = 3
    # Set the first capture exposure time
    cap_opt.SetHDRExposureTimeContent(0, exp_range_min)
    # Set the second capture exposure time
    cap_opt.SetHDRExposureTimeContent(1, int((exp_range_min + exp_range_max)/2))
    # Set the third capture exposure time
    cap_opt.SetHDRExposureTimeContent(2, exp_range_max)

    cap_opt.SetHDRProjectorBrightnessContent(0, 100)
    cap_opt.SetHDRProjectorBrightnessContent(1, 240)

    # Capture a point map and a image with default setting.
    ret2 = x.Capture(cap_opt)

    # Create saving address of image and point map.
    save_address = "Data"
    TryCreateDir(save_address)

    if ret2 == True:
        print("RVC Camera capture successed!")

        # Get image data.
        img = x.GetImage()
        width = img.GetSize().cols
        height = img.GetSize().rows

        # Get image size and color information.
        print("width=%d, height=%d" % (width, height))
        if img.GetType() == RVC.ImageTypeEnum.Mono8:
            print("This is mono camera")
        else:
            print("This is color camera")

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

    # Shut Down RVC System.
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
