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
        static void UseX1()
        {
            #region Step 0 ,Init & Find & Open

            if (false == RVC_CSharp.System.Init())
            {
                Console.WriteLine("Failed to init system.");
                Console.ReadKey();
                return;
            }

            Device device = RVC_CSharp.System.FindDeviceByIndex(0);
            if (false == device.IsValid() || false == device.CheckCanConnected())
            {
                Console.WriteLine("Device Can not be Connected.\nPlease Check Connection.");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            // optional 
            // Print Device Info
            DeviceInfo info = new DeviceInfo();
            device.GetDeviceInfo(ref info);
            info.Print();

            if (info.support_x1 == false)
            {
                Console.WriteLine("Device not support x1!");
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
            X1 camera = RVC_CSharp.X1.Create(device, CameraID.CameraID_Left);
            camera.Open();
            if (false == camera.IsValid() || false == camera.IsOpen())
            {
                Console.WriteLine($"Failed to open camera .Error: {System.GetLastErrorMessage()} ");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }


            #endregion

            #region Step 1 ,[Main Step] Modify Options And Capture

            X1.CaptureOptions cap_opt = X1.CaptureOptions.Default();

            // Transform point map's coordinate to camera or reference plane
            cap_opt.transform_to_camera = true;
            // Set noise points filter range (0~30)
            cap_opt.filter_range = 0;
            // Set projector brightness (1~240)
            cap_opt.projector_brightness = 200;
            // Set camera exposure time (3~100) ms
            cap_opt.exposure_time_2d = 20;
            cap_opt.exposure_time_3d = 20;

            // Set HDR exposure times [0, 2, 3]. 0 presents not use hdr. 2 and 3 presents hdr times.
            cap_opt.hdr_exposure_times = 3;
            cap_opt.hdr_exposuretime_content = new int[3];
            cap_opt.hdr_exposuretime_content[0] = 3;
            cap_opt.hdr_exposuretime_content[1] = 6;
            cap_opt.hdr_exposuretime_content[2] = 12;

            bool ret = false;

            ret = camera.SaveCaptureOptionParameters(cap_opt);
            if (ret)
            {
                Console.WriteLine("Save Capture Option Parameters Succeed");
            }
            else
            {
                Console.WriteLine($"Save Capture Option Parameters Failed. Error: {System.GetLastErrorMessage()} ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.WriteLine("Press any key to exit. ");
                Console.ReadKey();
                return;
            }

            X1.CaptureOptions options = new X1.CaptureOptions();

            ret = camera.LoadCaptureOptionParameters(ref options);
            if (ret)
            {
                Console.WriteLine("Load Capture Option Parameters Succeed");
            }
            else
            {
                Console.WriteLine($"Load Capture Option Parameters Failed. Error: {System.GetLastErrorMessage()} ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.WriteLine("Press any key to exit. ");
                Console.ReadKey();
                return;
            }

            options.Print();
            #endregion

            #region Step 2 , Close

            camera.Close();
            camera.Destroy();

            RVC_CSharp.System.Shutdown();
            Console.WriteLine("System close.");

            Console.ReadKey();
            #endregion
            return;

        }
        static void UseX2()
        {
            #region Step 0 ,Init & Find & Open

            if (false == RVC_CSharp.System.Init())
            {
                Console.WriteLine("Failed to init system.");
                return;
            }

            Device device = RVC_CSharp.System.FindDeviceByIndex(0);
            //Device device = RVC_CSharp.System.FindDeviceBySN("P2GM353W002");
            if(device.IsFirmwareMatch() == false)
            {
                Console.WriteLine("Device firmware mismatch. Please use RVCManager to upgrade the firmware");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }
            
            if (false == device.IsValid() || false == device.CheckCanConnected())
            {
                Console.WriteLine("Device Can not be Connected.\nPlease Check Connection.");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            X2 camera = RVC_CSharp.X2.Create(device);
            camera.Open();
            if (false == camera.IsValid() || false == camera.IsOpen())
            {
                Console.WriteLine($"Failed to open camera .Error: {System.GetLastErrorMessage()} ");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }
            // optional 
            // Print Device Info
            DeviceInfo info = new DeviceInfo();
            device.GetDeviceInfo(ref info);
            info.Print();
            #endregion

            #region Step 1 ,[Main Step] Modify Options And Capture

            X2.CaptureOptions cap_opt = X2.CaptureOptions.Default();

            // Transform point map's coordinate to camera or reference plane
            cap_opt.transform_to_camera = RVC_CSharp.CameraID.CameraID_NONE;
            // Set light contrast threshold range (0~10). the default value is 3.
            cap_opt.light_contrast_threshold = 3;
            // Set projector brightness (1~240)
            cap_opt.projector_brightness = 200;
            // Set camera exposure time (3~100) ms
            cap_opt.exposure_time_2d = 20;
            cap_opt.exposure_time_3d = 20;
            // Set projector color
            cap_opt.projector_color = RVC_CSharp.ProjectorColor.ProjectorColor_Blue;

            bool ret = false;

            ret = camera.SaveCaptureOptionParameters(cap_opt);

            if (ret)
            {
                Console.WriteLine("Save Capture Option Parameters Succeed");
            }
            else
            {
                Console.WriteLine($"Save Capture Option Parameters Failed. Error: {System.GetLastErrorMessage()} ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.WriteLine("Press any key to exit. ");
                Console.ReadKey();
                return;
            }

            X2.CaptureOptions options = new X2.CaptureOptions();

            ret = camera.LoadCaptureOptionParameters(ref options);

            if (ret)
            {
                Console.WriteLine("Load Capture Option Parameters Succeed");
            }
            else
            {
                Console.WriteLine($"Load Capture Option Parameters Failed. Error: {System.GetLastErrorMessage()} ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.WriteLine("Press any key to exit. ");
                Console.ReadKey();
                return;
            }


            options.Print();

            #endregion

            #region Step 2 ,  Close

            camera.Close();
            camera.Destroy();

            RVC_CSharp.System.Shutdown();
            Console.WriteLine("System close.");

            Console.ReadKey();
            #endregion

            return;
        }
        static void Main()
        {
            UseX1();
            UseX2();
            Console.ReadKey();
            return;
        }

    }
}
