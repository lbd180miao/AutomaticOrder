#if OpenCV_Enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;
using OpenCvSharp;

namespace RVC_CSharp
{

    public static class Opencv_Extension
    {
        /// <summary>
        /// 将 RVC 的 Image 转换为 Mat格式
        /// </summary>
        /// <param name="image">RVC 的 图像 数据</param>
        /// <returns>如果是灰度相机，那么是单通道图像 CV_8UC1 ；如果是彩色相机，那么是RGB图像 CV_8UC3</returns>
        public static Mat ToMat(this RVC_CSharp.Image image)
        {
            return new Mat(image.GetSize().height, image.GetSize().width,
                image.GetType() == ImageType.Mono8 ? MatType.CV_8UC1 : MatType.CV_8UC3, image.GetDataPtr()).Clone();
        }

        /// <summary>
        /// 将 RVC的DepthMap 转换为 Mat格式
        /// </summary>
        /// <param name="depthMap">RVC 的 深度图 数据</param>
        /// <param name="unit_mm">是否将数值转换为毫米单位，否则保持原有的数值单位（米）</param>
        /// <returns> 输出格式 CV_64FC1 </returns>
        public static Mat ToMat(this RVC_CSharp.DepthMap depthMap,bool unit_mm = true)
        {
            int width = depthMap.GetSize().width;
            int height = depthMap.GetSize().height;
            return new Mat(height, width, MatType.CV_64FC1, depthMap.GetDataPtr()).Clone() * (unit_mm ? 1000.0 : 1.0);
        }

        /// <summary>
        /// 将 RVC 的 PointMap 转换为 Mat格式
        /// </summary>
        /// <param name="depthMap">RVC 的 点云 数据</param>
        /// <param name="unit_mm">是否将数值转换为毫米单位，否则保持原有的数值单位（米）</param>
        /// <returns> 输出格式 CV_64FC3 </returns>
        public static Mat ToMat(this RVC_CSharp.PointMap depthMap, bool unit_mm = true)
        {
            int width = depthMap.GetSize().width;
            int height = depthMap.GetSize().height;
            return new Mat(height, width, MatType.CV_64FC3, depthMap.GetPointDataPtr()).Clone() * (unit_mm ? 1000.0 : 1.0);
        }

    }

}
#endif