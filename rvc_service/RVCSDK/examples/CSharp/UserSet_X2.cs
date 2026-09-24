using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;

namespace RVC_CSharp
{
    class UserSet_X2
    {
        static void Main()
        {
            #region Step 0 ,Init & Find & Open

            // Initialize RVC system.
            if (!RVC_CSharp.System.Init())
            {
                Console.WriteLine("Failed to init system.");
                return;
            }

            // Find Device
            // Method 2 , find Device By Index . 
            Device device = RVC_CSharp.System.FindDeviceByIndex(0);

            // Find whether any Camera is connected or not.
            if (false == device.IsValid())
            {
                Console.WriteLine("Can not find any Camera!");
                RVC_CSharp.System.Shutdown();
                return;
            }

            if (device.IsFirmwareMatch() == false)
            {
                Console.WriteLine("device firmware mismatch, Please use RVCManager to upgrade the firmware");
                RVC_CSharp.System.Shutdown();
                return;
            }

            // Create and open RVC X2 Camera.
            X2 x2 = RVC_CSharp.X2.Create(device);
            x2.Open();
            if (!x2.IsOpen())
            {
                Console.WriteLine("RVC X Camera is not opened!");
                RVC_CSharp.X2.Destroy(x2);
                RVC_CSharp.System.Shutdown();
                return;
            }
            Console.WriteLine("RVC X Camera is opened!");

            #endregion

            #region Step 1 ,Show Different User Set Examples
            // (1) Switch to the User Set with ID 1, name it "high_light", set the capture mode of the parameter group to
            // CaptureMode_Ultra and complete the capture.
            x2.SetCurrentUserSet(1);
            string name1 = "high_light";
            bool ret = x2.SetUserSetName(1, name1);
            if (ret == false)
            {
                Console.WriteLine($"SetUserSetName failed: {RVC_CSharp.System.GetLastErrorMessage()}");
            }

            X2.CaptureOptions cap_opt = X2.CaptureOptions.Default();
            x2.LoadCaptureOptionParameters(ref cap_opt);

            cap_opt.capture_mode = CaptureMode.CaptureMode_Ultra;

            if (x2.Capture(cap_opt) == true)
            {
                Console.WriteLine("RVC X Camera capture successed!");
            }
            else
            {
                Console.WriteLine("RVC X Camera capture failed!");
            }

            // (2) Switch to the User Set with ID 0 and complete the capture.
            x2.SetCurrentUserSet(0);
            if (x2.Capture() == true)
            {
                Console.WriteLine("RVC X Camera capture successed!");
            }
            else
            {
                Console.WriteLine("RVC X Camera capture failed!");
            }

            // (4) Switch to the User Set with ID 1 and save the parameter settings as the JSON file "high_light.json".
            x2.SetCurrentUserSet(1);
            x2.SaveSettingToFile("./high_light.json");

            // (5) Switch to the User Set with ID 2, change the name of this User Set to "high_light2", and import the parameter
            // settings from the JSON file "high_light.json".
            x2.SetCurrentUserSet(2);
            string name2 = "high_light2";
            ret = x2.SetUserSetName(2, name2);
            if (ret == false)
            {
                Console.WriteLine($"SetUserSetName failed: {RVC_CSharp.System.GetLastErrorMessage()}");
            }
            x2.LoadSettingFromFile("./high_light.json");

            #endregion

            #region Step 2 ,Close And Release Device
            // Close RVC Camera.
            x2.Close();

            // Destroy RVC Camera.
            RVC_CSharp.X2.Destroy(x2);

            // Shutdown RVC System.
            RVC_CSharp.System.Shutdown();

            #endregion
        }
    }
}