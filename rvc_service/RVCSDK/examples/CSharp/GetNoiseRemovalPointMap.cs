/**
 * This example is to demonstrate the usage of Cluster Filter and Reflection Filter. Cluster Filter is used in almost
 * all scenarios. It is employed to remove small clusters of outliers. Reflection Filter is designed to eliminate large
 * areas of point cloud noise caused by reflections, which are difficult to remove with Cluster Filter alone.
 */
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

            /**
             * The Cluster Filter removes floating points and isolated clusters from the point cloud.
             * The 'noise_removal_distance' parameter indicates the maximum distance between points that are considered to be
             * in the same class. Points that are farther apart than this value will be classified into a new class.
             * The 'noise_removal_point_number' parameter specifies that if the number of points within the same cluster is less
             * than this value, they will be considered as outliers and removed.
             */
            options.noise_removal_distance = 0.5;// unit: mm
            options.noise_removal_point_number = 40;

            /**
             * 'reflection_filter_threshold' used to remove large-area erroneous point clouds caused by reflections.
             * The higher this value is set, the more points will be removed by the reflection filter.
             * Setting it too large may remove data from thin and pointy objects.
             * range:[0, 30]
             */
            options.reflection_filter_threshold = 10;
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
