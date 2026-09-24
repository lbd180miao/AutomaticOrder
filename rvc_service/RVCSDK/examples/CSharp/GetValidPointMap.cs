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
        static List<double> ExtractValidPoint(PointMap pm)
        {
            int pmSize = pm.GetSize().width * pm.GetSize().height;
            List<double> validXyzs = new List<double>(pmSize * 3);

            IntPtr pmDataPtr = pm.GetPointDataPtr();
            int stride = Marshal.SizeOf<double>() * 3;

            for (int i = 0; i < pmSize; i++)
            {
                double[] point = new double[3];
                Marshal.Copy(pmDataPtr + i * stride, point, 0, 3);

                if (!double.IsNaN(point[2]))
                {
                    validXyzs.AddRange(point);
                }
            }

            return validXyzs;
        }
        private static void SavePlyFile(string path, double[] data, int pointCount)
        {
            using (var writer = new StreamWriter(path))
            {
                writer.WriteLine("ply");
                writer.WriteLine("format ascii 1.0");
                writer.WriteLine($"element vertex {pointCount}");
                writer.WriteLine("property float x");
                writer.WriteLine("property float y");
                writer.WriteLine("property float z");
                writer.WriteLine("end_header");

                for (int i = 0; i < data.Length; i += 3)
                {
                    writer.WriteLine($"{data[i]} {data[i + 1]} {data[i + 2]}");
                }
            }
        }
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
            
            ret = camera.Capture();

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
            List<double> validXyzs = ExtractValidPoint(pointMap);

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

            // Valid Point Cloud
            string vaildPointCloudFile = $"./{info.name}-{info.sn}/VaildPointCloud.ply";
            Console.WriteLine($"Save Vaild-PointMap,path = {vaildPointCloudFile}");
            SavePlyFile(vaildPointCloudFile, validXyzs.ToArray(), validXyzs.Count / 3);

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
