using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;

namespace RVC_CSharp
{

    public static class RVC_CSharp_Tool
    {
        /// <summary>
        /// 保存彩色点云
        /// </summary>
        /// <param name="pointMap">点云数据</param>
        /// <param name="image">图像数据</param>
        /// <param name="filename">文件名</param>
        /// <param name="unit_mm">保存单位，是否为毫米，否则为米</param>
        public static void SaveColorPointCloud(this PointMap pointMap, Image image, string filename = "./RvcColorPointMapAscii.ply", bool unit_mm = true)
        {
            pointMap.Save(filename, unit_mm ? PointMapUnit.Millimeter : PointMapUnit.Meter, true, image);
        }

        /// <summary>
        /// 保存PLY+ASCII格式的点云
        /// 由于ASCII保存的比较慢，不建议使用，建议使用二进制保存
        /// </summary>
        /// <param name="pointMap">点云数据</param>
        /// <param name="filePath">文件名</param>
        /// <param name="unit_mm">保存单位，是否为毫米，否则为米</param>
        [Obsolete]
        public static void SavePlyAscii(this PointMap pointMap, string filePath = "./RvcPointMapAscii.ply", bool unit_mm = true)
        {
            pointMap.Save(filePath, unit_mm ? PointMapUnit.Millimeter : PointMapUnit.Meter, false);
        }


        /// <summary>
        /// 保存PLY+Binary格式的点云【二进制】
        /// </summary>
        /// <param name="pointMap">点云数据</param>
        /// <param name="filePath">文件名</param>
        /// <param name="unit_mm">保存单位，是否为毫米，否则为米</param>
        public static void SavePlyBinary(this PointMap pointMap, string filePath = "./RvcPointMapBinary.ply",bool unit_mm = true)
        {
            pointMap.Save(filePath, unit_mm ? PointMapUnit.Millimeter : PointMapUnit.Meter, true);
        }


        public static void SavePlyBinary(double[] xs, double[] ys, double[] zs, string filePath, bool unit_mm = true)
        {
            int len = xs.Length;

            string save_address = filePath;// "./Data/save.ply";
            FileStream fs = new FileStream(save_address, FileMode.Create);

            BinaryWriter binaryWriter = new BinaryWriter(fs);
            string header = default;
            header += "ply\n";
            //header += unit_mm ? "unit = millimeter\n" : "unit = meter\n";
            header += "format binary_little_endian 1.0\n";
            header += "comment Created by Rvbust, Inc\n";
            header += $"element vertex {len}\n";
            header += "property float x\n";
            header += "property float y\n";
            header += "property float z\n";
            header += "end_header\n";
            byte[] bhelddata = new UTF8Encoding().GetBytes(header);
            binaryWriter.Write(bhelddata, 0, bhelddata.Length);

            for (int i = 0; i < len; i++)
            {
                byte[] datax = BitConverter.GetBytes((float)xs[i]);
                binaryWriter.Write(datax, 0, datax.Length);
                byte[] datay = BitConverter.GetBytes((float)ys[i]);
                binaryWriter.Write(datay, 0, datay.Length);
                byte[] dataz = BitConverter.GetBytes((float)zs[i]);
                binaryWriter.Write(dataz, 0, dataz.Length);
            }
            binaryWriter.Flush();
            binaryWriter.Close();
            fs.Close();
        }

        /// <summary>
        /// 点云裁剪
        /// 裁剪范围  xMin-xMax,yMin-yMax,zMin-zMax
        /// Truncate Point Cloud in xMin-xMax,yMin-yMax,zMin-zMax
        /// </summary>
        public static void Truncate(this PointMap pointMap, double xMin, double xMax,
            double yMin, double yMax, double zMin, double zMax,
            ref List<double> x, ref List<double> y, ref List<double> z, bool unit_mm = true)
        {
            pointMap.GetPointMapSeperated(out double[] xs, out double[] ys, out double[] zs, unit_mm ? 1000.0 : 1.0);
            PointCloudTruncate(xs, ys, zs, xMin, xMax, yMin, yMax, zMin, zMax, ref x, ref y, ref z);
        }

        /// <summary>
        /// 点云移除 null 值
        /// 移除之后，x,y,z序列的长度将由实际的有效点的数量决定，对应的值将不能和row和col对应
        /// There will always be some points with value null in the point cloud,and we can remove these points in this function.
        /// </summary>
        public static void RemoveNull(this PointMap pointMap,
            out List<double> x, out List<double> y, out List<double> z, bool unit_mm = true)
        {
            pointMap.GetPointMapSeperated(out double[] xs, out double[] ys, out double[] zs, unit_mm ? 1000.0 : 1.0);
            PointCloudRemoveNull(xs, ys, zs, out x, out y, out z);
        }

        /// <summary>
        /// 点云替换 null 值
        /// x,y,z的长度 = width * height
        /// There will always be some points with value null in the point cloud,and we can replace the values of these points with the specified values.
        /// </summary>
        public static void ReplaceNull(this PointMap pointMap,
            out double[] x, out double[] y, out double[] z,
            double rx = 0.0, double ry = 0.0, double rz = 0.0, bool unit_mm = true)
        {
            pointMap.GetPointMapSeperated(out x, out y, out z, unit_mm ? 1000.0 : 1.0);
            PointCloudReplaceNull(x, y, z, rx, ry, rz);
        }

        public static string Name(this CaptureMode mode)
        {
            switch (mode)
            {
                case CaptureMode.CaptureMode_Fast:
                    return "快速模式";
                case CaptureMode.CaptureMode_Normal:
                    return "标准模式";
                case CaptureMode.CaptureMode_Ultra:
                    return "高精度模式";
                case CaptureMode.CaptureMode_Robust:
                    return "抗干扰模式";
                case CaptureMode.CaptureMode_AntiInterReflection:
                    return "抗多次反射模式";
                case CaptureMode.CaptureMode_SwingLineScan:
                    return "摆动线扫模式";
                case CaptureMode.CaptureMode_FixedLineScan:
                    return "固定线扫模式";
                case CaptureMode.CaptureMode_LineArrayShift:
                    return "面阵线移模式";
                case CaptureMode.CaptureMode_All:
                    return "全模式";
                default:
                    throw new ArgumentOutOfRangeException(nameof(mode), mode, null);
            }
        }
        public static string Name(this ProjectorColor color)
        {
            switch (color)
            {
                case ProjectorColor.ProjectorColor_None:
                    return "无";
                case ProjectorColor.ProjectorColor_Red:
                    return "红色";
                case ProjectorColor.ProjectorColor_Green:
                    return "绿色";
                case ProjectorColor.ProjectorColor_Blue:
                    return "蓝色";
                case ProjectorColor.ProjectorColor_White:
                    return "白色";
                case ProjectorColor.ProjectorColor_ALL:
                    return "全色";
                default:
                    throw new ArgumentOutOfRangeException(nameof(color), color, null);
            }
        }
        public static string Name(this SmoothnessLevel smoothness)
        {
            switch (smoothness)
            {
                case SmoothnessLevel.SmoothnessLevel_Off:
                    return "关";
                case SmoothnessLevel.SmoothnessLevel_Weak:
                    return "弱";
                case SmoothnessLevel.SmoothnessLevel_Normal:
                    return "中";
                case SmoothnessLevel.SmoothnessLevel_Strong:
                    return "强";
                default:
                    throw new ArgumentOutOfRangeException(nameof(smoothness), smoothness, null);
            }
        }

        /// <summary>
        /// 打印参数信息
        /// </summary>
        /// <param name="options"></param>
        public static void Print(this DeviceInfo info)
        {
            Console.WriteLine($"打印设备参数---");

            Console.WriteLine($"设备名称--[name] = {info.name}");
            Console.WriteLine($"设备序列号--[sn] = {info.sn}");
            Console.WriteLine($"出厂日期--[factroydate] = {info.factroydate}");
            Console.WriteLine($"端口类型--[type] = {info.type}");
            Console.WriteLine($"端口号--[port] = {info.port}【只针对网络相机】");
            Console.WriteLine($"主板类型--[boardmodel] = {info.boardmodel}");
            Console.WriteLine($"支持的相机类型--[cameraid] = {info.cameraid}");
            Console.WriteLine($"是否支持单相机--[support_x1] = {info.support_x1}");
            Console.WriteLine($"是否支持双相机--[support_x2] = {info.support_x2}");
            Console.WriteLine($"支持的投影颜色--[support_color] = {info.support_color}");
            Console.WriteLine($"工作距离-近--[workingdist_near_mm] = {info.workingdist_near_mm}");
            Console.WriteLine($"工作距离-远--[workingdist_far_mm] = {info.workingdist_far_mm}");
            Console.WriteLine($"固件版本--[firmware_version] = {info.firmware_version}");
            Console.WriteLine($"支持的拍摄模式--[support_capture_mode] = {info.support_capture_mode}");
            Console.WriteLine($"是否支持防护盖控制--[support_protective_cover] = {info.support_protective_cover}");
            Console.WriteLine($"是否支持硬触发--[support_hardware_trigger] = {info.support_hardware_trigger}");
        }

        /// <summary>
        /// 打印参数信息
        /// </summary>
        /// <param name="options"></param>
        public static void Print(this X1.CaptureOptions options)
        {
                Console.WriteLine($"拍摄参数---");

                /**
                * P and I series supports the following modes:
                * CaptureMode_Normal
                * CaptureMode_Fast
                * CaptureMode_AntiInterReflection
                *
                * G series supports the following modes:
                * CaptureMode_Ultra
                * CaptureMode_AntiInterReflection
                *
                * Note:The CaptureMode_Robust has been deprecated. You can achieve the same effect by setting the scan_times
                * parameter.
                */
                Console.WriteLine($"拍摄模式--[capture_mode] = {options.capture_mode.Name()}");
                // Parameters related to 2D Capture
                Console.WriteLine($"2D 曝光时间--[exposure_time_2d] = {options.exposure_time_2d}");
                Console.WriteLine($"2D 增益--[gain_2d] = {options.gain_2d}");
                Console.WriteLine($"2D Gamma--[gamma_2d] = {options.gamma_2d}");
                Console.WriteLine($"2D 拍摄是否使用光机--[use_projector_capturing_2d_image] = {options.use_projector_capturing_2d_image}");

                // Parameters related to 3D Capture
                
                Console.WriteLine($"3D采集中拍摄2D图-[enable_2d_in_capture] = {options.enable_2d_in_capture}");
                Console.WriteLine($"3D 曝光时间--[exposure_time_3d] = {options.exposure_time_3d}");
                Console.WriteLine($"3D 增益--[gain_3d] = {options.gain_3d}");
                Console.WriteLine($"3D Gamma--[gamma_3d] = {options.gamma_3d}");
                Console.WriteLine($"光强对比度阈值--[light_contrast_threshold] = {options.light_contrast_threshold}");
                Console.WriteLine($"投影亮度--[projector_brightness] = {options.projector_brightness}");
                // Note:Only the G series support the 'scan_times' parameter.
                Console.WriteLine($"扫描次数[G系列相机]--[scan_times] = {options.scan_times}");

                Console.WriteLine($"HDR 次数--[hdr_exposure_times] = {options.hdr_exposure_times}");
                Console.WriteLine($"HDR 曝光(0,1,2)--[hdr_exposuretime_content] = {options.hdr_exposuretime_content[0]},{options.hdr_exposuretime_content[1]},{options.hdr_exposuretime_content[2]}");
                Console.WriteLine($"HDR 增益(0,1,2)--[hdr_gain_3d] = {options.hdr_gain_3d[0]},{options.hdr_gain_3d[1]},{options.hdr_gain_3d[2]}");
                // Note:Only the G series support the 'hdr_scan_times' parameter.
                Console.WriteLine($"HDR 扫描次数(0,1,2)--[hdr_scan_times_content] = {options.hdr_scan_times[0]},{options.hdr_scan_times[1]},{options.hdr_scan_times[2]}");
                Console.WriteLine($"HDR 投影亮度(0,1,2)--[hdr_projector_brightness_content] = {options.hdr_projector_brightness[0]},{options.hdr_projector_brightness[1]},{options.hdr_projector_brightness[2]}");

                // Parameters related to post-processing
                Console.WriteLine($"置信度去噪阈值--[confidence_threshold] = {options.confidence_threshold}");
                Console.WriteLine($"是否使用自动聚类去噪--[use_auto_noise_removal] = {options.use_auto_noise_removal}");
                Console.WriteLine($"聚类降噪距离阈值--[noise_removal_distance] = {options.noise_removal_distance}");
                Console.WriteLine($"聚类降噪有效点数阈值--[noise_removal_point_number] = {options.noise_removal_point_number}");
                Console.WriteLine($"反射去噪阈值--[reflection_filter_threshold] = {options.reflection_filter_threshold}");
                Console.WriteLine($"高斯平滑--[smooth_sigma] = {options.smooth_sigma}");
                Console.WriteLine($"下采样距离(m)--[downsample_distance] = {options.downsample_distance}");
                Console.WriteLine($"是否计算法向量--[calc_normal] = {options.calc_normal}");
                Console.WriteLine($"计算法向量距离--[calc_normal_radius] = {options.calc_normal_radius}");
                Console.WriteLine($"z向截断最小值--[truncate_z_min] = {options.truncate_z_min}");
                Console.WriteLine($"z向截断最大值--[truncate_z_max] = {options.truncate_z_max}");

                Console.WriteLine($"ROI(x,y,w,h)--[roi] = {options.roi.x},{options.roi.y},{options.roi.width},{options.roi.height}");

        }

        /// <summary>
        /// 打印参数信息
        /// </summary>
        /// <param name="options"></param>
        public static void Print(this X2.CaptureOptions options)
        {
                Console.WriteLine($"拍摄参数---");
                /**
                * P and I series supports the following modes:
                * CaptureMode_Normal
                * CaptureMode_Fast
                * CaptureMode_AntiInterReflection
                *
                * G series supports the following modes:
                * CaptureMode_Ultra
                * CaptureMode_AntiInterReflection
                *
                * M series supports the following modes:
                * CaptureMode_Ultra
                * CaptureMode_AntiInterReflection
                * CaptureMode_SwingLineScan
                * CaptureMode_FixedLineScan
                *
                * Note:The CaptureMode_Robust has been deprecated. You can achieve the same effect by setting the
                * 'scan_times' parameter.
                */
                Console.WriteLine($"拍摄模式--[capture_mode] = {options.capture_mode.Name()}");
                // Parameters related to 2D Capture
                Console.WriteLine($"2D 曝光时间--[exposure_time_2d] = {options.exposure_time_2d}");
                Console.WriteLine($"2D 增益--[gain_2d] = {options.gain_2d}");
                Console.WriteLine($"2D Gamma--[gamma_2d] = {options.gamma_2d}");
                Console.WriteLine($"2D 拍摄是否使用光机--[use_projector_capturing_2d_image] = {options.use_projector_capturing_2d_image}");

                // Parameters related to 3D Capture
                Console.WriteLine($"3D采集中拍摄2D图-[enable_2d_in_capture] = {options.enable_2d_in_capture}");
                Console.WriteLine($"3D 曝光时间--[exposure_time_3d] = {options.exposure_time_3d}");
                Console.WriteLine($"3D 增益--[gain_3d] = {options.gain_3d}");
                Console.WriteLine($"3D Gamma--[gamma_3d] = {options.gamma_3d}");
                Console.WriteLine($"光强对比度阈值--[light_contrast_threshold] = {options.light_contrast_threshold}");
                Console.WriteLine($"投影亮度--[projector_brightness] = {options.projector_brightness}");
                // Note:Only the G and M series support the 'scan_times' parameter.
                Console.WriteLine($"扫描次数--[scan_times] = {options.scan_times}");

                // Note:Only M series support the 'line_scanner_*' and 'correspond2d' parameters.
                Console.WriteLine($"线扫时间--[line_scanner_scan_time_ms] = {options.line_scanner_scan_time_ms}");
                Console.WriteLine($"线扫单行曝光时间--[line_scanner_exposure_time_us] = {options.line_scanner_exposure_time_us}");
                Console.WriteLine($"线扫最小距离--[line_scanner_min_distance] = {options.line_scanner_min_distance}");
                Console.WriteLine($"线扫最大距离--[line_scanner_max_distance] = {options.line_scanner_max_distance}");
                Console.WriteLine($"线扫亮度阈值--[line_scanner_brightness_threshold] = {options.line_scanner_brightness_threshold}");
                Console.WriteLine($"固定线扫激光线位置--[line_scanner_laser_position] = {options.line_scanner_laser_position}");
                Console.WriteLine($"点云是否与2D图对齐--[correspond2d] = {options.correspond2d}");
                Console.WriteLine($"触发模式--[trigger_mode] = {options.trigger_mode}");
                Console.WriteLine($"编码器触发间隔--[encoder_trigger_interval] = {options.encoder_trigger_interval}");

                /**
                * Currently supported HDR modes include:
                * CaptureMode_Normal
                * CaptureMode_Fast
                * CaptureMode_Ultra
                * CaptureMode_AntiInterReflection
                */
                Console.WriteLine($"HDR 次数--[hdr_exposuretime_content] = {options.hdr_exposure_times}");
                Console.WriteLine($"HDR 曝光(0,1,2)--[hdr_exposuretime_content] = {options.hdr_exposuretime_content[0]},{options.hdr_exposuretime_content[1]},{options.hdr_exposuretime_content[2]}");
                Console.WriteLine($"HDR 增益(0,1,2)--[hdr_gain3d_content] = {options.hdr_gain_3d[0]},{options.hdr_gain_3d[1]},{options.hdr_gain_3d[2]}");
                Console.WriteLine($"HDR 扫描次数(0,1,2)--[hdr_scan_times_content] = {options.hdr_scan_times[0]},{options.hdr_scan_times[1]},{options.hdr_scan_times[2]}");
                // Note:Only the G and M series support the 'hdr_scan_times' parameter.
                Console.WriteLine($"HDR 投影亮度(0,1,2)--[hdr_projector_brightness_content] = {options.hdr_projector_brightness[0]},{options.hdr_projector_brightness[1]},{options.hdr_projector_brightness[2]}");
                
                // Parameters related to post-processing
                Console.WriteLine($"置信度去噪阈值--[confidence_threshold] = {options.confidence_threshold}");
                Console.WriteLine($"线扫置信度--[line_scanner_confidence] = {options.line_scanner_confidence}");
                Console.WriteLine($"是否使用自动聚类去噪--[use_auto_noise_removal] = {options.use_auto_noise_removal}");
                Console.WriteLine($"聚类降噪距离阈值--[noise_removal_distance] = {options.noise_removal_distance}");
                Console.WriteLine($"聚类降噪有效点数阈值--[noise_removal_point_number] = {options.noise_removal_point_number}");
                Console.WriteLine($"反射去噪阈值--[reflection_filter_threshold] = {options.reflection_filter_threshold}");
                Console.WriteLine($"高斯平滑--[smooth_sigma] = {options.smooth_sigma}");
                Console.WriteLine($"下采样距离(m)--[downsample_distance] = {options.downsample_distance}");
                Console.WriteLine($"是否计算法向量--[calc_normal] = {options.calc_normal}");
                Console.WriteLine($"计算法向量距离--[calc_normal_radius] = {options.calc_normal_radius}");
                Console.WriteLine($"点云补全-[pointcloud_completion] = {options.pointcloud_completion}");
                Console.WriteLine($"ROI(x,y,w,h)--[roi] = {options.roi.x},{options.roi.y},{options.roi.width},{options.roi.height}");
                Console.WriteLine($"z向截断最小值--[truncate_z_min] = {options.truncate_z_min}");
                Console.WriteLine($"z向截断最大值--[truncate_z_max] = {options.truncate_z_max}");
        }

        /// <summary>
        /// 因为ascii保存较慢，建议使用 SavePlyBinary
        /// </summary>
        [Obsolete]
        public static void SavePlyAscii(double[] xs, double[] ys, double[] zs, string filePath, bool unit_mm = true)
        {
            int len = xs.Length;

            string save_address = filePath;// "./Data/save.ply";
            FileStream fs = new FileStream(save_address, FileMode.Create);

            string header = default;
            header += "ply\n";
            header += "format ascii 1.0\n";
            //header += unit_mm ? "unit = millimeter\n" : "unit = meter\n";
            header += "comment Created by Rvbust, Inc\n";
            header += $"element vertex {len}\n";
            header += "property float x\n";
            header += "property float y\n";
            header += "property float z\n";
            header += "end_header\n";
            byte[] bhelddata = new UTF8Encoding().GetBytes(header);
            fs.Write(bhelddata, 0, bhelddata.Length);
            for (int i = 0; i < len; i++)
            {
                string sdata = $"{xs[i]} {ys[i]} {zs[i]}\n";
                byte[] data = new UTF8Encoding().GetBytes(sdata);
                fs.Write(data, 0, data.Length);
            }
            fs.Flush();
            fs.Close();
        }

        /// <summary>
        /// 因为ascii保存较慢，建议使用 SavePlyBinary
        /// </summary>
        [Obsolete]
        public static void SavePlyAscii(List<double> xs, List<double> ys, List<double> zs, string filePath, bool unit_mm = true)
        {
            int len = xs.Count;

            string save_address = filePath;// "./Data/save.ply";
            FileStream fs = new FileStream(save_address, FileMode.Create);

            string header = default;
            header += "ply\n";
            header += "format ascii 1.0\n";
            //header += unit_mm ? "unit = millimeter\n" : "unit = meter\n";
            header += "comment Created by Rvbust, Inc\n";
            header += $"element vertex {len}\n";
            header += "property float x\n";
            header += "property float y\n";
            header += "property float z\n";
            header += "end_header\n";
            byte[] bhelddata = new UTF8Encoding().GetBytes(header);
            fs.Write(bhelddata, 0, bhelddata.Length);
            for (int i = 0; i < len; i++)
            {
                string sdata = $"{xs[i]} {ys[i]} {zs[i]}\n";
                byte[] data = new UTF8Encoding().GetBytes(sdata);
                fs.Write(data, 0, data.Length);
            }
            fs.Flush();
            fs.Close();
        }


        /// <summary>
        /// 因为ascii保存较慢，建议使用 SavePlyBinary
        /// </summary>
        [Obsolete]
        private static void SavePlyWithColorAscii(double[] xs, double[] ys, double[] zs, byte[] bgr, string filePath, bool unit_mm)
        {
            int len = xs.Length;
            string save_address = filePath;// "./Data/save.ply";
            FileStream fs = new FileStream(save_address, FileMode.Create);

            string header = default;
            header += "ply\n";
            header += "format ascii 1.0\n";
            //header += unit_mm ? "unit = millimeter\n" : "unit = meter\n";
            header += "comment Created by Rvbust, Inc\n";
            header += $"element vertex {len}\n";
            header += "property float x\n";
            header += "property float y\n";
            header += "property float z\n";
            header += "property uchar red\n";
            header += "property uchar green\n";
            header += "property uchar blue\n";
            header += "end_header\n";
            byte[] bhelddata = new UTF8Encoding().GetBytes(header);
            fs.Write(bhelddata, 0, bhelddata.Length);

            for (int i = 0; i < len; i++)
            {
                string sdata = $"{xs[i]} {ys[i]} {zs[i]} {bgr[i * 3 + 2]} {bgr[i * 3 + 1]} {bgr[i * 3]}\n";
                byte[] data = new UTF8Encoding().GetBytes(sdata);
                fs.Write(data, 0, data.Length);
            }
            fs.Flush();
            fs.Close();
        }

        /// <summary>
        /// 因为ascii保存较慢，建议使用 SavePlyBinary
        /// </summary>
        [Obsolete]
        private static void SavePlyWithGrayAscii(double[] xs, double[] ys, double[] zs, byte[] gray, string filePath, bool unit_mm)
        {
            int len = xs.Length;

            string save_address = filePath;// "./Data/save.ply";
            FileStream fs = new FileStream(save_address, FileMode.Create);

            string header = default;
            header += "ply\n";
            header += "format ascii 1.0\n";
            //header += unit_mm ? "unit = millimeter\n" : "unit = meter\n";
            header += "comment Created by Rvbust, Inc\n";
            header += $"element vertex {len}\n";
            header += "property float x\n";
            header += "property float y\n";
            header += "property float z\n";
            header += "property uchar red\n";
            header += "property uchar green\n";
            header += "property uchar blue\n";
            header += "end_header\n";
            byte[] bhelddata = new UTF8Encoding().GetBytes(header);
            fs.Write(bhelddata, 0, bhelddata.Length);

            for (int i = 0; i < len; i++)
            {
                string sdata = $"{xs[i]} {ys[i]} {zs[i]} {gray[i]} {gray[i]} {gray[i]}\n";
                byte[] data = new UTF8Encoding().GetBytes(sdata);
                fs.Write(data, 0, data.Length);
            }
            fs.Flush();
            fs.Close();
        }

        private static void ž(double[] xs, double[] ys, double[] zs, double xMin, double xMax,
            double yMin, double yMax, double zMin, double zMax,
            ref List<double> x, ref List<double> y, ref List<double> z)
        {
            x.Clear();
            y.Clear();
            z.Clear();

            int len = xs.Length;
            for (int i = 0; i < len; i++)
            {
                if (xs[i] >= xMin &&
                    xs[i] <= xMax &&
                    ys[i] >= yMin &&
                    ys[i] <= yMax &&
                    zs[i] >= zMin &&
                    zs[i] <= zMax)
                {
                    x.Add(xs[i]);
                    y.Add(ys[i]);
                    z.Add(zs[i]);
                }
            }
        }

        private static void PointCloudRemoveNull(double[] xs, double[] ys, double[] zs,
            out List<double> x, out List<double> y, out List<double> z)
        {
            x = new List<double>();
            y = new List<double>();
            z = new List<double>();

            int len = xs.Length;
            for (int i = 0; i < len; i++)
            {
                if (double.IsInfinity(xs[i]) ||
                    double.IsNaN(xs[i]) ||
                    double.IsInfinity(ys[i]) ||
                    double.IsNaN(ys[i]) ||
                    double.IsInfinity(zs[i]) ||
                    double.IsNaN(zs[i]))
                {

                }
                else
                {
                    x.Add(xs[i]);
                    y.Add(ys[i]);
                    z.Add(zs[i]);
                }
            }
        }

        private static void PointCloudTruncate(double[] xs, double[] ys, double[] zs, double xMin, double xMax,
    double yMin, double yMax, double zMin, double zMax,
    ref List<double> x, ref List<double> y, ref List<double> z)
        {
            x.Clear();
            y.Clear();
            z.Clear();

            int len = xs.Length;
            for (int i = 0; i < len; i++)
            {
                if (xs[i] >= xMin &&
                    xs[i] <= xMax &&
                    ys[i] >= yMin &&
                    ys[i] <= yMax &&
                    zs[i] >= zMin &&
                    zs[i] <= zMax)
                {
                    x.Add(xs[i]);
                    y.Add(ys[i]);
                    z.Add(zs[i]);
                }
            }
        }
        private static void PointCloudReplaceNull(double[] x, double[] y, double[] z,
            double rx = 0.0, double ry = 0.0, double rz = 0.0)
        {
            int len = x.Length;
            for (int i = 0; i < len; i++)
            {
                if (double.IsInfinity(x[i]) ||
                    double.IsNaN(x[i]) ||
                    double.IsInfinity(y[i]) ||
                    double.IsNaN(y[i]) ||
                    double.IsInfinity(z[i]) ||
                    double.IsNaN(z[i]))
                {
                    x[i] = rx;
                    y[i] = ry;
                    z[i] = rz;
                }
            }
        }
    }
}
