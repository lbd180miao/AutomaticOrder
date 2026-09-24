using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;
using static System.Net.Mime.MediaTypeNames;

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
            //Device device = RVC_CSharp.System.FindDeviceBySN("P2GM353W002");
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
            CameraID cameraId = CameraID.CameraID_Left;
            if (info.support_extra)
            {
	            cameraId = CameraID.CameraID_Extra;
            }
            #endregion

            #region Step 1 ,[Main Step] Modify Options And Capture

            X2.CaptureOptions options = new X2.CaptureOptions();
            camera.LoadCaptureOptionParameters(ref options);
            // Transform point map's coordinate to camera
            options.transform_to_camera = cameraId;
            // Set 2d and 3d exposure time. Capture with white light, range [11, 100]ms, others [3, 100]ms.
            options.exposure_time_2d = 20;
            options.exposure_time_3d = 20;
            // Set 2d and 3d gain. the default value is 0. The gain value of each series cameras is different, you can call
            // function GetGainRange() to get specific range.
            options.gain_2d = 0;
            options.gain_3d = 0;
            // Set 2d and 3d gamma. the default value is 1. The gamma value of each series cameras is different, you can call
            // function GetGammaRange() to get specific range.
            options.gamma_2d = 1;
            options.gamma_3d = 1;
            // range in [0, 10]. the default value is 3. The contrast of point less than this value will be treat * as invalid
            // point and be removed.
            options.light_contrast_threshold = 2;
            // Set projector color. the default value is RVC::ProjectorColor_Blue.
            options.projector_color = ProjectorColor.ProjectorColor_Blue;
            
            bool ret = false;

            options.Print();

            // Method 1 , Use Default Options and Modify.
            // X2.CaptureOptions options = X2.CaptureOptions.Default();
            // TODO:modify options
            // ret = camera.Capture(options);

            // Method 2 , Load Options From Camera and Modify.
            // X2.CaptureOptions options = new X2.CaptureOptions();
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
                Console.WriteLine($"Failed to Capture .Error: {System.GetLastErrorMessage()} ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            Image image = camera.GetImage(cameraId);
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

            // Mesh
            Mesh mesh = camera.GetMesh();
            string meshFile = $"./{info.name}-{info.sn}/Mesh.stl";
            Console.WriteLine($"Save Mesh,path = {meshFile}");
            mesh.Save(meshFile, PointMapUnit.Meter);

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
