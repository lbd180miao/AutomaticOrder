#include <RVC/RVC.h>

#include <algorithm>
#include <chrono>
#include <cstring>
#include <iostream>
#include <mutex>
#include <thread>

#include "IO/FileIO.h"
#include "IO/SavePointMap.h"

using namespace RVC;

/**
 * @brief Callback to handle acquired line scan data.
 *        CRITICAL: This function must be efficient to prevent frame drops. Avoid time-consuming operations.
 *
 * @param line_data Acquired line scan data and metadata
 * @param pUser Pointer to user-defined data structure
 */
std::mutex mtx;
void callbackFunc(X2::FixedLineScanCallBackInfo line_data, RVC::UserPtr pUser) {
    std::cout << "pointmap_index:" << line_data.pointmap_index
              << ", timestamp(us):" << line_data.pointmap.GetTimestamp()
              << ", pointmap size:" << line_data.pointmap.GetSize().width << "x" << line_data.pointmap.GetSize().height
              << " ,the first point of the point cloud:";
    double* pts_data = line_data.pointmap.GetPointDataPtr();
    int point_index = 0;                       // First point of the line
    double x = pts_data[point_index * 3 + 0];  // unit: m
    double y = pts_data[point_index * 3 + 1];  // unit: m
    double z = pts_data[point_index * 3 + 2];  // unit: m
    std::cout << "(" << x << "," << y << "," << z << ")" << std::endl;
}

int main(int argc, char* argv[]) {
    // Initialize RVC X system.
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
    // Create a RVC X Camera and choose use left side camera.
    RVC::X2 x2 = RVC::X2::Create(device);
    // Open RVC X Camera.
    x2.Open();
    // Test RVC X Camera is opened or not.
    if (!x2.IsOpen()) {
        std::cout << "RVC X Camera is not opened!" << std::endl;
        RVC::X2::Destroy(x2);
        RVC::SystemShutdown();
        return 1;
    }

    // Set capture options.
    RVC::X2::CaptureOptions cap_opt;
    x2.LoadCaptureOptionParameters(cap_opt);
    // Set fixed line scan mode.
    cap_opt.capture_mode = RVC::CaptureMode_FixedLineScan;
    // Enable hard trigger mode for fixed line scan.
    cap_opt.trigger_mode = RVC::TriggerMode_FixedRate;

    // Auto set fixed rate
    {
        // cap_opt.auto_set_fixed_rate = true;
    }

    // Set fixed rate by user
    {
        cap_opt.auto_set_fixed_rate = false;
        cap_opt.fixed_rate = 100;  // Set fixed rate to 100 Hz
    }

    // Set callback function to handle acquired line scan data.
    x2.SetFixedLineScanCallback(callbackFunc, nullptr);
    x2.ResetTimestamp();
    if (!x2.StartFixedLineScan(cap_opt)) {
        std::cout << "Failed to start fixed line scan!" << std::endl;
        x2.Close();
        // Destroy RVC X Camera.
        RVC::X2::Destroy(x2);
        // Shutdown RVC X System.
        RVC::SystemShutdown();
        return 1;
    }

    int sleep_seconds = 10;
    std::cout << "Start Fixed Rate Line Scan Mode for " << sleep_seconds << " seconds..." << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(sleep_seconds));

    x2.StopFixedLineScan();

    std::cout << "Stopped Fixed Rate Line Scan Mode." << std::endl;

    // Close RVC X Camera.
    x2.Close();

    // Destroy RVC X Camera.
    RVC::X2::Destroy(x2);

    // Shutdown RVC X System.
    RVC::SystemShutdown();

    return 0;
}