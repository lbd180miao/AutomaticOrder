using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using OpenCvSharp;
using RVC_CSharp;

namespace RVC_CSharp
{
    class Program
    {
        private static void Help()
        {
            Console.WriteLine("Usage: ./GetCaliBoardPoseX1 exposure_time_ms circle_center_distance_m circle_radius_m");
            Console.WriteLine("circle center distance(circle step) and circle radius can be found in calibration board.");
        }

        static void Main(string[] args)
        {

            #region Step 0 ,Check Cmd
            if (args.Length != 3)
            {
                Help();
                Console.ReadKey();
                Environment.Exit(0);
            }
            #endregion

            #region Step 1 ,Init & Find & Open

            if (false == RVC_CSharp.System.Init())
            {
                Console.WriteLine("Failed to init system.");
                Console.ReadKey();
                return;
            }

            Device device = RVC_CSharp.System.FindDeviceByIndex(0);
            //Device device = RVC_CSharp.System.FindDeviceBySN("P2GM353W002");
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

            #region Step 2 ,[Main Step] Modify Options And Capture
            bool ret = false;

            X1.CaptureOptions options = new X1.CaptureOptions();

            ret = camera.LoadCaptureOptionParameters(ref options);
            if (ret) { Console.WriteLine("Load Capture Option Parameters Succeed"); }

            options.Print();
            
            ret = camera.Capture(options);

            if (false == ret)
            {
                Console.WriteLine($"Failed to Capture .Error: { System.GetLastErrorMessage() } ");
                camera.Close();
                camera.Destroy();
                RVC_CSharp.System.Shutdown();
                Console.ReadKey();
                return;
            }

            Image image = camera.GetImage();
            DepthMap depth = camera.GetDepthMap();
            PointMap pointMap = camera.GetPointMap();

            Directory.CreateDirectory($"./{info.name}-{info.sn}");

            // 2D Image
            string imageFile = $"./{info.name}-{info.sn}/Image.bmp";
            if (image.SaveImage(imageFile))
            {
                Console.WriteLine($"Save Image,path = {imageFile} Succeed");
            }

            // Point Cloud 
            string pointCloudFile = $"./{info.name}-{info.sn}/PointCloud.ply";
            Console.WriteLine($"Save PointMap,path = {pointCloudFile}");
            pointMap.SavePlyBinary(pointCloudFile);

            // Color Point Cloud
            string colorPointCloudFile = $"./{info.name}-{info.sn}/ColorPointCloud.ply";
            Console.WriteLine($"Save Color-PointMap,path = {colorPointCloudFile}");
            pointMap.SaveColorPointCloud(image, colorPointCloudFile);

            #endregion

            #region Step 3 ,Get CaliBoard Pose And Transform PointCloud
            // set capture option parameter
            options.exposure_time_2d = int.Parse(args[0]);
            options.exposure_time_3d = int.Parse(args[0]);
            options.use_projector_capturing_2d_image = true;

            // set calibration board detection parameter
            float[] intrinsic_matrix = new float[9];
            float[] extrinsic_matrix = new float[16];
            float[] distortion = new float[5];

            ret = camera.GetIntrinsicParameters(intrinsic_matrix, distortion);
            if (ret) { Console.WriteLine("GetIntrinsicParameters Succeed"); }

            ret = camera.GetExtrinsicMatrix(extrinsic_matrix);
            if (ret) { Console.WriteLine("GetExtrinsicMatrix Succeed"); }

            // Pixel distance in Z plane where Z equals to calibration board position Z.
            double pixel_dist_m = extrinsic_matrix[11] / intrinsic_matrix[0];
            double circle_radius_m = double.Parse(args[2]);
            double circle_radius_pixel = circle_radius_m / pixel_dist_m;

            int[] calib_board_size = new int[2] { 4, 11 };
            double center_distance = double.Parse(args[1]);

            var blobDetectorParams = new SimpleBlobDetector.Params();
            blobDetectorParams.FilterByColor = true;
            blobDetectorParams.BlobColor = 255;
            blobDetectorParams.FilterByArea = true;
            blobDetectorParams.MinArea = (float)(circle_radius_pixel * circle_radius_pixel * Math.PI / 3);
            blobDetectorParams.MaxArea = (float)(circle_radius_pixel * circle_radius_pixel * Math.PI * 3);
            blobDetectorParams.FilterByCircularity = true;
            blobDetectorParams.MinCircularity = 0.5f;

            Console.WriteLine("area threshold pixel: {0}, {1}",
                blobDetectorParams.MinArea,
                blobDetectorParams.MaxArea);

            double[] R_in_camera = new double[9];
            double[] T_in_camera = new double[3];
            Mat drawedImage = new Mat();

            bool found = GetCaliBoardPose(pointMap, image, center_distance, calib_board_size, blobDetectorParams,
                                         ref R_in_camera, ref T_in_camera, drawedImage);

            imageFile = $"./{info.name}-{info.sn}/drawedImage.bmp";
            Cv2.ImWrite(imageFile, drawedImage);

            if (!found)
            {
                Console.WriteLine("Get pose failed. please adjust parameter according to ./Data/drawedImage.png. if calibboard in 2d");
                Console.WriteLine("image is detected, then adjust exposure time of 3d, otherwise, adjust blobdetector parameter");
            }
            else
            {
                PrintHomogeneousMatrix(R_in_camera, T_in_camera);
                // transform point cloud from camera coordinate to calibBoard coordinate
                double[] R_in_calib = new double[9];
                double[] T_in_calib = new double[3];
                RigidTransformInv(R_in_camera, T_in_camera, out R_in_calib, out T_in_calib);
                PointMap pointMapInCali = camera.GetPointMap();

                RigidTransformPointMap(ref pointMapInCali, R_in_calib, T_in_calib);
                pointCloudFile = $"./{info.name}-{info.sn}/PointCloudInCali.ply";
                colorPointCloudFile = $"./{info.name}-{info.sn}/ColorPointCloudInCali.ply";
                pointMapInCali.SavePlyBinary(pointCloudFile, unit_mm: false);
                pointMapInCali.SaveColorPointCloud(image, colorPointCloudFile, unit_mm: false);
            }
            #endregion

            #region Step 4 , Data Process And Close


            camera.Close();
            camera.Destroy();

            RVC_CSharp.System.Shutdown();
            Console.WriteLine("System close.");

            Console.ReadKey();
            #endregion

            return;
        }

        // Image To Mat
        public static Mat ToCVGrayImage(Image image)
        {
            Mat cvImage = new Mat();
            ImageType imageType = image.GetType();
            IntPtr imageData = image.GetDataPtr();
            Size imageSize = image.GetSize();

            switch (imageType)
            {
                case ImageType.Mono8:
                    cvImage = new Mat(imageSize.height, imageSize.width, MatType.CV_8UC1, imageData);
                    break;
                case ImageType.RGB8:
                    using (Mat rgbImage = new Mat(imageSize.height, imageSize.width, MatType.CV_8UC3, imageData))
                        Cv2.CvtColor(rgbImage, cvImage, ColorConversionCodes.RGB2GRAY);
                    break;
                case ImageType.BGR8:
                    using (Mat bgrImage = new Mat(imageSize.height, imageSize.width, MatType.CV_8UC3, imageData))
                        Cv2.CvtColor(bgrImage, cvImage, ColorConversionCodes.BGR2GRAY);
                    break;
                default:
                    throw new NotSupportedException("Unsupported image type");
            }
            return cvImage.Clone();
        }

        // Detect Circle
        public static bool DetectCVCircle(
            Image image,
            SimpleBlobDetector blobDetector,
            int[] calibBoardSize,
            out List<Point2f> centers,
            Mat debugImage = null)
        {
            centers = new List<Point2f>();
            using Mat cvImage = ToCVGrayImage(image);

            if (cvImage.Empty())
            {
                Console.WriteLine("Image is empty");
                return false;
            }

            Point2f[] centersArray;
            // Find Circles Grid
            bool found = Cv2.FindCirclesGrid(
                cvImage,
                new OpenCvSharp.Size(calibBoardSize[0], calibBoardSize[1]),
                out centersArray,
                FindCirclesGridFlags.AsymmetricGrid | FindCirclesGridFlags.Clustering,
                blobDetector);

            if (found) centers.AddRange(centersArray);
            // Draw Image
            if (debugImage != null)
            {
                Cv2.CvtColor(cvImage, debugImage, ColorConversionCodes.GRAY2BGR);
                if (!found)
                {
                    KeyPoint[] keyPoints = blobDetector.Detect(cvImage);
                    Cv2.DrawKeypoints(cvImage, keyPoints, debugImage, Scalar.Red);
                }
                else
                {
                    Cv2.DrawChessboardCorners(debugImage,
                        new OpenCvSharp.Size(calibBoardSize[0], calibBoardSize[1]), centers, found);
                }
            }
            return found;
        }

        // Extract Center From PCD
        public static void ExtractCenterFromPCD(
            PointMap pm,
            List<Point2f> centers,
            List<double> xyzs)
        {
            xyzs.Clear();
            Size pmSize = pm.GetSize();
            IntPtr pmDataPtr = pm.GetPointDataPtr();
            double[] pmData = new double[pmSize.width * pmSize.height * 3];
            Marshal.Copy(pmDataPtr, pmData, 0, pmData.Length);

            foreach (Point2f pt in centers)
            {
                int idX0 = (int)pt.X, idY0 = (int)pt.Y;
                if (idX0 < 0 || idX0 >= pmSize.width - 1 ||
                    idY0 < 0 || idY0 >= pmSize.height - 1)
                {
                    xyzs.AddRange(new[] { double.NaN, double.NaN, double.NaN });
                    continue;
                }

                double wx = pt.X - idX0, wy = pt.Y - idY0;
                double[] p0 = GetPoint(pmData, pmSize, idX0, idY0);
                double[] p1 = GetPoint(pmData, pmSize, idX0 + 1, idY0);
                double[] p2 = GetPoint(pmData, pmSize, idX0, idY0 + 1);
                double[] p3 = GetPoint(pmData, pmSize, idX0 + 1, idY0 + 1);

                for (int i = 0; i < 3; i++)
                {
                    double val = (1 - wx) * (1 - wy) * p0[i] +
                                 wx * (1 - wy) * p1[i] +
                                 (1 - wx) * wy * p2[i] +
                                 wx * wy * p3[i];
                    xyzs.Add(val);
                }
            }
        }

        // Generate Cali Board Centers
        public static void GenerateCalibBoardCenters(
            double centerDistance,
            int[] calibBoardSize,
            List<double> centers)
        {
            centers.Clear();
            for (int r = 0; r < calibBoardSize[1]; r++)
            {
                for (int c = 0; c < calibBoardSize[0]; c++)
                {
                    double y = c * centerDistance + 0.5 * centerDistance * (r % 2);
                    double x = r * centerDistance * 0.5;
                    centers.Add(x);
                    centers.Add(y);
                    centers.Add(0);
                }
            }
        }

        // Get Cali Board Pose
        public static bool GetCaliBoardPose(
            PointMap pm,
            Image image,
            double centerDistance,
            int[] calibBoardSize,
            SimpleBlobDetector.Params blobParams,
            ref double[] R,
            ref double[] T,
            Mat debugImage = null)
        {
            using var blobDetector = SimpleBlobDetector.Create(blobParams);
            List<Point2f> centers = new List<Point2f>();

            bool found = DetectCVCircle(image, blobDetector, calibBoardSize, out centers, debugImage);
            if (!found) return false;

            List<double> centerInPcd = new List<double>();
            ExtractCenterFromPCD(pm, centers, centerInPcd);

            List<double> refCenters = new List<double>();
            GenerateCalibBoardCenters(centerDistance, calibBoardSize, refCenters);

            found = ComputeRigidTransform(
                refCenters.ToArray(),
                centerInPcd.ToArray(),
                refCenters.Count / 3,
                ref R,
                ref T);

            return found;
        }

        // Rigid Transform Inverse
        public static void RigidTransformInv(
            double[] R,
            double[] T,
            out double[] invR,
            out double[] invT)
        {
            invR = new double[9];
            invT = new double[3];

            for (int i = 0; i < 3; i++)
                for (int j = 0; j < 3; j++)
                    invR[j * 3 + i] = R[i * 3 + j];

            for (int i = 0; i < 3; i++)
            {
                invT[i] = 0;
                for (int j = 0; j < 3; j++)
                    invT[i] -= invR[i * 3 + j] * T[j];
            }
        }

        // Rigid Transform Point Map
        public static void RigidTransformPointMap(
           ref PointMap pm,
            double[] R,
            double[] T)
        {
            Size pmSize = pm.GetSize();
            IntPtr pmDataPtr = pm.GetPointDataPtr();
            double[] pmData = new double[pmSize.width * pmSize.height * 3];
            Marshal.Copy(pmDataPtr, pmData, 0, pmData.Length);

            for (int i = 0; i < pmData.Length; i += 3)
            {
                double x = pmData[i], y = pmData[i + 1], z = pmData[i + 2];

                double tx = R[0] * x + R[1] * y + R[2] * z;
                double ty = R[3] * x + R[4] * y + R[5] * z;
                double tz = R[6] * x + R[7] * y + R[8] * z;

                pmData[i] = tx + T[0];
                pmData[i + 1] = ty + T[1];
                pmData[i + 2] = tz + T[2];
            }

            Marshal.Copy(pmData, 0, pmDataPtr, pmData.Length);
        }

        // Get Index Point
        private static double[] GetPoint(double[] pmData, Size pmSize, int x, int y)
        {
            int index = (x + y * pmSize.width) * 3;
            return new[] { pmData[index], pmData[index + 1], pmData[index + 2] };
        }

        // Compute Rigid Transform
        public static bool ComputeRigidTransform(
            double[] srcPCD,
            double[] dstPCD,
            int nPts,
            ref double[] R,
            ref double[] T)
        {
            if (srcPCD.Length < nPts * 3 || dstPCD.Length < nPts * 3)
                throw new ArgumentException("Point Cloud Length Error");

            double[] srcMean = new double[3], dstMean = new double[3];
            int countValid = 0;

            for (int i = 0; i < nPts; i++)
            {
                int srcIdx = i * 3, dstIdx = i * 3;
                if (!IsValidPoint(srcPCD, srcIdx) || !IsValidPoint(dstPCD, dstIdx))
                    continue;

                for (int j = 0; j < 3; j++)
                {
                    srcMean[j] += srcPCD[srcIdx + j];
                    dstMean[j] += dstPCD[dstIdx + j];
                }
                countValid++;
            }

            if (countValid < 3) return false;

            for (int i = 0; i < 3; i++)
            {
                srcMean[i] /= countValid;
                dstMean[i] /= countValid;
            }

            double[,] H = new double[3, 3];
            for (int i = 0; i < nPts; i++)
            {
                int srcIdx = i * 3, dstIdx = i * 3;
                if (!IsValidPoint(srcPCD, srcIdx) || !IsValidPoint(dstPCD, dstIdx))
                    continue;

                double[] srcDelta = new double[3], dstDelta = new double[3];
                for (int j = 0; j < 3; j++)
                {
                    srcDelta[j] = srcPCD[srcIdx + j] - srcMean[j];
                    dstDelta[j] = dstPCD[dstIdx + j] - dstMean[j];
                }

                for (int row = 0; row < 3; row++)
                    for (int col = 0; col < 3; col++)
                        H[row, col] += srcDelta[row] * dstDelta[col];
            }

            using (Mat hMat = new Mat(3, 3, MatType.CV_64FC1, H))
            {
                Mat w = new Mat(), u = new Mat(), vt = new Mat();
                Cv2.SVDecomp(hMat, w, u, vt, SVD.Flags.ModifyA);

                Mat v = vt.T();
                Mat rMat = v * u.T();

                if (Cv2.Determinant(rMat) < 0)
                {
                    Mat uNeg = u.Clone();
                    for (int col = 0; col < uNeg.Cols; col++)
                        uNeg.Set(uNeg.Rows - 1, col, -uNeg.At<double>(uNeg.Rows - 1, col));

                    rMat = v * uNeg.T();
                }

                R = new double[9];
                for (int i = 0; i < 3; i++)
                    for (int j = 0; j < 3; j++)
                        R[i * 3 + j] = rMat.At<double>(i, j);
            }

            T = new double[3];
            for (int i = 0; i < 3; i++)
            {
                double sum = 0;
                for (int j = 0; j < 3; j++)
                    sum += R[i * 3 + j] * srcMean[j];
                T[i] = dstMean[i] - sum;
            }

            return true;
        }

        // Is Valid Point
        private static bool IsValidPoint(double[] pointArray, int index)
        {
            return !double.IsNaN(pointArray[index + 2]);
        }

        public static void PrintHomogeneousMatrix(double[] R, double[] T)
        {
            Mat homogeneousMatrix = new Mat(4, 4, MatType.CV_64FC4, 1);
            homogeneousMatrix.SetTo(new Scalar(0));

            for (int i = 0; i < 3; i++)
            {
                for (int j = 0; j < 3; j++)
                {
                    homogeneousMatrix.Set<double>(i, j, R[i * 3 + j]);
                }
            }

            for (int i = 0; i < 3; i++)
            {
                homogeneousMatrix.Set<double>(i, 3, T[i]);
            }

            homogeneousMatrix.Set<double>(3, 3, 1.0);

            Console.WriteLine("Transformation:");
            for (int i = 0; i < homogeneousMatrix.Rows; i++)
            {
                for (int j = 0; j < homogeneousMatrix.Cols; j++)
                {
                    double value = homogeneousMatrix.Get<double>(i, j);
                    Console.Write($"{value,10:F4}"); 
                }
                Console.WriteLine();
            }
        }
    }
}
