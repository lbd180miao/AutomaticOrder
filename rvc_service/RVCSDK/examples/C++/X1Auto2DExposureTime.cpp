#include <RVC/RVC.h>

#include <iostream>

#include "IO/FileIO.h"
#include "IO/SavePointMap.h"

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
        std::cout << "Failed to open camera! Please check whether the camera is connected and make sure it is not "
                     "occupied and supports X1."
                  << std::endl;
        RVC::X1::Destroy(x1);
        RVC::SystemShutdown();
        return -1;
    }

    RVC::DeviceInfo info;
    device.GetDeviceInfo(&info);

    // Set capture parameters
    RVC::X1::CaptureOptions cap_opt;
    x1.LoadCaptureOptionParameters(cap_opt);

    const std::string save_directory = "./Data/";
    MakeDirectories(save_directory);

    // Set ROI
    RVC::ROI roi = RVC::ROI(10, 10, 200, 200);

    // Get auto 2d exposure time with high speed
    bool ret = x1.GetAuto2DExposureTime(cap_opt, roi);
    if (ret) {
        std::cout << "get auto 2d exposure time success" << std::endl;
        std::cout << "auto exposure_time_2d:" << cap_opt.exposure_time_2d << std::endl;
    } else {
        std::cout << "get auto 2d exposure time failed, custom setting will be used" << std::endl;
    }

    // Capture a image with auto 2d exposure time.
    if (x1.Capture2D(cap_opt)) {
        // Get image data.
        RVC::Image img = x1.GetImage();
        std::string img_addr = save_directory + "test.png";
        std::cout << "save image to file: " << img_addr << std::endl;
        img.SaveImage(img_addr.c_str());
    } else {
        std::cout << RVC::GetLastErrorMessage() << std::endl;
        std::cout << "RVC Camera capture failed!" << std::endl;
    }

    // Close RVC Camera.
    x1.Close();

    // Destroy RVC Camera.
    RVC::X1::Destroy(x1);

    // Shutdown RVC System.
    RVC::SystemShutdown();

    return 0;
}
