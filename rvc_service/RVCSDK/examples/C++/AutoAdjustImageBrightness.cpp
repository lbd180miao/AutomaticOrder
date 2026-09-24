// Copyright (c) RVBUST, Inc - All rights reserved.

#include <RVC/RVC.h>

#include <algorithm>
#include <iostream>
#include <numeric>
#include <vector>

int GetMeanValue(const RVC::Image& image) {
    unsigned char* data = image.GetDataPtr();
    int channels = image.GetType() == RVC::ImageType::Mono8 ? 1 : 3;
    int total_pixels = image.GetSize().width * image.GetSize().height;
    long long sum = 0;
    for (int i = 0; i < total_pixels * channels; ++i) {
        sum += data[i];
    }
    return (int)(sum / (total_pixels * channels));
}

template <typename T>
static T Interplate(T x0, int y0, T x1, int y1, int y) {
    return (T)((y - y0) * (x1 - x0) / (double)(y1 - y0) + (double)x0);
}

int GetReferenceImageBrightness(const std::string& camera_sn, const RVC::ROI& roi, int& reference_roi_brightness) {
    RVC::SystemInit();
    RVC::Device device = RVC::SystemFindDevice(camera_sn.c_str());
    RVC::X1 x1 = RVC::X1::Create(device);
    x1.Open();
    if (!x1.IsOpen()) {
        std::cout << "RVC X Camera is not opened!" << std::endl;
        RVC::X1::Destroy(x1);
        RVC::SystemShutdown();
        return -1;
    }

    RVC::X1::CaptureOptions capture_options;
    x1.LoadCaptureOptionParameters(capture_options);
    RVC::ROI origin_roi = capture_options.roi;
    capture_options.roi = roi;
    if (x1.CheckRoi(capture_options.roi) == false) {
        std::cout << "roi is not valid,need to adjust. " << std::endl;
        capture_options.roi = x1.AutoAdjustRoi(capture_options.roi);
    }

    bool ret1 = x1.Capture2D(capture_options);
    if (ret1 == false) {
        std::cout << "Capture2D failed!" << std::endl;
        x1.Close();
        RVC::X1::Destroy(x1);
        RVC::SystemShutdown();
        return -1;
    }

    reference_roi_brightness = GetMeanValue(x1.GetImage());
    std::cout << "reference reference_roi_brightness: " << reference_roi_brightness << std::endl;

    capture_options.roi = origin_roi;
    x1.SaveCaptureOptionParameters(capture_options);

    x1.Close();
    RVC::X1::Destroy(x1);
    RVC::SystemShutdown();
    return 0;
}

int AutoAdjustImageBrightness(const std::string& camera_sn, const RVC::ROI& roi, int& target_roi_brightness,
                              RVC::X1::CaptureOptions& auto_adjust_opts) {
    RVC::SystemInit();
    RVC::Device device = RVC::SystemFindDevice(camera_sn.c_str());
    RVC::X1 x1 = RVC::X1::Create(device);
    x1.Open();
    if (!x1.IsOpen()) {
        std::cout << "RVC X Camera is not opened!" << std::endl;
        RVC::X1::Destroy(x1);
        RVC::SystemShutdown();
        return -1;
    }
    int exposure_time_min, exposure_time_max;
    x1.GetExposureTimeRange(&exposure_time_min, &exposure_time_max);
    RVC::X1::CaptureOptions capture_options;
    x1.LoadCaptureOptionParameters(capture_options);
    std::cout << "Origin capture options:" << std::endl;
    std::cout << "exposure_time_2d: " << capture_options.exposure_time_2d << std::endl;
    std::cout << "gain_2d: " << capture_options.gain_2d << std::endl;
    std::cout << "projector_brightness: " << capture_options.projector_brightness << std::endl;
    std::cout << "enable_2d_in_capture: " << (capture_options.enable_2d_in_capture ? "true" : "false") << std::endl;
    std::cout << "ROI: (" << capture_options.roi.x << ", " << capture_options.roi.y << ", " << capture_options.roi.width
              << ", " << capture_options.roi.height << ")" << std::endl;
    std::cout << "----------------------------------------" << std::endl;
    RVC::ROI origin_roi = capture_options.roi;
    capture_options.gain_2d = 0;
    capture_options.projector_brightness = 240;
    capture_options.enable_2d_in_capture = true;  // this can be set to false
    capture_options.roi = roi;
    if (x1.CheckRoi(capture_options.roi) == false) {
        std::cout << "roi is not valid,need to adjust. " << std::endl;
        capture_options.roi = x1.AutoAdjustRoi(capture_options.roi);
    }

    capture_options.exposure_time_2d = exposure_time_min;
    bool ret1 = x1.Capture2D(capture_options);
    int mean_value_min = GetMeanValue(x1.GetImage());
    capture_options.exposure_time_2d = exposure_time_max;
    bool ret2 = x1.Capture2D(capture_options);
    if (ret1 == false || ret2 == false) {
        std::cout << "Capture2D failed!" << std::endl;
        x1.Close();
        RVC::X1::Destroy(x1);
        RVC::SystemShutdown();
        return -1;
    }
    int mean_value_max = GetMeanValue(x1.GetImage());
    std::cout << "exposure_time_2d min: " << exposure_time_min << ", mean value min: " << mean_value_min << std::endl;
    std::cout << "exposure_time_2d max: " << exposure_time_max << ", mean value max: " << mean_value_max << std::endl;
    if (mean_value_min == mean_value_max) {
        std::cout << "Adjust failed!" << std::endl;
        x1.Close();
        RVC::X1::Destroy(x1);
        RVC::SystemShutdown();
        return -1;
    }
    // 1. if target is between min and max, adjust exposure_time_2d
    if (target_roi_brightness > mean_value_min && target_roi_brightness < mean_value_max) {
        std::cout << "Adjust exposure_time_2d." << std::endl;
        while (exposure_time_min < exposure_time_max) {
            int new_exposure_time =
                Interplate(exposure_time_min, mean_value_min, exposure_time_max, mean_value_max, target_roi_brightness);
            capture_options.exposure_time_2d = new_exposure_time;
            bool ret = x1.Capture2D(capture_options);
            if (ret == false) {
                std::cout << "Capture2D failed!" << std::endl;
                x1.Close();
                RVC::X1::Destroy(x1);
                RVC::SystemShutdown();
                return -1;
            }
            int new_mean_value = GetMeanValue(x1.GetImage());
            // if (new_mean_value <= mean_value_min || new_mean_value >= mean_value_max) {
            //     break;
            // }
            if (new_mean_value < target_roi_brightness) {
                exposure_time_min = new_exposure_time + 1;
                mean_value_min = new_mean_value;
            } else if (new_mean_value > target_roi_brightness) {
                exposure_time_max = new_exposure_time - 1;
                mean_value_max = new_mean_value;
            } else {
                break;
            }

            std::cout << "exposure_time_2d: " << new_exposure_time << ", mean value: " << new_mean_value
                      << ",exposure_time_2d min: " << exposure_time_min
                      << " ,exposure_time_2d max: " << exposure_time_max << ",mean_value_min: " << mean_value_min
                      << ",mean_value_max: " << mean_value_max << std::endl;
        }
    }
    // 2. if min exposure_time_2d is still brighter than target, adjust projector_brightness
    else if (target_roi_brightness <= mean_value_min) {
        std::cout << "Adjust projector_brightness, or you can set enable_2d_in_capture to false and try again!"
                  << std::endl;
        capture_options.exposure_time_2d = exposure_time_min;
        int projector_brightness_min = 1;
        int projector_brightness_max = 240;
        capture_options.projector_brightness = projector_brightness_min;
        bool ret = x1.Capture2D(capture_options);
        if (ret == false) {
            std::cout << "Capture2D failed!" << std::endl;
            x1.Close();
            RVC::X1::Destroy(x1);
            RVC::SystemShutdown();
            return -1;
        }
        mean_value_min = GetMeanValue(x1.GetImage());
        if (target_roi_brightness < mean_value_min) {
            std::cout << "Adjust failed. Unable to reach target image brightness!" << std::endl;
            x1.Close();
            RVC::X1::Destroy(x1);
            RVC::SystemShutdown();
            return -1;
        }
        while (projector_brightness_min < projector_brightness_max) {
            int new_projector_brightness = Interplate(projector_brightness_min, mean_value_min,
                                                      projector_brightness_max, mean_value_max, target_roi_brightness);
            capture_options.projector_brightness = new_projector_brightness;
            ret = x1.Capture2D(capture_options);
            if (ret == false) {
                std::cout << "Capture2D failed!" << std::endl;
                x1.Close();
                RVC::X1::Destroy(x1);
                RVC::SystemShutdown();
                return -1;
            }
            int new_mean_value = GetMeanValue(x1.GetImage());
            std::cout << "projector_brightness: " << new_projector_brightness << ", mean value: " << new_mean_value
                      << std::endl;
            if (new_mean_value <= mean_value_min || new_mean_value >= mean_value_max) {
                break;
            }
            if (new_mean_value < target_roi_brightness) {
                projector_brightness_min = new_projector_brightness + 1;
                mean_value_min = new_mean_value;
            } else if (new_mean_value > target_roi_brightness) {
                projector_brightness_max = new_projector_brightness - 1;
                mean_value_max = new_mean_value;
            } else {
                break;
            }
        }
    }
    // 3. if max exposure_time_2d is still darker than target, adjust gain_2d
    else if (target_roi_brightness >= mean_value_max) {
        std::cout << "Adjust gain_2d." << std::endl;
        capture_options.exposure_time_2d = exposure_time_max;
        float gain_min = 0;
        float gain_max = 0;
        x1.GetGainRange(&gain_min, &gain_max);
        capture_options.gain_2d = gain_max;
        bool ret = x1.Capture2D(capture_options);
        if (ret == false) {
            std::cout << "Capture2D failed!" << std::endl;
            x1.Close();
            RVC::X1::Destroy(x1);
            RVC::SystemShutdown();
            return -1;
        }
        mean_value_max = GetMeanValue(x1.GetImage());
        if (target_roi_brightness > mean_value_max) {
            std::cout << "Adjust failed. Unable to reach target image brightness!" << std::endl;
            x1.Close();
            RVC::X1::Destroy(x1);
            RVC::SystemShutdown();
            return -1;
        }
        while (gain_min < gain_max) {
            float new_gain_2d = Interplate(gain_min, mean_value_min, gain_max, mean_value_max, target_roi_brightness);
            capture_options.gain_2d = new_gain_2d;
            ret = x1.Capture2D(capture_options);
            if (ret == false) {
                std::cout << "Capture2D failed!" << std::endl;
                x1.Close();
                RVC::X1::Destroy(x1);
                RVC::SystemShutdown();
                return -1;
            }
            int new_mean_value = GetMeanValue(x1.GetImage());
            std::cout << "gain_2d: " << new_gain_2d << ", mean value: " << new_mean_value << std::endl;
            if (new_mean_value <= mean_value_min || new_mean_value >= mean_value_max) {
                break;
            }
            if (new_mean_value < target_roi_brightness) {
                gain_min = new_gain_2d + 0.1f;
                mean_value_min = new_mean_value;
            } else if (new_mean_value > target_roi_brightness) {
                gain_max = new_gain_2d - 0.1f;
                mean_value_max = new_mean_value;
            } else {
                break;
            }
        }
    }

    x1.Capture2D(capture_options);
    int new_mean_value = GetMeanValue(x1.GetImage());
    std::cout << std::endl;
    std::cout << "Final result:" << std::endl;
    std::cout << "Exposure time: " << capture_options.exposure_time_2d << ", gain2d: " << capture_options.gain_2d
              << ", projector_brightness: " << capture_options.projector_brightness
              << ", enable_2d_in_capture: " << (capture_options.enable_2d_in_capture ? "true" : "false")
              << ", mean value: " << new_mean_value << std::endl;
    std::cout
        << "If the projector_brightness is changed, please note that the projector_brightness has an impact on "
           "point cloud in non-HDR mode. In this case, you can keep the previous projector_brightness to capture the 3D"
           " point cloud and use different projector_brightness and call Capture2D function to capture a 2D image "
           "separately."
        << std::endl;
    capture_options.roi = origin_roi;
    x1.SaveCaptureOptionParameters(capture_options);

    auto_adjust_opts = capture_options;

    x1.Close();
    RVC::X1::Destroy(x1);
    RVC::SystemShutdown();

    return 0;
}

int main(int argc, char* argv[]) {
    std::string reference_camera_sn = "I1GC312W619";
    std::string target_camera_sn = "I1GC312W619";
    RVC::ROI roi(512, 512, 128, 128);
    int reference_brightness_value = 0;
    RVC::X1::CaptureOptions auto_adjust_opts;

    // Use Reference Camera and ROI to get reference brightness value
    GetReferenceImageBrightness(reference_camera_sn, roi, reference_brightness_value);

    // Use Target Camera, ROI and reference brightness value to get auto adjust capture options
    AutoAdjustImageBrightness(target_camera_sn, roi, reference_brightness_value, auto_adjust_opts);
    return 0;
}
