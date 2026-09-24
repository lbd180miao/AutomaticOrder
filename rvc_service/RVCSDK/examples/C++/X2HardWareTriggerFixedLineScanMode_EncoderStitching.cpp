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

#define MAX_LINE_NUM 40000

// User-defined data structure to hold context for the callback
struct PointMapWithInfo {
    int pointmap_index;
    int encoder_index;
    uint64_t pointmap_timestamp;
    double* pointmap_data;  // x,y,z,x,y,z,...
    size_t pointmap_size;
};
struct UserData {
    std::mutex mtx;
    double* buffer = nullptr;
    std::vector<PointMapWithInfo> pointmaps;

    UserData() = delete;
    UserData(const UserData&) = delete;
    UserData& operator=(const UserData&) = delete;
    UserData(UserData&&) = delete;
    UserData& operator=(UserData&&) = delete;

    UserData(size_t max_line_num, size_t pointmap_size) {
        if (max_line_num > 0 && pointmap_size > 0) {
            buffer = new double[max_line_num * pointmap_size * 3];
        } else {
            buffer = nullptr;
        }
        if (pointmap_size > 0) {
            pointmaps.reserve(max_line_num);
        }
    }

    ~UserData() {
        if (buffer) {
            delete[] buffer;
            buffer = nullptr;
        }
    }
};

/**
 * @brief Callback to handle acquired line scan data.
 *        CRITICAL: This function must be efficient to prevent frame drops. Avoid time-consuming operations.
 *
 * @param line_data Acquired line scan data and metadata
 * @param pUser Pointer to user-defined data structure
 */
void callbackFunc(X2::FixedLineScanCallBackInfo line_data, RVC::UserPtr pUser) {
    struct UserData* user_data = static_cast<UserData*>(pUser);

    if (line_data.pointmap_index >= MAX_LINE_NUM) {
        return;
    }
    // Copy point cloud data from RVC SDK memory to std::vector
    // This is necessary because RVC SDK may reuse or free this memory after callback returns
    PointMapWithInfo pm_info;
    pm_info.pointmap_index = line_data.pointmap_index;
    pm_info.encoder_index = line_data.encoder_index;
    pm_info.pointmap_timestamp = line_data.pointmap.GetTimestamp();
    pm_info.pointmap_size = line_data.pointmap.GetSize().width * line_data.pointmap.GetSize().height;
    pm_info.pointmap_data = user_data->buffer + pm_info.pointmap_index * pm_info.pointmap_size * 3;
    memcpy(pm_info.pointmap_data, line_data.pointmap.GetPointDataConstPtr(),
           sizeof(double) * pm_info.pointmap_size * 3);

    // Move temporary object into the shared vector
    // Using std::move avoids additional copy operations, improving performance
    user_data->pointmaps.push_back(pm_info);
}

RVC::PointMap stitchPointMapsByEncoder(const std::vector<PointMapWithInfo>& pointmaps,
                                       const std::vector<double>& move_direction = {0, 1, 0},
                                       double distance_per_trigger = 1.0) {
    RVC::PointMap stitched_pointmap;
    if (pointmaps.empty()) {
        std::cout << "No pointmaps to stitch." << std::endl;
        return stitched_pointmap;
    }
    stitched_pointmap =
        RVC::PointMap::Create(RVC::PointMapType::PointsOnly, RVC::Size(pointmaps[0].pointmap_size, pointmaps.size()));
    if (!stitched_pointmap.IsValid()) {
        std::cout << "Failed to create PointMap." << std::endl;
        return stitched_pointmap;
    }
    for (size_t i = 0; i < pointmaps.size(); ++i) {
        const auto& pm_info = pointmaps[i];
        int pointmap_index = pm_info.pointmap_index;
        double displacement[3] = {move_direction[0] * distance_per_trigger * pm_info.encoder_index,
                                  move_direction[1] * distance_per_trigger * pm_info.encoder_index,
                                  move_direction[2] * distance_per_trigger * pm_info.encoder_index};
        for (size_t j = 0; j < pm_info.pointmap_size; ++j) {
            double x = pm_info.pointmap_data[j * 3 + 0];
            double y = pm_info.pointmap_data[j * 3 + 1];
            double z = pm_info.pointmap_data[j * 3 + 2];
            stitched_pointmap.GetPointDataPtr()[(pointmap_index * stitched_pointmap.GetSize().width + j) * 3 + 0] =
                x + displacement[0];
            stitched_pointmap.GetPointDataPtr()[(pointmap_index * stitched_pointmap.GetSize().width + j) * 3 + 1] =
                y + displacement[1];
            stitched_pointmap.GetPointDataPtr()[(pointmap_index * stitched_pointmap.GetSize().width + j) * 3 + 2] =
                z + displacement[2];
        }
    }
    return stitched_pointmap;
}

int CalculateEncoderIndexMaxGap(std::vector<PointMapWithInfo>& pointmaps) {
    if (pointmaps.size() < 2) {
        return 0;
    }
    std::sort(pointmaps.begin(), pointmaps.end(),
              [](const PointMapWithInfo& a, const PointMapWithInfo& b) { return a.encoder_index < b.encoder_index; });
    int max_diff = std::numeric_limits<int>::min();

    for (size_t i = 1; i < pointmaps.size(); ++i) {
        int diff = pointmaps[i].encoder_index - pointmaps[i - 1].encoder_index;
        if (diff > max_diff)
            max_diff = diff;
    }
    return max_diff;
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

    RVC::DeviceInfo info;
    device.GetDeviceInfo(&info);
    if (info.support_hardware_trigger == false) {
        std::cout << "The camera does not support hardware trigger mode!" << std::endl;
        x2.Close();
        RVC::X2::Destroy(x2);
        RVC::SystemShutdown();
        return -1;
    }

    // Set capture options.
    RVC::X2::CaptureOptions cap_opt;
    x2.LoadCaptureOptionParameters(cap_opt);
    // Set fixed line scan mode.
    cap_opt.capture_mode = RVC::CaptureMode_FixedLineScan;
    // Enable hard trigger mode for fixed line scan.
    cap_opt.trigger_mode = RVC::TriggerMode_HardWare;
    /**
     * Set number of encoder pulses required to trigger one profile acquisition
     *
     * The setting of ‘encoder_trigger_interval’ requires comprehensive consideration of the following factors:
     * 1. Actual movement distance per encoder pulse D (unit: mm);
     * 2. Camera's maximum trigger frame rate FPS (unit: frames/second);
     * 3. Guide rail movement speed V (unit: mm/s);
     * 4. Required line spacing (unit: mm).
     *
     * Example:
     * Given:
     * - Distance per encoder pulse D = 0.1 mm
     * - Maximum camera trigger frame rate = 300 FPS
     * - Guide rail movement speed V = 400 mm/s
     *
     * Calculation:
     * - Encoder pulse frequency F = V / D = 4000 Hz
     * - Minimum encoder trigger interval = F / FPS = 4000 / 300 ≈ 14 pulses
     *   (meaning: trigger camera acquisition every 14 encoder pulses)
     * - Resulting line spacing = D × trigger interval = 0.1 mm × 14 = 1.4 mm
     */
    cap_opt.encoder_trigger_interval = 14;

    RVC::Size resolution;
    x2.GetCameraResolution(resolution);
    size_t pointmap_size = resolution.width;

    UserData userdata(MAX_LINE_NUM, pointmap_size);
    // Set callback function to handle acquired line scan data.
    x2.SetFixedLineScanCallback(callbackFunc, &userdata);

    // Start monitoring for trigger signals.The fixed line scan mode should be initiated before the hardware signals
    // begin and terminated after they cease.

    if (!x2.StartFixedLineScan(cap_opt)) {
        std::cout << "Failed to start fixed line scan!" << std::endl;
        x2.Close();
        // Destroy RVC X Camera.
        RVC::X2::Destroy(x2);
        // Shutdown RVC X System.
        RVC::SystemShutdown();
        return 1;
    }

    std::cout << "Start monitoring for trigger signals..." << std::endl;

    // Simulate monitoring for trigger signals for 10 seconds.
    std::this_thread::sleep_for(std::chrono::seconds(10));

    // Stop monitoring
    x2.StopFixedLineScan();
    std::cout << "Capture finished! Number of captured lines:" << userdata.pointmaps.size() << std::endl;

    // Stitch pointmaps based on timestamps
    std::vector<double> move_direction{0, 1, 0};
    double distance_per_pulse = 0.1 * 0.001;                                              // unit: m/pulse
    double distance_per_trigger = distance_per_pulse * cap_opt.encoder_trigger_interval;  // unit: m/trigger
    RVC::PointMap stitched_pointmap =
        stitchPointMapsByEncoder(userdata.pointmaps, move_direction, distance_per_trigger);
    // Save stitched pointmap to file
    if (stitched_pointmap.IsValid()) {
        const std::string save_directory = "./Data/";
        MakeDirectories(save_directory);
        std::string pm_addr = save_directory + "test.ply";
        std::cout << "save point map to file: " << pm_addr << std::endl;
        stitched_pointmap.Save(pm_addr.c_str(), RVC::PointMapUnit::Meter, true);
        RVC::PointMap::Destroy(stitched_pointmap);
    }

    int max_encoder_gap = CalculateEncoderIndexMaxGap(userdata.pointmaps);
    std::cout << "Max encoder index gap: " << max_encoder_gap << std::endl;
    if (max_encoder_gap > 1) {
        std::cout << "Trigger frequency is too high. Please reduce the trigger frequency, or increase the "
                     "'encoder_trigger_interval'."
                  << std::endl;
    }

    // Close RVC X Camera.
    x2.Close();

    // Destroy RVC X Camera.
    RVC::X2::Destroy(x2);

    // Shutdown RVC X System.
    RVC::SystemShutdown();

    return 0;
}