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

            int img_w = image.GetSize().width;
            int img_h = image.GetSize().height;
            bool is_color = image.GetType() == ImageType.Mono8 ? false : true;

            unsafe
            {
                byte* img_data_ptr = (byte*)image.GetDataPtr().ToPointer();
                double* xyz_ptr = (double*)pointMap.GetPointDataPtr().ToPointer();

                for (int r = 0; r < img_h; r += 10)
                {
                    for (int c = 0; c < img_w; c += 10)
                    {
                        int point_index = (r * img_w + c) * 3;
                        double x = xyz_ptr[point_index];
                        double y = xyz_ptr[point_index + 1];
                        double z = xyz_ptr[point_index + 2];

                        if (is_color) 
                        {
                            
                            int pixel_index = (r * img_w + c) * 3;
                            byte red = img_data_ptr[pixel_index];
                            byte green = img_data_ptr[pixel_index + 1];
                            byte blue = img_data_ptr[pixel_index + 2];

                            if (!double.IsNaN(z))
                            {
                                Console.WriteLine(
    "image position(xy): ({0}, {1}) color: ({2}, {3}, {4}), correspondence xyz: ({5:F6}, {6:F6}, {7:F6})",
    c, r, red, green, blue, x, y, z);
                            }

                        }
                        else 
                        {
                            int pixel_index = r * img_w + c;
                            byte gray = img_data_ptr[pixel_index];

                            if (!double.IsNaN(z))
                            {
                                Console.WriteLine(
                                "image position(xy): ({0}, {1}) density: {2}, correspondence xyz: ({3:F6}, {4:F6}, {5:F6})",
                                c, r, gray, x, y, z);
                            }

                        }
                    }
                }
            }

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
