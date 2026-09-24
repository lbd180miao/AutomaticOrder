using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
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
            // optional 
            // Print Device Info
            DeviceInfo info = new DeviceInfo();
            device.GetDeviceInfo(ref info);
            info.Print();            
            #endregion

            #region Step 3 , Capture

            X1.CaptureOptions options = X1.CaptureOptions.Default();
            camera.LoadCaptureOptionParameters(ref options);

            options.transform_to_camera = true;
            options.exposure_time_2d = 20;
            options.exposure_time_3d = 20;

            double[] transformation = new double[]{0.9981883352,
                                0.0502378577,
                                0.0331089875,
                                -0.0472612266,
                                0.0505828392,
                                -0.9986731004,
                                -0.0096651386,
                                0.076352919,
                                0.0325794993,
                                0.0113223752,
                                -0.999405013,
                                0.9951857984,
                                0.0,
                                0.0,
                                0.0,
                                1.0

    };

            X1.CustomTransformOptions custom_trans_opt = X1.CustomTransformOptions.Default();
            custom_trans_opt.coordinate_select = X1.CustomTransformOptions.CoordinateSelect.CoordinateSelect_Camera;
            custom_trans_opt.transform = transformation;

            bool ret = camera.SetCustomTransformation(custom_trans_opt);

            if (ret)
            {
                Console.WriteLine("set transformation success");
            }
            else
            {
                Console.WriteLine("set transformation failed!custom transformation will not be used!");
            }

            ret = camera.Capture(options);

            if (false == ret)
            {
                Console.WriteLine($"Failed to Capture .Error: {System.GetLastErrorMessage()} ");
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

            #region Step 4 , Data Process

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

            Console.WriteLine("Successfully Process Data .");

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
