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
    if devices[0].IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        return 1
    # Method 2,Find device by sn.
    # This is the most recommended method when you have multiple cameras.
    # device = RVC.SystemFindDevice("M2GM012W019")

    # Create and Open
    x2 = RVC.X2.Create(device)
    ret = x2.Open()
    if x2.IsOpen() == True:
        print("RVC Camera is opened!")
    else:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x2)
        RVC.SystemShutdown()
        return -1

    ret, info = device.GetDeviceInfo()
    print(info.name + "-" + info.sn)
    camera_id = RVC.CameraID_Left
    if info.support_extra:
        camera_id = RVC.CameraID_Extra

    # Print ExposureTime Range
    _, exp_range_min, exp_range_max = x2.GetExposureTimeRange()
    print("ExposureTime Range:[{}, {}]".format(exp_range_min, exp_range_max))

    # Capture
    ret = x2.Capture()
    if ret:
        print("Capture successed!")
    else:
        print("Capture failed!")
        print(RVC.GetLastErrorMessage())
        x2.Close()
        RVC.X2.Destroy(x2)
        RVC.SystemShutdown()
        return -1

    # Data Process
    save_address = "Data"
    TryCreateDir(save_address)
    save_address += "/" + info.sn
    TryCreateDir(save_address)
    save_address += "/x2"
    TryCreateDir(save_address)

    img = x2.GetImage(camera_id)
    pm = x2.GetPointMap()

    pm.Save(save_address + "/pointmap.ply",
            RVC.PointMapUnitEnum.Millimeter, True)
    pm.SaveWithImage(save_address + "/pointmap_color.ply",
                     img, RVC.PointMapUnitEnum.Millimeter, True)
    img.SaveImage(save_address + "/image.png")

    # numpy extension
    img_np = np.array(img, copy=False)
    pm_np = np.array(pm, copy=False).reshape(-1, 3)
    size = img_np.size

    # Release
    x2.Close()
    RVC.X2.Destroy(x2)
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
