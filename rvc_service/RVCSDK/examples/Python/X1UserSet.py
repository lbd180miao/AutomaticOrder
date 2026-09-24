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
        print("Can not find any RVC  Camera!")
        RVC.SystemShutdown()
        return -1

    device = devices[0]

    if device.IsFirmwareMatch() == False:
        print("device firmware mismatch, Please use RVCManager to upgrade the firmware")
        RVC.SystemShutdown()
        return -1

    # Create and open RVC Camera.
    x1 = RVC.X1.Create(device)
    x1.Open()
    if not x1.IsOpen():
        print("RVC X Camera is not opened!")
        RVC.X1.Destroy(x1)
        RVC.SystemShutdown()
        return 1
    
    print("RVC X Camera is opened!")

    # (1) Switch to the User Set with ID 1, name it "high_light",
    # and complete the capture.
    x1.SetCurrentUserSet(1)
    name1 = "high_light"
    ret = x1.SetUserSetName(1, name1)
    if not ret:
        print("SetUserSetName failed:", RVC.GetLastErrorMessage())
    # Set capture parameters
    cap_opt = RVC.X1_CaptureOptions()
    ret,cap_opt = x1.LoadCaptureOptionParameters()
    cap_opt.capture_mode = RVC.CaptureMode.CaptureMode_Normal

    if x1.Capture(cap_opt):
        print("RVC X Camera capture successed!")
    else:
        print("RVC X Camera capture failed!")

    # (2) Switch to the User Set with ID 0 and complete the capture.
    x1.SetCurrentUserSet(0)
    if x1.Capture():
        print("RVC X Camera capture successed!")
    else:
        print("RVC X Camera capture failed!")

    # (4) Switch to the User Set with ID 1 and save the parameter settings as the JSON file "high_light.json".
    x1.SetCurrentUserSet(1)
    json_name = "./high_light.json"
    x1.SaveSettingToFile(json_name)

    # (5) Switch to the User Set with ID 2, change the name of this User Set to "high_light2",
    # and import the parameter settings from the JSON file above.
    x1.SetCurrentUserSet(2)
    name2 = "high_light2"
    ret = x1.SetUserSetName(2, name2)
    if not ret:
        print("SetUserSetName failed:", RVC.GetLastErrorMessage())
    x1.LoadSettingFromFile(json_name)

    # Close RVC Camera.
    x1.Close()

    # Destroy RVC Camera.
    RVC.X1.Destroy(x1)

    # Shutdown RVC System.
    RVC.SystemShutdown()
    return 0


if __name__ == "__main__":
    App()
