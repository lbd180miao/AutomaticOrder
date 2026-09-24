using RVC_CSharp;
using RVC_CSharp.Utils;
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
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

        private static PointMap StitchPointMapsByTimestamp(List<PointMapWithInfo> pointmaps,
                                                        double[] move_direction,
                                                        double move_speed)
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

                double time_offset_s = pm_info.pointmap_timestamp / 1e6;  // Convert microseconds to seconds
                double displacementX = move_direction[0] * move_speed * time_offset_s;
                double displacementY = move_direction[1] * move_speed * time_offset_s;
                double displacementZ = move_direction[2] * move_speed * time_offset_s;

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

        private static void CalculateTimestampIntervals(
           List<PointMapWithInfo> pointmaps,
           out double minIntervalMs,
           out double maxIntervalMs)
        {
            minIntervalMs = 0;
            maxIntervalMs = 0;

            if (pointmaps == null || pointmaps.Count < 2)
            {
                return;
            }

            pointmaps.Sort((a, b) => a.pointmap_index.CompareTo(b.pointmap_index));

            double minInterval = double.MaxValue;
            double maxInterval = double.MinValue;

            for (int i = 1; i < pointmaps.Count; i++)
            {
                double interval = pointmaps[i].pointmap_timestamp - pointmaps[i - 1].pointmap_timestamp;

                if (interval < minInterval) minInterval = interval;
                if (interval > maxInterval) maxInterval = interval;
            }

            minIntervalMs = minInterval * 0.001;
            maxIntervalMs = maxInterval * 0.001;
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

            UserData userdata = new UserData();
            GCHandle handle = GCHandle.Alloc(userdata);
            IntPtr userDataPtr = GCHandle.ToIntPtr(handle);

            callbackDelegate = new X2FixedLineScanCallBackPtr(CallbackFunc);
            X2_SetFixedLineScanCallback(x2.m_handle, callbackDelegate, userDataPtr);

            x2.ResetTimestamp();
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

            int sleep_seconds = 10;
            Console.WriteLine($"Start Fixed Rate Line Scan Mode for {sleep_seconds} seconds...");
            Thread.Sleep(TimeSpan.FromSeconds(sleep_seconds));

            x2.StopFixedLineScan();
            Console.WriteLine("Stopped Fixed Rate Line Scan Mode.");
            Console.WriteLine($"Total PointMaps acquired: {userdata.pointmaps.Count}");

            // Stitch pointmaps based on timestamps
            double[] move_direction = new double[] { 0, 1, 0 };
            double move_speed = 0.1;  // unit: m/s
            PointMap stitched_pointmap = StitchPointMapsByTimestamp(userdata.pointmaps, move_direction, move_speed);
            if (stitched_pointmap.IsValid())
            {
                string save_directory = "./Data/";
                Directory.CreateDirectory(save_directory);
                string pm_addr = save_directory + "test.ply";
                Console.WriteLine($"Save point map to file: {pm_addr}");
                stitched_pointmap.Save(pm_addr, PointMapUnit.Meter, true);
                PointMap.Destroy(stitched_pointmap);
            }

            CalculateTimestampIntervals(userdata.pointmaps, out double min_interval_ms, out double max_interval_ms);
            Console.WriteLine($"min timestamp interval: {min_interval_ms:F2} ms , max timestamp interval: {max_interval_ms:F2} ms");
            if (max_interval_ms - min_interval_ms > 0.5) {
                if (cap_opt.auto_set_fixed_rate)
                {
                    Console.WriteLine($"Frame drop! Auto Set frame rate is too high.");
                }
                else
                {
                    Console.WriteLine($"Frame drop! Frame rate: {cap_opt.fixed_rate} ,is too high.");
                }
            }

            x2.Close();
            X2.Destroy(x2);
            System.Shutdown();
            handle.Free();

            Console.ReadKey();
        }
    }
}