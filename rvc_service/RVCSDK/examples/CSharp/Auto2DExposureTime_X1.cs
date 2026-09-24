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

            #region Step 1 , Find Device

            // Method 1 , find Device By Sn . You can get device SN by RVC Manager.
            // * Most Recommended Method .
            //Device device = RVC_CSharp.System.FindDeviceBySN("12345678");

            // Method 2 , find Device By Index . 
            // If you only have one camera, you can use this method.
            Device device = RVC_CSharp.System.FindDeviceByIndex(0);

            if (false == device.IsValid() || false == device.CheckCanConnected())
            {
                Console.WriteLine("Device Can not be Connected.\nPlease Check Connection.");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            #endregion

            #region Step 2 , Open Camera

            if (device.IsFirmwareMatch() == false)
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
                Console.WriteLine($"Failed to open camera. Error: {System.GetLastErrorMessage()} ");
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

            #region Step 3 , Get Auto 2D Exposure Time and Capture

            X1.CaptureOptions options = new X1.CaptureOptions();
            camera.LoadCaptureOptionParameters(ref options);

            // Set ROI used to evaluate brightness for auto exposure calculation.
            // If width or height equals 0, the full image will be used.
            ROI roi = new ROI(10, 10, 200, 200);

            // Get auto 2D exposure time.
            // On success, options.exposure_time_2d is updated with the automatically determined value.
            // On failure, options.exposure_time_2d retains its original value and can be used as a fallback.
            bool ret = camera.GetAuto2DExposureTime(ref options, roi);
            if (ret)
            {
                Console.WriteLine("Get auto 2D exposure time success.");
                Console.WriteLine($"Auto exposure_time_2d: {options.exposure_time_2d}");
            }
            else
            {
                Console.WriteLine($"Get auto 2D exposure time failed. Error: {System.GetLastErrorMessage()}");
                Console.WriteLine("Custom exposure_time_2d setting will be used.");
            }

            // Capture a 2D image using the (auto-adjusted) capture options.
            ret = camera.Capture2D(options);
            if (false == ret)
            {
                Console.WriteLine($"Failed to Capture2D. Error: {System.GetLastErrorMessage()} ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            Image image = camera.GetImage();

            #endregion

            #region Step 4 , Data Process

            Directory.CreateDirectory($"./{info.name}-{info.sn}");

            // 2D Image
            string imageFile = $"./{info.name}-{info.sn}/Image.bmp";
            Console.WriteLine($"Save Image, path = {imageFile}");
            image.SaveImage(imageFile);

            Console.WriteLine("Successfully saved image.");

            #endregion

            #region Step 5 , Close And Release Device

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
