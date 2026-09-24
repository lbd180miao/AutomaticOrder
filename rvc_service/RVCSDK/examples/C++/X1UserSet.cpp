#include <RVC/RVC.h>

#include <fstream>
#include <iostream>
#include <string>

using namespace RVC;
using namespace std;

int main(int argc, char *argv[]) {
    // Initialize RVC system.
    RVC::SystemInit();

    // Choose RVC Camera type (USB, GigE or All)
    RVC::Device devices[10];
    size_t actual_size = 0;
    SystemListDevices(devices, 10, &actual_size, RVC::SystemListDeviceType::All);

    // Find whether any Camera is connected or not.
    if (actual_size == 0) {
        std::cout << "Can not find any Camera!" << std::endl;
        RVC::SystemShutdown();
        return -1;
    }

    if (devices[0].IsFirmwareMatch() == false) {
        std::cout << "device firmware mismatch, Please use RVCManager to upgrade the firmware" << std::endl;
        RVC::SystemShutdown();
        return -1;
    }

    // Create and open RVC Camera.
    RVC::Device device = devices[0];
    RVC::X1 x1 = RVC::X1::Create(device);
    x1.Open();
    if (!x1.IsOpen()) {
        std::cout << "RVC X Camera is not opened!" << std::endl;
        RVC::X1::Destroy(x1);
        RVC::SystemShutdown();
        return 1;
    }
    std::cout << "RVC X Camera is opened!" << std::endl;

    //(1) Switch to the User Set with ID 1, name it "high_light", set the capture mode of the parameter group to
    // CaptureMode_Ultra and complete the capture.
    x1.SetCurrentUserSet(1);
    const std::string name1 = "high_light";
    bool ret = x1.SetUserSetName(1, name1.c_str());
    if (ret == false) {
        std::cout << "SetUserSetName failed: " << RVC::GetLastErrorMessage() << std::endl;
    }
    // Set capture parameters
    RVC::X1::CaptureOptions cap_opt;
    x1.LoadCaptureOptionParameters(cap_opt);
    cap_opt.capture_mode = CaptureMode::CaptureMode_Normal;

    if (x1.Capture(cap_opt) == true) {
        std::cout << "RVC X Camera capture successed!" << std::endl;
    } else {
        std::cout << "RVC X Camera capture failed!" << std::endl;
    }

    //(2) Switch to the User Set with ID 0 and complete the capture.
    x1.SetCurrentUserSet(0);
    if (x1.Capture() == true) {
        std::cout << "RVC X Camera capture successed!" << std::endl;
    } else {
        std::cout << "RVC X Camera capture failed!" << std::endl;
    }

    //(4) Switch to the User Set with ID 1 and save the parameter settings as the JSON file "high_light.json".
    x1.SetCurrentUserSet(1);
    x1.SaveSettingToFile("./high_light.json");

    //(5) Switch to the User Set with ID 2, change the name of this User Set to "high_light2", and import the parameter
    // settings from the JSON file "high_light.json".
    x1.SetCurrentUserSet(2);
    const std::string name2 = "high_light2";
    ret = x1.SetUserSetName(2, name2.c_str());
    if (ret == false) {
        std::cout << "SetUserSetName failed: " << RVC::GetLastErrorMessage() << std::endl;
    }
    x1.LoadSettingFromFile("./high_light.json");

    // Close RVC Camera.
    x1.Close();

    // Destroy RVC Camera.
    RVC::X1::Destroy(x1);

    // Shutdown RVC System.
    RVC::SystemShutdown();
    return 0;
}
