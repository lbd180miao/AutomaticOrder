# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import os
import numpy as np
import cv2
from Utils.Tools import *


def CodedCircleMarkerDetectOffline(folder, image_name):
    img = cv2.imread(folder + "/" + image_name)
    marker_type = RVC.CodedCircleMarkerType()
    marker_type.N = 15
    marker_type.r1_to_r0_ratio = 4.0 / 1.5
    marker_type.r2_to_r0_ratio = 6.0 / 1.5
    markers = RVC.DetectCodedCircleMarker(img, marker_type)
    print("markerNums: ", len(markers))
    for i in range(len(markers)):
        center = (int(markers[i].x), int(markers[i].y))
        cv2.circle(img, center, 0, (0, 0, 255), -1)
        cv2.putText(img, str(markers[i].code), center,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    cv2.namedWindow("image")
    cv2.moveWindow("image", 50, 25)
    new_height = 900
    new_width = int(img.shape[1] / img.shape[0] * new_height)
    img = cv2.resize(img, (new_width, new_height))
    cv2.imshow("image", img)
    cv2.waitKey(0)

def CodedCircleMarkerDetectOnline():
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
        return 1
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

    # while not press space
    while cv2.waitKey(10) != 32:
        x.Capture2D(camera_id)
        img = x.GetImage(camera_id)
        marker_type = RVC.CodedCircleMarkerType()
        # **** Notice: need to be changed according to the actual type. ****
        marker_type.N = 15
        marker_type.r1_to_r0_ratio = 4.0 / 1.5
        marker_type.r2_to_r0_ratio = 6.0 / 1.5
        markers = RVC.DetectCodedCircleMarker(img, marker_type)
        img = np.array(img, copy=False)
        print("markerNums: ", len(markers))
        img_show = img
        # if gray image, convert to BGR image
        if len(img.shape) == 2:
            img_show = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        for i in range(len(markers)):
            center = (int(markers[i].x), int(markers[i].y))
            cv2.circle(img_show, center, 0, (0, 0, 255), -1)
            cv2.putText(img_show, str(markers[i].code), center,
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.namedWindow("image")
        cv2.moveWindow("image", 50, 25)
        new_height = 900
        new_width = int(img_show.shape[1] / img_show.shape[0] * new_height)
        img_show = cv2.resize(img_show, (new_width, new_height))
        cv2.imshow("image", img_show)

    x.Close()
    RVC.X2.Destroy(x)
    RVC.SystemShutdown()
    return 0

def ConcentricCircleMarkerDetectOffline(folder: str, image_name: str, pointmap_name: str) -> None:
    # Load image and point map
    image_path = f"{folder}/{image_name}"
    pointmap_path = f"{folder}/{pointmap_name}"
    image = RVC.Image.CreateFromFile(image_path)
    pointmap = RVC.PointMap.CreateFromFile(pointmap_path, image.GetSize(), RVC.PointMapUnitEnum.Meter)

    print("only detect pixel 2d")
    ret2d, marker_num_2d, point2d = RVC.DetectConcentricCircleMarker2d(image)
    if ret2d == 0:
        print(f"2D marker num: {marker_num_2d}")
        pts2d = point2d[: 2 * marker_num_2d]  # trim to actual count
        for i in range(marker_num_2d):
            x, y = pts2d[2 * i], pts2d[2 * i + 1]
            print(f"Marker {i}: ({x}, {y})")
    else:
        print(f"DetectConcentricCircleMarker2d failed, error code = {ret2d}")

    print("\ndetect pixel 2d and point 3d")
    ret3d, marker_num_3d, point2d_3d, point3d = RVC.DetectConcentricCircleMarker3d(image, pointmap)
    if ret3d == 0:
        print(f"3D marker num: {marker_num_3d}")
        pts2d = point2d_3d[: 2 * marker_num_3d]
        pts3d = point3d[: 3 * marker_num_3d]
        for i in range(marker_num_3d):
            x, y = pts2d[2 * i], pts2d[2 * i + 1]
            X, Y, Z = pts3d[3 * i], pts3d[3 * i + 1], pts3d[3 * i + 2]
            print(f"Marker {i}: ({x}, {y}), ({X}, {Y}, {Z})")
    else:
        print(f"DetectConcentricCircleMarker3d failed, error code = {ret3d}")

    RVC.Image.Destroy(image)
    RVC.PointMap.Destroy(pointmap)

if __name__ == "__main__":
    example_type = 2
    if example_type == 0:
        CodedCircleMarkerDetectOnline()
    elif example_type == 1:
        CodedCircleMarkerDetectOffline("D:/", "0.png")
    elif example_type == 2:
        ConcentricCircleMarkerDetectOffline("D:/", "0.png", "0.ply")
    exit(0)
