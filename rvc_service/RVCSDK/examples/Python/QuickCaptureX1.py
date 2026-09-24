# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import os
import numpy as np
import cv2
from Utils.Tools import *


def App():
    # Initialize RVC system.
    RVC.SystemInit()

    # Find Device

    # Method 1,Find device by index.
    ret, devices = RVC.SystemListDevices(RVC.SystemListDeviceTypeEnum.All)
    if len(devices) == 0:
        print("Can not find any Device!")
        RVC.SystemShutdown()
        return -1
    device = devices[0]

    # Method 2,Find device by sn.
    # This is the most recommended method when you have multiple cameras.
    # device1 = RVC.SystemFindDevice("12345678")
    if devices[0].IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        return 1
    # Create and Open
    x1 = RVC.X1.Create(device, RVC.CameraID_Left)
    ret = x1.Open()
    if x1.IsOpen() == True:
        print("RVC Camera is opened!")
    else:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X1.")
        RVC.X1.Destroy(x1)
        RVC.SystemShutdown()
        return -1
    
    ret, info = device.GetDeviceInfo()
    print(info.name + "-" + info.sn)

    # PrintCaptureMode(devices[0])
    # Print ExposureTime Range
    _, exp_range_min, exp_range_max = x1.GetExposureTimeRange()
    print("ExposureTime Range:[{}, {}]".format(exp_range_min, exp_range_max))

    # Capture
    ret = x1.Capture()
    if ret:
        print("RVC Camera capture successed!")
    else:
        print("RVC Camera capture failed!")
        print(RVC.GetLastErrorMessage())
        x1.Close()
        RVC.X1.Destroy(x1)
        RVC.SystemShutdown()
        return -1

    # Data Process
    save_address = "Data"
    TryCreateDir(save_address)
    save_address += "/" + info.sn
    TryCreateDir(save_address)
    save_address += "/x1"
    TryCreateDir(save_address)

    img = x1.GetImage()
    pm = x1.GetPointMap()

    pm.Save(save_address + "/pointmap.ply",
            RVC.PointMapUnitEnum.Millimeter, True)
    pm.SaveWithImage(save_address + "/pointmap_color.ply",
                     img, RVC.PointMapUnitEnum.Millimeter, True)
    img.SaveImage(save_address+"/image.png")

    # numpy extension
    img_np = np.array(img, copy=False)
    pm_np = np.array(pm, copy=False).reshape(-1, 3)
    size = img_np.size

    # Release
    x1.Close()
    RVC.X1.Destroy(x1)
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
