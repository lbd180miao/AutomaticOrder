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
    
    x.Open()
    
    if x.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X1.")
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        exit(1)
    

    ret, T_extrinsic = x.GetExtrinsicMatrix()
    if ret == True:
        print("\nExtrinsicMatrix:")
        print(T_extrinsic)

    ret, T_intrinsic_matrix, T_distortion = x.GetIntrinsicParameters()
    if ret == True:
        print("\nIntrinsicParameters:")
        print(T_intrinsic_matrix)
        print("\ndistortion:")
        print(T_distortion)

    # Close RVC Camera.
    x.Close()

    # Destroy RVC Camera.
    RVC.X1.Destroy(x)

    # Shutdown RVC System.
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
