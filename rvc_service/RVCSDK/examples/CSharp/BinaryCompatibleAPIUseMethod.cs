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

            bool ret = false;

            // Load Options From File and Capture.
            // You can save these parameters as different configuration files  By RVC Manager and then import the files before capture.
            // When switching the RVC SDK version,if you capture with options,you should load the options from a JSON file.
            // Using the "Capture(options)" function may cause exceptions because the structure of "struct CaptureOptions" varies across different versions.
            // Loading options from a JSON file can effectively avoid such exceptions.

            // Load setting from file.json
            {
                ret = camera.LoadSettingFromFile("file.json");
                if (ret)
                {
                    Console.WriteLine("Load file.json Succeed");
                }
                else
                {
                    Console.WriteLine($"Load file.json Failed. Error: {System.GetLastErrorMessage()} ");
                    camera.Close();
                    camera.Destroy();
                    RVC_CSharp.System.Shutdown();
                    Console.WriteLine("Press any key to exit. ");
                    Console.ReadKey();
                    return;
                }
            }

            // Save setting to file_out.json
            {

                //ret = camera.SaveSettingToFile("file_out.json");
                //if (ret)
                //{
                //    Console.WriteLine("After Saving file_out.json succeed");
                //}
                //else
                //{
                //    Console.WriteLine($"After Saving file_out.json failed. Error: {System.GetLastErrorMessage()} ");
                //    camera.Close();
                //    camera.Destroy();
                //    RVC_CSharp.System.Shutdown();
                //    Console.ReadKey();
                //    Console.WriteLine("Press any key to exit. ");
                //    return;
                //}
            }

            // Use Capture() without capture options struct to use parameters stored in camera
            ret = camera.Capture();

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
