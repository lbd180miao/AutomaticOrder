/**
 * This program illustrates the process of transforming a depth map into a point cloud.
 *
 * Important: When the capture mode is set to `CaptureMode_SwingLineScan` and `correspond2d` is disabled (set to false),
 * the retrieval of a depth map is not feasible. If you require a depth map in the swinglinescan mode, you should enable
 * `correspond2d` (set it to true). However, be advised that enabling `correspond2d` will adjust the original point
 * cloud data. Moreover, while the original point cloud computation uses the sub-pixel center of the laser line, the
 * conversion from depth map to point cloud operates on integer-level pixels, which can lead to minor inaccuracies,with
 * a maximum error not exceeding the point spacing.
 */
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Runtime.InteropServices;
using OpenCvSharp;
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

            X1.CaptureOptions options = new X1.CaptureOptions();
            camera.LoadCaptureOptionParameters(ref options);

            // We need camera coordinate system data to perform the correct conversion
            options.transform_to_camera = true;
            X1.CustomTransformOptions custom_trans_opt = X1.CustomTransformOptions.Default();
            custom_trans_opt.coordinate_select = X1.CustomTransformOptions.CoordinateSelect.CoordinateSelect_Disabled;
            bool ret = camera.SetCustomTransformation(custom_trans_opt);
            if (false == ret)
            {
                Console.WriteLine($"Failed to SetCustomTransformation .Error: {System.GetLastErrorMessage()} ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                return;
            }

            ret = camera.Capture(options);

            if (false == ret)
            {
                Console.WriteLine($"Failed to Capture .Error: {System.GetLastErrorMessage()} ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                return;
            }

            Image image = camera.GetImage();
            DepthMap depth = camera.GetDepthMap();
            PointMap pointMap = camera.GetPointMap();

            #endregion

            #region Step 4 , Convert depth map to point map and compare

            float[] intrinsic_matrix = new float[9];
            float[] distortion = new float[5];

            ret = camera.GetIntrinsicParameters(intrinsic_matrix, distortion);
            if (false == ret)
            {
                Console.WriteLine($"Failed to GetIntrinsicParameters .Error: {System.GetLastErrorMessage()} ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                return;
            }

            PointMap convertPm = ConvertDepthMapToPointMap(depth, intrinsic_matrix, distortion, options.roi);
            bool rtf = IsPointMapEqual(pointMap, convertPm, out double maxDiff, 1.0e-6);
            Console.WriteLine($"Pointmap is {(rtf ? "Equal" : "Not Equal")}, Max_diff (mm): {maxDiff * 1000:F4}");

            #endregion

            #region Step 5 , Data Process

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

            // Color Convert Point Cloud
            colorPointCloudFile = $"./{info.name}-{info.sn}/ColorPointCloud_Con.ply";
            Console.WriteLine($"Save Color-Convert-PointMap,path = {colorPointCloudFile}");
            convertPm.SaveColorPointCloud(image, colorPointCloudFile);

            Console.WriteLine("Successfully Process Data .");

            #endregion

            #region Step 6 , Close And Release Device

            camera.Close();
            camera.Destroy();

            RVC_CSharp.System.Shutdown();
            Console.WriteLine("System close.");

            Console.ReadKey();
            #endregion

            return;
        }

        private static PointMap ConvertDepthMapToPointMap(DepthMap depth, float[] intrinsic_matrix, float[] distortion, ROI roi)
        {
            // Get Depth Size
            Size sz = depth.GetSize();
            int width = sz.width, height = sz.height, imageSize = width * height;

            Point2f[] pts = new Point2f[imageSize];
            for (int r = roi.y, idx = 0; r < roi.y + height; r++)
            {
                for (int c = roi.x; c < roi.x + width; c++, idx++)
                {
                    pts[idx] = new Point2f(c, r);
                }
            }

            float[] distortionCv = { distortion[0], distortion[1], distortion[3], distortion[4], distortion[2] };

            using (Mat intrinsicMat = new Mat(3, 3, MatType.CV_32FC1, intrinsic_matrix))
            using (Mat distortionMat = new Mat(1, 5, MatType.CV_32FC1, distortionCv))
            {
                Mat undistortedPtsMat = new Mat();
                Cv2.UndistortPoints(InputArray.Create(pts), undistortedPtsMat, intrinsicMat, distortionMat);

                IntPtr zPtr = depth.GetDataPtr();
                int bufferSize = imageSize * 3 * sizeof(double);
                IntPtr pointDataPtr = Marshal.AllocHGlobal(bufferSize);
                unsafe
                {
                    double* z = (double*)zPtr.ToPointer();
                    Point2f* undistortedPts = (Point2f*)undistortedPtsMat.Data.ToPointer();
                    double* pmData = (double*)pointDataPtr.ToPointer();

                    for (int i = 0; i < imageSize; i++)
                    {
                        pmData[i * 3] = undistortedPts[i].X * z[i]; // X
                        pmData[i * 3 + 1] = undistortedPts[i].Y * z[i]; // Y
                        pmData[i * 3 + 2] = z[i]; // Z
                    }
                }
                return PointMap.Create(PointMapType.PointsOnly, sz, pointDataPtr, true);
            }
        }

        private static bool IsPointMapEqual(PointMap pm0, PointMap pm1,
                                      out double maxDiff, double tol = 1e-6)
        {
            maxDiff = -1;

            var size0 = pm0.GetSize();
            var size1 = pm1.GetSize();
            if (size0.width != size1.width || size0.height != size1.height)
            {
                return false;
            }

            int dataSize = size0.width * size0.height * 3;
            if (dataSize == 0)
            {
                maxDiff = 0;
                return true;
            }

            IntPtr dataPtr0 = pm0.GetPointDataPtr();
            IntPtr dataPtr1 = pm1.GetPointDataPtr();

            if (dataPtr0 == IntPtr.Zero || dataPtr1 == IntPtr.Zero)
            {
                throw new ArgumentException("Invalid PointMap data pointer");
            }

            maxDiff = 0;
            bool validityConsistent = true;

            unsafe
            {
                double* data0 = (double*)dataPtr0;
                double* data1 = (double*)dataPtr1;

                for (int i = 0; i < dataSize; i++)
                {
                    bool valid0 = !double.IsNaN(data0[i]);
                    bool valid1 = !double.IsNaN(data1[i]);

                    if (valid0 != valid1)
                    {
                        validityConsistent = false;
                    }

                    if (valid0 && valid1)
                    {
                        double diff = Math.Abs(data0[i] - data1[i]);
                        if (diff > maxDiff)
                        {
                            maxDiff = diff;
                        }
                    }
                }
            }

            return validityConsistent && maxDiff < tol;
        }

    }
}
