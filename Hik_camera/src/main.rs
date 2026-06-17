use chg_hik::{Camera, enumerate_devices, init_sdk, connect_by_ip, ImageConfig, ImageFormat};
use chg_hik::config::EnvConfig;
use std::fs;
use std::io::{self, Write};
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== 海康威视相机图像采集示例 ===\n");

    // 1. 选择图像格式和质量
    let image_config = select_image_config()?;
    println!("\n已选择图像格式: {:?}, 质量: {}", image_config.format, image_config.quality);

    // 2. 选择连接方式
    println!("\n请选择连接方式：");
    println!("1. 枚举设备（自动搜索所有相机）");
    println!("2. 指定 IP 地址直连（跳过枚举）");
    print!("\n请输入选项 (1 或 2): ");
    io::stdout().flush()?;

    let mut choice = String::new();
    io::stdin().read_line(&mut choice)?;
    let choice = choice.trim();

    // 创建 images 文件夹
    let images_dir = PathBuf::from("images");
    if !images_dir.exists() {
        fs::create_dir(&images_dir)?;
    }

    // 3. 加载环境配置
    println!("\n步骤 1: 加载环境配置...");
    let env_config = EnvConfig::load()?;
    env_config.apply()?;

    // 4. 初始化 SDK
    println!("\n步骤 2: 初始化 MVS SDK...");
    let lib = init_sdk()?;

    match choice {
        "1" => run_enumerate_mode(&lib, &images_dir, image_config),
        "2" => run_direct_ip_mode(&lib, &images_dir, image_config),
        _ => {
            println!("无效的选项，使用默认枚举模式");
            run_enumerate_mode(&lib, &images_dir, image_config)
        }
    }
}

/// 让用户选择图像格式和质量
fn select_image_config() -> Result<ImageConfig, Box<dyn std::error::Error>> {
    println!("请选择图像格式：");
    println!("1. PNG  - 无损压缩（推荐，文件较小）");
    println!("2. JPEG - 有损压缩（适合照片）");
    println!("3. BMP  - 无压缩（文件最大）");
    println!("4. TIFF - 无损格式（文件较大）");
    print!("\n请输入选项 (1-4，默认 1): ");
    io::stdout().flush()?;

    let mut format_choice = String::new();
    io::stdin().read_line(&mut format_choice)?;
    let format_choice = format_choice.trim();

    let format = match format_choice {
        "2" => ImageFormat::JPEG,
        "3" => ImageFormat::BMP,
        "4" => ImageFormat::TIFF,
        _ => ImageFormat::PNG, // 默认 PNG
    };

    // 根据格式询问质量
    let quality = match format {
        ImageFormat::PNG => {
            print!("请输入 PNG 压缩质量 (0-9，0=最快 9=最小文件，默认 5): ");
            io::stdout().flush()?;
            let mut quality_str = String::new();
            io::stdin().read_line(&mut quality_str)?;
            quality_str.trim().parse().unwrap_or(5)
        }
        ImageFormat::JPEG => {
            print!("请输入 JPEG 质量 (50-99，值越高质量越好，默认 90): ");
            io::stdout().flush()?;
            let mut quality_str = String::new();
            io::stdin().read_line(&mut quality_str)?;
            quality_str.trim().parse().unwrap_or(90)
        }
        ImageFormat::BMP | ImageFormat::TIFF => 0, // 不需要质量参数
    };

    ImageConfig::new(format, quality).map_err(|e| e.into())
}

/// 枚举模式：自动搜索所有相机
fn run_enumerate_mode(
    lib: &hik_rs::Lib,
    images_dir: &PathBuf,
    image_config: ImageConfig,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("\n=== 枚举模式 ===");

    // 3. 枚举设备
    println!("\n步骤 3: 枚举设备...");
    let device_list = enumerate_devices(&lib)?;
    let device_count = device_list.nDeviceNum;

    if device_count == 0 {
        println!("✗ 未找到任何相机");
        return Ok(());
    }

    println!("✓ 找到 {} 个相机", device_count);

    // 4. 初始化所有相机
    println!("\n步骤 4: 初始化所有相机...");
    let mut cameras: Vec<Camera> = Vec::new();

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
        return Ok(());
    }

    println!("✓ 成功初始化 {} 个相机", cameras.len());

    // 5. 同步采集图像
    println!("\n步骤 5: 开始采集图像...");
    let num_images = 5; // 每个相机采集 5 张图片

    for img_idx in 0..num_images {
        println!("\n  [第 {}/{} 轮采集]", img_idx + 1, num_images);

        // 所有相机同时采集
        for camera in &cameras {
            if let Err(e) = camera.capture_image(img_idx + 1, &images_dir) {
                eprintln!("    ✗ {}", e);
            }
        }

        // 采集间隔
        if img_idx < num_images - 1 {
            std::thread::sleep(std::time::Duration::from_millis(200));
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
    println!("图片已保存到 images 文件夹");
    println!(
        "共 {} 个相机，每个相机采集 {} 张图片",
        cameras.len(),
        num_images
    );

    Ok(())
}

/// IP 直连模式：指定相机 IP 和 PC IP
fn run_direct_ip_mode(
    lib: &hik_rs::Lib,
    images_dir: &PathBuf,
    image_config: ImageConfig,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("\n=== IP 直连模式 ===");

    // 获取相机 IP
    print!("\n请输入相机 IP 地址 (例如 192.168.1.64): ");
    io::stdout().flush()?;
    let mut camera_ip = String::new();
    io::stdin().read_line(&mut camera_ip)?;
    let camera_ip = camera_ip.trim();

    // 获取 PC 网卡 IP
    print!("请输入 PC 网卡 IP 地址 (例如 192.168.1.100): ");
    io::stdout().flush()?;
    let mut pc_ip = String::new();
    io::stdin().read_line(&mut pc_ip)?;
    let pc_ip = pc_ip.trim();

    // 3. 通过 IP 连接相机
    println!("\n步骤 3: 通过 IP 连接相机...");
    let camera = connect_by_ip(camera_ip, pc_ip, &lib, image_config)?;
    println!("✓ 相机连接成功");

    // 4. 采集图像
    println!("\n步骤 4: 开始采集图像...");
    let num_images = 5; // 采集 5 张图片

    for img_idx in 0..num_images {
        println!("\n  [第 {}/{} 轮采集]", img_idx + 1, num_images);

        if let Err(e) = camera.capture_image(img_idx + 1, &images_dir) {
            eprintln!("    ✗ {}", e);
        }

        // 采集间隔
        if img_idx < num_images - 1 {
            std::thread::sleep(std::time::Duration::from_millis(200));
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
    println!("图片已保存到 images 文件夹");
    println!("共采集 {} 张图片", num_images);

    Ok(())
}
