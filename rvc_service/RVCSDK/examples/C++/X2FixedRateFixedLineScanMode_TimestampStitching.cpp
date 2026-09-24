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

    // Copy point cloud data from RVC SDK memory to std::vector
    // This is necessary because RVC SDK may reuse or free this memory after callback returns
    if (line_data.pointmap_index >= MAX_LINE_NUM) {
        return;
    }
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

/**
 * @brief Stitch multiple pointmaps based on their timestamps
 */
RVC::PointMap stitchPointMapsByTimestamp(const std::vector<PointMapWithInfo>& pointmaps,
                                         const std::vector<double>& move_direction = {0, 1, 0},
                                         double move_speed = 1.0) {
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
        double time_offset_s = pm_info.pointmap_timestamp / 1e6;  // Convert microseconds to seconds
        double displacement[3] = {move_direction[0] * move_speed * time_offset_s,
                                  move_direction[1] * move_speed * time_offset_s,
                                  move_direction[2] * move_speed * time_offset_s};
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

void CalculateTimestampGapStats(std::vector<PointMapWithInfo>& pointmaps, uint64_t& min_timestamp_gap,
                                uint64_t& max_timestamp_gap) {
    //
    std::sort(pointmaps.begin(), pointmaps.end(),
              [](const PointMapWithInfo& a, const PointMapWithInfo& b) { return a.pointmap_index < b.pointmap_index; });

    std::vector<uint64_t> diffs;
    diffs.reserve(pointmaps.size() - 1);
    for (size_t i = 1; i < pointmaps.size(); ++i) {
        uint64_t diff = pointmaps[i].pointmap_timestamp - pointmaps[i - 1].pointmap_timestamp;
        diffs.push_back(diff);
    }

    auto minmax = std::minmax_element(diffs.begin(), diffs.end());
    min_timestamp_gap = *minmax.first;
    max_timestamp_gap = *minmax.second;
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

    RVC::Size resolution;
    x2.GetCameraResolution(resolution);
    size_t pointmap_size = resolution.width;
    UserData userdata(MAX_LINE_NUM, pointmap_size);
    // Set callback function to handle acquired line scan data.
    x2.SetFixedLineScanCallback(callbackFunc, &userdata);
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
    std::cout << "Total PointMaps acquired: " << userdata.pointmaps.size() << std::endl;

    // Stitch pointmaps based on timestamps
    std::vector<double> move_direction{0, 1, 0};
    double move_speed = 0.1;  // unit: m/s
    RVC::PointMap stitched_pointmap = stitchPointMapsByTimestamp(userdata.pointmaps, move_direction, move_speed);
    // Save stitched pointmap to file
    if (stitched_pointmap.IsValid()) {
        const std::string save_directory = "./Data/";
        MakeDirectories(save_directory);
        std::string pm_addr = save_directory + "test.ply";
        std::cout << "save point map to file: " << pm_addr << std::endl;
        stitched_pointmap.Save(pm_addr.c_str(), RVC::PointMapUnit::Meter, true);
        RVC::PointMap::Destroy(stitched_pointmap);
    }

    uint64_t min_timestamp_gap, max_timestamp_gap;
    CalculateTimestampGapStats(userdata.pointmaps, min_timestamp_gap, max_timestamp_gap);
    std::cout << "min timestamp gap(ms): " << min_timestamp_gap * 0.001
              << "\tmax timestamp gap(ms): " << max_timestamp_gap * 0.001 << std::endl;

    if (max_timestamp_gap - min_timestamp_gap > 500) {
        if (cap_opt.auto_set_fixed_rate) {
            std::cout << "Frame drop! Auto Set frame rate is too high. " << std::endl;
        } else {
            std::cout << "Frame drop! Frame rate: " << cap_opt.fixed_rate << " is too high. " << std::endl;
        }
    }

    // Close RVC X Camera.
    x2.Close();

    // Destroy RVC X Camera.
    RVC::X2::Destroy(x2);

    // Shutdown RVC X System.
    RVC::SystemShutdown();

    return 0;
}