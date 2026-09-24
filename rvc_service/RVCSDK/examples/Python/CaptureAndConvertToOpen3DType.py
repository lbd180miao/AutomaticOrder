# Copyright (c) RVBUST, Inc - All rights reserved.
import open3d as o3d
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

    # Scan all RVC USB Camera devices.
    ret, devices = RVC.SystemListDevices(opt)
    print("RVC USB Camera devices number:%d" % len(devices))

    # Find whether any RVC Camera is connected or not.
    if len(devices) == 0:
        print("Can not find any RVC USB Camera!")
        RVC.SystemShutdown()
        return 1
    print("devices size = %d" % len(devices))
    if devices[0].IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        exit(1)
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
   # PrintCaptureMode(devices[0])

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

    if ret2 == True:
        print("RVC Camera capture successed!")

        pm = x.GetPointMap()
        n_pts = pm.GetSize().rows * pm.GetSize().cols
        pm = np.array(pm, copy=False).reshape(-1, 3)
        pcd_o3d = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pm.reshape((-1, 3))))
        step = n_pts // 10000

        for i in range(0,n_pts,step):
            rvc_point = pm[i]
            o3d_point = pcd_o3d.points[i]
            print(f"index: {i} RVC::PointMap:{rvc_point} , open3d::PointCloud:{o3d_point}")

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
