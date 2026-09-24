using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using RVC_CSharp;
using static RVC_CSharp.RVC_CSharp_DLL;

namespace RVC_CSharp
{

    class Program
    {
        // Keep the delegate alive to prevent it from being garbage collected
        private static X2FixedLineScanCallBackPtr callbackDelegate;

        /**
         * @brief Callback to handle acquired line scan data.
         *        CRITICAL: This function must be efficient to prevent frame drops. Avoid time-consuming operations.
         *
         * @param line_data Acquired line scan data and metadata
         * @param pUser Pointer to user-defined data structure
         */
        private static void CallbackFunc(X2FixedLineScanCallBackInfo line_data, IntPtr pUser)
        {
            var pointmap = line_data.pointmap;
            var size = pointmap.GetSize();
            var pointCount = size.width * size.height;

            int totalElements = pointCount * 3;
            double[] pointmapData = new double[totalElements];

            IntPtr sourcePtr = pointmap.GetPointDataPtr();
            Marshal.Copy(sourcePtr, pointmapData, 0, totalElements);

 
            Console.WriteLine("pointmap_index:" + line_data.pointmap_index
            + ", timestamp(us):" + line_data.pointmap.GetTimestamp()
            + ", pointmap size:" + line_data.pointmap.GetSize().width + "x" + line_data.pointmap.GetSize().height
            + " ,the first point of the point cloud: "
            + "(" + pointmapData[0] + "," + pointmapData[1] + "," + pointmapData[2] + ")");
            
        }

        static void Main(string[] args)
        {
            // Initialize RVC X system.
            System.Init();

            // Choose RVC Camera type (USB, GigE or All)
            Device[] devices = new Device[10];
            int actual_size = 0;
            System.ListDevices(devices, ref actual_size, 10, SystemListDeviceType.All);

            // Find whether any Camera is connected or not.
            if (actual_size == 0)
            {
                Console.WriteLine("Can not find any Camera!");
                System.Shutdown();
                Console.ReadKey();
                return;
            }

            if (!devices[0].IsFirmwareMatch())
            {
                Console.WriteLine("device firmware mismatch, Please use RVCManager to upgrade the firmware");
                System.Shutdown();
                Console.ReadKey();
                return;
            }

            // Create and open RVC Camera.
            Device device = devices[0];
            X2 x2 = X2.Create(device);
            x2.Open();
            if (!x2.IsOpen())
            {
                Console.WriteLine("RVC X Camera is not opened!");
                X2.Destroy(x2);
                System.Shutdown();
                Console.ReadKey();
                return;
            }

            // Set capture options.
            X2.CaptureOptions cap_opt = X2.CaptureOptions.Default();
            x2.LoadCaptureOptionParameters(ref cap_opt);
            // Set fixed line scan mode.
            cap_opt.capture_mode = CaptureMode.CaptureMode_FixedLineScan;
            // Enable fixed rate trigger mode for fixed line scan.
            cap_opt.trigger_mode = TriggerMode.TriggerMode_FixedRate;

            // Set fixed rate by user (e.g. 100 Hz)
            cap_opt.auto_set_fixed_rate = false;
            cap_opt.fixed_rate = 100;

            callbackDelegate = new X2FixedLineScanCallBackPtr(CallbackFunc);
            X2_SetFixedLineScanCallback(x2.m_handle, callbackDelegate, IntPtr.Zero);

            x2.ResetTimestamp();
            if (!x2.StartFixedLineScan(cap_opt))
            {
                Console.WriteLine("Failed to start fixed line scan!");
                x2.Close();
                X2.Destroy(x2);
                System.Shutdown();
                Console.ReadKey();
                return;
            }

            int sleep_seconds = 10;
            Console.WriteLine($"Start Fixed Rate Line Scan Mode for {sleep_seconds} seconds...");
            Thread.Sleep(TimeSpan.FromSeconds(sleep_seconds));

            x2.StopFixedLineScan();
            Console.WriteLine("Stopped Fixed Rate Line Scan Mode.");

            x2.Close();
            X2.Destroy(x2);
            System.Shutdown();

            Console.ReadKey();
        }
    }
}