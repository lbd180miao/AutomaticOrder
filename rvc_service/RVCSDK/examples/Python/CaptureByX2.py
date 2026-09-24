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

    x = RVC.X2.Create(device)
    x.Open()
    if x.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)

    ret, info = device.GetDeviceInfo()
    camera_id = RVC.CameraID_Left
    if info.support_extra:
        camera_id = RVC.CameraID_Extra

    # Print ExposureTime Range
    _, exp_range_min, exp_range_max = x.GetExposureTimeRange()
    print("ExposureTime Range:[{}, {}]".format(exp_range_min, exp_range_max))

    # Set capture parameters
    cap_opt = RVC.X2_CaptureOptions()
    ret,cap_opt = x.LoadCaptureOptionParameters()
    # Transform point map's coordinate to camera
    # plane(RVC.CameraID_NONE)
    cap_opt.transform_to_camera = camera_id
    # Set camera exposure time (3~100) ms
    cap_opt.exposure_time_2d = 20
    cap_opt.exposure_time_3d = 20
    # Set 2d and 3d gain. the default value is 0. The gain value of each series cameras is different, you can call function GetGainRange() to get specific range.
    cap_opt.gain_2d = 0
    cap_opt.gain_3d = 0
    # Set 2d and 3d gamma. the default value is 1. The gamma value of each series cameras is different, you can call function GetGammaRange() to get specific range.
    cap_opt.gamma_2d = 1
    cap_opt.gamma_3d = 1
    # range in [0, 10]. the default value is 3. The contrast of point less than this value will be treat * as invalid point and1`` be removed.
    cap_opt.light_contrast_threshold = 2
    # Set projector color. the default value is RVC.ProjectorColor_Blue.
    cap_opt.projector_color = RVC.ProjectorColor_Blue

    # Capture a point map and a image.
    ret2 = x.Capture(cap_opt)

    # Create saving address of image and point map.
    save_dir = "Data"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    if ret2 == True:
        # Get image data. choose left or right side. the point map is map to left image.
        img = x.GetImage(camera_id)

        # Save image
        if img.SaveImage(save_dir + "/image.png"):
            print("Save image successed!")
        else:
            print("Save image failed!")

        # Save point map (m) to file.
        if x.GetPointMap().Save("{}/test.ply".format(save_dir), RVC.PointMapUnitEnum.Meter):
            print("Save point map successed!")
        else:
            print("Save point map failed!")

        # Save mesh to file.
        x.GetMesh().Save("{}/test.stl".format(save_dir), RVC.PointMapUnitEnum.Meter)

    else:
        print("RVC Camera capture failed!")
        print(RVC.GetLastErrorMessage())
        x.Close()
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(0)
    # Close RVC Camera
    x.Close()

    # Destroy RVC Camera
    RVC.X2.Destroy(x)

    # Shut Down RVC System
    RVC.SystemShutdown()
