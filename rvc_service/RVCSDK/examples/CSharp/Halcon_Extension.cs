#if Halcon_Enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;
using HalconDotNet;

namespace RVC_CSharp
{
    public static class Halcon_Extension
    {
        /// <summary>
        /// 将 RVC 的 Image 数据 转换成 Halcon 的 HObject
        /// 你需要先获取 Halcon 的 License
        /// </summary>
        /// <param name="image">RVC 的 图像 数据</param>
        /// <returns> Halcon 的 图像 数据</returns>
        public static HObject ToHalcon(this RVC_CSharp.Image image)
        {
            HObject obj = null;
            int width = image.GetSize().width;
            int height = image.GetSize().height;

            if (image.GetType() == ImageType.Mono8)
            {
                HOperatorSet.GenImage1Extern(out obj, "byte", width, height, image.GetDataPtr(), IntPtr.Zero);
            }
            else if (image.GetType() == ImageType.BGR8)
            {
                HOperatorSet.GenImageInterleaved(
                    out obj,
                    image.GetDataPtr(),  
                    "bgr",               
                    width,               
                    height,              
                    0,                   
                    "byte",              
                    width,               
                    height,              
                    0,                   
                    0,                   
                    8,                   
                    0                    
                );
            }
            return obj;
        }

        public enum NullValueConvertMethod
        {
            KeepNull,
            ToZero,
            ToMinimum,
            ToGivenValue
        }

        /// <summary>
        /// 将 RVC 的 DepthMap 数据 转换成 Halcon 的 HObject
        /// 你需要先获取 Halcon 的 License
        /// </summary>
        /// <param name="depthMap">RVC 的 深度图 数据</param>
        /// <param name="method">Null值的处理方式</param>
        /// <param name="value">可以吧Null值转化为特定的值</param>
        /// <param name="unit_mm">点云数值单位，是否为毫米，否则为米</param>
        /// <returns>Halcon 的 深度图 数据</returns>
        public static HObject ToHalcon(this RVC_CSharp.DepthMap depthMap, NullValueConvertMethod method = NullValueConvertMethod.KeepNull, double value = 0.0, bool unit_mm = true)
        {
            int width = depthMap.GetSize().width;
            int height = depthMap.GetSize().height;
            int size = width * height;

            double[] depthData = new double[size];
            Marshal.Copy(depthMap.GetDataPtr(), depthData, 0, size);

            double min = Double.MaxValue;
            double max = double.MinValue;

            if (method == NullValueConvertMethod.ToMinimum)
            {
                for (int i = 0; i < depthData.Length; i++)
                {
                    double depth = depthData[i];
                    if (double.IsNaN(depth))
                        continue;
                    if (depth > max)
                        max = depth;
                    if (depth < min)
                        min = depth;
                }
            }

            double k = unit_mm ? 1000.0 : 1.0;

            float[] imageData = new float[size];
            for (int i = 0; i < size; i++)
            {
                if (double.IsNaN(depthData[i]))
                {
                    if (method == NullValueConvertMethod.KeepNull)
                    {
                        imageData[i] = (float) (depthData[i] * k);
                    }
                    else if (method == NullValueConvertMethod.ToZero)
                    {
                        imageData[i] = 0;
                    }
                    else if (method == NullValueConvertMethod.ToMinimum)
                    {
                        imageData[i] = (float)min;
                    }
                    else if (method == NullValueConvertMethod.ToGivenValue)
                    {
                        imageData[i] = (float)value;
                    }
                    else
                    {
                        imageData[i] = (float) (depthData[i] * k);
                    }
                }
                else
                {
                    imageData[i] = (float)(depthData[i] * k);
                }
            }

            IntPtr pDepth = Marshal.AllocHGlobal(size * sizeof(float));
            Marshal.Copy(imageData, 0, pDepth, size);
            HOperatorSet.GenImage1(out HObject HDepImg, "real", width, height, pDepth);
            // Marshal.Release(pDepth);
            Marshal.FreeHGlobal(pDepth);
            return HDepImg;
        }

        /// <summary>
        /// 将 RVC 的 PointMap 数据 转换成 Halcon 的 HTuple
        /// </summary>
        /// <param name="pointMap">RVC 的 点云 数据</param>
        /// <param name="unit_mm">点云数值单位，是否为毫米，否则为米</param>
        /// <returns>Halcon 的 点云 数据</returns>
        public static HTuple ToHalcon(this RVC_CSharp.PointMap pointMap,bool unit_mm = true)
        {
            int width = pointMap.GetSize().width;
            int height = pointMap.GetSize().height;
            int size = width * height;

            pointMap.GetPointMapSeperated(out double[]  xs, out double[] ys, out double[] zs, unit_mm ? 1000.0:1.0);

            HTuple Hx = xs, Hy = ys, hz = zs;
            //HOperatorSet.GenObjectModel3dFromPoints(Hx, Hy, hz, out HTuple hv_ObjectModel3D);

            HOperatorSet.GenObjectModel3dFromPoints(Hx, Hy, hz, out var hv_ObjectModel3D);
            return hv_ObjectModel3D;
        }

        /// <summary>
        /// 保存 Halcon 的 图像 数据
        /// 你需要先获取 Halcon 的 License
        /// </summary>
        /// <param name="image">Halcon 的 图像 数据</param>
        /// <param name="format">保存格式</param>
        /// <param name="name">保存的文件名</param>
        public static void SaveImage(this HObject image, string format = "bmp", string name = "./HalconImage.bmp")
        {
            HOperatorSet.WriteImage(image, format, 0, name);
        }

        /// <summary>
        /// 保存 Halcon 的 深度图 数据
        /// 你需要先获取 Halcon 的 License
        /// </summary>
        /// <param name="depth">Halcon 的 深度图 数据</param>
        /// <param name="format">保存格式</param>
        /// <param name="name">保存的文件名</param>
        public static void SaveDepth(this HObject depth, string format = "tiff", string name = "./HalconDepth.tiff")
        {
            HOperatorSet.WriteImage(depth, format, 0, name);
        }

        /// <summary>
        /// 保存 Halcon 的 点云 数据
        /// 你需要先获取 Halcon 的 License
        /// </summary>
        /// <param name="pointMap">Halcon 的 点云 数据</param>
        /// <param name="format">保存格式</param>
        /// <param name="name">保存的文件名</param>
        public static void SavePointCloud(this HTuple pointMap, string format = "ply", string name = "./HalconPointMap.ply")
        {
            HOperatorSet.WriteObjectModel3d(pointMap, format, name, new HTuple(), new HTuple());
        }
    }
}
#endif