using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Threading;
using System.Runtime.InteropServices;
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
                + ", encoder_index:" + line_data.encoder_index
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
            // Create a RVC X Camera and choose use left side camera.
            X2 x2 = X2.Create(device);
            // Open RVC X Camera.
            x2.Open();
            // Test RVC X Camera is opened or not.
            if (!x2.IsOpen())
            {
                Console.WriteLine("RVC X Camera is not opened!");
                X2.Destroy(x2);
                System.Shutdown();
                Console.ReadKey();
                return;
            }

            // optional 
            // Print Device Info
            DeviceInfo info = new DeviceInfo();
            device.GetDeviceInfo(ref info);
            info.Print();
            if (!info.support_hardware_trigger)
            {
                Console.WriteLine("The camera does not support hardware trigger mode!");
                x2.Close();
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
            // Enable hard trigger mode for fixed line scan.
            cap_opt.trigger_mode = TriggerMode.TriggerMode_HardWare;
            /**
             * Set number of encoder pulses required to trigger one profile acquisition
             *
             * The setting of ‘encoder_trigger_interval’ requires comprehensive consideration of the following factors:
             * 1. Actual movement distance per encoder pulse D (unit: mm);
             * 2. Camera's maximum trigger frame rate FPS (unit: frames/second);
             * 3. Guide rail movement speed V (unit: mm/s);
             * 4. Required line spacing (unit: mm).
             *
             * Example:
             * Given:
             * - Distance per encoder pulse D = 0.1 mm
             * - Maximum camera trigger frame rate = 300 FPS
             * - Guide rail movement speed V = 400 mm/s
             *
             * Calculation:
             * - Encoder pulse frequency F = V / D = 4000 Hz
             * - Minimum encoder trigger interval = F / FPS = 4000 / 300 ≈ 14 pulses
             *   (meaning: trigger camera acquisition every 14 encoder pulses)
             * - Resulting line spacing = D × trigger interval = 0.1 mm × 14 = 1.4 mm
             */
            cap_opt.encoder_trigger_interval = 14;

            callbackDelegate = new X2FixedLineScanCallBackPtr(CallbackFunc);
            X2_SetFixedLineScanCallback(x2.m_handle, callbackDelegate, IntPtr.Zero);

            // Start monitoring for trigger signals.The fixed line scan mode should be initiated before the hardware signals begin and terminated after they cease.
            if (!x2.StartFixedLineScan(cap_opt))
            {
                Console.WriteLine("Failed to start fixed line scan!");
                x2.Close();
                X2.Destroy(x2);
                System.Shutdown();
                Console.ReadKey();
                return;
            }

            Console.WriteLine("Start monitoring for trigger signals...");

            // Simulate monitoring for trigger signals for 10 seconds.
            Thread.Sleep(TimeSpan.FromSeconds(10));

            // Stop monitoring
            x2.StopFixedLineScan();
            Console.WriteLine("Stopped monitoring for trigger signals.");

            // Close RVC X Camera.
            x2.Close();

            // Destroy RVC X Camera.
            X2.Destroy(x2);

            // Shutdown RVC X System.
            System.Shutdown();

            Console.ReadKey();
        }
    }
}
