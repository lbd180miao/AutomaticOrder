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
    # Create a RVC Camera
    x = RVC.X2.Create(devices[0])

    # Test RVC Camera is valid or not
    if x.IsValid() == False:
        print("RVC Camera is not valid!")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)
    
    # Print Supported Capture_Mode
    #PrintCaptureMode(devices[0])

    # Open RVC Camera
    ret1 = x.Open()

    # Test RVC Camera is opened or not
    if x.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)

    ret, info = devices[0].GetDeviceInfo()
    camera_id = RVC.CameraID_Left
    if info.support_extra:
        camera_id = RVC.CameraID_Extra

    # Print ExposureTime Range
    _, exp_range_min, exp_range_max = x.GetExposureTimeRange()
    print("ExposureTime Range:[{}, {}]".format(exp_range_min, exp_range_max))

    # Set capture parameters
    cap_opt = RVC.X2_CaptureOptions()
    ret,cap_opt = x.LoadCaptureOptionParameters()
    # Set capture mode
    cap_opt.capture_mode = RVC.CaptureMode_SwingLineScan
    # Set the scan time. The longer the scan time, the denser the point cloud will be.
    cap_opt.line_scanner_scan_time_ms = 2500
    # Set exposure time
    cap_opt.line_scanner_exposure_time_us = 300
    # Set minimum distance
    cap_opt.line_scanner_min_distance = 400
    # Set maximum distance
    cap_opt.line_scanner_max_distance = 800
    # Set whether to enable point clouds to correspond to 2D images.
    # If set to true, a depth map will be generated, otherwise no depth map will be generated.
    cap_opt.correspond2d = False

    #When `correspond2d == true`, setting `pointcloud_completion` to true results in a dense point cloud
    cap_opt.pointcloud_completion = False

    # Set line scanner confidence
    cap_opt.line_scanner_confidence = 0.72

    # Capture a point map and a image.
    ret2 = x.Capture(cap_opt)

    # Create saving address of image and point map.
    save_dir = "Data"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    if ret2 == True:
        # Get image data. choose left or right side. the point map is map to left image.
        img = x.GetImage(camera_id)
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
