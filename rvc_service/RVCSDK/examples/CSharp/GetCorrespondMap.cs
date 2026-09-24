using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;

namespace RVC_CSharp
{
    class Program
    {

        static void Main()
        {
            #region Step 0 , Start init system.

            if (false == RVC_CSharp.System.Init())
            {
                Console.WriteLine("Failed to init system.");
                Console.ReadKey();
                return;
            }
            else
            {
                Console.WriteLine("Successfully init system.");
            }

            #endregion

            #region Step 1 , Start Find Devices

            Console.WriteLine("Step 1 , Start Find Devices.");

            List<Device> devices = RVC_CSharp.System.ListDevices(SystemListDeviceType.GigE);

            if (devices == null || devices.Count <= 0)
            {
                Console.WriteLine("Can not find device.\nPlease Check Connection.");

                Console.WriteLine("System close.");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            Console.WriteLine($"Find {devices.Count} devices.");

            #endregion

            #region Step 2 , Choose Target Device

            Console.WriteLine("Step 2 , Choose Target Device.");

            Console.WriteLine("List All Devices.");
            DeviceInfo info = new DeviceInfo();
            for (int i = 0; i < devices.Count; i++)
            {
                var deviceTmp = devices[i];
                DeviceInfo infoTmp = new DeviceInfo();
                deviceTmp.GetDeviceInfo(ref infoTmp);
                bool canConnected = deviceTmp.CheckCanConnected();
                Console.WriteLine("\n");
                Console.WriteLine($"{i}-设备名称--[name] = {infoTmp.name}");
                Console.WriteLine($"{i}-设备序列号--[sn] = {infoTmp.sn}");
                Console.WriteLine($"{i}-出厂日期--[factroydate] = {infoTmp.factroydate}");
                Console.WriteLine($"{i}-端口类型--[type] = {infoTmp.type}");
                Console.WriteLine($"{i}-端口号--[port] = {infoTmp.port}【只针对网络相机】");
                if (canConnected)
                {
                    Console.WriteLine($"{i}-主板类型--[boardmodel] = {infoTmp.boardmodel}");
                    Console.WriteLine($"{i}-支持的相机类型--[cameraid] = {infoTmp.cameraid}");
                    Console.WriteLine($"{i}-是否支持单相机--[support_x1] = {infoTmp.support_x1}");
                    Console.WriteLine($"{i}-是否支持双相机--[support_x2] = {infoTmp.support_x2}");
                    Console.WriteLine($"{i}-支持的投影颜色--[support_color] = {infoTmp.support_color}");
                    Console.WriteLine($"{i}-工作距离-近--[workingdist_near_mm] = {infoTmp.workingdist_near_mm}");
                    Console.WriteLine($"{i}-工作距离-远--[workingdist_far_mm] = {infoTmp.workingdist_far_mm}");
                    Console.WriteLine($"{i}-固件版本--[firmware_version] = {infoTmp.firmware_version}");
                    Console.WriteLine($"{i}-支持的拍摄模式--[support_capture_mode] = {infoTmp.support_capture_mode}");
                    Console.WriteLine($"{i}-是否支持防护盖控制--[support_protective_cover] = {infoTmp.support_protective_cover}");
                }
                Console.WriteLine($"{i}-是否可以连接 = {canConnected}");
                Console.WriteLine("\n");
            }

            Console.WriteLine("Input the id of device that you want to connect.");

            Console.Write("ID : ");
            string str = Console.ReadLine();
            var parseRet = int.TryParse(str, out int id);
            if (!parseRet || id < 0 || id >= devices.Count)
            {
                Console.WriteLine("Input is not valid");
                Console.WriteLine("System close.");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            RVC_CSharp.Device device = devices[id];
            device.GetDeviceInfo(ref info);
            #endregion

            #region Step 3 , Open Camera

            if (false == device.IsValid() || false == device.CheckCanConnected())
            {
                Console.WriteLine("Device Can not be Connected.\nPlease Check Connection.");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            if (!info.support_x2 || (info.support_capture_mode & CaptureMode.CaptureMode_SwingLineScan) == 0)
            {
                Console.WriteLine("Device not support X2 or SwingLineScan!");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }
            if(device.IsFirmwareMatch() == false)
            {
                Console.WriteLine("Device firmware mismatch. Please use RVCManager to upgrade the firmware");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }
            X2 camera = RVC_CSharp.X2.Create(device);
            camera.Open();
            if (false == camera.IsValid() || false == camera.IsOpen())
            {
                Console.WriteLine($"Failed to open camera .Error: { System.GetLastErrorMessage() } ");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }
            #endregion

            #region Step 4 , Capture

            X2.CaptureOptions options = X2.CaptureOptions.Default();
            camera.LoadCaptureOptionParameters(ref options);

            options.capture_mode = CaptureMode.CaptureMode_SwingLineScan;
            options.line_scanner_scan_time_ms = 2500;
            options.line_scanner_min_distance = 400;
            options.line_scanner_max_distance = 800;
            options.line_scanner_exposure_time_us = 300;
            options.correspond2d = false;

            bool ret = camera.Capture(options);

            if (false == ret)
            {
                Console.WriteLine($"Failed to Capture .Error: { System.GetLastErrorMessage() } ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            DepthMap depth = camera.GetDepthMap();
            PointMap pointMap = camera.GetPointMap();

            if (options.capture_mode == CaptureMode.CaptureMode_SwingLineScan && !options.correspond2d)
            {
                CorrespondMap correspond_map =camera.GetCorrespondMap();
                Size sz = correspond_map.GetSize();
                int select_point3d_index = (sz.height * sz.width) / 2;

                unsafe
                {
                    double* dataPtr = (double*)correspond_map.GetDataPtr();
                    double correspond2d_x = dataPtr[2 * select_point3d_index];
                    double correspond2d_y = dataPtr[2 * select_point3d_index + 1];
                    Console.WriteLine($"The {select_point3d_index}th 3D point corresponds to the 2D pixel: ({correspond2d_x}, {correspond2d_y})");
                }
            }
            else
            {
                Console.WriteLine("CorrespondMap is only effective when the mode is SwingLineScan mode and Correspond2d is set to false. In other cases, the 3D points already correspond to the 2D image.");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            #endregion

            #region Step 5 , Data Process

            Directory.CreateDirectory($"./{info.name}-{info.sn}");


            // Depth
            string depthFile = $"./{info.name}-{info.sn}/Depth.tiff";
            Console.WriteLine($"Save Depth,path = {depthFile}");
            depth.SaveDepthMap(depthFile);

            // Point Cloud 
            string pointCloudFile = $"./{info.name}-{info.sn}/PointCloud.ply";
            Console.WriteLine($"Save PointMap,path = {pointCloudFile}");
            pointMap.SavePlyBinary(pointCloudFile);

            Console.WriteLine("Successfully Process Data .");

            #endregion

            #region Step 6 , Close And Release Device

            camera.Close();
            camera.Destroy();

            RVC_CSharp.System.Shutdown();
            Console.WriteLine("System close.");

            Console.ReadKey();
            #endregion

            return;
        }

    }
}
