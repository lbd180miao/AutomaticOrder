// Copyright (c) RVBUST, Inc - All rights reserved.
#pragma once

#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <string>
#include <vector>

// Define EXPORTED for any platform
#if defined _WIN32 || defined __CYGWIN__
#ifdef RVC_WIN_EXPORT
#ifdef __GNUC__
#define RVC_EXPORT __attribute__((dllexport))
#else
#define RVC_EXPORT __declspec(dllexport)  // Note: actually gcc seems to also supports this syntax.
#endif
#else
#ifdef __GNUC__
#define RVC_EXPORT __attribute__((dllimport))
#else
#define RVC_EXPORT __declspec(dllimport)  // Note: actually gcc seems to also supports this syntax.
#endif
#endif
#define RVC_NOT_EXPORT
#else
#if __GNUC__ >= 4
#define RVC_EXPORT __attribute__((visibility("default")))
#define RVC_NOT_EXPORT __attribute__((visibility("hidden")))
#else
#define RVC_EXPORT
#define RVC_NOT_EXPORT
#endif
#endif

/**
 * @brief RVC namespace
 *
 */
namespace RVC {
/**
 * @brief Handle id 4 bytes long
 *
 */
typedef uint32_t HandleID;
/**
 * @brief RVC Handle
 *
 */
struct RVC_EXPORT Handle {
    /**
     * @brief Construct a new Handle object
     *
     */
    Handle() : sid(0), gid(0) {}
    /**
     * @brief Construct a new Handle object with sid and gid
     *
     * @param sid_
     * @param gid_
     */
    Handle(HandleID sid_, HandleID gid_) : sid(sid_), gid(gid_) {}
    /**
     * @brief Construct a new Handle object with another Handle
     *
     * @param rhs Another Handle
     */
    Handle(const Handle &rhs) : sid(rhs.sid), gid(rhs.gid) {}
    /**
     * @brief Assigns new Object to the Handle object,
     * replace its current parameters.
     *
     * @param rhs A Handle object of the same type
     * @return Handle& *this
     */
    Handle &operator=(const Handle &rhs) {
        sid = rhs.sid;
        gid = rhs.gid;
        return *this;
    }
    /**
     * @brief Compare with another Handle object
     *
     * @param rhs Another Handle object
     * @return true Equal
     * @return false Not equal
     */
    inline bool operator==(const Handle &rhs) { return sid == rhs.sid && gid == rhs.gid; }
    /**
     * @brief Compare with another Handle object
     *
     * @param rhs Another Handle object
     * @return true Not equal
     * @return false Equal
     */
    inline bool operator!=(const Handle &rhs) { return sid != rhs.sid || gid != rhs.gid; }

    HandleID sid;
    HandleID gid;
};

/**
 * @brief Image/PointMap Size
 *
 */
struct RVC_EXPORT Size {
    /**
     * @brief Construct a new Image/PointMap Size object
     *
     */
    Size() : width(0), height(0) {}
    /**
     * @brief Construct a new Image/PointMap Size object with width/cols and height/rows
     *
     * @param w Image width/PointMap cols
     * @param h Image height/PointMap rows
     */
    Size(int w, int h) : width(w), height(h) {}
    /**
     * @brief width or cols
     *
     */
    union {
        int32_t width, cols;
    };
    /**
     * @brief height or rows
     *
     */
    union {
        int32_t height, rows;
    };
};

/**
 * @brief Compare two Image size
 *
 * @param lhs one Image Size
 * @param rhs another Image Size
 * @return true equal
 * @return false not equal
 */
inline bool operator==(const Size &lhs, const Size &rhs) {
    return lhs.width == rhs.width && lhs.height == rhs.height;
}
/**
 * @brief Compare two Image size
 *
 * @param lhs one Image Size
 * @param rhs another Image Size
 * @return true not equal
 * @return false equal
 */
inline bool operator!=(const Size &lhs, const Size &rhs) {
    return lhs.width != rhs.width || lhs.height != rhs.height;
}

/**
 * @brief Image ROI
 *
 */
struct RVC_EXPORT ROI {
    /**
     * @brief Construct a new Image ROI object
     *
     */
    ROI() : x(0), y(0), width(0), height(0) {}
    /**
     * @brief Construct a new Image ROI object with x,y,w,h
     *
     * @param x start x of Image roi (col index of roi up left corner)
     * @param y start y of Image roi (row index of roi up left corner)
     * @param w image roi width
     * @param h image roi height
     */
    ROI(int x, int y, int w, int h) : x(x), y(y), width(w), height(h) {}
    /**
     * @brief start x of Image roi (col index of roi up left corner)
     *
     */
    int x;
    /**
     * @brief start y of Image roi (row index of roi up left corner)
     *
     */
    int y;
    /**
     * @brief Image roi width
     *
     */
    int width;
    /**
     * @brief Image roi height
     *
     */
    int height;
};

/**
 * @brief Device ROIRange
 *
 */
struct RVC_EXPORT ROIRange {
    /**
     * @brief step of x of Image roi (col index of roi up left corner)
     *
     */
    int x_step;
    /**
     * @brief step of y of Image roi (row index of roi up left corner)
     *
     */
    int y_step;
    /**
     * @brief step of width of Image roi
     *
     */
    int width_step;
    /**
     * @brief step of height of Image roi
     *
     */
    int height_step;
    /**
     * @brief Minimum value of width of Image roi
     *
     */
    int width_min;
    /**
     * @brief Minimum value of height of Image roi
     *
     */
    int height_min;
    /**
     * @brief Maximum value of width of Image roi
     *
     */
    int width_max;
    /**
     * @brief Maximum value of height of Image roi
     *
     */
    int height_max;
};

/**
 * @brief Compare two Image ROI
 *
 * @param lhs one Image roi
 * @param rhs another Image roi
 * @return true equal
 * @return false  not equal
 */
inline bool operator==(const ROI &lhs, const ROI &rhs) {
    return lhs.width == rhs.width && lhs.height == rhs.height && lhs.x == rhs.x && lhs.y == rhs.y;
}

/**
 * @brief Compare two Image roi
 *
 * @param lhs one Image roi
 * @param rhs another Image roi
 * @return true equal
 * @return false not equal
 */
inline bool operator!=(const ROI &lhs, const ROI &rhs) {
    return lhs.width != rhs.width || lhs.height != rhs.height || lhs.x != rhs.x || lhs.y != rhs.y;
}
/**
 * @brief Image Type
 *
 *  All support type are *Mono8*, *RGB8*, *BGR8*
 */
struct RVC_EXPORT ImageType {
    enum Enum {
        None = 0,
        Mono8 = 1,
        RGB8 = 2,
        BGR8 = 3,
    };
    /**
     * @brief Print given ImageType
     *
     * @param type ImageType
     * @return const char* Name of ImageType
     */
    static const char *ToString(ImageType::Enum type);
    /**
     * @brief Get pixel size of ImageType
     *
     * @param type ImageType
     * @return size_t Pixel size
     */
    static size_t GetPixelSize(ImageType::Enum type);
};

/**
 * @brief RVC X Image object
 *
 */
struct RVC_EXPORT Image {
    /**
     * @brief Create Image object
     *
     * @param it image type
     * @param sz image size
     * @param data image data
     * @param own_data Image object
     * @return Image A Image object with given parameters
     */
    static Image Create(ImageType::Enum it, const Size sz, unsigned char *data = nullptr, bool own_data = true);
    static Image CreateFromFile(const char *addr);
    /**
     * @brief Destroy Image object
     *
     * @param img Image object will be destroyed
     * @param no_reuse True for reuse current space of PointMap
     */
    static void Destroy(Image img, bool no_reuse = true);
    /**
     * @brief Deep clone Image object
     */
    Image Clone() const;
    /**
     * @brief Check Image obejct is Valid or not.
     *
     * @return true Valid
     * @return false Not valid
     */
    bool IsValid() const;
    /**
     * @brief Get the Image Size object
     *
     * @return Size A Image Size object
     */
    Size GetSize() const;
    /**
     * @brief Get the ImageType object
     *
     * @return ImageType Image type
     */
    ImageType::Enum GetType() const;
    /**
     * @brief Get the Data Ptr of Image object
     *
     * @return unsigned* Data Ptr
     */
    unsigned char *GetDataPtr() const;
    /**
     * @brief Get the Data Const Ptr of Image object
     *
     * @return const unsigned* Data Ptr
     */
    const unsigned char *GetDataConstPtr() const;
    /**
     * @brief Save Image to file
     *
     * @param address save address
     *
     * @return true Success
     * @return false Failed
     */
    bool SaveImage(const char *addr) const;
    /**
     * @brief Retrieves the timestamp of the Image
     *
     * Returns the timestamp value representing the acquisition time
     * of the image data. The timestamp is measured in
     * microseconds (us).
     *
     * @return uint64_t Timestamp value in microseconds (us)
     */
    uint64_t GetTimestamp() const;

    /**
     * @brief Sets the timestamp for the Image
     *
     * Updates the timestamp value associated with the Image data.
     * The timestamp should represent the acquisition time of the image data
     * and must be provided in microseconds (us).
     *
     * @param timestamp Timestamp value in microseconds (us) to be set
     * @return bool True if the timestamp was successfully set, false otherwise
     */
    bool SetTimestamp(const uint64_t timestamp);
    /**
     * @brief RVC Handle
     *
     */
    Handle m_handle;
};

/**
 * @brief RVC X DepthMap
 *
 */
struct RVC_EXPORT DepthMap {
    /**
     * @brief Create DepthMap object
     *
     * @param sz depthmap size
     * @param data depthmap data
     * @param own_data depthmap data
     * @return DepthMap object with given parameters
     */
    static DepthMap Create(const Size sz, double *data = nullptr, bool own_data = true);

    /**
     * @brief Destroy DepthMap object
     *
     * @param depthmap DepthMap object will be destroyed
     * @param no_reuse True for reuse current space of PointMap
     */
    static void Destroy(DepthMap depthmap, bool no_reuse = true);

    /**
     * @brief Check DepthMap obejct is Valid or not.
     *
     * @return true
     * @return false
     */
    bool IsValid();
    /**
     * @brief Get the DepthMap Size object
     *
     * @return Size
     */
    Size GetSize();
    /**
     * @brief Get the Data Ptr of DepthMap
     *
     * @return double* Data Ptr
     */
    double *GetDataPtr();
    /**
     * @brief Get the Data Const Ptr of DepthMap
     *
     * @return const double* Data Ptr
     */
    const double *GetDataConstPtr();

    /**
     * @brief Save DepthMap to file
     *
     * @param address save address
     * @param is_m  save depthmap with m/mm
     *
     * @return true Success
     * @return false Failed
     */
    bool SaveDepthMap(const char *address, bool is_m = true);

    /**
     * @brief DepthMap Handle
     *
     */
    Handle m_handle;
};

struct RVC_EXPORT ConfidenceMap {
    /**
     * @brief create confidence map object, if object is no used, call Destroy to destroy it
     *
     * @param sz confidence map size
     * @param data confidence map data
     * @param own_data own data flag
     * @return ConfidenceMap object with given parameters
     * @sa ConfidenceMap::Destroy
     */
    static ConfidenceMap Create(const Size sz, double *data = nullptr, bool own_data = true);

    /**
     * @brief Destroy confidence map object.
     *
     * @param confidencemap confidencemap to be destroy
     * @param no_reuse True for reuse current space of confidence map
     */
    static void Destroy(ConfidenceMap confidencemap, bool no_reuse = true);

    /**
     * @brief Check obejct is Valid or not.
     *
     * @return true
     * @return false
     */
    bool IsValid();

    /**
     * @brief Get the Size object
     *
     * @return Size
     */
    Size GetSize();
    /**
     * @brief Get the Data Ptr object
     *
     * @return double*
     */
    double *GetDataPtr();
    /**
     * @brief Get the Data Const Ptr object
     *
     * @return const double*
     */
    const double *GetDataConstPtr();

    /**
     * @brief confidence map handle
     *
     */
    Handle m_handle;
};

/**
 * @brief RVC X PointMap Type
 *
 */
struct RVC_EXPORT PointMapType {
    /**
     * @brief PointMap Type Support type *PointsOnly* and *PointsNormals*
     * @param PointsOnly which only contains points
     * @param PointsNormals which contains points with normals
     */
    enum Enum {
        None = 0,
        PointsOnly = 1,
        PointsNormals = 2,
    };
    /**
     * @brief print PointMap Type`s name
     *
     * @param e Pointmap Type
     * @return const char* Pointmap Type`s name
     */
    static const char *ToString(enum Enum e);
};

struct RVC_EXPORT PointMapUnit {
    /**
     * @brief Unit support *Meter* and *Millimeter*
     */
    enum Enum {
        Meter = 0,
        Millimeter = 1,
    };
    /**
     * @brief print PointMapUnit's name
     * @param e PointMapUnit
     * @return string
     */
    static const char *ToString(Enum e);
};

/**
 * @brief RVC X PointMap
 *
 */
struct RVC_EXPORT PointMap {
    /**
     * @brief Create PointMap object
     *
     * @param pmt PointMapType
     * @param size PointMap Size
     * @param data PointMap data (m)
     * @param owndata True for malloc a new space for PointMap
     * @return PointMap A PointMap object
     */
    static PointMap Create(PointMapType::Enum pmt, const Size size, double *data = nullptr, bool owndata = true);
    /**
     * @brief Create PointMap object from file. Only support the *.ply* format.
     * If actual number of points in the point cloud is not equal to sz.width * sz.height, the function will return an
     * invalid pointmap. If point cloud unit in the file is millimeter, the point cloud data will be divided by 1000.
     * @param fileName Name of file to be loaded.
     * @param sz Size of the point cloud.
     * @param unit The unit of the point cloud data in the file.
     */
    static PointMap CreateFromFile(const char *fileName, const Size sz, const PointMapUnit::Enum unit);
    /**
     * @brief Destroy a PointMap object
     *
     * @param pm PointMap object will be destroyed
     * @param no_reuse True for reuse current space of PointMap
     */
    static void Destroy(PointMap pm, bool no_reuse = true);
    /**
     * @brief export PointMap's data to local file. Only support the *.ply* format.
     * @param fileName Name of file to be created.
     * @param unit The unit of exported data. If save unit is millimeter, the point cloud data will be multiplied by
     * 1000.
     * @param isBinary Whether to export to binary format.
     * @return bool.
     */
    bool Save(const char *fileName, const PointMapUnit::Enum unit, const bool isBinary,
              const Image &rawImage = Image());
    /**
     * @brief Check PointMap is Valid or not
     *
     * @return true Valid
     * @return false Not valid
     */
    bool IsValid() const;
    /**
     * @brief Get the PointMap Size object
     *
     * @return Size PointMap Size
     */
    Size GetSize() const;
    /**
     * @brief Get the Point Data Ptr of PointMap object
     *
     * @return double* Point Data Ptr (m)
     */
    double *GetPointDataPtr();
    /**
     * @brief Get the Normal Data Ptr of PointMap object
     *
     * @return double* Normal Data Ptr
     */
    double *GetNormalDataPtr();
    /**
     * @brief Get the Point Data Const Ptr of PointMap object
     *
     * @return const double* Point Data Ptr (m)
     */
    const double *GetPointDataConstPtr() const;
    /**
     * @brief Get the Normal Const Data Ptr of PointMap object
     *
     * @return const double* Normal Data Ptr
     */
    const double *GetNormalDataConstPtr() const;

    /**
     * @brief Get the Point Data Seperated
     *
     * @param x
     * @param y
     * @param z
     * @param scale  default set to 1
     * @return true
     * @return false
     */

    bool GetPointMapSeperated(double *x, double *y, double *z, const double scale = 1.0);

    /*
     * @brief clone the point data
     * return PointMap
     */

    PointMap Clone() const;

    /**
     * @brief Retrieves the timestamp of the PointMap
     *
     * Returns the timestamp value representing the acquisition time
     * of the point cloud data. The timestamp is measured in
     * microseconds (us).
     *
     * @return uint64_t Timestamp value in microseconds (us)
     */
    uint64_t GetTimestamp() const;

    /**
     * @brief Sets the timestamp for the PointMap
     *
     * Updates the timestamp value associated with the PointMap data.
     * The timestamp should represent the acquisition time of the point cloud data
     * and must be provided in microseconds (us).
     *
     * @param timestamp Timestamp value in microseconds (us) to be set
     * @return bool True if the timestamp was successfully set, false otherwise
     */
    bool SetTimestamp(const uint64_t timestamp);

    /**
     * @brief RVC Handle
     *
     */
    Handle m_handle;
};

struct RVC_EXPORT Mesh {
    static Mesh CreateFromPointMapData(const Size &size, const double *data = nullptr,
                                       const double &z_threshold = 0.01);
    static Mesh CreateFromPointMap(const PointMap &pm, const double &z_threshold = 0.01);

    static void Destroy(Mesh mesh, bool no_reuse = true);
    bool IsValid() const;
    Size GetSize() const;
    double *GetMeshPointDataPtr();
    int *GetMeshIndexDataPtr();
    const double *GetMeshPointDataConstPtr() const;
    const int *GetMeshIndexDataConstPtr() const;
    const int &GetMeshIndexNum() const;
    bool Save(const char *file, const PointMapUnit::Enum unit = PointMapUnit::Meter);
    Mesh Clone() const;
    Handle m_handle;
};

struct RVC_EXPORT CorrespondMap {
    static CorrespondMap Create(const Size sz, double *data = nullptr, bool own_data = true);
    static void Destroy(CorrespondMap correspondMap, bool no_reuse = true);

    bool IsValid();
    Size GetSize();
    double *GetDataPtr();
    const double *GetDataConstPtr();

    Handle m_handle;
};

/**
 * @brief Get last error of RVC SDK
 *
 * @return int
 */
RVC_EXPORT int GetLastError();

/**
 * @brief Get the Version of RVC SDK
 *
 * @return string of version
 */
RVC_EXPORT const char *GetVersion();

/**
 * @brief Get the lastest error message. The pointer to string is temporary, you need to copy data from its buffer to
 * your buffer to prevent dangling pointer.
 * @return string of error message
 */
RVC_EXPORT const char *GetLastErrorMessage();

/**
 * @brief CameraID, support *CameraID_Left* and *CameraID_Right*
 *
 * @enum CameraID
 *
 */
enum CameraID {
    CameraID_NONE = 0,
    CameraID_0 = 1 << 0,
    CameraID_1 = 1 << 1,
    CameraID_2 = 1 << 2,
    CameraID_3 = 1 << 3,
    CameraID_Left = CameraID_0,
    CameraID_Right = CameraID_1,
    CameraID_Both = CameraID_Left | CameraID_Right,
    CameraID_Extra = CameraID_2
};

/**
 * @brief RVC supported Camera Port type
 *
 * All support type is *PortType_USB*, *PortType_GIGE*
 */
enum PortType {
    PortType_NONE = 0,
    PortType_USB = 1,
    PortType_GIGE = 2,
};

/**
 * @brief RVC supported Camera Network type
 *
 *  Only valid when Camera PortType is *PortType_GIGE*
 *
 * All support type is *NetworkType_DHCP*, *NetworkType_STATIC*
 */
enum NetworkType {
    NetworkType_DHCP = 0,
    NetworkType_STATIC = 1,
};

/**
 * @brief Projector color, support *ProjectorColor_Red*, *ProjectorColor_Green*, *ProjectorColor_Blue*,
 * *ProjectorColor_White* and *ProjectorColor_ALL*
 *
 */
enum ProjectorColor {
    ProjectorColor_None = 0,
    ProjectorColor_Red = 1,
    ProjectorColor_Green = 2,
    ProjectorColor_Blue = 4,
    ProjectorColor_White = 8,
    ProjectorColor_ALL = ProjectorColor_Red | ProjectorColor_Green | ProjectorColor_Blue | ProjectorColor_White,
};

/**
 * @brief Protective Cover Status
 *
 */
enum ProtectiveCoverStatus {
    ProtectiveCoverStatus_Unknown = 0,
    ProtectiveCoverStatus_Closed = 1,
    ProtectiveCoverStatus_Closing = 2,
    ProtectiveCoverStatus_Open = 3,
    ProtectiveCoverStatus_Opening = 4,
};

/**
 * @brief White balance ratio selector, suport *BalanceSelector_Red*, *BalanceSelector_Green* and *BalanceSelector_Blue*
 *
 */
enum BalanceSelector {
    BalanceSelector_None = 0,
    BalanceSelector_Red,
    BalanceSelector_Green,
    BalanceSelector_Blue,
};

/**
 * @brief NetworkDevie, support *NetworkDevice_LightMachine*, *NetworkDevice_LeftCamera* and *NetworkDevice_RightCamera*
 *
 */
enum NetworkDevice {
    NetworkDevice_LightMachine = 0,
    NetworkDevice_LeftCamera = 1,
    NetworkDevice_RightCamera = 2,
    NetworkDevice_ExtraCamera = 3,
};

/**
 * @brief NetworkDevieStatus, support *NetworkDeviceStatus_OK*, *NetworkDeviceStatus_Not_Reachable*,
 * *NetworkDeviceStatus_In_Use* and *NetworkDeviceStatus_Conflict*
 *
 */
enum NetworkDeviceStatus_ {
    NetworkDeviceStatus_OK,
    NetworkDeviceStatus_Not_Reachable,
    NetworkDeviceStatus_In_Use,
    NetworkDeviceStatus_Conflict,
};

/**
 * @brief CaptureMode, support *CaptureMode_Fast*, *CaptureMode_Normal*, *CaptureMode_Ultra*, *CaptureMode_Robust*,
 * *CaptureMode_AntiInterReflection* and *CaptureMode_SwingLineScan*
 *
 */
enum CaptureMode {
    CaptureMode_Fast = 1 << 0,
    CaptureMode_Normal = 1 << 1,
    CaptureMode_Ultra = 1 << 2,
    CaptureMode_Robust = 1 << 3,  // [deprecated] CaptureMode_Robust is deprecated! Use scan_times instead.
    CaptureMode_AntiInterReflection = 1 << 4,
    CaptureMode_SwingLineScan = 1 << 5,
    CaptureMode_FixedLineScan = 1 << 6,
    CaptureMode_LineArrayShift = 1 << 7,
    CaptureMode_All = CaptureMode_Fast | CaptureMode_Normal | CaptureMode_Ultra | CaptureMode_Robust |
                      CaptureMode_AntiInterReflection | CaptureMode_SwingLineScan | CaptureMode_FixedLineScan |
                      CaptureMode_LineArrayShift,
};

/**
 * @enum TriggerMode
 * @brief Defines the trigger source for point cloud acquisition
 *
 * This enumeration specifies how the 3D camera initiates point cloud generation,
 * determining whether acquisition is triggered by software (explicit function calls)
 * or by external hardware signals.
 */
enum TriggerMode {
    /**
     * @brief Software trigger mode
     *
     * In this mode, point clouds are generated only when explicitly requested
     * by calling the SDK's capture functions. The application has full control
     * over the timing of acquisition by calling either:
     * - Capture()
     * - GetFixedLineScanPointMap()
     *
     * @note This mode is supported by all acquisition modes.
     */
    TriggerMode_SoftWare = 0,

    /**
     * @brief Hardware trigger mode
     *
     * Point clouds are generated automatically in response to external
     * hardware signals (e.g., encoder pulses, PLC outputs, or GPIO signals).
     * The application must register a callback function to receive point cloud
     * data asynchronously when hardware triggers occur. The fixed line scan mode should be initiated before the
     * hardware signals begin and terminated after they cease.
     *
     * @note Hardware trigger is only supported when using FixedLineScan
     *       acquisition mode. Other modes require software trigger.
     * @see SetFixedLineScanCallback
     */
    TriggerMode_HardWare = 1,

    /**
     * @brief Fixed-rate automatic trigger mode
     *
     * In this mode, the camera automatically generates point clouds at a fixed
     * internal frequency, without requiring external hardware signals or
     * explicit software calls for each acquisition.
     *
     * The application must register a callback function to receive point cloud
     * data asynchronously as it is generated at the predefined rate.
     *
     * @note This mode requires registration of a callback function to receive data.
     * @see SetFixedLineScanCallback
     */
    TriggerMode_FixedRate = 2,
};

/**

 * @brief RVC X Device info
 *
 * @param name Device name
 * @param sn Device serial number
 * @param factroydate Device manufacture date
 * @param port Port number
 * @param type Support *PortType_USB* and *PortType_GIGE*
 * @param cameraid Support *CameraID_Left*, *CameraID_Right* and *CameraID_Both*
 * @param boardmodel main borad model type
 * @param support_x2 support x2 or not
 * @param support_color supported projector color
 * @param firmware_version RVC Camera firmware version
 */
struct RVC_EXPORT DeviceInfo {
    char name[32];
    char sn[32];
    char factroydate[32];
    char port[32];
    enum PortType type;
    enum CameraID cameraid;
    int boardmodel;
    bool support_x2;
    enum ProjectorColor support_color;
    int workingdist_near_mm;
    int workingdist_far_mm;
    char firmware_version[128];
    enum CaptureMode support_capture_mode;
    bool support_x1;
    bool support_protective_cover;
    bool support_extra;
    bool support_hardware_trigger;
};

/**
 * @brief Device struct
 *
 */
struct RVC_EXPORT Device {
    /**
     * @brief Destroy the device
     *
     * @param d Device to be destroyed
     */
    static void Destroy(Device d);
    /**
     * @brief Check device is valid or not
     *
     * @return true Valid
     * @return false Not valid
     */
    bool IsValid() const;
    /**
     * @brief Print device info
     *
     */
    void Print() const;
    /**
     * @brief Get the DeviceInfo object
     *
     * @param pinfo Current Device information
     * @return true Success
     * @return false Failed
     */
    bool GetDeviceInfo(DeviceInfo *pinfo);
    /**
     * @brief Set the Device network configuration
     *
     * @param d NetworkDevice
     * @param type NetworkType of Device DHCP/Static
     * @param ip New ip for Device, valid if NetworkType is *NetworkType_STATIC*
     * @param netMask New netmask for Device, valid if NetworkType is *NetworkType_STATIC*
     * @param gateway New gateway for Device, valid if NetworkType is *NetworkType_STATIC*
     * @return int status code
     */
    int SetNetworkConfig(enum NetworkDevice d, NetworkType type, const char *ip, const char *netMask,
                         const char *gateway);
    /**
     * @brief Get the device network configuration
     *
     * @param d NetworkDevice
     * @param type NetworkType of Device DHCP/Static
     * @param ip Current ip of Device
     * @param netMask Current netmask of Device
     * @param gateway Current gateway of Device
     * @param status Device`s status
     * @return int Status code
     */
    int GetNetworkConfig(enum NetworkDevice d, NetworkType *type, char *ip, char *netMask, char *gateway, int *status);
    /**
     * @brief Automatically configure network IP addresses for all devices (LightMachine and cameras)
     *        This function automatically finds available IP addresses in the same network segment
     *        and configures them for devices that are not in OK status.
     *        This is equivalent to the "one-click configuration" feature in RVC Manager.
     *
     * @return int Status code (RVC_NO_ERROR on success)
     */
    int AutoConfigureNetwork();
    /**
     * @brief Upgrade RVC Device Firmware
     *
     * @param device_firmware_path   device firmware path, rvbin
     * @param config_data_path   config data path, if set to nullptr, will ignore
     * @return bool Status
     */
    bool UpgradeFirmware(const char *device_firmware_path, const char *config_data_path);
    /**
     * @brief Check if device firmware is match
     *
     * @return true : firmware match
     * @return false : firmware mismatch, need to upgrade
     */
    bool IsFirmwareMatch(void);
    /**
     * @brief RVC Handle
     *
     */
    Handle m_handle;
};

/**
 * @brief System list Device type
 *
 * All support type are *USB*, *GigE*, *ALL*
 */
struct RVC_EXPORT SystemListDeviceType {
    /**
     * @brief RVC camera type, support *USB*, *GigE* and *All*
     *
     */
    enum Enum {
        None = 0,
        USB = 1 << 0,
        GigE = 1 << 1,
        All = USB | GigE,
    };
    /**
     * @brief print SystemListDeviceType
     *
     * @param e List Device Type
     * @return const char* name of SystemListDeviceType
     */
    static const char *ToString(const SystemListDeviceType::Enum e);
};

/**
 * @brief SystemInit
 *
 * @return true Success
 * @return false Failed
 */
RVC_EXPORT bool SystemInit();
/**
 * @brief Check system is inited or not
 *
 * @return true Inited
 * @return false Not Inited
 */
RVC_EXPORT bool SystemIsInited();
/**
 * @brief SystemShutdown
 *
 */
RVC_EXPORT void SystemShutdown();


/**
 * @brief List the fix number devices
 *
 * @param pdevices device listed
 * @param size desire list devices number
 * @param actual_size actually list devices number
 * @param opt List DeviceType All/USB/GIGE optional
 * @return int Status code
 *
 * @snippet X1Test.cpp List USB Device using ptr
 */
RVC_EXPORT int SystemListDevices(Device *pdevices, size_t size, size_t *actual_size,
                                 SystemListDeviceType::Enum opt = SystemListDeviceType::All);

/**
 * @brief Return the device according to the serialNumber, if the device is valid
 *
 * @param serialNumber Device Struct serial number
 * @return Device The serialNumber  corresponding Device Struct
 */
RVC_EXPORT Device SystemFindDevice(const char *serialNumber);

/**
 *  @brief Set the name of logger
 *
 * @param loggerName The logger name
 */
RVC_EXPORT void SystemSetLoggerName(const char *loggerName);



enum CameraTempSelector {
    CameraTempSelector_Camera,
    CameraTempSelector_CoreBoard,
    CameraTempSelector_FpgaCore,
    CameraTempSelector_Framegrabberboard,
    CameraTempSelector_Sensor,
    CameraTempSelector_SensorBoard,
};

enum SmoothnessLevel { SmoothnessLevel_Off, SmoothnessLevel_Weak, SmoothnessLevel_Normal, SmoothnessLevel_Strong };

// UserPtr
typedef void *UserPtr;

/**
 * @brief X1 struct
 *
 */
struct RVC_EXPORT X1 {
    /**
     * @brief Capture options
     *
     * @snippet X1Test.cpp Capture with options
     */
    struct CaptureOptions {
        /**
         * @brief Construct a new Capture Options object
         *
         */
        CaptureOptions() {
            calc_normal = false;
            transform_to_camera = true;
            use_auto_noise_removal = true;
            noise_removal_distance = 0;
            noise_removal_point_number = 40;
            light_contrast_threshold = 3;
            phase_filter_range = 0;
            projector_brightness = 240;
            exposure_time_2d = 11;
            exposure_time_3d = 11;
            gain_2d = 0.f;
            gain_3d = 0.f;
            hdr_exposure_times = 0;
            hdr_exposuretime_content[0] = 11;
            hdr_exposuretime_content[1] = 20;
            hdr_exposuretime_content[2] = 50;
            hdr_gain_3d[0] = 0;
            hdr_gain_3d[1] = 0;
            hdr_gain_3d[2] = 0;

            hdr_scan_times[0] = 1;
            hdr_scan_times[1] = 1;
            hdr_scan_times[2] = 1;

            hdr_projector_brightness[0] = 240;
            hdr_projector_brightness[1] = 240;
            hdr_projector_brightness[2] = 240;
            calc_normal_radius = 5;
            gamma_2d = 1.f;
            gamma_3d = 1.f;
            use_projector_capturing_2d_image = true;
            smoothness = SmoothnessLevel_Off;
            downsample_distance = 0.0;
            capture_mode = CaptureMode_Normal;
            confidence_threshold = 0;
            roi = RVC::ROI();
            truncate_z_min = -9999.f;
            truncate_z_max = 9999.f;
            bilateral_filter_kernal_size = 0;
            bilateral_filter_depth_sigma = 0;
            bilateral_filter_space_sigma = 0;
            scan_times = 1;
            use_auto_bilateral_filter = true;
            reflection_filter_threshold = 0;
            smooth_sigma = 1.75;
            enable_2d_in_capture = true;
        }
        /**
         * @brief flag Whether calculate 3D points normal vector
         *
         */
        bool calc_normal;
        /**
         * @brief flag Whether transfrom 3D points from calibration board system to camera coordinate system
         *
         */
        bool transform_to_camera;
        /**
         * Point cloud noise removal algorithm 1, contains one parameter: filter_range.
         * If this algorithm does not work well, set filter_range to 0 and try noise removal algorithm 2 below.
         * @brief Set the noise filter value. The larger the value, the greater the filtering degree.
         * The default value has been changed to 0 from 1 after v1.6.1.
         */
        [[deprecated]] int filter_range;
        /**
         * Point cloud noise removal algorithm, contains three parameters: use_auto_noise_removal,
         * noise_removal_distance and noise_removal_point_number. This algorithm performs noise reduction through a
         * clustering algorithm. The point cloud is classified into blocks according to the distance
         * (noise_removal_distance). If the total number of points in the block is less than a certain threshold
         * (noise_removal_point_number), the points in the block are considered as noise points and need to be removed.
         */
        /**
         * @brief flag Whether to use auto noise removal.
         * If true, the noise_removal_distance and noise_removal_point_number will be ignored. It will automatically
         * adjust these two parameters according to the point cloud data and do noise removal.
         */
        bool use_auto_noise_removal;
        /**
         * @brief The smaller the value, the greater the filtering degree.
         * range: 0 ~ 20 (units: mm)
         */
        double noise_removal_distance;
        /**
         * @brief Set the noise filter parameter 2. The larger the value, the greater the filtering degree.
         */
        int noise_removal_point_number;
        /**
         * @brief Light contrast trheshold, range in [0, 10]. The contrast of point less than this value will be treat
         * as invalid point and be removed.
         *
         */
        int light_contrast_threshold;
        /**
         * @brief Set the phase filter value. The larger the value, the greater the filtering degree 0~40
         *
         */
        int phase_filter_range;
        /**
         * @brief Set the exposure_time 2D value in milliseconds
         *
         */
        int exposure_time_2d;
        /**
         * @brief Set the exposure_time 3D value in milliseconds
         *
         */
        int exposure_time_3d;
        /**
         * @brief Set the projector brightness value
         *
         */
        int projector_brightness;
        /**
         * @brief Set the 2D gain value
         *
         */
        float gain_2d;
        /**
         * @brief Set the 3D gain value
         *
         */
        float gain_3d;
        /**
         * @brief Set the hdr exposure times value. 0,2,3
         *
         */
        int hdr_exposure_times;
        /**
         * @brief Set the hdr exposure time content. capture with white light, range [11, 100], others [3, 100]. If use
         * M-series, range[10, 100].
         *
         */
        int hdr_exposuretime_content[3];
        /**
         * @brief Set the hdr 3D gain content.
         *
         */
        float hdr_gain_3d[3];

        /**
         * @brief Set the hdr scan times, only use in robust mode. range: [1, 8]
         *
         */
        int hdr_scan_times[3];

        /**
         * @brief Set the hdr projector brightness value
         *
         */
        int hdr_projector_brightness[3];
        /**
         * @brief Neighborhood radius in pixel of calculating normal, > 0
         */
        unsigned int calc_normal_radius;
        /**
         * @brief Set the 2D gamma value
         *
         */
        float gamma_2d;
        /**
         * @brief Set the 3D gamma value
         *
         */
        float gamma_3d;
        /**
         * @brief Set 2D image whether use projector
         *
         */
        bool use_projector_capturing_2d_image;
        /**
         * @brief control point map smoothness
         *
         */
        [[deprecated(
            "smoothness has been deprecated in CPU version,use smooth_sigma instead")]] SmoothnessLevel smoothness;

        /**
         * @brief uniform downsample distance. if <= 0, do nothing.
         *
         */
        double downsample_distance;

        /**
         * @brief control capture mode
         *
         */
        CaptureMode capture_mode;

        /**
         * @brief confidence threshold, the point with confindence low then this value will be removed
         * range: [0, 1]
         *
         */
        double confidence_threshold;

        /**
         * @brief set ROI function, only 3d points in the roi will be generated.
         * This function can improve 3d capturespeed.
         * The parameters of roi must comply with the rules of the equipment and can be checked by CheckRoi.
         * We recommend that you adjust roi automatically through C before AutoAdjustRoi.
         */
        RVC::ROI roi;

        /**
         * @brief truncate point map and depth map by z direction minimum value (units: mm)
         * and truncate_z_min should less than truncate_z_max range: [-9999, 9999]
         *
         */
        double truncate_z_min;

        /**
         * @brief truncate point map and depth map by z direction maximum value (units: mm)
         * and truncate_z_max should more than truncate_z_min range: [-9999, 9999]
         *
         */
        double truncate_z_max;

        /**
         * @brief the kernal size of bilateral filter of depth map
         * range: [3, 31], 0 for not use bilateral filter
         *
         */
        [[deprecated("Use smooth_sigma instead")]] int bilateral_filter_kernal_size;

        /**
         * @brief the guassian sigma in depth of bilateral filter of depth map
         * range: [0, 100]
         *
         */
        [[deprecated("Use smooth_sigma instead")]] double bilateral_filter_depth_sigma;

        /**
         * @brief the guassian sigma in space of bilateral filter of depth map
         * range: [0, 100]
         *
         */
        [[deprecated("Use smooth_sigma instead")]] double bilateral_filter_space_sigma;

        /**
         * @brief scan times, only use in robust mode. range: [1, 8]
         */
        int scan_times;

        /**
         * @brief flag Whether to use auto bilateral filter.
         * If true, the bilateral_filter_kernal_size and bilateral_filter_depth_sigma and bilateral_filter_space_sigma
         * will be ignored. It will automatically adjust these three parameters according to the point cloud data and do
         * bilateral filter.
         */
        [[deprecated("Use smooth_sigma instead")]] bool use_auto_bilateral_filter;

        /**
         * @brief Used to remove large-area erroneous point clouds caused by reflections.
         * The higher this value is set, the more points will be removed by the reflection filter.
         * Setting it too large may remove data from thin and pointy objects.
         * range:[0, 30]
         */
        int reflection_filter_threshold;

        /**
         * @brief The Gaussian filters are used to smooth points.
         * The larger the smooth_sigma, the smoother the point cloud becomes. However, an excessively large smooth_sigma
         * can cause edges to be smoothed out as well.
         * range: [0, 5]
         */
        double smooth_sigma;

        /**
         * @brief Acquire 2D images during capture
         */
        bool enable_2d_in_capture;
    };
    /**
     * @brief Options when setting custom transformation
     *
     */
    struct CustomTransformOptions {
        /**
         * @brief base coordinate of custom transformation,default is *CoordinateSelect_Disabled*
         *
         * All support type is
         * *CoordinateSelect_Disabled*,*CoordinateSelect_Camera*,*CoordinateSelect_CaliBoard*
         */
        enum CoordinateSelect {
            CoordinateSelect_Disabled,
            CoordinateSelect_Camera,
            CoordinateSelect_CaliBoard,
        };

        CustomTransformOptions()
            : coordinate_select(CoordinateSelect_Disabled), transform{1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1} {}

        /**
         * @brief base coordinate setting of custom transformation
         *
         */

        CoordinateSelect coordinate_select;

        /**
         * @brief custom transformation, translation unit: m
         *
         */
        double transform[16];
    };

    /**
     * @brief X1 CollectionCallBackInfo
     */
    struct CollectionCallBackInfo {
        Image image;
    };

    /**
     * @brief X1 CalculationCallBackInfo
     */
    struct CalculationCallBackInfo {
        Image image;
        PointMap pointmap;
        DepthMap depthmap;
        ConfidenceMap confidencemap;
    };

    /**
     * @brief X1 CallBackPtr
     */
    typedef void (*CollectionCallBackPtr)(X1::CollectionCallBackInfo, X1::CaptureOptions, UserPtr);
    typedef void (*CalculationCallBackPtr)(X1::CalculationCallBackInfo, X1::CaptureOptions, UserPtr);

    /**
     * @brief Create a RVC X Camera and choose the CameraID which you desire before you use X1
     *
     * @param d One RVC X Camera
     * @param camid Choose *CameraID_Left* or *CameraID_Left*
     * @return X1 RVC X object
     *
     * @snippet X1Test.cpp Create RVC X1
     */
    static X1 Create(const Device &d, enum CameraID camid = CameraID_Left);
    /**
     * @brief Release all X1 resources after you use X1
     *
     * @param x RVC X object to be released
     *
     * @snippet X1Test.cpp Create RVC X1
     */
    static void Destroy(X1 &x);
    /**
     * @brief Check X1 is valid or not before use X1
     *
     * @return true Available
     * @return false Not available
     *
     * @snippet X1Test.cpp Create RVC X1
     */
    bool IsValid();
    /**
     * @brief Open X1 before you use it
     *
     * @return true Success
     * @return false Failed
     *
     * @snippet X1Test.cpp Create RVC X1
     */
    bool Open();
    /**
     * @brief Close X1 after you Open it
     *
     * @snippet X1Test.cpp Create RVC X1
     */
    void Close();
    /**
     * @brief Check X1 is open or not
     *
     * @return true Is open
     * @return false Not open
     *
     * @snippet X1Test.cpp Create RVC X1
     */
    bool IsOpen();
    /**
     * @brief Check X1 is physically connected or not
     *
     * @return true Is physically connected
     * @return false Not physically connected
     *
     * @snippet X1Test.cpp Create RVC X1
     */
    bool IsPhysicallyConnected();
    /**
     * @brief Open ProtectiveCover
     *
     * @return true if success
     * @return false if failed
     */
    bool OpenProtectiveCover();
    /**
     * @brief Open ProtectiveCover Async
     *
     * @return true if success
     * @return false if failed
     */
    bool OpenProtectiveCoverAsync();
    /**
     * @brief Close ProtectiveCover
     *
     * @return true if success
     * @return false if failed
     */
    bool CloseProtectiveCover();
    /**
     * @brief Close ProtectiveCover Async
     *
     * @return true if success
     * @return false if failed
     */
    bool CloseProtectiveCoverAsync();
    /**
     * @brief Reset ProtectiveCover
     *
     * @return true if success
     * @return false if failed
     */
    bool ResetProtectiveCover();

    /**
     * @brief Get Status of ProtectiveCover
     * @return ProtectiveCoverStatus
     */
    bool GetProtectiveCoverStatus(ProtectiveCoverStatus &status);
    /**
     * @brief Provide a callback to RVC system and it will be called when collection finished.
     * @param cb The callback
     * @param ctx The user-pointer
     *
     * @return true when succeed to set
     * @return false when failed to set
     *
     * @snippet CaptureCallBack.cpp
     */
    bool SetCollectionCallBack(X1::CollectionCallBackPtr cb, UserPtr ctx);

    /**
     * @brief Provide a callback to RVC system and it will be called when calculation finished.
     * @param cb The callback
     * @param ctx The user-pointer
     *
     * @return true when succeed to set
     * @return false when failed to set
     *
     * @snippet CaptureCallBack.cpp
     */
    bool SetCalculationCallBack(X1::CalculationCallBackPtr cb, UserPtr ctx);

    /**
     * @brief Capture one point map and one image. This function will save capture options into camera.
     *
     * @param opts CaptureOptions
     * @return true Success
     * @return false Failed
     *
     * @snippet X1Test.cpp Capture with options
     */
    bool Capture(const CaptureOptions &opts);
    /**
     * @brief Capture one point map and one image. This function will load capture options from camera.
     *
     * @return true Success
     * @return false Failed
     *
     */
    bool Capture();
    /**
     * @brief Capture one image. This function will save capture options into camera. You can use GetImage() to obtain
     * 2D imgae
     *
     * @param opts CaptureOptions
     * @return true Success
     * @return false Failed
     */
    bool Capture2D(const CaptureOptions &opts);
    /**
     * @brief Capture one image.  This function will load capture options from camera. You can use GetImage() to obtain
     * 2D imgae
     *
     * @return true Success
     * @return false Failed
     */
    bool Capture2D();
    /**
     * @brief Set the camera band width ratio
     *
     * @param percent Band width ratio
     * @return true Success
     * @return false Failed
     */
    bool SetBandwidth(float percent);

    /**
     * @brief Get the camera band width ratio
     *
     * @param percent Band width ratio
     * @return true Success
     * @return false Failed
     */
    bool GetBandwidth(float &percent);

    /**
     * @brief Set the Transformation of output point cloud
     *
     * @param opts  Custom Transform Options
     * @return true
     * @return false
     */
    bool SetCustomTransformation(const CustomTransformOptions &opts);
    /**
     * @brief Get the Custom Transformation object
     *
     * @param opts
     * @return true
     * @return false
     */
    bool GetCustomTransformation(CustomTransformOptions &opts);
    /**
     * @brief Save encoded map in txt
     *
     * @param addr save encoded images address
     * @return int num
     */
    bool SaveEncodedImagesData(const char *addr);

    /**
     * @brief Get the Image object
     *
     * @return Image
     */
    Image GetImage();
    /**
     * @brief Get the DepthMap object
     *
     * @return DepthMap A DepthMap
     */
    DepthMap GetDepthMap();
    /**
     * @brief Get the Point Map object
     *
     * @return PointMap
     */
    PointMap GetPointMap();
    /**
     * @brief Get the Confidence Map object
     *
     * @return ConfidenceMap
     */
    ConfidenceMap GetConfidenceMap();
    /**
     * @brief Get the extrinsic matrix (transformation from calibration board to specified camera)
     *
     * @param matrix [out] 4x4 transformation matrix stored as a 16-element array in row-major order.
     *                     The matrix represents the transformation from the calibration board coordinate system
     *                     to the specified camera coordinate system.
     *                     Format: [R11, R12, R13, T1,
     *                             R21, R22, R23, T2,
     *                             R31, R32, R33, T3,
     *                             0,   0,   0,   1]
     *                     Where R is the 3x3 rotation matrix and T is the 3x1 translation vector.
     * @return true Success
     * @return false Failed
     */
    bool GetExtrinsicMatrix(float *matrix);
    /**
     * @brief Get intrinsic and distortion parameters.
     * @param instrinsicMatrix [out] Output intrinsic matrix. This is a 9-element array storing
     *                               a 3x3 matrix in row-major order: [fx, 0, cx, 0, fy, cy, 0, 0, 1]
     *                               - fx, fy: Focal lengths in x and y directions (in pixels)
     *                               - cx, cy: Principal point coordinates (in pixels)
     * @param distortion [out] Output distortion coefficients. This is a 5-element array containing:
     *                         [k1, k2, k3, p1, p2]
     *                         - k1, k2, k3: Radial distortion coefficients
     *                         - p1, p2: Tangential distortion coefficients
     *                         Note: This order is different from OpenCV's default order (k1,k2,p1,p2,k3).
     * @return true if successful
     * @return false if failed
     */
    bool GetIntrinsicParameters(float *instrinsic_matrix, float *distortion);
    /**
     * @brief  GetProjectorTemperature
     * @param  &temperature:
     * @return true Success
     * @return false Failed
     */
    bool GetProjectorTemperature(float &temperature);
    /**
     * @brief  GetCameraTemperature
     * @note   TODO:
     * @param  seletor:
     * @param  &temperature:
     * @retval
     */
    [[deprecated]] bool GetCameraTemperature(CameraTempSelector seletor, float &temperature);
    /**
     * @brief Set the white balance ratio value
     *
     * @param selector support BalanceSelector_Red, BalanceSelector_Green and BalanceSelector_Blue
     * @param value  balance ratio value
     * @return true Success
     * @return false Failed
     */
    bool SetBalanceRatio(BalanceSelector selector, float value);
    /**
     * @brief Get the white balance ratio value
     *
     * @param selector support BalanceSelector_Red, BalanceSelector_Green and BalanceSelector_Blue
     * @param value balance ratio value
     * @return true Success
     * @return false Failed
     */
    bool GetBalanceRatio(BalanceSelector selector, float *value);

    /**
     * @brief Get the white balance ratio value range
     *
     * @param selector support BalanceSelector_Red, BalanceSelector_Green and BalanceSelector_Blue
     * @param min_value selector's minimum value
     * @param max_value selector's maximum value
     * @return true Success
     * @return false Failed
     */
    bool GetBalanceRange(BalanceSelector selector, float *min_value, float *max_value);

    /**
     * @brief Only Color Camera can use this function. This function can get suitable white balance paramters
     *
     * @param wb_times how many images used for calculate the white balance paramters
     * @param opts capture options. exposure_time_2d, gain_2d, gamma_2d will be used. use_projector_capturing_2d_image
     * == true, brightness will be used too.
     * @param roi auto white balance will be operated here
     * @return true
     * @return false
     */
    bool AutoWhiteBalance(int wb_times = 10, const CaptureOptions &opts = CaptureOptions(),
                          const RVC::ROI &roi = RVC::ROI());

    /**
     * @brief Get the Exposure Time Range
     *
     * @param min_value exposure time minimum value
     * @param max_value exposure time maxinum value
     * @return true Success
     * @return false Failed
     */
    bool GetExposureTimeRange(int *min_value, int *max_value);

    /**
     * @brief Get the Gain Range
     *
     * @param min_value gain minimum value
     * @param max_value gain minimum value
     * @return true Success
     * @return false Failed
     */
    bool GetGainRange(float *min_value, float *max_value);

    /**
     * @brief Get the Gamma Range
     *
     * @param min_value gamma minimum value
     * @param max_value gamma minimum value
     * @return true Success
     * @return false Failed
     */
    bool GetGammaRange(float *min_value, float *max_value);

    /**
     * @brief Save capture option parameters
     *
     * @param opts CaptureOptions
     * @return true Success
     * @return false Failed
     */
    bool SaveCaptureOptionParameters(const X1::CaptureOptions &opts);

    /**
     * @brief Get capture option parameters
     *
     * @param opts CaptureOptions
     * @return true Success
     * @return false Failed
     */
    bool LoadCaptureOptionParameters(X1::CaptureOptions &opts);

    /**
     * @brief Get auto capture setting. Exposure_time_2d, exposure_time_3d, projector_brightness,
     * light_contrast_threshold will be adjusted automatically. automatically
     *
     * @param opts
     * @return CaptureOptions
     */
    bool GetAutoCaptureSetting(CaptureOptions &opts, const ROI &roi = ROI());

    /**
     * @brief adjust 3D capturing parameters
     *
     * @param opts [in,out] capture options. if  hdr_exposure_times > 1, hdr_exposure_times and hdr_exposuretime_content
     * will be adjusted. If hdr_exposure_times equals to 1, exposure_time_3d will be adjusted.
     * @param roi [in] if width or height equal to 0, all image will be used.
     * @return true
     * @return false
     */
    bool GetAutoHdrCaptureSetting(CaptureOptions &opts, const ROI &roi);

    /**
     * @brief Automatically calculates and applies the optimal point cloud noise removal parameters.
     *
     * WARNING: This is a time-consuming operation as it triggers actual camera captures.
     * This function evaluates the current scene to determine the best cluster-based noise
     * removal settings and applies them to the current point cloud.
     *
     * @param[in,out] opts Capture options. Upon successful execution, the following parameters
     * inside this struct will be modified and overwritten:
     * - `opts.noise_removal_distance`
     * - `opts.noise_removal_point_number`
     * @return true The automatic noise removal parameters were successfully calculated and applied.
     * @return false The operation failed (e.g., camera not ready or capture failed).
     */
    bool GetAutoNoiseRemovalSetting(CaptureOptions &opts);

    /**
     * @brief Load camera setting from local file .
     * @param filename [in]
     * @return true the content of file is correctly .
     * @return false the content of file is not correctly .
     */
    bool LoadSettingFromFile(const char *filename);

    /**
     * @brief Save camera setting to local file.
     * @param filename [in]
     * @return true Successfully written to the file.
     * @return false Failed write to file.
     */
    bool SaveSettingToFile(const char *filename);

    /**
     * @brief Check whether the parameters of ROI comply with the rules of Device.
     * @param roi [in] .
     * @return true
     * @return false
     */
    bool CheckRoi(ROI roi);

    /**
     * @brief Automatically correct the parameters of ROI. You need to correct ROI before Capture/Captrue2D.
     * @param roi [in] If you want to get a maximum ROI, you can pass in the default value.
     * @return ROI Corrected ROI.
     */
    ROI AutoAdjustRoi(ROI roi = ROI());

    /**
     * @brief Get the range of ROI.
     */
    bool GetRoiRange(ROIRange &range);

    /**
     * @brief Get Camera Resolution
     *
     * @param resolution
     * @return true
     * @return false
     */
    bool GetCameraResolution(Size &resolution);

    /**
     * @brief Get auto 2d exposure time automatically
     * @param opts [in]
     * @param roi [in]
     * @return true
     * @return false
     */
    bool GetAuto2DExposureTime(CaptureOptions &opts, const ROI &roi = ROI());

    /**
     * @brief Get the Mesh object
     *
     * @return Mesh A Mesh
     */
    Mesh GetMesh();

    /**
     * @brief Set Current User Set by id. The user can utilize a total of 10 parameters groups to
     * quickly adjust camera settings for different 3d imaging scenarios.
     *
     * @param id [in] 0~9
     * @return true
     * @return false
     */
    bool SetCurrentUserSet(const int &id);

    /**
     * @brief Get Current User Set's id.
     *
     * @param id [out] 0~9
     * @return true
     * @return false
     */
    bool GetCurrentUserSet(int &id);

    /**
     * @brief Set User Set's name with id. The user can briefly describe the usage scenario of this
     * parameters groups by using a name.
     *
     * @param id [in]
     * @param name [in]
     * @return true
     * @return false
     */
    bool SetUserSetName(const int &id, const char *name);

    /**
     * @brief Get Current User Set's name with id.
     *
     * @param id [in]
     * @param name [out]
     * @return true
     * @return false
     */
    bool GetUserSetName(const int &id, char *name);

    /**
     * @brief RVC Handle
     *
     */
    Handle m_handle;
};


/**
 * @brief X2 struct
 *
 */
struct RVC_EXPORT X2 {
    /**
     * @brief Capture options
     *
     */
    struct CaptureOptions {
        /**
         * @brief Construct a new Capture Options object
         *
         */
        CaptureOptions() {
            transform_to_camera = CameraID_Left;
            projector_brightness = 240;
            calc_normal = false;
            calc_normal_radius = 5;
            use_auto_noise_removal = true;
            noise_removal_distance = 0;
            noise_removal_point_number = 40;
            light_contrast_threshold = 3;
            edge_noise_reduction_threshold = 2;
            exposure_time_2d = 11;
            exposure_time_3d = 11;
            gain_2d = 0.f;
            gain_3d = 0.f;
            hdr_exposure_times = 0;
            hdr_exposuretime_content[0] = 11;
            hdr_exposuretime_content[1] = 20;
            hdr_exposuretime_content[2] = 50;
            hdr_gain_3d[0] = 0;
            hdr_gain_3d[1] = 0;
            hdr_gain_3d[2] = 0;

            hdr_scan_times[0] = 1;
            hdr_scan_times[1] = 1;
            hdr_scan_times[2] = 1;

            hdr_projector_brightness[0] = 240;
            hdr_projector_brightness[1] = 240;
            hdr_projector_brightness[2] = 240;
            gamma_2d = 1.f;
            gamma_3d = 1.f;
            projector_color = ProjectorColor_Blue;
            use_projector_capturing_2d_image = true;
            smoothness = SmoothnessLevel_Off;
            downsample_distance = 0.0;
            capture_mode = CaptureMode_Normal;
            confidence_threshold = 0;
            scan_times = 1;

            bilateral_filter_kernal_size = 0;
            bilateral_filter_depth_sigma = 0;
            bilateral_filter_space_sigma = 0;

            line_scanner_scan_time_ms = 1000;
            line_scanner_exposure_time_us = 300;
            line_scanner_min_distance = 0;
            line_scanner_max_distance = 0;

            correspond2d = false;
            line_scanner_laser_position = 65536 / 2;
            use_auto_bilateral_filter = true;
            reflection_filter_threshold = 0;
            smooth_sigma = 1.75;

            roi = RVC::ROI();
            enable_2d_in_capture = true;
            pointcloud_completion = false;
            line_scanner_brightness_threshold = 5;
            trigger_mode = TriggerMode_SoftWare;
            encoder_trigger_interval = 8;
            truncate_z_min = -29999;
            truncate_z_max = 29999;
            line_scanner_confidence = 0.72;
            fixed_rate = 1;
            auto_set_fixed_rate = true;
            enable_transfer_control = false;
        }
        /**
         * @brief CameraID_Left transfrom 3D points from calibration board system to left camera coordinate system
         * CameraID_Right transfrom 3D points from calibration board system to right camera coordinate system
         * other is do not transfrom
         */
        CameraID transform_to_camera;
        /**
         * @brief Set the projector brightness value
         *
         */
        int projector_brightness;
        /**
         * @brief flag Whether calculate 3D points normal vector
         *
         */
        bool calc_normal;

        /**
         * @brief Neighborhood radius in pixel of calculating normal, > 0
         */
        unsigned int calc_normal_radius;

        /**
         * @brief Light contrast trheshold, range in [0, 10]. The contrast of point less than this value will be treat
         * as invalid point and be removed.
         *
         */
        int light_contrast_threshold;
        /**
         * @brief edge control after point matching, range in [0, 10], default = 2. The big the value, the more edge
         * noise to be removed.
         *
         */
        [[deprecated]] int edge_noise_reduction_threshold;
        /**
         * @brief Set the exposure_time 2D value in milliseconds
         *
         */
        int exposure_time_2d;
        /**
         * @brief Set the exposure_time 3D value in milliseconds
         *
         */
        int exposure_time_3d;
        /**
         * @brief Set the 2D gain value in milliseconds
         *
         */
        float gain_2d;
        /**
         * @brief Set the 3D gain value in milliseconds
         *
         */
        float gain_3d;
        /**
         * @brief Set the hdr exposure times value. 0,2,3
         *
         */
        int hdr_exposure_times;
        /**
         * @brief Set the hdr exposure time content. capture with white light, range [11, 100], others [3, 100]. If use
         * M-series, range[10, 100].
         *
         */
        int hdr_exposuretime_content[3];
        /**
         * @brief Set the hdr 3D gain content.
         *
         */
        float hdr_gain_3d[3];
        /**
         * @brief Set the hdr projector brightness value
         *
         */
        int hdr_projector_brightness[3];
        /**
         * @brief Set the 2D gamma value in milliseconds
         *
         */
        float gamma_2d;
        /**
         * @brief Set the 3D gamma value in milliseconds
         *
         */
        float gamma_3d;
        /**
         * @brief  projector color
         */
        ProjectorColor projector_color;
        /**
         * @brief Set 2D image whether use projector
         *
         */
        bool use_projector_capturing_2d_image;

        /**
         * @brief control point map smoothness
         *
         */
        [[deprecated(
            "smoothness has been deprecated in CPU version,use smooth_sigma instead")]] SmoothnessLevel smoothness;
        /**
         * Point cloud noise removal algorithm, contains three parameters: use_auto_noise_removal,
         * noise_removal_distance and noise_removal_point_number. This algorithm performs noise reduction through a
         * clustering algorithm. The point cloud is classified into blocks according to the distance
         * (noise_removal_distance). If the total number of points in the block is less than a certain threshold
         * (noise_removal_point_number), the points in the block are considered as noise points and need to be removed.
         */
        /**
         * @brief flag Whether to use auto noise removal.
         * If true, the noise_removal_distance and noise_removal_point_number will be ignored. It will automatically
         * adjust these two parameters according to the point cloud data and do noise removal.
         */
        bool use_auto_noise_removal;
        /**
         * @brief The smaller the value, the greater the filtering degree.
         * range: 0 ~ 20 (units: mm)
         */
        double noise_removal_distance;
        /**
         * @brief Set the noise filter parameter 2. The larger the value, the greater the filtering degree.
         */
        int noise_removal_point_number;

        /**
         * @brief uniform downsample distance. if <= 0, do nothing.
         *
         */
        double downsample_distance;

        /**
         * @brief control capture mode
         *
         */
        CaptureMode capture_mode;

        /**
         * @brief confidence threshold, the point with confindence low then this value will be removed
         * range: [0, 1]
         *
         */
        double confidence_threshold;
        /**
         * @brief scan times, only use in robust mode. range: [1, 8]
         */
        int scan_times;
        /**
         * @brief Set the hdr scan times, only use in robust mode. range: [1, 8]
         *
         */
        int hdr_scan_times[3];

        /**
         * @brief the kernal size of bilateral filter of depth map
         * range: [3, 31], 0 for not use bilateral filter
         *
         */
        [[deprecated("Use smooth_sigma instead")]] int bilateral_filter_kernal_size;

        /**
         * @brief the guassian sigma in depth of bilateral filter of depth map
         * range: [0, 100]
         *
         */
        [[deprecated("Use smooth_sigma instead")]] double bilateral_filter_depth_sigma;

        /**
         * @brief the guassian sigma in space of bilateral filter of depth map
         * range: [0, 100]
         *
         */
        [[deprecated("Use smooth_sigma instead")]] double bilateral_filter_space_sigma;

        /**
         * @brief Set line scanner mode's total scan time
         */
        int line_scanner_scan_time_ms;
        /**
         * @brief Set line scanner mode's single line exposure time
         */
        int line_scanner_exposure_time_us;
        /**
         * @brief Set line scanner mode's minimum working distance
         */
        int line_scanner_min_distance;
        /**
         * @brief Set line scanner mode's maximum working distance
         */
        int line_scanner_max_distance;

        /**
         * @brief whether to generate point clouds corresponding to 2D images
         *
         */
        bool correspond2d;

        /**
         * @brief select laser position in fixed line scan mode
         *
         */
        uint16_t line_scanner_laser_position;

        /**
         * @brief flag Whether to use auto bilateral filter.
         * If true, the bilateral_filter_kernal_size and bilateral_filter_depth_sigma and bilateral_filter_space_sigma
         * will be ignored. It will automatically adjust these three parameters according to the point cloud data and do
         * bilateral filter.
         */
        [[deprecated("Use smooth_sigma instead")]] bool use_auto_bilateral_filter;

        /**
         * @brief Used to remove large-area erroneous point clouds caused by reflections.
         * The higher this value is set, the more points will be removed by the reflection filter.
         * Setting it too large may remove data from thin and pointy objects.
         * range:[0, 30]
         */
        int reflection_filter_threshold;

        /**
         * @brief The Gaussian filters are used to smooth points.
         * The larger the smooth_sigma, the smoother the point cloud becomes. However, an excessively large smooth_sigma
         * can cause edges to be smoothed out as well.
         * range: [0, 5]
         */
        double smooth_sigma;

        /**
         * @brief set ROI function, only 3d points in the roi will be generated.
         * This function can improve 3d capture speed and only support SwingLineScan capture mode.
         * The parameters of roi must comply with the rules of the equipment and can be checked by CheckRoi.
         * We recommend that you adjust roi automatically through C before AutoAdjustRoi.
         */
        RVC::ROI roi;

        /**
         * @brief Acquire 2D images during capture
         */
        bool enable_2d_in_capture;

        /**
         * @brief In 'CaptureMode_SwingLineScan' mode with 'correspond2d' enabled,turning on 'pointcloud_completion'
         * will interpolate the point cloud to produce a dense reconstruction.
         */
        bool pointcloud_completion;

        /*
         * @brief Only laser lines with brightness greater than the 'line_scanner_brightness_threshold' will be
         * extracted by the algorithm. A higher threshold results in fewer extracted points, while a lower threshold
         * yields more points but may introduce additional noise. When scanning black objects, a lower threshold can be
         * used.
         *
         * range: [0, 200]
         *
         * default: 5
         */
        int line_scanner_brightness_threshold;

        /**
         * @brief Trigger mode. Currently, only the 'FixedLineScan' mode supports
         *        hardware triggering (TriggerMode_HardWare); all other modes only
         *        support software triggering (TriggerMode_SoftWare).
         */
        TriggerMode trigger_mode;

        /**
         * @brief Number of encoder pulses required to trigger one profile acquisition
         */
        int encoder_trigger_interval;

        /**
         * @brief truncate point map and depth map by z direction minimum value (units: mm)
         * and truncate_z_min should less than truncate_z_max range: [-29999, 29999]
         *
         */
        double truncate_z_min;

        /**
         * @brief truncate point map and depth map by z direction maximum value (units: mm)
         * and truncate_z_max should more than truncate_z_min range: [-29999, 29999]
         *
         */
        double truncate_z_max;

        /**
         * @brief Line scanner confidence threshold for point cloud filtering
         *
         * Sets the minimum confidence level for line scanner data points [0,1]
         * - Value 0: disables this filtering function
         * - Values >0: points with confidence below this value are removed and fixed when possible
         *
         * How it works:
         * - Higher values: more points removed (cleaner data)
         * - Lower values: more points kept (may include noise)
         * - Removes noise that clustering filters cannot remove
         * - Default 0.72 works well for most scenarios within the default working range
         *
         * Adjustment suggestions:
         * - 0.72 is optimal for most scenarios within the default working range
         * - For extended ranges (e.g., scanning distant objects), consider lowering this value
         *
         * Warning: Setting too high may remove valid data points
         */
        double line_scanner_confidence;

        /**
         * @brief Fixed-rate trigger frequency in Hz
         *
         * Specifies the internal trigger frequency in TriggerMode_FixedRate mode.
         *
         * @details
         * - Unit: Hertz (Hz), frames per second
         * - Only effective when TriggerMode = TriggerMode_FixedRate
         * - Behavior:
         *   - If auto_set_fixed_rate = true: ignored, camera auto-estimates rate
         *   - If auto_set_fixed_rate = false: use specified frequency
         *
         * @note Automatic rate estimation provides a relatively safe value but doesn't guarantee no frame drops.
         */
        double fixed_rate;

        /**
         * @brief Enable automatic fixed rate estimation
         *
         * When true: camera auto-estimates trigger rate, ignoring fixed_rate.
         * When false: manual fixed_rate setting takes effect.
         *
         * @note Automatic rate estimation provides a relatively safe value but doesn't guarantee no frame drops.
         */
        bool auto_set_fixed_rate;

        /**
         * @brief Enable transfer control
         *
         * When true: Network transmission is more stable, but data may be lost if the buffer is full.
         * When false: Network transmission is faster, but packet loss may occur.
         *
         */
        bool enable_transfer_control;
    };
    /**
     * @brief Options when setting custom transformation
     *
     */
    struct CustomTransformOptions {
        /**
         * @brief base coordinate of custom transformation,default is *CoordinateSelect_Disabled*
         *
         * All support type is
         * *CoordinateSelect_Disabled*,*CoordinateSelect_CameraLeft*,*CoordinateSelect_CameraRight*,*CoordinateSelect_CaliBoard*
         */
        enum CoordinateSelect {
            CoordinateSelect_Disabled,
            CoordinateSelect_CameraLeft,
            CoordinateSelect_CameraRight,
            CoordinateSelect_CaliBoard,
            CoordinateSelect_CameraExtra,
        };

        CustomTransformOptions()
            : coordinate_select(CoordinateSelect_Disabled), transform{1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1} {}

        /**
         * @brief base coordinate setting of custom transformation
         *
         */
        CoordinateSelect coordinate_select;

        /**
         * @brief custom transformation, translation unit: m
         *
         */
        double transform[16];
    };

    /**
     * @brief X2 CollectionCallBackInfo
     */
    struct CollectionCallBackInfo {
        Image image[2];
    };

    /**
     * @brief X2 CalculationCallBackInfo
     */
    struct CalculationCallBackInfo {
        Image image[2];
        PointMap pointmap;
        DepthMap depthmap;
        ConfidenceMap confidencemap;
    };

    /**
     * @struct FixedLineScanCallBackInfo
     * @brief Callback information structure for fixed-line scan mode
     *
     * Contains point cloud data and indices for each trigger event in fixed-line scan mode.
     * Used only with CaptureMode_FixedLineScan when trigger mode is set to
     * TriggerMode_HardWare or TriggerMode_FixedRate.
     */
    struct FixedLineScanCallBackInfo {
        /**
         * @brief Point cloud data for the current trigger event
         */
        RVC::PointMap pointmap;

        /**
         * @brief Sequential frame index (0, 1, 2, ...)
         *
         * Increments continuously regardless of frame drops.
         * Always increases by 1 between consecutive frames.
         */
        int pointmap_index;

        /**
         * @brief Encoder/trigger event index (0, 1, 2, ...)
         *
         * May skip values when frames are dropped.
         * Use for spatial positioning and stitching.
         */
        int encoder_index;
    };

    /**
     * @brief X2 CallBackPtr
     */
    typedef void (*CollectionCallBackPtr)(X2::CollectionCallBackInfo, X2::CaptureOptions, UserPtr);
    typedef void (*CalculationCallBackPtr)(X2::CalculationCallBackInfo, X2::CaptureOptions, UserPtr);

    typedef void (*FixedLineScanCallBackPtr)(X2::FixedLineScanCallBackInfo, UserPtr);

    /**
     * @brief Create a RVC X Camera before you use x2
     *
     * @param d One RVC X Camera
     * @return X2 RVC X object
     */
    static X2 Create(const Device &d);
    /**
     * @brief Release all X2 resources after you use X2
     *
     * @param x RVC X2 object to be released
     */
    static void Destroy(X2 &x);

    /**
     * @brief Check X2 is valid or not before use X2
     *
     * @return true Available
     * @return false Not available
     */
    bool IsValid();
    /**
     * @brief Open X2 before you use it
     *
     * @return true Success
     * @return false Failed
     */
    bool Open();
    /**
     * @brief Close X2 after you Open it
     */
    void Close();
    /**
     * @brief Check X2 is open or not
     *
     * @return true Is open
     * @return false Not open
     */
    bool IsOpen();
    /**
     * @brief Check X2 is physically connected or not
     *
     * @return true Is physically connected
     * @return false Not physically connected
     */
    bool IsPhysicallyConnected();
    /**
     * @brief Open ProtectiveCover
     *
     * @return true if success
     * @return false if failed
     */
    bool OpenProtectiveCover();
    /**
     * @brief Open ProtectiveCover Async
     *
     * @return true if success
     * @return false if failed
     */
    bool OpenProtectiveCoverAsync();
    /**
     * @brief Close ProtectiveCover
     *
     * @return true if success
     * @return false if failed
     */
    bool CloseProtectiveCover();
    /**
     * @brief Close ProtectiveCover Async
     *
     * @return true if success
     * @return false if failed
     */
    bool CloseProtectiveCoverAsync();
    /**
     * @brief Reset ProtectiveCover
     *
     * @return true if success
     * @return false if failed
     */
    bool ResetProtectiveCover();
    /**
     * @brief Get Status of ProtectiveCover
     * @return ProtectiveCoverStatus
     */
    bool GetProtectiveCoverStatus(ProtectiveCoverStatus &status);
    /**
     * @brief Provide a callback to RVC system and it will be called when collection finished.
     * @param cb The callback
     * @param ctx The user-pointer
     *
     * @return true when succeed to set
     * @return false when failed to set
     *
     * @snippet CaptureCallBack.cpp
     */
    bool SetCollectionCallBack(X2::CollectionCallBackPtr cb, UserPtr ctx);
    /**
     * @brief Provide a callback to RVC system and it will be called when calculation finished.
     * @param cb The callback
     * @param ctx The user-pointer
     *
     * @return true when succeed to set
     * @return false when failed to set
     *
     * @snippet CaptureCallBack.cpp
     */
    bool SetCalculationCallBack(X2::CalculationCallBackPtr cb, UserPtr ctx);

    /**
     * @brief Capture one point map and one image.This function will save capture options into camera.
     *
     * @param opts CaptureOptions
     * @return true Success
     * @return false Failed
     */
    bool Capture(const CaptureOptions &opts);
    /**
     * @brief Capture one point map and one image.This function will load capture options from camera.
     *
     * @return true Success
     * @return false Failed
     */
    bool Capture();

    /**
     * @brief Start capture fixed line scan. Only support CaptureMode_FixedLineScan mode. This function will save
     * capture options into camera. Need to call the StopFixedLineScan interface to manually stop
     * @param opts CaptureOptions
     * @return true Success
     * @return false Failed
     */
    bool StartFixedLineScan(const CaptureOptions &opts);

    /**
     * @brief Start capture fixed line scan. Only support CaptureMode_FixedLineScan mode.
     * Need to call the StopFixedLineScan interface to manually stop
     *
     * @return true Success
     * @return false Failed
     */
    bool StartFixedLineScan();

    /**
     * @brief Get fixed line scan point map
     *
     * @return PointMap
     */
    [[deprecated("Use bool GetFixedLineScanPointMap(PointMap &point_map) instead")]] PointMap
    GetFixedLineScanPointMap();

    /**
     * @brief Get fixed line scan point map
     *
     * @return true Success
     * @return false Failed
     */
    bool GetFixedLineScanPointMap(PointMap &point_map);

    /**
     * @brief Stop capture fixed line scan.
     *
     * @return true Success
     * @return false Failed
     */
    bool StopFixedLineScan();

    /**
     * @brief
     *
     * @param cid Capture one image. This function will save capture options into camera. You can use GetImage() to
     * obtain 2D imgae
     * @param opts CaptureOptions
     * @return true Success
     * @return false Failed
     */
    bool Capture2D(const CameraID cid, const CaptureOptions &opts);
    /**
     * @brief
     *
     * @param cid Capture one image. This function will load capture options from camera. You can use GetImage() to
     * obtain 2D imgae
     * @return true Success
     * @return false Failed
     */
    bool Capture2D(const CameraID cid);
    /**
     * @brief Set the camera band width ratio
     *
     * @param percent Band width ratio
     * @return true Success
     * @return false Failed
     */
    bool SetBandwidth(float percent);

    /**
     * @brief Get the camera band width ratio
     *
     * @param percent Band width ratio
     * @return true Success
     * @return false Failed
     */
    bool GetBandwidth(float &percent);

    /**
     * @brief Set the Transformation of output point cloud
     *
     * @param opts  Custom Transform Options
     * @return true
     * @return false
     */
    bool SetCustomTransformation(const CustomTransformOptions &opts);

    /**
     * @brief Get the Custom Transformation object
     *
     * @param opts
     * @return true
     * @return false
     */
    bool GetCustomTransformation(CustomTransformOptions &opts);

    /**
     * @brief Get the Point Map object
     *
     * @return PointMap
     */
    PointMap GetPointMap();
    /**
     * @brief Get the Image object
     *
     * @return Image
     */
    Image GetImage(const CameraID cid);

    /**
     * @brief Get the DepthMap object
     *
     * @return DepthMap A DepthMap
     */
    DepthMap GetDepthMap();

    /**
     * @brief Get the Confidence Map object
     *
     * @return ConfidenceMap
     */
    ConfidenceMap GetConfidenceMap();
    /**
     * @brief Get the Correspond Map object
     *
     * @return Correspond
     */
    CorrespondMap GetCorrespondMap();

    /**
     * @brief Get the extrinsic matrix (transformation from calibration board to specified camera)
     * @param cid [in] Camera selection option. Available values: {CameraID_Left, CameraID_Right, CameraID_Extra}
     * @param matrix [out] 4x4 transformation matrix stored as a 16-element array in row-major order.
     *                     The matrix represents the transformation from the calibration board coordinate system
     *                     to the specified camera coordinate system.
     *                     Format: [R11, R12, R13, T1,
     *                             R21, R22, R23, T2,
     *                             R31, R32, R33, T3,
     *                             0,   0,   0,   1]
     *                     Where R is the 3x3 rotation matrix and T is the 3x1 translation vector.
     * @return true Success
     * @return false Failed
     */
    bool GetExtrinsicMatrix(const CameraID cid, float *matrix);

    /**
     * @brief Get intrinsic and distortion parameters of the specified camera.
     *
     * @param cid [in] Camera selection option. Available values: {CameraID_Left, CameraID_Right, CameraID_Extra}
     * @param instrinsicMatrix [out] Output intrinsic matrix. This is a 9-element array storing
     *                               a 3x3 matrix in row-major order: [fx, 0, cx, 0, fy, cy, 0, 0, 1]
     *                               - fx, fy: Focal lengths in x and y directions (in pixels)
     *                               - cx, cy: Principal point coordinates (in pixels)
     * @param distortion [out] Output distortion coefficients. This is a 5-element array containing:
     *                         [k1, k2, k3, p1, p2]
     *                         - k1, k2, k3: Radial distortion coefficients
     *                         - p1, p2: Tangential distortion coefficients
     *                         Note: This order is different from OpenCV's default order (k1,k2,p1,p2,k3).
     * @return true if successful
     * @return false if failed
     */
    bool GetIntrinsicParameters(const CameraID cid, float *instrinsicMatrix, float *distortion);
    /**
     * @brief  GetProjectorTemperature
     * @param  &temperature:
     * @return true Success
     * @return false Failed
     */
    bool GetProjectorTemperature(float &temperature);
    /**
     * @brief  GetCameraTemperature
     * @note   TODO:
     * @param  cid:
     * @param  seletor:
     * @param  &temperature:
     * @retval
     */
    [[deprecated]] bool GetCameraTemperature(const CameraID cid, CameraTempSelector seletor, float &temperature);
    /**
     * @brief Only Color Camera can use this function. This function can get suitable white balance paramters
     *
     * @param wb_times how many images used for calculate the white balance paramters
     * @param opts capture options. exposure_time_2d, gain_2d, gamma_2d will be used. use_projector_capturing_2d_image
     * == true, brightness will be used too.
     * @param roi auto white balance will be operated here
     * @return true
     * @return false
     */
    bool AutoWhiteBalance(int wb_times = 10, const CaptureOptions &opts = CaptureOptions(),
                          const RVC::ROI &roi = RVC::ROI());
    /**
     * @brief Get the Exposure Time Range
     *
     * @param min_value exposure time minimum value
     * @param max_value exposure time maxinum value
     * @return true Success
     * @return false Failed
     */
    bool GetExposureTimeRange(int *min_value, int *max_value);
    /**
     * @brief Get the Gain Range
     *
     * @param min_value gain minimum value
     * @param max_value gain minimum value
     * @return true Success
     * @return false Failed
     */
    bool GetGainRange(float *min_value, float *max_value);
    /**
     * @brief Get the Gamma Range
     *
     * @param min_value gamma minimum value
     * @param max_value gamma minimum value
     * @return true Success
     * @return false Failed
     */
    bool GetGammaRange(float *min_value, float *max_value);
    /**
     * @brief Save encoded map in txt
     *
     * @return true
     * @return false
     */
    bool SaveEncodedImagesData(const char *addr);

    /**
     * @brief Save capture option parameters
     *
     * @param opts CaptureOptions
     * @return true Success
     * @return false Failed
     */
    bool SaveCaptureOptionParameters(const X2::CaptureOptions &opts);

    /**
     * @brief Get capture option parameters
     *
     * @param opts CaptureOptions
     * @return true Success
     * @return false Failed
     */
    bool LoadCaptureOptionParameters(X2::CaptureOptions &opts);

    /**
     * @brief Get auto capture setting. Exposure_time_2d, exposure_time_3d, projector_brightness,
     * light_contrast_threshold will be adjusted automatically. automatically
     *
     * @param opts
     * @return CaptureOptions
     */
    bool GetAutoCaptureSetting(CaptureOptions &opts, const ROI &roi = ROI());

    /**
     * @brief adjust 3D capturing parameters
     *
     * @param opts [in,out] capture options. if  hdr_exposure_times > 1, hdr_exposure_times and hdr_exposuretime_content
     * will be adjusted. If hdr_exposure_times equals to 1, exposure_time_3d will be adjusted.
     * @param roi [in] if width or height equal to 0, all image will be used.
     * @return true
     * @return false
     */
    bool GetAutoHdrCaptureSetting(CaptureOptions &opts, const ROI &roi);

    /**
     * @brief Automatically calculates and applies the optimal point cloud noise removal parameters.
     *
     * WARNING: This is a time-consuming operation as it triggers actual camera captures.
     * This function evaluates the current scene to determine the best cluster-based noise
     * removal settings and applies them to the current point cloud.
     *
     * @param[in,out] opts Capture options. Upon successful execution, the following parameters
     * inside this struct will be modified and overwritten:
     * - `opts.noise_removal_distance`
     * - `opts.noise_removal_point_number`
     * @return true The automatic noise removal parameters were successfully calculated and applied.
     * @return false The operation failed (e.g., camera not ready or capture failed).
     */
    bool GetAutoNoiseRemovalSetting(CaptureOptions &opts);

    /**
     * @brief Load camera setting from local file .
     * @param filename [in]
     * @return true the content of file is correctly .
     * @return false the content of file is not correctly .
     */
    bool LoadSettingFromFile(const char *filename);

    /**
     * @brief Save camera setting to local file.
     * @param filename [in]
     * @return true Successfully written to the file.
     * @return false Failed write to file.
     */
    bool SaveSettingToFile(const char *filename);

    /**
     * @brief Check whether the parameters of ROI meet the requirements.
     * @param roi [in] .
     * @return true
     * @return false
     */
    bool CheckRoi(ROI roi);

    /**
     * @brief Automatically correct the parameters of ROI. You need to correct ROI before Capture/Captrue2D.
     * @param roi [in] If you want to get a maximum ROI, you can pass in the default value.
     * @return ROI Corrected ROI.
     */
    ROI AutoAdjustRoi(ROI roi = ROI());

    /**
     * @brief Get the range of ROI.
     */
    bool GetRoiRange(ROIRange &range);

    /**
     * @brief Get Camera Resolution
     *
     * @param resolution
     * @return true
     * @return false
     */
    bool GetCameraResolution(Size &resolution);

    /**
     * @brief Get the Mesh object
     *
     * @return Mesh A Mesh
     */
    Mesh GetMesh();

    /**
     * @brief Registers callback for point cloud results in fixed line scan mode.
     *
     * Invoked for each completed line scan when using hardware-triggered
     * or fixed-rate triggered mode.
     *
     * Must be called before StartFixedLineScan().
     *
     * @param cb Callback function.
     * @param ctx User context pointer. Must remain valid during scanning.
     *
     * @return true if registration succeeded, false otherwise.
     *
     * @note Use with CaptureMode_FixedLineScan and TriggerMode_HardWare or TriggerMode_FixedRate.
     * @note Callback must be thread-safe (invoked from multiple threads).
     */
    bool SetFixedLineScanCallback(const X2::FixedLineScanCallBackPtr cb, UserPtr ctx);

    /**
     * @brief Retrieves the camera timestamp in microseconds (us)
     *
     * @param[out] timestamp Reference to store the retrieved timestamp value in microseconds (us)
     * @return bool True if the timestamp was successfully retrieved, false otherwise
     */
    bool GetTimestamp(uint64_t &timestamp);

    /**
     * @brief Resets the camera timestamp to zero
     *
     * Resets the internal camera timestamp value to 0 microseconds(us).
     * This function is primarily used for synchronization with user clocks
     * or external timing references, allowing the camera's internal time
     * base to be aligned with user-defined timing requirements or to
     * initiate a new timing cycle based on user control.
     *
     * @return bool True if the timestamp was successfully reset to zero, false otherwise
     */
    bool ResetTimestamp();

    /**
     * @brief Get auto 2d exposure time automatically
     * @param opts [in]
     * @param roi [in]
     * @return true
     * @return false
     */
    bool GetAuto2DExposureTime(CaptureOptions &opts, const ROI &roi = ROI());

    /**
     * @brief Set Current User Set by id. The user can utilize a total of 10 parameters groups to
     * quickly adjust camera settings for different 3d imaging scenarios.
     *
     * @param id [in] 0~9
     * @return true
     * @return false
     */
    bool SetCurrentUserSet(const int &id);

    /**
     * @brief Get Current User Set's id.
     *
     * @param id [out] 0~9
     * @return true
     * @return false
     */
    bool GetCurrentUserSet(int &id);

    /**
     * @brief Set User Set's name with id. The user can briefly describe the usage scenario of this
     * parameters groups by using a name.
     *
     * @param id [in]
     * @param name [in]
     * @return true
     * @return false
     */
    bool SetUserSetName(const int &id, const char *name);

    /**
     * @brief Get Current User Set's name with id.
     *
     * @param id [in]
     * @param name [out]
     * @return true
     * @return false
     */
    bool GetUserSetName(const int &id, char *name);

    Handle m_handle;
};

// You can use these to better get and set.
namespace utils {
struct Point3D {
    Point3D(double x = 0.0, double y = 0.0, double z = 0.0) : x(x), y(y), z(z) {}
    double x;
    double y;
    double z;
};

// Helper class upon RVC::PointMap to ease data-access
struct PointMap {
    PointMap(RVC::PointMap pm) : pm(pm) {}
    Point3D At(int rows, int cols) {
        Point3D p;
        auto sz = pm.GetSize();
        if (!pm.IsValid()) {
            printf("RVC::Utils: Invalid");
            assert(false);
        } else if (rows >= sz.rows || cols >= sz.cols) {
            printf("RVC::Utils: Invalid rows and cols(%d, %d), size(%d, %d)", rows, cols, sz.rows, sz.cols);
            assert(false);
        } else {
            double *data = pm.GetPointDataPtr() + 3 * (rows * sz.cols + cols);
            p.x = *data++;
            p.y = *data++;
            p.z = *data++;
        }
        return p;
    }
    void Set(int rows, int cols, const Point3D p) {
        auto sz = pm.GetSize();
        if (!pm.IsValid()) {
            printf("RVC::Utils: Invalid");
            assert(false);
        } else if (rows >= sz.rows || cols >= sz.cols) {
            printf("RVC::Utils: Invalid rows and cols(%d, %d), size(%d, %d)", rows, cols, sz.rows, sz.cols);
            assert(false);
        } else {
            double *data = pm.GetPointDataPtr() + 3 * (rows * sz.cols + cols);
            *data++ = p.x;
            *data++ = p.y;
            *data++ = p.z;
        }
    }

    RVC::Size GetSize() { return pm.GetSize(); }

    RVC::PointMap pm;
};

template <typename T, typename H>
T _At(H handle, int rows, int cols) {
    T v = 0;
    RVC::Size sz = handle.GetSize();
    if (!handle.IsValid()) {
        printf("RVC::Utils: Invalid");
        assert(false);
        return v;
    } else if (rows >= sz.rows || cols >= sz.cols) {
        printf("RVC::Utils: Invalid rows and cols(%d, %d), size(%d, %d)", rows, cols, sz.rows, sz.cols);
        assert(false);
        return v;
    } else {
        return *(handle.GetDataConstPtr() + rows * sz.cols + cols);
    }
}

template <typename T, typename H>
void _Set(H handle, int rows, int cols, const T v) {
    RVC::Size sz = handle.GetSize();
    if (!handle.IsValid()) {
        printf("RVC::Utils: Invalid");
        assert(false);
    } else if (rows >= sz.rows || cols >= sz.cols) {
        printf("RVC::Utils: Invalid rows and cols(%d, %d), size(%d, %d)", rows, cols, sz.rows, sz.cols);
        assert(false);
    } else {
        *(handle.GetDataPtr() + rows * sz.cols + cols) = v;
    }
}

// Helper class upon RVC::Image to ease data-access
struct Image {
    Image(RVC::Image img) : img(img) {}
    unsigned char At(int rows, int cols) { return _At<unsigned char>(img, rows, cols); }
    void Set(int rows, int cols, const unsigned char v) { _Set(img, rows, cols, v); }
    RVC::Size GetSize() { return img.GetSize(); }

    RVC::Image img;
};

// Helper class upon RVC::ConfidenceMap to ease data-access
struct ConfidenceMap {
    ConfidenceMap(RVC::ConfidenceMap cm) : cm(cm) {}
    double At(int rows, int cols) { return _At<double>(cm, rows, cols); }
    void Set(int rows, int cols, const double v) { _Set(cm, rows, cols, v); }
    RVC::Size GetSize() { return cm.GetSize(); }

    RVC::ConfidenceMap cm;
};

// Helper class upon RVC::DepthMap to ease data-access
struct DepthMap {
    DepthMap(RVC::DepthMap dm) : dm(dm) {}
    double At(int rows, int cols) { return _At<double>(dm, rows, cols); }
    void Set(int rows, int cols, const double v) { _Set(dm, rows, cols, v); }
    RVC::Size GetSize() { return dm.GetSize(); }

    RVC::DepthMap dm;
};
}  // namespace utils
}  // namespace RVC