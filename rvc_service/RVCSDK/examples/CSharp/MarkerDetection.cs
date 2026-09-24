using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;
using OpenCvSharp;

using static RVC_CSharp.MarkerDetection;
using System.Windows.Forms;
using System.ComponentModel;

namespace RVC_CSharp
{
    class Program
    {
        static void CodedCircleMarkerDetectOnline()
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
            DeviceInfo info = new DeviceInfo();
            device.GetDeviceInfo(ref info);
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
            #endregion

            #region Step 4 , Marker Detection

            CodedCircleMarkerType type; // Need to be changed according to the actual type
            type.N = 15;
            type.r1_to_r0_ratio = 4.0 / 1.5;
            type.r2_to_r0_ratio = 6.0 / 1.5;
            List<CodedCircleMarker> markers = DetectCodedCircleMarker(image.m_handle, type);

            Mat cvImage = image.ToMat();
            if (cvImage.Empty())
            {
                Console.WriteLine("cvImage is empty.");
                RVC_CSharp.System.Shutdown();
                Console.WriteLine("System close.");
                Console.ReadKey();
            }
            if (cvImage.Channels() == 1)
            {
                Cv2.CvtColor(cvImage, cvImage, ColorConversionCodes.GRAY2BGR);
            }

            if (markers.Count == 0)
            {
                Console.WriteLine("No marker detected.");
            }
            else
            {
                Console.WriteLine("Detected markers:");
                foreach (CodedCircleMarker marker in markers)
                {
                    Cv2.Circle(cvImage, new Point(marker.x, marker.y), 0, new Scalar(0, 0, 255), 1);
                    Cv2.PutText(cvImage, marker.code.ToString(), new Point(marker.x, marker.y),
                        HersheyFonts.HersheySimplex, 0.5, new Scalar(0, 0, 255), 1);
                    Console.WriteLine($"code: {marker.code}, Center: ({marker.x}, {marker.y})");
                }
            }
            Cv2.NamedWindow("image");
            Cv2.MoveWindow("image", 50, 25);
            int newHeight = 900;
            int newWidth = (int)((double)cvImage.Cols / cvImage.Rows * newHeight);
            Cv2.Resize(cvImage, cvImage, new OpenCvSharp.Size(newWidth, newHeight));
            Cv2.ImShow("image", cvImage);
            Cv2.WaitKey(0);

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

        static void CodedCircleMarkerDetectOffline(string folder, string imageName)
        {
            var imagePath = Path.Combine(folder, imageName);
            Image image = Image.CreateFromFile(imagePath);
            if (image.IsValid() == false)
            {
                Console.WriteLine("Failed to load image.");
                Console.ReadKey();
                return;
            }
            CodedCircleMarkerType type; // Need to be changed according to the actual type
            type.N = 15;
            type.r1_to_r0_ratio = 4.0 / 1.5;
            type.r2_to_r0_ratio = 6.0 / 1.5;
            List<CodedCircleMarker> markers = DetectCodedCircleMarker(image.m_handle, type);
            Mat cvImage = image.ToMat();
            if (cvImage.Empty())
            {
                Console.WriteLine("cvImage is empty.");
                RVC_CSharp.System.Shutdown();
                Console.WriteLine("System close.");
                Console.ReadKey();
            }
            if (cvImage.Channels() == 1)
            {
                Cv2.CvtColor(cvImage, cvImage, ColorConversionCodes.GRAY2BGR);
            }

            if (markers.Count == 0)
            {
                Console.WriteLine("No marker detected.");
            }
            else
            {
                Console.WriteLine("Detected markers:");
                foreach (CodedCircleMarker marker in markers)
                {
                    Cv2.Circle(cvImage, new Point(marker.x, marker.y), 0, new Scalar(0, 0, 255), 1);
                    Cv2.PutText(cvImage, marker.code.ToString(), new Point(marker.x, marker.y),
                        HersheyFonts.HersheySimplex, 0.5, new Scalar(0, 0, 255), 1);
                    Console.WriteLine($"code: {marker.code}, Center: ({marker.x}, {marker.y})");
                }
            }
            Cv2.NamedWindow("image");
            Cv2.MoveWindow("image", 50, 25);
            int newHeight = 900;
            int newWidth = (int)((double)cvImage.Cols / cvImage.Rows * newHeight);
            Cv2.Resize(cvImage, cvImage, new OpenCvSharp.Size(newWidth, newHeight));
            Cv2.ImShow("image", cvImage);
            Cv2.WaitKey(0);

            // If use CreateFromFile(), you should call Destroy() to release the resource to RVC system.
            Image.Destroy(image);
        }

        public static void ConcentricCircleMarkerDetectOffline(string folder, string imageName, string pointmapName)
        {
            var imagePath = Path.Combine(folder, imageName);
            var pointMapPath = Path.Combine(folder, pointmapName);

            var image = Image.CreateFromFile(imagePath);
            var pointMap = PointMap.CreateFromFile(pointMapPath, image.GetSize(), PointMapUnit.Meter);

            Console.WriteLine("only detect pixel 2d");
            {
                List<double> pixelXY = null!;
                int errorCode = DetectConcentricCircleMarker2d(image.m_handle, ref pixelXY);
                if (errorCode == 0)
                {
                    // pixelXY 长度固定为 2000，按 2 个一组取前 markerNum*2 个值
                    int markerNum = pixelXY.Count / 2;
                    Console.WriteLine($"2D marker num: {markerNum}");
                    for (int i = 0; i < markerNum; i++)
                        Console.WriteLine($"Marker {i}: ({pixelXY[2 * i]}, {pixelXY[2 * i + 1]})");
                }
                else
                {
                    Console.WriteLine($"DetectConcentricCircleMarker2d failed, error code = {errorCode}");
                }
            }
            Console.WriteLine();

            Console.WriteLine("detect pixel 2d and point 3d");
            {
                List<double> pixelXY = null!;
                List<double> pointXYZ = null!;
                int errorCode = DetectConcentricCircleMarker3d(image.m_handle, pointMap.m_handle, ref pixelXY, ref pointXYZ);
                if (errorCode == 0)
                {
                    // pixelXY 长度固定 2000，pointXYZ 长度固定 3000，按 2/3 个一组读取
                    int markerNum = pointXYZ.Count / 3;
                    Console.WriteLine($"3D marker num: {markerNum}");
                    for (int i = 0; i < markerNum; i++)
                    {
                        Console.WriteLine(
                            $"Marker {i}: ({pixelXY[2 * i]}, {pixelXY[2 * i + 1]}), " +
                            $"({pointXYZ[3 * i]}, {pointXYZ[3 * i + 1]}, {pointXYZ[3 * i + 2]})");
                    }
                }
                else
                {
                    Console.WriteLine($"DetectConcentricCircleMarker3d failed, error code = {errorCode}");
                }
            }

            Image.Destroy(image);
            PointMap.Destroy(pointMap);
        }

        static void Main()
        {
            int exampleType = 2;
            if (exampleType == 0)
            {
                CodedCircleMarkerDetectOffline("D:/", "0.png");
            }else if(exampleType == 1)
            {
                CodedCircleMarkerDetectOnline();
            }
            else if (exampleType == 2)
            {
                ConcentricCircleMarkerDetectOffline("D:/", "0.png", "0.ply");
            }
            return;
        }

    }
}
