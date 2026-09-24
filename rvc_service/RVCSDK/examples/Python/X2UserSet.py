# Copyright (c) RVBUST, Inc - All rights reserved.
import PyRVC as RVC
import os


def App():

    # Initialize RVC system.
    RVC.SystemInit()

    # Choose RVC Camera type (USB, GigE or All)
    opt = RVC.SystemListDeviceTypeEnum.All

    # Scan all RVC Camera devices.
    ret, devices = RVC.SystemListDevices(opt)

    # Find whether any Camera is connected or not.
    if len(devices) == 0:
        print("Can not find any Camera!")
        RVC.SystemShutdown()
        return -1
    
    if devices[0].IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        return -1

    # Create and open RVC Camera.
    x2 = RVC.X2.Create(devices[0])
    x2.Open()
    if not x2.IsOpen():
        print("RVC X Camera is not opened!")
        RVC.X2.Destroy(x2)
        RVC.SystemShutdown()
        return 1
    
    print("RVC X Camera is opened!")

    # (1) Switch to the User Set with ID 1, name it "high_light", set the capture mode of the parameter group to
    # CaptureMode_Ultra and complete the capture.
    x2.SetCurrentUserSet(1)
    name1 = "high_light"
    ret = x2.SetUserSetName(1, name1)
    if not ret:
        print("SetUserSetName failed:", RVC.GetLastErrorMessage())
    # Set capture parameters
    cap_opt = RVC.X2_CaptureOptions()
    ret,cap_opt = x2.LoadCaptureOptionParameters()
    cap_opt.capture_mode = RVC.CaptureMode.CaptureMode_Ultra

    if x2.Capture(cap_opt):
        print("RVC X Camera capture successed!")
    else:
        print("RVC X Camera capture failed!")

    # (2) Switch to the User Set with ID 0 and complete the capture.
    x2.SetCurrentUserSet(0)
    if x2.Capture():
        print("RVC X Camera capture successed!")
    else:
        print("RVC X Camera capture failed!")

    # (4) Switch to the User Set with ID 1 and save the parameter settings as the JSON file "high_light.json".
    x2.SetCurrentUserSet(1)
    x2.SaveSettingToFile("./high_light.json")

    # (5) Switch to the User Set with ID 2, change the name of this User Set to "high_light2", and import the parameter
    # settings from the JSON file "high_light.json".
    x2.SetCurrentUserSet(2)
    name2 = "high_light2"
    ret = x2.SetUserSetName(2, name2)
    if not ret:
        print("SetUserSetName failed:", RVC.GetLastErrorMessage())
    x2.LoadSettingFromFile("./high_light.json")

    # Close RVC Camera.
    x2.Close()

    # Destroy RVC Camera.
    RVC.X2.Destroy(x2)

    # Shutdown RVC System.
    RVC.SystemShutdown()
    return 0


if __name__ == "__main__":
    App()