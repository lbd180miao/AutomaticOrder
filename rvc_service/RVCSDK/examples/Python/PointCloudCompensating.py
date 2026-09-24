# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import os
import numpy as np
import cv2


class CameraHelper:
    x2 = RVC.X2()
    x2_opts = None
    camera_id = RVC.CameraID_Left

    def __init__(self):
        RVC.SystemInit()

    def __del__(self):
        if self.x2.IsOpen():
            self.x2.Close()
        if self.x2.IsValid():
            RVC.X2.Destroy(self.x2)
        RVC.SystemShutdown()

    def Open(self):
        RVC.SystemInit()
        opt = RVC.SystemListDeviceTypeEnum.All
        ret, devices = RVC.SystemListDevices(opt)
        print("RVC Camera devices number:", len(devices))
        if len(devices) == 0:
            print("Can not find any RVC Camera!")
            RVC.SystemShutdown()
            return False
        if devices[0].IsFirmwareMatch() == False:
            print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
            RVC.SystemShutdown()
            return False
        # Create and open RVC Camera
        device = devices[0]
        self.x2 = RVC.X2.Create(device)
        self.x2.Open()
        if self.x2.IsOpen() == False:
            print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
            RVC.X2.Destroy(self.x2)
            RVC.SystemShutdown()
            return False

        ret, info = device.GetDeviceInfo()
        self.camera_id = RVC.CameraID_Left
        if info.support_extra:
            self.camera_id = RVC.CameraID_Extra
        # Load capture options
        ret, self.x2_opts = self.x2.LoadCaptureOptionParameters()
        # Set the coordinate system to the camera coordinate system
        self.x2_opts.transform_to_camera = self.camera_id
        custom_transform_opt = RVC.X2_CustomTransformOptions()
        custom_transform_opt.coordinate_select = RVC.X2CustomTransformCoordinate.CoordinateSelect_Disabled
        ret = self.x2.SetCustomTransformation(custom_transform_opt)        
        return ret

    def Capture(self):
        is_capture_success = self.x2.Capture(self.x2_opts)
        if not is_capture_success:
            return RVC.PointMap(), RVC.Image()
        return self.x2.GetPointMap(), self.x2.GetImage(self.camera_id)

def CompensateForX2():
    camera_helper = CameraHelper()
    is_open_success = camera_helper.Open()
    if not is_open_success:
        print("RVC Camera fails to open!")
        return -1

    compensator = RVC.Compensator_FixedMarkers()

    # Capture a reference point map in static scene and initialize compensator.
    pm, image = camera_helper.Capture()
    ret = compensator.Initialize(pm, image, 0) # 0 for calibration board, 1 for concentric circles
    if ret != 0:
        print(f"Initialize fails! Error code: {ret}.")
        return -1
    print("Initialize successfully!")
    
    save_address = "Data"
    os.makedirs(save_address, exist_ok=True)
    # It is recommended to update the model within every 50 captures.
    # The value 50 is not fixed and needs to take into account the speed of the ambient temperature change and the camera shooting rhythm.
    # In this sample program, there are only 10 frames in between as a demonstration.
    interval_between_compensation = 10  # 100
    pm, image = camera_helper.Capture()
    pm.SaveWithImage(f"{save_address}/pointcloud_0.ply", image, RVC.PointMapUnitEnum.Meter, True)
    image.SaveImage(save_address + "/image_0.png")
    for _ in range(interval_between_compensation):
        camera_helper.Capture()
    
    # Capture the fixed markers and update compensation model.
    pm, image = camera_helper.Capture()
    ret, drift_distance = compensator.Update(pm, image)
    if ret != 0:
        print(f"Update compensation model fails! Error code: {ret}.")
        return -1
    print(f"Current drift distance: {drift_distance}")
    print("Update compensation model successfully!")
    
    # After update compensation model, we can compensate for the point cloud.
    pm, image = camera_helper.Capture()
    pm.SaveWithImage(f"{save_address}/pointcloud_n_before_compensate.ply", image, RVC.PointMapUnitEnum.Meter, True)
    image.SaveImage(save_address + "/image_n.png")
    ret, pm = compensator.Apply(pm)
    pm.SaveWithImage(f"{save_address}/pointcloud_n_after_compensate.ply", image, RVC.PointMapUnitEnum.Meter, True)
    print("Compensate pm successfully!")

    return 0


if __name__ == "__main__":
    """
    Use case: Compensate for the point cloud drift caused by changes of camera or ambient temperature
    
    Process: 
    1. Capture the fixed markers to initialize; 
    2. Use the camera normally and take n frames;
    3. Keep the camera in the same position as it was initialized and capture the same fixed markers to update the model; 
    4. Continue to use the camera to take n frames, and for each frame we can apply the updated model to compensate;
    5. Repeat the process of 3 and 4.
    It is recommended that n should be within 50. And the initialization step is recommended to be done after hand-eye calibration.
    """
    CompensateForX2()
