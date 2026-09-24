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

    # ROI Setting
    roi = RVC.ROI(10, 10, 200, 200)

    # get hdr exposure parameters.
    ret2, cap_opt = x.GetAutoHdrCaptureSetting(cap_opt, roi)
    if ret2:
        print(f"projector_brightness: {cap_opt.projector_brightness}")
        if cap_opt.hdr_exposure_times == 0:
            print("hdr exposure setting will not be used")
            print("exposure_time_3d: {}".format(cap_opt.exposure_time_3d))
        else:
            print("hdr_exposure_times: {}".format(cap_opt.hdr_exposure_times))
            for i in range(cap_opt.hdr_exposure_times):
                print("hdr exposure index: {} exposure time: {}".format(
                    i + 1, cap_opt.GetHDRExposureTimeContent(i)))

        # Capture a point map and a image.
        ret3 = x.Capture(cap_opt)

        # Create saving address of image and point map.
        save_dir = "Data"
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        if ret3 == True:
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
        else:
            print("RVC Camera capture failed!")
            print(RVC.GetLastErrorMessage())
    else:
        print("get auto capture setting failed, custom setting will be used.")
        print(RVC.GetLastErrorMessage())

    # Close RVC Camera
    x.Close()

    # Destroy RVC Camera
    RVC.X2.Destroy(x)

    # Shut Down RVC System
    RVC.SystemShutdown()
