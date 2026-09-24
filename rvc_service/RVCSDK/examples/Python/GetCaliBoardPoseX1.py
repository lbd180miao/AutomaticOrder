# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import sys
import os
import numpy as np
import cv2

from Utils.CaliBoardUtils import *
from Utils.Tools import *


def App(gamma, pattern_type):

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
    #
    x = RVC.X1.Create(devices[0], RVC.CameraID_Left)

    # Test RVC Camera is valid or not
    if x.IsValid() == False:
        print("RVC Camera is not valid!")
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        exit(1)
    #PrintCaptureMode(devices[0])

    # Open RVC Camera
    ret1 = x.Open()

    # Test RVC Camera is opened or not
    if x.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X1.")
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        exit(1)
        
    # Print ExposureTime Range
    _, exp_range_min, exp_range_max = x.GetExposureTimeRange()
    print("ExposureTime Range:[{}, {}]".format(exp_range_min, exp_range_max))

    # Set capture parameters
    cap_opt = RVC.X1_CaptureOptions()
    ret,cap_opt = x.LoadCaptureOptionParameters()
    # Choose point map's coordinate. True for camera coordinate and False for cali board coordinate
    cap_opt.transform_to_camera = True
    # Set camera exposure time (3~100) ms
    cap_opt.exposure_time_2d = 6
    cap_opt.exposure_time_3d = 6
    cap_opt.use_projector_capturing_2d_image = True

    # Capture a point map and a image.
    ret2 = x.Capture(cap_opt)

    # Create saving address of image and point map.
    save_dir = "Data"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    if ret2 == True:
        # Get image data. choose left or right side. the point map is map to left image.
        img = x.GetImage()
        
        # Save image
        if img.SaveImage(save_dir + "/image.png"):
            print("Save image successed!")
        else:
            print("Save image failed!")
        # Convert point map (m) to array and save it.
        pm = np.array(x.GetPointMap(), copy=False).reshape(-1, 3)
        # Save point map (m) to file.
        if x.GetPointMap().Save("Data/test.ply", RVC.PointMapUnitEnum.Meter):
            print("Save point map successed!")
        else:
            print("Save point map failed!")

        img = np.array(img, copy=False)
        # Get cali borad pose by image and point cloud
        cali_board_pose = GetCaliBoardPose(img,
                                           pm,
                                           gamma=gamma,
                                           m_type=pattern_type)
        if cali_board_pose is not None:
            print("transformation:{}".format(np.linalg.inv(cali_board_pose)))
            print("This transformation helps you transform point cloud from left camera coordinate of X1 to cali board coordinate")
        else:
            print("Get pose failed!")
    else:
        print("RVC Camera capture failed!")
        print(RVC.GetLastErrorMessage())
        x.Close()
        RVC.X1.Destroy(x)
        RVC.SystemShutdown()
        exit(0)
    # Close RVC Camera
    x.Close()

    # Destroy RVC Camera
    RVC.X1.Destroy(x)

    # Shut Down RVC System
    RVC.SystemShutdown()


if __name__ == "__main__":
    """
        This demo shows how to get cali borad pose based on the X1 left camera coordinate.
        For more details about order of circles center please see OpenCV documentation of 
        api findCirclesGrid().

        argv[1]: gamma (gamma>0), for adjust image brightness. gamma>1 will increse image brightness
                 and gamma<1 will decrease image brightness
        argv[2]: pattern_type, type of cali board pattern used. You can choose A2,A3, ..., A10
                 Center distance of circles on cali borad (m):
                 A2:0.08
                 A3:0.056
                 A4:0.04
                 A5:0.028
                 A6:0.02
                 A7:0.014
                 A8:0.01
                 A9:0.007
                 A10:0.0048

        Please select a cali board pattern of appropriate size according to the working distance
        of 3D camera. For details, please consult technical support.
    """

    if len(sys.argv) != 3:
        sys.exit("Invalid arguments: Usage: python3 GetCaliBoardPose.py 1 A4")

    gamma = sys.argv[1]
    pattern_type = sys.argv[2]

    print("gamma:{},pattern_type:{}".format(gamma, pattern_type))

    gamma = float(gamma)
    App(gamma, pattern_type)
