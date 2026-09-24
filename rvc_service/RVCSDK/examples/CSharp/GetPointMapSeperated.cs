using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

namespace RVC_CSharp
{
    class Program
    {

        static void Main()
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
                Console.WriteLine($"Failed to open camera .Error: { System.GetLastErrorMessage() } ");
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

            X1.CaptureOptions options = new X1.CaptureOptions();
            camera.LoadCaptureOptionParameters(ref options);

            bool ret = false;

            options.Print();

            // Method 1 , Use Default Options and Modify.
            // X1.CaptureOptions options = X1.CaptureOptions.Default();
            // TODO:modify options
            // ret = camera.Capture(options);

            // Method 2 , Load Options From Camera and Modify.
            // X1.CaptureOptions options = new X1.CaptureOptions();
            // camera.LoadCaptureOptionParameters(ref options);
            // TODO:modify options
            // ret = camera.Capture(options);

            // *****
            // Method 3 , Using the internal parameters of the camera.
            // We suggest adjusting the camera parameters By RVC Manager.
            // Then, when we use SDK, we directly use the parameters inside the camera.
            ret = camera.Capture(options);

            // Method 4 , Load Options From File and Capture.
            // If you need to capture multiple scenes, their parameters are different.
            // You can save these parameters as different configuration files  By RVC Manager and then import the files before capture.
            // ret = camera.LoadSettingFromFile("file.json");
            // ret = camera.Capture();


            if (false == ret)
            {
                Console.WriteLine($"Failed to Capture .Error: { System.GetLastErrorMessage() } ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            Image image = camera.GetImage();
            DepthMap depth = camera.GetDepthMap();
            PointMap pointMap = camera.GetPointMap();

            #endregion

            #region Step 2 , Data Process And Close

            Directory.CreateDirectory($"./{info.name}-{info.sn}");

            // 2D Image
            string imageFile = $"./{info.name}-{info.sn}/Image.bmp";
            Console.WriteLine($"Save Image,path = {imageFile}");
            image.SaveImage(imageFile);

            // Depth
            string depthFile = $"./{info.name}-{info.sn}/Depth.tiff";
            Console.WriteLine($"Save Depth,path = {depthFile}");
            depth.SaveDepthMap(depthFile);

            // Point Cloud 
            string pointCloudFile = $"./{info.name}-{info.sn}/PointCloud.ply";
            Console.WriteLine($"Save PointMap,path = {pointCloudFile}");
            pointMap.SavePlyBinary(pointCloudFile);

            // Color Point Cloud
            string colorPointCloudFile = $"./{info.name}-{info.sn}/ColorPointCloud.ply";
            Console.WriteLine($"Save Color-PointMap,path = {colorPointCloudFile}");
            pointMap.SaveColorPointCloud(image, colorPointCloudFile);

            Size sz = pointMap.GetSize();
            int pm_num = sz.width * sz.height;
            double[] x = new double[pm_num];
            double[] y = new double[pm_num];
            double[] z = new double[pm_num];

            ret = pointMap.GetPointMapSeperated(out x, out y, out z, 1.0);

            if (ret)
            {
                int validCount = 0;
                for (int i = 0; i < pm_num && validCount < 100; i++)
                {
                    if (double.IsNaN(x[i]))
                        continue;
                    Console.WriteLine($"index:{i}, x:{x[i]:F6}, y:{y[i]:F6}, z:{z[i]:F6}");
                    validCount++;
                }
            }
            else
            {
                Console.WriteLine("Get point map separated failed!");
            }

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
