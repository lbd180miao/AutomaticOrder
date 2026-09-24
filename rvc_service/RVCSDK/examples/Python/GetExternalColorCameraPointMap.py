import PyRVC as RVC
import numpy as np
import cv2
import os
from Utils.Tools import *

# This example shows the process of acquiring the point cloud of an external camera. Note that this program cannot be
# run directly. The part that acquires the image of the external camera needs to be modified.
if __name__ == "__main__":
    # Prepare work: Users need to calibrate the external camera themselves. 
    # The quality of calibration directly affects the quality of final result.
    external_camera_intrinsic_matrix = [9609.9961, 0, 1231.808, 0, 9608.9238, 1020.5879, 0, 0, 1]    # Needs to be modified.
    external_camera_camera_distortion = [0.21287285, -1.2765415, 0.00071774476, -0.0017654195, -11.771881]  # Needs to be modified.
    external_camera_image_width = 2448;                                             # Needs to be modified.
    external_camera_image_height = 2048;                                            # Needs to be modified.
    
    # 1. Initialize
    RVC.SystemInit()
    opt = RVC.SystemListDeviceTypeEnum.All
    ret, devices = RVC.SystemListDevices(opt)
    if len(devices) == 0:
        print("Can not find any RVC Camera!")
        RVC.SystemShutdown()
        exit(1)
    if devices[0].IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        exit(1)
    x = RVC.X2.Create(devices[0])
    ret1 = x.Open()
    if x.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(1)
    ret, info = devices[0].GetDeviceInfo()
    if info.support_extra:
        print("Device has already support color camera!")
        RVC.SystemShutdown()
        exit(1)

    save_dir = "Data"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    # 2. Capture three point maps with 4*11 calibration board to get external camera extrinsic matrix.
    # 2.1 capture first point map
    input("Put the calibration board at the nearest working distance and take first frame. Press Enter to continue...")
    ret = x.Capture()
    internal_camera_point_map0 = x.GetPointMap().Clone()        
    internal_camera_image0 = x.GetImage(RVC.CameraID_Left).Clone()
    internal_camera_point_map0.SaveWithImage("{}/calibration_internal0.ply".format(save_dir), internal_camera_image0, RVC.PointMapUnitEnum.Meter, True)
    internal_camera_image0.SaveImage(save_dir + "/calibration_internal0.png")

    external_camera_image0 = np.array([...])  # External image should be numpy array. Needs to be modified.

    # 2.2 capture second point map
    input("Put the calibration board at the middle working distance and take second frame. Press Enter to continue...")
    ret = x.Capture()
    internal_camera_point_map1 = x.GetPointMap().Clone()
    internal_camera_image1 = x.GetImage(RVC.CameraID_Left).Clone()
    internal_camera_point_map1.SaveWithImage("{}/calibration_internal1.ply".format(save_dir), internal_camera_image1, RVC.PointMapUnitEnum.Meter, True)
    internal_camera_image1.SaveImage(save_dir + "/calibration_internal1.png")
    external_camera_image1 = np.array([...])  # External image should be numpy array. Needs to be modified.

    # 2.3 capture third point map
    input("Put the calibration board at the furthest working distance and take third frame. Press Enter to continue...")
    ret = x.Capture()
    internal_camera_point_map2 = x.GetPointMap().Clone()
    internal_camera_image2 = x.GetImage(RVC.CameraID_Left).Clone()
    internal_camera_point_map2.SaveWithImage("{}/calibration_internal2.ply".format(save_dir), internal_camera_image2, RVC.PointMapUnitEnum.Meter, True)
    internal_camera_image2.SaveImage(save_dir + "/calibration_internal2.png")
    external_camera_image2 = np.array([...])  # External image should be numpy array. Needs to be modified.

    # 2.4 get external camera extrinsic matrix
    error_code, external_camera_extrinsic_matrix, error = RVC.GetExternalCameraExtrinsicMatrix(
            internal_camera_image0, internal_camera_point_map0, external_camera_image0, 
            internal_camera_image1, internal_camera_point_map1, external_camera_image1, 
            internal_camera_image2, internal_camera_point_map2, external_camera_image2, 
            external_camera_image_width, external_camera_image_height,
            external_camera_intrinsic_matrix,
            external_camera_camera_distortion)
    if error_code != 0:
        print("Get external camera extrinsic matrix failed! Error code: ", error_code)
        x.Close()
        RVC.X2.Destroy(x)
        RVC.SystemShutdown()
        exit(0)

    print("External camera extrinsic matrix: ", external_camera_extrinsic_matrix)
    print("Reprojection error: ", error)
    
    # 3. After calibration, we can capture a point map with RVC camera and the corresponding image by external camera and get external camera point map.
    ret = x.Capture()
    internal_camera_point_map = x.GetPointMap()        
    internal_camera_image = x.GetImage(RVC.CameraID_Left)
    internal_camera_point_map.SaveWithImage("{}/scene_internal.ply".format(save_dir), internal_camera_image, RVC.PointMapUnitEnum.Meter, True)
    internal_camera_image.SaveImage(save_dir + "/scene_internal.png")
    external_camera_point_map = RVC.GetExternalCameraPointMap(
        internal_camera_point_map, 
        external_camera_image_width, external_camera_image_height, 
        external_camera_intrinsic_matrix, external_camera_camera_distortion, external_camera_extrinsic_matrix)
    external_camera_point_map.Save("{}/scene_external.ply".format(save_dir), RVC.PointMapUnitEnum.Meter, True)
            
    x.Close()
    RVC.X2.Destroy(x)
    RVC.SystemShutdown()
