using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Collections.Generic;
using System.Diagnostics;

namespace RVC_CSharp
{
    #region Basic Enum

    /**
     * @brief NetworkDevieStatus, support *NetworkDeviceStatus_OK*, *NetworkDeviceStatus_Not_Reachable*,
     * *NetworkDeviceStatus_In_Use* and *NetworkDeviceStatus_Conflict*
     *
     */
    public enum NetworkDeviceStatus_
    {
        NetworkDeviceStatus_OK,
        NetworkDeviceStatus_Not_Reachable,
        NetworkDeviceStatus_In_Use,
        NetworkDeviceStatus_Conflict,
    };

    /// <summary>
    /// System list Device type
    /// All support type are *USB*, *GigE*, *ALL*
    /// </summary>
    public enum SystemListDeviceType
    {
        None = 0,
        USB = 1 << 0,
        GigE = 1 << 1,
        All = USB | GigE,
    };

    /// <summary>
    /// NetworkDevice
    /// support *NetworkDevice_LightMachine*, *NetworkDevice_LeftCamera* and *NetworkDevice_RightCamera* NetworkDevice_ExtraCamera*
    /// </summary>
    public enum NetworkDevice
    {
        NetworkDevice_LightMachine = 0,
        NetworkDevice_LeftCamera = 1,
        NetworkDevice_RightCamera = 2,
        NetworkDevice_ExtraCamera = 3,
    };

    /// <summary>
    /// RVC supported Camera Network type
    /// Only valid when Camera PortType is *PortType_GIGE*
    /// All support type is *NetworkType_DHCP*, *NetworkType_STATIC*
    /// </summary>
    public enum NetworkType
    {
        NetworkType_DHCP = 0,
        NetworkType_STATIC = 1,
    };

    /// <summary>
    /// CaptureMode
    /// support *CaptureMode_Fast*, *CaptureMode_Normal*,*CaptureMode_Ultra*,*CaptureMode_Robust*,*CaptureMode_AntiInterReflection*,
    /// </summary>
    [Flags]
    public enum CaptureMode
    {
        CaptureMode_Fast = 1 << 0,
        CaptureMode_Normal = 1 << 1,
        CaptureMode_Ultra = 1 << 2,
        CaptureMode_Robust = 1 << 3,
        CaptureMode_AntiInterReflection = 1 << 4,
        CaptureMode_SwingLineScan = 1 << 5,
        CaptureMode_FixedLineScan = 1 << 6,
        CaptureMode_LineArrayShift = 1 << 7,
        CaptureMode_All = CaptureMode_Fast | CaptureMode_Normal | CaptureMode_Ultra | CaptureMode_Robust |
                          CaptureMode_AntiInterReflection | CaptureMode_SwingLineScan | CaptureMode_FixedLineScan |
            CaptureMode_LineArrayShift,
    };

    public enum TriggerMode
    {
        TriggerMode_SoftWare = 0,
        TriggerMode_HardWare = 1,
        TriggerMode_FixedRate = 2,
    };

    /// <summary>
    /// Projector color
    /// support *ProjectorColor_Red*, *ProjectorColor_Green*, *ProjectorColor_Blue*,*ProjectorColor_White* and *ProjectorColor_ALL*
    /// </summary>
    public enum ProjectorColor
    {
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
    public enum ProtectiveCoverStatus
    {
        ProtectiveCoverStatus_Unknown = 0,
        ProtectiveCoverStatus_Closed = 1,
        ProtectiveCoverStatus_Closing = 2,
        ProtectiveCoverStatus_Open = 3,
        ProtectiveCoverStatus_Opening = 4,
    };

    /// <summary>
    /// CameraID
    /// support *CameraID_Left* , *CameraID_Right*, *CameraID_Both*
    /// </summary>
    public enum CameraID
    {
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

    /// <summary>
    /// RVC supported Camera Port type
    /// All support type is *PortType_USB*, *PortType_GIGE*
    /// </summary>
    public enum PortType
    {
        PortType_NONE = 0,
        PortType_USB = 1,
        PortType_GIGE = 2,
    };

    /// <summary>
    /// 
    /// </summary>
    public enum SmoothnessLevel
    {
        SmoothnessLevel_Off,
        SmoothnessLevel_Weak,
        SmoothnessLevel_Normal,
        SmoothnessLevel_Strong
    };

    /// <summary>
    /// 
    /// </summary>
    public enum CameraTempSelector
    {
        CameraTempSelector_Camera,
        CameraTempSelector_CoreBoard,
        CameraTempSelector_FpgaCore,
        CameraTempSelector_Framegrabberboard,
        CameraTempSelector_Sensor,
        CameraTempSelector_SensorBoard,
    };

    /**
     * @brief White balance ratio selector, suport *BalanceSelector_Red*, *BalanceSelector_Green* and *BalanceSelector_Blue*
     *
     */
    public enum BalanceSelector
    {
        BalanceSelector_None = 0,
        BalanceSelector_Red,
        BalanceSelector_Green,
        BalanceSelector_Blue,
    };

    /**
     * @brief Image Type
     *
     *  All support type are *Mono8*, *RGB8*, *BGR8*
     */
    public enum ImageType
    {
        None = 0,
        Mono8 = 1,
        RGB8 = 2,
        BGR8 = 3,
    };


    /**
     * @brief RVC X PointMap Type
     * @brief PointMap Type Support type *PointsOnly* and *PointsNormals*
     * @param PointsOnly which only contains points
     * @param PointsNormals which contains points with normals
     */
    public enum PointMapType
    {
        None = 0,
        PointsOnly = 1,
        PointsNormals = 2,
    };

    /**
     * @brief RVC X PointMap Unit
     * @brief PointMap Type Support type *Meter* and *Millimeter*
     */
    public enum PointMapUnit
    {
        Meter = 0,
        Millimeter = 1,
    }

    #endregion

    /// <summary>
    /// Marker type for compensation
    /// </summary>
    public enum CompensatorMarkerType
    {
        MarkerType_CalibrationBoard = 0,
        MarkerType_ConcentricCircle = 1
    };

    #region Common Function

    public static class Common
    {
        /**
         * @brief Print given ImageType
         *
         * @param type ImageType
         * @return const char* Name of ImageType
         */
        public static string ToString(ImageType type) => RVC_CSharp_DLL.ImageType_ToString(type);

        /**
         * @brief Get pixel size of ImageType
         *
         * @param type ImageType
         * @return size_t Pixel size
         */
        public static int GetPixelSize(ImageType type) => RVC_CSharp_DLL.ImageType_GetPixelSize(type);

        /**
        * @brief print PointMap Type`s name
        *
        * @param e Pointmap Type
        * @return const char* Pointmap Type`s name
        */
        public static string ToString(PointMapType type) => RVC_CSharp_DLL.PointMapType_ToString(type);

    }

    #endregion

    #region Basic Struct

    /**
     * @brief RVC Handle
     *
     */
    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct Handle
    {
        /**
         * @brief Construct a new Handle object with sid and gid
         *
         * @param sid_
         * @param gid_
         */
        //public Handle(int sid_, int gid_)
        //{
        //    this.sid = sid_;
        //    this.gid = gid_;
        //}
        public int sid;
        public int gid;
    };

    /// <summary>
    /// Compensator handle (C interface)
    /// </summary>
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct CCompensatorHandle
    {
        public IntPtr sid;
        public IntPtr gid;
    };

    /**
     * @brief Image/PointMap Size
     * In case of [union],the Size in CSharp is different from the Size in cpp.
     */
    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct Size
    {
        /**
         * @brief Construct a new Image/PointMap Size object with width/cols and height/rows
         *
         * @param w Image width/PointMap cols
         * @param h Image height/PointMap rows
         */
        public Size(int w, int h)
        {
            width = w;
            height = h;
        }

        /**
         * @brief width or cols
         *
         */
        public int width;
        /**
         * @brief height or rows
         *
         */
        public int height;
    };

    /**
     * @brief RVC X Image object
     *
     */
    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct Image
    {
        /**
         * @brief RVC Handle
         *
         */
        public Handle m_handle;

        /**
         * @brief Create Image object
         *
         * @param it image type
         * @param sz image size
         * @param data image data
         * @param own_data Image object
         * @return Image A Image object with given parameters
         */
        public static Image Create(ImageType type, Size sz, IntPtr data, bool own_data = true) =>
            new Image() { m_handle = RVC_CSharp_DLL.Image_Create(type, sz, data, own_data) };

        public static Image CreateFromFile(string addr) =>
            new Image() { m_handle = RVC_CSharp_DLL.Image_CreateFromFile(addr) };
        /**
         * @brief Destroy Image object
         *
         * @param img Image object will be destroyed
         * @param no_reuse True for reuse current space of PointMap
         */
        public static void Destroy(Image img, bool no_reuse = true) => RVC_CSharp_DLL.Image_Destroy(img.m_handle, no_reuse);

        /**
         * @brief Check Image obejct is Valid or not.
         *
         * @return true Valid
         * @return false Not valid
         */
        public bool IsValid() => RVC_CSharp_DLL.Image_IsValid(m_handle);

        /**
         * @brief Get the Image Size object
         *
         * @return Size A Image Size object
         */
        public Size GetSize() => RVC_CSharp_DLL.Image_GetSize(m_handle);

        /**
         * @brief Get the ImageType object
         *
         * @return ImageType Image type
         */
        public ImageType GetType() => RVC_CSharp_DLL.Image_GetType(m_handle);

        /**
         * @brief Get the Data Ptr of Image object
         *
         * @return unsigned* Data Ptr
         */
        public IntPtr GetDataPtr() => RVC_CSharp_DLL.Image_GetDataPtr(m_handle);

        /**
         * @brief Save Image to file
         *
         * @param address save address
         *
         * @return true Success
         * @return false Failed
         */
        public bool SaveImage(string addr) => RVC_CSharp_DLL.Image_SaveImage(m_handle, addr);

        /**
         * @brief Retrieves the timestamp of the Image in microseconds (us)
         */
        public UInt64 GetTimestamp() => RVC_CSharp_DLL.Image_GetTimestamp(m_handle);

        /**
         * @brief Sets the timestamp for the Image in microseconds (us)
         */
        public bool SetTimestamp(UInt64 timestamp) => RVC_CSharp_DLL.Image_SetTimestamp(m_handle, timestamp);

    };

    /**
     * @brief RVC X DepthMap
     *
     */
    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct DepthMap
    {

        /**
         * @brief DepthMap Handle
         *
         */
        public Handle m_handle;

        /**
         * @brief Create DepthMap object
         *
         * @param sz depthmap size
         * @param data depthmap data
         * @param own_data depthmap data
         * @return DepthMap object with given parameters
         */
        public static DepthMap Create(Size sz, IntPtr data, bool own_data = true)
            => new DepthMap() { m_handle = RVC_CSharp_DLL.DepthMap_Create(sz, data, own_data) };

        /**
         * @brief Destroy DepthMap object
         *
         * @param depthmap DepthMap object will be destroyed
         * @param no_reuse True for reuse current space of PointMap
         */
        public static void Destroy(DepthMap depthmap, bool no_reuse = true) =>
            RVC_CSharp_DLL.DepthMap_Destroy(depthmap.m_handle, no_reuse);

        /**
         * @brief Check DepthMap obejct is Valid or not.
         *
         * @return true
         * @return false
         */
        public bool IsValid() => RVC_CSharp_DLL.DepthMap_IsValid(m_handle);

        /**
         * @brief Get the DepthMap Size object
         *
         * @return Size
         */
        public Size GetSize() => RVC_CSharp_DLL.DepthMap_GetSize(m_handle);

        /**
         * @brief Get the Data Ptr of DepthMap. Data unit is m, so it will be very small.
         * 
         * @return double* Data Ptr
         */
        public IntPtr GetDataPtr() => RVC_CSharp_DLL.DepthMap_GetDataPtr(m_handle);

        /**
         * @brief Save DepthMap to file
         *
         * @param address save address
         * @param is_m  save depthmap with m/mm
         *
         * @return true Success
         * @return false Failed
         */
        public bool SaveDepthMap(string address, bool is_m = true) => RVC_CSharp_DLL.DepthMap_SaveDepthMap(m_handle, address, is_m);
    };

    /**
     * @brief RVC X PointMap
     *
     */
    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct PointMap
    {
        /**
         * @brief RVC Handle
         *
         */
        public Handle m_handle;

        /**
         * @brief Create PointMap object
         *
         * @param pmt PointMapType
         * @param size PointMap Size
         * @param data PointMap data (m)
         * @param owndata True for malloc a new space for PointMap
         * @return PointMap A PointMap object
         */
        public static PointMap Create(PointMapType type, Size sz, IntPtr data, bool own_data = true)
            => new PointMap() { m_handle = RVC_CSharp_DLL.PointMap_Create(type, sz, data, own_data) };

        public static PointMap CreateFromFile(string file, Size sz, PointMapUnit unit)
            => new PointMap() { m_handle = RVC_CSharp_DLL.PointMap_CreateFromFile(file, sz, unit) };

        /**
         * @brief Destroy a PointMap object
         *
         * @param pm PointMap object will be destroyed
         * @param no_reuse True for reuse current space of PointMap
         */
        public static void Destroy(PointMap pm, bool no_reuse = true) => RVC_CSharp_DLL.PointMap_Destroy(pm.m_handle, no_reuse);

        /**
         * @brief Check PointMap is Valid or not
         *
         * @return true Valid
         * @return false Not valid
         */
        public bool IsValid() => RVC_CSharp_DLL.PointMap_IsValid(m_handle);

        /**
         * @brief Get the PointMap Size object
         *
         * @return Size PointMap Size
         */
        public Size GetSize() => RVC_CSharp_DLL.PointMap_GetSize(m_handle);

        /**
         * @brief Get the Point Data Ptr of PointMap object
         *
         * @return double* Point Data Ptr (m)
         */
        public IntPtr GetPointDataPtr() => RVC_CSharp_DLL.PointMap_GetPointDataPtr(m_handle);

        /**
         * @brief Get the Normal Data Ptr of PointMap object
         *
         * @return double* Normal Data Ptr
         */
        public IntPtr GetNormalDataPtr() => RVC_CSharp_DLL.PointMap_GetNormalDataPtr(m_handle);

        /**
         * @brief export PointMap's data to local file. Only support the *.ply* format.
         * @param fileName Name of file to be created.
         * @param unit The unit of exported data.
         * @param isBinary Whether to export to binary format.
         * @return bool.
        */
        public bool Save(string filename, PointMapUnit unit, bool isBinary, Image image = new Image()) =>
            RVC_CSharp_DLL.PointMap_Save(m_handle, filename, unit, isBinary, image.m_handle);

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
        public bool GetPointMapSeperated(out double[] x, out double[] y, out double[] z, double scale = 1.0)
        {
            var size = this.GetSize();
            var count = size.width * size.height;
            x = new double[count];
            y = new double[count];
            z = new double[count];
            return GetPointMapSeperated(x, y, z, scale);
        }

        /**
        * @brief Retrieves the timestamp of the PointMap
        *
        * Returns the timestamp value representing the acquisition time
        * of the point cloud data. The timestamp is measured in
        * microseconds (µs).
        *
        * @return UInt64  Timestamp value in microseconds (µs)
        */
        public UInt64 GetTimestamp() => RVC_CSharp_DLL.PointMap_GetTimestamp(m_handle);

        /**
        * @brief Sets the timestamp for the PointMap
        *
        * Updates the timestamp value associated with the PointMap data.
        * The timestamp should represent the acquisition time of the point cloud data
        * and must be provided in microseconds (µs).
        *
        * @param timestamp Timestamp value in microseconds (µs) to be set
        * @return bool True if the timestamp was successfully set, false otherwise
        */
        public bool SetTimestamp(UInt64 timestamp) => RVC_CSharp_DLL.PointMap_SetTimestamp(m_handle, timestamp);

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
        private bool GetPointMapSeperated(double[] x, double[] y, double[] z, double scale = 1.0) =>
            RVC_CSharp_DLL.PointMap_GetPointMapSeperated(m_handle, x, y, z, scale);
    };

    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct Mesh
    {
        /**
         * @brief Mesh handle
         *
         */
        public Handle m_handle;

        /**
         * @brief Check Mesh is Valid or not
         *
         * @return true Valid
         * @return false Not valid
         */
        public bool IsValid() => RVC_CSharp_DLL.Mesh_IsValid(m_handle);

        /**
         * @brief Save Mesh to file. Only support the *.stl* format.
         * @param filename Name of file to be created.
         * @param unit The unit of exported data.
         * @return bool.
         */
        public bool Save(string filename, PointMapUnit unit = PointMapUnit.Meter) =>
            RVC_CSharp_DLL.Mesh_Save(m_handle, filename, unit);

        /**
         * @brief Destroy a Mesh object
         *
         * @param mesh Mesh object will be destroyed
         * @param no_reuse True for reuse current space of Mesh
         */
        public static void Destroy(Mesh mesh, bool no_reuse = true) => RVC_CSharp_DLL.Mesh_Destroy(mesh.m_handle, no_reuse);
    };

    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct CorrespondMap
    {
        /**
         * @brief correspond map handle
         *
         */
        public Handle m_handle;

        public static CorrespondMap Create(Size sz, IntPtr data, bool own_data = true) =>
            new CorrespondMap() { m_handle = RVC_CSharp_DLL.CorrespondMap_Create(sz, data, own_data) };


        public static void Destroy(CorrespondMap correspondMap, bool no_reuse = true) =>
            RVC_CSharp_DLL.CorrespondMap_Destroy(correspondMap.m_handle, no_reuse);

        /**
         * @brief Check obejct is Valid or not.
         *
         * @return true
         * @return false
         */
        public bool IsValid() => RVC_CSharp_DLL.CorrespondMap_IsValid(m_handle);

        /**
         * @brief Get the Size object
         *
         * @return Size
         */
        public Size GetSize() => RVC_CSharp_DLL.CorrespondMap_GetSize(m_handle);
        /**
         * @brief Get the Data Ptr object
         *
         * @return double*
         */
        public IntPtr GetDataPtr() => RVC_CSharp_DLL.CorrespondMap_GetDataPtr(m_handle);
    };

    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct ConfidenceMap
    {
        /**
         * @brief confidence map handle
         *
         */
        public Handle m_handle;

        /**
         * @brief create confidence map object, if object is no used, call Destroy to destroy it
         *
         * @param sz confidence map size
         * @param data confidence map data
         * @param own_data own data flag
         * @return ConfidenceMap object with given parameters
         * @sa ConfidenceMap::Destroy
         */
        public static ConfidenceMap Create(Size sz, IntPtr data, bool own_data = true) =>
            new ConfidenceMap() { m_handle = RVC_CSharp_DLL.ConfidenceMap_Create(sz, data, own_data) };

        /**
         * @brief Destroy confidence map object.
         *
         * @param confidencemap confidencemap to be destroy
         * @param no_reuse True for reuse current space of confidence map
         */
        public static void Destroy(ConfidenceMap confidencemap, bool no_reuse = true) =>
            RVC_CSharp_DLL.ConfidenceMap_Destroy(confidencemap.m_handle, no_reuse);

        /**
         * @brief Check obejct is Valid or not.
         *
         * @return true
         * @return false
         */
        public bool IsValid() => RVC_CSharp_DLL.ConfidenceMap_IsValid(m_handle);

        /**
         * @brief Get the Size object
         *
         * @return Size
         */
        public Size GetSize() => RVC_CSharp_DLL.ConfidenceMap_GetSize(m_handle);
        /**
         * @brief Get the Data Ptr object
         *
         * @return double*
         */
        public IntPtr GetDataPtr() => RVC_CSharp_DLL.ConfidenceMap_GetDataPtr(m_handle);
    };

    /**
     * @brief Image ROI
     *
     */
    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct ROI
    {
        /**
         * @brief Construct a new Image ROI object with x,y,w,h
         *
         * @param x start x of Image roi (col index of roi up left corner)
         * @param y start y of Image roi (row index of roi up left corner)
         * @param w image roi width
         * @param h image roi height
         */
        public ROI(int x, int y, int w, int h)
        {
            this.x = x;
            this.y = y;
            this.width = w;
            this.height = h;
        }
        /**
         * @brief start x of Image roi (col index of roi up left corner)
         *
         */
        public int x;
        /**
         * @brief start y of Image roi (row index of roi up left corner)
         *
         */
        public int y;
        /**
         * @brief Image roi width
         *
         */
        public int width;
        /**
         * @brief Image roi height
         *
         */
        public int height;
    };


    /**
     * @brief Device ROIRange
     *
     */
    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct ROIRange
    {
        /**
         * @brief step of x of Image roi (col index of roi up left corner)
         *
         */
        public int x_step;
        /**
         * @brief step of y of Image roi (row index of roi up left corner)
         *
         */
        public int y_step;
        /**
         * @brief step of width of Image roi
         *
         */
        public int width_step;
        /**
         * @brief step of height of Image roi
         *
         */
        public int height_step;
        /**
         * @brief Minimum value of width of Image roi
         *
         */
        public int width_min;
        /**
         * @brief Minimum value of height of Image roi
         *
         */
        public int height_min;
        /**
         * @brief Maximum value of width of Image roi
         *
         */
        public int width_max;
        /**
         * @brief Maximum value of height of Image roi
         *
         */
        public int height_max;
    };


    /// <summary>
    /// RVC X Device info
    /// @param name Device name
    /// @param sn Device serial number
    /// @param factroydate Device manufacture date
    /// @param port Port number
    /// @param type Support* PortType_USB* and * PortType_GIGE*
    /// @param cameraid Support* CameraID_Left*, * CameraID_Right* and * CameraID_Both*
    /// @param boardmodel main borad model type
    /// @param support_x2 support x2 or not
    /// @param support_color supported projector color
    /// @param firmware_version RVC Camera firmware version
    /// </summary>
    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct DeviceInfo
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string name;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string sn;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string factroydate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string port;
        public PortType type;
        public CameraID cameraid;
        public int boardmodel;
        [MarshalAs(UnmanagedType.I1)]
        public bool support_x2;
        public ProjectorColor support_color;
        public int workingdist_near_mm;
        public int workingdist_far_mm;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string firmware_version;
        public CaptureMode support_capture_mode;
        [MarshalAs(UnmanagedType.I1)]
        public bool support_x1;
        [MarshalAs(UnmanagedType.I1)]
        public bool support_protective_cover;
        [MarshalAs(UnmanagedType.I1)]
        public bool support_extra;
        [MarshalAs(UnmanagedType.I1)]
        public bool support_hardware_trigger;
    };

    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct X1CollectionCallBackInfo
    {
        public Image image;
    }

    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct X1CalculationCallBackInfo
    {
        public Image image;
        public PointMap pointmap;
        public DepthMap depthmap;
        public ConfidenceMap confidencemap;
    }

    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct X2CollectionCallBackInfo
    {
        public Image left_image;
        public Image right_image;
    }

    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct X2CalculationCallBackInfo
    {
        public Image left_image;
        public Image right_image;
        public PointMap pointmap;
        public DepthMap depthmap;
        public ConfidenceMap confidencemap;
        public CorrespondMap correspondmap;
    }

    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct X2FixedLineScanCallBackInfo
    {
        public PointMap pointmap;
        public int pointmap_index;
        public int encoder_index;
    }
    #endregion

    #region MainFunction

    /// <summary>
    /// RVC System
    /// </summary>
    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct System
    {
        /// <summary>
        /// SystemInit
        /// </summary>
        /// <returns>
        /// true Success
        /// false Failed
        /// </returns>
        public static bool Init() => RVC_CSharp_DLL.System_Init();

        /// <summary>
        /// Check system is inited or not
        /// </summary>
        /// <returns>
        /// true Inited
        /// false Not Inited
        /// </returns>
        public static bool IsInited() => RVC_CSharp_DLL.System_IsInit();

        /// <summary>
        /// SystemShutdown
        /// </summary>
        public static void Shutdown() => RVC_CSharp_DLL.System_ShutDown();

        /// <summary>
        /// List the fix number devices
        /// </summary>
        /// @param pdevices device listed
        /// @param len desire list devices number
        /// @param actual_size actually list devices number
        /// @param opt List DeviceType All/USB/GIGE optional
        /// <returns>Status code</returns>
        public static void ListDevices(Device[] pdevices, ref int actual_size, int maxLen = 10,
            SystemListDeviceType opt = SystemListDeviceType.All)
        {
            int[] handles = new int[maxLen * 2];
            RVC_CSharp_DLL.System_ListDevices(handles, maxLen, ref actual_size, opt);
            for (int i = 0; i < actual_size; i++)
            {
                pdevices[i].m_handle = new Handle()
                {
                    sid = handles[i * 2],
                    gid = handles[i * 2 + 1]
                };
            }
        }
        /// <summary>
        /// more easier way to find devices
        /// </summary>
        /// <param name="maxLen"></param>
        /// <param name="opt"></param>
        /// <returns></returns>
        public static List<Device> ListDevices(SystemListDeviceType opt = SystemListDeviceType.All, int maxLen = 100)
        {
            Device[] devices = new Device[maxLen];
            int actual_size = 0;
            ListDevices(devices, ref actual_size, maxLen, opt);
            List<Device> output = new List<Device>();
            for (int i = 0; i < actual_size; i++)
            {
                output.Add(devices[i]);
            }
            return output;
        }

        /// <summary>
        /// find target device by serialNumber
        /// </summary>
        /// @param serialNumber Device Struct serial number
        /// @return Device The serialNumber  corresponding Device Struct
        /// <returns>whether find target device</returns>
        public static bool FindDevice(string serialNumber, ref Device device)
        {
            Handle handle = new Handle();
            RVC_CSharp_DLL.System_FindDevice(serialNumber, ref handle);
            device.m_handle = handle;
            return device.IsValid();
        }


        /// <summary>
        /// find target device by serialNumber
        /// </summary>
        /// @param serialNumber Device Struct serial number
        /// @return Device The serialNumber  corresponding Device Struct
        /// <returns>whether find target device</returns>
        public static Device FindDeviceBySN(string serialNumber)
        {
            Device device = new Device();
            RVC_CSharp_DLL.System_FindDevice(serialNumber, ref device.m_handle);
            return device;
        }

        /// <summary>
        /// find target device by index
        /// </summary>
        /// @param index Device list index.
        /// @return Device The serialNumber corresponding Device Struct
        /// <returns>whether find target device</returns>
        public static Device FindDeviceByIndex(uint index)
        {
            Device device = new Device();
            var devices = ListDevices();
            if (index < devices.Count)
            {
                device = devices[(int)index];
            }
            return device;
        }

        /// <summary>
        /// find target device which is Can-Connected
        /// </summary>
        /// @param index Device list index.
        /// @return Device The serialNumber  corresponding Device Struct
        /// <returns>whether find target device</returns>
        public static Device FindDeviceCanConnected()
        {
            var devices = ListDevices();
            for (int i = 0; i < devices.Count; i++)
            {
                if (devices[i].CheckCanConnected())
                {
                    return devices[i];
                }
            }
            return new Device();
        }

        /**
         * @brief Get last error of RVC SDK
         *
         * @return int
         */
        public static int GetLastError() => RVC_CSharp_DLL.System_GetLastError();

        /**
         * @brief Get the Version of RVC SDK
         *
         * @return string of version
         */
        public static string GetVersion()
        {
            IntPtr ptr = RVC_CSharp_DLL.System_GetVersion();
            return Marshal.PtrToStringAnsi(ptr) ?? "Unknown";
        }

        /**
         * @brief Get last error message of RVC SDK
         *
         * @return string of last error
         */
        public static string GetLastErrorMessage() => RVC_CSharp_DLL.System_GetLastErrorMessage();

    }

    /// <summary>
    /// Device struct
    /// </summary>
    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct Device
    {
        /// <summary>
        /// RVC Handle
        /// </summary>
        public Handle m_handle;

        /// <summary>
        /// Destroy the device
        /// </summary>
        /// @param d Device to be destroyed
        public static void Destroy(Device d) => RVC_CSharp_DLL.Device_Destroy(d.m_handle);

        /**
         * @brief Check device is valid or not
         *
         * @return true Valid
         * @return false Not valid
         */
        public bool IsValid() => RVC_CSharp_DLL.Device_IsValid(m_handle);

        /**
         * @brief Check if device firmware is match
         *
         * @return true : firmware match
         * @return false : firmware mismatch, need to upgrade
         */
        public bool IsFirmwareMatch() => RVC_CSharp_DLL.Device_IsFirmwareMatch(m_handle);

        /**
         * @brief Print device info
         *
         */
        public void Print() => RVC_CSharp_DLL.Device_Print(m_handle);

        /**
         * @brief Get the DeviceInfo object
         *
         * @param pinfo Current Device information
         * @return true Success
         * @return false Failed
         */
        public bool GetDeviceInfo(ref DeviceInfo pinfo) => RVC_CSharp_DLL.Device_GetDeviceInfo(m_handle, ref pinfo);

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
        public int SetNetworkConfig(NetworkDevice d, NetworkType type, string ip, string netMask, string gateway) =>
            RVC_CSharp_DLL.Device_SetNetworkConfig(m_handle, d, type, ip, netMask, gateway);

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
        public int GetNetworkConfig(NetworkDevice d, ref NetworkType type, StringBuilder ip, StringBuilder netMask,
            StringBuilder gateway, ref NetworkDeviceStatus_ status) =>
            RVC_CSharp_DLL.Device_GetNetworkConfig(m_handle, d, ref type, ip, netMask, gateway, ref status);

        /**
         * @brief Auto configure network for GigE device
         * @return int 0 on success, non-zero error code on failure
         */
        public int AutoConfigureNetwork() => RVC_CSharp_DLL.Device_AutoConfigureNetwork(m_handle);

        public bool CheckCanConnected()
        {
            DeviceInfo info = new DeviceInfo();
            GetDeviceInfo(ref info);

            bool canConnected = true;

            if (info.type == PortType.PortType_USB)
            {
                // Usb camera always can be connected 
                canConnected = true;
            }
            else if (info.type == PortType.PortType_GIGE)
            {
                // For the GIGE camera, we need to check the status of the LightMachine, the LeftCamera and the RightCamera.

                NetworkType networkType = NetworkType.NetworkType_DHCP;
                StringBuilder ip = new StringBuilder(256);
                StringBuilder netMask = new StringBuilder(256);
                StringBuilder gateway = new StringBuilder(256);
                NetworkDeviceStatus_ status = NetworkDeviceStatus_.NetworkDeviceStatus_OK;

                //LightMachine
                int ret1 = GetNetworkConfig(NetworkDevice.NetworkDevice_LightMachine, ref networkType, ip, netMask, gateway, ref status);
                if (ret1 == 0)
                {
                    // status means the state of assembly
                    canConnected = canConnected && status == NetworkDeviceStatus_.NetworkDeviceStatus_OK;
                }
                else
                {
                    //Failed
                    canConnected = false;
                }

                //LeftCamera
                if ((info.cameraid & CameraID.CameraID_Left) != 0)
                {
                    int ret2 = GetNetworkConfig(NetworkDevice.NetworkDevice_LeftCamera, ref networkType, ip, netMask, gateway, ref status);
                    if (ret2 == 0)
                    {
                        // status means the state of assembly
                        canConnected = canConnected && status == NetworkDeviceStatus_.NetworkDeviceStatus_OK;
                    }
                    else
                    {
                        //Failed
                        canConnected = false;
                    }
                }

                //RightCamera
                if ((info.cameraid & CameraID.CameraID_Right) != 0)
                {
                    int ret3 = GetNetworkConfig(NetworkDevice.NetworkDevice_RightCamera, ref networkType, ip, netMask, gateway, ref status);
                    if (ret3 == 0)
                    {
                        // status means the state of assembly
                        canConnected = canConnected && status == NetworkDeviceStatus_.NetworkDeviceStatus_OK;
                    }
                    else
                    {
                        //Failed
                        canConnected = false;
                    }
                }

            }

            if (IsFirmwareMatch() == false)
                return false;

            return canConnected;
        }

    };

    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct X1
    {
        [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public struct CaptureOptions
        {
            /// <summary>
            /// the default value of CaptureOptions
            /// </summary>
            /// <returns></returns>
            public static CaptureOptions Default()
            {
                CaptureOptions options = new CaptureOptions();
                options.calc_normal = false;
                options.calc_normal_radius = 5;
                options.transform_to_camera = false;
                options.filter_range = 0;
                options.use_auto_noise_removal = true;
                options.noise_removal_distance = 0;
                options.noise_removal_point_number = 40;
                options.light_contrast_threshold = 3;
                options.phase_filter_range = 0;
                options.projector_brightness = 240;
                options.exposure_time_2d = 11;
                options.exposure_time_3d = 11;
                options.gain_2d = 0;
                options.gain_3d = 0;
                options.hdr_exposure_times = 0;
                options.hdr_exposuretime_content = new int[3];
                options.hdr_exposuretime_content[0] = 11;
                options.hdr_exposuretime_content[1] = 20;
                options.hdr_exposuretime_content[2] = 50;
                options.hdr_gain_3d = new float[3];
                options.hdr_gain_3d[0] = 0;
                options.hdr_gain_3d[1] = 0;
                options.hdr_gain_3d[2] = 0;
                options.hdr_scan_times = new int[3];
                options.hdr_scan_times[0] = 1;
                options.hdr_scan_times[1] = 1;
                options.hdr_scan_times[2] = 1;
                options.hdr_projector_brightness = new int[3];
                options.hdr_projector_brightness[0] = 240;
                options.hdr_projector_brightness[1] = 240;
                options.hdr_projector_brightness[2] = 240;
                options.gamma_2d = 1.0f;
                options.gamma_3d = 1.0f;
                options.use_projector_capturing_2d_image = true;
                options.smoothness = SmoothnessLevel.SmoothnessLevel_Off;
                options.downsample_distance = 0.0;
                options.capture_mode = CaptureMode.CaptureMode_Normal;
                options.confidence_threshold = 0;
                options.roi = new ROI(0, 0, 0, 0);
                options.truncate_z_min = -9999.0;
                options.truncate_z_max = 9999.0;
                options.use_auto_bilateral_filter = true;
                options.bilateral_filter_kernal_size = 0;
                options.bilateral_filter_depth_sigma = 0.0;
                options.bilateral_filter_space_sigma = 0.0;
                options.scan_times = 1;
                options.reflection_filter_threshold = 0;
                options.smooth_sigma = 1.75;
                options.enable_2d_in_capture = true;
                return options;
            }

            /**
             * @brief flag Whether calculate 3D points normal vector
             *
             */
            [MarshalAs(UnmanagedType.I1)]
            public bool calc_normal;
            /**
             * @brief flag Whether transform 3D points from calibration board system to camera coordinate system
             *
             */
            [MarshalAs(UnmanagedType.I1)]
            public bool transform_to_camera;
            /**
             * Point cloud noise removal algorithm 1, contains one parameter: filter_range.
             * If this algorithm does not work well, set filter_range to 0 and try noise removal algorithm 2 below.
             * @brief Set the noise filter value. The larger the value, the greater the filtering degree.
             * The default value has been changed to 0 from 1 after v1.6.1.
             */
            [Obsolete] public int filter_range;
            /**
             * Point cloud noise removal algorithm, contains three parameters: use_auto_noise_removal, noise_removal_distance and
             * noise_removal_point_number. This algorithm performs noise reduction through a clustering algorithm. The point
             * cloud is classified into blocks according to the distance (noise_removal_distance). If the total number of
             * points in the block is less than a certain threshold (noise_removal_point_number), the points in the block
             * are considered as noise points and need to be removed.
             */
            /**
             * @brief flag Whether to use auto noise removal. 
             * If true, the noise_removal_distance and noise_removal_point_number will be ignored. It will automatically
             * adjust these two parameters according to the point cloud data and do noise removal.
             */
            [MarshalAs(UnmanagedType.I1)]
            public bool use_auto_noise_removal;
            /**
             * @brief The smaller the value, the greater the filtering degree.
             * range: 0 ~ 20 (units: mm)
             */
            public double noise_removal_distance;
            /**
             * @brief The larger the value, the greater the filtering degree.
             * range: 0 ~ 100
             */
            public int noise_removal_point_number;
            /**
             * @brief Light contrast trheshold, range in [0, 10]. The contrast of point less than this value will be treat
             * as invalid point and be removed.
             *
             */
            public int light_contrast_threshold;
            /**
             * @brief Set the phase filter value. The larger the value, the greater the filtering degree 0~40
             *
             */
            public int phase_filter_range;
            /**
             * @brief Set the exposure_time 2D value in milliseconds
             *
             */
            public int exposure_time_2d;
            /**
             * @brief Set the exposure_time 3D value in milliseconds
             *
             */
            public int exposure_time_3d;
            /**
             * @brief Set the projector brightness value
             *
             */
            public int projector_brightness;
            /**
             * @brief Set the 2D gain value
             *
             */
            public float gain_2d;
            /**
             * @brief Set the 3D gain value
             *
             */
            public float gain_3d;
            /**
             * @brief Set the hdr exposure times value. 0,2,3
             *
             */
            public int hdr_exposure_times;
            /**
             * @brief Set the hdr exposure time content. capture with white light, range [11, 100], others [3, 100]
             *
             */
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
            public int[] hdr_exposuretime_content;

            /**
             * @brief Set the hdr 3D gain content.
             *
             */
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
            public float[] hdr_gain_3d;

            /**
             * @brief Set the hdr scan times, only use in robust mode. range [2, 4],
             *
             */
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
            public int[] hdr_scan_times;
            /**
             * @brief Set the hdr projector brightness value
             *
             */
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
            public int[] hdr_projector_brightness;
            /**
             * @brief Neighborhood radius in pixel of calculating normal, > 0
             */
            public int calc_normal_radius;
            /**
             * @brief Set the 2D gamma value
             *
             */
            public float gamma_2d;
            /**
             * @brief Set the 3D gamma value
             *
             */
            public float gamma_3d;
            /**
             * @brief Set 2D image whether use projector
             *
             */
            [MarshalAs(UnmanagedType.I1)]
            public bool use_projector_capturing_2d_image;

            /**
             * @brief control point map smoothness
             *
             */
            [Obsolete("Use smooth_sigma instead")] public SmoothnessLevel smoothness;

            /**
             * @brief uniform downsample distance. if <= 0, do nothing.
             *
             */
            public double downsample_distance;

            /**
             * @brief control capture mode
             *
             */
            public CaptureMode capture_mode;

            /**
             * @brief confidence threshold, the point with confindence low then this value will be removed
             * range: [0, 1]
             *
             */
            public double confidence_threshold;

            /**
            * @brief set ROI function, only 3d points in the roi will be generated.
            * This function can improve 3d capturespeed.
            * The parameters of roi must comply with the rules of the equipment and can be checked by CheckRoi.
            * We recommend that you adjust roi automatically through C before AutoAdjustRoi.
            */
            public ROI roi;

            /**
             * @brief truncate point map and depth map by z direction minimum value (units: mm)
             * and truncate_z_min should less than truncate_z_max range: [-9999, 9999]
             *
             */
            public double truncate_z_min;

            /**
             * @brief truncate point map and depth map by z direction maximum value (units: mm)
             * and truncate_z_max should more than truncate_z_min range: [-9999, 9999]
             *
             */
            public double truncate_z_max;

            /**
             * @brief the kernal size of bilateral filter of depth map
             * range: [3, 31], 0 for not use bilateral filter
             *
             */
            [Obsolete("Use smooth_sigma instead")] public int bilateral_filter_kernal_size;

            /**
             * @brief the guassian sigma in depth of bilateral filter of depth map
             * range: [0, 100]
             *
             */
            [Obsolete("Use smooth_sigma instead")] public double bilateral_filter_depth_sigma;

            /**
             * @brief the guassian sigma in space of bilateral filter of depth map
             * range: [0, 100]
             *
             */
            [Obsolete("Use smooth_sigma instead")] public double bilateral_filter_space_sigma;

            /**
             * @brief scan times, only use in robust mode. range [2, 4],
             */
            public int scan_times;

            /**
             * @brief flag Whether to use auto bilateral filter.
             * If true, the bilateral_filter_kernal_size and bilateral_filter_depth_sigma and bilateral_filter_space_sigma
             * will be ignored. It will automatically adjust these three parameters according to the point cloud data and do
             * bilateral filter.
             */
            [MarshalAs(UnmanagedType.I1)]
            [Obsolete("Use smooth_sigma instead")] public bool use_auto_bilateral_filter;

            /**
            * @brief Used to remove large-area erroneous point clouds caused by reflections.
            * The higher this value is set, the more points will be removed by the reflection filter.
            * Setting it too large may remove data from thin and pointy objects.
            * range:[0, 30]
            */
            public int reflection_filter_threshold;


            /**
            * @brief The Gaussian filters are used to smooth points.
            * The larger the smooth_sigma, the smoother the point cloud becomes. However, an excessively large smooth_sigma
            * can cause edges to be smoothed out as well.
            * range: [0, 5]
            */
            public double smooth_sigma;

            /**
             * @brief Acquire 2D images during capture
             */
            public bool enable_2d_in_capture;
        };

        /**
         * @brief Options when setting custom transformation
         *
         */
        [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public struct CustomTransformOptions
        {
            /**
             * @brief base coordinate of custom transformation,default is *CoordinateSelect_Disabled*
             *
             * All support type is
             * *CoordinateSelect_Disabled*,*CoordinateSelect_Camera*,*CoordinateSelect_CaliBoard*
             */
            public enum CoordinateSelect
            {
                CoordinateSelect_Disabled,
                CoordinateSelect_Camera,
                CoordinateSelect_CaliBoard,
            };

            public static CustomTransformOptions Default()
            {
                return new CustomTransformOptions()
                {
                    coordinate_select = CoordinateSelect.CoordinateSelect_Disabled,
                    transform = new double[16] { 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1 }
                };
            }

            /**
            * @brief base coordinate setting of custom transformation
            *
            */
            public CoordinateSelect coordinate_select;

            /**
             * @brief custom transformation, translation unit: m
             * len = 16
             */
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 16)]

            public double[] transform;
        };

        /**
         * @brief RVC Handle
         *
         */
        public Handle m_handle;

        /**
        * @brief Create a RVC X Camera and choose the CameraID which you desire before you use X1
        *
        * @param d One RVC X Camera
        * @param id Choose *CameraID_Left* or *CameraID_Right*
        * @return X1 RVC X object
        */
        public static X1 Create(Device d, CameraID id) => new X1() { m_handle = RVC_CSharp_DLL.X1_Create(d.m_handle, id) };

        /**
         * @brief Release all X1 resources after you use X1
         *
         * @param x RVC X object to be released
         *
         * @snippet X1Test.cpp Create RVC X1
         */
        public static void Destroy(X1 x) => RVC_CSharp_DLL.X1_Destroy(x.m_handle);

        public void Destroy() => RVC_CSharp_DLL.X1_Destroy(m_handle);

        /**
         * @brief Check X1 is valid or not before use X1
         *
         * @return true Available
         * @return false Not available
         *
         * @snippet X1Test.cpp Create RVC X1
         */
        public bool IsValid()
        {
            bool ret = RVC_CSharp_DLL.X1_IsValid(m_handle);
            return ret;
        }

        /**
         * @brief Open X1 before you use it
         *
         * @return true Success
         * @return false Failed
         *
         * @snippet X1Test.cpp Create RVC X1
         */
        public bool Open() => RVC_CSharp_DLL.X1_Open(m_handle);

        /**
         * @brief Close X1 after you Open it
         *
         * @snippet X1Test.cpp Create RVC X1
         */
        public void Close() => RVC_CSharp_DLL.X1_Close(m_handle);

        /**
         * @brief Check X1 is open or not
         *
         * @return true Is open
         * @return false Not open
         *
         * @snippet X1Test.cpp Create RVC X1
         */
        public bool IsOpen() => RVC_CSharp_DLL.X1_IsOpen(m_handle);

        /**
         * @brief Check X1 is physically connected or not
         *
         * @return true Is physically connected
         * @return false Not physically connected
         *
         * @snippet X1Test.cpp Create RVC X1
         */
        public bool IsPhysicallyConnected() => RVC_CSharp_DLL.X1_IsPhysicallyConnected(m_handle);

        /**
         * @brief Capture one point map and one image. This function will save capture options into camera.
         *
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         *
         * @snippet X1Test.cpp Capture with options
         */
        public bool Capture(CaptureOptions opts) => RVC_CSharp_DLL.X1_Capture(m_handle, opts);

        /**
         * @brief Capture one point map and one image. This function will load capture options from camera.
         *
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         *
         * @snippet X1Test.cpp Capture with options
         */
        public bool Capture() => RVC_CSharp_DLL.X1_Capture_(m_handle);

        /**
         * @brief Capture one image. This function will save capture options into camera. You can use GetImage() to obtain
         * 2D imgae
         *
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool Capture2D(CaptureOptions opts) => RVC_CSharp_DLL.X1_Capture2D(m_handle, opts);

        /**
         * @brief Capture one image. This function will load capture options from camera. You can use GetImage() to obtain
         * 2D imgae
         *
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool Capture2D() => RVC_CSharp_DLL.X1_Capture2D_(m_handle);

        /**
         * @brief Set the camera band width ratio
         *
         * @param percent Band width ratio
         * @return true Success
         * @return false Failed
         */
        public bool SetBandwidth(float percent) => RVC_CSharp_DLL.X1_SetBandwidth(m_handle, percent);

        /**
         * @brief Get the camera band width ratio
         *
         * @param percent Band width ratio
         * @return true Success
         * @return false Failed
         */
        public bool GetBandwidth(ref float percent) => RVC_CSharp_DLL.X1_GetBandwidth(m_handle, ref percent);

        /**
         * @brief Set the Transformation of output point cloud
         *
         * @param opts  Custom Transform Options
         * @return true
         * @return false
         */
        public bool SetCustomTransformation(CustomTransformOptions opts) => RVC_CSharp_DLL.X1_SetCustomTransformation(m_handle, opts);

        /**
         * @brief Get the Custom Transformation object
         *
         * @param opts
         * @return true
         * @return false
         */
        public bool GetCustomTransformation(ref CustomTransformOptions opts) => RVC_CSharp_DLL.X1_GetCustomTransformation(m_handle, ref opts);

        /**
         * @brief Get the Image object
         *
         * @return Image
         */
        public Image GetImage() => new Image() { m_handle = RVC_CSharp_DLL.X1_GetImage(m_handle) };

        /**
         * @brief Get the DepthMap object
         *
         * @return DepthMap A DepthMap
         */
        public DepthMap GetDepthMap() => new DepthMap() { m_handle = RVC_CSharp_DLL.X1_GetDepthMap(m_handle) };

        /**
         * @brief Get the Point Map object
         *
         * @return PointMap
         */
        public PointMap GetPointMap() => new PointMap() { m_handle = RVC_CSharp_DLL.X1_GetPointMap(m_handle) };

        /**
         * @brief Get the Mesh object
         *
         * @return Mesh
         */
        public Mesh GetMesh() => new Mesh() { m_handle = RVC_CSharp_DLL.X1_GetMesh(m_handle) };

        /**
         * @brief Get the Confidence Map object
         *
         * @return ConfidenceMap
         */
        public ConfidenceMap GetConfidenceMap() => new ConfidenceMap() { m_handle = RVC_CSharp_DLL.X1_GetConfidenceMap(m_handle) };

        /**
         * @brief Get the extrinsic matrix
         *
         * @param matrix  extrinsic matrix,len = 16
         * @return true Success
         * @return false Failed
         */
        public bool GetExtrinsicMatrix(float[] matrix) => RVC_CSharp_DLL.X1_GetExtrinsicMatrix(m_handle, matrix);

        /**
         * @brief Get the intrinsic matrix
         *
         * @param instrinsic_matrix camera instrinsic matrix,len = 9
         * @param distortion ,len = 5
         * @return true Success
         * @return false Failed
         */
        public bool GetIntrinsicParameters(float[] instrinsic_matrix, float[] distortion) =>
            RVC_CSharp_DLL.X1_GetIntrinsicParameters(m_handle, instrinsic_matrix, distortion);


        /**
         * @brief  GetProjectorTemperature
         * @note   TODO:
         * @param  &temperature:
         * @retval
         */
        public bool GetProjectorTemperature(ref float temperature) =>
            RVC_CSharp_DLL.X1_GetProjectorTemperature(m_handle, ref temperature);


        /**
         * @brief  GetCameraTemperature
         * @note   TODO:
         * @param  seletor:
         * @param  &temperature:
         * @retval
         */
        public bool GetCameraTemperature(CameraTempSelector seletor, ref float temperature) =>
            RVC_CSharp_DLL.X1_GetCameraTemperature(m_handle, seletor, ref temperature);

        /**
         * @brief Set the white balance ratio value
         *
         * @param selector support BalanceSelector_Red, BalanceSelector_Green and BalanceSelector_Blue
         * @param value  balance ratio value
         * @return true Success
         * @return false Failed
         */
        public bool SetBalanceRatio(BalanceSelector selector, float value) => RVC_CSharp_DLL.X1_SetBalanceRatio(m_handle, selector, value);

        /**
         * @brief Get the white balance ratio value
         *
         * @param selector support BalanceSelector_Red, BalanceSelector_Green and BalanceSelector_Blue
         * @param value balance ratio value
         * @return true Success
         * @return false Failed
         */
        public bool GetBalanceRatio(BalanceSelector selector, ref float value) =>
            RVC_CSharp_DLL.X1_GetBalanceRatio(m_handle, selector, ref value);

        /**
         * @brief Get the white balance ratio value range
         *
         * @param selector support BalanceSelector_Red, BalanceSelector_Green and BalanceSelector_Blue
         * @param min_value selector's minimum value
         * @param max_value selector's maximum value
         * @return true Success
         * @return false Failed
         */
        public bool GetBalanceRange(BalanceSelector selector, ref float min_value, ref float max_value) =>
            RVC_CSharp_DLL.X1_GetBalanceRange(m_handle, selector, ref min_value, ref max_value);

        /**
         * @brief Only Color Camera can use this function. This function can get suitable white balance paramters
         *
         * @param wb_times how many images used for calculate the white balance paramters,defalut = 10
         * @param opts capture options. exposure_time_2d, gain_2d, gamma_2d will be used. use_projector_capturing_2d_image
         * == true, brightness will be used too.
         * @param roi auto white balance will be operated here
         * @return true
         * @return false
         */
        public bool AutoWhiteBalance(int wb_times, CaptureOptions opts, ROI roi) =>
            RVC_CSharp_DLL.X1_AutoWhiteBalance(m_handle, wb_times, opts, roi);

        /**
         * @brief Get the Exposure Time Range
         *
         * @param min_value exposure time minimum value
         * @param max_value exposure time maxinum value
         * @return true Success
         * @return false Failed
         */
        public bool GetExposureTimeRange(ref int min_value, ref int max_value) =>
            RVC_CSharp_DLL.X1_GetExposureTimeRange(m_handle, ref min_value, ref max_value);

        /**
         * @brief Get the Gain Range
         *
         * @param min_value gain minimum value
         * @param max_value gain minimum value
         * @return true Success
         * @return false Failed
         */
        public bool GetGainRange(ref float min_value, ref float max_value) =>
            RVC_CSharp_DLL.X1_GetGainRange(m_handle, ref min_value, ref max_value);

        /**
         * @brief Get the Gamma Range
         *
         * @param min_value gamma minimum value
         * @param max_value gamma minimum value
         * @return true Success
         * @return false Failed
         */
        public bool GetGammaRange(ref float min_value, ref float max_value) =>
            RVC_CSharp_DLL.X1_GetGammaRange(m_handle, ref min_value, ref max_value);

        /**
         * @brief Save capture option parameters
         *
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool SaveCaptureOptionParameters(CaptureOptions opts) => RVC_CSharp_DLL.X1_SaveCaptureOptionParameters(m_handle, opts);

        /**
         * @brief Get capture option parameters
         *
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool LoadCaptureOptionParameters(ref CaptureOptions opts) =>
            RVC_CSharp_DLL.X1_LoadCaptureOptionParameters(m_handle, ref opts);

        /**
         * @brief Get auto capture setting. Exposure_time_2d, exposure_time_3d, projector_brightness, light_contrast_threshold will be adjusted automatically.
         * automatically
         *
         * @param opts
         * @return CaptureOptions
         */
        public bool GetAutoCaptureSetting(ref CaptureOptions opts, ROI roi) =>
            RVC_CSharp_DLL.X1_GetAutoCaptureSetting(m_handle, ref opts, roi);

        /**
         * @brief adjust 3D capturing parameters
         *
         * @param opts [in,out] capture options. if  hdr_exposure_times > 1, hdr_exposure_times and hdr_exposuretime_content
         * will be adjusted. If hdr_exposure_times equals to 1, exposure_time_3d will be adjusted.
         * @param roi [in] if width or height equal to 0, all image will be used.
         * @return true
         * @return false
         */
        public bool GetAutoHdrCaptureSetting(ref CaptureOptions opts, ROI roi) =>
            RVC_CSharp_DLL.X1_GetAutoHdrCaptureSetting(m_handle, ref opts, roi);

        /**
         * @brief Automatically adjust 2D exposure time (exposure_time_2d) in CaptureOptions.
         *
         * @param opts [in,out] capture options. exposure_time_2d will be adjusted automatically.
         * @param roi [in] region of interest used to evaluate brightness. If width or height equal to 0, full image is used.
         * @return true on success, false on failure (custom setting will be retained).
         */
        public bool GetAuto2DExposureTime(ref CaptureOptions opts, ROI roi) =>
            RVC_CSharp_DLL.X1_GetAuto2DExposureTime(m_handle, ref opts, roi);

        /**
         * @brief Get automatic noise removal results
         */
        public bool GetAutoNoiseRemovalSetting(ref CaptureOptions opts) =>
            RVC_CSharp_DLL.X1_GetAutoNoiseRemovalSetting(m_handle, ref opts);

        /**
        * @brief Load camera setting from local file .
        * @param filename [in]
        * @return true the content of file is correctly .
        * @return false the content of file is not correctly .
        */
        public bool LoadSettingFromFile(string filename) => RVC_CSharp_DLL.X1_LoadSettingFromFile(m_handle, filename);

        /**
         * @brief Save camera setting to local file.
         * @param filename [in]
         * @return true Successfully written to the file.
         * @return false Failed write to file.
         */
        public bool SaveSettingToFile(string filename) => RVC_CSharp_DLL.X1_SaveSettingToFile(m_handle, filename);

        /**
         * @brief Check whether the parameters of ROI meet the requirements.
         * @param roi [in] .
         * @return true
         * @return false
         */
        public bool CheckRoi(ROI roi) => RVC_CSharp_DLL.X1_CheckRoi(m_handle, roi);

        /**
         * @brief Automatically correct the parameters of ROI. You need to correct ROI before Capture/Captrue2D.
         * @param roi [in] If you want to get a maximum ROI, you can pass in the default value.
         * @return ROI Corrected ROI.
         */
        public ROI AutoAdjustRoi(ROI roi) => RVC_CSharp_DLL.X1_AutoAdjustRoi(m_handle, roi);

        /**
         * @brief Get the range of ROI.
         */
        public bool GetRoiRange(ref ROIRange range) => RVC_CSharp_DLL.X1_GetRoiRange(m_handle, ref range);

        /**
         * @brief Get the range of ROI.
        */
        public bool GetCameraResolution(ref Size size) => RVC_CSharp_DLL.X1_GetCameraResolution(m_handle, ref size);

        /**
         * @brief Open ProtectiveCover
         *
         * @return true if success
         * @return false if failed
         */
        public bool OpenProtectiveCover() => RVC_CSharp_DLL.X1_OpenProtectiveCover(m_handle);
        /**
         * @brief Close ProtectiveCover
         *
         * @return true if success
         * @return false if failed
         */
        public bool CloseProtectiveCover() => RVC_CSharp_DLL.X1_CloseProtectiveCover(m_handle);
        /**
         * @brief Reset ProtectiveCover
         *
         * @return true if success
         * @return false if failed
         */
        public bool ResetProtectiveCover() => RVC_CSharp_DLL.X1_ResetProtectiveCover(m_handle);
        /**
         * @brief Get Status of ProtectiveCover
         * @return ProtectiveCoverStatus
         */
        public bool GetProtectiveCoverStatus(ref ProtectiveCoverStatus status) => RVC_CSharp_DLL.X1_GetProtectiveCoverStatus(m_handle, ref status);

        /**
         * @brief Save Encoded Images Data
         */
        public bool SaveEncodedImagesData(string address) => RVC_CSharp_DLL.X1_SaveEncodedImagesData(m_handle, address);


        public bool SetCurrentUserSet(int id) => RVC_CSharp_DLL.X1_SetCurrentUserSet(m_handle, id);

        public bool GetCurrentUserSet(ref int id) => RVC_CSharp_DLL.X1_GetCurrentUserSet(m_handle, id);

        public bool SetUserSetName(int id, string name) => RVC_CSharp_DLL.X1_SetUserSetName(m_handle, id, name);

        public bool GetUserSetName(int id, string name) => RVC_CSharp_DLL.X1_GetUserSetName(m_handle, id, name);

    }

    [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct X2
    {

        /**
         * @brief Capture options
         *
         */
        [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public struct CaptureOptions
        {
            /**
             * @brief Construct a new Capture Options object
             *
             */
            public static CaptureOptions Default()
            {
                CaptureOptions options = new CaptureOptions();
                options.transform_to_camera = CameraID.CameraID_NONE;
                options.projector_brightness = 240;
                options.calc_normal = false;
                options.calc_normal_radius = 5;
                options.use_auto_noise_removal = true;
                options.noise_removal_distance = 0;
                options.noise_removal_point_number = 40;
                options.light_contrast_threshold = 3;
                options.edge_noise_reduction_threshold = 2;
                options.exposure_time_2d = 11;
                options.exposure_time_3d = 11;
                options.gain_2d = 0.0f;
                options.gain_3d = 0.0f;
                options.hdr_exposure_times = 0;
                options.hdr_exposuretime_content = new int[3];
                options.hdr_exposuretime_content[0] = 11;
                options.hdr_exposuretime_content[1] = 20;
                options.hdr_exposuretime_content[2] = 50;
                options.hdr_gain_3d = new float[3];
                options.hdr_gain_3d[0] = 0;
                options.hdr_gain_3d[1] = 0;
                options.hdr_gain_3d[2] = 0;
                options.hdr_projector_brightness = new int[3];
                options.hdr_projector_brightness[0] = 240;
                options.hdr_projector_brightness[1] = 240;
                options.hdr_projector_brightness[2] = 240;
                options.gamma_2d = 1.0f;
                options.gamma_3d = 1.0f;
                options.projector_color = ProjectorColor.ProjectorColor_Blue;
                options.use_projector_capturing_2d_image = true;
                options.smoothness = SmoothnessLevel.SmoothnessLevel_Off;
                options.downsample_distance = 0.0;
                options.capture_mode = CaptureMode.CaptureMode_Normal;
                options.confidence_threshold = 0;
                options.scan_times = 1;
                options.hdr_scan_times = new int[3];
                options.hdr_scan_times[0] = 1;
                options.hdr_scan_times[1] = 1;
                options.hdr_scan_times[2] = 1;
                options.use_auto_bilateral_filter = true;
                options.bilateral_filter_kernal_size = 0;
                options.bilateral_filter_depth_sigma = 0.0;
                options.bilateral_filter_space_sigma = 0.0;

                options.line_scanner_scan_time_ms = 1000;
                options.line_scanner_exposure_time_us = 300;
                options.line_scanner_min_distance = 0;
                options.line_scanner_max_distance = 0;
                options.correspond2d = false;
                options.line_scanner_laser_position = 0xffff / 2;

                options.reflection_filter_threshold = 0;
                options.smooth_sigma = 1.75;

                options.roi = new ROI(0, 0, 0, 0);

                //options.use_extra_color_camera = true;
                options.enable_2d_in_capture = true;
                options.pointcloud_completion = false;
                options.line_scanner_brightness_threshold = 5;
                options.trigger_mode = TriggerMode.TriggerMode_SoftWare;
                options.encoder_trigger_interval = 8;
                options.truncate_z_min = -29999;
                options.truncate_z_max = 29999;
                options.line_scanner_confidence = 0.72;
                options.fixed_rate = 1;
                options.auto_set_fixed_rate = true;
                return options;
            }

            /**
             * @brief CameraID_Left transfrom 3D points from calibration board system to left camera coordinate system
             * CameraID_Right transfrom 3D points from calibration board system to right camera coordinate system
             * other is do not transfrom
             */
            public CameraID transform_to_camera;
            /**
             * @brief Set the projector brightness value
             *
             */
            public int projector_brightness;
            /**
             * @brief flag Whether calculate 3D points normal vector
             *
             */
            [MarshalAs(UnmanagedType.I1)]
            public bool calc_normal;

            /**
             * @brief Neighborhood radius in pixel of calculating normal, > 0
             */
            public int calc_normal_radius;

            /**
             * @brief Light contrast trheshold, range in [0, 10]. The contrast of point less than this value will be treat
             * as invalid point and be removed.
             *
             */
            public int light_contrast_threshold;
            /**
             * @brief edge control after point matching, range in [0, 10], default = 2. The big the value, the more edge
             * noise to be removed.
             *
             */
            [Obsolete] public int edge_noise_reduction_threshold;
            /**
             * @brief Set the exposure_time 2D value in milliseconds
             *
             */
            public int exposure_time_2d;
            /**
             * @brief Set the exposure_time 3D value in milliseconds
             *
             */
            public int exposure_time_3d;
            /**
             * @brief Set the 2D gain value in milliseconds
             *
             */
            public float gain_2d;
            /**
             * @brief Set the 3D gain value in milliseconds
             *
             */
            public float gain_3d;
            /**
             * @brief Set the hdr exposure times value. 0,2,3
             *
             */
            public int hdr_exposure_times;
            /**
             * @brief Set the hdr exposure time content. capture with white light, range [11, 100], others [3, 100]
             *
             */
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
            public int[] hdr_exposuretime_content;
            /**
             * @brief Set the hdr 3D gain content.
             *
             */
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
            public float[] hdr_gain_3d;
            /**
             * @brief Set the hdr projector brightness value
             *
             */
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
            public int[] hdr_projector_brightness;
            /**
             * @brief Set the 2D gamma value in milliseconds
             *
             */
            public float gamma_2d;
            /**
             * @brief Set the 3D gamma value in milliseconds
             *
             */
            public float gamma_3d;
            /**
             * @brief  projector color
             */
            public ProjectorColor projector_color;
            /**
             * @brief Set 2D image whether use projector
             *
             */
            [MarshalAs(UnmanagedType.I1)]
            public bool use_projector_capturing_2d_image;

            /**
             * @brief control point map smoothness
             *
             */
            [Obsolete("Use smooth_sigma instead")] public SmoothnessLevel smoothness;
            /**
             * Point cloud noise removal algorithm, contains three parameters: use_auto_noise_removal, noise_removal_distance and
             * noise_removal_point_number. This algorithm performs noise reduction through a clustering algorithm. The point
             * cloud is classified into blocks according to the distance (noise_removal_distance). If the total number of
             * points in the block is less than a certain threshold (noise_removal_point_number), the points in the block
             * are considered as noise points and need to be removed.
             */
            /**
             * @brief flag Whether to use auto noise removal. 
             * If true, the noise_removal_distance and noise_removal_point_number will be ignored. It will automatically
             * adjust these two parameters according to the point cloud data and do noise removal.
             */
            [MarshalAs(UnmanagedType.I1)]
            public bool use_auto_noise_removal;
            /**
             * @brief The smaller the value, the greater the filtering degree.
             * range: 0 ~ 20 (units: mm)
             */
            public double noise_removal_distance;
            /**
             * @brief Set the noise filter parameter 2. The larger the value, the greater the filtering degree.
             * range: 0 ~ 100
             */
            public int noise_removal_point_number;

            /**
             * @brief uniform downsample distance. if <= 0, do nothing.
             *
             */
            public double downsample_distance;

            /**
             * @brief control capture mode
             *
             */
            public CaptureMode capture_mode;

            /**
             * @brief confidence threshold, the point with confindence low then this value will be removed
             * range: [0, 1]
             *
             */
            public double confidence_threshold;
            /**
            * @brief scan times, only use in robust mode. range [2, 8],
            */
            public int scan_times;
            /**
             * @brief Set the hdr scan times, only use in robust mode. range [2, 8],
             *
             */
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
            public int[] hdr_scan_times;

            /**
             * @brief the kernal size of bilateral filter of depth map
             * range: [3, 31], 0 for not use bilateral filter
             *
             */
            [Obsolete("Use smooth_sigma instead")] public int bilateral_filter_kernal_size;
            /**
             * @brief the guassian sigma in depth of bilateral filter of depth map
             * range: [0, 100]
             *
             */
            [Obsolete("Use smooth_sigma instead")] public double bilateral_filter_depth_sigma;
            /**
             * @brief the guassian sigma in space of bilateral filter of depth map
             * range: [0, 100]
             *
             */
            [Obsolete("Use smooth_sigma instead")] public double bilateral_filter_space_sigma;

            /**
            * @brief Set line scanner mode's total scan time
            */
            public int line_scanner_scan_time_ms;
            /**
             * @brief Set line scanner mode's single line exposure time
             */
            public int line_scanner_exposure_time_us;
            /**
             * @brief Set line scanner mode's minimum working distance
             */
            public int line_scanner_min_distance;
            /**
             * @brief Set line scanner mode's maximum working distance
             */
            public int line_scanner_max_distance;

            /**
             * @brief whether to generate point clouds corresponding to 2D images
             *
             */
            [MarshalAs(UnmanagedType.I1)]
            public bool correspond2d;

            /**
             * @brief laser position for FixedLineScan mode
             *
             */
            public ushort line_scanner_laser_position;

            /**
             * @brief flag Whether to use auto bilateral filter.
             * If true, the bilateral_filter_kernal_size and bilateral_filter_depth_sigma and bilateral_filter_space_sigma
             * will be ignored. It will automatically adjust these three parameters according to the point cloud data and do
             * bilateral filter.
             */
            [MarshalAs(UnmanagedType.I1)]
            [Obsolete("Use smooth_sigma instead")] public bool use_auto_bilateral_filter;


            /**
            * @brief Used to remove large-area erroneous point clouds caused by reflections.
            * The higher this value is set, the more points will be removed by the reflection filter.
            * Setting it too large may remove data from thin and pointy objects.
            * range:[0, 30]
            */
            public int reflection_filter_threshold;

            /**
            * @brief The Gaussian filters are used to smooth points.
            * The larger the smooth_sigma, the smoother the point cloud becomes. However, an excessively large smooth_sigma
            * can cause edges to be smoothed out as well.
            * range: [0, 5]
            */
            public double smooth_sigma;

            /**
            * @brief set ROI function, only 3d points in the roi will be generated.
            * This function can improve 3d capturespeed and only support swing line scan roi.
            * The parameters of roi must comply with the rules of the equipment and can be checked by CheckRoi.
            * We recommend that you adjust roi automatically through C before AutoAdjustRoi.
            */
            public ROI roi;

            /**
            * @brief Acquire 2D images during capture
            */
            [MarshalAs(UnmanagedType.I1)]
            public bool enable_2d_in_capture;

            /**
             * @brief In 'CaptureMode_SwingLineScan' mode with 'correspond2d' enabled,turning on 'pointcloud_completion'
             * will interpolate the point cloud to produce a dense reconstruction.
             */
            [MarshalAs(UnmanagedType.I1)]
            public bool pointcloud_completion;

            /**
            * @brief Only laser lines with brightness greater than the 'line_scanner_brightness_threshold' will be
            * extracted by the algorithm. A higher threshold results in fewer extracted points, while a lower threshold
            * yields more points but may introduce additional noise. When scanning black objects, a lower threshold can be
            * used.
            *
            * range: [0, 200]
            *
            * default: 5
            */
            public int line_scanner_brightness_threshold;

            /**
            * @brief Trigger mode. Currently, only the 'FixedLineScan' mode supports
            *        hardware triggering (TriggerMode_HardWare); all other modes only
            *        support software triggering (TriggerMode_SoftWare).
            */
            public TriggerMode trigger_mode;

            /**
            * @brief Number of encoder pulses required to trigger one profile acquisition
            */
            public int encoder_trigger_interval;

            /**
             * @brief truncate point map and depth map by z direction minimum value (units: mm)
             * and truncate_z_min should less than truncate_z_max range: [-29999, 29999]
             *
             */
            public double truncate_z_min;

            /**
             * @brief truncate point map and depth map by z direction maximum value (units: mm)
             * and truncate_z_max should more than truncate_z_min range: [-29999, 29999]
             *
             */
            public double truncate_z_max;

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
            public double line_scanner_confidence;

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
            public double fixed_rate;

            /**
             * @brief Enable automatic fixed rate estimation
             *
             * When true: camera auto-estimates trigger rate, ignoring fixed_rate.
             * When false: manual fixed_rate setting takes effect.
             *
             * @note Automatic rate estimation provides a relatively safe value but doesn't guarantee no frame drops.
             */
            [MarshalAs(UnmanagedType.I1)]
            public bool auto_set_fixed_rate;
        };

        /**
         * @brief Options when setting custom transformation
         *
         */
        [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public struct CustomTransformOptions
        {

            /**
             * @brief base coordinate of custom transformation,default is *CoordinateSelect_Disabled*
             */
            public enum CoordinateSelect
            {
                CoordinateSelect_Disabled,
                CoordinateSelect_CameraLeft,
                CoordinateSelect_CameraRight,
                CoordinateSelect_CaliBoard,
                CoordinateSelect_CameraExtra,
            };

            /**
             * @brief base coordinate setting of custom transformation
             *
             */
            public CoordinateSelect coordinate_select;

            /**
             * @brief custom transformation, translation unit: m
             *
             */
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 16)]
            public double[] transform;

            public static CustomTransformOptions Default()
            {
                return new CustomTransformOptions
                {
                    coordinate_select = CoordinateSelect.CoordinateSelect_Disabled,
                    transform = new double[16]
                    {
                1, 0, 0, 0,
                0, 1, 0, 0,
                0, 0, 1, 0,
                0, 0, 0, 1
                    }
                };
            }

        };

        /**
         * @brief RVC Handle
         *
         */
        public Handle m_handle;

        /**
         * @brief Create a RVC X Camera before you use x2
         *
         * @param d One RVC X Camera
         * @return X2 RVC X object
         */
        public static X2 Create(Device device) => new X2() { m_handle = RVC_CSharp_DLL.X2_Create(device.m_handle) };

        /**
         * @brief Release all X2 resources after you use X2
         *
         * @param x RVC X2 object to be released
         */
        public static void Destroy(X2 x2) => RVC_CSharp_DLL.X2_Destroy(x2.m_handle);
        public void Destroy() => RVC_CSharp_DLL.X2_Destroy(m_handle);

        /**
         * @brief Check X2 is valid or not before use X2
         *
         * @return true Available
         * @return false Not available
         */
        public bool IsValid() => RVC_CSharp_DLL.X2_IsValid(m_handle);

        /**
         * @brief Open X2 before you use it
         *
         * @return true Success
         * @return false Failed
         */
        public bool Open() => RVC_CSharp_DLL.X2_Open(m_handle);

        /**
         * @brief Close X2 after you Open it
         */
        public void Close() => RVC_CSharp_DLL.X2_Close(m_handle);

        /**
         * @brief Check X2 is open or not
         *
         * @return true Is open
         * @return false Not open
         */
        public bool IsOpen() => RVC_CSharp_DLL.X2_IsOpen(m_handle);

        /**
         * @brief Check X2 is physically connected or not
         *
         * @return true Is physically connected
         * @return false Not physically connected
         */
        public bool IsPhysicallyConnected() => RVC_CSharp_DLL.X2_IsPhysicallyConnected(m_handle);

        /**
         * @brief Capture one point map and one image.This function will save capture options into camera.
         *
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool Capture(CaptureOptions opts) => RVC_CSharp_DLL.X2_Capture(m_handle, opts);

        /**
         * @brief Capture one point map and one image.This function will load capture options from camera.
         *
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool Capture() => RVC_CSharp_DLL.X2_Capture_(m_handle);

        /**
         * @brief
         *
         * @param cid Capture one image. This function will save capture options into camera. You can use GetImage() to
         * obtain 2D imgae
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool Capture2D(CameraID cid, CaptureOptions opts) => RVC_CSharp_DLL.X2_Capture2D(m_handle, cid, opts);

        /**
         * @brief
         *
         * @param cid Capture one image. This function will save capture options into camera. You can use GetImage() to
         * obtain 2D imgae
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool Capture2D(CameraID cid) => RVC_CSharp_DLL.X2_Capture2D_(m_handle, cid);

        /**
         * @brief Set the camera band width ratio
         *
         * @param percent Band width ratio
         * @return true Success
         * @return false Failed
         */
        public bool SetBandwidth(float percent) => RVC_CSharp_DLL.X2_SetBandwidth(m_handle, percent);

        /**
         * @brief Get the camera band width ratio
         *
         * @param percent Band width ratio
         * @return true Success
         * @return false Failed
         */
        public bool GetBandwidth(ref float percent) => RVC_CSharp_DLL.X2_GetBandwidth(m_handle, ref percent);

        /**
         * @brief Set the Transformation of output point cloud
         *
         * @param opts  Custom Transform Options
         * @return true
         * @return false
         */
        public bool SetCustomTransformation(CustomTransformOptions opts) => RVC_CSharp_DLL.X2_SetCustomTransformation(m_handle, opts);

        /**
         * @brief Get the Custom Transformation object
         *
         * @param opts
         * @return true
         * @return false
         */
        public bool GetCustomTransformation(ref CustomTransformOptions opts) => RVC_CSharp_DLL.X2_GetCustomTransformation(m_handle, ref opts);

        /**
         * @brief Get the Point Map object
         *
         * @return PointMap
         */
        public PointMap GetPointMap() => new PointMap() { m_handle = RVC_CSharp_DLL.X2_GetPointMap(m_handle) };

        /**
         * @brief Get the Mesh object
         *
         * @return Mesh
         */
        public Mesh GetMesh() => new Mesh() { m_handle = RVC_CSharp_DLL.X2_GetMesh(m_handle) };

        /**
         * @brief Get the Point Map object
         *
         * @return PointMap
         */
        public CorrespondMap GetCorrespondMap() => new CorrespondMap() { m_handle = RVC_CSharp_DLL.X2_GetCorrespondMap(m_handle) };

        /**
         * @brief Get the Image object
         *
         * @return Image
         */
        public Image GetImage(CameraID cid) => new Image() { m_handle = RVC_CSharp_DLL.X2_GetImage(m_handle, cid) };

        /**
         * @brief Get the DepthMap object
         *
         * @return DepthMap A DepthMap
         */
        public DepthMap GetDepthMap() => new DepthMap() { m_handle = RVC_CSharp_DLL.X2_GetDepthMap(m_handle) };

        /**
         * @brief Get the Confidence Map object
         *
         * @return ConfidenceMap
         */
        public ConfidenceMap GetConfidenceMap() => new ConfidenceMap() { m_handle = RVC_CSharp_DLL.X2_GetConfidenceMap(m_handle) };

        /**
         * @brief Get extrinsic matrix
         *
         * @param cid [in] option of {CameraID_Left, CameraID_Right}
         * @param matrix [out] the extrinsic matrix,len = 16
         * @return true for success
         */
        public bool GetExtrinsicMatrix(CameraID cid, float[] matrix) => RVC_CSharp_DLL.X2_GetExtrinsicMatrix(m_handle, cid, matrix);

        /**
         * @brief Get intrinsic parameters
         *
         * @param cid [in] option of {CameraID_Left, CameraID_Right}
         * @param instrinsicMatrix [out] intrinsic parameters of selected camera,len = 9
         * @param distortion [out] distortion parameter of selected camera,len = 5
         * @return true for success.
         */
        public bool GetIntrinsicParameters(CameraID cid, float[] instrinsicMatrix, float[] distortion) =>
            RVC_CSharp_DLL.X2_GetIntrinsicParameters(m_handle, cid, instrinsicMatrix, distortion);


        /**
         * @brief  GetProjectorTemperature
         * @note   TODO:
         * @param  &temperature:
         * @retval
         */
        public bool GetProjectorTemperature(ref float temperature) =>
            RVC_CSharp_DLL.X2_GetProjectorTemperature(m_handle, ref temperature);


        /**
         * @brief  GetCameraTemperature
         * @note   TODO:
         * @param  cid:
         * @param  seletor:
         * @param  &temperature:
         * @retval
         */
        public bool GetCameraTemperature(CameraID cid, CameraTempSelector seletor, ref float temperature) =>
            RVC_CSharp_DLL.X2_GetCameraTemperature(m_handle, cid, seletor, ref temperature);

        /**
         * @brief Only Color Camera can use this function. This function can get suitable white balance paramters
         *
         * @param wb_times how many images used for calculate the white balance paramters, default = 10
         * @param opts capture options. exposure_time_2d, gain_2d, gamma_2d will be used. use_projector_capturing_2d_image
         * == true, brightness will be used too.
         * @param roi auto white balance will be operated here
         * @return true
         * @return false
         */
        public bool AutoWhiteBalance(int wb_times, CaptureOptions opts, ROI roi) =>
            RVC_CSharp_DLL.X2_AutoWhiteBalance(m_handle, wb_times, opts, roi);

        /**
         * @brief Get the Exposure Time Range
         *
         * @param min_value exposure time minimum value
         * @param max_value exposure time maxinum value
         * @return true Success
         * @return false Failed
         */
        public bool GetExposureTimeRange(ref int min_value, ref int max_value) =>
            RVC_CSharp_DLL.X2_GetExposureTimeRange(m_handle, ref min_value, ref max_value);

        /**
         * @brief Get the Gain Range
         *
         * @param min_value gain minimum value
         * @param max_value gain minimum value
         * @return true Success
         * @return false Failed
         */
        public bool GetGainRange(ref float min_value, ref float max_value) =>
            RVC_CSharp_DLL.X2_GetGainRange(m_handle, ref min_value, ref max_value);

        /**
         * @brief Get the Gamma Range
         *
         * @param min_value gamma minimum value
         * @param max_value gamma minimum value
         * @return true Success
         * @return false Failed
         */
        public bool GetGammaRange(ref float min_value, ref float max_value) =>
            RVC_CSharp_DLL.X2_GetGammaRange(m_handle, ref min_value, ref max_value);

        /**
         * @brief Save capture option parameters
         *
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool SaveCaptureOptionParameters(CaptureOptions opts) =>
            RVC_CSharp_DLL.X2_SaveCaptureOptionParameters(m_handle, opts);

        /**
         * @brief Get capture option parameters
         *
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool LoadCaptureOptionParameters(ref CaptureOptions opts) =>
            RVC_CSharp_DLL.X2_LoadCaptureOptionParameters(m_handle, ref opts);

        /**
         * @brief Get auto capture setting. Exposure_time_2d, exposure_time_3d, projector_brightness, light_contrast_threshold will be adjusted automatically.
         * automatically
         *
         * @param opts
         * @return CaptureOptions
         */
        public bool GetAutoCaptureSetting(ref CaptureOptions opts, ROI roi) =>
            RVC_CSharp_DLL.X2_GetAutoCaptureSetting(m_handle, ref opts, roi);

        /**
         * @brief adjust 3D capturing parameters
         *
         * @param opts [in,out] capture options. if  hdr_exposure_times > 1, hdr_exposure_times and hdr_exposuretime_content
         * will be adjusted. If hdr_exposure_times equals to 1, exposure_time_3d will be adjusted.
         * @param roi [in] if width or height equal to 0, all image will be used.
         * @return true
         * @return false
         */
        public bool GetAutoHdrCaptureSetting(ref CaptureOptions opts, ROI roi) =>
            RVC_CSharp_DLL.X2_GetAutoHdrCaptureSetting(m_handle, ref opts, roi);

        /**
         * @brief Automatically adjust 2D exposure time (exposure_time_2d) in CaptureOptions.
         *
         * @param opts [in,out] capture options. exposure_time_2d will be adjusted automatically.
         * @param roi [in] region of interest used to evaluate brightness. If width or height equal to 0, full image is used.
         * @return true on success, false on failure (custom setting will be retained).
         */
        public bool GetAuto2DExposureTime(ref CaptureOptions opts, ROI roi) =>
            RVC_CSharp_DLL.X2_GetAuto2DExposureTime(m_handle, ref opts, roi);

        /**
         * @brief Get automatic noise removal results
         */
        public bool GetAutoNoiseRemovalSetting(ref CaptureOptions opts) =>
            RVC_CSharp_DLL.X2_GetAutoNoiseRemovalSetting(m_handle, ref opts);

        /**
        * @brief Load camera setting from local file .
        * @param filename [in]
        * @return true the content of file is correctly .
        * @return false the content of file is not correctly .
        */
        public bool LoadSettingFromFile(string filename) =>
            RVC_CSharp_DLL.X2_LoadSettingFromFile(m_handle, filename);

        /**
         * @brief Save camera setting to local file.
         * @param filename [in]
         * @return true Successfully written to the file.
         * @return false Failed write to file.
         */
        public bool SaveSettingToFile(string filename) =>
            RVC_CSharp_DLL.X2_SaveSettingToFile(m_handle, filename);

        /**
 * @brief Check whether the parameters of ROI meet the requirements.
 * @param roi [in] .
 * @return true
 * @return false
 */
        public bool CheckRoi(ROI roi) => RVC_CSharp_DLL.X2_CheckRoi(m_handle, roi);

        /**
         * @brief Automatically correct the parameters of ROI. You need to correct ROI before Capture/Captrue2D.
         * @param roi [in] If you want to get a maximum ROI, you can pass in the default value.
         * @return ROI Corrected ROI.
         */
        public ROI AutoAdjustRoi(ROI roi) => RVC_CSharp_DLL.X2_AutoAdjustRoi(m_handle, roi);

        /**
         * @brief Get the range of ROI.
         */
        public bool GetRoiRange(ref ROIRange range) => RVC_CSharp_DLL.X2_GetRoiRange(m_handle, ref range);

        /**
         * @brief Get Camera Resolution.
        */
        public bool GetCameraResolution(ref Size size) => RVC_CSharp_DLL.X2_GetCameraResolution(m_handle, ref size);

        /**
        * @brief Retrieves the camera timestamp in microseconds (µs)
        *
        * @param[out] timestamp Reference to store the retrieved timestamp value in microseconds (µs)
        * @return bool True if the timestamp was successfully retrieved, false otherwise
        */
        public bool GetTimestamp(ref UInt64 timestamp) => RVC_CSharp_DLL.X2_GetTimestamp(m_handle, ref timestamp);

        /**
        * @brief Resets the camera timestamp to zero
        *
        * Resets the internal camera timestamp value to 0 microseconds(µs).
        * This function is primarily used for synchronization with user clocks
        * or external timing references, allowing the camera's internal time
        * base to be aligned with user-defined timing requirements or to
        * initiate a new timing cycle based on user control.
        *
        * @return bool True if the timestamp was successfully reset to zero, false otherwise
        */
        public bool ResetTimestamp() => RVC_CSharp_DLL.X2_ResetTimestamp(m_handle);

        /**
         * @brief Start capture fixed line scan. Only support CaptureMode_FixedLineScan mode. This function will save
         * capture options into camera. Need to call the StopFixedLineScan interface to manually stop
         * @param opts CaptureOptions
         * @return true Success
         * @return false Failed
         */
        public bool StartFixedLineScan(CaptureOptions opts) => RVC_CSharp_DLL.X2_StartFixedLineScan(m_handle, opts);

        /**
         * @brief Start capture fixed line scan. Only support CaptureMode_FixedLineScan mode.
         * Need to call the StopFixedLineScan interface to manually stop
         *
         * @return true Success
         * @return false Failed
         */
        public bool StartFixedLineScan() => RVC_CSharp_DLL.X2_StartFixedLineScan_(m_handle);

        /**
         * @brief Get fixed line scan point map
         *
         * @return true Success
         * @return false Failed
         */
        public PointMap GetFixedLineScanPointMap() => new PointMap() { m_handle = RVC_CSharp_DLL.X2_GetFixedLineScanPointMap(m_handle) };

        /**
         * @brief Stop capture fixed line scan.
         *
         * @return true Success
         * @return false Failed
         */
        public bool StopFixedLineScan() => RVC_CSharp_DLL.X2_StopFixedLineScan(m_handle);

        /**
         * @brief Open ProtectiveCover
         *
         * @return true if success
         * @return false if failed
         */
        public bool OpenProtectiveCover() => RVC_CSharp_DLL.X2_OpenProtectiveCover(m_handle);
        /**
         * @brief Close ProtectiveCover
         *
         * @return true if success
         * @return false if failed
         */
        public bool CloseProtectiveCover() => RVC_CSharp_DLL.X2_CloseProtectiveCover(m_handle);
        /**
         * @brief Reset ProtectiveCover
         *
         * @return true if success
         * @return false if failed
         */
        public bool ResetProtectiveCover() => RVC_CSharp_DLL.X2_ResetProtectiveCover(m_handle);
        /**
         * @brief Get Status of ProtectiveCover
         * @return ProtectiveCoverStatus
         */
        public bool GetProtectiveCoverStatus(ref ProtectiveCoverStatus status) => RVC_CSharp_DLL.X2_GetProtectiveCoverStatus(m_handle, ref status);

        /**
         * @brief Save Encoded Images Data
         */
        public bool SaveEncodedImagesData(string address) => RVC_CSharp_DLL.X2_SaveEncodedImagesData(m_handle, address);


        public bool SetCurrentUserSet(int id) => RVC_CSharp_DLL.X2_SetCurrentUserSet(m_handle, id);

        public bool GetCurrentUserSet(ref int id) => RVC_CSharp_DLL.X2_GetCurrentUserSet(m_handle, id);

        public bool SetUserSetName(int id, string name) => RVC_CSharp_DLL.X2_SetUserSetName(m_handle, id, name);

        public bool GetUserSetName(int id, string name) => RVC_CSharp_DLL.X2_GetUserSetName(m_handle, id, name);
    };
    #endregion

    #region Special Functions
    public struct MarkerDetection
    {
        // To generate coded circle marker pattern, see: Examples/Python/Utils/GenerateCodedCircle.py
        [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public struct CodedCircleMarkerType
        {
            public CodedCircleMarkerType(int _N, double _r1_to_r0_ratio, double _r2_to_r0_ratio)
            {
                N = _N;
                r1_to_r0_ratio = _r1_to_r0_ratio;
                r2_to_r0_ratio = _r2_to_r0_ratio;
            }

            public int N;
            public double r1_to_r0_ratio;
            public double r2_to_r0_ratio;
        }

        [StructLayoutAttribute(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public struct CodedCircleMarker
        {
            public CodedCircleMarker(double _x, double _y, int _code)
            {
                x = _x;
                y = _y;
                code = _code;
            }

            public double x;
            public double y;
            public int code;
        }

        public static List<CodedCircleMarker> DetectCodedCircleMarker(Handle imageHandle, CodedCircleMarkerType type)
        {
            int marker_num = 0;
            int[] code = new int[1000];
            double[] x = new double[1000];
            double[] y = new double[1000];
            RVC_CSharp_DLL.MarkerDetection_DetectCodedCircleMarker(imageHandle, type, ref marker_num, code, x, y);
            List<CodedCircleMarker> result = new List<CodedCircleMarker>();
            for (int i = 0; i < marker_num; i++)
            {
                MarkerDetection.CodedCircleMarker codedCircleMarker = new MarkerDetection.CodedCircleMarker(x[i], y[i], code[i]);
                result.Add(codedCircleMarker);
            }
            return result;
        }

        public static int DetectConcentricCircleMarker2d(Handle imageHandle, ref List<double> pixel_xy)
        {
            int marker_num = 0;
            double[] xy = new double[2000];
            int ret = RVC_CSharp_DLL.MarkerDetection_DetectConcentricCircleMarker2d(imageHandle, ref marker_num, xy);
            pixel_xy = new List<double>();
            for (int i = 0; i < marker_num; i++)
            {
                pixel_xy.Add(xy[2 * i]);
                pixel_xy.Add(xy[2 * i + 1]);
            }
            return ret;
        }

        public static int DetectConcentricCircleMarker3d(Handle imageHandle, Handle pointMapHandle,
            ref List<double> pixel_xy, ref List<double> point_xyz)
        {
            int marker_num = 0;
            double[] xy = new double[2000];
            double[] xyz = new double[3000];
            int ret = RVC_CSharp_DLL.MarkerDetection_DetectConcentricCircleMarker3d(
                imageHandle, pointMapHandle, ref marker_num, xy, xyz);
            pixel_xy = new List<double>();
            point_xyz = new List<double>();
            for (int i = 0; i < marker_num; i++)
            {
                pixel_xy.Add(xy[2 * i]);
                pixel_xy.Add(xy[2 * i + 1]);
                point_xyz.Add(xyz[3 * i]);
                point_xyz.Add(xyz[3 * i + 1]);
                point_xyz.Add(xyz[3 * i + 2]);
            }
            return ret;
        }

        public static int TestAccuracy(Handle image, Handle pointmap, float[] camera_intrinsic,
                            float[] camera_distortion, int caliboard_pattern_size_width,
                            int caliboard_pattern_size_height, float caliboard_circle_center_standard_3d_distance_step,
                           [Out] float[] circle_center_2d, [Out] float[] circle_center_3d,
                           out float measuring_distance, out float error_percentage)
        {
            return RVC_CSharp_DLL.MarkerDetection_TestAccuracy(image, pointmap, camera_intrinsic,
                camera_distortion, caliboard_pattern_size_width, caliboard_pattern_size_height,
               caliboard_circle_center_standard_3d_distance_step, circle_center_2d, circle_center_3d,
              out measuring_distance, out error_percentage);
        }

    }

    public struct PointCloudStitching
    {
        /**
         * @brief Use the coded circle marker to get the transformation of point_map1 relative to point_map0 coordinate system.
         *
         * Notice:
         * 1. The image should be neither too bright nor too dark.
         * 2. The radius of the circle in the middle of the coded marker should be greater than 5 pixels (10 pixels is
         * recommended).
         * 3. The point cloud quality of the circle in the middle of the encoded marker should be good.
         * 4. There must be at least 3 circles in the public field of view (6 or more circles is recommended), and they cannot
         * be in a line.
         *
         * @return
         * error code:
         *  0: succeeds.
         * -1: fails. Because point_map0 or point_map1 is not valid.
         * -2: fails. Because image0 or image1 is not valid.
         * -3: fails. Because not enough markers are detected.
         * -4: fails. Because too few circles are in the public field of view.
         * -5: fails. Because point cloud of markers is not good.
         * -6: fails. Because the markers have been moved.
         */
        public static int GetTwoCameraTransformByCodedCircleMarker(Handle point_map0, Handle image0, Handle point_map1, Handle image1, MarkerDetection.CodedCircleMarkerType type,
            ref List<double> R, ref List<double> t)
        {
            double[] _R = new double[9];
            double[] _t = new double[3];
            int result = RVC_CSharp_DLL.PointCloudStitching_GetTwoCameraTransformByCodedCircleMarker(point_map0, image0, point_map1, image1, type, _R, _t);
            R = new List<double>(_R);
            t = new List<double>(_t);
            return result;
        }

        /**
         * @brief Transform the point cloud point_map1 to the coordinate system of point_map0.
         *        point_map1 = R * point_map1 + t
         */
        public static void TransformPointCloud(Handle point_map1, List<double> R, List<double> t)
        {
            RVC_CSharp_DLL.PointCloudStitching_TransformPointCloud(R.ToArray(), t.ToArray(), point_map1);
        }
    }

    #region Utils
    namespace Utils
    {
        public struct Point3D
        {
            public double X;
            public double Y;
            public double Z;

            public Point3D(double x = 0.0, double y = 0.0, double z = 0.0)
            {
                X = x;
                Y = y;
                Z = z;
            }
        }
        public class PointMap
        {
            private RVC_CSharp.PointMap pm;

            public PointMap(RVC_CSharp.PointMap pm)
            {
                this.pm = pm;
            }

            public Point3D At(int rows, int cols)
            {
                Point3D p = new Point3D();
                Size sz = pm.GetSize();

                if (!pm.IsValid())
                {
                    Debug.WriteLine("RVC::Utils: Invalid");
                    Debug.Assert(false);
                }
                else if (rows >= sz.height || cols >= sz.width)
                {
                    Debug.WriteLine($"RVC::Utils: Invalid rows and cols({rows}, {cols}), size({sz.height}, {sz.width})");
                    Debug.Assert(false);
                }
                else
                {
                    unsafe
                    {
                        double* data = (double*)pm.GetPointDataPtr().ToPointer();
                        int offset = 3 * (rows * sz.width + cols);
                        p.X = data[offset];
                        p.Y = data[offset + 1];
                        p.Z = data[offset + 2];
                    }
                }
                return p;
            }

            public void Set(int rows, int cols, Point3D p)
            {
                Size sz = pm.GetSize();

                if (!pm.IsValid())
                {
                    Debug.WriteLine("RVC::Utils: Invalid");
                    Debug.Assert(false);
                }
                else if (rows >= sz.height || cols >= sz.width)
                {
                    Debug.WriteLine($"RVC::Utils: Invalid rows and cols({rows}, {cols}), size({sz.height}, {sz.width})");
                    Debug.Assert(false);
                }
                else
                {
                    unsafe
                    {
                        double* data = (double*)pm.GetPointDataPtr().ToPointer();
                        int offset = 3 * (rows * sz.width + cols);
                        data[offset] = p.X;
                        data[offset + 1] = p.Y;
                        data[offset + 2] = p.Z;
                    }
                }
            }

            public void Save(string path)
            {
                pm.SavePlyBinary(path);
            }

            public void Save(string path, RVC_CSharp.Image img)
            {
                pm.SaveColorPointCloud(img, path);
            }

            public Size GetSize() => pm.GetSize();
        }

        public class Image
        {
            private RVC_CSharp.Image img;

            public Image(RVC_CSharp.Image img)
            {
                this.img = img;
            }

            public byte At(int rows, int cols)
            {
                Size sz = img.GetSize();

                if (!img.IsValid())
                {
                    Debug.WriteLine("RVC::Utils: Invalid");
                    Debug.Assert(false);
                    return 0;
                }
                else if (rows >= sz.height || cols >= sz.width)
                {
                    Debug.WriteLine($"RVC::Utils: Invalid rows and cols({rows}, {cols}), size({sz.height}, {sz.width})");
                    Debug.Assert(false);
                    return 0;
                }
                else
                {
                    unsafe
                    {
                        byte* ptr = (byte*)img.GetDataPtr().ToPointer();
                        return ptr[rows * sz.width + cols];
                    }
                }
            }

            public void Set(int rows, int cols, byte value)
            {
                Size sz = img.GetSize();

                if (!img.IsValid())
                {
                    Debug.WriteLine("RVC::Utils: Invalid");
                    Debug.Assert(false);
                }
                else if (rows >= sz.height || cols >= sz.width)
                {
                    Debug.WriteLine($"RVC::Utils: Invalid rows and cols({rows}, {cols}), size({sz.height}, {sz.width})");
                    Debug.Assert(false);
                }
                else
                {
                    unsafe
                    {
                        byte* ptr = (byte*)img.GetDataPtr().ToPointer();
                        ptr[rows * sz.width + cols] = value;
                    }
                }
            }

            public void SaveImage(string path)
            {
                img.SaveImage(path);
            }

            public Size GetSize() => img.GetSize();
            public RVC_CSharp.Image GetImage() => img;
        }

        public class ConfidenceMap
        {
            private RVC_CSharp.ConfidenceMap cm;

            public ConfidenceMap(RVC_CSharp.ConfidenceMap cm)
            {
                this.cm = cm;
            }

            public double At(int rows, int cols)
            {
                Size sz = cm.GetSize();

                if (!cm.IsValid())
                {
                    Debug.WriteLine("RVC::Utils: Invalid");
                    Debug.Assert(false);
                    return 0;
                }
                else if (rows >= sz.height || cols >= sz.width)
                {
                    Debug.WriteLine($"RVC::Utils: Invalid rows and cols({rows}, {cols}), size({sz.height}, {sz.width})");
                    Debug.Assert(false);
                    return 0;
                }
                else
                {
                    unsafe
                    {
                        double* ptr = (double*)cm.GetDataPtr().ToPointer();
                        return ptr[rows * sz.width + cols];
                    }
                }
            }

            public void Set(int rows, int cols, double value)
            {
                Size sz = cm.GetSize();

                if (!cm.IsValid())
                {
                    Debug.WriteLine("RVC::Utils: Invalid");
                    Debug.Assert(false);
                }
                else if (rows >= sz.height || cols >= sz.width)
                {
                    Debug.WriteLine($"RVC::Utils: Invalid rows and cols({rows}, {cols}), size({sz.height}, {sz.width})");
                    Debug.Assert(false);
                }
                else
                {
                    unsafe
                    {
                        double* ptr = (double*)cm.GetDataPtr().ToPointer();
                        ptr[rows * sz.width + cols] = value;
                    }
                }
            }

            public Size GetSize() => cm.GetSize();

        }

        public class DepthMap
        {
            private RVC_CSharp.DepthMap dm;

            public DepthMap(RVC_CSharp.DepthMap dm)
            {
                this.dm = dm;
            }

            public double At(int rows, int cols)
            {
                Size sz = dm.GetSize();

                if (!dm.IsValid())
                {
                    Debug.WriteLine("RVC::Utils: Invalid");
                    Debug.Assert(false);
                    return 0;
                }
                else if (rows >= sz.height || cols >= sz.width)
                {
                    Debug.WriteLine($"RVC::Utils: Invalid rows and cols({rows}, {cols}), size({sz.height}, {sz.width})");
                    Debug.Assert(false);
                    return 0;
                }
                else
                {
                    unsafe
                    {
                        double* ptr = (double*)dm.GetDataPtr().ToPointer();
                        return ptr[rows * sz.width + cols];
                    }
                }
            }

            public void Set(int rows, int cols, double value)
            {
                Size sz = dm.GetSize();

                if (!dm.IsValid())
                {
                    Debug.WriteLine("RVC::Utils: Invalid");
                    Debug.Assert(false);
                }
                else if (rows >= sz.height || cols >= sz.width)
                {
                    Debug.WriteLine($"RVC::Utils: Invalid rows and cols({rows}, {cols}), size({sz.height}, {sz.width})");
                    Debug.Assert(false);
                }
                else
                {
                    unsafe
                    {
                        double* ptr = (double*)dm.GetDataPtr().ToPointer();
                        ptr[rows * sz.width + cols] = value;
                    }
                }
            }
            public void Save(string path)
            {
                dm.SaveDepthMap(path);
            }

            public Size GetSize() => dm.GetSize();
        }
    }

    #endregion

    public struct ExternalColorCamera
    {
        /**
 * @brief The user needs to calibrate the external camera by themselves first(The distortion parameter model
 * is [k1, k2, p1, p2, k3]).
 * Then capture the calibration board at three distances: near, middle and far, and at the same time use
 * the external camera to capture three coresponding images. Finally, call this API to get the extrinsic matrix of the
 * external camera to the RVC camera. The camera resolution does not need to be the same as the RVC camera resolution.
 * The calibration board should large enough, and the minimum recommended size is no less than 1/20 of the field of
 * view.
 * Usage example: GetExternalColorCameraPointMap.cpp / GetExternalColorCameraPointMap.py
 * The API is experimental and may change in the future.
 */

        /**
         * @param internal_camera_image0: First image taken by the RVC camera in the nearest distance.
         * @param internal_camera_point_map0: First point map taken by the RVC camera.
         * @param external_camera_image_data0: First corresponding image taken by the external camera.
         * @param internal_camera_image1: Second image taken by the RVC camera in the middle distance.
         * @param internal_camera_point_map1: Second point map taken by the RVC camera.
         * @param external_camera_image_data1: Second corresponding image taken by the external camera.
         * @param internal_camera_image2: Third image taken by the RVC camera in the furthest distance.
         * @param internal_camera_point_map2: Third point map taken by the RVC camera.
         * @param external_camera_image_data2: Third corresponding image taken by the external camera.
         * @param external_camera_width: The width of the external camera image.
         * @param external_camera_height: The height of the external camera image.
         * @param external_camera_intrinsic_matrix: The 3 * 3 intrinsic matrix of the external camera.
         * @param external_camera_camera_distortion: The 5 distortion parameters of the external camera. The order is [k1, k2,
         * p1, p2, k3].
         *
         * @return
         * external_camera_extrinsic_matrix:
         * The 4 * 4 extrinsic matrix of the external camera. Note that users need to allocate memory outside the API first, and
         * then pass the pointer in.
         *
         * @return
         * error:
         * Reprojection error(unit: pixel). The smaller the value, the better the extrinsic matrix calibration result.
         *
         * @return
         * error code:
         * 0: succeeds.
         * -1: fails. Because internal_camera_image0 is not good and it fails to detect calibration board.
         * -2: fails. Because internal_camera_point_map0 is not good and it fails to extract the circle center of calibration
         * board point cloud.
         * -3: fails. Because external_camera_image0 is not good and it fails to detect calibration board.
         * -4: fails. Because internal_camera_image1 is not good and it fails to detect calibration board.
         * -5: fails. Because internal_camera_point_map1 is not good and it fails to extract the circle center of calibration
         * board point cloud.
         * -6: fails. Because external_camera_image1 is not good and it fails to detect calibration board.
         * -7: fails. Because internal_camera_image2 is not good and it fails to detect calibration board.
         * -8: fails. Because internal_camera_point_map2 is not good and it fails to extract the circle center of calibration
         * board point cloud.
         * -9: fails. Because external_camera_image2 is not good and it fails to detect calibration board.
         */
        public static int GetExternalCameraExtrinsicMatrix(Handle internal_camera_image0, Handle internal_camera_point_map0,
           [MarshalAs(UnmanagedType.LPArray)] byte[] external_camera_image_data0, Handle internal_camera_image1, Handle internal_camera_point_map1,
           [MarshalAs(UnmanagedType.LPArray)] byte[] external_camera_image_data1, Handle internal_camera_image2, Handle internal_camera_point_map2,
           [MarshalAs(UnmanagedType.LPArray)] byte[] external_camera_image_data2, int externalWidth, int externalHeight,
            [MarshalAs(UnmanagedType.LPArray)] float[] intrinsicMatrix,
            [MarshalAs(UnmanagedType.LPArray)] float[] distortionParams,
            float[] extrinsicMatrix,
            out double reprojectionError)
        {
            return RVC_CSharp_DLL.ExternalColorCamera_GetExternalCameraExtrinsicMatrix(internal_camera_image0, internal_camera_point_map0,
                 external_camera_image_data0, internal_camera_image1, internal_camera_point_map1,
                 external_camera_image_data1, internal_camera_image2, internal_camera_point_map2,
                 external_camera_image_data2, externalWidth, externalHeight, intrinsicMatrix,
                 distortionParams, extrinsicMatrix, out reprojectionError);
        }

        /**
         * @brief Use the point cloud captured by the RVC camera to get the point cloud of the external camera.
         *
         * @param internal_camera_point_map: Use GetPointMap() to get the 3D point map captured by the RVC camera.
         * The coordinate system and length unit of internal_camera_point_map must be the same as the coordinate system of the
         * point cloud during calibration.
         * @param external_camera_width: The width of the external camera image.
         * @param external_camera_height: The height of the external camera image.
         * @param external_camera_intrinsic_matrix: The 3 * 3 intrinsic matrix of the external camera.
         * @param external_camera_camera_distortion: The 5 distortion parameters of the external camera. The order is [k1, k2,
         * p1, p2, k3].
         * @param external_camera_extrinsic_matrix: The 4 * 4 extrinsic matrix of the external camera obtained by
         * GetExternalCameraExtrinsicMatrix() above.
         *
         * @return
         * external_camera_point_map:
         * The point map of the external camera. The resolution of the external camera point map is the same as the external
         * camera image.
         */
        public static PointMap GetExternalCameraPointMap(Handle internal_camera_point_map,
            int externalWidth, int externalHeight,
            [MarshalAs(UnmanagedType.LPArray)] float[] intrinsicMatrix,
            [MarshalAs(UnmanagedType.LPArray)] float[] distortionParams,
            [MarshalAs(UnmanagedType.LPArray)] float[] extrinsicMatrix)
        {
            return RVC_CSharp_DLL.ExternalColorCamera_GetExternalCameraPointMap(internal_camera_point_map, externalWidth, externalHeight,
                intrinsicMatrix, distortionParams, extrinsicMatrix);
        }
    }
    #endregion

    #region Compensator

    /// <summary>
    /// Point cloud compensator wrapper for C# (Experimental)
    /// </summary>
    public class Compensator : IDisposable
    {
        /// <summary>
        /// Underlying C handle
        /// </summary>
        public CCompensatorHandle Handle { get; private set; }

        /// <summary>
        /// Create a compensator instance
        /// </summary>
        public Compensator()
        {
            Handle = RVC_CSharp_DLL.Compensator_Create();
            if (Handle.sid == IntPtr.Zero)
            {
                throw new InvalidOperationException("Failed to create compensator");
            }
        }

        /// <summary>
        /// Check if the compensator is valid
        /// </summary>
        public bool IsValid => RVC_CSharp_DLL.Compensator_IsValid(Handle);

        /// <summary>
        /// Initialize compensator with reference data
        /// </summary>
        /// <param name="pmRef">Reference point cloud (camera coordinates)</param>
        /// <param name="imgRef">Reference image</param>
        /// <param name="markerType">Marker type (calibration board or concentric circles)</param>
        public void Initialize(PointMap pmRef, Image imgRef, CompensatorMarkerType markerType)
        {
            if (!pmRef.IsValid())
                throw new ArgumentNullException(nameof(pmRef));
            if (!imgRef.IsValid())
                throw new ArgumentNullException(nameof(imgRef));

            int ret = RVC_CSharp_DLL.Compensator_Initialize(Handle, pmRef.m_handle, imgRef.m_handle, (int)markerType);
            if (ret != 0)
            {
                throw new InvalidOperationException($"Compensator_Initialize failed with code {ret}");
            }
        }

        /// <summary>
        /// Update compensator with current data
        /// </summary>
        /// <param name="pm">Current point cloud (camera coordinates)</param>
        /// <param name="img">Current image</param>
        /// <returns>Drift distance (meters)</returns>
        public double Update(PointMap pm, Image img)
        {
            double drift = 0;
            int ret = RVC_CSharp_DLL.Compensator_Update(Handle, pm.m_handle, img.m_handle, ref drift);
            if (ret != 0)
            {
                throw new InvalidOperationException($"Compensator_Update failed with code {ret}");
            }
            return drift;
        }

        /// <summary>
        /// Apply compensation to a point cloud
        /// </summary>
        /// <param name="pm">Point cloud to compensate (in-place)</param>
        public void Apply(PointMap pm)
        {
            int ret = RVC_CSharp_DLL.Compensator_Apply(Handle, pm.m_handle);
            if (ret != 0)
            {
                throw new InvalidOperationException($"Compensator_Apply failed with code {ret}");
            }
        }

        /// <summary>
        /// Release resources
        /// </summary>
        public void Dispose()
        {
            if (IsValid)
            {
                RVC_CSharp_DLL.Compensator_Destroy(Handle);
                Handle = new CCompensatorHandle(); // Invalidate handle
            }
            GC.SuppressFinalize(this);
        }

        ~Compensator()
        {
            Dispose();
        }
    }

    #endregion

    #region DLL

    public class RVC_CSharp_DLL
    {
        #region Other

        [DllImport("RVC_C.dll")]
        public extern static string ImageType_ToString(ImageType type);

        [DllImport("RVC_C.dll")]
        public extern static int ImageType_GetPixelSize(ImageType type);

        [DllImport("RVC_C.dll")]
        public extern static string PointMapType_ToString(PointMapType type);

        #endregion

        #region System

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool System_Init();

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool System_IsInit();

        [DllImport("RVC_C.dll")]
        public extern static void System_ShutDown();

        [DllImport("RVC_C.dll")]
        public extern static void System_ListDevices(int[] pdevices, int len, ref int actual_size,
            SystemListDeviceType opt = SystemListDeviceType.All);

        [DllImport("RVC_C.dll")]
        public extern static void System_FindDevice(string serialNumber, ref Handle deviceHandle);

        [DllImport("RVC_C.dll")]
        public extern static int System_GetLastError();

        [DllImport("RVC_C.dll",
            CallingConvention = CallingConvention.Cdecl,
            CharSet = CharSet.Ansi)]
        public extern static IntPtr System_GetVersion();

        [DllImport("RVC_C.dll")]
        public extern static string System_GetLastErrorMessage();

        #endregion

        #region Device

        [DllImport("RVC_C.dll")]
        public extern static void Device_Destroy(Handle devicehandle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool Device_IsValid(Handle devicehandle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool Device_IsFirmwareMatch(Handle devicehandle);

        [DllImport("RVC_C.dll")]
        public extern static void Device_Print(Handle devicehandle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool Device_GetDeviceInfo(Handle devicehandle, ref DeviceInfo pinfo);

        [DllImport("RVC_C.dll")]
        public extern static int Device_SetNetworkConfig(Handle devicehandle, NetworkDevice d, NetworkType type, string ip, string netMask,
            string gateway);

        [DllImport("RVC_C.dll")]
        public extern static int Device_GetNetworkConfig(Handle devicehandle, NetworkDevice d, ref NetworkType type, StringBuilder ip, StringBuilder netMask, StringBuilder gateway, ref NetworkDeviceStatus_ status);

        [DllImport("RVC_C.dll")]
        public extern static int Device_AutoConfigureNetwork(Handle devicehandle);

        #endregion

        #region X1

        [DllImport("RVC_C.dll")]
        public extern static Handle X1_Create(Handle deviceHandle, CameraID id);

        [DllImport("RVC_C.dll")]
        public extern static void X1_Destroy(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_IsValid(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_Open(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        public extern static void X1_Close(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_IsOpen(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_IsPhysicallyConnected(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_Capture(Handle x1Handle, X1.CaptureOptions opts);
        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_Capture_(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_Capture2D(Handle x1Handle, X1.CaptureOptions opts);
        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_Capture2D_(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_SetBandwidth(Handle x1Handle, float percent);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetBandwidth(Handle x1Handle, ref float percent);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_SetCustomTransformation(Handle x1Handle, X1.CustomTransformOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetCustomTransformation(Handle x1Handle, ref X1.CustomTransformOptions opts);

        [DllImport("RVC_C.dll")]
        public extern static Handle X1_GetImage(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        public extern static Handle X1_GetDepthMap(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        public extern static Handle X1_GetPointMap(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        public extern static Handle X1_GetMesh(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        public extern static Handle X1_GetConfidenceMap(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetExtrinsicMatrix(Handle x1Handle, float[] matrix);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetIntrinsicParameters(Handle x1Handle, float[] instrinsic_matrix, float[] distortion);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetProjectorTemperature(Handle x1Handle, ref float temperature);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetCameraTemperature(Handle x1Handle, CameraTempSelector seletor, ref float temperature);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_SetBalanceRatio(Handle x1Handle, BalanceSelector selector, float value);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetBalanceRatio(Handle x1Handle, BalanceSelector selector, ref float value);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetBalanceRange(Handle x1Handle, BalanceSelector selector, ref float min_value, ref float max_value);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_AutoWhiteBalance(Handle x1Handle, int wb_times, X1.CaptureOptions opts, ROI roi);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetExposureTimeRange(Handle x1Handle, ref int min_value, ref int max_value);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetGainRange(Handle x1Handle, ref float min_value, ref float max_value);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetGammaRange(Handle x1Handle, ref float min_value, ref float max_value);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_SaveCaptureOptionParameters(Handle x1Handle, X1.CaptureOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_LoadCaptureOptionParameters(Handle x1Handle, ref X1.CaptureOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetAutoCaptureSetting(Handle x1Handle, ref X1.CaptureOptions opts, ROI roi);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetAutoHdrCaptureSetting(Handle x1Handle, ref X1.CaptureOptions opts, ROI roi);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetAuto2DExposureTime(Handle x1Handle, ref X1.CaptureOptions opts, ROI roi);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetAutoNoiseRemovalSetting(Handle x1Handle, ref X1.CaptureOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_LoadSettingFromFile(Handle x1Handle, string filename);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_SaveSettingToFile(Handle x1Handle, string filename);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_CheckRoi(Handle x1Handle, ROI roi);

        [DllImport("RVC_C.dll")]
        public extern static ROI X1_AutoAdjustRoi(Handle x1Handle, ROI roi);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetRoiRange(Handle x1Handle, ref ROIRange range);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetCameraResolution(Handle x1Handle, ref Size size);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_OpenProtectiveCover(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_CloseProtectiveCover(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_ResetProtectiveCover(Handle x1Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetProtectiveCoverStatus(Handle x1Handle, ref ProtectiveCoverStatus status);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        public delegate void X1CollectionCallBackPtr(X1CollectionCallBackInfo info, X1.CaptureOptions options, IntPtr p);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        public delegate void X1CalculationCallBackPtr(X1CalculationCallBackInfo info, X1.CaptureOptions options, IntPtr p);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_SetCollectionCallBack(Handle x1Handle, X1CollectionCallBackPtr callback, IntPtr p);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_SetCalculationCallBack(Handle x1Handle, X1CalculationCallBackPtr callback, IntPtr p);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_SaveEncodedImagesData(Handle x1Handle, string addr);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_SetCurrentUserSet(Handle x1Handle, int id);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetCurrentUserSet(Handle x1Handle, int id);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_SetUserSetName(Handle x1Handle, int id, [MarshalAs(UnmanagedType.LPStr)] string name);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X1_GetUserSetName(Handle x1Handle, int id, [MarshalAs(UnmanagedType.LPStr)] string name);
        #endregion

        #region X2

        [DllImport("RVC_C.dll")]
        public extern static Handle X2_Create(Handle deviceHandle);

        [DllImport("RVC_C.dll")]
        public extern static void X2_Destroy(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_IsValid(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_Open(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        public extern static void X2_Close(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_IsOpen(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_IsPhysicallyConnected(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_Capture(Handle x2Handle, X2.CaptureOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_Capture_(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_Capture2D(Handle x2Handle, CameraID cid, X2.CaptureOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_Capture2D_(Handle x2Handle, CameraID cid);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_SetBandwidth(Handle x2Handle, float percent);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetBandwidth(Handle x2Handle, ref float percent);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_SetCustomTransformation(Handle x2Handle, X2.CustomTransformOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetCustomTransformation(Handle x2Handle, ref X2.CustomTransformOptions opts);

        [DllImport("RVC_C.dll")]
        public extern static Handle X2_GetPointMap(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        public extern static Handle X2_GetMesh(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        public extern static Handle X2_GetCorrespondMap(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        public extern static Handle X2_GetImage(Handle x2Handle, CameraID cid);

        [DllImport("RVC_C.dll")]
        public extern static Handle X2_GetDepthMap(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        public extern static Handle X2_GetConfidenceMap(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetExtrinsicMatrix(Handle x2Handle, CameraID cid, float[] matrix);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetIntrinsicParameters(Handle x2Handle, CameraID cid, float[] instrinsicMatrix, float[] distortion);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetProjectorTemperature(Handle x2Handle, ref float temperature);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetCameraTemperature(Handle x2Handle, CameraID cid, CameraTempSelector seletor, ref float temperature);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_AutoWhiteBalance(Handle x2Handle, int wb_times, X2.CaptureOptions opts, ROI roi);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetExposureTimeRange(Handle x2Handle, ref int min_value, ref int max_value);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetGainRange(Handle x2Handle, ref float min_value, ref float max_value);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetGammaRange(Handle x2Handle, ref float min_value, ref float max_value);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_SaveCaptureOptionParameters(Handle x2Handle, X2.CaptureOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_LoadCaptureOptionParameters(Handle x2Handle, ref X2.CaptureOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetAutoCaptureSetting(Handle x2Handle, ref X2.CaptureOptions opts, ROI roi);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetAutoHdrCaptureSetting(Handle x2Handle, ref X2.CaptureOptions opts, ROI roi);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetAuto2DExposureTime(Handle x2Handle, ref X2.CaptureOptions opts, ROI roi);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetAutoNoiseRemovalSetting(Handle x2Handle, ref X2.CaptureOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_LoadSettingFromFile(Handle x2Handle, string filename);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_SaveSettingToFile(Handle x2Handle, string filename);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_CheckRoi(Handle x2Handle, ROI roi);

        [DllImport("RVC_C.dll")]
        public extern static ROI X2_AutoAdjustRoi(Handle x2Handle, ROI roi);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetRoiRange(Handle x2Handle, ref ROIRange range);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetCameraResolution(Handle x2Handle, ref Size size);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetTimestamp(Handle x2Handle, ref UInt64 timestamp);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_ResetTimestamp(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_StartFixedLineScan(Handle x2Handle, X2.CaptureOptions opts);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_StartFixedLineScan_(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        public extern static Handle X2_GetFixedLineScanPointMap(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_StopFixedLineScan(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_OpenProtectiveCover(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_CloseProtectiveCover(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_ResetProtectiveCover(Handle x2Handle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetProtectiveCoverStatus(Handle x2Handle, ref ProtectiveCoverStatus status);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        public delegate void X2CollectionCallBackPtr(X2CollectionCallBackInfo info, X2.CaptureOptions options, IntPtr p);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        public delegate void X2CalculationCallBackPtr(X2CalculationCallBackInfo info, X2.CaptureOptions options, IntPtr p);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        public delegate void X2FixedLineScanCallBackPtr(X2FixedLineScanCallBackInfo info, IntPtr p);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_SetCollectionCallBack(Handle x2Handle, X2CollectionCallBackPtr callback, IntPtr p);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_SetCalculationCallBack(Handle x2Handle, X2CalculationCallBackPtr callback, IntPtr p);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_SetFixedLineScanCallback(Handle x2Handle, X2FixedLineScanCallBackPtr callback, IntPtr p);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_SaveEncodedImagesData(Handle x2Handle, string addr);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_SetCurrentUserSet(Handle x2Handle, int id);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetCurrentUserSet(Handle x2Handle, int id);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_SetUserSetName(Handle x2Handle, int id, [MarshalAs(UnmanagedType.LPStr)] string name);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool X2_GetUserSetName(Handle x2Handle, int id, [MarshalAs(UnmanagedType.LPStr)] string name);

        #endregion

        #region Image

        [DllImport("RVC_C.dll")]
        public extern static Handle Image_Create(ImageType it, Size sz, IntPtr data, bool own_data = true);

        [DllImport("RVC_C.dll")]
        public extern static Handle Image_CreateFromFile(string addr);

        [DllImport("RVC_C.dll")]
        public extern static void Image_Destroy(Handle imageHandle, bool no_reuse = true);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool Image_IsValid(Handle imageHandle);

        [DllImport("RVC_C.dll")]
        public extern static Size Image_GetSize(Handle imageHandle);

        [DllImport("RVC_C.dll")]
        public extern static ImageType Image_GetType(Handle imageHandle);

        [DllImport("RVC_C.dll")]
        public extern static IntPtr Image_GetDataPtr(Handle imageHandle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool Image_SaveImage(Handle imageHandle, string addr);

        [DllImport("RVC_C.dll")]
        public extern static UInt64 Image_GetTimestamp(Handle imageHandle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool Image_SetTimestamp(Handle imageHandle, UInt64 timestamp);

        #endregion

        #region DepthMap

        [DllImport("RVC_C.dll")]
        public extern static Handle DepthMap_Create(Size sz, IntPtr data, bool own_data = true);

        [DllImport("RVC_C.dll")]
        public extern static void DepthMap_Destroy(Handle depthHandle, bool no_reuse = true);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool DepthMap_IsValid(Handle depthHandle);

        [DllImport("RVC_C.dll")]
        public extern static Size DepthMap_GetSize(Handle depthHandle);

        [DllImport("RVC_C.dll")]
        public extern static IntPtr DepthMap_GetDataPtr(Handle depthHandle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool DepthMap_SaveDepthMap(Handle depthHandle, string address, bool is_m = true);

        #endregion

        #region PointMap

        [DllImport("RVC_C.dll")]
        public extern static Handle PointMap_Create(PointMapType type, Size size, IntPtr data, bool owndata = true);

        [DllImport("RVC_C.dll")]
        public extern static Handle PointMap_CreateFromFile(string file, Size size, PointMapUnit unit);

        [DllImport("RVC_C.dll")]
        public extern static void PointMap_Destroy(Handle pointMapHandle, bool no_reuse = true);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool PointMap_IsValid(Handle pointMapHandle);

        [DllImport("RVC_C.dll")]
        public extern static Size PointMap_GetSize(Handle pointMapHandle);

        [DllImport("RVC_C.dll")]
        public extern static IntPtr PointMap_GetPointDataPtr(Handle pointMapHandle);

        [DllImport("RVC_C.dll")]
        public extern static IntPtr PointMap_GetNormalDataPtr(Handle pointMapHandle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool PointMap_GetPointMapSeperated(Handle pointMapHandle, double[] x, double[] y, double[] z, double scale = 1.0);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool PointMap_Save(Handle pointMapHandle, [MarshalAs(UnmanagedType.LPUTF8Str)] string filename, PointMapUnit unit, bool isBinary, Handle imageHandle);

        [DllImport("RVC_C.dll")]
        public extern static UInt64 PointMap_GetTimestamp(Handle pointMapHandle);

        [DllImport("RVC_C.dll")]
        public extern static bool PointMap_SetTimestamp(Handle pointMapHandle, UInt64 timestamp);
        #endregion

        #region Mesh

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool Mesh_IsValid(Handle meshHandle);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool Mesh_Save(Handle meshHandle, [MarshalAs(UnmanagedType.LPUTF8Str)] string filename, PointMapUnit unit);

        [DllImport("RVC_C.dll")]
        public extern static void Mesh_Destroy(Handle meshHandle, bool no_reuse = true);

        #endregion

        #region CorrespondMap

        [DllImport("RVC_C.dll")]
        public extern static Handle CorrespondMap_Create(Size sz, IntPtr data, bool own_data = true);

        [DllImport("RVC_C.dll")]
        public extern static void CorrespondMap_Destroy(Handle correspondHandle, bool no_reuse = true);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool CorrespondMap_IsValid(Handle correspondHandle);

        [DllImport("RVC_C.dll")]
        public extern static Size CorrespondMap_GetSize(Handle correspondHandle);

        [DllImport("RVC_C.dll")]
        public extern static IntPtr CorrespondMap_GetDataPtr(Handle correspondHandle);

        #endregion

        #region ConfidenceMap

        [DllImport("RVC_C.dll")]
        public extern static Handle ConfidenceMap_Create(Size sz, IntPtr data, bool own_data = true);

        [DllImport("RVC_C.dll")]
        public extern static void ConfidenceMap_Destroy(Handle confidenceHandle, bool no_reuse = true);

        [DllImport("RVC_C.dll")]
        [return: MarshalAs(UnmanagedType.I1)]
        public extern static bool ConfidenceMap_IsValid(Handle confidenceHandle);

        [DllImport("RVC_C.dll")]
        public extern static Size ConfidenceMap_GetSize(Handle confidenceHandle);

        [DllImport("RVC_C.dll")]
        public extern static IntPtr ConfidenceMap_GetDataPtr(Handle confidenceHandle);

        #endregion

        #region Special Functions
        [DllImport("RVC_C.dll")]
        public extern static void MarkerDetection_DetectCodedCircleMarker(Handle imageHandle, MarkerDetection.CodedCircleMarkerType type, ref int marker_num, int[] code, double[] x, double[] y);

        [DllImport("RVC_C.dll")]
        public extern static int MarkerDetection_DetectConcentricCircleMarker2d(Handle imageHandle, ref int marker_num, double[] pixel_xy);

        [DllImport("RVC_C.dll")]
        public extern static int MarkerDetection_DetectConcentricCircleMarker3d(Handle imageHandle, Handle pointmapHandle, ref int marker_num, double[] pixel_xy, double[] point_xyz);

        [DllImport("RVC_C.dll")]
        public extern static int MarkerDetection_TestAccuracy(Handle image, Handle pointMap, [In] float[] camera_intrinsic,
                            float[] camera_distortion, int caliboard_pattern_size_width,
                            int caliboard_pattern_size_height, float caliboard_circle_center_standard_3d_distance_step, [Out] float[] circle_center_2d,
                           [Out] float[] circle_center_3d, out float measuring_distance, out float error_percentage);

        [DllImport("RVC_C.dll")]
        public extern static int PointCloudStitching_GetTwoCameraTransformByCodedCircleMarker(Handle point_map0, Handle image0, Handle point_map1, Handle image1, MarkerDetection.CodedCircleMarkerType type, double[] R,
    double[] t);

        [DllImport("RVC_C.dll")]
        public extern static void PointCloudStitching_TransformPointCloud(double[] R, double[] t, Handle point_map);

        [DllImport("RVC_C.dll")]
        public extern static int ExternalColorCamera_GetExternalCameraExtrinsicMatrix(Handle internal_camera_image0, Handle internal_camera_point_map0,
           [MarshalAs(UnmanagedType.LPArray)] byte[] external_camera_image_data0, Handle internal_camera_image1, Handle internal_camera_point_map1,
           [MarshalAs(UnmanagedType.LPArray)] byte[] external_camera_image_data1, Handle internal_camera_image2, Handle internal_camera_point_map2,
           [MarshalAs(UnmanagedType.LPArray)] byte[] external_camera_image_data2, int externalWidth, int externalHeight,
            [MarshalAs(UnmanagedType.LPArray)] float[] intrinsicMatrix,
            [MarshalAs(UnmanagedType.LPArray)] float[] distortionParams,
            float[] extrinsicMatrix,
            out double reprojectionError);

        [DllImport("RVC_C.dll")]
        public extern static PointMap ExternalColorCamera_GetExternalCameraPointMap(Handle internal_camera_point_map,
            int externalWidth, int externalHeight,
            [MarshalAs(UnmanagedType.LPArray)] float[] intrinsicMatrix,
            [MarshalAs(UnmanagedType.LPArray)] float[] distortionParams,
            [MarshalAs(UnmanagedType.LPArray)] float[] extrinsicMatrix);
        #endregion

        #region Compensator Functions

        [DllImport("RVC_C.dll", CallingConvention = CallingConvention.StdCall)]
        public static extern CCompensatorHandle Compensator_Create();

        [DllImport("RVC_C.dll", CallingConvention = CallingConvention.StdCall)]
        public static extern void Compensator_Destroy(CCompensatorHandle handle);

        [DllImport("RVC_C.dll", CallingConvention = CallingConvention.StdCall)]
        public static extern bool Compensator_IsValid(CCompensatorHandle handle);

        [DllImport("RVC_C.dll", CallingConvention = CallingConvention.StdCall)]
        public static extern int Compensator_Initialize(
            CCompensatorHandle handle,
            Handle pm_reference,
            Handle img_reference,
            int markerType
        );

        [DllImport("RVC_C.dll", CallingConvention = CallingConvention.StdCall)]
        public static extern int Compensator_Update(
            CCompensatorHandle handle,
            Handle pm,
            Handle img,
            ref double driftDistance
        );

        [DllImport("RVC_C.dll", CallingConvention = CallingConvention.StdCall)]
        public static extern int Compensator_Apply(
            CCompensatorHandle handle,
            Handle pm
        );

        #endregion

    }

    #endregion

}
