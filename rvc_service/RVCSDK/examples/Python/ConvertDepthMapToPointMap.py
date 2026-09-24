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

    # Scan all RVC USB Camera devices.
    ret, devices = RVC.SystemListDevices(opt)

    # Find whether any RVC Camera is connected or not.
    if len(devices) == 0:
        print("Can not find any RVC USB Camera!")
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
    if not x.IsValid():
        print("RVC Camera is not valid!")
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        return 1
    #PrintCaptureMode(devices[0])

    # Open RVC Camera.
    ret1 = x.Open()

    # Test RVC Camera is opened or not.
    if x.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X1.")
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        return 1
    
    # Print ExposureTime Range
    _, exp_range_min, exp_range_max = x.GetExposureTimeRange()
    print("ExposureTime Range:[{}, {}]".format(exp_range_min, exp_range_max))

    cap_opts = RVC.X1_CaptureOptions()
    ret,cap_opts = x.LoadCaptureOptionParameters()
    cap_opts.transform_to_camera = True
    custom_transform_options = RVC.X1_CustomTransformOptions()
    custom_transform_options.coordinate_select = RVC.X1CustomTransformCoordinate.CoordinateSelect_Disabled
    x.SetCustomTransformation(custom_transform_options)
    # Capture a point map and a image.
    ret2 = x.Capture(cap_opts)

    # Create saving address of image and point map.
    save_address = "Data"
    TryCreateDir(save_address)

    if ret2 == True:
        pm_sz = x.GetPointMap().GetSize()
        width = pm_sz.width
        height = pm_sz.height

        pm = np.array(x.GetPointMap(), copy=False).reshape(-1, 3)
        # Save point map (m) to file.
        if x.GetPointMap().Save("Data/test.ply", RVC.PointMapUnitEnum.Meter):
            print("Save point map successed!")
        else:
            print("Save point map failed!")

        dp = np.array(x.GetDepthMap(), copy=False)

        # convert depthmap to pointmap
        ret, intrinsic_matrix, distortion = x.GetIntrinsicParameters()
        intrinsic_matrix = np.array(intrinsic_matrix).reshape((3, 3))
        k1, k2, k3, p1, p2 = distortion
        distortion_cv = np.array([k1, k2, p1, p2, k3])

        X = range(width)
        Y = range(height)
        XY = np.array(np.meshgrid(X, Y), dtype=float).reshape((2, -1)).T
        XY = XY + [cap_opts.roi.x,cap_opts.roi.y]
        undistorted_XY = cv2.undistortPoints(
            XY, intrinsic_matrix, distortion_cv).reshape((height, width, 2))
        convert_pm = np.array([undistorted_XY[:, :, 0] * dp,
                               undistorted_XY[:, :, 1] * dp, dp]).reshape((3, -1)).T

        # compute convert error
        valid_mask0 = ~np.isnan(pm[:, 2])
        valid_mask1 = ~np.isnan(convert_pm[:, 2])
        sub_pm = np.abs(convert_pm[valid_mask0] - pm[valid_mask0])
        print(np.all(valid_mask0 == valid_mask1))
        print(f"min diff (mm): {np.min(sub_pm, axis=0) * 1000}")
        print(f"max diff (mm): {np.max(sub_pm, axis=0) * 1000}")
    else:
        print(RVC.GetLastErrorMessage())

    # Close RVC Camera.
    x.Close()

    # Destroy RVC Camera.
    RVC.X1.Destroy(x)

    # Shutdown RVC System.
    RVC.SystemShutdown()

    return 0


if __name__ == "__main__":
    App()
