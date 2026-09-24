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

    # Set capture parameters
    cap_opt = RVC.X2_CaptureOptions()
    ret,cap_opt = x.LoadCaptureOptionParameters()
    # Set capture mode
    cap_opt.capture_mode = RVC.CaptureMode_FixedLineScan
    # Set trigger mode to software trigger
    cap_opt.trigger_mode = RVC.TriggerMode_SoftWare
    # Set exposure time
    cap_opt.line_scanner_exposure_time_us = 300
    # Set minimum distance
    cap_opt.line_scanner_min_distance = 400
    # Set maximum distance
    cap_opt.line_scanner_max_distance = 800
    # Set laser line brightness threshold
    cap_opt.line_scanner_brightness_threshold = 5
    # Set whether to enable point clouds to correspond to 2D images.
    # If set to true, a depth map will be generated, otherwise no depth map will be generated.
    cap_opt.correspond2d = False


    capture_times = 1000
    i = 0
    # Create saving address of image and point map.
    save_dir = "Data"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # Reset timestamp to zero before starting capture
    x.ResetTimestamp()  

    #Start Fixed Line Scan 
    ret = x.StartFixedLineScan(cap_opt)
    if ret == False:
        print("Start Fixed Line Scan failed!")
        x.Close()
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)
        

    #Get Fixed Line Scan PointMap continuously
    while i < capture_times:
        pm = RVC.PointMap()
        # Capture a point map and a image.
        ret = x.GetFixedLineScanPointMap(pm)

        if ret == True and i%100 ==0:
            # Get timestamp of the captured point map
            timestamp = pm.GetTimestamp()
            print("Capture Fixed Line Scan Point Map %d, timestamp=%d us"%(i, timestamp))
            # Save point map (m) to file.
            if pm.Save("{}/test_{}.ply".format(save_dir,i), RVC.PointMapUnitEnum.Meter):
                print("Save point map %s/test_%d.ply successed!"% (save_dir,i))
            else:
                print("Save point map failed!")
                print(RVC.GetLastErrorMessage())
        i += 1

    #Stop Fixed Line Scan 
    x.StopFixedLineScan()

    # Close RVC Camera
    x.Close()

    # Destroy RVC Camera
    RVC.X2.Destroy(x)

    # Shut Down RVC System
    RVC.SystemShutdown()
