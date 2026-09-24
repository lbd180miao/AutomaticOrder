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

    # device = RVC.SystemFindDevice("I1UM358B001")

    if devices[0].IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        return 1
    # Create a RVC Camera 
    x = RVC.X2.Create(devices[0])

    # Test RVC Camera is valid or not.
    if x.IsValid() == True:
        print("RVC Camera is valid!")
    else:
        print("RVC Camera is not valid!")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        return 1
    
    #PrintCaptureMode(devices[0])

    # Open RVC Camera.
    ret1 = x.Open()

    # Test RVC Camera is opened or not.
    if x.IsOpen() == True:
        print("RVC Camera is opened!")
    else:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        return 1
    
    ret, info = devices[0].GetDeviceInfo()
    camera_id = RVC.CameraID_Left
    if info.support_extra:
        camera_id = RVC.CameraID_Extra

    # Print ExposureTime Range
    _, exp_range_min, exp_range_max = x.GetExposureTimeRange()
    print("ExposureTime Range:[{}, {}]".format(exp_range_min, exp_range_max))

    # Set capture parameters.
    cap_opt = RVC.X2_CaptureOptions()
    ret,cap_opt = x.LoadCaptureOptionParameters()

    # Set capture mode
    cap_opt.capture_mode = RVC.CaptureMode_SwingLineScan
    # Set the scan time. The longer the scan time, the denser the point cloud will be.
    cap_opt.line_scanner_scan_time_ms = 1000
    # Set exposure time
    cap_opt.line_scanner_exposure_time_us = 300
    # Set minimum distance
    cap_opt.line_scanner_min_distance = 400
    # Set maximum distance
    cap_opt.line_scanner_max_distance = 1000
    # Set whether to enable point clouds to correspond to 2D images.
    # If set to true, a depth map will be generated, otherwise no depth map will be generated.
    cap_opt.correspond2d = False

    # Set ROI's width, height, offset x and y
    cap_opt.roi.width = 512
    cap_opt.roi.height = 512
    cap_opt.roi.x = 256
    cap_opt.roi.y = 256

    retRange,roiRange = x.GetRoiRange()


    retRoi = x.CheckRoi(cap_opt.roi)

    if retRoi == False:
        cap_opt.roi =  x.AutoAdjustRoi(cap_opt.roi)


    # Capture a point map and a image with default setting.
    ret2 = x.Capture(cap_opt)

    # Create saving address of image and point map.
    save_address = "Data"
    TryCreateDir(save_address)

    if ret2 == True:
        print("RVC Camera capture successed!")

        # Get image data.
        img = x.GetImage(camera_id)
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
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        return 1

    # Close RVC Camera.
    x.Close()

    # Destroy RVC Camera.
    RVC.X2.Destroy(x)

    # Shut Down RVC System.
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
