using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
#if Halcon_Enable
using HalconDotNet;
#endif
#if OpenCV_Enable
using OpenCvSharp;
#endif
#if VisionPro_Enable
using Cognex.VisionPro;
#endif
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

            #region Step 3 , Capture

            // Capture using the internal parameters of the camera.
            // We suggest that you adjust the parameters in RVC Manager first.
            bool ret = camera.Capture();

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

#if OpenCV_Enable
            // OpencvExtension
            Mat matImage = image.ToMat();
            Mat matDepth = depth.ToMat();
            Mat matPointCloud = pointMap.ToMat();
            matImage.SaveImage($"./{info.name}-{info.sn}/OpencvImage.bmp");
            Console.WriteLine($"Save Opencv Image,path = ./{info.name}-{info.sn}/OpencvImage.bmp");
#endif  


#if Halcon_Enable
            // HalconExtension,需要Lincese才能运行  
            try
            {
                HObject halconImage = image.ToHalcon();
                HObject halconDepth = depth.ToHalcon();
                HTuple halconPointCloud = pointMap.ToHalcon();

                halconImage.SaveImage("bmp", $"./{info.name}-{info.sn}/HalconImage.bmp");
                Console.WriteLine($"Save Halcon Image,path = ./{info.name}-{info.sn}/HalconImage.bmp");

                halconDepth.SaveDepth("tiff", $"./{info.name}-{info.sn}/HalconDepth.tiff");
                Console.WriteLine($"Save Halcon Depth,path = ./{info.name}-{info.sn}/HalconDepth.tiff");

                halconPointCloud.SavePointCloud("om3", $"./{info.name}-{info.sn}/HalconPointCloud.om3");
                Console.WriteLine($"Save Halcon PointMap,path = ./{info.name}-{info.sn}/HalconPointCloud.om3");

            }
            catch (Exception e)
            {
                Console.WriteLine(e);
            }
#endif

#if VisionPro_Enable

            // VisionProExtension,需要Lincese才能运行   

            try
            {
                CogImage16Range range = pointMap.ToVisionPro();
                range.Save($"./{info.name}-{info.sn}/VisionProPointMap.idb");
                Console.WriteLine($"Save VisionPro PointMap,path = ./{info.name}-{info.sn}/VisionProPointMap.idb");

            }
            catch (Exception e)
            {
                Console.WriteLine(e);
            }
#endif

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
