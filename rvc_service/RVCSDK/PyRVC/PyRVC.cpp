// Copyright (c) RVBUST, Inc - All rights reserved.

#include <RVC/RVC.h>
#include <RVC/experimental/ExternalColorCamera.h>
#include <RVC/experimental/MarkerDetection.h>
#include <RVC/experimental/PointCloudCompensator.h>
#include <RVC/experimental/PointCloudStitching.h>
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <chrono>
#include <string>
#include <vector>

#define DEVICE_MAX_NUM 16

using namespace RVC;
using namespace pybind11;

struct NormalData {
    NormalData() {}

    NormalData(double *data, RVC::Size size, bool valid) : data(data), size(size), isValid(valid) {}

    static NormalData fromPointMap(PointMap pointMap) {
        return NormalData(pointMap.GetNormalDataPtr(), pointMap.GetSize(), pointMap.GetNormalDataPtr() != nullptr);
    }

    bool IsValid() { return isValid; }

    Size GetSize() { return size; }

    bool isValid = false;
    double *data = nullptr;
    RVC::Size size = RVC::Size(0, 0);
};

PYBIND11_MODULE(PyRVC, m) {
    m.def("GetVersion", &GetVersion, call_guard<gil_scoped_release>());

    m.def("GetLastError", &GetLastError, call_guard<gil_scoped_release>());

    m.def(
        "GetLastErrorMessage", [] { return std::string(GetLastErrorMessage()); }, call_guard<gil_scoped_release>());

    class_<Size>(m, "Size")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def(init<int, int>(), call_guard<gil_scoped_release>())
        .def_readwrite("width", &Size::width)
        .def_readwrite("height", &Size::height)
        .def_readwrite("cols", &Size::cols)
        .def_readwrite("rows", &Size::rows);

    class_<ROI>(m, "ROI")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def(init<int, int, int, int>(), call_guard<gil_scoped_release>())
        .def_readwrite("x", &ROI::x)
        .def_readwrite("y", &ROI::y)
        .def_readwrite("width", &ROI::width)
        .def_readwrite("height", &ROI::height);

    class_<ROIRange>(m, "ROIRange")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_readwrite("x_step", &ROIRange::x_step)
        .def_readwrite("y_step", &ROIRange::y_step)
        .def_readwrite("width_step", &ROIRange::width_step)
        .def_readwrite("height_step", &ROIRange::height_step)
        .def_readwrite("width_min", &ROIRange::width_min)
        .def_readwrite("height_min", &ROIRange::height_min)
        .def_readwrite("width_max", &ROIRange::width_max)
        .def_readwrite("height_max", &ROIRange::height_max);

    enum_<RVC::CameraID>(m, "CameraID")
        .value("CameraID_NONE", RVC::CameraID::CameraID_NONE)
        .value("CameraID_0", RVC::CameraID::CameraID_0)
        .value("CameraID_1", RVC::CameraID::CameraID_1)
        .value("CameraID_2", RVC::CameraID::CameraID_2)
        .value("CameraID_3", RVC::CameraID::CameraID_3)
        .value("CameraID_Left", RVC::CameraID::CameraID_Left)
        .value("CameraID_Right", RVC::CameraID::CameraID_Right)
        .value("CameraID_Both", RVC::CameraID::CameraID_Both)
        .value("CameraID_Extra", RVC::CameraID::CameraID_Extra)
        .export_values();

    enum_<RVC::PortType>(m, "PortType")
        .value("PortType_NONE", RVC::PortType::PortType_NONE)
        .value("PortType_USB", RVC::PortType::PortType_USB)
        .value("PortType_GIGE", RVC::PortType::PortType_GIGE)
        .export_values();

    enum_<RVC::CameraTempSelector>(m, "CameraTempSelector")
        .value("CameraTempSelector_Camera", RVC::CameraTempSelector::CameraTempSelector_Camera)
        .value("CameraTempSelector_CoreBoard", RVC::CameraTempSelector::CameraTempSelector_CoreBoard)
        .value("CameraTempSelector_FpgaCore", RVC::CameraTempSelector::CameraTempSelector_FpgaCore)
        .value("CameraTempSelector_Framegrabberboard", RVC::CameraTempSelector::CameraTempSelector_Framegrabberboard)
        .value("CameraTempSelector_Sensor", RVC::CameraTempSelector::CameraTempSelector_Sensor)
        .value("CameraTempSelector_SensorBoard", RVC::CameraTempSelector::CameraTempSelector_SensorBoard)
        .export_values();

    enum_<RVC::ProjectorColor>(m, "ProjectorColor")
        .value("ProjectorColor_None", RVC::ProjectorColor::ProjectorColor_None)
        .value("ProjectorColor_Red", RVC::ProjectorColor::ProjectorColor_Red)
        .value("ProjectorColor_Green", RVC::ProjectorColor::ProjectorColor_Green)
        .value("ProjectorColor_Blue", RVC::ProjectorColor::ProjectorColor_Blue)
        .value("ProjectorColor_White", RVC::ProjectorColor::ProjectorColor_White)
        .export_values();

    enum_<RVC::BalanceSelector>(m, "BalanceSelector")
        .value("BalanceSelector_None", RVC::BalanceSelector::BalanceSelector_None)
        .value("BalanceSelector_Red", RVC::BalanceSelector::BalanceSelector_Red)
        .value("BalanceSelector_Green", RVC::BalanceSelector::BalanceSelector_Green)
        .value("BalanceSelector_Blue", RVC::BalanceSelector::BalanceSelector_Blue)
        .export_values();

    enum_<RVC::NetworkType>(m, "NetworkType")
        .value("NetworkType_DHCP", RVC::NetworkType::NetworkType_DHCP)
        .value("NetworkType_STATIC", RVC::NetworkType::NetworkType_STATIC)
        .export_values();

    enum_<RVC::NetworkDevice>(m, "NetworkDevice")
        .value("NetworkDevice_LightMachine", RVC::NetworkDevice::NetworkDevice_LightMachine)
        .value("NetworkDevice_LeftCamera", RVC::NetworkDevice::NetworkDevice_LeftCamera)
        .value("NetworkDevice_RightCamera", RVC::NetworkDevice::NetworkDevice_RightCamera)
        .value("NetworkDevice_ExtraCamera", RVC::NetworkDevice::NetworkDevice_ExtraCamera)
        .export_values();

    enum_<RVC::X1::CustomTransformOptions::CoordinateSelect>(m, "X1CustomTransformCoordinate")
        .value("CoordinateSelect_Disabled", RVC::X1::CustomTransformOptions::CoordinateSelect_Disabled)
        .value("CoordinateSelect_Camera", RVC::X1::CustomTransformOptions::CoordinateSelect_Camera)
        .value("CoordinateSelect_CaliBoard", RVC::X1::CustomTransformOptions::CoordinateSelect_CaliBoard)
        .export_values();

    enum_<RVC::X2::CustomTransformOptions::CoordinateSelect>(m, "X2CustomTransformCoordinate")
        .value("CoordinateSelect_Disabled", RVC::X2::CustomTransformOptions::CoordinateSelect_Disabled)
        .value("CoordinateSelect_CameraLeft", RVC::X2::CustomTransformOptions::CoordinateSelect_CameraLeft)
        .value("CoordinateSelect_CameraRight", RVC::X2::CustomTransformOptions::CoordinateSelect_CameraRight)
        .value("CoordinateSelect_CaliBoard", RVC::X2::CustomTransformOptions::CoordinateSelect_CaliBoard)
        .value("CoordinateSelect_CameraExtra", RVC::X2::CustomTransformOptions::CoordinateSelect_CameraExtra)
        .export_values();

    class_<RVC::DeviceInfo>(m, "DeviceInfo")
        .def_readonly("name", &RVC::DeviceInfo::name)
        .def_readonly("sn", &RVC::DeviceInfo::sn)
        .def_readonly("factroydate", &RVC::DeviceInfo::factroydate)
        .def_readonly("port", &RVC::DeviceInfo::port)
        .def_readonly("type", &RVC::DeviceInfo::type)
        .def_readonly("cameraid", &RVC::DeviceInfo::cameraid)
        .def_readonly("boardmodel", &RVC::DeviceInfo::boardmodel)
        .def_readonly("support_x2", &RVC::DeviceInfo::support_x2)
        .def_readonly("support_color", &RVC::DeviceInfo::support_color)
        .def_readonly("workingdist_near_mm", &RVC::DeviceInfo::workingdist_near_mm)
        .def_readonly("workingdist_far_mm", &RVC::DeviceInfo::workingdist_far_mm)
        .def_readonly("support_x1", &RVC::DeviceInfo::support_x1)
        .def_readonly("support_capture_mode", &RVC::DeviceInfo::support_capture_mode)
        .def_readonly("support_protective_cover", &RVC::DeviceInfo::support_protective_cover)
        .def_readonly("support_extra", &RVC::DeviceInfo::support_extra);

    class_<Device>(m, "Device")
        .def_static("Destroy", &Device::Destroy, call_guard<gil_scoped_release>())
        .def("IsValid", &Device::IsValid, call_guard<gil_scoped_release>())
        .def("Print", &Device::Print, call_guard<gil_scoped_release>())
        .def(
            "GetDeviceInfo",
            [](Device &self) {
                DeviceInfo info;
                bool ret = self.GetDeviceInfo(&info);
                return std::make_pair(ret, info);
            },
            call_guard<gil_scoped_release>())
        .def("IsFirmwareMatch", &Device::IsFirmwareMatch, call_guard<gil_scoped_release>())
        .def("SetNetworkConfig",
             [](Device &self, const RVC::NetworkDevice d, const RVC::NetworkType type, const char *ip,
                const char *netMask, const char *gateway) {
                 return self.SetNetworkConfig(d, type, ip, netMask, gateway) == 0 ? true : false;
             },
             call_guard<gil_scoped_release>())
        .def("GetNetworkConfig",
             [](Device &self, const RVC::NetworkDevice d) {
                 RVC::NetworkType type;
                 char ip[16];
                 char netmask[16];
                 char gateway[16];
                 memset(ip, 0, sizeof(char) * 16);
                 memset(netmask, 0, sizeof(char) * 16);
                 memset(gateway, 0, sizeof(char) * 16);
                 int status = 0;
                 {
                     gil_scoped_release release;
                     self.GetNetworkConfig(d, &type, &ip[0], &netmask[0], &gateway[0], &status);
                 }
                 return std::make_tuple(type, bytes(ip), bytes(netmask), bytes(gateway), status);
             })
        .def("AutoConfigureNetwork", &Device::AutoConfigureNetwork, call_guard<gil_scoped_release>());

    enum_<SystemListDeviceType::Enum>(m, "SystemListDeviceTypeEnum")
        .value("USB", SystemListDeviceType::USB)
        .value("GigE", SystemListDeviceType::GigE)
        .value("All", SystemListDeviceType::All)
        .export_values();

    enum_<PointMapUnit::Enum>(m, "PointMapUnitEnum")
        .value("Meter", PointMapUnit::Meter)
        .value("Millimeter", PointMapUnit::Millimeter)
        .export_values();

    m.def(
        "SystemListDeviceTypeToString",
        [](const SystemListDeviceType::Enum &e) { return SystemListDeviceType::ToString(e); },
        call_guard<gil_scoped_release>());

    m.def(
        "SystemListDevices",
        [](SystemListDeviceType::Enum opt = SystemListDeviceType::USB) {
            std::vector<Device> devices(DEVICE_MAX_NUM);
            size_t actualsize = 0;
            int ret = SystemListDevices(&devices[0], DEVICE_MAX_NUM, &actualsize, opt);
            devices.resize(actualsize);
            return std::make_pair(ret, devices);
        },
        call_guard<gil_scoped_release>());

    enum_<ImageType::Enum>(m, "ImageTypeEnum")
        .value("None", ImageType::None)
        .value("Mono8", ImageType::Mono8)
        .value("RGB8", ImageType::RGB8)
        .value("BGR8", ImageType::BGR8)
        .export_values();

    enum_<ProtectiveCoverStatus>(m, "ProtectiveCoverStatus")
        .value("ProtectiveCoverStatus_Unknown", ProtectiveCoverStatus_Unknown)
        .value("ProtectiveCoverStatus_Closed", ProtectiveCoverStatus_Closed)
        .value("ProtectiveCoverStatus_Closing", ProtectiveCoverStatus_Closing)
        .value("ProtectiveCoverStatus_Open", ProtectiveCoverStatus_Open)
        .value("ProtectiveCoverStatus_Opening", ProtectiveCoverStatus_Opening);

    m.def(
        "ImageTypeToString", [](const ImageType::Enum &e) { return ImageType::ToString(e); },
        call_guard<gil_scoped_release>());
    m.def(
        "ImageTypeGetPixelSize", [](const ImageType::Enum &e) { return ImageType::GetPixelSize(e); },
        call_guard<gil_scoped_release>());

    m.def(
        "ImageCreate", [](const ImageType::Enum it, const Size &sz) { return Image::Create(it, sz, nullptr, true); },
        call_guard<gil_scoped_release>());

    m.def(
        "ImageDestroy", [](Image &img, bool no_reuse = true) { Image::Destroy(img, no_reuse); }, "Destroy the image",
        arg("img"), arg("no_reuse") = true, call_guard<gil_scoped_release>());

    class_<Image>(m, "Image", buffer_protocol())
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_static("CreateFromFile", &Image::CreateFromFile, call_guard<gil_scoped_release>())
        .def_static(
            "Destroy", [](Image &img) { Image::Destroy(img); }, call_guard<gil_scoped_release>())
        .def("IsValid", &Image::IsValid, call_guard<gil_scoped_release>())
        .def("GetSize", &Image::GetSize, call_guard<gil_scoped_release>())
        .def("SaveImage", &Image::SaveImage, call_guard<gil_scoped_release>())
        .def("GetType", &Image::GetType, call_guard<gil_scoped_release>())
        .def("Clone", &Image::Clone, call_guard<gil_scoped_release>())
        .def("GetTimestamp", &Image::GetTimestamp, call_guard<gil_scoped_release>())
        .def("SetTimestamp", &Image::SetTimestamp, call_guard<gil_scoped_release>())
        // construct a proper buffer object a.k.a numpy array for Image
        // If the image is mono type, it will return a buffer object with two dimension: shape == (rows, cols)
        // if the image is 2,3,4 channels, it will return a buffer object with three dimension: shape = (rows, cols, cn)
        .def_buffer([](Image &im) -> buffer_info {
            Size size = im.GetSize();
            ImageType::Enum it = im.GetType();
            size_t cn = it;  // directly to channel type
            size_t w = size.width, h = size.height;

            if (it == 0 || w <= 0 || h <= 0)
                return buffer_info();  // return empty buffer object.

            if (it == 1) {
                return buffer_info(im.GetDataPtr(), {h, w}, {sizeof(char) * w, sizeof(char)});
            } else {
                return buffer_info(im.GetDataPtr(), {h, w, cn},
                                   {sizeof(char) * w * cn, sizeof(char) * cn, sizeof(char)});
            }
        });

    class_<DepthMap>(m, "DepthMap", buffer_protocol())
        .def(init<>(), call_guard<gil_scoped_release>())
        .def("IsValid", &DepthMap::IsValid, call_guard<gil_scoped_release>())
        .def("GetSize", &DepthMap::GetSize, call_guard<gil_scoped_release>())
        .def("SaveDepthMap", &DepthMap::SaveDepthMap, call_guard<gil_scoped_release>())
        .def_buffer([](DepthMap &self) -> buffer_info {
            Size sz = self.GetSize();
            double *p = self.GetDataPtr();
            const auto dsize = sizeof(double);

            return buffer_info(p, {sz.height, sz.width}, {dsize * sz.width * 1, dsize});
        });
    class_<ConfidenceMap>(m, "ConfidenceMap", buffer_protocol())
        .def(init<>())
        .def("IsValid", &ConfidenceMap::IsValid)
        .def("GetSize", &ConfidenceMap::GetSize)
        .def_buffer([](ConfidenceMap &self) -> buffer_info {
            Size sz = self.GetSize();
            double *p = self.GetDataPtr();
            const auto dsize = sizeof(double);

            return buffer_info(p, {sz.height, sz.width}, {dsize * sz.width * 1, dsize});
        });

    class_<CorrespondMap>(m, "CorrespondMap", buffer_protocol())
        .def(init<>())
        .def("IsValid", &CorrespondMap::IsValid)
        .def("GetSize", &CorrespondMap::GetSize)
        .def_buffer([](CorrespondMap &self) -> buffer_info {
            Size sz = self.GetSize();
            double *p = self.GetDataPtr();
            const auto dsize = sizeof(double);

            return buffer_info(p, {sz.height, sz.width, 2}, {dsize * sz.width * 2, dsize * 2, dsize});
        });

    enum_<PointMapType::Enum>(m, "PointMapTypeEnum")
        .value("None", PointMapType::None)
        .value("PointsOnly", PointMapType::PointsOnly)
        .value("PointsNormals", PointMapType::PointsNormals)
        .export_values();

    m.def(
        "PointMapTypeToString", [](const PointMapType::Enum &e) { return PointMapType::ToString(e); },
        call_guard<gil_scoped_release>());

    m.def(
        "PointMapCreate",
        [](const PointMapType::Enum it, const Size &sz) { return PointMap::Create(it, sz, nullptr, true); },
        call_guard<gil_scoped_release>());

    m.def(
        "PointMapDestroy", [](PointMap &img) { PointMap::Destroy(img); }, call_guard<gil_scoped_release>());

    class_<PointMap>(m, "PointMap", buffer_protocol())
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_static(
            "CreateFromFile",
            [](const char *file, const Size &sz, const PointMapUnit::Enum unit) {
                return PointMap::CreateFromFile(file, sz, unit);
            },
            call_guard<gil_scoped_release>())
        .def_static(
            "Destroy", [](PointMap &img) { PointMap::Destroy(img); }, call_guard<gil_scoped_release>())
        .def("IsValid", &PointMap::IsValid, call_guard<gil_scoped_release>())
        .def("GetSize", &PointMap::GetSize, call_guard<gil_scoped_release>())
        .def("Clone", &PointMap::Clone, call_guard<gil_scoped_release>())
        // TODO: Implement and use protocol buffer
        .def(
            "GetNormalDataPtr", [](PointMap &self) { return NormalData::fromPointMap(self); },
            call_guard<gil_scoped_release>())

        .def(
            "Save",
            [](PointMap &self, const char *filename, PointMapUnit::Enum unit, bool isBinary) {
                bool ret = self.Save(filename, unit, isBinary, Image());
                return ret;
            },
            arg("filename"), arg("unit") = PointMapUnit::Millimeter, arg("isBinary") = true,
            call_guard<gil_scoped_release>())

        .def(
            "SaveWithImage",
            [](PointMap &self, const char *filename, Image image, PointMapUnit::Enum unit, bool isBinary) {
                bool ret = self.Save(filename, unit, isBinary, image);
                return ret;
            },
            arg("filename"), arg("image"), arg("unit") = PointMapUnit::Millimeter, arg("isBinary") = true,
            call_guard<gil_scoped_release>())

        .def("GetTimestamp", &PointMap::GetTimestamp, call_guard<gil_scoped_release>())

        .def("SetTimestamp", &PointMap::SetTimestamp, call_guard<gil_scoped_release>())

        .def_buffer([](PointMap &self) -> buffer_info {
            Size sz = self.GetSize();
            double *p = self.GetPointDataPtr();
            const auto dsize = sizeof(double);

            return buffer_info(p, {sz.height, sz.width, 3}, {dsize * sz.width * 3, dsize * 3, dsize});
        });

    class_<Mesh>(m, "Mesh", buffer_protocol())
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_static(
            "CreateFromPointMapData",
            [](const Size &size, const double *data = nullptr, const double &z_threshold = 0.01) {
                return Mesh::CreateFromPointMapData(size, data, z_threshold);
            },
            call_guard<gil_scoped_release>())
        .def_static(
            "CreateFromPointMap",
            [](const PointMap &pm, const double &z_threshold = 0.01) {
                return Mesh::CreateFromPointMap(pm, z_threshold);
            },
            call_guard<gil_scoped_release>())
        .def_static(
            "Destroy", [](Mesh &mesh) { Mesh::Destroy(mesh); }, call_guard<gil_scoped_release>())
        .def("IsValid", &Mesh::IsValid, call_guard<gil_scoped_release>())
        .def("GetSize", &Mesh::GetSize, call_guard<gil_scoped_release>())
        .def("Clone", &Mesh::Clone, call_guard<gil_scoped_release>())
        .def("Save", &Mesh::Save, call_guard<gil_scoped_release>());

    class_<NormalData>(m, "NormalData", buffer_protocol())
        .def(init<>(), call_guard<gil_scoped_release>())
        .def("IsValid", &NormalData::IsValid, call_guard<gil_scoped_release>())
        .def("GetSize", &NormalData::GetSize, call_guard<gil_scoped_release>())

        .def_buffer([](NormalData &self) -> buffer_info {
            Size sz = self.GetSize();
            const auto dsize = sizeof(double);
            return buffer_info(self.data, {sz.height, sz.width, 3}, {dsize * sz.width * 3, dsize * 3, dsize});
        });

    m.def("SystemInit", &SystemInit, "Initialize system.", call_guard<gil_scoped_release>());
    m.def("SystemIsInited", &SystemIsInited, "System Is Inited?", call_guard<gil_scoped_release>());
    m.def("SystemShutdown", &SystemShutdown, "Shut down the system.", call_guard<gil_scoped_release>());

    m.def(
        "SystemFindDevice", [](const char *serialNumber) { return SystemFindDevice(serialNumber); },
        "Find the device with serial number.", arg("serialNumber"), call_guard<gil_scoped_release>());

    class_<X1::CaptureOptions>(m, "X1_CaptureOptions")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_readwrite("calc_normal", &X1::CaptureOptions::calc_normal)
        .def_readwrite("calc_normal_radius", &X1::CaptureOptions::calc_normal_radius)
        .def_readwrite("light_contrast_threshold", &X1::CaptureOptions::light_contrast_threshold)
        .def_readwrite("transform_to_camera", &X1::CaptureOptions::transform_to_camera)
        .def_readwrite("filter_range", &X1::CaptureOptions::filter_range)
        .def_readwrite("use_auto_noise_removal", &X1::CaptureOptions::use_auto_noise_removal)
        .def_readwrite("noise_removal_distance", &X1::CaptureOptions::noise_removal_distance)
        .def_readwrite("noise_removal_point_number", &X1::CaptureOptions::noise_removal_point_number)
        .def_readwrite("phase_filter_range", &X1::CaptureOptions::phase_filter_range)
        .def_readwrite("projector_brightness", &X1::CaptureOptions::projector_brightness)
        .def_readwrite("exposure_time_2d", &X1::CaptureOptions::exposure_time_2d)
        .def_readwrite("exposure_time_3d", &X1::CaptureOptions::exposure_time_3d)
        .def_readwrite("gain_2d", &X1::CaptureOptions::gain_2d)
        .def_readwrite("gain_3d", &X1::CaptureOptions::gain_3d)
        .def_readwrite("gamma_2d", &X1::CaptureOptions::gamma_2d)
        .def_readwrite("gamma_3d", &X1::CaptureOptions::gamma_3d)
        .def_readwrite("hdr_exposure_times", &X1::CaptureOptions::hdr_exposure_times)
        .def_readwrite("use_projector_capturing_2d_image", &X1::CaptureOptions::use_projector_capturing_2d_image)
        .def_readwrite("smoothness", &X1::CaptureOptions::smoothness)
        .def_readwrite("downsample_distance", &X1::CaptureOptions::downsample_distance)
        .def_readwrite("scan_times", &X1::CaptureOptions::scan_times)
        .def_readwrite("truncate_z_min", &X1::CaptureOptions::truncate_z_min)
        .def_readwrite("truncate_z_max", &X1::CaptureOptions::truncate_z_max)
        .def_readwrite("use_auto_bilateral_filter", &X1::CaptureOptions::use_auto_bilateral_filter)
        .def_readwrite("bilateral_filter_kernal_size", &X1::CaptureOptions::bilateral_filter_kernal_size)
        .def_readwrite("bilateral_filter_depth_sigma", &X1::CaptureOptions::bilateral_filter_depth_sigma)
        .def_readwrite("bilateral_filter_space_sigma", &X1::CaptureOptions::bilateral_filter_space_sigma)
        .def_readwrite("reflection_filter_threshold", &X1::CaptureOptions::reflection_filter_threshold)
        .def_readwrite("smooth_sigma", &X1::CaptureOptions::smooth_sigma)
        .def_readwrite("enable_2d_in_capture", &X1::CaptureOptions::enable_2d_in_capture)

        .def(
            "GetHDRExposureTimeContent",
            [](X1::CaptureOptions &opt, int index) {
                int exp = -1;
                if (index >= 0 && index < 3) {
                    exp = opt.hdr_exposuretime_content[index];
                }
                return exp;
            },
            call_guard<gil_scoped_release>())
        .def(
            "SetHDRExposureTimeContent",
            [](X1::CaptureOptions &opt, int index, int exposure_time) {
                if (index >= 0 && index < 3) {
                    if (exposure_time >= 3 && exposure_time <= 100) {
                        opt.hdr_exposuretime_content[index] = exposure_time;
                        return true;
                    }
                }
                return false;
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetHDRGainContent",
            [](X1::CaptureOptions &opt, int index) {
                float exp = -1.0f;
                if (index >= 0 && index < 3) {
                    exp = opt.hdr_gain_3d[index];
                }
                return exp;
            },
            call_guard<gil_scoped_release>())
        .def(
            "SetHDRGainContent",
            [](X1::CaptureOptions &opt, int index, float gain_3d) {
                if (index >= 0 && index < 3) {
                    if (gain_3d >= 0 && gain_3d <= 20) {
                        opt.hdr_gain_3d[index] = gain_3d;
                        return true;
                    }
                }
                return false;
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetHDRScanTimesContent",
            [](X1::CaptureOptions &opt, int index) {
                int exp = -1;
                if (index >= 0 && index < 3) {
                    exp = opt.hdr_scan_times[index];
                }
                return exp;
            },
            call_guard<gil_scoped_release>())
        .def(
            "SetHDRScanTimesContent",
            [](X1::CaptureOptions &opt, int index, int scan_times) {
                if (index >= 0 && index < 3) {
                    if (scan_times >= 2 && scan_times <= 4) {
                        opt.hdr_scan_times[index] = scan_times;
                        return true;
                    }
                }
                return false;
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetHDRProjectorBrightnessContent",
            [](X1::CaptureOptions &opt, int index) {
                int exp = -1;
                if (index >= 0 && index < 3) {
                    exp = opt.hdr_projector_brightness[index];
                }
                return exp;
            },
            call_guard<gil_scoped_release>())
        .def(
            "SetHDRProjectorBrightnessContent",
            [](X1::CaptureOptions &opt, int index, int projector_brightness) {
                if (index >= 0 && index < 3) {
                    if (projector_brightness >= 1 && projector_brightness <= 240) {
                        opt.hdr_projector_brightness[index] = projector_brightness;
                        return true;
                    }
                }
                return false;
            },
            call_guard<gil_scoped_release>())
        .def_readwrite("capture_mode", &X1::CaptureOptions::capture_mode)
        .def_readwrite("confidence_threshold", &X1::CaptureOptions::confidence_threshold)
        .def_readwrite("roi", &X1::CaptureOptions::roi);

    class_<X1::CustomTransformOptions>(m, "X1_CustomTransformOptions")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_readwrite("coordinate_select", &X1::CustomTransformOptions::coordinate_select)
        .def("SetTransform",
             [](X1::CustomTransformOptions &self, array_t<double> &transform) {
                 buffer_info buf = transform.request();
                 double *ptr = (double *)buf.ptr;
                 for (size_t i = 0; i < 16; i++) {
                     self.transform[i] = *(ptr + i);
                 }
             });


    enum_<SmoothnessLevel>(m, "SmoothnessLevel")
        .value("SmoothnessLevel_Off", SmoothnessLevel_Off)
        .value("SmoothnessLevel_Weak", SmoothnessLevel_Weak)
        .value("SmoothnessLevel_Normal", SmoothnessLevel_Normal)
        .value("SmoothnessLevel_Strong", SmoothnessLevel_Strong)
        .export_values();

    enum_<CaptureMode>(m, "CaptureMode")
        .value("CaptureMode_Fast", CaptureMode_Fast)
        .value("CaptureMode_Normal", CaptureMode_Normal)
        .value("CaptureMode_Ultra", CaptureMode_Ultra)
        .value("CaptureMode_Robust", CaptureMode_Robust)
        .value("CaptureMode_AntiInterReflection", CaptureMode_AntiInterReflection)
        .value("CaptureMode_SwingLineScan", CaptureMode_SwingLineScan)
        .value("CaptureMode_FixedLineScan", CaptureMode_FixedLineScan)
        .value("CaptureMode_LineArrayShift", CaptureMode_LineArrayShift)
        .export_values();

    enum_<TriggerMode>(m, "TriggerMode")
        .value("TriggerMode_SoftWare", TriggerMode_SoftWare)
        .value("TriggerMode_HardWare", TriggerMode_HardWare)
        .value("TriggerMode_FixedRate", TriggerMode_FixedRate)
        .export_values();

    class_<X1>(m, "X1")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_static(
            "Create", [](const Device &d, enum CameraID camid) { return X1::Create(d, camid); }, arg("device"),
            arg("camid") = RVC::CameraID_Left, call_guard<gil_scoped_release>())
        .def_static("Destroy", &X1::Destroy, call_guard<gil_scoped_release>())
        .def("Open", &X1::Open, call_guard<gil_scoped_release>())
        .def("IsOpen", &X1::IsOpen, call_guard<gil_scoped_release>())
        .def("Close", &X1::Close, call_guard<gil_scoped_release>())
        .def("IsValid", &X1::IsValid, call_guard<gil_scoped_release>())
        .def("IsPhysicallyConnected", &X1::IsPhysicallyConnected, call_guard<gil_scoped_release>())
        .def(
            "Capture",
            [](X1 &self, X1::CaptureOptions opts) {
                bool ret = false;
                ret = self.Capture(opts);
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def(
            "Capture",
            [](X1 &self) {
                bool ret = false;
                ret = self.Capture();
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def(
            "Capture2D",
            [](X1 &self, const X1::CaptureOptions &opts) {
                bool ret = false;
                ret = self.Capture2D(opts);
                return ret;
            },
            arg("opts") = X1::CaptureOptions(), call_guard<gil_scoped_release>())
        .def(
            "Capture2D",
            [](X1 &self) {
                bool ret = false;
                ret = self.Capture2D();
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def("SetBandwidth", &X1::SetBandwidth, call_guard<gil_scoped_release>())
        .def(
            "SetCustomTransformation",
            [](X1 &self, X1::CustomTransformOptions opts) {
                bool ret = self.SetCustomTransformation(opts);
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetCustomTransformation",
            [](X1 &self) {
                X1::CustomTransformOptions opts;
                bool ret = self.GetCustomTransformation(opts);
                return std::make_tuple(ret, opts);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetCameraResolution",
            [](X1 &self) {
                Size resolution;
                bool ret = self.GetCameraResolution(resolution);
                return std::make_tuple(ret, resolution);
            },
            call_guard<gil_scoped_release>())

        .def(
            "GetProjectorTemperature",
            [](X1 &self) {
                float temperature;
                bool ret = self.GetProjectorTemperature(temperature);
                return std::make_tuple(ret, temperature);
            },
            call_guard<gil_scoped_release>())
        .def("GetImage", &X1::GetImage, call_guard<gil_scoped_release>())
        .def(
            "GetExposureTimeRange",
            [](X1 &self) {
                int min_v, max_v;
                bool ret = self.GetExposureTimeRange(&min_v, &max_v);
                return std::make_tuple(ret, min_v, max_v);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetGainRange",
            [](X1 &self) {
                float min_v, max_v;
                bool ret = self.GetGainRange(&min_v, &max_v);
                return std::make_tuple(ret, min_v, max_v);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetGammaRange",
            [](X1 &self) {
                float min_v, max_v;
                bool ret = self.GetGammaRange(&min_v, &max_v);
                return std::make_tuple(ret, min_v, max_v);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetCameraTemperature",
            [](X1 &self, CameraTempSelector sel) {
                float temperature;
                bool ret = self.GetCameraTemperature(sel, temperature);
                return std::make_pair(ret, temperature);
            },
            call_guard<gil_scoped_release>())
        .def("GetDepthMap", &X1::GetDepthMap, call_guard<gil_scoped_release>())
        .def("GetPointMap", &X1::GetPointMap, call_guard<gil_scoped_release>())
        .def("GetMesh", &X1::GetMesh, call_guard<gil_scoped_release>())
        .def("GetConfidenceMap", &X1::GetConfidenceMap, call_guard<gil_scoped_release>())
        .def("SaveEncodedImagesData", &X1::SaveEncodedImagesData, call_guard<gil_scoped_release>())
        .def("SetBalanceRatio", &X1::SetBalanceRatio, call_guard<gil_scoped_release>())
        .def(
            "GetBalanceRatio",
            [](X1 &self, BalanceSelector selector) {
                float value;
                bool ret = self.GetBalanceRatio(selector, &value);
                return std::make_tuple(ret, value);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetBalanceRange",
            [](X1 &self, BalanceSelector selector) {
                float min_v, max_v;
                bool ret = self.GetBalanceRange(selector, &min_v, &max_v);
                return std::make_tuple(ret, min_v, max_v);
            },
            call_guard<gil_scoped_release>())
        .def("AutoWhiteBalance", &X1::AutoWhiteBalance, call_guard<gil_scoped_release>())
        .def(
            "GetExtrinsicMatrix",
            [](X1 &self) {
                std::vector<float> matrix = {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
                bool ret = self.GetExtrinsicMatrix(&matrix[0]);
                return std::make_pair(ret, matrix);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetIntrinsicParameters",
            [](X1 &self) {
                std::vector<float> intrinsic_matrix = {0, 0, 0, 0, 0, 0, 0, 0, 0};
                std::vector<float> distortion = {0, 0, 0, 0, 0};
                bool ret = self.GetIntrinsicParameters(&intrinsic_matrix[0], &distortion[0]);
                return std::make_tuple(ret, intrinsic_matrix, distortion);
            },
            call_guard<gil_scoped_release>())
        .def("SaveCaptureOptionParameters", &X1::SaveCaptureOptionParameters, call_guard<gil_scoped_release>())
        .def(
            "LoadCaptureOptionParameters",
            [](X1 &self) {
                X1::CaptureOptions opts;
                bool ret = self.LoadCaptureOptionParameters(opts);
                return std::make_pair(ret, opts);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetAutoCaptureSetting",
            [](X1 &self, X1::CaptureOptions opts, ROI roi) {
                bool ret = false;
                ret = self.GetAutoCaptureSetting(opts, roi);
                return std::make_pair(ret, opts);
            },
            arg("opts") = X1::CaptureOptions(), arg("roi") = ROI(), call_guard<gil_scoped_release>())
        .def(
            "GetAutoHdrCaptureSetting",
            [](X1 &self, X1::CaptureOptions opts, ROI roi) {
                bool ret = false;
                ret = self.GetAutoHdrCaptureSetting(opts, roi);
                return std::make_pair(ret, opts);
            },
            arg("opts") = X1::CaptureOptions(), arg("roi") = ROI(), call_guard<gil_scoped_release>())
        .def(
            "GetAutoNoiseRemovalSetting",
            [](X1 &self, X1::CaptureOptions opts) {
                bool ret = false;
                ret = self.GetAutoNoiseRemovalSetting(opts);
                return std::make_pair(ret, opts);
            },
            call_guard<gil_scoped_release>())
        .def("LoadSettingFromFile", &X1::LoadSettingFromFile, call_guard<gil_scoped_release>())
        .def("SaveSettingToFile", &X1::SaveSettingToFile, call_guard<gil_scoped_release>())
        .def("CheckRoi", &X1::CheckRoi, call_guard<gil_scoped_release>())
        .def("AutoAdjustRoi", &X1::AutoAdjustRoi, call_guard<gil_scoped_release>())
        .def(
            "GetRoiRange",
            [](X1 &self) {
                bool ret = false;
                ROIRange range;
                ret = self.GetRoiRange(range);
                return std::make_pair(ret, range);
            },
            call_guard<gil_scoped_release>())
        .def("OpenProtectiveCover", &X1::OpenProtectiveCover, call_guard<gil_scoped_release>())
        .def("CloseProtectiveCover", &X1::CloseProtectiveCover, call_guard<gil_scoped_release>())
        .def("ResetProtectiveCover", &X1::ResetProtectiveCover, call_guard<gil_scoped_release>())
        .def("OpenProtectiveCoverAsync", &X1::OpenProtectiveCoverAsync, call_guard<gil_scoped_release>())
        .def("CloseProtectiveCoverAsync", &X1::CloseProtectiveCoverAsync, call_guard<gil_scoped_release>())
        .def(
            "GetProtectiveCoverStatus",
            [](X1 &self) {
                bool ret = false;
                ProtectiveCoverStatus status = ProtectiveCoverStatus::ProtectiveCoverStatus_Unknown;
                ret = self.GetProtectiveCoverStatus(status);
                return std::make_pair(ret, status);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetAuto2DExposureTime",
            [](X1 &self, X1::CaptureOptions opts, ROI roi) {
                bool ret = false;
                ret = self.GetAuto2DExposureTime(opts, roi);
                return std::make_pair(ret, opts);
            },
            arg("opts") = X1::CaptureOptions(), arg("roi") = ROI(), call_guard<gil_scoped_release>())
        .def("SetCurrentUserSet", &X1::SetCurrentUserSet, call_guard<gil_scoped_release>())
        .def("GetCurrentUserSet", &X1::GetCurrentUserSet, call_guard<gil_scoped_release>())
        .def("SetUserSetName", &X1::SetUserSetName, call_guard<gil_scoped_release>())
        .def("GetUserSetName", &X1::GetUserSetName, call_guard<gil_scoped_release>());


    class_<X2::CaptureOptions>(m, "X2_CaptureOptions")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_readwrite("transform_to_camera", &X2::CaptureOptions::transform_to_camera)
        .def_readwrite("projector_brightness", &X2::CaptureOptions::projector_brightness)
        .def_readwrite("calc_normal", &X2::CaptureOptions::calc_normal)
        .def_readwrite("calc_normal_radius", &X2::CaptureOptions::calc_normal_radius)
        .def_readwrite("light_contrast_threshold", &X2::CaptureOptions::light_contrast_threshold)
        .def_readwrite("edge_noise_reduction_threshold", &X2::CaptureOptions::edge_noise_reduction_threshold)
        .def_readwrite("use_auto_noise_removal", &X2::CaptureOptions::use_auto_noise_removal)
        .def_readwrite("noise_removal_distance", &X2::CaptureOptions::noise_removal_distance)
        .def_readwrite("noise_removal_point_number", &X2::CaptureOptions::noise_removal_point_number)
        .def_readwrite("exposure_time_2d", &X2::CaptureOptions::exposure_time_2d)
        .def_readwrite("exposure_time_3d", &X2::CaptureOptions::exposure_time_3d)
        .def_readwrite("gain_2d", &X2::CaptureOptions::gain_2d)
        .def_readwrite("gain_3d", &X2::CaptureOptions::gain_3d)
        .def_readwrite("hdr_exposure_times", &X2::CaptureOptions::hdr_exposure_times)
        .def_readwrite("use_projector_capturing_2d_image", &X2::CaptureOptions::use_projector_capturing_2d_image)
        .def_readwrite("correspond2d", &X2::CaptureOptions::correspond2d)
        .def_readwrite("smoothness", &X2::CaptureOptions::smoothness)
        .def_readwrite("downsample_distance", &X2::CaptureOptions::downsample_distance)
        .def_readwrite("scan_times", &X2::CaptureOptions::scan_times)
        .def_readwrite("use_auto_bilateral_filter", &X2::CaptureOptions::use_auto_bilateral_filter)
        .def_readwrite("bilateral_filter_kernal_size", &X2::CaptureOptions::bilateral_filter_kernal_size)
        .def_readwrite("bilateral_filter_depth_sigma", &X2::CaptureOptions::bilateral_filter_depth_sigma)
        .def_readwrite("bilateral_filter_space_sigma", &X2::CaptureOptions::bilateral_filter_space_sigma)
        .def_readwrite("line_scanner_scan_time_ms", &X2::CaptureOptions::line_scanner_scan_time_ms)
        .def_readwrite("line_scanner_exposure_time_us", &X2::CaptureOptions::line_scanner_exposure_time_us)
        .def_readwrite("line_scanner_min_distance", &X2::CaptureOptions::line_scanner_min_distance)
        .def_readwrite("line_scanner_max_distance", &X2::CaptureOptions::line_scanner_max_distance)
        .def_readwrite("line_scanner_laser_position", &X2::CaptureOptions::line_scanner_laser_position)
        .def_readwrite("line_scanner_brightness_threshold", &X2::CaptureOptions::line_scanner_brightness_threshold)
        .def_readwrite("line_scanner_confidence", &X2::CaptureOptions::line_scanner_confidence)
        .def_readwrite("reflection_filter_threshold", &X2::CaptureOptions::reflection_filter_threshold)
        .def_readwrite("smooth_sigma", &X2::CaptureOptions::smooth_sigma)
        .def_readwrite("roi", &X2::CaptureOptions::roi)
        .def_readwrite("enable_2d_in_capture", &X2::CaptureOptions::enable_2d_in_capture)
        .def_readwrite("pointcloud_completion", &X2::CaptureOptions::pointcloud_completion)
        .def_readwrite("truncate_z_min", &X2::CaptureOptions::truncate_z_min)
        .def_readwrite("truncate_z_max", &X2::CaptureOptions::truncate_z_max)
        .def_readwrite("trigger_mode", &X2::CaptureOptions::trigger_mode)
        .def_readwrite("encoder_trigger_interval", &X2::CaptureOptions::encoder_trigger_interval)
        .def_readwrite("fixed_rate", &X2::CaptureOptions::fixed_rate)
        .def_readwrite("auto_set_fixed_rate", &X2::CaptureOptions::auto_set_fixed_rate)
        .def_readwrite("enable_transfer_control", &X2::CaptureOptions::enable_transfer_control)
        .def(
            "GetHDRExposureTimeContent",
            [](X2::CaptureOptions &opt, int index) {
                int exp = -1;
                if (index >= 0 && index < 3) {
                    exp = opt.hdr_exposuretime_content[index];
                }
                return exp;
            },
            call_guard<gil_scoped_release>())
        .def(
            "SetHDRExposureTimeContent",
            [](X2::CaptureOptions &opt, int index, int exposure_time) {
                if (index >= 0 && index < 3) {
                    if (exposure_time >= 3 && exposure_time <= 100) {
                        opt.hdr_exposuretime_content[index] = exposure_time;
                        return true;
                    }
                }
                return false;
            },
            call_guard<gil_scoped_release>())

        .def(
            "GetHDRGainContent",
            [](X2::CaptureOptions &opt, int index) {
                float exp = -1.0f;
                if (index >= 0 && index < 3) {
                    exp = opt.hdr_gain_3d[index];
                }
                return exp;
            },
            call_guard<gil_scoped_release>())
        .def(
            "SetHDRGainContent",
            [](X2::CaptureOptions &opt, int index, float gain_3d) {
                if (index >= 0 && index < 3) {
                    if (gain_3d >= 0 && gain_3d <= 20) {
                        opt.hdr_gain_3d[index] = gain_3d;
                        return true;
                    }
                }
                return false;
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetHDRProjectorBrightnessContent",
            [](X2::CaptureOptions &opt, int index) {
                int exp = -1;
                if (index >= 0 && index < 3) {
                    exp = opt.hdr_projector_brightness[index];
                }
                return exp;
            },
            call_guard<gil_scoped_release>())
        .def(
            "SetHDRProjectorBrightnessContent",
            [](X2::CaptureOptions &opt, int index, int projector_brightness) {
                if (index >= 0 && index < 3) {
                    if (projector_brightness >= 1 && projector_brightness <= 240) {
                        opt.hdr_projector_brightness[index] = projector_brightness;
                        return true;
                    }
                }
                return false;
            },
            call_guard<gil_scoped_release>())
        .def("SetHDRScanTimesContent",
             [](X2::CaptureOptions &self, int index, int scan_time) {
                 if (index >= 0 && index < 3) {
                     if (scan_time >= 1 && scan_time <= 8) {
                         self.hdr_scan_times[index] = scan_time;
                         return true;
                     }
                 }
                 return false;
             })
        .def("GetHDRScanTimesContent",
             [](X2::CaptureOptions &self, int index) {
                 if (index >= 0 && index < 3) {
                     return self.hdr_scan_times[index];
                 }
                 return -1;
             })
        .def_readwrite("gamma_2d", &X2::CaptureOptions::gamma_2d)
        .def_readwrite("gamma_3d", &X2::CaptureOptions::gamma_3d)
        .def_readwrite("scan_times", &X2::CaptureOptions::scan_times)
        // .def_readwrite("confidence_filter_threshold", &X2::CaptureOptions::confidence_filter_threshold)
        .def_readwrite("projector_color", &X2::CaptureOptions::projector_color)
        .def_readwrite("capture_mode", &X2::CaptureOptions::capture_mode)
        .def_readwrite("confidence_threshold", &X2::CaptureOptions::confidence_threshold);
    class_<X2::CustomTransformOptions>(m, "X2_CustomTransformOptions")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_readwrite("coordinate_select", &X2::CustomTransformOptions::coordinate_select)
        .def("SetTransform",
             [](X2::CustomTransformOptions &self, array_t<double> &transform) {
                 buffer_info buf = transform.request();
                 double *ptr = (double *)buf.ptr;
                 for (size_t i = 0; i < 16; i++) {
                     self.transform[i] = *(ptr + i);
                 }
             });

    class_<X2>(m, "X2")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_static(
            "Create", [](const Device &d) { return X2::Create(d); }, arg("device"), call_guard<gil_scoped_release>())
        .def_static("Destroy", &X2::Destroy, call_guard<gil_scoped_release>())
        .def("Open", &X2::Open, call_guard<gil_scoped_release>())
        .def("IsOpen", &X2::IsOpen, call_guard<gil_scoped_release>())
        .def("Close", &X2::Close, call_guard<gil_scoped_release>())
        .def("IsValid", &X2::IsValid, call_guard<gil_scoped_release>())
        .def("IsPhysicallyConnected", &X2::IsPhysicallyConnected, call_guard<gil_scoped_release>())
        .def(
            "Capture",
            [](X2 &self, X2::CaptureOptions opts) {
                bool ret = false;
                ret = self.Capture(opts);
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def(
            "Capture",
            [](X2 &self) {
                bool ret = false;
                ret = self.Capture();
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def(
            "StartFixedLineScan",
            [](X2 &self, X2::CaptureOptions opts) {
                bool ret = false;
                ret = self.StartFixedLineScan(opts);
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def(
            "StartFixedLineScan",
            [](X2 &self) {
                bool ret = false;
                ret = self.StartFixedLineScan();
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetFixedLineScanPointMap",
            [](X2 &self) {
                PointMap pm;
                pm = self.GetFixedLineScanPointMap();
                return pm;
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetFixedLineScanPointMap",
            [](X2 &self, PointMap &point_map) {
                bool ret = false;
                ret = self.GetFixedLineScanPointMap(point_map);
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def(
            "StopFixedLineScan",
            [](X2 &self) {
                bool ret = false;
                ret = self.StopFixedLineScan();
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def(
            "Capture2D",
            [](X2 &self, const CameraID cid, const X2::CaptureOptions &opts) {
                bool ret = false;
                ret = self.Capture2D(cid, opts);
                return ret;
            },
            arg("cid"), arg("opts") = X2::CaptureOptions(), call_guard<gil_scoped_release>())
        .def(
            "Capture2D",
            [](X2 &self, const CameraID cid) {
                bool ret = false;
                ret = self.Capture2D(cid);
                return ret;
            },
            arg("cid"), call_guard<gil_scoped_release>())
        .def("SetBandwidth", &X2::SetBandwidth, call_guard<gil_scoped_release>())
        .def(
            "SetCustomTransformation",
            [](X2 &self, X2::CustomTransformOptions opts) {
                bool ret = self.SetCustomTransformation(opts);
                return ret;
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetCustomTransformation",
            [](X2 &self) {
                X2::CustomTransformOptions opts;
                bool ret = self.GetCustomTransformation(opts);
                return std::make_tuple(ret, opts);
            },
            call_guard<gil_scoped_release>())

        .def(
            "GetCameraResolution",
            [](X2 &self) {
                Size resolution;
                bool ret = self.GetCameraResolution(resolution);
                return std::make_tuple(ret, resolution);
            },
            call_guard<gil_scoped_release>())

        .def(
            "GetTimestamp",
            [](X2 &self) {
                uint64_t timestamp;
                bool ret = self.GetTimestamp(timestamp);
                return std::make_tuple(ret, timestamp);
            },
            call_guard<gil_scoped_release>())

        .def(
            "ResetTimestamp",
            [](X2 &self) {
                bool ret = self.ResetTimestamp();
                return ret;
            },
            call_guard<gil_scoped_release>())

        .def(
            "GetProjectorTemperature",
            [](X2 &self) {
                float temperature;
                bool ret = self.GetProjectorTemperature(temperature);
                return std::make_tuple(ret, temperature);
            },
            call_guard<gil_scoped_release>())
        .def("GetImage", &X2::GetImage, call_guard<gil_scoped_release>())
        .def("GetPointMap", &X2::GetPointMap, call_guard<gil_scoped_release>())
        .def("GetMesh", &X2::GetMesh, call_guard<gil_scoped_release>())
        .def("GetConfidenceMap", &X2::GetConfidenceMap, call_guard<gil_scoped_release>())
        .def("GetCorrespondMap", &X2::GetCorrespondMap, call_guard<gil_scoped_release>())
        .def("SaveEncodedImagesData", &X2::SaveEncodedImagesData, call_guard<gil_scoped_release>())
        .def("GetDepthMap", &X2::GetDepthMap, call_guard<gil_scoped_release>())
        .def("AutoWhiteBalance", &X2::AutoWhiteBalance, call_guard<gil_scoped_release>())
        .def(
            "GetExtrinsicMatrix",
            [](X2 &self, CameraID cid) {
                std::vector<float> matrix(16);
                bool ret = self.GetExtrinsicMatrix(cid, matrix.data());
                return std::make_pair(ret, matrix);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetIntrinsicParameters",
            [](X2 &self, CameraID cid) {
                std::vector<float> intrinsic_matrix(9);
                std::vector<float> distortion(5);
                bool ret = self.GetIntrinsicParameters(cid, intrinsic_matrix.data(), distortion.data());
                return std::make_tuple(ret, intrinsic_matrix, distortion);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetExposureTimeRange",
            [](X2 &self) {
                int min_v, max_v;
                bool ret = self.GetExposureTimeRange(&min_v, &max_v);
                return std::make_tuple(ret, min_v, max_v);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetGainRange",
            [](X2 &self) {
                float min_v, max_v;
                bool ret = self.GetGainRange(&min_v, &max_v);
                return std::make_tuple(ret, min_v, max_v);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetGammaRange",
            [](X2 &self) {
                float min_v, max_v;
                bool ret = self.GetGammaRange(&min_v, &max_v);
                return std::make_tuple(ret, min_v, max_v);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetCameraTemperature",
            [](X2 &self, CameraID cid, CameraTempSelector sel) {
                float temperature;
                bool ret;
                ret = self.GetCameraTemperature(cid, sel, temperature);
                return std::make_pair(ret, temperature);
            },
            call_guard<gil_scoped_release>())
        .def("SaveCaptureOptionParameters", &X2::SaveCaptureOptionParameters, call_guard<gil_scoped_release>())
        .def(
            "LoadCaptureOptionParameters",
            [](X2 &self) {
                X2::CaptureOptions opts;
                bool ret = self.LoadCaptureOptionParameters(opts);
                return std::make_pair(ret, opts);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetAutoCaptureSetting",
            [](X2 &self, X2::CaptureOptions opts, ROI roi) {
                bool ret = false;
                ret = self.GetAutoCaptureSetting(opts, roi);
                return std::make_pair(ret, opts);
            },
            arg("opts") = X2::CaptureOptions(), arg("roi") = ROI(), call_guard<gil_scoped_release>())
        .def(
            "GetAutoHdrCaptureSetting",
            [](X2 &self, X2::CaptureOptions opts, ROI roi) {
                bool ret = false;
                ret = self.GetAutoHdrCaptureSetting(opts, roi);
                return std::make_pair(ret, opts);
            },
            arg("opts") = X2::CaptureOptions(), arg("roi") = ROI(), call_guard<gil_scoped_release>())
        .def(
            "GetAutoNoiseRemovalSetting",
            [](X2 &self, X2::CaptureOptions opts) {
                bool ret = false;
                ret = self.GetAutoNoiseRemovalSetting(opts);
                return std::make_pair(ret, opts);
            },
            call_guard<gil_scoped_release>())
        .def("LoadSettingFromFile", &X2::LoadSettingFromFile, call_guard<gil_scoped_release>())
        .def("SaveSettingToFile", &X2::SaveSettingToFile, call_guard<gil_scoped_release>())
        .def("CheckRoi", &X2::CheckRoi, call_guard<gil_scoped_release>())
        .def("AutoAdjustRoi", &X2::AutoAdjustRoi, call_guard<gil_scoped_release>())
        .def(
            "GetRoiRange",
            [](X2 &self) {
                bool ret = false;
                ROIRange range;
                ret = self.GetRoiRange(range);
                return std::make_pair(ret, range);
            },
            call_guard<gil_scoped_release>())
        .def("OpenProtectiveCover", &X2::OpenProtectiveCover, call_guard<gil_scoped_release>())
        .def("CloseProtectiveCover", &X2::CloseProtectiveCover, call_guard<gil_scoped_release>())
        .def("ResetProtectiveCover", &X2::ResetProtectiveCover, call_guard<gil_scoped_release>())
        .def("OpenProtectiveCoverAsync", &X2::OpenProtectiveCoverAsync, call_guard<gil_scoped_release>())
        .def("CloseProtectiveCoverAsync", &X2::CloseProtectiveCoverAsync, call_guard<gil_scoped_release>())
        .def(
            "GetProtectiveCoverStatus",
            [](X2 &self) {
                bool ret = false;
                ProtectiveCoverStatus status = ProtectiveCoverStatus::ProtectiveCoverStatus_Unknown;
                ret = self.GetProtectiveCoverStatus(status);
                return std::make_pair(ret, status);
            },
            call_guard<gil_scoped_release>())
        .def(
            "GetAuto2DExposureTime",
            [](X2 &self, X2::CaptureOptions opts, ROI roi) {
                bool ret = false;
                ret = self.GetAuto2DExposureTime(opts, roi);
                return std::make_pair(ret, opts);
            },
            arg("opts") = X2::CaptureOptions(), arg("roi") = ROI(), call_guard<gil_scoped_release>())
        .def("SetCurrentUserSet", &X2::SetCurrentUserSet, call_guard<gil_scoped_release>())
        .def("GetCurrentUserSet", &X2::GetCurrentUserSet, call_guard<gil_scoped_release>())
        .def("SetUserSetName", &X2::SetUserSetName, call_guard<gil_scoped_release>())
        .def("GetUserSetName", &X2::GetUserSetName, call_guard<gil_scoped_release>());

    class_<Compensator_FixedMarkers>(m, "Compensator_FixedMarkers")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def(
            "Initialize",
            [](Compensator_FixedMarkers &self, const PointMap &pm, const RVC::Image &img, int markerType) {
                return self.Initialize(pm, img, markerType);
            },
            call_guard<gil_scoped_release>())
        .def(
            "Update",
            [](Compensator_FixedMarkers &self, const PointMap &pm, const RVC::Image &img) {
                double driftDistance = 0;
                bool ret = self.Update(pm, img, driftDistance);
                return std::make_tuple(ret, driftDistance);
            },
            call_guard<gil_scoped_release>())
        .def(
            "Apply",
            [](Compensator_FixedMarkers &self, PointMap &pm) {
                bool ret = self.Apply(pm);
                return std::make_tuple(ret, pm);
            },
            call_guard<gil_scoped_release>());

    m.def("GetExternalCameraExtrinsicMatrix",
          [](const Image &internal_camera_image0, const PointMap &internal_camera_point_map0,
             const pybind11::array_t<unsigned char> &external_camera_image0, const Image &internal_camera_image1,
             const PointMap &internal_camera_point_map1, const pybind11::array_t<unsigned char> &external_camera_image1,
             const Image &internal_camera_image2, const PointMap &internal_camera_point_map2,
             const pybind11::array_t<unsigned char> &external_camera_image2, int external_camera_image_width,
             int external_camera_image_height, const std::vector<float> &external_camera_intrinsic_matrix,
             const std::vector<float> &external_camera_camera_distortion) {
              pybind11::buffer_info buf0 = external_camera_image0.request();
              unsigned char *ptr0 = (unsigned char *)buf0.ptr;
              pybind11::buffer_info buf1 = external_camera_image1.request();
              unsigned char *ptr1 = (unsigned char *)buf1.ptr;
              pybind11::buffer_info buf2 = external_camera_image2.request();
              unsigned char *ptr2 = (unsigned char *)buf2.ptr;
              std::vector<float> external_camera_extrinsic_matrix(16);
              double error;
              bool ret;
              {
                  gil_scoped_release release;
                  ret = GetExternalCameraExtrinsicMatrix(
                      internal_camera_image0, internal_camera_point_map0, ptr0, internal_camera_image1,
                      internal_camera_point_map1, ptr1, internal_camera_image2, internal_camera_point_map2, ptr2,
                      external_camera_image_width, external_camera_image_height, external_camera_intrinsic_matrix.data(),
                      external_camera_camera_distortion.data(), external_camera_extrinsic_matrix.data(), error);
              }
              return std::make_tuple(ret, external_camera_extrinsic_matrix, error);
          });

    m.def(
        "GetExternalCameraPointMap",
        [](const PointMap &internal_camera_point_map, const int external_camera_image_width,
           const int external_camera_image_height, const std::vector<float> &external_camera_intrinsic_matrix,
           const std::vector<float> &external_camera_camera_distortion,
           const std::vector<float> &external_camera_extrinsic_matrix) {
            PointMap external_camera_point_map = GetExternalCameraPointMap(
                internal_camera_point_map, external_camera_image_width, external_camera_image_height,
                external_camera_intrinsic_matrix.data(), external_camera_camera_distortion.data(),
                external_camera_extrinsic_matrix.data());
            return external_camera_point_map;
        },
        call_guard<gil_scoped_release>());

    class_<CodedCircleMarkerType>(m, "CodedCircleMarkerType")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_readwrite("N", &CodedCircleMarkerType::N)
        .def_readwrite("r1_to_r0_ratio", &CodedCircleMarkerType::r1_to_r0_ratio)
        .def_readwrite("r2_to_r0_ratio", &CodedCircleMarkerType::r2_to_r0_ratio);

    class_<CodedCircleMarker>(m, "CodedCircleMarker")
        .def(init<>(), call_guard<gil_scoped_release>())
        .def_readwrite("x", &CodedCircleMarker::x)
        .def_readwrite("y", &CodedCircleMarker::y)
        .def_readwrite("code", &CodedCircleMarker::code);

    m.def(
        "DetectCodedCircleMarker",
        [](const RVC::Image &img, const RVC::CodedCircleMarkerType &type) {
            RVC::CodedCircleMarker markers[1000];
            int markerNums = 0;
            RVC::DetectCodedCircleMarker(img, type, &markerNums, markers);

            std::vector<RVC::CodedCircleMarker> markersVec;
            for (int i = 0; i < markerNums; i++) {
                markersVec.push_back(markers[i]);
            }
            return markersVec;
        },
        call_guard<gil_scoped_release>());

    // pass in cv::Mat img directly.
    // Notice: The CPython ABI changes from version to version, often in incompatible ways, so you have to compile for
    // each version separately.
    m.def(
        "DetectCodedCircleMarker",
        [](const pybind11::array_t<unsigned char> &img, const RVC::CodedCircleMarkerType &type) {
            pybind11::buffer_info buf = img.request();
            unsigned char *ptr = (unsigned char *)buf.ptr;
            int width = buf.shape[1];
            int height = buf.shape[0];
            int channels = buf.ndim > 2 ? buf.shape[2] : 1;

            RVC::Image image;
            if (channels == 1) {
                image = RVC::Image::Create(RVC::ImageType::Mono8, RVC::Size(width, height), ptr, false);
            } else {  // channels == 3
                image = RVC::Image::Create(RVC::ImageType::BGR8, RVC::Size(width, height), ptr, false);
            }

              RVC::CodedCircleMarker markers[1000];
              int markerNums = 0;
              {
                  gil_scoped_release release;
                  RVC::DetectCodedCircleMarker(image, type, &markerNums, markers);
              }

              std::vector<RVC::CodedCircleMarker> markersVec;
              for (int i = 0; i < markerNums; i++) {
                  markersVec.push_back(markers[i]);
              }
              return markersVec;
          });

    m.def(
        "DetectConcentricCircleMarker2d",
        [](const RVC::Image &image) {
            std::vector<double> point2d(2000);
            int markerNums = 0;
            int ret = RVC::DetectConcentricCircleMarker2d(image, &markerNums, point2d.data());
            return std::make_tuple(ret, markerNums, point2d);
        },
        call_guard<gil_scoped_release>());

    m.def(
        "DetectConcentricCircleMarker3d",
        [](const RVC::Image &image, const RVC::PointMap &pm) {
            std::vector<double> point2d(2000);
            std::vector<double> point3d(3000);
            int markerNums = 0;
            int ret = RVC::DetectConcentricCircleMarker3d(image, pm, &markerNums, point2d.data(), point3d.data());
            return std::make_tuple(ret, markerNums, point2d, point3d);
        },
        call_guard<gil_scoped_release>());

    m.def(
        "GetTwoCameraTransformByCodedCircleMarker",
        [](const RVC::PointMap &pm0, const RVC::Image &img0, const RVC::PointMap &pm1, const RVC::Image &img1,
           const RVC::CodedCircleMarkerType &type) {
            std::vector<double> RVector(9);
            std::vector<double> tVector(3);
            int ret = RVC::GetTwoCameraTransformByCodedCircleMarker(pm0, img0, pm1, img1, type, RVector.data(),
                                                                    tVector.data());

            gil_scoped_acquire acquire;
            pybind11::array_t<double> R({3, 3});
            double *R_ptr = (double *)R.request().ptr;
            for (int i = 0; i < 9; i++) {
                R_ptr[i] = RVector[i];
            }
            pybind11::array_t<double> t(3);
            double *t_ptr = (double *)t.request().ptr;
            for (int i = 0; i < 3; i++) {
                t_ptr[i] = tVector[i];
            }
            return std::make_tuple(ret, R, t);
        },
        call_guard<gil_scoped_release>());

    m.def("TransformPointCloud",
          [](const pybind11::array_t<double> &R, const pybind11::array_t<double> &t, RVC::PointMap &pm) {
              double *R_ptr = (double *)R.request().ptr;
              double *t_ptr = (double *)t.request().ptr;
              {
                  gil_scoped_release release;
                  RVC::TransformPointCloud(R_ptr, t_ptr, pm);
              }
          });

    m.def(
        "TestAccuracy",
        [](const RVC::Image &image, const RVC::PointMap &pointmap, const int caliboard_pattern_size_width,
           const int caliboard_pattern_size_height, const float caliboard_circle_center_standard_3d_distance_step) {
            float measuring_distance = 0;
            float error_percentage = 0;
            int nums = caliboard_pattern_size_width * caliboard_pattern_size_height;
            std::vector<float> circle_center_2d(nums * 2);
            std::vector<float> circle_center_3d(nums * 3);
            int ret = RVC::TestAccuracy(image, pointmap, nullptr, nullptr, caliboard_pattern_size_width,
                                        caliboard_pattern_size_height,
                                        caliboard_circle_center_standard_3d_distance_step, circle_center_2d.data(),
                                        circle_center_3d.data(), measuring_distance, error_percentage);
            return std::make_tuple(ret, circle_center_2d, circle_center_3d, measuring_distance, error_percentage);
        },
        call_guard<gil_scoped_release>());

    m.def(
        "TestAccuracy",
        [](const RVC::Image &image, const RVC::PointMap &pointmap, const std::vector<float> &intrinsic_matrix,
           const std::vector<float> &distortion, const int caliboard_pattern_size_width,
           const int caliboard_pattern_size_height, const float caliboard_circle_center_standard_3d_distance_step) {
            float measuring_distance = 0;
            float error_percentage = 0;
            int nums = caliboard_pattern_size_width * caliboard_pattern_size_height;
            std::vector<float> circle_center_2d(nums * 2);
            std::vector<float> circle_center_3d(nums * 3);
            int ret = RVC::TestAccuracy(image, pointmap, intrinsic_matrix.data(), distortion.data(),
                                        caliboard_pattern_size_width, caliboard_pattern_size_height,
                                        caliboard_circle_center_standard_3d_distance_step, circle_center_2d.data(),
                                        circle_center_3d.data(), measuring_distance, error_percentage);
            return std::make_tuple(ret, circle_center_2d, circle_center_3d, measuring_distance, error_percentage);
        },
        call_guard<gil_scoped_release>());
}
