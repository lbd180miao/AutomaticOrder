# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import os
import numpy as np
import cv2
from Utils.Tools import *


def InversionRt(R, t):
    R_inv = R.T
    t_inv = -np.dot(R_inv, t)
    return R_inv, t_inv


def stitch_online():
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
    x2 = RVC.X2.Create(device)
    x2.Open()
    if x2.IsOpen() == False:
        print("Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X2.")
        RVC.X2.Destroy(x2)
        RVC.SystemShutdown()
        exit(1)

    ret, info = device.GetDeviceInfo()
    camera_id = RVC.CameraID_Left
    if info.support_extra:
        camera_id = RVC.CameraID_Extra

    saveFolder = "./output/"
    TryCreateDir(saveFolder)

    x2.Capture()
    point_map0 = x2.GetPointMap()
    image0 = x2.GetImage(camera_id)
    point_map0.SaveWithImage(saveFolder + "/point_map0.ply",
                             image0, RVC.PointMapUnitEnum.Millimeter, True)
    image0.SaveImage(saveFolder + "/image0.png")

    point_maps = []
    images = []
    point_maps.append(point_map0.Clone())
    images.append(image0.Clone())

    total_stitch_count = 3
    Rs = []
    ts = []
    for count in range(1, total_stitch_count):
        input("Move camera and take next frame. Press Enter to continue...")
        x2.Capture()
        point_map = x2.GetPointMap()
        image = x2.GetImage(camera_id)
        point_map.SaveWithImage(saveFolder + "/point_map" + str(count) +
                                ".ply", image, RVC.PointMapUnitEnum.Millimeter, True)
        image.SaveImage(saveFolder + "/image" + str(count) + ".png")
        type = RVC.CodedCircleMarkerType()
        # **** Notice: need to be changed according to the actual type. ****
        type.N = 15
        type.r1_to_r0_ratio = 4.0 / 1.5
        type.r2_to_r0_ratio = 6.0 / 1.5
        ret, R, t = RVC.GetTwoCameraTransformByCodedCircleMarker(point_maps[-1], images[-1], point_map, image,
                                                                 type)
        Rs.append(R)
        ts.append(t)
        if ret != 0:
            print(
                "Failed to get two camera transform by coded circle marker, error code: %d" % ret)
            x2.Close()
            RVC.X2.Destroy(x2)
            RVC.SystemShutdown()
            return
        RVC.TransformPointCloud(R, t, point_map)
        point_map.SaveWithImage(saveFolder + "/point_map" + str(count) +
                                "_transformed.ply", image, RVC.PointMapUnitEnum.Millimeter, True)

        point_maps.append(point_map.Clone())
        images.append(image.Clone())

    # The above is to convert all point clouds to the first camera coordinate system.
    # Option: the following is to convert all point clouds to the last camera coordinate system.
    R_inv, t_inv = InversionRt(Rs[-1], ts[-1])
    for i in range(len(point_maps) - 1):
        RVC.TransformPointCloud(R_inv, t_inv, point_maps[i])
        point_maps[i].SaveWithImage(saveFolder + "/point_map" + str(i) +
                                    "_transformed_to_last.ply", images[i], RVC.PointMapUnitEnum.Millimeter, True)

    # If use CreateFromFile() or Clone(), we should call destroy function to return resources to RVC system
    for i in range(len(point_maps)):
        RVC.PointMap.Destroy(point_maps[i])
        RVC.Image.Destroy(images[i])
    x2.Close()
    RVC.X2.Destroy(x2)
    RVC.SystemShutdown()
    return


def stitch_offline(folder, ply_names, image_names):
    image0 = RVC.Image.CreateFromFile(os.path.join(folder, image_names[0]))
    image1 = RVC.Image.CreateFromFile(os.path.join(folder, image_names[1]))
    point_map0 = RVC.PointMap.CreateFromFile(
        os.path.join(folder, ply_names[0]), image0.GetSize(), RVC.PointMapUnitEnum.Meter)
    point_map1 = RVC.PointMap.CreateFromFile(
        os.path.join(folder, ply_names[1]), image1.GetSize(), RVC.PointMapUnitEnum.Meter)
    if not (image0.IsValid() and image1.IsValid() and point_map0.IsValid() and point_map1.IsValid()):
        print("Failed to load image or point cloud")
        return

    type = RVC.CodedCircleMarkerType()
    type.N = 15  # Need to be changed according to the actual type
    type.r1_to_r0_ratio = 4.0 / 1.5
    type.r2_to_r0_ratio = 6.0 / 1.5

    ret, R1, t1 = RVC.GetTwoCameraTransformByCodedCircleMarker(
        point_map0, image0, point_map1, image1, type)
    print(R1)
    print(t1)
    if ret != 0:
        print(
            f"Failed to get two camera transform by coded circle marker, ret: {ret}")
        return
    RVC.TransformPointCloud(R1, t1, point_map1)
    save_folder = os.path.join(folder, "output/")
    TryCreateDir(save_folder)
    point_map1.SaveWithImage(save_folder + "/output1.ply",
                             image1, RVC.PointMapUnitEnum.Meter, True)

    if len(ply_names) < 3 or len(image_names) < 3:
        return
    # Convert point_map2 to the coordinate system of the point_map0
    image2 = RVC.Image.CreateFromFile(os.path.join(folder, image_names[2]))
    point_map2 = RVC.PointMap.CreateFromFile(
        os.path.join(folder, ply_names[2]), image2.GetSize(), RVC.PointMapUnitEnum.Meter)

    ret, R2, t2 = RVC.GetTwoCameraTransformByCodedCircleMarker(
        point_map1, image1, point_map2, image2, type)
    if ret != 0:
        print(
            f"Failed to get two camera transform by coded circle marker, ret: {ret}")
        return

    RVC.TransformPointCloud(R2, t2, point_map2)
    point_map2.SaveWithImage(os.path.join(save_folder, "output2.ply"),
                             image2, RVC.PointMapUnitEnum.Meter, True)

    # If use CreateFromFile() or Clone(), we should call destroy function to return resources to RVC system
    RVC.PointMap.Destroy(point_map0)
    RVC.PointMap.Destroy(point_map1)
    RVC.PointMap.Destroy(point_map2)
    RVC.Image.Destroy(image0)
    RVC.Image.Destroy(image1)
    RVC.Image.Destroy(image2)


# User guild: RVCSDK/docs/PointCloudStitchingManual.pdf
if __name__ == "__main__":
    stitch_online()
    exit(0)
    stitch_offline("./Data/", ["0.ply", "1.ply",
                   "2.ply"], ["0.png", "1.png", "2.png"])
    exit(0)
