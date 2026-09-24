using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;
using static RVC_CSharp.ExternalColorCamera;

namespace RVC_CSharp
{
    class Program
    {
        // This example shows the process of acquiring the point cloud of an external camera. Note that this program cannot be
        // run directly. The part that acquires the image of the external camera needs to be modified.
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
            X2 camera = RVC_CSharp.X2.Create(device);
            camera.Open();
            if (false == camera.IsValid() || false == camera.IsOpen())
            {
                Console.WriteLine($"Failed to open camera .Error: {System.GetLastErrorMessage()} ");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }
            DeviceInfo info = new DeviceInfo();
            device.GetDeviceInfo(ref info);
            if (info.support_extra == true)
            {
                Console.WriteLine("Device has already support color!");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }
            #endregion

            #region Step 1 ,Get External Camera Extrinsic Matrix
            // Prepare work: Users need to calibrate the external camera themselves. 
            // The quality of calibration directly affects the quality of final result.
            float[] external_camera_intrinsic_matrix = { 2400, 0, 1000, 0, 2400, 750, 0, 0, 1 }; ;         // Needs to be modified.
            float[] external_camera_camera_distortion = { -0.099f, 0.218f, 0.00037f, 0.0001f, -0.26f };  // Needs to be modified.
            int external_camera_image_width = 0;                                                        // Needs to be modified.
            int external_camera_image_height = 0;                                                       // Needs to be modified. 

            // Capture three point maps with 4 * 11 calibration board to get external camera extrinsic matrix.
            float[] external_camera_extrinsic_matrix = new float[16];

            bool ret = false;

            unsafe
            {
                Directory.CreateDirectory($"./{info.name}-{info.sn}");
                // Capture First Point Map
                Console.WriteLine("Put the calibration board at the nearest working distance and take first frame.");
                Console.WriteLine("Press Enter to continue...");

                Console.ReadLine();

                ret = camera.Capture();
                if (!ret)
                {
                    Console.WriteLine($"Failed to capture.Error: {System.GetLastErrorMessage()} ");
                    camera.Close();
                    camera.Destroy();
                    RVC_CSharp.System.Shutdown();
                    Console.ReadKey();
                    return;
                }

                PointMap internalCameraPointMap0 = camera.GetPointMap();

                Image internalCameraImage0 = camera.GetImage(CameraID.CameraID_Left);

                byte[] externalCameraImageData0 = null;// Get external image. Needs to be modified.

                string pmAddr = $"./{info.name}-{info.sn}/calibration_internal0.ply";
                string imgAddr = $"./{info.name}-{info.sn}/calibration_internal0.ply";
                internalCameraPointMap0.SaveColorPointCloud(internalCameraImage0, pmAddr, unit_mm: false);
                internalCameraImage0.SaveImage(imgAddr);

                // Capture Second Point Map
                Console.WriteLine("Put the calibration board at the middle working distance and take first frame.");
                Console.WriteLine("Press Enter to continue...");
                Console.ReadLine();

                ret = camera.Capture();
                if (!ret)
                {
                    Console.WriteLine($"Failed to capture.Error: {System.GetLastErrorMessage()} ");
                    camera.Close();
                    camera.Destroy();
                    RVC_CSharp.System.Shutdown();
                    Console.ReadKey();
                    return;
                }

                PointMap internalCameraPointMap1 = camera.GetPointMap();

                Image internalCameraImage1 = camera.GetImage(CameraID.CameraID_Left);

                byte[] externalCameraImageData1 = null;// Get external image. Needs to be modified.

                pmAddr = $"./{info.name}-{info.sn}/calibration_internal1.ply";
                imgAddr = $"./{info.name}-{info.sn}/calibration_internal1.ply";
                internalCameraPointMap1.SaveColorPointCloud(internalCameraImage1, pmAddr, unit_mm: false);
                internalCameraImage1.SaveImage(imgAddr);

                // Capture Second Point Map
                Console.WriteLine("Put the calibration board at the furthest working distance and take first frame.");
                Console.WriteLine("Press Enter to continue...");
                Console.ReadLine();

                ret = camera.Capture();
                if (!ret)
                {
                    Console.WriteLine($"Failed to capture.Error: {System.GetLastErrorMessage()} ");
                    camera.Close();
                    camera.Destroy();
                    RVC_CSharp.System.Shutdown();
                    Console.ReadKey();
                    return;
                }

                PointMap internalCameraPointMap2 = camera.GetPointMap();

                Image internalCameraImage2 = camera.GetImage(CameraID.CameraID_Left);

                byte[] externalCameraImageData2 = null;// Get external image. Needs to be modified.

                pmAddr = $"./{info.name}-{info.sn}/calibration_internal1.ply";
                imgAddr = $"./{info.name}-{info.sn}/calibration_internal1.ply";
                internalCameraPointMap2.SaveColorPointCloud(internalCameraImage2, pmAddr, unit_mm: false);
                internalCameraImage2.SaveImage(imgAddr);

                // Get External Camera Extrinsic Matrix
                double error;
                int errorCode = GetExternalCameraExtrinsicMatrix(internalCameraImage0.m_handle,
                    internalCameraPointMap0.m_handle,
                    externalCameraImageData0, internalCameraImage1.m_handle, internalCameraPointMap1.m_handle,
                    externalCameraImageData1, internalCameraImage2.m_handle, internalCameraPointMap2.m_handle,
                    externalCameraImageData2, external_camera_image_width, external_camera_image_height,
                    external_camera_intrinsic_matrix, external_camera_camera_distortion,
                    external_camera_extrinsic_matrix, out error);

                if (errorCode != 0)
                {
                    Console.WriteLine($"Get external camera extrinsic matrix failed! Error: {System.GetLastErrorMessage()} ");
                    camera.Close();
                    camera.Destroy();
                    RVC_CSharp.System.Shutdown();
                    Console.WriteLine("Press any key to exit. ");
                    Console.ReadKey();
                    return;
                }

                // print extrinsic matrix and error
                Console.WriteLine("External camera extrinsic matrix:");
                Console.WriteLine(string.Join(", ", external_camera_extrinsic_matrix));
                Console.WriteLine($"Reprojection error(pixel): {error}");
            }
            // Capture three point maps with 4*11 calibration board to get external camera extrinsic matrix.

            #endregion

            #region Step 2 , Capture With External Color Camera

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

            Image image = camera.GetImage(CameraID.CameraID_Left);
            DepthMap depth = camera.GetDepthMap();
            PointMap pointMap = camera.GetPointMap();

            // 2D Image
            string imageFile = $"./{info.name}-{info.sn}/scene_internal.png";
            Console.WriteLine($"Save Image,path = {imageFile}");
            image.SaveImage(imageFile);

            // Point Cloud 
            string pointCloudFile = $"./{info.name}-{info.sn}/scene_internal.ply";
            Console.WriteLine($"Save PointMap,path = {pointCloudFile}");
            pointMap.SaveColorPointCloud(image, pointCloudFile, false);

            PointMap external_camera_point_map = GetExternalCameraPointMap(pointMap.m_handle, external_camera_image_width, external_camera_image_height,
        external_camera_intrinsic_matrix, external_camera_camera_distortion, external_camera_extrinsic_matrix);

            string pointCloudFile2 = $"./{info.name}-{info.sn}/scene_internal.ply";
            external_camera_point_map.Save(pointCloudFile2, PointMapUnit.Meter, true);

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
