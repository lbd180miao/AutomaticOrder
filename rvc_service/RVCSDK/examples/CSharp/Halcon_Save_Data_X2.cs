using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
#if Halcon_Enable
using HalconDotNet;
#endif
using RVC_CSharp;
using static RVC_CSharp.Halcon_Extension;

namespace RVC_CSharp
{
    class Program
    {
        static HObject GetChannelImage(double[] imageArray, int width, int height, NullValueConvertMethod method = NullValueConvertMethod.KeepNull, double value = 0.0, double scale = 1)
        {
            int size = width * height;
            double min = double.MaxValue;
            double max = double.MinValue;

            if (method == NullValueConvertMethod.ToMinimum)
            {
                for (int i = 0; i < imageArray.Length; i++)
                {
                    double imageValue = imageArray[i];
                    if (double.IsNaN(imageValue))
                        continue;
                    if (imageValue > max)
                        max = imageValue;
                    if (imageValue < min)
                        min = imageValue;
                }
            }

            double k = scale;

            float[] imageData = new float[size];
            for (int i = 0; i < size; i++)
            {
                if (double.IsNaN(imageArray[i]))
                {
                    if (method == NullValueConvertMethod.KeepNull)
                    {
                        imageData[i] = (float)(imageArray[i] * k);
                    }
                    else if (method == NullValueConvertMethod.ToZero)
                    {
                        imageData[i] = 0;
                    }
                    else if (method == NullValueConvertMethod.ToMinimum)
                    {
                        imageData[i] = (float)min;
                    }
                    else if (method == NullValueConvertMethod.ToGivenValue)
                    {
                        imageData[i] = (float)value;
                    }
                    else
                    {
                        imageData[i] = (float)(imageArray[i] * k);
                    }
                }
                else
                {
                    imageData[i] = (float)(imageArray[i] * k);
                }
            }

            IntPtr pImage = Marshal.AllocHGlobal(size * sizeof(float));
            Marshal.Copy(imageData, 0, pImage, size);
            HOperatorSet.GenImage1(out HObject HImg, "real", width, height, pImage);
            Marshal.FreeHGlobal(pImage);
            return HImg;
        }
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
            if(device.IsFirmwareMatch() == false)
            {
                Console.WriteLine("Device firmware mismatch. Please use RVCManager to upgrade the firmware");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }
            #endregion

            #region Step 2 , Open Camera

            X2 camera = RVC_CSharp.X2.Create(device);
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
                Console.WriteLine($"Failed to Capture .Error: { System.GetLastErrorMessage() } ");
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


#if Halcon_Enable
            // HalconExtension,需要Lincese才能运行  
            try
            {
                HObject halconImage = image.ToHalcon();
                HObject halconDepth = depth.ToHalcon();
                HTuple halconPointCloud = pointMap.ToHalcon();

                //Save Halcon Ply
                HOperatorSet.WriteObjectModel3d(halconPointCloud, "ply_binary", $"./{info.name}-{info.sn}/HalconPointCloud.ply", new HTuple(), new HTuple());

                //Save Halcon XYZ_Map
                HObject imageX, imageY, imageZ, mutiChannelImage;
                double scale = 1;
                Size sz = pointMap.GetSize();
                if (pointMap.GetPointMapSeperated(out double[] xs, out double[] ys, out double[] zs, scale))
                {
                    imageX = GetChannelImage(xs, sz.width, sz.height, NullValueConvertMethod.KeepNull, scale);
                    imageY = GetChannelImage(ys, sz.width, sz.height, NullValueConvertMethod.KeepNull, scale);
                    imageZ = GetChannelImage(zs, sz.width, sz.height, NullValueConvertMethod.KeepNull, scale);
                    HOperatorSet.Compose3(imageX, imageY, imageZ, out mutiChannelImage);

                    Console.WriteLine("Compose 3 Chnannel Image");
                    HOperatorSet.WriteImage(mutiChannelImage, "tiff", 0, "outpu.tiff");
                }
                else
                {
                    Console.WriteLine("Compose 3 Chnannel Image Failed");
                }



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
