#include "RVC_C.h"
// #include <iostream>

using namespace RVC;

Image GetImage(CHandle handle) {
    Image ret;
    ret.m_handle = Handle(handle.sid, handle.gid);
    return ret;
}

DepthMap GetDepthMap(CHandle handle) {
    DepthMap ret;
    ret.m_handle = Handle(handle.sid, handle.gid);
    return ret;
}

PointMap GetPointMap(CHandle handle) {
    PointMap ret;
    ret.m_handle = Handle(handle.sid, handle.gid);
    return ret;
}

CorrespondMap GetCorrespondMap(CHandle handle) {
    CorrespondMap ret;
    ret.m_handle = Handle(handle.sid, handle.gid);
    return ret;
}

ConfidenceMap GetConfidenceMap(CHandle handle) {
    ConfidenceMap ret;
    ret.m_handle = Handle(handle.sid, handle.gid);
    return ret;
}

Device GetDevice(CHandle handle) {
    Device ret;
    ret.m_handle = Handle(handle.sid, handle.gid);
    return ret;
}

X1 GetX1(CHandle handle) {
    X1 ret;
    ret.m_handle = Handle(handle.sid, handle.gid);
    return ret;
}

X2 GetX2(CHandle handle) {
    X2 ret;
    ret.m_handle = Handle(handle.sid, handle.gid);
    return ret;
}

Mesh GetMesh(CHandle handle) {
    Mesh ret;
    ret.m_handle = Handle(handle.sid, handle.gid);
    return ret;
}

Size GetSize(CSize size) {
    return Size(size.width, size.height);
}

CSize GetCSize(Size size) {
    CSize ret;
    ret.width = size.width;
    ret.height = size.height;
    return ret;
}

CHandle GetCHandle(Handle handle) {
    CHandle ret;
    ret.sid = handle.sid;
    ret.gid = handle.gid;
    return ret;
}

RVC::ROI GetRoi(CROI roi) {
    RVC::ROI ret;
    ret.x = roi.x;
    ret.y = roi.y;
    ret.width = roi.width;
    ret.height = roi.height;
    return ret;
}

CROI GetCROI(RVC::ROI roi) {
    CROI ret;
    ret.x = roi.x;
    ret.y = roi.y;
    ret.width = roi.width;
    ret.height = roi.height;
    return ret;
}

static RVC::Compensator_FixedMarkers* GetCompensator(CCompensatorHandle h) {
    return reinterpret_cast<RVC::Compensator_FixedMarkers*>(h.sid);
}

EXTERN_DLL char* __stdcall ImageType_ToString(RVC::ImageType::Enum type) {
    return (char*)ImageType::ToString(type);
}

EXTERN_DLL int __stdcall ImageType_GetPixelSize(RVC::ImageType::Enum type) {
    return ImageType::GetPixelSize(type);
}

EXTERN_DLL char* __stdcall PointMapType_ToString(RVC::PointMapType::Enum type) {
    return (char*)PointMapType::ToString(type);
}

EXTERN_DLL bool __stdcall System_Init() {
    return SystemInit();
}

EXTERN_DLL bool __stdcall System_IsInit() {
    return SystemIsInited();
}

EXTERN_DLL void __stdcall System_ShutDown() {
    return SystemShutdown();
}

EXTERN_DLL void __stdcall System_ListDevices(int* pdevices, int len, int& actual_size,
                                             RVC::SystemListDeviceType::Enum opt) {
    if (len >= 100)
        len = 100;
    Device deviceList[100];
    size_t size = 0;
    SystemListDevices(deviceList, len, &size, opt);
    actual_size = size;
    for (int i = 0; i < actual_size && i < len; i++) {
        pdevices[i * 2] = deviceList[i].m_handle.sid;
        pdevices[i * 2 + 1] = deviceList[i].m_handle.gid;
    }
}

EXTERN_DLL bool __stdcall System_FindDevice(char* serialNumber, CHandle& deviceHandle) {
    Device device = SystemFindDevice(serialNumber);
    deviceHandle = GetCHandle(device.m_handle);
    bool ret = device.IsValid();
    return device.IsValid();
}

EXTERN_DLL int __stdcall System_GetLastError() {
    return GetLastError();
}

EXTERN_DLL char* __stdcall System_GetLastErrorMessage() {
    return (char*)GetLastErrorMessage();
}

EXTERN_DLL char* __stdcall System_GetVersion() {
    return (char*)GetVersion();
}

EXTERN_DLL void __stdcall Device_Destroy(CHandle devicehandle) {
    return Device::Destroy(GetDevice(devicehandle));
}

EXTERN_DLL bool __stdcall Device_IsValid(CHandle devicehandle) {
    return GetDevice(devicehandle).IsValid();
}

EXTERN_DLL bool __stdcall Device_IsFirmwareMatch(CHandle devicehandle) {
    return GetDevice(devicehandle).IsFirmwareMatch();
}

EXTERN_DLL bool __stdcall Device_GetDeviceInfo(CHandle devicehandle, RVC::DeviceInfo& pinfo) {
    RVC::DeviceInfo tmp_info;
    auto ret = GetDevice(devicehandle).GetDeviceInfo(&tmp_info);
    pinfo = tmp_info;
    return ret;
}

EXTERN_DLL int __stdcall Device_SetNetworkConfig(CHandle devicehandle, RVC::NetworkDevice d, RVC::NetworkType type,
                                                 char* ip, char* netMask, char* gateway) {
    return GetDevice(devicehandle).SetNetworkConfig(d, type, ip, netMask, gateway);
}

EXTERN_DLL int __stdcall Device_GetNetworkConfig(CHandle devicehandle, RVC::NetworkDevice d, RVC::NetworkType& type,
                                                 char* ip, char* netMask, char* gateway, NetworkDeviceStatus_& status) {
    int tmp_status = 0;
    int ret = GetDevice(devicehandle).GetNetworkConfig(d, &type, ip, netMask, gateway, &tmp_status);
    status = (NetworkDeviceStatus_)tmp_status;
    return ret;
}

EXTERN_DLL int __stdcall Device_AutoConfigureNetwork(CHandle devicehandle) {
    return GetDevice(devicehandle).AutoConfigureNetwork();
}

EXTERN_DLL CHandle __stdcall X1_Create(CHandle deviceHandle, RVC::CameraID id) {
    return GetCHandle(X1::Create(GetDevice(deviceHandle), id).m_handle);
}

EXTERN_DLL void __stdcall X1_Destroy(CHandle x1Handle) {
    return X1::Destroy(GetX1(x1Handle));
}

EXTERN_DLL bool __stdcall X1_IsValid(CHandle x1Handle) {
    bool ret = GetX1(x1Handle).IsValid();
    return ret;
}

EXTERN_DLL bool __stdcall X1_Open(CHandle x1Handle) {
    bool ret = GetX1(x1Handle).Open();
    return ret;
}

EXTERN_DLL void __stdcall X1_Close(CHandle x1Handle) {
    return GetX1(x1Handle).Close();
}

EXTERN_DLL bool __stdcall X1_IsOpen(CHandle x1Handle) {
    return GetX1(x1Handle).IsOpen();
}

EXTERN_DLL bool __stdcall X1_IsPhysicallyConnected(CHandle x1Handle) {
    return GetX1(x1Handle).IsPhysicallyConnected();
}

EXTERN_DLL bool __stdcall X1_Capture(CHandle x1Handle, RVC::X1::CaptureOptions opts) {
    bool ret = GetX1(x1Handle).Capture(opts);
    return ret;
}

EXTERN_DLL bool __stdcall X1_Capture_(CHandle x1Handle) {
    bool ret = GetX1(x1Handle).Capture();
    return ret;
}

EXTERN_DLL bool __stdcall X1_Capture2D(CHandle x1Handle, RVC::X1::CaptureOptions opts) {
    bool ret = GetX1(x1Handle).Capture2D(opts);
    return ret;
}

EXTERN_DLL bool __stdcall X1_Capture2D_(CHandle x1Handle) {
    bool ret = GetX1(x1Handle).Capture2D();
    return ret;
}

EXTERN_DLL bool __stdcall X1_SetBandwidth(CHandle x1Handle, float percent) {
    return GetX1(x1Handle).SetBandwidth(percent);
}

EXTERN_DLL bool __stdcall X1_GetBandwidth(CHandle x1Handle, float& percent) {
    return GetX1(x1Handle).GetBandwidth(percent);
}

EXTERN_DLL bool __stdcall X1_SetCustomTransformation(CHandle x1Handle, RVC::X1::CustomTransformOptions opts) {
    return GetX1(x1Handle).SetCustomTransformation(opts);
}

EXTERN_DLL bool __stdcall X1_GetCustomTransformation(CHandle x1Handle, RVC::X1::CustomTransformOptions& opts) {
    return GetX1(x1Handle).GetCustomTransformation(opts);
}

EXTERN_DLL CHandle __stdcall X1_GetImage(CHandle x1Handle) {
    return GetCHandle(GetX1(x1Handle).GetImage().m_handle);
}

EXTERN_DLL CHandle __stdcall X1_GetDepthMap(CHandle x1Handle) {
    return GetCHandle(GetX1(x1Handle).GetDepthMap().m_handle);
}

EXTERN_DLL CHandle __stdcall X1_GetPointMap(CHandle x1Handle) {
    return GetCHandle(GetX1(x1Handle).GetPointMap().m_handle);
}

EXTERN_DLL CHandle __stdcall X1_GetMesh(CHandle x1Handle) {
    return GetCHandle(GetX1(x1Handle).GetMesh().m_handle);
}

EXTERN_DLL CHandle __stdcall X1_GetConfidenceMap(CHandle x1Handle) {
    return GetCHandle(GetX1(x1Handle).GetConfidenceMap().m_handle);
}

EXTERN_DLL bool __stdcall X1_GetExtrinsicMatrix(CHandle x1Handle, float* matrix) {
    return GetX1(x1Handle).GetExtrinsicMatrix(matrix);
}

EXTERN_DLL bool __stdcall X1_GetIntrinsicParameters(CHandle x1Handle, float* instrinsic_matrix, float* distortion) {
    return GetX1(x1Handle).GetIntrinsicParameters(instrinsic_matrix, distortion);
}

EXTERN_DLL bool __stdcall X1_GetProjectorTemperature(CHandle x1Handle, float& temperature) {
    return GetX1(x1Handle).GetProjectorTemperature(temperature);
}

EXTERN_DLL bool __stdcall X1_GetCameraTemperature(CHandle x1Handle, RVC::CameraTempSelector seletor,
                                                  float& temperature) {
    return GetX1(x1Handle).GetCameraTemperature(seletor, temperature);
}

EXTERN_DLL bool __stdcall X1_SetBalanceRatio(CHandle x1Handle, RVC::BalanceSelector selector, float value) {
    return GetX1(x1Handle).SetBalanceRatio(selector, value);
}

EXTERN_DLL bool __stdcall X1_GetBalanceRatio(CHandle x1Handle, RVC::BalanceSelector selector, float& value) {
    return GetX1(x1Handle).GetBalanceRatio(selector, &value);
}

EXTERN_DLL bool __stdcall X1_GetBalanceRange(CHandle x1Handle, RVC::BalanceSelector selector, float& min_value,
                                             float& max_value) {
    return GetX1(x1Handle).GetBalanceRange(selector, &min_value, &max_value);
}

EXTERN_DLL bool __stdcall X1_AutoWhiteBalance(CHandle x1Handle, int wb_times, RVC::X1::CaptureOptions opts, CROI roi) {
    return GetX1(x1Handle).AutoWhiteBalance(wb_times, opts, GetRoi(roi));
}

EXTERN_DLL bool __stdcall X1_GetExposureTimeRange(CHandle x1Handle, int& min_value, int& max_value) {
    int tmp_min, tmp_max;
    auto ret = GetX1(x1Handle).GetExposureTimeRange(&tmp_min, &tmp_max);
    min_value = tmp_min;
    max_value = tmp_max;
    return ret;
}

EXTERN_DLL bool __stdcall X1_GetGainRange(CHandle x1Handle, float& min_value, float& max_value) {
    float tmp_min, tmp_max;
    auto ret = GetX1(x1Handle).GetGainRange(&tmp_min, &tmp_max);
    min_value = tmp_min;
    max_value = tmp_max;
    return ret;
}

EXTERN_DLL bool __stdcall X1_GetGammaRange(CHandle x1Handle, float& min_value, float& max_value) {
    float tmp_min, tmp_max;
    auto ret = GetX1(x1Handle).GetGammaRange(&tmp_min, &tmp_max);
    min_value = tmp_min;
    max_value = tmp_max;
    return ret;
}

EXTERN_DLL bool __stdcall X1_SaveCaptureOptionParameters(CHandle x1Handle, RVC::X1::CaptureOptions opts) {
    return GetX1(x1Handle).SaveCaptureOptionParameters(opts);
}

EXTERN_DLL bool __stdcall X1_LoadCaptureOptionParameters(CHandle x1Handle, RVC::X1::CaptureOptions& opts) {
    bool ret = GetX1(x1Handle).LoadCaptureOptionParameters(opts);
    return ret;
}

EXTERN_DLL bool __stdcall X1_GetAutoCaptureSetting(CHandle x1Handle, RVC::X1::CaptureOptions& opts, CROI roi) {
    bool ret = GetX1(x1Handle).GetAutoCaptureSetting(opts, GetRoi(roi));
    return ret;
}

EXTERN_DLL bool __stdcall X1_GetAutoHdrCaptureSetting(CHandle x1Handle, RVC::X1::CaptureOptions& opts, CROI roi) {
    bool ret = GetX1(x1Handle).GetAutoHdrCaptureSetting(opts, GetRoi(roi));
    return ret;
}

EXTERN_DLL bool __stdcall X1_GetAutoNoiseRemovalSetting(CHandle x1Handle, RVC::X1::CaptureOptions& opts) {
    bool ret = GetX1(x1Handle).GetAutoNoiseRemovalSetting(opts);
    return ret;
}

EXTERN_DLL bool __stdcall X1_GetAuto2DExposureTime(CHandle x1Handle, RVC::X1::CaptureOptions& opts, CROI roi) {
    bool ret = GetX1(x1Handle).GetAuto2DExposureTime(opts, GetRoi(roi));
    return ret;
}

EXTERN_DLL bool __stdcall X1_LoadSettingFromFile(CHandle x1Handle, char* filename) {
    return GetX1(x1Handle).LoadSettingFromFile(filename);
}

EXTERN_DLL bool __stdcall X1_SaveSettingToFile(CHandle x1Handle, char* filename) {
    return GetX1(x1Handle).SaveSettingToFile(filename);
}

EXTERN_DLL bool __stdcall X1_CheckRoi(CHandle x1Handle, CROI roi) {
    return GetX1(x1Handle).CheckRoi(GetRoi(roi));
}

EXTERN_DLL CROI __stdcall X1_AutoAdjustRoi(CHandle x1Handle, CROI roi) {
    return GetCROI(GetX1(x1Handle).AutoAdjustRoi(GetRoi(roi)));
}

EXTERN_DLL bool __stdcall X1_GetRoiRange(CHandle x1Handle, RVC::ROIRange& range) {
    return GetX1(x1Handle).GetRoiRange(range);
}

EXTERN_DLL bool __stdcall X1_GetCameraResolution(CHandle x1Handle, RVC::Size& size) {
    return GetX1(x1Handle).GetCameraResolution(size);
}

EXTERN_DLL bool __stdcall X1_OpenProtectiveCover(CHandle x1Handle) {
    return GetX1(x1Handle).OpenProtectiveCover();
}

EXTERN_DLL bool __stdcall X1_CloseProtectiveCover(CHandle x1Handle) {
    return GetX1(x1Handle).CloseProtectiveCover();
}

EXTERN_DLL bool __stdcall X1_ResetProtectiveCover(CHandle x1Handle) {
    return GetX1(x1Handle).ResetProtectiveCover();
}

EXTERN_DLL bool __stdcall X1_OpenProtectiveCoverAsync(CHandle x1Handle) {
    return GetX1(x1Handle).OpenProtectiveCoverAsync();
}

EXTERN_DLL bool __stdcall X1_CloseProtectiveCoverAsync(CHandle x1Handle) {
    return GetX1(x1Handle).CloseProtectiveCoverAsync();
}

EXTERN_DLL bool __stdcall X1_GetProtectiveCoverStatus(CHandle x1Handle, ProtectiveCoverStatus& status) {
    return GetX1(x1Handle).GetProtectiveCoverStatus(status);
}

EXTERN_DLL bool __stdcall X1_SetCollectionCallBack(CHandle x1Handle, RVC::X1::CollectionCallBackPtr cb,
                                                   RVC::UserPtr ctx) {
    return GetX1(x1Handle).SetCollectionCallBack(cb, ctx);
}

EXTERN_DLL bool __stdcall X1_SetCalculationCallBack(CHandle x1Handle, RVC::X1::CalculationCallBackPtr cb,
                                                    RVC::UserPtr ctx) {
    return GetX1(x1Handle).SetCalculationCallBack(cb, ctx);
}

EXTERN_DLL bool __stdcall X1_SetCurrentUserSet(CHandle x1Handle, int id) {
    return GetX1(x1Handle).SetCurrentUserSet(id);
}

EXTERN_DLL bool __stdcall X1_GetCurrentUserSet(CHandle x1Handle, int& id) {
    return GetX1(x1Handle).GetCurrentUserSet(id);
}

EXTERN_DLL bool __stdcall X1_SetUserSetName(CHandle x1Handle, int id, char* name) {
    return GetX1(x1Handle).SetUserSetName(id, name);
}

EXTERN_DLL bool __stdcall X1_GetUserSetName(CHandle x1Handle, int id, char* name) {
    return GetX1(x1Handle).GetUserSetName(id, name);
}

EXTERN_DLL bool __stdcall X1_SaveEncodedImagesData(CHandle x1Handle, char* addr) {
    return GetX1(x1Handle).SaveEncodedImagesData(addr);
}

EXTERN_DLL CHandle __stdcall X2_Create(CHandle deviceHandle) {
    return GetCHandle(X2::Create(GetDevice(deviceHandle)).m_handle);
}

EXTERN_DLL void __stdcall X2_Destroy(CHandle x2Handle) {
    return X2::Destroy(GetX2(x2Handle));
}

EXTERN_DLL bool __stdcall X2_IsValid(CHandle x2Handle) {
    return GetX2(x2Handle).IsValid();
}

EXTERN_DLL bool __stdcall X2_Open(CHandle x2Handle) {
    return GetX2(x2Handle).Open();
}

EXTERN_DLL void __stdcall X2_Close(CHandle x2Handle) {
    return GetX2(x2Handle).Close();
}

EXTERN_DLL bool __stdcall X2_IsOpen(CHandle x2Handle) {
    return GetX2(x2Handle).IsOpen();
}

EXTERN_DLL bool __stdcall X2_IsPhysicallyConnected(CHandle x2Handle) {
    return GetX2(x2Handle).IsPhysicallyConnected();
}

EXTERN_DLL bool __stdcall X2_Capture(CHandle x2Handle, RVC::X2::CaptureOptions opts) {
    bool ret = GetX2(x2Handle).Capture(opts);
    return ret;
}

EXTERN_DLL bool __stdcall X2_Capture_(CHandle x2Handle) {
    bool ret = GetX2(x2Handle).Capture();
    return ret;
}

EXTERN_DLL bool __stdcall X2_Capture2D(CHandle x2Handle, RVC::CameraID cid, RVC::X2::CaptureOptions opts) {
    bool ret = GetX2(x2Handle).Capture2D(cid, opts);
    return ret;
}

EXTERN_DLL bool __stdcall X2_Capture2D_(CHandle x2Handle, RVC::CameraID cid) {
    bool ret = GetX2(x2Handle).Capture2D(cid);
    return ret;
}

EXTERN_DLL bool __stdcall X2_SetBandwidth(CHandle x2Handle, float percent) {
    return GetX2(x2Handle).SetBandwidth(percent);
}

EXTERN_DLL bool __stdcall X2_GetBandwidth(CHandle x2Handle, float& percent) {
    return GetX2(x2Handle).GetBandwidth(percent);
}

EXTERN_DLL bool __stdcall X2_SetCustomTransformation(CHandle x2Handle, RVC::X2::CustomTransformOptions opts) {
    return GetX2(x2Handle).SetCustomTransformation(opts);
}

EXTERN_DLL bool __stdcall X2_GetCustomTransformation(CHandle x2Handle, RVC::X2::CustomTransformOptions& opts) {
    return GetX2(x2Handle).GetCustomTransformation(opts);
}

EXTERN_DLL CHandle __stdcall X2_GetImage(CHandle x2Handle, RVC::CameraID cid) {
    return GetCHandle(GetX2(x2Handle).GetImage(cid).m_handle);
}

EXTERN_DLL CHandle __stdcall X2_GetDepthMap(CHandle x2Handle) {
    return GetCHandle(GetX2(x2Handle).GetDepthMap().m_handle);
}

EXTERN_DLL CHandle __stdcall X2_GetPointMap(CHandle x2Handle) {
    return GetCHandle(GetX2(x2Handle).GetPointMap().m_handle);
}

EXTERN_DLL CHandle __stdcall X2_GetMesh(CHandle x2Handle) {
    return GetCHandle(GetX2(x2Handle).GetMesh().m_handle);
}

EXTERN_DLL CHandle __stdcall X2_GetCorrespondMap(CHandle x2Handle) {
    return GetCHandle(GetX2(x2Handle).GetCorrespondMap().m_handle);
}

EXTERN_DLL CHandle __stdcall X2_GetConfidenceMap(CHandle x2Handle) {
    return GetCHandle(GetX2(x2Handle).GetConfidenceMap().m_handle);
}

EXTERN_DLL bool __stdcall X2_GetExtrinsicMatrix(CHandle x2Handle, RVC::CameraID cid, float* matrix) {
    return GetX2(x2Handle).GetExtrinsicMatrix(cid, matrix);
}

EXTERN_DLL bool __stdcall X2_GetIntrinsicParameters(CHandle x2Handle, RVC::CameraID cid, float* instrinsic_matrix,
                                                    float* distortion) {
    return GetX2(x2Handle).GetIntrinsicParameters(cid, instrinsic_matrix, distortion);
}

EXTERN_DLL bool __stdcall X2_GetProjectorTemperature(CHandle x2Handle, float& temperature) {
    return GetX2(x2Handle).GetProjectorTemperature(temperature);
}

EXTERN_DLL bool __stdcall X2_GetCameraTemperature(CHandle x2Handle, RVC::CameraID cid, RVC::CameraTempSelector seletor,
                                                  float& temperature) {
    return GetX2(x2Handle).GetCameraTemperature(cid, seletor, temperature);
}

EXTERN_DLL bool __stdcall X2_AutoWhiteBalance(CHandle x2Handle, int wb_times, RVC::X2::CaptureOptions opts, CROI roi) {
    return GetX2(x2Handle).AutoWhiteBalance(wb_times, opts, GetRoi(roi));
}

EXTERN_DLL bool __stdcall X2_GetExposureTimeRange(CHandle x2Handle, int& min_value, int& max_value) {
    int tmp_min, tmp_max;
    auto ret = GetX2(x2Handle).GetExposureTimeRange(&tmp_min, &tmp_max);
    min_value = tmp_min;
    max_value = tmp_max;
    return ret;
}

EXTERN_DLL bool __stdcall X2_GetGainRange(CHandle x2Handle, float& min_value, float& max_value) {
    float tmp_min, tmp_max;
    auto ret = GetX2(x2Handle).GetGainRange(&tmp_min, &tmp_max);
    min_value = tmp_min;
    max_value = tmp_max;
    return ret;
}

EXTERN_DLL bool __stdcall X2_GetGammaRange(CHandle x2Handle, float& min_value, float& max_value) {
    float tmp_min, tmp_max;
    auto ret = GetX2(x2Handle).GetGammaRange(&tmp_min, &tmp_max);
    min_value = tmp_min;
    max_value = tmp_max;
    return ret;
}

EXTERN_DLL bool __stdcall X2_SaveCaptureOptionParameters(CHandle x2Handle, RVC::X2::CaptureOptions opts) {
    return GetX2(x2Handle).SaveCaptureOptionParameters(opts);
}

EXTERN_DLL bool __stdcall X2_LoadCaptureOptionParameters(CHandle x2Handle, RVC::X2::CaptureOptions& opts) {
    return GetX2(x2Handle).LoadCaptureOptionParameters(opts);
}

EXTERN_DLL bool __stdcall X2_GetAutoCaptureSetting(CHandle x2Handle, RVC::X2::CaptureOptions& opts, CROI roi) {
    return GetX2(x2Handle).GetAutoCaptureSetting(opts, GetRoi(roi));
}

EXTERN_DLL bool __stdcall X2_GetAutoHdrCaptureSetting(CHandle x2Handle, RVC::X2::CaptureOptions& opts, CROI roi) {
    return GetX2(x2Handle).GetAutoHdrCaptureSetting(opts, GetRoi(roi));
}

EXTERN_DLL bool __stdcall X2_GetAutoNoiseRemovalSetting(CHandle x2Handle, RVC::X2::CaptureOptions& opts) {
    return GetX2(x2Handle).GetAutoNoiseRemovalSetting(opts);
}

EXTERN_DLL bool __stdcall X2_GetAuto2DExposureTime(CHandle x2Handle, RVC::X2::CaptureOptions& opts, CROI roi) {
    return GetX2(x2Handle).GetAuto2DExposureTime(opts, GetRoi(roi));
}

EXTERN_DLL bool __stdcall X2_LoadSettingFromFile(CHandle x2Handle, char* filename) {
    return GetX2(x2Handle).LoadSettingFromFile(filename);
}

EXTERN_DLL bool __stdcall X2_SaveSettingToFile(CHandle x2Handle, char* filename) {
    return GetX2(x2Handle).SaveSettingToFile(filename);
}

EXTERN_DLL bool __stdcall X2_CheckRoi(CHandle x2Handle, CROI roi) {
    return GetX2(x2Handle).CheckRoi(GetRoi(roi));
}

EXTERN_DLL CROI __stdcall X2_AutoAdjustRoi(CHandle x2Handle, CROI roi) {
    return GetCROI(GetX2(x2Handle).AutoAdjustRoi(GetRoi(roi)));
}

EXTERN_DLL bool __stdcall X2_GetRoiRange(CHandle x2Handle, RVC::ROIRange& range) {
    return GetX2(x2Handle).GetRoiRange(range);
}

EXTERN_DLL bool __stdcall X2_GetCameraResolution(CHandle x2Handle, RVC::Size& size) {
    return GetX2(x2Handle).GetCameraResolution(size);
}

EXTERN_DLL bool __stdcall X2_GetTimestamp(CHandle x2Handle, uint64_t& timestamp) {
    return GetX2(x2Handle).GetTimestamp(timestamp);
}

EXTERN_DLL bool __stdcall X2_ResetTimestamp(CHandle x2Handle) {
    return GetX2(x2Handle).ResetTimestamp();
}

EXTERN_DLL bool __stdcall X2_StartFixedLineScan(CHandle x2Handle, RVC::X2::CaptureOptions opts) {
    bool ret = GetX2(x2Handle).StartFixedLineScan(opts);
    return ret;
}

EXTERN_DLL bool __stdcall X2_StartFixedLineScan_(CHandle x2Handle) {
    bool ret = GetX2(x2Handle).StartFixedLineScan();
    return ret;
}

EXTERN_DLL CHandle __stdcall X2_GetFixedLineScanPointMap(CHandle x2Handle) {
    return GetCHandle(GetX2(x2Handle).GetFixedLineScanPointMap().m_handle);
}

EXTERN_DLL bool __stdcall X2_StopFixedLineScan(CHandle x2Handle) {
    bool ret = GetX2(x2Handle).StopFixedLineScan();
    return ret;
}

EXTERN_DLL bool __stdcall X2_OpenProtectiveCover(CHandle x2Handle) {
    return GetX2(x2Handle).OpenProtectiveCover();
}

EXTERN_DLL bool __stdcall X2_CloseProtectiveCover(CHandle x2Handle) {
    return GetX2(x2Handle).CloseProtectiveCover();
}

EXTERN_DLL bool __stdcall X2_ResetProtectiveCover(CHandle x2Handle) {
    return GetX2(x2Handle).ResetProtectiveCover();
}

EXTERN_DLL bool __stdcall X2_OpenProtectiveCoverAsync(CHandle x1Handle) {
    return GetX2(x1Handle).OpenProtectiveCoverAsync();
}

EXTERN_DLL bool __stdcall X2_CloseProtectiveCoverAsync(CHandle x1Handle) {
    return GetX2(x1Handle).CloseProtectiveCoverAsync();
}

EXTERN_DLL bool __stdcall X2_GetProtectiveCoverStatus(CHandle x2Handle, ProtectiveCoverStatus& status) {
    return GetX2(x2Handle).GetProtectiveCoverStatus(status);
}

EXTERN_DLL bool __stdcall X2_SetCollectionCallBack(CHandle x2Handle, RVC::X2::CollectionCallBackPtr cb,
                                                   RVC::UserPtr ctx) {
    return GetX2(x2Handle).SetCollectionCallBack(cb, ctx);
}

EXTERN_DLL bool __stdcall X2_SetCalculationCallBack(CHandle x2Handle, RVC::X2::CalculationCallBackPtr cb,
                                                    RVC::UserPtr ctx) {
    return GetX2(x2Handle).SetCalculationCallBack(cb, ctx);
}

EXTERN_DLL bool __stdcall X2_SetFixedLineScanCallback(CHandle x2Handle, RVC::X2::FixedLineScanCallBackPtr cb,
                                                      RVC::UserPtr ctx) {
    return GetX2(x2Handle).SetFixedLineScanCallback(cb, ctx);
}

EXTERN_DLL bool __stdcall X2_SetCurrentUserSet(CHandle x2Handle, int id) {
    return GetX2(x2Handle).SetCurrentUserSet(id);
}

EXTERN_DLL bool __stdcall X2_GetCurrentUserSet(CHandle x2Handle, int& id) {
    return GetX2(x2Handle).GetCurrentUserSet(id);
}

EXTERN_DLL bool __stdcall X2_SetUserSetName(CHandle x2Handle, int id, char* name) {
    return GetX2(x2Handle).SetUserSetName(id, name);
}

EXTERN_DLL bool __stdcall X2_GetUserSetName(CHandle x2Handle, int id, char* name) {
    return GetX2(x2Handle).GetUserSetName(id, name);
}

EXTERN_DLL bool __stdcall X2_SaveEncodedImagesData(CHandle x2Handle, char* addr) {
    return GetX2(x2Handle).SaveEncodedImagesData(addr);
}

EXTERN_DLL CHandle __stdcall Image_Create(RVC::ImageType::Enum it, CSize sz, unsigned char* data, bool own_data) {
    return GetCHandle(Image::Create(it, GetSize(sz), data, own_data).m_handle);
}

EXTERN_DLL CHandle __stdcall Image_CreateFromFile(const char* file) {
    return GetCHandle(Image::CreateFromFile(file).m_handle);
}

EXTERN_DLL void __stdcall Image_Destroy(CHandle imageHandle, bool no_reuse) {
    return Image::Destroy(GetImage(imageHandle), no_reuse);
}

EXTERN_DLL bool __stdcall Image_IsValid(CHandle imageHandle) {
    return GetImage(imageHandle).IsValid();
}

EXTERN_DLL CSize __stdcall Image_GetSize(CHandle imageHandle) {
    return GetCSize(GetImage(imageHandle).GetSize());
}

EXTERN_DLL RVC::ImageType::Enum __stdcall Image_GetType(CHandle imageHandle) {
    return GetImage(imageHandle).GetType();
}

EXTERN_DLL unsigned char* __stdcall Image_GetDataPtr(CHandle imageHandle) {
    return GetImage(imageHandle).GetDataPtr();
}

EXTERN_DLL bool __stdcall Image_SaveImage(CHandle imageHandle, char* addr) {
    return GetImage(imageHandle).SaveImage(addr);
}

EXTERN_DLL uint64_t __stdcall Image_GetTimestamp(CHandle imageHandle) {
    return GetImage(imageHandle).GetTimestamp();
}

EXTERN_DLL bool __stdcall Image_SetTimestamp(CHandle imageHandle, const uint64_t timestamp) {
    return GetImage(imageHandle).SetTimestamp(timestamp);
}

EXTERN_DLL CHandle __stdcall DepthMap_Create(CSize sz, double* data, bool own_data) {
    return GetCHandle(DepthMap::Create(GetSize(sz), data, own_data).m_handle);
}

EXTERN_DLL void __stdcall DepthMap_Destroy(CHandle depthHandle, bool no_reuse) {
    return DepthMap::Destroy(GetDepthMap(depthHandle), no_reuse);
}

EXTERN_DLL bool __stdcall DepthMap_IsValid(CHandle depthHandle) {
    return GetDepthMap(depthHandle).IsValid();
}

EXTERN_DLL CSize __stdcall DepthMap_GetSize(CHandle depthHandle) {
    return GetCSize(GetDepthMap(depthHandle).GetSize());
}

EXTERN_DLL double* __stdcall DepthMap_GetDataPtr(CHandle depthHandle) {
    return GetDepthMap(depthHandle).GetDataPtr();
}

EXTERN_DLL bool __stdcall DepthMap_SaveDepthMap(CHandle depthHandle, char* address, bool is_m) {
    return GetDepthMap(depthHandle).SaveDepthMap(address, is_m);
}

EXTERN_DLL CHandle __stdcall PointMap_Create(RVC::PointMapType::Enum type, CSize size, double* data, bool owndata) {
    return GetCHandle(PointMap::Create(type, GetSize(size), data, owndata).m_handle);
}

EXTERN_DLL CHandle __stdcall PointMap_CreateFromFile(const char* file, CSize size, const RVC::PointMapUnit::Enum unit) {
    return GetCHandle(PointMap::CreateFromFile(file, GetSize(size), unit).m_handle);
}

EXTERN_DLL void __stdcall PointMap_Destroy(CHandle pointMapHandle, bool no_reuse) {
    return PointMap::Destroy(GetPointMap(pointMapHandle), no_reuse);
}

EXTERN_DLL bool __stdcall PointMap_IsValid(CHandle pointMapHandle) {
    return GetPointMap(pointMapHandle).IsValid();
}

EXTERN_DLL CSize __stdcall PointMap_GetSize(CHandle pointMapHandle) {
    return GetCSize(GetPointMap(pointMapHandle).GetSize());
}

EXTERN_DLL double* __stdcall PointMap_GetPointDataPtr(CHandle pointMapHandle) {
    return GetPointMap(pointMapHandle).GetPointDataPtr();
}

EXTERN_DLL double* __stdcall PointMap_GetNormalDataPtr(CHandle pointMapHandle) {
    return GetPointMap(pointMapHandle).GetNormalDataPtr();
}

EXTERN_DLL bool __stdcall PointMap_GetPointMapSeperated(CHandle pointMapHandle, double* x, double* y, double* z,
                                                        double scale) {
    return GetPointMap(pointMapHandle).GetPointMapSeperated(x, y, z, scale);
}

EXTERN_DLL bool __stdcall PointMap_Save(CHandle pointMapHandle, char* filename, RVC::PointMapUnit::Enum unit,
                                        bool isBinary, CHandle imageHandle) {
    return GetPointMap(pointMapHandle).Save(filename, unit, isBinary, GetImage(imageHandle));
}

EXTERN_DLL uint64_t __stdcall PointMap_GetTimestamp(CHandle pointMapHandle) {
    return GetPointMap(pointMapHandle).GetTimestamp();
}

EXTERN_DLL bool __stdcall PointMap_SetTimestamp(CHandle pointMapHandle, const uint64_t timestamp) {
    return GetPointMap(pointMapHandle).SetTimestamp(timestamp);
}

EXTERN_DLL CHandle __stdcall CorrespondMap_Create(CSize sz, double* data, bool own_data) {
    return GetCHandle(CorrespondMap::Create(GetSize(sz), data, own_data).m_handle);
}

EXTERN_DLL void __stdcall CorrespondMap_Destroy(CHandle correspondHandle, bool no_reuse) {
    return CorrespondMap::Destroy(GetCorrespondMap(correspondHandle), no_reuse);
}

EXTERN_DLL bool __stdcall CorrespondMap_IsValid(CHandle correspondHandle) {
    return GetCorrespondMap(correspondHandle).IsValid();
}

EXTERN_DLL CSize __stdcall CorrespondMap_GetSize(CHandle correspondHandle) {
    return GetCSize(GetCorrespondMap(correspondHandle).GetSize());
}

EXTERN_DLL double* __stdcall CorrespondMap_GetDataPtr(CHandle correspondHandle) {
    return GetCorrespondMap(correspondHandle).GetDataPtr();
}

EXTERN_DLL CHandle __stdcall ConfidenceMap_Create(CSize sz, double* data, bool own_data) {
    return GetCHandle(ConfidenceMap::Create(GetSize(sz), data, own_data).m_handle);
}

EXTERN_DLL void __stdcall ConfidenceMap_Destroy(CHandle confidenceHandle, bool no_reuse) {
    return ConfidenceMap::Destroy(GetConfidenceMap(confidenceHandle), no_reuse);
}

EXTERN_DLL bool __stdcall ConfidenceMap_IsValid(CHandle confidenceHandle) {
    return GetConfidenceMap(confidenceHandle).IsValid();
}

EXTERN_DLL CSize __stdcall ConfidenceMap_GetSize(CHandle confidenceHandle) {
    return GetCSize(GetConfidenceMap(confidenceHandle).GetSize());
}

EXTERN_DLL double* __stdcall ConfidenceMap_GetDataPtr(CHandle confidenceHandle) {
    return GetConfidenceMap(confidenceHandle).GetDataPtr();
}


EXTERN_DLL bool __stdcall Mesh_IsValid(CHandle meshHandle) {
    return GetMesh(meshHandle).IsValid();
}

EXTERN_DLL bool __stdcall Mesh_Save(CHandle meshHandle, char* filename, RVC::PointMapUnit::Enum unit) {
    return GetMesh(meshHandle).Save(filename, unit);
}

EXTERN_DLL void __stdcall Mesh_Destroy(CHandle meshHandle, bool no_reuse) {
    return Mesh::Destroy(GetMesh(meshHandle), no_reuse);
}

EXTERN_DLL void __stdcall MarkerDetection_DetectCodedCircleMarker(CHandle imageHandle, RVC::CodedCircleMarkerType type,
                                                                  int& marker_num, int* code, double* x, double* y) {
    RVC::CodedCircleMarker markers[1000];
    RVC::DetectCodedCircleMarker(GetImage(imageHandle), type, &marker_num, markers);
    for (int i = 0; i < marker_num; i++) {
        code[i] = markers[i].code;
        x[i] = markers[i].x;
        y[i] = markers[i].y;
    }
}

EXTERN_DLL int __stdcall MarkerDetection_DetectConcentricCircleMarker2d(CHandle imageHandle, int& marker_num,
                                                                        double* pixel_xy) {
    return RVC::DetectConcentricCircleMarker2d(GetImage(imageHandle), &marker_num, pixel_xy);
}

EXTERN_DLL int __stdcall MarkerDetection_DetectConcentricCircleMarker3d(CHandle imageHandle, CHandle pointMapHandle,
                                                                        int& marker_num, double* pixel_xy,
                                                                        double* point_xyz) {
    return RVC::DetectConcentricCircleMarker3d(GetImage(imageHandle), GetPointMap(pointMapHandle), &marker_num,
                                               pixel_xy, point_xyz);
}

EXTERN_DLL int __stdcall MarkerDetection_TestAccuracy(CHandle image, CHandle pointmap, const float camera_intrinsic[9],
                                                      const float camera_distortion[5],
                                                      const int caliboard_pattern_size_width,
                                                      const int caliboard_pattern_size_height,
                                                      const float caliboard_circle_center_standard_3d_distance_step,
                                                      float* circle_center_2d, float* circle_center_3d,
                                                      float& measuring_distance, float& error_percentage) {
    return RVC::TestAccuracy(GetImage(image), GetPointMap(pointmap), camera_intrinsic, camera_distortion,
                             caliboard_pattern_size_width, caliboard_pattern_size_height,
                             caliboard_circle_center_standard_3d_distance_step, circle_center_2d, circle_center_3d,
                             measuring_distance, error_percentage);
}

EXTERN_DLL int __stdcall PointCloudStitching_GetTwoCameraTransformByCodedCircleMarker(
    CHandle point_map0, CHandle image0, CHandle point_map1, CHandle image1, RVC::CodedCircleMarkerType type,
    double R[9], double t[3]) {
    return RVC::GetTwoCameraTransformByCodedCircleMarker(GetPointMap(point_map0), GetImage(image0),
                                                         GetPointMap(point_map1), GetImage(image1), type, R, t);
}

EXTERN_DLL void __stdcall PointCloudStitching_TransformPointCloud(const double R[9], const double t[3],
                                                                  CHandle point_map) {
    RVC::PointMap point_map_ = GetPointMap(point_map);
    RVC::TransformPointCloud(R, t, point_map_);
}

EXTERN_DLL int __stdcall ExternalColorCamera_GetExternalCameraExtrinsicMatrix(
    CHandle internal_camera_image0, CHandle internal_camera_point_map0,
    const unsigned char* external_camera_image_data0, CHandle internal_camera_image1,
    CHandle internal_camera_point_map1, const unsigned char* external_camera_image_data1,
    CHandle internal_camera_image2, CHandle internal_camera_point_map2,
    const unsigned char* external_camera_image_data2, int external_camera_width, int external_camera_height,
    const float* external_camera_intrinsic_matrix, const float* external_camera_camera_distortion,
    float* external_camera_extrinsic_matrix, double& reprojection_error) {
    RVC::Image internal_camera_image_0 = GetImage(internal_camera_image0);
    RVC::PointMap internal_camera_point_map_0 = GetPointMap(internal_camera_point_map0);
    RVC::Image internal_camera_image_1 = GetImage(internal_camera_image0);
    RVC::PointMap internal_camera_point_map_1 = GetPointMap(internal_camera_point_map0);
    RVC::Image internal_camera_image_2 = GetImage(internal_camera_image0);
    RVC::PointMap internal_camera_point_map_2 = GetPointMap(internal_camera_point_map0);

    return RVC::GetExternalCameraExtrinsicMatrix(
        internal_camera_image_0, internal_camera_point_map_0, external_camera_image_data0, internal_camera_image_1,
        internal_camera_point_map_1, external_camera_image_data1, internal_camera_image_2, internal_camera_point_map_2,
        external_camera_image_data2, external_camera_width, external_camera_height, external_camera_intrinsic_matrix,
        external_camera_camera_distortion, external_camera_extrinsic_matrix, reprojection_error);
}

EXTERN_DLL CHandle __stdcall ExternalColorCamera_GetExternalCameraPointMap(
    CHandle internal_camera_point_map, const int external_camera_width, const int external_camera_height,
    const float* external_camera_intrinsic_matrix, const float* external_camera_camera_distortion,
    const float* external_camera_extrinsic_matrix) {
    RVC::PointMap internal_camera_point_map_ = GetPointMap(internal_camera_point_map);

    return GetCHandle(RVC::GetExternalCameraPointMap(internal_camera_point_map_, external_camera_width,
                                                     external_camera_height, external_camera_intrinsic_matrix,
                                                     external_camera_camera_distortion,
                                                     external_camera_extrinsic_matrix)
                          .m_handle);
}

EXTERN_DLL CCompensatorHandle __stdcall Compensator_Create() {
    auto compensator = new RVC::Compensator_FixedMarkers();
    CCompensatorHandle handle;
    handle.sid = reinterpret_cast<uintptr_t>(compensator);
    handle.gid = 0;
    return handle;
}

EXTERN_DLL int __stdcall Compensator_Initialize(CCompensatorHandle handle, CHandle pm_reference, CHandle img_reference,
                                                int markerType) {
    auto compensator = GetCompensator(handle);
    if (compensator == nullptr)
        return -1;

    auto pm_ref = GetPointMap(pm_reference);
    auto img_ref = GetImage(img_reference);
    // std::cout << "Compensator Address: " << compensator << std::endl;
    // std::cout << "PM Handle: " << pm_reference.sid << std::endl;
    if (!compensator || !pm_ref.IsValid() || !img_ref.IsValid()) {
        return -2;
    }
    return compensator->Initialize(pm_ref, img_ref, markerType);
}

EXTERN_DLL int __stdcall Compensator_Update(CCompensatorHandle handle, CHandle pmHandle, CHandle imgHandle,
                                            double* driftDistance) {
    auto compensator = GetCompensator(handle);
    if (!compensator)
        return -1;

    auto pm = GetPointMap(pmHandle);
    auto img = GetImage(imgHandle);
    if (!pm.IsValid() || !img.IsValid())
        return -2;

    return compensator->Update(pm, img, *driftDistance);
}

EXTERN_DLL int __stdcall Compensator_Apply(CCompensatorHandle handle, CHandle pmHandle) {
    auto compensator = GetCompensator(handle);
    if (!compensator)
        return -1;

    auto pm = GetPointMap(pmHandle);
    if (!pm.IsValid())
        return -2;

    return compensator->Apply(pm);
}

EXTERN_DLL void __stdcall Compensator_Destroy(CCompensatorHandle handle) {
    auto compensator = GetCompensator(handle);
    delete compensator;
}

EXTERN_DLL bool __stdcall Compensator_IsValid(CCompensatorHandle handle) {
    auto compensator = GetCompensator(handle);
    return (compensator != nullptr);
}
