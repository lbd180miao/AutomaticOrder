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
        print("Can not find any RVC  Camera!")
        RVC.SystemShutdown()
        return 1
    print("devices size =%d" % len(devices))
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

    # Set custom transformation.To get your transformation,please see GetCaliBoardPose.py
    # Note: coordinate select here should be the same as the capture setting when you
    #       get your transformation. The correctness of transformation matrix will be check
    #       in SetCustomTransformation()
    transformation = np.array([[-0.99532179, -0.0892033, -0.03711218,  0.26125841],
                               [-0.08950467, 0.99596495, 0.00653654,   0.1388469],
                               [0.03637935,  0.00982767, -0.99928973,  0.99669197],
                               [0.,          0.,         0.,           1.]])

    custom_transform_opt = RVC.X1_CustomTransformOptions()
    custom_transform_opt.coordinate_select = RVC.X1CustomTransformCoordinate.CoordinateSelect_CaliBoard
    custom_transform_opt.SetTransform(transformation)
    ret2 = x.SetCustomTransformation(custom_transform_opt)

    if ret2:
        print("set transformation success")
    else:
        print("set transformation failed!custom transformation will not be used!")
        print(RVC.GetLastErrorMessage())

    # Set capture parameters
    cap_opt = RVC.X1_CaptureOptions()
    ret,cap_opt = x.LoadCaptureOptionParameters()
    # Transform point map's coordinate to left/right(RVC.CameraID_Left/RVC.CameraID_Right) camera or reference
    # plane(RVC.CameraID_NONE)
    cap_opt.transform_to_camera = True
    # Set camera exposure time (3~100) ms
    cap_opt.exposure_time_2d = 20
    cap_opt.exposure_time_3d = 20

    # Capture a point map and a image.
    ret3 = x.Capture(cap_opt)

    # Create saving address of image and point map.
    save_address = "Data"
    TryCreateDir(save_address)

    if ret3 == True:
        print("RVC Camera capture successed!")

        # Get image data and image size.
        img = x.GetImage()
        width = img.GetSize().cols
        height = img.GetSize().rows

        # Check the camera color information.
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
