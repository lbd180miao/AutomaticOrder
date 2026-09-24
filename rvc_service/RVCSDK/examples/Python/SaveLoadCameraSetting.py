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

    # Save CameraSetting
    ret1 = x.SaveSettingToFile("d://test.json")
    if(ret1 == False):
        print("RVC Camera failed to SaveSettingToFile !" )
        print(RVC.GetLastErrorMessage())
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        return 1

    # Load CameraSetting
    ret1 = x.LoadSettingFromFile("d://test.json")
    if(ret1 == False):
        print("RVC Camera failed to LoadSettingFromFile !" )
        print(RVC.GetLastErrorMessage())
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        return 1

     # Load CaptureOptions
    ret, x1_opts= x.LoadCaptureOptionParameters()

     # Test RVC Camera is opened or not.
    if ret1 == False:
        print("LoadCaptureOptionParameters failed !" )
        print(RVC.GetLastErrorMessage())
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        return 1
    
    
    # Capture a point map and a image.
    ret2 = x.Capture(x1_opts)

    
    if ret2 == True:
        print("RVC Camera capture successed!")
        # Get image data.
        image = x.GetImage()
    
        # Get point map data (m).
        pm = x.GetPointMap()
        
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


def UseX2():
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

    ret1 = x.SaveSettingToFile("d://test.json")
    if(ret1 == False):
        print("RVC Camera failed to SaveSettingToFile !" )
        print(RVC.GetLastErrorMessage())
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        return 1

    # Load CameraSetting
    ret1 = x.LoadSettingFromFile("d://test.json")
    if(ret1 == False):
        print("RVC Camera failed to LoadSettingFromFile !" )
        print(RVC.GetLastErrorMessage())
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
    UseX1()
    UseX2()
