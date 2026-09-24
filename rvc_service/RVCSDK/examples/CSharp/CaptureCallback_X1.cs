using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using System.Threading;
using RVC_CSharp;
using static RVC_CSharp.RVC_CSharp_DLL;

namespace RVC_CSharp
{
    class Program
    {
        public static void X1CollectionCallBack(X1CollectionCallBackInfo info, X1.CaptureOptions options, IntPtr p)
        {
            info.image.SaveImage("D:/collection.png");
            return;
        }

        public static void X1CalculationCallBack(X1CalculationCallBackInfo info, X1.CaptureOptions options, IntPtr p)
        {
            info.depthmap.SaveDepthMap("D:/calculation.tiff");
            info.pointmap.SavePlyBinary("D:/calculation.ply");
            info.image.SaveImage("D:/calculation.png");
            return;
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

            #endregion

            #region Step 1 , Find Device

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
            bool success = X1_SetCollectionCallBack(camera.m_handle, X1CollectionCallBack, IntPtr.Zero);
            bool success2 = X1_SetCalculationCallBack(camera.m_handle, X1CalculationCallBack, IntPtr.Zero);
            if (false == success || false == success2)
            {
                Console.WriteLine($"Failed to set callback .Error: {System.GetLastErrorMessage()} ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

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

    }
}
