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
        static void Main()
        {
            #region Step 0 , Start init system.

            LOG("Step 0,Start init system.");

            RVC_CSharp.System.Init();

            if (RVC_CSharp.System.IsInited() == false)
            {
                LOG("Failed to init system.");
                Console.ReadKey();
                return;
            }

            LOG("Successfully init system.");


            #endregion

            #region Step 1 , Start Find Devices

            LOG("Step 1 , Start Find Devices.");

            List<Device> devices = RVC_CSharp.System.ListDevices(SystemListDeviceType.All);

            if (devices == null || devices.Count <= 0)
            {
                LOG("Can not find device.\nPlease Check Connection.");

                LOG("System close.");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            LOG($"Find {devices.Count} devices.");

            #endregion

            #region Step 2 , Choose Target Device

            LOG("Step 2 , Choose Target Device.");

            LOG("List All Devices.");
            //int canConnectedIndex = -1;
            for (int i = 0; i < devices.Count; i++)
            {
                var deviceTmp = devices[i];
                DeviceInfo infoTmp = new DeviceInfo();
                deviceTmp.GetDeviceInfo(ref infoTmp);
                bool canConnected = deviceTmp.CheckCanConnected();
                LOG("\n");
                LOG($"{i}-设备名称--[name] = {infoTmp.name}");
                LOG($"{i}-设备序列号--[sn] = {infoTmp.sn}");
                LOG($"{i}-出厂日期--[factroydate] = {infoTmp.factroydate}");
                LOG($"{i}-端口类型--[type] = {infoTmp.type}");
                if(canConnected)
                {
                    LOG($"{i}-端口号--[port] = {infoTmp.port}【只针对网络相机】");
                    LOG($"{i}-主板类型--[boardmodel] = {infoTmp.boardmodel}");
                    LOG($"{i}-支持的相机类型--[cameraid] = {infoTmp.cameraid}");
                    LOG($"{i}-是否支持双相机--[support_x2] = {infoTmp.support_x2}");
                    LOG($"{i}-支持的投影颜色--[support_color] = {infoTmp.support_color}");
                    LOG($"{i}-工作距离-近--[workingdist_near_mm] = {infoTmp.workingdist_near_mm}");
                    LOG($"{i}-工作距离-远--[workingdist_far_mm] = {infoTmp.workingdist_far_mm}");
                    LOG($"{i}-固件版本--[firmware_version] = {infoTmp.firmware_version}");
                    LOG($"{i}-支持的拍摄模式--[support_capture_mode] = {infoTmp.support_capture_mode}");
                }
                LOG($"{i}-是否可以连接 = {canConnected}");
                LOG("\n");
                //if (canConnectedIndex == -1 && canConnected)
                //{
                    //canConnectedIndex = i;
                //}
            }

            //if (canConnectedIndex == -1)
            //{
            //    LOG("No Device Can Connected.");
            //    LOG("System close.");
            //    RVC_CSharp.System.Shutdown();
            //    Console.ReadKey();
            //    return;
            //}

            LOG("Input the id of device that you want to connect.");
            LOG($"Input {devices.Count} means all devices.");

            Console.Write("ID : ");
            string str = Console.ReadLine();
            var parseRet = int.TryParse(str, out int id);
            if (!parseRet || id < 0 || id > devices.Count)
            {
                LOG("Input is not valid");
                LOG("System close.");
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            Capture(devices,id);
            

            #endregion

            #region Step 6 , Close And Release Device

            LOG("Step 6 , Close And Release Device");

            RVC_CSharp.System.Shutdown();
            LOG("System close.");
            Console.ReadKey();

            #endregion
            return;
        }

        public static void Capture(List<Device> devices,int id)
        {
            for (int i = 0; i < devices.Count; i++)
            {
                if (i == id || id == devices.Count )
                {
                    var device = devices[i];
                    DeviceInfo info = new DeviceInfo();
                    device.GetDeviceInfo(ref info);

                    if (!device.CheckCanConnected())
                    {
                        LOG($"{id}-DeviceName={info.name}-SV={info.sn}-Not CanConnected.");
                        continue;
                    }

                    do
                    {
                        if ((info.cameraid & RVC_CSharp.CameraID.CameraID_Left) != 0)
                        {
                            LOG("Step 3 , Open Left Camera ");
                            if(device.IsFirmwareMatch() == false)
                            {
                                Console.WriteLine("Device firmware mismatch. Please use RVCManager to upgrade the firmware");
                                RVC_CSharp.System.Shutdown();
                                Console.ReadKey();
                                return;
                            }
                            LOG("Create Left Camera");
                            var x1 = RVC_CSharp.X1.Create(device, CameraID.CameraID_Left);

                            LOG("Open Left Camera");
                            x1.Open();

                            if (x1.IsValid() == false || x1.IsOpen() == false)
                            {
                                LOG("---------Failed to open Left camera .");
                                break;
                            }

                            LOG("Successfully open camera.");

                            // Capture
                            // Step 4,Capture
                            LOG("Step 4 , Capture");
                            LOG("Load Capture Option Parameters From Camera.");
                            X1.CaptureOptions options = new X1.CaptureOptions();
                            x1.LoadCaptureOptionParameters(ref options);

                            options.Print();

                            if (x1.Capture(options) == false)
                            {
                                LOG("Failed to capture Left.");
                                x1.Close();
                                break;
                            }

                            LOG("Successfully Capture Left.");

                            var image = x1.GetImage();
                            var depth = x1.GetDepthMap();
                            var pointMap = x1.GetPointMap();


                            LOG("Step 5 , Data Process");

                            Directory.CreateDirectory($"./{info.name}-{info.sn}");
                            Directory.CreateDirectory($"./{info.name}-{info.sn}/Left");

                            // 2D Image
                            string imageFile = $"./{info.name}-{info.sn}/Left/Image.bmp";
                            LOG($"Save Image,path = {imageFile}");
                            image.SaveImage(imageFile);

                            // Depth
                            string depthFile = $"./{info.name}-{info.sn}/Left/Depth.tiff";
                            LOG($"Save Depth,path = {depthFile}");
                            depth.SaveDepthMap(depthFile);

                            // Point Cloud 
                            string pointCloudFile = $"./{info.name}-{info.sn}/Left/PointCloud.ply";
                            LOG($"Save PointMap,path = {pointCloudFile}");
                            pointMap.SavePlyBinary(pointCloudFile);

                            // Color Point Cloud
                            string colorPointCloudFile = $"./{info.name}-{info.sn}/Left/ColorPointCloud.ply";
                            LOG($"Save Color-PointMap,path = {colorPointCloudFile}");
                            pointMap.SaveColorPointCloud(image, colorPointCloudFile);


                            LOG("Successfully Save Data Left.");
                            x1.Close();
                        }

                    } while (false);

                    do
                    {
                        if ((info.cameraid & RVC_CSharp.CameraID.CameraID_Right) != 0)
                        {
                            LOG("Step 3 , Open Single Camera ");

                            LOG("Create Right Camera");
                            var x1 = RVC_CSharp.X1.Create(device, CameraID.CameraID_Right);

                            LOG("Open Right Camera");
                            x1.Open();

                            if (x1.IsValid() == false || x1.IsOpen() == false)
                            {
                                LOG("---------Failed to open Right camera .");
                                break;
                            }

                            LOG("Successfully open camera.");

                            // Capture
                            // Step 4,Capture
                            LOG("Step 4 , Capture");
                            LOG("Load Capture Option Parameters From Camera.");
                            X1.CaptureOptions options = new X1.CaptureOptions();
                            x1.LoadCaptureOptionParameters(ref options);
                            options.Print();


                            if (x1.Capture(options) == false)
                            {
                                LOG("Failed to capture Right.");
                                x1.Close();
                                break;
                            }

                            LOG("Successfully Capture Right.");

                            var image = x1.GetImage();
                            var depth = x1.GetDepthMap();
                            var pointMap = x1.GetPointMap();


                            LOG("Step 5 , Data Process");

                            Directory.CreateDirectory($"./{info.name}-{info.sn}");
                            Directory.CreateDirectory($"./{info.name}-{info.sn}/Right");

                            // 2D Image
                            string imageFile = $"./{info.name}-{info.sn}/Right/Image.bmp";
                            LOG($"Save Image,path = {imageFile}");
                            image.SaveImage(imageFile);

                            // Depth
                            string depthFile = $"./{info.name}-{info.sn}/Right/Depth.tiff";
                            LOG($"Save Depth,path = {depthFile}");
                            depth.SaveDepthMap(depthFile);

                            // Point Cloud 
                            string pointCloudFile = $"./{info.name}-{info.sn}/Right/PointCloud.ply";
                            LOG($"Save PointMap,path = {pointCloudFile}");
                            pointMap.SavePlyBinary(pointCloudFile);

                            // Color Point Cloud
                            string colorPointCloudFile = $"./{info.name}-{info.sn}/Right/ColorPointCloud.ply";
                            LOG($"Save Color-PointMap,path = {colorPointCloudFile}");
                            pointMap.SaveColorPointCloud(image, colorPointCloudFile);


                            LOG("Successfully Save Data Right.");
                            x1.Close();
                        }

                    } while (false);

                    do
                    {
                        if (info.support_x2)
                        {
                            LOG("Step 3 , Open Both Camera ");

                            LOG("Create Both Camera");
                            var x2 = RVC_CSharp.X2.Create(device);

                            LOG("Open Both Camera");
                            x2.Open();

                            if (x2.IsValid() == false || x2.IsOpen() == false)
                            {
                                LOG("---------Failed to open Both camera .");
                                break;
                            }

                            LOG("Successfully open camera.");

                            // Capture
                            // Step 4,Capture
                            LOG("Step 4 , Capture");
                            LOG("Load Capture Option Parameters From Camera.");
                            X2.CaptureOptions options = new X2.CaptureOptions();
                            x2.LoadCaptureOptionParameters(ref options);

                            options.Print();

                            if (x2.Capture(options) == false)
                            {
                                LOG("Failed to capture Both.");
                                x2.Close();
                                break;
                            }

                            LOG("Successfully Capture Both.");
                            CameraID cameraId = CameraID.CameraID_Left;
                            if (info.support_extra)
                            {
                                cameraId = CameraID.CameraID_Extra;
                            }
                            var image = x2.GetImage(cameraId);
                            var depth = x2.GetDepthMap();
                            var pointMap = x2.GetPointMap();


                            LOG("Step 5 , Data Process");

                            Directory.CreateDirectory($"./{info.name}-{info.sn}");
                            Directory.CreateDirectory($"./{info.name}-{info.sn}/Both");

                            // 2D Image
                            string imageFile = $"./{info.name}-{info.sn}/Both/Image.bmp";
                            LOG($"Save Image,path = {imageFile}");
                            image.SaveImage(imageFile);

                            // Depth
                            string depthFile = $"./{info.name}-{info.sn}/Both/Depth.tiff";
                            LOG($"Save Depth,path = {depthFile}");
                            depth.SaveDepthMap(depthFile);

                            // Point Cloud 
                            string pointCloudFile = $"./{info.name}-{info.sn}/Both/PointCloud.ply";
                            LOG($"Save PointMap,path = {pointCloudFile}");
                            pointMap.SavePlyBinary(pointCloudFile);

                            // Color Point Cloud
                            string colorPointCloudFile = $"./{info.name}-{info.sn}/Both/ColorPointCloud.ply";
                            LOG($"Save Color-PointMap,path = {colorPointCloudFile}");
                            pointMap.SaveColorPointCloud(image, colorPointCloudFile);


                            LOG("Successfully Save Data Both.");
                            x2.Close();
                        }

                    } while (false);
                }
            }
        }

        static void LOG(string str)
        {
            Console.WriteLine(str);
        }
    }
}
