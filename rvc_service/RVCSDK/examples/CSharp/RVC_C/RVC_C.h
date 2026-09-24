// Copyright (c) RVBUST, Inc - All rights reserved.
#pragma once

#include <RVC/RVC.h>
#include <RVC/experimental/ExternalColorCamera.h>
#include <RVC/experimental/MarkerDetection.h>
#include <RVC/experimental/PointCloudCompensator.h>
#include <RVC/experimental/PointCloudStitching.h>

/// @file

#define EXTERN_DLL extern "C" __declspec(dllexport)

extern "C" {
struct CSize {
    /**
     * @brief width or cols
     *
     */
    int width;
    /**
     * @brief height or rows
     *
     */
    int height;
};

struct CHandle {
    int sid;
    int gid;
};

struct CROI {
    int x;
    int y;
    int width;
    int height;
};

/**
 * @brief Compensator handle wrapper for C interface
 */
struct CCompensatorHandle {
    uintptr_t sid;
    uintptr_t gid;
};
}

EXTERN_DLL char* __stdcall ImageType_ToString(RVC::ImageType::Enum type);

EXTERN_DLL int __stdcall ImageType_GetPixelSize(RVC::ImageType::Enum type);

EXTERN_DLL char* __stdcall PointMapType_ToString(RVC::PointMapType::Enum type);

EXTERN_DLL bool __stdcall System_Init();

EXTERN_DLL bool __stdcall System_IsInit();

EXTERN_DLL void __stdcall System_ShutDown();

EXTERN_DLL void __stdcall System_ListDevices(
    int* pdevices, int len, int& actual_size,
    RVC::SystemListDeviceType::Enum opt = RVC::SystemListDeviceType::Enum::All);

EXTERN_DLL bool __stdcall System_FindDevice(char* serialNumber, CHandle& deviceHandle);

EXTERN_DLL int __stdcall System_GetLastError();

EXTERN_DLL char* __stdcall System_GetLastErrorMessage();

EXTERN_DLL char* __stdcall System_GetVersion();

EXTERN_DLL void __stdcall Device_Destroy(CHandle devicehandle);

EXTERN_DLL bool __stdcall Device_IsValid(CHandle devicehandle);

EXTERN_DLL bool __stdcall Device_IsFirmwareMatch(CHandle devicehandle);

EXTERN_DLL void __stdcall Device_Print(CHandle devicehandle);

EXTERN_DLL bool __stdcall Device_GetDeviceInfo(CHandle devicehandle, RVC::DeviceInfo& pinfo);

EXTERN_DLL int __stdcall Device_SetNetworkConfig(CHandle devicehandle, RVC::NetworkDevice d, RVC::NetworkType type,
                                                 char* ip, char* netMask, char* gateway);

EXTERN_DLL int __stdcall Device_GetNetworkConfig(CHandle devicehandle, RVC::NetworkDevice d, RVC::NetworkType& type,
                                                 char* ip, char* netMask, char* gateway,
                                                 RVC::NetworkDeviceStatus_& status);

EXTERN_DLL int __stdcall Device_AutoConfigureNetwork(CHandle devicehandle);

EXTERN_DLL CHandle __stdcall X1_Create(CHandle deviceHandle, RVC::CameraID id);

EXTERN_DLL void __stdcall X1_Destroy(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_IsValid(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_Open(CHandle x1Handle);

EXTERN_DLL void __stdcall X1_Close(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_IsOpen(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_IsPhysicallyConnected(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_Capture(CHandle x1Handle, RVC::X1::CaptureOptions opts);

EXTERN_DLL bool __stdcall X1_Capture_(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_Capture2D(CHandle x1Handle, RVC::X1::CaptureOptions opts);

EXTERN_DLL bool __stdcall X1_Capture2D_(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_SetBandwidth(CHandle x1Handle, float percent);

EXTERN_DLL bool __stdcall X1_GetBandwidth(CHandle x1Handle, float& percent);

EXTERN_DLL bool __stdcall X1_SetCustomTransformation(CHandle x1Handle, RVC::X1::CustomTransformOptions opts);

EXTERN_DLL bool __stdcall X1_GetCustomTransformation(CHandle x1Handle, RVC::X1::CustomTransformOptions& opts);

EXTERN_DLL CHandle __stdcall X1_GetImage(CHandle x1Handle);

EXTERN_DLL CHandle __stdcall X1_GetDepthMap(CHandle x1Handle);

EXTERN_DLL CHandle __stdcall X1_GetPointMap(CHandle x1Handle);

EXTERN_DLL CHandle __stdcall X1_GetMesh(CHandle x1Handle);

EXTERN_DLL CHandle __stdcall X1_GetConfidenceMap(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_GetExtrinsicMatrix(CHandle x1Handle, float* matrix);

EXTERN_DLL bool __stdcall X1_GetIntrinsicParameters(CHandle x1Handle, float* instrinsic_matrix, float* distortion);

EXTERN_DLL bool __stdcall X1_GetProjectorTemperature(CHandle x1Handle, float& temperature);

EXTERN_DLL bool __stdcall X1_GetCameraTemperature(CHandle x1Handle, RVC::CameraTempSelector seletor,
                                                  float& temperature);

EXTERN_DLL bool __stdcall X1_SetBalanceRatio(CHandle x1Handle, RVC::BalanceSelector selector, float value);

EXTERN_DLL bool __stdcall X1_GetBalanceRatio(CHandle x1Handle, RVC::BalanceSelector selector, float& value);

EXTERN_DLL bool __stdcall X1_GetBalanceRange(CHandle x1Handle, RVC::BalanceSelector selector, float& min_value,
                                             float& max_value);

EXTERN_DLL bool __stdcall X1_AutoWhiteBalance(CHandle x1Handle, int wb_times, RVC::X1::CaptureOptions opts, CROI roi);

EXTERN_DLL bool __stdcall X1_GetExposureTimeRange(CHandle x1Handle, int& min_value, int& max_value);

EXTERN_DLL bool __stdcall X1_GetGainRange(CHandle x1Handle, float& min_value, float& max_value);

EXTERN_DLL bool __stdcall X1_GetGammaRange(CHandle x1Handle, float& min_value, float& max_value);

EXTERN_DLL bool __stdcall X1_SaveCaptureOptionParameters(CHandle x1Handle, RVC::X1::CaptureOptions opts);

EXTERN_DLL bool __stdcall X1_LoadCaptureOptionParameters(CHandle x1Handle, RVC::X1::CaptureOptions& opts);

EXTERN_DLL bool __stdcall X1_GetAutoCaptureSetting(CHandle x1Handle, RVC::X1::CaptureOptions& opts, CROI roi);

EXTERN_DLL bool __stdcall X1_GetAutoHdrCaptureSetting(CHandle x1Handle, RVC::X1::CaptureOptions& opts, CROI roi);

EXTERN_DLL bool __stdcall X1_GetAutoNoiseRemovalSetting(CHandle x1Handle, RVC::X1::CaptureOptions& opts);

EXTERN_DLL bool __stdcall X1_GetAuto2DExposureTime(CHandle x1Handle, RVC::X1::CaptureOptions& opts, CROI roi);

EXTERN_DLL bool __stdcall X1_LoadSettingFromFile(CHandle x1Handle, char* filename);

EXTERN_DLL bool __stdcall X1_SaveSettingToFile(CHandle x1Handle, char* filename);

EXTERN_DLL bool __stdcall X1_CheckRoi(CHandle x1Handle, CROI roi);

EXTERN_DLL CROI __stdcall X1_AutoAdjustRoi(CHandle x1Handle, CROI roi);

EXTERN_DLL bool __stdcall X1_GetRoiRange(CHandle x1Handle, RVC::ROIRange& range);

EXTERN_DLL bool __stdcall X1_GetCameraResolution(CHandle x1Handle, RVC::Size& size);

EXTERN_DLL bool __stdcall X1_OpenProtectiveCover(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_CloseProtectiveCover(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_ResetProtectiveCover(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_OpenProtectiveCoverAsync(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_CloseProtectiveCoverAsync(CHandle x1Handle);

EXTERN_DLL bool __stdcall X1_GetProtectiveCoverStatus(CHandle x1Handle, RVC::ProtectiveCoverStatus& status);

EXTERN_DLL bool __stdcall X1_SetCollectionCallBack(CHandle x1Handle, RVC::X1::CollectionCallBackPtr cb,
                                                   RVC::UserPtr ctx);

EXTERN_DLL bool __stdcall X1_SetCalculationCallBack(CHandle x1Handle, RVC::X1::CalculationCallBackPtr cb,
                                                    RVC::UserPtr ctx);

EXTERN_DLL bool __stdcall X1_SetCurrentUserSet(CHandle x1Handle, int id);

EXTERN_DLL bool __stdcall X1_GetCurrentUserSet(CHandle x1Handle, int& id);

EXTERN_DLL bool __stdcall X1_SetUserSetName(CHandle x1Handle, int id, char* name);

EXTERN_DLL bool __stdcall X1_GetUserSetName(CHandle x1Handle, int id, char* name);

EXTERN_DLL bool __stdcall X1_SaveEncodedImagesData(CHandle x1Handle, char* addr);

EXTERN_DLL CHandle __stdcall X2_Create(CHandle deviceHandle);

EXTERN_DLL void __stdcall X2_Destroy(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_IsValid(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_Open(CHandle x2Handle);

EXTERN_DLL void __stdcall X2_Close(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_IsOpen(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_IsPhysicallyConnected(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_Capture(CHandle x2Handle, RVC::X2::CaptureOptions opts);

EXTERN_DLL bool __stdcall X2_Capture_(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_Capture2D(CHandle x2Handle, RVC::CameraID cid, RVC::X2::CaptureOptions opts);

EXTERN_DLL bool __stdcall X2_Capture2D_(CHandle x2Handle, RVC::CameraID cid);

EXTERN_DLL bool __stdcall X2_SetBandwidth(CHandle x2Handle, float percent);

EXTERN_DLL bool __stdcall X2_GetBandwidth(CHandle x2Handle, float& percent);

EXTERN_DLL bool __stdcall X2_SetCustomTransformation(CHandle x2Handle, RVC::X2::CustomTransformOptions opts);

EXTERN_DLL bool __stdcall X2_GetCustomTransformation(CHandle x2Handle, RVC::X2::CustomTransformOptions& opts);

EXTERN_DLL CHandle __stdcall X2_GetPointMap(CHandle x2Handle);

EXTERN_DLL CHandle __stdcall X2_GetMesh(CHandle x2Handle);

EXTERN_DLL CHandle __stdcall X2_GetImage(CHandle x2Handle, RVC::CameraID cid);

EXTERN_DLL CHandle __stdcall X2_GetDepthMap(CHandle x2Handle);

EXTERN_DLL CHandle __stdcall X2_GetConfidenceMap(CHandle x2Handle);

EXTERN_DLL CHandle __stdcall X2_GetCorrespondMap(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_GetExtrinsicMatrix(CHandle x2Handle, RVC::CameraID cid, float* matrix);

EXTERN_DLL bool __stdcall X2_GetIntrinsicParameters(CHandle x2Handle, RVC::CameraID cid, float* instrinsicMatrix,
                                                    float* distortion);

EXTERN_DLL bool __stdcall X2_GetProjectorTemperature(CHandle x2Handle, float& temperature);

EXTERN_DLL bool __stdcall X2_GetCameraTemperature(CHandle x2Handle, RVC::CameraID cid, RVC::CameraTempSelector seletor,
                                                  float& temperature);

EXTERN_DLL bool __stdcall X2_AutoWhiteBalance(CHandle x2Handle, int wb_times, RVC::X2::CaptureOptions opts, CROI roi);

EXTERN_DLL bool __stdcall X2_GetExposureTimeRange(CHandle x2Handle, int& min_value, int& max_value);

EXTERN_DLL bool __stdcall X2_GetGainRange(CHandle x2Handle, float& min_value, float& max_value);

EXTERN_DLL bool __stdcall X2_GetGammaRange(CHandle x2Handle, float& min_value, float& max_value);

EXTERN_DLL bool __stdcall X2_SaveCaptureOptionParameters(CHandle x2Handle, RVC::X2::CaptureOptions opts);

EXTERN_DLL bool __stdcall X2_LoadCaptureOptionParameters(CHandle x2Handle, RVC::X2::CaptureOptions& opts);

EXTERN_DLL bool __stdcall X2_GetAutoCaptureSetting(CHandle x2Handle, RVC::X2::CaptureOptions& opts, CROI roi);

EXTERN_DLL bool __stdcall X2_GetAutoHdrCaptureSetting(CHandle x2Handle, RVC::X2::CaptureOptions& opts, CROI roi);

EXTERN_DLL bool __stdcall X2_GetAutoNoiseRemovalSetting(CHandle x2Handle, RVC::X2::CaptureOptions& opts);

EXTERN_DLL bool __stdcall X2_GetAuto2DExposureTime(CHandle x2Handle, RVC::X2::CaptureOptions& opts, CROI roi);

EXTERN_DLL bool __stdcall X2_LoadSettingFromFile(CHandle x2Handle, char* filename);

EXTERN_DLL bool __stdcall X2_SaveSettingToFile(CHandle x2Handle, char* filename);

EXTERN_DLL bool __stdcall X2_CheckRoi(CHandle x2Handle, CROI roi);

EXTERN_DLL CROI __stdcall X2_AutoAdjustRoi(CHandle x2Handle, CROI roi);

EXTERN_DLL bool __stdcall X2_GetRoiRange(CHandle x2Handle, RVC::ROIRange& range);

EXTERN_DLL bool __stdcall X2_GetCameraResolution(CHandle x2Handle, RVC::Size& size);

EXTERN_DLL bool __stdcall X2_StartFixedLineScan(CHandle x2Handle, RVC::X2::CaptureOptions opts);

EXTERN_DLL bool __stdcall X2_GetTimestamp(CHandle x2Handle, uint64_t& timestamp);

EXTERN_DLL bool __stdcall X2_ResetTimestamp(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_StartFixedLineScan_(CHandle x2Handle);

EXTERN_DLL CHandle __stdcall X2_GetFixedLineScanPointMap(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_StopFixedLineScan(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_OpenProtectiveCover(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_CloseProtectiveCover(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_ResetProtectiveCover(CHandle x2Handle);

EXTERN_DLL bool __stdcall X2_OpenProtectiveCoverAsync(CHandle x1Handle);

EXTERN_DLL bool __stdcall X2_CloseProtectiveCoverAsync(CHandle x1Handle);

EXTERN_DLL bool __stdcall X2_GetProtectiveCoverStatus(CHandle x2Handle, RVC::ProtectiveCoverStatus& status);

EXTERN_DLL bool __stdcall X2_SetCollectionCallBack(CHandle x2Handle, RVC::X2::CollectionCallBackPtr cb,
                                                   RVC::UserPtr ctx);

EXTERN_DLL bool __stdcall X2_SetCalculationCallBack(CHandle x2Handle, RVC::X2::CalculationCallBackPtr cb,
                                                    RVC::UserPtr ctx);

EXTERN_DLL bool __stdcall X2_SetCurrentUserSet(CHandle x2Handle, int id);

EXTERN_DLL bool __stdcall X2_GetCurrentUserSet(CHandle x2Handle, int& id);

EXTERN_DLL bool __stdcall X2_SetUserSetName(CHandle x2Handle, int id, char* name);

EXTERN_DLL bool __stdcall X2_GetUserSetName(CHandle x2Handle, int id, char* name);

EXTERN_DLL bool __stdcall X2_SetFixedLineScanCallback(CHandle x2Handle, RVC::X2::FixedLineScanCallBackPtr cb,
                                                      RVC::UserPtr ctx);

EXTERN_DLL bool __stdcall X2_SaveEncodedImagesData(CHandle x2Handle, char* addr);

EXTERN_DLL CHandle __stdcall Image_Create(RVC::ImageType::Enum it, CSize sz, unsigned char* data, bool own_data = true);

EXTERN_DLL void __stdcall Image_Destroy(CHandle imageHandle, bool no_reuse = true);

EXTERN_DLL bool __stdcall Image_IsValid(CHandle imageHandle);

EXTERN_DLL CSize __stdcall Image_GetSize(CHandle imageHandle);

EXTERN_DLL RVC::ImageType::Enum __stdcall Image_GetType(CHandle imageHandle);

EXTERN_DLL unsigned char* __stdcall Image_GetDataPtr(CHandle imageHandle);

EXTERN_DLL bool __stdcall Image_SaveImage(CHandle imageHandle, char* addr);

EXTERN_DLL uint64_t __stdcall Image_GetTimestamp(CHandle imageHandle);

EXTERN_DLL bool __stdcall Image_SetTimestamp(CHandle imageHandle, const uint64_t timestamp);

EXTERN_DLL CHandle __stdcall DepthMap_Create(CSize sz, double* data, bool own_data = true);

EXTERN_DLL void __stdcall DepthMap_Destroy(CHandle depthHandle, bool no_reuse = true);

EXTERN_DLL bool __stdcall DepthMap_IsValid(CHandle depthHandle);

EXTERN_DLL CSize __stdcall DepthMap_GetSize(CHandle depthHandle);

EXTERN_DLL double* __stdcall DepthMap_GetDataPtr(CHandle depthHandle);

EXTERN_DLL bool __stdcall DepthMap_SaveDepthMap(CHandle depthHandle, char* address, bool is_m = true);

EXTERN_DLL CHandle __stdcall PointMap_Create(RVC::PointMapType::Enum type, CSize size, double* data,
                                             bool owndata = true);

EXTERN_DLL CHandle __stdcall PointMap_CreateFromFile(const char* file, CSize size, const RVC::PointMapUnit::Enum unit);

EXTERN_DLL void __stdcall PointMap_Destroy(CHandle pointMapHandle, bool no_reuse = true);

EXTERN_DLL bool __stdcall PointMap_IsValid(CHandle pointMapHandle);

EXTERN_DLL CSize __stdcall PointMap_GetSize(CHandle pointMapHandle);

EXTERN_DLL double* __stdcall PointMap_GetPointDataPtr(CHandle pointMapHandle);

EXTERN_DLL double* __stdcall PointMap_GetNormalDataPtr(CHandle pointMapHandle);

EXTERN_DLL bool __stdcall PointMap_GetPointMapSeperated(CHandle pointMapHandle, double* x, double* y, double* z,
                                                        double scale = 1.0);

EXTERN_DLL bool __stdcall PointMap_Save(CHandle pointMapHandle, char* filename, RVC::PointMapUnit::Enum unit,
                                        bool isBinary, CHandle imageHandle);

EXTERN_DLL uint64_t __stdcall PointMap_GetTimestamp(CHandle pointMapHandle);

EXTERN_DLL bool __stdcall PointMap_SetTimestamp(CHandle pointMapHandle, const uint64_t timestamp);

EXTERN_DLL CHandle __stdcall CorrespondMap_Create(CSize sz, double* data, bool own_data = true);

EXTERN_DLL void __stdcall CorrespondMap_Destroy(CHandle correspondMapHandle, bool no_reuse = true);

EXTERN_DLL bool __stdcall CorrespondMap_IsValid(CHandle correspondMapHandle);

EXTERN_DLL CSize __stdcall CorrespondMap_GetSize(CHandle correspondMapHandle);

EXTERN_DLL double* __stdcall CorrespondMap_GetDataPtr(CHandle correspondMapHandle);

EXTERN_DLL CHandle __stdcall ConfidenceMap_Create(CSize sz, double* data, bool own_data = true);

EXTERN_DLL void __stdcall ConfidenceMap_Destroy(CHandle confidenceHandle, bool no_reuse = true);

EXTERN_DLL bool __stdcall ConfidenceMap_IsValid(CHandle confidenceHandle);

EXTERN_DLL CSize __stdcall ConfidenceMap_GetSize(CHandle confidenceHandle);

EXTERN_DLL double* __stdcall ConfidenceMap_GetDataPtr(CHandle confidenceHandle);

EXTERN_DLL bool __stdcall Mesh_IsValid(CHandle meshHandle);

EXTERN_DLL bool __stdcall Mesh_Save(CHandle meshHandle, char* filename, RVC::PointMapUnit::Enum unit);

EXTERN_DLL void __stdcall Mesh_Destroy(CHandle meshHandle, bool no_reuse = true);

EXTERN_DLL void __stdcall MarkerDetection_DetectCodedCircleMarker(CHandle imageHandle, RVC::CodedCircleMarkerType type,
                                                                  int& marker_num, int* code, double* x, double* y);

EXTERN_DLL int __stdcall MarkerDetection_DetectConcentricCircleMarker2d(CHandle imageHandle, int& marker_num,
                                                                        double* pixel_xy);

EXTERN_DLL int __stdcall MarkerDetection_DetectConcentricCircleMarker3d(CHandle imageHandle, CHandle pointMapHandle,
                                                                        int& marker_num, double* pixel_xy,
                                                                        double* point_xyz);

EXTERN_DLL int __stdcall MarkerDetection_TestAccuracy(CHandle image, CHandle pointMap, const float camera_intrinsic[9],
                                                      const float camera_distortion[5],
                                                      const int caliboard_pattern_size_width,
                                                      const int caliboard_pattern_size_height,
                                                      const float caliboard_circle_center_standard_3d_distance_step,
                                                      float* circle_center_2d, float* circle_center_3d,
                                                      float& measuring_distance, float& error_percentage);

EXTERN_DLL int __stdcall PointCloudStitching_GetTwoCameraTransformByCodedCircleMarker(
    CHandle point_map0, CHandle image0, CHandle point_map1, CHandle image1, RVC::CodedCircleMarkerType type,
    double R[9], double t[3]);

EXTERN_DLL void __stdcall PointCloudStitching_TransformPointCloud(const double R[9], const double t[3],
                                                                  CHandle point_map);

EXTERN_DLL int __stdcall ExternalColorCamera_GetExternalCameraExtrinsicMatrix(
    CHandle internal_camera_image0, CHandle internal_camera_point_map0,
    const unsigned char* external_camera_image_data0, CHandle internal_camera_image1,
    CHandle internal_camera_point_map1, const unsigned char* external_camera_image_data1,
    CHandle internal_camera_image2, CHandle internal_camera_point_map2,
    const unsigned char* external_camera_image_data2, int external_camera_width, int external_camera_height,
    const float* external_camera_intrinsic_matrix, const float* external_camera_camera_distortion,
    float* external_camera_extrinsic_matrix, double& reprojection_error);

EXTERN_DLL CHandle __stdcall ExternalColorCamera_GetExternalCameraPointMap(
    CHandle internal_camera_point_map, const int external_camera_width, const int external_camera_height,
    const float* external_camera_intrinsic_matrix, const float* external_camera_camera_distortion,
    const float* external_camera_extrinsic_matrix);

//=================================================
// PointCloudCompensator C Interface
//=================================================
EXTERN_DLL CCompensatorHandle __stdcall Compensator_Create();

EXTERN_DLL void __stdcall Compensator_Destroy(CCompensatorHandle handle);

EXTERN_DLL int __stdcall Compensator_Initialize(CCompensatorHandle handle, CHandle pm_reference, CHandle img_reference,
                                                int markerType);

EXTERN_DLL int __stdcall Compensator_Update(CCompensatorHandle handle, CHandle pm, CHandle img, double* driftDistance);

EXTERN_DLL int __stdcall Compensator_Apply(CCompensatorHandle handle, CHandle pm);

EXTERN_DLL bool __stdcall Compensator_IsValid(CCompensatorHandle handle);
