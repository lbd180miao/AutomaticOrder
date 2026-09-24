#include <RVC/RVC.h>

#include <iostream>

#include "IO/SavePointMap.h"

// Open3D
#include <open3d/Open3D.h>

static open3d::geometry::PointCloud PointMap2CloudPoint(RVC::PointMap &pm) {
    open3d::geometry::PointCloud pointcloud;
    int point_num = pm.GetSize().height * pm.GetSize().width;
    const double *pm_data = pm.GetPointDataConstPtr();
    for (int i = 0; i < point_num; i++) {
        Eigen::Vector3d cur_point(pm_data[3 * i + 0], pm_data[3 * i + 1], pm_data[3 * i + 2]);
        pointcloud.points_.push_back(cur_point);
    }
    return pointcloud;
}

int main(int argc, char **argv) {
    // Initialize RVC system
    RVC::SystemInit();

    // Scan all RVC Camera devices
    RVC::Device devices[10];
    size_t actual_size = 0;
    SystemListDevices(devices, 10, &actual_size, RVC::SystemListDeviceType::All);

    // Find whether any RVC Camera is connected or not
    if (actual_size == 0) {
        std::cout << "Can not find any RVC Camera!" << std::endl;
        RVC::SystemShutdown();
        return -1;
    }
    if(devices[0].IsFirmwareMatch() == false){
        std::cout << "device firmware mismatch, Please use RVCManager to upgrade the firmware" << std::endl;
        RVC::SystemShutdown();
        return -1;
    }
    // Create a RVC Camera and choose use left side camera
    RVC::X1 x1 = RVC::X1::Create(devices[0], RVC::CameraID_Left);

    // Open RVC Camera
    x1.Open();

    // Test RVC Camera is opened or not
    if (!x1.IsOpen()) {
        std::cout << "Failed to open camera! Please check whether the camera is connected and make sure it is not occupied and supports X1." << std::endl;
        RVC::X1::Destroy(x1);
        RVC::SystemShutdown();
        return -1;
    }

    // Capture a point map and a image (default can be x1.Capture();)
    if (x1.Capture() == true) {
        std::cout << "RVC Camera capture successed!" << std::endl;
        // Get point map data (m)
        RVC::PointMap pm = x1.GetPointMap();
        open3d::geometry::PointCloud cloud = PointMap2CloudPoint(pm);

        const double *pm_data = pm.GetPointDataConstPtr();

        const size_t n_pts = pm.GetSize().width * pm.GetSize().height;
        const size_t step = n_pts / 10000;  // print 10000 point

        for (size_t i = 0; i < n_pts; i += step) {
            printf("index: %d RVC::PointMap: (%.6f, %.6f, %.6f), open3d::PointCloud: (%.6f, %.6f, %.6f)\n", i,
                   pm_data[i * 3], pm_data[i * 3 + 1], pm_data[i * 3 + 2], cloud.points_[i](0), cloud.points_[i](1),
                   cloud.points_[i](2));
        }

    } else {
        std::cout << RVC::GetLastErrorMessage() << std::endl;
        std::cout << "RVC Camera capture failed!" << std::endl;
    }

    // Close RVC Camera
    x1.Close();

    // Destroy RVC Camera
    RVC::X1::Destroy(x1);

    // Shut Down RVC System
    RVC::SystemShutdown();
    return 0;
}