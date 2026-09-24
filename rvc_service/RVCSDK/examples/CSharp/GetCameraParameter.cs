using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
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

            #region Step 1 ,GetCameraParameter
            float[] params_intrinsic = new float[9];
            float[] distortion = new float[5];
            float[] T_extrinsic = new float[16];
            bool ret = camera.GetExtrinsicMatrix(T_extrinsic);
            bool ret2 = camera.GetIntrinsicParameters(params_intrinsic, distortion);

            ret &= ret2;
            if (ret)
            {
                Console.WriteLine("camera Extrinsic Matrix: ");
                for (int i = 0; i < 16; i++)
                {
                    Console.Write(T_extrinsic[i].ToString() + ", ");
                }
                Console.WriteLine("\ncamera intrinsic parameter: ");
                for (int i = 0; i < 9; i++)
                {
                    Console.Write(params_intrinsic[i].ToString() + ", ");
                }
                Console.WriteLine("\ncamera distortion: ");
                for (int i = 0; i < 5; i++)
                {
                    Console.Write(distortion[i].ToString() + ", ");
                }
                Console.WriteLine("\n\n");
            }
            else
            {
                Console.WriteLine(System.GetLastErrorMessage());
                Console.WriteLine("RVC X camera is not valid !!!");
            }
            #endregion

            #region Step 2 ,Close

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
