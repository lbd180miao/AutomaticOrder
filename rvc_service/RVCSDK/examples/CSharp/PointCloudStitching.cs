using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;
using static RVC_CSharp.MarkerDetection;

namespace RVC_CSharp
{
    class Program
    {
        static void TestOnline()
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
            CameraID cameraId = CameraID.CameraID_Left;
            if (info.support_extra)
            {
	            cameraId = CameraID.CameraID_Extra;
            }            
            #endregion

            #region Step 3 , Capture and stitch

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

            Image image0 = camera.GetImage(cameraId);
            PointMap pointMap0 = camera.GetPointMap();

            Console.WriteLine("Take next frame. Press Enter to continue...");
            Console.ReadLine();

            camera.Capture();
            Image image1 = camera.GetImage(cameraId);
            PointMap pointMap1 = camera.GetPointMap();

            CodedCircleMarkerType type; // Need to be changed according to the actual type
            type.N = 15;
            type.r1_to_r0_ratio = 4.0 / 1.5;
            type.r2_to_r0_ratio = 6.0 / 1.5;

            List<double> R1 = new List<double>();
            List<double> t1 = new List<double>();
            int ret1 = PointCloudStitching.GetTwoCameraTransformByCodedCircleMarker(pointMap0.m_handle, image0.m_handle, pointMap1.m_handle, image1.m_handle, type, ref R1, ref t1);
            if (ret1 != 0)
            {
                Console.WriteLine("Failed to get transform.");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }
            PointCloudStitching.TransformPointCloud(pointMap1.m_handle, R1, t1);
            pointMap1.Save("output1.ply", PointMapUnit.Meter, true, image1);
            #endregion

            #region Step 4 , Close And Release Device

            camera.Close();
            camera.Destroy();

            RVC_CSharp.System.Shutdown();
            Console.WriteLine("System close.");

            Console.ReadKey();
            #endregion

            return;
        }

        static void TestOffline(string folder, List<string> ply_names, List<string> image_names)
        {
            // Convert point_map1 to the coordinate system of the point_map0
            Image image0 = Image.CreateFromFile(folder + image_names[0]);
            Image image1 = Image.CreateFromFile(folder + image_names[1]);
            if (image0.IsValid() == false || image1.IsValid() == false)
            {
                Console.WriteLine("Failed to load image");
                Console.ReadKey();
                return;
            }

            PointMap pointMap0 = PointMap.CreateFromFile(folder + ply_names[0], image0.GetSize(), PointMapUnit.Meter);
            PointMap pointMap1 = PointMap.CreateFromFile(folder + ply_names[1], image1.GetSize(), PointMapUnit.Meter);
            if (pointMap0.IsValid() == false || pointMap1.IsValid() == false)
            {
                Console.WriteLine("Failed to load point map.");
                Console.ReadKey();
                return;
            }

            CodedCircleMarkerType type; // Need to be changed according to the actual type
            type.N = 15;
            type.r1_to_r0_ratio = 4.0 / 1.5;
            type.r2_to_r0_ratio = 6.0 / 1.5;

            List<double> R1 = new List<double>();
            List<double> t1 = new List<double>();
            int ret = PointCloudStitching.GetTwoCameraTransformByCodedCircleMarker(pointMap0.m_handle, image0.m_handle, pointMap1.m_handle, image1.m_handle, type, ref R1, ref t1);
            if (ret != 0)
            {
                Console.WriteLine("Failed to get transform.");
                Console.ReadKey();
                return;
            }
            PointCloudStitching.TransformPointCloud(pointMap1.m_handle, R1, t1);

            string saveFolder = folder + "result/";
            Directory.CreateDirectory(saveFolder);
            pointMap1.Save(saveFolder + "output1.ply", PointMapUnit.Meter, true, image1);

            if (ply_names.Count() < 3 || image_names.Count() < 3)
            {
                Console.WriteLine("ply_names.Count() < 3 || image_names.Count() < 3.");
                Console.ReadKey();
                return;
            }

            // Convert point_map2 to the coordinate system of the point_map0
            Image image2 = Image.CreateFromFile(folder + image_names[2]);
            if (image2.IsValid() == false)
            {
                Console.WriteLine("Failed to load image");
                Console.ReadKey();
                return;
            }
            PointMap pointMap2 = PointMap.CreateFromFile(folder + ply_names[2], image2.GetSize(), PointMapUnit.Meter);
            if (pointMap2.IsValid() == false)
            {
                Console.WriteLine("Failed to load point map.");
                Console.ReadKey();
                return;
            }

            List<double> R2 = new List<double>();
            List<double> t2 = new List<double>();
            ret = PointCloudStitching.GetTwoCameraTransformByCodedCircleMarker(pointMap1.m_handle, image1.m_handle, pointMap2.m_handle, image2.m_handle, type, ref R2, ref t2);
            if (ret != 0)
            {
                Console.WriteLine("Failed to get transform.");
                Console.ReadKey();
                return;
            }
            PointCloudStitching.TransformPointCloud(pointMap2.m_handle, R2, t2);
            pointMap2.Save(saveFolder + "output2.ply", PointMapUnit.Meter, true, image2);

            // If use CreateFromFile(), you should call Destroy() to release the resource to RVC system.
            Image.Destroy(image0);
            Image.Destroy(image1);
            Image.Destroy(image2);
            PointMap.Destroy(pointMap0);
            PointMap.Destroy(pointMap1);
            PointMap.Destroy(pointMap2);
        }

        // User guild: RVCSDK/docs/PointCloudStitchingManual.pdf
        /*
        This example shows how to stitch three point clouds into the coordinate system of the first point cloud.
        If you have more than three point clouds, the process is the same.
        To generate coded circle marker pattern, see: Examples/Python/Utils/GenerateCodedCircle.py
        */
        static void Main()
        {
            string folder = "D:/temp/";
            List<string> ply_names = new List<string> { "0.ply", "1.ply", "2.ply" };
            List<string> image_names = new List<string> { "0.png", "1.png", "2.png" };
            TestOffline(folder, ply_names, image_names);
            Console.ReadKey();
            return;
            TestOnline();
            Console.ReadKey();
            return;
        }

    }
}
