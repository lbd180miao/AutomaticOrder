import PyRVC as RVC
import numpy as np
import cv2
import os
from Utils.Tools import *

if __name__ == "__main__":
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
    x = RVC.X1.Create(device)
    x.Open()
    if x.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X1.")
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        exit(1)

    ret, info = device.GetDeviceInfo()

    # ROI Setting
    start_x = 10
    start_y = 10
    width = 200
    height = 200

    roi = RVC.ROI(start_x, start_y, width, height)

    # Set capture parameters
    cap_opt = RVC.X1_CaptureOptions()
    ret,cap_opt = x.LoadCaptureOptionParameters()

    # Get auto 2d exposure time with high speed
    ret2, cap_opt = x.GetAuto2DExposureTime(cap_opt, roi)

    if ret2:
        print("get auto 2d exposure time success!")
        print("auto exposure_time_2d: {} ms".format(cap_opt.exposure_time_2d))
    else:
        print("get auto 2d exposure time failed, custom setting will be used.")
        print(RVC.GetLastErrorMessage())

    # Capture a image.
    ret3 = x.Capture2D(cap_opt)

    # Create saving address of image.
    save_dir = "Data"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    if ret3 == True:
        # Get image data.
        img = x.GetImage()

        # Save image
        if img.SaveImage(save_dir + "/image.png"):
            print("Save image successed!")
        else:
            print("Save image failed!")
    else:
        print("RVC Camera capture failed!")
        print(RVC.GetLastErrorMessage())
        x.Close()
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        exit(0)
    # Close RVC Camera
    x.Close()

    # Destroy RVC Camera
    RVC.X1.Destroy(x)

    # Shut Down RVC System
    RVC.SystemShutdown()
