import PyRVC as RVC
import numpy as np
import cv2
import os
from Utils.Tools import *
import time

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
    # Create a RVC Camera
    x = RVC.X2.Create(devices[0])

    # Test RVC Camera is valid or not
    if x.IsValid() == False:
        print("RVC Camera is not valid!")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)

    # Print Supported Capture_Mode
    # PrintCaptureMode(devices[0])

    # Open RVC Camera
    ret1 = x.Open()

    # Test RVC Camera is opened or not
    if x.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)

    _, info = devices[0].GetDeviceInfo()
    if not info.support_protective_cover:
        print("The device does not support protective cover")
        x.Close()
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)

    _, status = x.GetProtectiveCoverStatus()
    if status != RVC.ProtectiveCoverStatus.ProtectiveCoverStatus_Open:
        x.OpenProtectiveCover()
        print("ProtectiveCover is opening")

    print("ProtectiveCover is open")

    _, opts = x.LoadCaptureOptionParameters()
    ret = x.Capture(opts)
    if not ret:
        print("Capture failed")
        print(RVC.GetLastErrorMessage())
        
    x.CloseProtectiveCover()
        
    print("ProtectiveCover is closed")
    
    # Close RVC Camera
    x.Close()

    # Destroy RVC Camera
    RVC.X2.Destroy(x)

    # Shut Down RVC System
    RVC.SystemShutdown()
