/**
 * Important:
 * When the capture mode is set to `CaptureMode_SwingLineScan`,
 * `correspond2d` MUST be enabled (set to true), and
 * the option "capture 2D image during 3D acquisition" must also be enabled.
 * Otherwise, the sample will fail.
 *
 * 注意：
 * 使用摆动线扫 (SwingLineScan) 执行示例时，必须同时开启：
 *   1. 2D 对齐（correspond2d = true）
 *   2. 在 3D 采集中拍摄 2D 图选项
 * 否则示例会执行失败。
 */

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;


namespace RVC_CSharp
{

    class Program
    {
        static void Main(string[] args)
        {
            //CompensateForX2Extra();
            CompensateForX2();
            //CompensateForX1();
            Console.ReadKey();

        }

        static void MakeDirectories(string path)
        {
            if (!Directory.Exists(path))
                Directory.CreateDirectory(path);
        }

        #region X2Extra Implementation
        class CameraHelperX2Extra : IDisposable
        {
            private X2 m_x2;
            private X2.CaptureOptions m_opts;

            public CameraHelperX2Extra()
            {
                System.Init();
            }

            public bool Open()
            {
                // List Devices
                var devices = System.ListDevices();
                if (devices.Count == 0) return false;
                if(devices[0].IsFirmwareMatch() == false)
                {
                    Console.WriteLine("Device firmware mismatch. Please use RVCManager to upgrade the firmware");
                    RVC_CSharp.System.Shutdown();
                    Console.ReadKey();
                    return false;
                }
                // Create and open camera
                m_x2 = X2.Create(devices[0]);
                if (!m_x2.Open()) return false;

                // Load capture options
                if (!m_x2.LoadCaptureOptionParameters(ref m_opts)) return false;

                // Configure transform
                m_opts.transform_to_camera = CameraID.CameraID_Extra;
                var customTransformOpt = X2.CustomTransformOptions.Default();
                return m_x2.SetCustomTransformation(customTransformOpt);
            }

            public void Capture(out PointMap pointMap, out Image image)
            {
                if (!m_x2.Capture(m_opts))
                {
                    Console.WriteLine($"Failed to Capture .Error: {System.GetLastErrorMessage()} ");
                    RVC_CSharp.System.Shutdown();
                    Console.ReadKey();
                }

                pointMap = m_x2.GetPointMap();
                image = m_x2.GetImage(CameraID.CameraID_Extra);

            }

            public void Dispose()
            {
                if (m_x2.IsOpen()) m_x2.Close();
                if (m_x2.IsValid()) X2.Destroy(m_x2);
                System.Shutdown();
            }
        }

        static void CompensateForX2Extra()
        {
            using var camera = new CameraHelperX2Extra();
            if (!camera.Open())
            {
                Console.WriteLine("RVC X2 Camera fails to open!");
                Console.ReadKey();
                return;
            }

            using var compensator = new Compensator();

            // 1. Initialize
            camera.Capture(out PointMap pm, out Image image);

            try
            {
                compensator.Initialize(pm, image, CompensatorMarkerType.MarkerType_CalibrationBoard);
                Console.WriteLine("Initialize successfully!");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Initialize failed: {ex.Message}");
                Console.ReadKey();
                return;
            }

            // 2. Update
            var dir = Path.Combine(Environment.CurrentDirectory, "Data");
            MakeDirectories(dir);

            int interval = 10;
            for (int i = 0; i < interval; i++)
            {
                camera.Capture(out PointMap tmpPm, out Image tmpImg); // Skip frames
            }

            camera.Capture(out PointMap updatePm, out Image updateImg);

            try
            {
                var drift = compensator.Update(updatePm, updateImg);
                Console.WriteLine($"Drift distance: {drift:F4}m\nUpdate success!");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Update failed: {ex.Message}");
                Console.ReadKey();
                return;
            }

            // 3. Apply
            camera.Capture(out PointMap finalPm, out Image finalImg);
            finalPm.Save(Path.Combine(dir, "before_compensate.ply"), PointMapUnit.Millimeter, true, finalImg);
            compensator.Apply(finalPm);
            finalPm.Save(Path.Combine(dir, "after_compensate.ply"), PointMapUnit.Millimeter, true, finalImg);
        }
        #endregion

        #region X2 Implementation
        class CameraHelperX2 : IDisposable
        {
            private X2 m_x2;
            private X2.CaptureOptions m_opts;

            public CameraHelperX2()
            {
                System.Init();
            }

            public bool Open()
            {
                // List Devices
                var devices = System.ListDevices();
                if (devices.Count == 0) return false;
                if(devices[0].IsFirmwareMatch() == false)
                {
                    Console.WriteLine("Device firmware mismatch. Please use RVCManager to upgrade the firmware");
                    RVC_CSharp.System.Shutdown();
                    Console.ReadKey();
                    return false;
                }
                // Create and open camera
                m_x2 = X2.Create(devices[0]);
                if (!m_x2.Open()) return false;

                // Load capture options
                if (!m_x2.LoadCaptureOptionParameters(ref m_opts)) return false;

                // Configure transform
                m_opts.transform_to_camera = CameraID.CameraID_Left;
                var customTransformOpt = X2.CustomTransformOptions.Default();
                return m_x2.SetCustomTransformation(customTransformOpt);
            }

            public void Capture(out PointMap pointMap, out Image image)
            {
                if (!m_x2.Capture(m_opts))
                {
                    Console.WriteLine($"Failed to Capture .Error: {System.GetLastErrorMessage()} ");
                    RVC_CSharp.System.Shutdown();
                    Console.ReadKey();
                }

                pointMap = m_x2.GetPointMap();
                image = m_x2.GetImage(CameraID.CameraID_Left);

            }

            public void Dispose()
            {
                if (m_x2.IsOpen()) m_x2.Close();
                if (m_x2.IsValid()) X2.Destroy(m_x2);
                System.Shutdown();
            }
        }

        static void CompensateForX2()
        {
            using var camera = new CameraHelperX2();
            if (!camera.Open())
            {
                Console.WriteLine("RVC X2 Camera fails to open!");
                Console.ReadKey();
                return;
            }

            using var compensator = new Compensator();

            // 1. Initialize
            camera.Capture(out PointMap pm, out Image image);

            try
            {
                compensator.Initialize(pm, image, CompensatorMarkerType.MarkerType_CalibrationBoard);
                Console.WriteLine("Initialize successfully!");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Initialize failed: {ex.Message}");
                Console.ReadKey();
                return;
            }

            // 2. Update
            var dir = Path.Combine(Environment.CurrentDirectory, "Data");
            MakeDirectories(dir);

            int interval = 10;
            for (int i = 0; i < interval; i++)
            {
                camera.Capture(out PointMap tmpPm, out Image tmpImg); // Skip frames
            }

            camera.Capture(out PointMap updatePm, out Image updateImg);

            try
            {
                var drift = compensator.Update(updatePm, updateImg);
                Console.WriteLine($"Drift distance: {drift:F4}m\nUpdate success!");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Update failed: {ex.Message}");
                Console.ReadKey();
                return;
            }

            // 3. Apply
            camera.Capture(out PointMap finalPm, out Image finalImg);
            finalPm.Save(Path.Combine(dir, "before_compensate.ply"), PointMapUnit.Millimeter, true, finalImg);
            compensator.Apply(finalPm);
            finalPm.Save(Path.Combine(dir, "after_compensate.ply"), PointMapUnit.Millimeter, true, finalImg);
        }
        #endregion

        #region X1 Implementation
        class CameraHelperX1 : IDisposable
        {
            private X1 m_x1;
            private X1.CaptureOptions m_opts;

            public CameraHelperX1() => System.Init();

            public bool Open()
            {
                var devices = System.ListDevices();
                if (devices.Count == 0) return false;
                if(devices[0].IsFirmwareMatch() == false)
                {
                    Console.WriteLine("Device firmware mismatch. Please use RVCManager to upgrade the firmware");
                    RVC_CSharp.System.Shutdown();
                    Console.ReadKey();
                    return false;
                }
                m_x1 = X1.Create(devices[0], CameraID.CameraID_Left);
                if (!m_x1.Open()) return false;

                if (!m_x1.LoadCaptureOptionParameters(ref m_opts)) return false;

                m_opts.transform_to_camera = true;
                //X1.CustomTransformOptions custom_transform_opt;
                //custom_transform_opt.coordinate_select = X1.CustomTransformOptions.CoordinateSelect.CoordinateSelect_Camera;
                return true;
            }


            public void Capture(out PointMap pointMap, out Image image)
            {
                if (!m_x1.Capture(m_opts))
                {
                    Console.WriteLine($"Failed to Capture .Error: {System.GetLastErrorMessage()} ");
                    RVC_CSharp.System.Shutdown();
                    Console.ReadKey();
                }

                pointMap = m_x1.GetPointMap();
                image = m_x1.GetImage();

            }

            public void Dispose()
            {
                if (m_x1.IsOpen()) m_x1.Close();
                if (m_x1.IsValid()) X1.Destroy(m_x1);
                System.Shutdown();
            }
        }

        static void CompensateForX1()
        {
            using var camera = new CameraHelperX1();
            if (!camera.Open())
            {
                Console.WriteLine("RVC X1 Camera fails to open!");
                Console.ReadKey();
                return;
            }

            using var compensator = new Compensator();

            // 1. Initialize
            camera.Capture(out PointMap pm, out Image image);

            try
            {
                compensator.Initialize(pm, image, CompensatorMarkerType.MarkerType_CalibrationBoard);
                Console.WriteLine("Initialize successfully!");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Initialize failed: {ex.Message}");
                Console.ReadKey();
                return;
            }

            // 2. Update
            var dir = Path.Combine(Environment.CurrentDirectory, "Data");
            MakeDirectories(dir);

            int interval = 10;
            for (int i = 0; i < interval; i++)
            {
                camera.Capture(out PointMap tmpPm, out Image tmpImg); // Skip frames
            }

            camera.Capture(out PointMap updatePm, out Image updateImg);

            try
            {
                var drift = compensator.Update(updatePm, updateImg);
                Console.WriteLine($"Drift distance: {drift}m\nUpdate success!");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Update failed: {ex.Message}");
                Console.ReadKey();
                return;
            }

            // 3. Apply
            camera.Capture(out PointMap finalPm, out Image finalImg);
            finalPm.Save(Path.Combine(dir, "x1_before.ply"), PointMapUnit.Millimeter, true, finalImg);
            compensator.Apply(finalPm);
            finalPm.Save(Path.Combine(dir, "x1_after.ply"), PointMapUnit.Millimeter, true, finalImg);
        }
        #endregion
    }

}