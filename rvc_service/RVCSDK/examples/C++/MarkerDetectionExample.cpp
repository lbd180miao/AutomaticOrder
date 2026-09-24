#include <RVC/RVC.h>
#include <RVC/experimental/MarkerDetection.h>

#include <opencv2/opencv.hpp>
#include <iostream>

#define USE_X1
#ifdef USE_X1
#define XX RVC::X1
#else
#define XX RVC::X2
#endif

#ifdef _WIN32
#include <direct.h>
#include <io.h>
#define MKDIR(path) _mkdir(path)
#else
#include <sys/stat.h>
#include <unistd.h>
#define MKDIR(path) mkdir(path, S_IRWXU | S_IRWXG | S_IROTH | S_IXOTH)
#endif

bool MakeDirectories(const std::string& directories) {
    return (0 == MKDIR(directories.c_str()));
}

std::string GetCurrentTimeStr() {
    auto now = std::chrono::system_clock::now();
    std::time_t now_time_t = std::chrono::system_clock::to_time_t(now);
    std::tm* now_tm = std::localtime(&now_time_t);
    std::ostringstream oss;
    oss << std::put_time(now_tm, "%Y-%m-%d_%H-%M-%S");
    return oss.str();
}

cv::Mat ConvertRVCImageToCVMat(const RVC::Image& img) {
    cv::Mat cv_image;
    if (img.GetType() == RVC::ImageType::Mono8) {
        cv::Mat cv_image_temp =
            cv::Mat(img.GetSize().height, img.GetSize().width, CV_8UC1, (void*)img.GetDataConstPtr());
        cv::cvtColor(cv_image_temp, cv_image, cv::COLOR_GRAY2BGR);
    } else if (img.GetType() == RVC::ImageType::RGB8 || img.GetType() == RVC::ImageType::BGR8) {
        cv_image = cv::Mat(img.GetSize().height, img.GetSize().width, CV_8UC3, (void*)img.GetDataConstPtr());
    } else {
        std::cout << "Unsupported image type!" << std::endl;
    }
    return cv_image;
}

void ShowCodedCircleMarkerResult(const RVC::Image& img, int cv_wait_time) {
    RVC::CodedCircleMarkerType type;
    // **** Notice: need to be changed according to the actual type. ****
    type.N = 15;
    type.r1_to_r0_ratio = 4.0f / 1.5f;
    type.r2_to_r0_ratio = 6.0f / 1.5f;
    int marker_nums;
    RVC::CodedCircleMarker markers[1000];
    RVC::DetectCodedCircleMarker(img, type, &marker_nums, markers);

    cv::Mat cv_image = ConvertRVCImageToCVMat(img);
    if (cv_image.empty()) {
        std::cout << "Convert RVC Image to CV Mat failed!" << std::endl;
        return;
    }

    for (int i = 0; i < marker_nums; i++) {
        cv::circle(cv_image, cv::Point(markers[i].x, markers[i].y), 0, cv::Scalar(0, 0, 255), -1);
        cv::putText(cv_image, std::to_string(markers[i].code), cv::Point(markers[i].x, markers[i].y),
                    cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 0, 255), 1);
    }
    std::cout << "markerNums: " << marker_nums << std::endl;
    cv::namedWindow("image");
    cv::moveWindow("image", 50, 25);
    int new_height = 900;
    int new_width = (int)((double)cv_image.cols / cv_image.rows * new_height);
    cv::resize(cv_image, cv_image, cv::Size(new_width, new_height));
    cv::imshow("image", cv_image);
    cv::waitKey(cv_wait_time);
}

void CodedCircleMarkerDetectOffline(const std::string& folder, const std::string& image_name) {
    RVC::Image image = RVC::Image::CreateFromFile((folder + "/" + image_name).c_str());
    ShowCodedCircleMarkerResult(image, 0);
    RVC::Image::Destroy(image);
}

void CodedCircleMarkerDetectOnline() {
    RVC::Device devices[10];
    size_t actual_size = 0;
    SystemListDevices(devices, 10, &actual_size, RVC::SystemListDeviceType::All);
    if (actual_size == 0) {
        std::cout << "Can not find any Camera!" << std::endl;
        return;
    }

    if (devices[0].IsFirmwareMatch() == false) {
        std::cout << "device firmware mismatch, Please use RVCManager to upgrade the firmware" << std::endl;
        RVC::SystemShutdown();
        return;
    }
#ifdef USE_X1
    XX camera = XX::Create(devices[0], RVC::CameraID_Left);
#else
    XX camera = XX::Create(devices[0]);
#endif
    camera.Open();
    if (!camera.IsOpen()) {
        std::cout << "Failed to open camera! Please check whether the camera is connected "
                     "and make sure it is not occupied!"
                  << std::endl;
        XX::Destroy(camera);
        RVC::SystemShutdown();
        return;
    }

    RVC::DeviceInfo info;
    devices[0].GetDeviceInfo(&info);
#ifndef USE_X1
    RVC::CameraID camera_id = RVC::CameraID_Left;
    if (info.support_extra) {
        camera_id = RVC::CameraID_Extra;
    }
#endif

    // RVC::XX::CaptureOptions cap_opt;
    // cap_opt.exposure_time_2d = 20;
    bool save = false;
    int save_index = 0;
    int max_save_count = 1000;

    std::string folder = "./DetectMarkersData/";
    MakeDirectories(folder);
    folder = folder + std::string(info.sn) + "/";
    MakeDirectories(folder);
    folder += GetCurrentTimeStr() + "/";
    MakeDirectories(folder);

    // while not press space
    while (cv::waitKey(10) != 32) {
#ifdef USE_X1
        camera.Capture2D();
        RVC::Image img = camera.GetImage();
#else
        camera.Capture2D(camera_id);
        RVC::Image img = camera.GetImage(camera_id);
#endif

        if (save) {
            std::string image_path = folder + std::to_string(save_index) + ".png";
            save_index++;
            save_index %= max_save_count;
            img.SaveImage(image_path.c_str());
        }

        ShowCodedCircleMarkerResult(img, 1);
    }

    camera.Close();
    XX::Destroy(camera);
    RVC::SystemShutdown();
    return;
}

void ConcentricCircleMarkerDetectOffline(const std::string& folder, const std::string& image_name,
                                         const std::string& pointmap_name) {
    RVC::Image image = RVC::Image::CreateFromFile((folder + "/" + image_name).c_str());
    RVC::PointMap pointmap =
        RVC::PointMap::CreateFromFile((folder + "/" + pointmap_name).c_str(), image.GetSize(), RVC::PointMapUnit::Meter);
    std::cout << "only detect pixel 2d" << std::endl;
    {
        int marker_num;
        double pixel_xy[2000];
        int error_code = RVC::DetectConcentricCircleMarker2d(image, &marker_num, pixel_xy);
        if (error_code == 0) {
            std::cout << "2D marker num: " << marker_num << std::endl;
            for (int i = 0; i < marker_num; i++) {
                std::cout << "Marker " << i << ": (" << pixel_xy[2 * i] << ", " << pixel_xy[2 * i + 1] << ")"
                          << std::endl;
            }
        } else {
            std::cout << "DetectConcentricCircleMarker2d failed, error code = " << error_code << std::endl;
        }
    }
    std::cout << std::endl;

    std::cout << "detect pixel 2d and point 3d" << std::endl;
    {
        int marker_num;
        double pixel_xy[2000];
        double point_xyz[3000];
        int error_code = RVC::DetectConcentricCircleMarker3d(image, pointmap, &marker_num, pixel_xy, point_xyz);
        if (error_code == 0) {
            std::cout << "3D marker num: " << marker_num << std::endl;
            for (int i = 0; i < marker_num; i++) {
                std::cout << "Marker " << i << ": (" << pixel_xy[2 * i] << ", " << pixel_xy[2 * i + 1] << "), ("
                          << point_xyz[3 * i] << ", " << point_xyz[3 * i + 1] << ", " << point_xyz[3 * i + 2] << ")"
                          << std::endl;
            }
        } else {
            std::cout << "DetectConcentricCircleMarker3d failed, error code = " << error_code << std::endl;
        }
    }
    RVC::Image::Destroy(image);
    RVC::PointMap::Destroy(pointmap);
}

int main(int argc, char* argv[]) {
    int example_type = 2;
    if (example_type == 0) {
        CodedCircleMarkerDetectOnline();
    } else if (example_type == 1) {
        std::string folder = "D:/";
        std::string image_name = "0.png";
        CodedCircleMarkerDetectOffline(folder, image_name);
    } else if (example_type == 2) {
        std::string folder = "D:/";
        std::string image_name = "0.png";
        std::string pointmap_name = "0.ply";
        ConcentricCircleMarkerDetectOffline(folder, image_name, pointmap_name);
    }

    return 0;
}