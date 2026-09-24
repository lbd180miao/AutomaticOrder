# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import os
import numpy as np
import cv2
from Utils.Tools import *


def App():

    # Initialize RVC system.
    RVC.SystemInit()

    # Choose RVC Camera type (USB, GigE or All)
    opt = RVC.SystemListDeviceTypeEnum.All

    # Scan all RVC Camera devices.
    ret, devices = RVC.SystemListDevices(opt)
    print("RVC Camera devices number:%d" % len(devices))

    #  Find whether any RVC Camera is connected or not.
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

    # Capture a point map and a image.
    ret2 = x.Capture()

    # Create saving address of image and point map.
    save_address = "Data"
    TryCreateDir(save_address)

    if ret2 == True:
        print("RVC Camera capture successed!")

        # Get image data and image size.
        img = x.GetImage()
        width = img.GetSize().cols
        height = img.GetSize().rows
        print("width=%d, height=%d" % (width, height))

        # Get image type. 
        # Mono camera type is RVC.ImageTypeEnum.Mono8
        # Color camera type is RVC.ImageTypeEnum.RGB8 or RVC.ImageTypeEnum.BGR8
        img_type = img.GetType()

        # Save image
        if img.SaveImage(save_address + "/image.png"):
            print("Save image successed!")
        else:
            print("Save image failed!")

        # Convert point map (m) to array and save it.
        pm = np.array(x.GetPointMap(), copy=False).reshape(-1, 3)
        # Save point map (m) to file.
        if x.GetPointMap().Save("Data/test.ply", RVC.PointMapUnitEnum.Meter):
            print("Save point map successed!")
        else:
            print("Save point map failed!")
        pm = pm.reshape((height, width, 3))
        px = width // 2
        py = height // 2
        img = np.array(img, copy=False)
        # Get each 2D image points pixel value
        if img_type == RVC.ImageTypeEnum.Mono8:
            print("image pixel value at position (x,y)=(%d,%d) is (%d)" %
                  (px, py, img[px, py]))
        else:
            print("image pixel valud at position (x,y)=(%d,%d) is (%d,%d,%d)" %
                  (px, py, img[px, py, 0], img[px, py, 1], img[px, py, 2]))
        # Get each 3D points value
        print("corresponse xyz in point map is(%.6f, %.6f, %.6f)" %
              (pm[px, py, 0], pm[px, py, 1], pm[px, py, 2]))
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

    # Shutdwwn RVC System.
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
