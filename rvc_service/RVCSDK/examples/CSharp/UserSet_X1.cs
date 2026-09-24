using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;

namespace RVC_CSharp
{
    class UserSet_X1
    {
        static void Main()
        {
            #region Step 0 ,Init & Find & Open

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

            // Create and open RVC Camera.
            X1 x1 = RVC_CSharp.X1.Create(device, CameraID.CameraID_Left);
            x1.Open();
            if (!x1.IsOpen())
            {
                Console.WriteLine("RVC X Camera is not opened!");
                RVC_CSharp.X1.Destroy(x1);
                RVC_CSharp.System.Shutdown();
                return;
            }
            Console.WriteLine("RVC X Camera is opened!");

            #endregion

            #region Step 1 ,Show Different User Set Examples
            // (1) Switch to the User Set with ID 1, name it "high_light",
            // and complete the capture.
            x1.SetCurrentUserSet(1);
            string name1 = "high_light";
            bool ret = x1.SetUserSetName(1, name1);
            if (ret == false)
            {
                Console.WriteLine($"SetUserSetName failed: {RVC_CSharp.System.GetLastErrorMessage()}");
            }

            X1.CaptureOptions cap_opt = X1.CaptureOptions.Default();
            x1.LoadCaptureOptionParameters(ref cap_opt);

            cap_opt.capture_mode = CaptureMode.CaptureMode_Normal;

            if (x1.Capture(cap_opt) == true)
            {
                Console.WriteLine("RVC X Camera capture successed!");
            }
            else
            {
                Console.WriteLine("RVC X Camera capture failed!");
            }

            // (2) Switch to the User Set with ID 0 and complete the capture.
            x1.SetCurrentUserSet(0);
            if (x1.Capture() == true)
            {
                Console.WriteLine("RVC X Camera capture successed!");
            }
            else
            {
                Console.WriteLine("RVC X Camera capture failed!");
            }

            // (4) Switch to the User Set with ID 1 and save the parameter settings as the JSON file "high_light.json".
            x1.SetCurrentUserSet(1);
            x1.SaveSettingToFile("./high_light.json");

            // (5) Switch to the User Set with ID 2, change the name of this User Set to "high_light2", and import the parameter
            // settings from the JSON file "high_light.json".
            x1.SetCurrentUserSet(2);
            string name2 = "high_light2";
            ret = x1.SetUserSetName(2, name2);
            if (ret == false)
            {
                Console.WriteLine($"SetUserSetName failed: {RVC_CSharp.System.GetLastErrorMessage()}");
            }
            x1.LoadSettingFromFile("./high_light.json");

            #endregion

            #region Step 2 ,Close And Release Device
            // Close RVC Camera.
            x1.Close();

            // Destroy RVC Camera.
            RVC_CSharp.X1.Destroy(x1);

            // Shutdown RVC System.
            RVC_CSharp.System.Shutdown();

            #endregion
        }
    }
}