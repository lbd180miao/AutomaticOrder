pub mod config;

use e_utils::res::CResult;
use hik_rs::mvs_sdk::types::{
    MvAccessMode, MvCcDeviceInfo, MvCcDeviceInfoList, MvEnumDeviceLayerType, MvFrameOut,
    MvSaveImgToFileParam,
};
use hik_rs::mvs_sdk::{create_gige_device_info, HcMvsCoreSdk};
use hik_rs::Lib;
use std::env;
use std::ffi::CString;
use std::fs;
use std::mem;
use std::os::raw::{c_char, c_uchar, c_uint, c_ushort};
use std::path::PathBuf;

#[cfg(feature = "extension-module")]
use pyo3::prelude::*;

#[cfg(feature = "extension-module")]
use config::EnvConfig;

/// 图像格式枚举
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(feature = "extension-module", pyo3::pyclass)]
pub enum ImageFormat {
    /// BMP 格式（无损，文件较大）
    BMP,
    /// JPEG 格式（有损压缩，质量范围 50-99）
    JPEG,
    /// PNG 格式（无损压缩，质量范围 0-9，推荐）
    PNG,
    /// TIFF 格式（无损，文件较大）
    TIFF,
}

impl ImageFormat {
    /// 获取对应的 SDK 常量值
    fn to_sdk_value(&self) -> c_uint {
        use hik_rs::mvs_sdk::{MV_IMAGE_BMP, MV_IMAGE_JPEG, MV_IMAGE_PNG, MV_IMAGE_TIF};
        match self {
            ImageFormat::BMP => MV_IMAGE_BMP as c_uint,
            ImageFormat::JPEG => MV_IMAGE_JPEG as c_uint,
            ImageFormat::PNG => MV_IMAGE_PNG as c_uint,
            ImageFormat::TIFF => MV_IMAGE_TIF as c_uint,
        }
    }

    /// 获取文件扩展名
    fn extension(&self) -> &'static str {
        match self {
            ImageFormat::BMP => "bmp",
            ImageFormat::JPEG => "jpg",
            ImageFormat::PNG => "png",
            ImageFormat::TIFF => "tif",
        }
    }

    /// 验证质量参数是否合法
    fn validate_quality(&self, quality: u32) -> Result<u32, String> {
        match self {
            ImageFormat::BMP | ImageFormat::TIFF => Ok(0), // BMP/TIFF 不需要质量参数
            ImageFormat::JPEG => {
                if (50..=99).contains(&quality) {
                    Ok(quality)
                } else {
                    Err(format!("JPEG 质量必须在 50-99 之间，当前值: {}", quality))
                }
            }
            ImageFormat::PNG => {
                if quality <= 9 {
                    Ok(quality)
                } else {
                    Err(format!("PNG 质量必须在 0-9 之间，当前值: {}", quality))
                }
            }
        }
    }
}

impl Default for ImageFormat {
    fn default() -> Self {
        ImageFormat::PNG
    }
}

/// 图像保存配置
#[derive(Debug, Clone, Copy)]
pub struct ImageConfig {
    /// 图像格式
    pub format: ImageFormat,
    /// 图像质量（JPEG: 50-99, PNG: 0-9, BMP/TIFF: 忽略）
    pub quality: u32,
}

impl ImageConfig {
    /// 创建新的图像配置
    pub fn new(format: ImageFormat, quality: u32) -> Result<Self, String> {
        let validated_quality = format.validate_quality(quality)?;
        Ok(ImageConfig {
            format,
            quality: validated_quality,
        })
    }
}

impl Default for ImageConfig {
    fn default() -> Self {
        ImageConfig {
            format: ImageFormat::PNG,
            quality: 5, // PNG 默认质量 5（中等压缩）
        }
    }
}

/// 相机参数配置
#[derive(Debug, Clone, Copy)]
#[cfg_attr(feature = "extension-module", pyo3::pyclass)]
pub struct CameraConfig {
    /// 曝光时间（微秒），None 表示不设置
    pub exposure_time: Option<f32>,
    /// 增益（dB），None 表示不设置
    pub gain: Option<f32>,
    /// 自动曝光模式，None 表示不设置
    pub exposure_auto: Option<bool>,
    /// 自动增益模式，None 表示不设置
    pub gain_auto: Option<bool>,
}

impl CameraConfig {
    /// 创建默认配置（所有参数都不设置）
    pub fn new() -> Self {
        Self {
            exposure_time: None,
            gain: None,
            exposure_auto: None,
            gain_auto: None,
        }
    }
}

impl Default for CameraConfig {
    fn default() -> Self {
        Self::new()
    }
}


/// 单个相机实例（Python 可访问）
#[cfg_attr(feature = "extension-module", pyo3::pyclass)]
pub struct Camera {
    sdk: HcMvsCoreSdk,
    pub index: usize,
    #[allow(dead_code)]
    info: String,
    /// 图像保存配置
    pub image_config: ImageConfig,
    /// 相机是否已打开
    is_open: bool,
    /// 输出目录
    output_dir: PathBuf,
    /// 拍摄计数器
    capture_count: usize,
}

impl Camera {
    /// 创建并打开相机（内部使用）
    pub fn new(
        index: usize,
        dev_info: &MvCcDeviceInfo,
        lib: &Lib,
        image_config: ImageConfig,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let mut sdk = HcMvsCoreSdk::default();
        sdk.set_lib(Lib::new(lib.get_path()));

        unsafe {
            // 创建句柄
            match sdk.create_handle(dev_info) {
                CResult::Ok(code) => {
                    if code != 0 {
                        return Err(format!("相机 {} 创建句柄失败，错误码: {}", index, code).into());
                    }
                }
                CResult::Err(e) => {
                    return Err(format!("相机 {} 创建句柄失败: {}", index, e).into());
                }
            }

            // 打开设备
            match sdk.open_device(MvAccessMode::Exclusive, 0) {
                CResult::Ok(code) => {
                    if code != 0 {
                        return Err(format!("相机 {} 打开设备失败，错误码: {}", index, code).into());
                    }
                }
                CResult::Err(e) => {
                    return Err(format!("相机 {} 打开设备失败: {}", index, e).into());
                }
            }

            // 开始采集
            match sdk.start_grabbing() {
                CResult::Ok(code) => {
                    if code != 0 {
                        return Err(format!("相机 {} 开始采集失败，错误码: {}", index, code).into());
                    }
                }
                CResult::Err(e) => {
                    return Err(format!("相机 {} 开始采集失败: {}", index, e).into());
                }
            }
        }

        let info = format!("Camera_{}", index);
        println!("  ✓ 相机 {} 初始化成功", index);

        Ok(Camera {
            sdk,
            index,
            info,
            image_config,
            is_open: true,
            output_dir: PathBuf::from("."),
            capture_count: 0,
        })
    }

    /// 创建未初始化的相机实例（Python 使用）
    #[cfg(feature = "extension-module")]
    fn new_uninitialized(
        camera_ip: Option<String>,
        pc_ip: Option<String>,
        output_dir: String,
        format: String,
        quality: u32,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        // 解析图像格式
        let image_format = match format.to_uppercase().as_str() {
            "PNG" => ImageFormat::PNG,
            "JPEG" | "JPG" => ImageFormat::JPEG,
            "BMP" => ImageFormat::BMP,
            "TIFF" | "TIF" => ImageFormat::TIFF,
            _ => {
                return Err(format!(
                    "不支持的图像格式: {}。支持的格式: PNG, JPEG, BMP, TIFF",
                    format
                )
                .into());
            }
        };

        let image_config = ImageConfig::new(image_format, quality)?;

        Ok(Camera {
            sdk: HcMvsCoreSdk::default(),
            index: 0,
            info: String::new(),
            image_config,
            is_open: false,
            output_dir: PathBuf::from(output_dir),
            capture_count: 0,
        })
    }

    /// 设置输出目录
    pub fn set_output_dir(&mut self, dir: PathBuf) {
        self.output_dir = dir;
    }

    /// 采集并保存一张图片（使用内部计数器）
    pub fn capture_quick(&mut self) -> Result<String, Box<dyn std::error::Error>> {
        if !self.is_open {
            return Err("相机未打开".into());
        }

        self.capture_count += 1;
        let image_index = self.capture_count;

        unsafe {
            let mut frame: MvFrameOut = mem::zeroed();

            // 获取图像
            match self.sdk.get_image_buffer(&mut frame as *mut _, 1000) {
                CResult::Ok(code) => {
                    if code != 0 {
                        return Err(
                            format!("相机 {} 获取图像失败，错误码: {}", self.index, code).into(),
                        );
                    }
                }
                CResult::Err(e) => {
                    return Err(format!("相机 {} 获取图像失败: {}", self.index, e).into());
                }
            }

            let width = frame.stFrameInfo.nWidth;
            let height = frame.stFrameInfo.nHeight;
            let pixel_type = frame.stFrameInfo.enPixelType;
            let data_len = frame.stFrameInfo.nFrameLen;

            // 构造保存路径（使用配置的图像格式）
            let extension = self.image_config.format.extension();
            let image_path = self.output_dir.join(format!("{}_{}.{}", self.index + 1, image_index, extension));
            let path_str = image_path.to_str().ok_or("路径转换失败")?;
            let path_cstring = CString::new(path_str)?;

            // 将 CString 转换为 [c_char; 256] 数组
            let mut path_array: [c_char; 256] = [0; 256];
            let path_bytes = path_cstring.as_bytes_with_nul();
            let copy_len = path_bytes.len().min(256);
            for i in 0..copy_len {
                path_array[i] = path_bytes[i] as c_char;
            }

            // 构造保存参数（使用配置的格式和质量）
            let mut save_param = MvSaveImgToFileParam {
                enPixelType: pixel_type,
                pData: frame.pBufAddr as *mut c_uchar,
                nDataLen: data_len as c_uint,
                nWidth: width as c_ushort,
                nHeight: height as c_ushort,
                enImageType: self.image_config.format.to_sdk_value(),
                nQuality: self.image_config.quality as c_uint,
                pImagePath: path_array,
                iMethodValue: 1, // 插值方法：1-双线性
                nReserved: [0; 8],
            };

            // 调用 SDK 保存图像
            match self.sdk.save_image_to_file(&mut save_param as *mut _) {
                CResult::Ok(code) => {
                    if code != 0 {
                        // 释放图像缓存
                        self.sdk.free_image_buffer(&mut frame as *mut _);
                        return Err(
                            format!("相机 {} 保存图像失败，错误码: {}", self.index, code).into(),
                        );
                    }
                }
                CResult::Err(e) => {
                    // 释放图像缓存
                    self.sdk.free_image_buffer(&mut frame as *mut _);
                    return Err(format!("相机 {} 保存图像失败: {}", self.index, e).into());
                }
            }

            // 释放图像缓存
            self.sdk.free_image_buffer(&mut frame as *mut _);

            Ok(image_path.to_string_lossy().to_string())
        }
    }

    /// 采集并保存一张图片
    pub fn capture_image(
        &self,
        image_index: usize,
        output_dir: &PathBuf,
    ) -> Result<(), Box<dyn std::error::Error>> {
        unsafe {
            let mut frame: MvFrameOut = mem::zeroed();

            // 获取图像
            match self.sdk.get_image_buffer(&mut frame as *mut _, 1000) {
                CResult::Ok(code) => {
                    if code != 0 {
                        return Err(
                            format!("相机 {} 获取图像失败，错误码: {}", self.index, code).into(),
                        );
                    }
                }
                CResult::Err(e) => {
                    return Err(format!("相机 {} 获取图像失败: {}", self.index, e).into());
                }
            }

            let width = frame.stFrameInfo.nWidth;
            let height = frame.stFrameInfo.nHeight;
            let pixel_type = frame.stFrameInfo.enPixelType;
            let data_len = frame.stFrameInfo.nFrameLen;

            println!(
                "    相机 {} - 图像尺寸: {}x{}, 像素格式: {}",
                self.index, width, height, pixel_type
            );

            // 构造保存路径（使用配置的图像格式）
            let extension = self.image_config.format.extension();
            let image_path = output_dir.join(format!("{}_{}.{}", self.index + 1, image_index, extension));
            let path_str = image_path.to_str().ok_or("路径转换失败")?;
            let path_cstring = CString::new(path_str)?;

            // 将 CString 转换为 [c_char; 256] 数组
            let mut path_array: [c_char; 256] = [0; 256];
            let path_bytes = path_cstring.as_bytes_with_nul();
            let copy_len = path_bytes.len().min(256);
            for i in 0..copy_len {
                path_array[i] = path_bytes[i] as c_char;
            }

            // 构造保存参数（使用配置的格式和质量）
            let mut save_param = MvSaveImgToFileParam {
                enPixelType: pixel_type,
                pData: frame.pBufAddr as *mut c_uchar,
                nDataLen: data_len as c_uint,
                nWidth: width as c_ushort,
                nHeight: height as c_ushort,
                enImageType: self.image_config.format.to_sdk_value(),
                nQuality: self.image_config.quality as c_uint,
                pImagePath: path_array,
                iMethodValue: 1, // 插值方法：1-双线性
                nReserved: [0; 8],
            };

            // 调用 SDK 保存图像
            match self.sdk.save_image_to_file(&mut save_param as *mut _) {
                CResult::Ok(code) => {
                    if code != 0 {
                        // 释放图像缓存
                        self.sdk.free_image_buffer(&mut frame as *mut _);
                        return Err(
                            format!("相机 {} 保存图像失败，错误码: {}", self.index, code).into(),
                        );
                    }
                }
                CResult::Err(e) => {
                    // 释放图像缓存
                    self.sdk.free_image_buffer(&mut frame as *mut _);
                    return Err(format!("相机 {} 保存图像失败: {}", self.index, e).into());
                }
            }

            // 释放图像缓存
            self.sdk.free_image_buffer(&mut frame as *mut _);

            println!(
                "    相机 {} - ✓ 已保存: {}",
                self.index,
                image_path.display()
            );
        }

        Ok(())
    }

    /// 应用相机参数配置
    pub fn configure(&self, config: &CameraConfig) -> Result<(), Box<dyn std::error::Error>> {
        if !self.is_open {
            return Err("相机未打开".into());
        }

        unsafe {
            // 设置自动曝光模式
            if let Some(auto) = config.exposure_auto {
                let key = CString::new("ExposureAuto")?;
                let value = if auto { 2 } else { 0 }; // 0=OFF, 2=CONTINUOUS
                match self.sdk.set_enum_value(key.as_ptr(), value) {
                    CResult::Ok(code) => {
                        if code != 0 {
                            return Err(format!("设置自动曝光模式失败，错误码: {}", code).into());
                        }
                    }
                    CResult::Err(e) => {
                        return Err(format!("设置自动曝光模式失败: {}", e).into());
                    }
                }
            }

            // 设置曝光时间（手动模式）
            if let Some(exposure) = config.exposure_time {
                // 先关闭自动曝光
                let key_auto = CString::new("ExposureAuto")?;
                match self.sdk.set_enum_value(key_auto.as_ptr(), 0) {
                    CResult::Ok(code) => {
                        if code != 0 {
                            return Err(format!("关闭自动曝光失败，错误码: {}", code).into());
                        }
                    }
                    CResult::Err(e) => {
                        return Err(format!("关闭自动曝光失败: {}", e).into());
                    }
                }

                // 设置曝光时间
                let key = CString::new("ExposureTime")?;
                match self.sdk.set_float_value(key.as_ptr(), exposure) {
                    CResult::Ok(code) => {
                        if code != 0 {
                            return Err(format!("设置曝光时间失败，错误码: {}", code).into());
                        }
                    }
                    CResult::Err(e) => {
                        return Err(format!("设置曝光时间失败: {}", e).into());
                    }
                }
            }

            // 设置自动增益模式
            if let Some(auto) = config.gain_auto {
                let key = CString::new("GainAuto")?;
                let value = if auto { 2 } else { 0 }; // 0=OFF, 2=CONTINUOUS
                match self.sdk.set_enum_value(key.as_ptr(), value) {
                    CResult::Ok(code) => {
                        if code != 0 {
                            return Err(format!("设置自动增益模式失败，错误码: {}", code).into());
                        }
                    }
                    CResult::Err(e) => {
                        return Err(format!("设置自动增益模式失败: {}", e).into());
                    }
                }
            }

            // 设置增益值（手动模式）
            if let Some(gain) = config.gain {
                // 先关闭自动增益
                let key_auto = CString::new("GainAuto")?;
                match self.sdk.set_enum_value(key_auto.as_ptr(), 0) {
                    CResult::Ok(code) => {
                        if code != 0 {
                            return Err(format!("关闭自动增益失败，错误码: {}", code).into());
                        }
                    }
                    CResult::Err(e) => {
                        return Err(format!("关闭自动增益失败: {}", e).into());
                    }
                }

                // 设置增益值
                let key = CString::new("Gain")?;
                match self.sdk.set_float_value(key.as_ptr(), gain) {
                    CResult::Ok(code) => {
                        if code != 0 {
                            return Err(format!("设置增益值失败，错误码: {}", code).into());
                        }
                    }
                    CResult::Err(e) => {
                        return Err(format!("设置增益值失败: {}", e).into());
                    }
                }
            }
        }

        Ok(())
    }

    /// 停止采集并关闭相机
    pub fn close(&self) -> Result<(), Box<dyn std::error::Error>> {
        unsafe {
            // 停止采集
            let _ = self.sdk.stop_grabbing();

            // 关闭设备
            match self.sdk.close_device() {
                CResult::Ok(code) => {
                    if code != 0 {
                        return Err(
                            format!("相机 {} 关闭设备失败，错误码: {}", self.index, code).into(),
                        );
                    }
                }
                CResult::Err(e) => {
                    return Err(format!("相机 {} 关闭设备失败: {}", self.index, e).into());
                }
            }

            // 销毁句柄
            let _ = self.sdk.destroy_handle();
        }

        Ok(())
    }
}

impl Drop for Camera {
    fn drop(&mut self) {
        if self.is_open {
            unsafe {
                let _ = self.sdk.stop_grabbing();
                let _ = self.sdk.close_device();
                let _ = self.sdk.destroy_handle();
                let _ = self.sdk.free();
            }
        }
    }
}

/// Python 方法 - CameraConfig
#[cfg(feature = "extension-module")]
#[pyo3::pymethods]
impl CameraConfig {
    /// 创建相机配置实例（Python 构造函数）
    #[new]
    fn py_new() -> Self {
        Self::new()
    }

    /// 获取曝光时间
    #[getter]
    fn exposure_time(&self) -> Option<f32> {
        self.exposure_time
    }

    /// 设置曝光时间（微秒）
    #[setter]
    fn set_exposure_time(&mut self, value: Option<f32>) {
        self.exposure_time = value;
    }

    /// 获取增益值
    #[getter]
    fn gain(&self) -> Option<f32> {
        self.gain
    }

    /// 设置增益值（dB）
    #[setter]
    fn set_gain(&mut self, value: Option<f32>) {
        self.gain = value;
    }

    /// 获取自动曝光模式
    #[getter]
    fn exposure_auto(&self) -> Option<bool> {
        self.exposure_auto
    }

    /// 设置自动曝光模式
    #[setter]
    fn set_exposure_auto(&mut self, value: Option<bool>) {
        self.exposure_auto = value;
    }

    /// 获取自动增益模式
    #[getter]
    fn gain_auto(&self) -> Option<bool> {
        self.gain_auto
    }

    /// 设置自动增益模式
    #[setter]
    fn set_gain_auto(&mut self, value: Option<bool>) {
        self.gain_auto = value;
    }
}

/// Python 方法 - Camera
#[cfg(feature = "extension-module")]
#[pyo3::pymethods]
impl Camera {
    /// 创建相机实例（Python 构造函数）
    ///
    /// 参数:
    ///     output_dir: 输出文件夹路径
    ///     camera_ip: 可选，相机的 IP 地址
    ///     pc_ip: 可选，PC 网卡的 IP 地址
    ///     format: 图像格式 (默认 "PNG")
    ///     quality: 图像质量 (默认 5)
    #[new]
    #[pyo3(signature = (output_dir, camera_ip=None, pc_ip=None, format="PNG".to_string(), quality=5))]
    fn py_new(
        output_dir: String,
        camera_ip: Option<String>,
        pc_ip: Option<String>,
        format: String,
        quality: u32,
    ) -> PyResult<Self> {
        // 解析图像格式
        let image_format = match format.to_uppercase().as_str() {
            "PNG" => ImageFormat::PNG,
            "JPEG" | "JPG" => ImageFormat::JPEG,
            "BMP" => ImageFormat::BMP,
            "TIFF" | "TIF" => ImageFormat::TIFF,
            _ => {
                return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    format!("不支持的图像格式: {}。支持的格式: PNG, JPEG, BMP, TIFF", format)
                ));
            }
        };

        let image_config = ImageConfig::new(image_format, quality).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(e)
        })?;

        // 创建输出目录
        let out_dir = PathBuf::from(&output_dir);
        if !out_dir.exists() {
            fs::create_dir_all(&out_dir).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("创建输出文件夹失败: {}", e))
            })?;
        }

        Ok(Camera {
            sdk: HcMvsCoreSdk::default(),
            index: 0,
            info: format!("Camera_IP_{}", camera_ip.as_deref().unwrap_or("enum")),
            image_config,
            is_open: false,
            output_dir: out_dir,
            capture_count: 0,
        })
    }

    /// 打开并初始化相机
    ///
    /// 参数:
    ///     camera_ip: 可选，相机的 IP 地址
    ///     pc_ip: 可选，PC 网卡的 IP 地址
    #[pyo3(signature = (camera_ip=None, pc_ip=None))]
    fn open(&mut self, camera_ip: Option<String>, pc_ip: Option<String>) -> PyResult<()> {
        use crate::config::EnvConfig;

        if self.is_open {
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "相机已经打开"
            ));
        }

        println!("=== 初始化相机 ===\n");

        // 1. 加载环境配置
        println!("步骤 1: 加载环境配置...");
        let env_config = EnvConfig::load().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("加载环境配置失败: {}", e))
        })?;
        env_config.apply().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("应用环境配置失败: {}", e))
        })?;

        // 2. 初始化 SDK
        println!("\n步骤 2: 初始化 MVS SDK...");
        let lib = init_sdk().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("初始化 SDK 失败: {}", e))
        })?;

        // 3. 连接相机
        match (camera_ip, pc_ip) {
            (Some(cam_ip), Some(pc_ip_addr)) => {
                // IP 直连模式
                println!("\n步骤 3: 通过 IP 连接相机...");
                let mut camera = connect_by_ip(&cam_ip, &pc_ip_addr, &lib, self.image_config).map_err(|e| {
                    PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("连接相机失败: {}", e))
                })?;

                // 将初始化好的相机数据移动到 self
                unsafe {
                    self.sdk = std::ptr::read(&camera.sdk);
                    self.index = camera.index;
                    self.info = std::ptr::read(&camera.info);
                    self.is_open = true;

                    // 标记原相机为已关闭，防止 Drop 时关闭设备
                    std::ptr::write(&mut camera.is_open, false);
                }

                println!("✓ 相机连接成功\n");
            }
            (None, None) => {
                // 枚举模式
                println!("\n步骤 3: 枚举设备...");
                let device_list = enumerate_devices(&lib).map_err(|e| {
                    PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("枚举设备失败: {}", e))
                })?;

                let device_count = device_list.nDeviceNum;
                if device_count == 0 {
                    return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                        "未找到任何相机"
                    ));
                }

                println!("✓ 找到 {} 个相机", device_count);

                // 初始化第一个相机
                println!("\n步骤 4: 初始化相机 0...");
                unsafe {
                    if let Some(dev_info) = device_list.pDeviceInfo[0].as_ref() {
                        let mut camera = Camera::new(0, dev_info, &lib, self.image_config).map_err(|e| {
                            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("初始化相机失败: {}", e))
                        })?;

                        // 将初始化好的相机数据移动到 self
                        self.sdk = std::ptr::read(&camera.sdk);
                        self.index = camera.index;
                        self.info = std::ptr::read(&camera.info);
                        self.is_open = true;

                        // 标记原相机为已关闭，防止 Drop 时关闭设备
                        std::ptr::write(&mut camera.is_open, false);

                        println!("✓ 相机初始化成功\n");
                    } else {
                        return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                            "获取设备信息失败"
                        ));
                    }
                }
            }
            _ => {
                return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    "使用 IP 直连模式时，必须同时提供 camera_ip 和 pc_ip 参数"
                ));
            }
        }

        Ok(())
    }

    /// 快速拍照（只需 100-200ms）
    ///
    /// 返回: 图片保存路径
    fn capture(&mut self) -> PyResult<String> {
        self.capture_quick().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("拍照失败: {}", e))
        })
    }

    /// 应用相机参数配置
    ///
    /// 参数:
    ///     config: CameraConfig 实例
    #[pyo3(name = "configure")]
    fn py_configure(&self, config: &CameraConfig) -> PyResult<()> {
        self.configure(config).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("配置相机参数失败: {}", e))
        })
    }

    /// 关闭相机
    fn close_camera(&mut self) -> PyResult<()> {
        if !self.is_open {
            return Ok(());
        }

        println!("关闭相机...");
        self.close().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("关闭相机失败: {}", e))
        })?;

        self.is_open = false;
        println!("✓ 相机已关闭");
        Ok(())
    }

    /// 上下文管理器 __enter__
    fn __enter__(slf: pyo3::Py<Self>) -> pyo3::Py<Self> {
        slf
    }

    /// 上下文管理器 __exit__
    fn __exit__(
        &mut self,
        _exc_type: Option<&PyAny>,
        _exc_value: Option<&PyAny>,
        _traceback: Option<&PyAny>,
    ) -> PyResult<bool> {
        self.close_camera()?;
        Ok(false)
    }
}

/// 初始化 SDK
pub fn init_sdk() -> Result<Lib, Box<dyn std::error::Error>> {
    let lib_path = env::var("HCMVS_LIB")?;

    // 根据操作系统选择正确的库文件
    let lib_filename = if cfg!(target_os = "windows") {
        "MvCameraControl.dll"
    } else if cfg!(target_os = "linux") {
        "libMvCameraControl.so"
    } else if cfg!(target_os = "macos") {
        "libMvCameraControl.dylib"
    } else {
        return Err("不支持的操作系统".into());
    };

    let dll_path = PathBuf::from(&lib_path).join(lib_filename);

    println!("  加载库文件: {}", dll_path.display());

    let lib = Lib::new(dll_path);
    println!("  ✓ MVS SDK 初始化成功");

    Ok(lib)
}

/// 枚举设备
pub fn enumerate_devices(lib: &Lib) -> Result<MvCcDeviceInfoList, Box<dyn std::error::Error>> {
    let mut sdk = HcMvsCoreSdk::default();
    sdk.set_lib(Lib::new(lib.get_path()));

    let mut device_list = MvCcDeviceInfoList::default();

    unsafe {
        let ret = sdk.enumrate_devices(
            MvEnumDeviceLayerType::GigeDevice, // GigE 网口设备
            &mut device_list as *mut _,
        );

        match ret {
            CResult::Ok(code) => {
                if code == 0 {
                    Ok(device_list)
                } else {
                    Err(format!("枚举设备失败，错误码: {}", code).into())
                }
            }
            CResult::Err(e) => Err(format!("枚举设备失败: {}", e).into()),
        }
    }
}

/// 通过指定 IP 地址创建相机（无需枚举）
///
/// # 参数
/// - `camera_ip`: 相机的 IP 地址，例如 "192.168.1.64"
/// - `pc_ip`: PC 网卡的 IP 地址，例如 "192.168.1.100"
/// - `lib`: SDK 库引用
/// - `image_config`: 图像保存配置

pub fn connect_by_ip(
    camera_ip: &str,
    pc_ip: &str,
    lib: &Lib,
    image_config: ImageConfig,
) -> Result<Camera, Box<dyn std::error::Error>> {
    println!("  尝试连接相机 IP: {}", camera_ip);
    println!("  PC 网卡 IP: {}", pc_ip);

    // 使用 hik-rs 提供的函数创建设备信息
    let dev_info = create_gige_device_info(camera_ip, pc_ip)
        .map_err(|e| format!("创建设备信息失败: {}", e))?;

    // 创建相机实例
    Camera::new(0, &dev_info, lib, image_config)
}

/// Python 函数：采集相机图像（支持枚举模式和IP直连模式）
///
/// 参数:
///     output_dir: 输出文件夹路径 (字符串)
///     format: 图像格式 (字符串: "PNG", "JPEG", "BMP", "TIFF", 默认 "PNG")
///     quality: 图像质量 (整数: JPEG 50-99, PNG 0-9, 默认 5)
///     camera_ip: 可选，相机的 IP 地址 (字符串，例如 "192.168.1.64")
///     pc_ip: 可选，PC 网卡的 IP 地址 (字符串，例如 "192.168.1.100")
///
/// 模式说明:
///     - 如果 camera_ip 和 pc_ip 都提供：使用 IP 直连模式（单相机）
///     - 如果不提供：使用枚举模式（多相机自动发现）
///
/// 返回:
///     字典，包含:
///         - success: 是否成功 (bool)
///         - cameras_found: 找到的相机数量 (int，仅枚举模式)
///         - cameras_initialized: 成功初始化的相机数量 (int)
///         - images_captured: 成功采集的图片总数 (int)
///         - message: 结果消息 (str)
#[cfg(feature = "extension-module")]
#[pyfunction]
#[pyo3(signature = (output_dir, format="PNG".to_string(), quality=5, camera_ip=None, pc_ip=None))]
fn capture_images(
    output_dir: String,
    format: String,
    quality: u32,
    camera_ip: Option<String>,
    pc_ip: Option<String>,
) -> PyResult<PyObject> {
    Python::with_gil(|py| {
        // 解析图像格式
        let image_format = match format.to_uppercase().as_str() {
            "PNG" => ImageFormat::PNG,
            "JPEG" | "JPG" => ImageFormat::JPEG,
            "BMP" => ImageFormat::BMP,
            "TIFF" | "TIF" => ImageFormat::TIFF,
            _ => {
                return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    format!("不支持的图像格式: {}。支持的格式: PNG, JPEG, BMP, TIFF", format)
                ));
            }
        };

        // 创建图像配置
        let image_config = ImageConfig::new(image_format, quality).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(e)
        })?;

        println!(
            "图像格式: {:?}, 质量: {}",
            image_config.format, image_config.quality
        );

        // 创建输出文件夹
        let images_dir = PathBuf::from(&output_dir);
        if !images_dir.exists() {
            fs::create_dir_all(&images_dir).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("创建输出文件夹失败: {}", e))
            })?;
        }

        // 1. 加载环境配置
        println!("步骤 1: 加载环境配置...");
        let env_config = EnvConfig::load().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("加载环境配置失败: {}", e))
        })?;
        env_config.apply().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("应用环境配置失败: {}", e))
        })?;

        // 2. 初始化 SDK
        println!("\n步骤 2: 初始化 MVS SDK...");
        let lib = init_sdk().map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("初始化 SDK 失败: {}", e))
        })?;

        // 判断使用哪种模式
        match (camera_ip, pc_ip) {
            // IP 直连模式
            (Some(cam_ip), Some(pc_ip_addr)) => {
                println!("=== 海康威视相机 IP 直连采集 ===\n");

                // 3. 通过 IP 连接相机
                println!("\n步骤 3: 通过 IP 连接相机...");
                let camera = connect_by_ip(&cam_ip, &pc_ip_addr, &lib, image_config).map_err(|e| {
                    PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("连接相机失败: {}", e))
                })?;

                println!("✓ 相机连接成功");

                // 4. 采集图像
                println!("\n步骤 4: 开始采集图像...");

                match camera.capture_image(1, &images_dir) {
                    Ok(_) => {
                        println!("    ✓ 图像采集成功");
                    }
                    Err(e) => {
                        eprintln!("    ✗ 图像采集失败: {}", e);
                        // 关闭相机
                        let _ = camera.close();
                        let result = pyo3::types::PyDict::new_bound(py);
                        result.set_item("success", false)?;
                        result.set_item("cameras_initialized", 1)?;
                        result.set_item("images_captured", 0)?;
                        result.set_item("message", format!("图像采集失败: {}", e))?;
                        return Ok(result.into());
                    }
                }

                // 5. 关闭相机
                println!("\n步骤 5: 关闭相机...");
                if let Err(e) = camera.close() {
                    eprintln!("  ✗ {}", e);
                } else {
                    println!("  ✓ 相机已关闭");
                }

                println!("\n=== 采集完成！ ===");
                println!("图片已保存到 {}", images_dir.display());

                // 返回结果
                let result = pyo3::types::PyDict::new_bound(py);
                result.set_item("success", true)?;
                result.set_item("cameras_initialized", 1)?;
                result.set_item("images_captured", 1)?;
                result.set_item("message", "成功采集 1 张图片")?;
                Ok(result.into())
            }

            // 枚举模式
            (None, None) => {
                println!("=== 海康威视多相机图像采集 ===\n");

                // 3. 枚举设备
                println!("\n步骤 3: 枚举设备...");
                let device_list = enumerate_devices(&lib).map_err(|e| {
                    PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("枚举设备失败: {}", e))
                })?;
                let device_count = device_list.nDeviceNum;

                if device_count == 0 {
                    println!("✗ 未找到任何相机");
                    let result = pyo3::types::PyDict::new_bound(py);
                    result.set_item("success", false)?;
                    result.set_item("cameras_found", 0)?;
                    result.set_item("cameras_initialized", 0)?;
                    result.set_item("images_captured", 0)?;
                    result.set_item("message", "未找到任何相机")?;
                    return Ok(result.into());
                }

                println!("✓ 找到 {} 个相机", device_count);

                // 4. 初始化所有相机
                println!("\n步骤 4: 初始化所有相机...");
                let mut cameras = Vec::new();

                for i in 0..device_count as usize {
                    unsafe {
                        if let Some(dev_info) = device_list.pDeviceInfo[i].as_ref() {
                            match Camera::new(i, dev_info, &lib, image_config) {
                                Ok(camera) => cameras.push(camera),
                                Err(e) => eprintln!("  ✗ 相机 {} 初始化失败: {}", i, e),
                            }
                        }
                    }
                }

                if cameras.is_empty() {
                    println!("✗ 没有成功初始化的相机");
                    let result = pyo3::types::PyDict::new_bound(py);
                    result.set_item("success", false)?;
                    result.set_item("cameras_found", device_count)?;
                    result.set_item("cameras_initialized", 0)?;
                    result.set_item("images_captured", 0)?;
                    result.set_item("message", "没有成功初始化的相机")?;
                    return Ok(result.into());
                }

                println!("✓ 成功初始化 {} 个相机", cameras.len());

                // 5. 同步采集图像
                println!("\n步骤 5: 开始采集图像...");
                let mut images_captured = 0;

                // 所有相机各拍摄一张照片
                for camera in &cameras {
                    match camera.capture_image(1, &images_dir) {
                        Ok(_) => {
                            images_captured += 1;
                            println!("    ✓ 相机 {} 图像采集成功", camera.index);
                        }
                        Err(e) => eprintln!("    ✗ 相机 {} 采集失败: {}", camera.index, e),
                    }
                }

                // 6. 关闭所有相机
                println!("\n步骤 6: 关闭所有相机...");
                for camera in &cameras {
                    if let Err(e) = camera.close() {
                        eprintln!("  ✗ {}", e);
                    } else {
                        println!("  ✓ 相机 {} 已关闭", camera.index);
                    }
                }

                println!("\n=== 采集完成！ ===");
                println!("图片已保存到 {}", images_dir.display());
                println!("共 {} 个相机，每个相机采集 1 张图片", cameras.len());

                // 返回结果
                let result = pyo3::types::PyDict::new_bound(py);
                result.set_item("success", true)?;
                result.set_item("cameras_found", device_count)?;
                result.set_item("cameras_initialized", cameras.len())?;
                result.set_item("images_captured", images_captured)?;
                result.set_item("message", format!("成功采集 {} 张图片", images_captured))?;
                Ok(result.into())
            }

            // 参数不完整
            _ => {
                Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    "使用 IP 直连模式时，必须同时提供 camera_ip 和 pc_ip 参数"
                ))
            }
        }
    })
}

/// Python 模块定义
#[cfg(feature = "extension-module")]
#[pymodule]
fn chg_hik(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // 注册 CameraConfig 类
    m.add_class::<CameraConfig>()?;
    // 注册 Camera 类
    m.add_class::<Camera>()?;
    // 注册 capture_images 函数（兼容旧接口）
    m.add_function(wrap_pyfunction!(capture_images, m)?)?;
    Ok(())
}
