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
    // User-defined data structure to hold context for the callback
    class PointMapWithInfo
    {
        public int pointmap_index;
        public int encoder_index;
        public ulong pointmap_timestamp;
        public double[] pointmap_data;  // x,y,z,x,y,z,...
    }

    class UserData
    {
        public List<PointMapWithInfo> pointmaps = new List<PointMapWithInfo>();
    }

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

            // Copy point cloud data from RVC SDK memory to UserData
            // This is necessary because RVC SDK may reuse or free this memory after callback returns
            GCHandle handle = GCHandle.FromIntPtr(pUser);
            var userData = (UserData)handle.Target;
            var pointmap = line_data.pointmap;
            var size = pointmap.GetSize();
            var pointCount = size.width * size.height;

            int totalElements = pointCount * 3;
            double[] pointmapData = new double[totalElements];

            IntPtr sourcePtr = pointmap.GetPointDataPtr();
            Marshal.Copy(sourcePtr, pointmapData, 0, totalElements);

            var pmInfo = new PointMapWithInfo
            {
                pointmap_index = line_data.pointmap_index,
                encoder_index = line_data.encoder_index,
                pointmap_timestamp = pointmap.GetTimestamp(),
                pointmap_data = pointmapData
            };


            userData.pointmaps.Add(pmInfo);
            
        }

        private static PointMap StitchPointMapsByEncoder(List<PointMapWithInfo> pointmaps,
                                                        double[] move_direction,
                                                        double distance_per_trigger)
        {

            if (pointmaps == null || pointmaps.Count == 0)
            {
                Console.WriteLine("No pointmaps to stitch.");
                return new PointMap();
            }

            int pointsPerLine = pointmaps[0].pointmap_data.Length / 3;
            var size = new Size(pointsPerLine, pointmaps.Count);
            // Pass IntPtr.Zero to let the SDK allocate memory managed by the PointMap object
            var stitched_pointmap = PointMap.Create(PointMapType.PointsOnly, size, IntPtr.Zero, true);

            if (!stitched_pointmap.IsValid())
            {
                Console.WriteLine("Failed to create PointMap.");
                return new PointMap();
            }

            IntPtr stitchedDataPtr = stitched_pointmap.GetPointDataPtr();
            int totalElements = size.width * size.height * 3;
            double[] allData = new double[totalElements];

            for (int i = 0; i < pointmaps.Count; i++)
            {
                var pm_info = pointmaps[i];
                int pointmap_index = pm_info.pointmap_index;

                double displacementX = move_direction[0] * distance_per_trigger * pm_info.encoder_index;
                double displacementY = move_direction[1] * distance_per_trigger * pm_info.encoder_index;
                double displacementZ = move_direction[2] * distance_per_trigger * pm_info.encoder_index;

                int rowStart = pointmap_index * stitched_pointmap.GetSize().width * 3;

                for (int j = 0; j < pointsPerLine; j++)
                {
                    int sourceIndex = j * 3;
                    int targetIndex = rowStart + sourceIndex;
                    allData[targetIndex] = pm_info.pointmap_data[sourceIndex] + displacementX;
                    allData[targetIndex + 1] = pm_info.pointmap_data[sourceIndex + 1] + displacementY;
                    allData[targetIndex + 2] = pm_info.pointmap_data[sourceIndex + 2] + displacementZ;
                }
            }
            Marshal.Copy(allData, 0, stitchedDataPtr, totalElements);
            return stitched_pointmap;
        }

        private static int CalculateEncoderIndexMaxGap(List<PointMapWithInfo> pointmaps)
        {

            if (pointmaps == null || pointmaps.Count < 2)
            {
                return 0;
            }

            pointmaps.Sort((a, b) => a.encoder_index.CompareTo(b.encoder_index));

            int maxInterval = int.MinValue;

            for (int i = 1; i < pointmaps.Count; i++)
            {
                int interval = pointmaps[i].encoder_index - pointmaps[i - 1].encoder_index;
                if (interval > maxInterval) maxInterval = interval;
            }

            return maxInterval;
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
            UserData userdata = new UserData();
            GCHandle handle = GCHandle.Alloc(userdata);
            IntPtr userDataPtr = GCHandle.ToIntPtr(handle);

            callbackDelegate = new X2FixedLineScanCallBackPtr(CallbackFunc);
            X2_SetFixedLineScanCallback(x2.m_handle, callbackDelegate, userDataPtr);

            // Start monitoring for trigger signals.The fixed line scan mode should be initiated before the hardware signals begin and terminated after they cease.
            if (!x2.StartFixedLineScan(cap_opt))
            {
                Console.WriteLine("Failed to start fixed line scan!");
                x2.Close();
                X2.Destroy(x2);
                System.Shutdown();
                handle.Free();
                Console.ReadKey();
                return;
            }

            Console.WriteLine("Start monitoring for trigger signals...");

            // Simulate monitoring for trigger signals for 10 seconds.
            Thread.Sleep(TimeSpan.FromSeconds(10));

            // Stop monitoring
            x2.StopFixedLineScan();
            Console.WriteLine($"Capture finished! Number of captured lines: {userdata.pointmaps.Count}");


            // Stitch pointmaps based on encoder index
            double[] move_direction = new double[] { 0, 1, 0 };
            double distance_per_pulse = 0.1 * 0.001;                                          // unit: m/pulse
            double distance_per_trigger = distance_per_pulse * cap_opt.encoder_trigger_interval; // unit: m/trigger
            PointMap stitched_pointmap = StitchPointMapsByEncoder(userdata.pointmaps, move_direction, distance_per_trigger);
            if (stitched_pointmap.IsValid())
            {
                string save_directory = "./Data/";
                Directory.CreateDirectory(save_directory);
                string pm_addr = save_directory + "test.ply";
                Console.WriteLine($"Save point map to file: {pm_addr}");
                stitched_pointmap.Save(pm_addr, PointMapUnit.Meter, true);
                PointMap.Destroy(stitched_pointmap);
            }
            int max_encoder_index_gap = CalculateEncoderIndexMaxGap(userdata.pointmaps);
            Console.WriteLine($"max encoder index gap: {max_encoder_index_gap}");
            if (max_encoder_index_gap > 1)
            {
                Console.WriteLine($"Trigger frequency is too high. Please reduce the trigger frequency, or increase the encoder_trigger_interval");
            }

            // Close RVC X Camera.
            x2.Close();

            // Destroy RVC X Camera.
            X2.Destroy(x2);

            // Shutdown RVC X System.
            System.Shutdown();

            handle.Free();

            Console.ReadKey();
        }
    }
}
