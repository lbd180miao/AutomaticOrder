#if VisionPro_Enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using RVC_CSharp;
using Cognex.VisionPro;
using Cognex.VisionPro.ImageFile;
using Cognex.VisionPro3D;


namespace RVC_CSharp
{
    public static class VisionPro_Extension
    {
        /// <summary>
        /// 将 RVC_CSharp.PointMap 转换为 CogImage16Range 的格式
        /// 你需要先获取 VisionPro 的 License
        /// </summary>
        /// <param name="pointMap">RVC 的 点云格式</param>
        /// <param name="unit_mm">数值单位，是否为毫米，否则为米</param>
        /// <returns>CogImage16Range格式的数据</returns>
        public static CogImage16Range ToVisionPro(this RVC_CSharp.PointMap pointMap, bool unit_mm = true,
            bool xInvert = false, bool yInvert = false)
        {
            int width = pointMap.GetSize().width;
            int height = pointMap.GetSize().height;
            int size = width * height;

            //数值单位,转换为mm
            pointMap.GetPointMapSeperated(out double[] xs, out double[] ys, out double[] zs, unit_mm ? 1000.0 : 1.0);

#region 寻找最大值和最小值

            double zmin = double.MaxValue;
            double xmin = double.MaxValue;
            double ymin = double.MaxValue;
            double xmax = double.MinValue;
            double ymax = double.MinValue;
            double zmax = double.MinValue;
            for (int i = 0; i < zs.Length; i++)
            {
                if (zs[i] < zmin)
                    zmin = zs[i];
                if (zs[i] > zmax)
                    zmax = zs[i];

                if (xs[i] < xmin)
                    xmin = xs[i];
                if (xs[i] > xmax)
                    xmax = xs[i];

                if (ys[i] < ymin)
                    ymin = ys[i];
                if (ys[i] > ymax)
                    ymax = ys[i];
            }

#endregion

#region 建立映射矩阵

            double xResolution = Convert.ToDouble(width / (xmax - xmin));
            double yResolution = Convert.ToDouble(height / (ymax - ymin));
            double zResolution = Convert.ToDouble(65535.0f / (zmax - zmin));

            double xOffset = -xResolution * xmin;
            double yOffset = -yResolution * ymin;
            double zOffset = -zResolution * zmin;

            Cog3DTransformLinear linear3Dtrans = new Cog3DTransformLinear(
                new Cog3DMatrix3x3(
                    xResolution, 0.0, 0.0,
                    0.0, yResolution, 0.0,
                    0.0, 0.0, zResolution),
                new Cog3DVect3(xOffset, yOffset, zOffset));

#endregion

#region 建立采样池,因为在同一个位点要取均值，所以把data和count缓存起来

            double[] data = new double[size];
            int[] count = new int[size];
            for (int i = 0; i < size; i++)
            {
                data[i] = 0;
                count[i] = 0;
            }

            for (int i = 0; i < size; i++)
            {
                //过滤NAN值
                if (double.IsNaN(zs[i]))
                    continue;
                var vec3 = linear3Dtrans.MapPoint(new Cog3DVect3(xs[i], ys[i], zs[i]));
                double x = vec3.X;
                double y = vec3.Y;
                double z = vec3.Z;

                int row = (int)y;
                int col = (int)x;
                if (row >= height)
                    row = height - 1;
                if (col >= width)
                    col = width - 1;
                var tmpData = data[row * width + col];
                var tmpCount = count[row * width + col];
                data[row * width + col] = (tmpData* tmpCount + z) /(tmpCount+1);
                count[row * width + col]++;
            }

#endregion

#region 采样会导致数据缺失，需要对缺失的点进行插值，插值条件【像素点的采样数量，count = 0 】【且周围8个像素的count!=0】，插值范围【周围8个像素中，非空的像素的均值】【插值之后，count为负数】

            for (int i = 1; i < height - 1; i++)
            {
                for (int j = 1; j < width - 1; j++)
                {
                    if (count[i * width + j] > 0)
                        continue;

                    var tc = count[(i - 1) * width + j];
                    var bc = count[(i + 1) * width + j];
                    var lc = count[i * width + j - 1];
                    var rc = count[i * width + j + 1];

                    var tlc = count[(i - 1) * width + j - 1];
                    var trc = count[(i - 1) * width + j + 1];
                    var blc = count[(i + 1) * width + j - 1];
                    var brc = count[(i + 1) * width + j + 1];

                    if (tc <= 0 &&
                        bc <= 0 &&
                        lc <= 0 &&
                        rc <= 0 &&
                        tlc <= 0 &&
                        trc <= 0 &&
                        blc <= 0 &&
                        brc <= 0)
                        continue;

                    var bd = data[(i + 1) * width + j];
                    var td = data[(i - 1) * width + j];
                    var ld = data[i * width + j - 1];
                    var rd = data[i * width + j + 1];

                    var tld = data[(i - 1) * width + j - 1];
                    var trd = data[(i - 1) * width + j + 1];
                    var bld = data[(i + 1) * width + j - 1];
                    var brd = data[(i + 1) * width + j + 1];

                    double tmpSum = 0;
                    int tmpCount = 0;
                    if (tc > 0)
                    {
                        tmpSum += td;
                        tmpCount++;
                    }
                    if (bc > 0)
                    {
                        tmpSum += bd;
                        tmpCount++;
                    }
                    if (lc > 0)
                    {
                        tmpSum += ld;
                        tmpCount++;
                    }
                    if (rc > 0)
                    {
                        tmpSum += rd;
                        tmpCount++;
                    }

                    if (tlc > 0)
                    {
                        tmpSum += tld;
                        tmpCount++;
                    }
                    if (trc > 0)
                    {
                        tmpSum += trd;
                        tmpCount++;
                    }
                    if (blc > 0)
                    {
                        tmpSum += bld;
                        tmpCount++;
                    }
                    if (brc > 0)
                    {
                        tmpSum += brd;
                        tmpCount++;
                    }

                    data[i * width + j] = tmpSum / tmpCount;
                    count[i * width + j] = -tmpCount;
                }
            }

#endregion

#region 测试功能，输出采样之后的结果

            bool test = false;
            if (test)
            {
                var inverse = linear3Dtrans.Inverse();
                for (int i = 1; i < height - 1; i++)
                {
                    for (int j = 1; j < width - 1; j++)
                    {
                        int id = i * width + j;
                        if (count[id] == 0)
                        {
                            xs[id] = double.NaN;
                            ys[id] = double.NaN;
                            zs[id] = double.NaN;
                        }
                        else
                        {
                            var vec = inverse.MapPoint(new Cog3DVect3(j, i, data[id]));
                            xs[id] = vec.X;
                            ys[id] = vec.Y;
                            zs[id] = vec.Z;
                        }
                    }
                }
                RVC_CSharp_Tool.SavePlyBinary(xs, ys, zs, "./PointCloudSampling.ply");
            }

#endregion

#region 给图像赋值

            CogImage16Grey cogImage16Grey = new CogImage16Grey(width, height);
            CogImage8Grey cogImage8Grey = new CogImage8Grey(width, height);
            for (int row = 0; row < height; ++row)
            {
                for (int col = 0; col < width; ++col)
                {
                    byte mask = 0;
                    ushort grey = 0;

                    int c = count[row * width + col];
                    if (c == 0)
                    {
                        mask = 0;
                        grey = 0;
                    }
                    else
                    {
                        mask = 255;
                        grey = (ushort)(data[row * width + col]);
                    }

                    int colInvert = xInvert ? width - 1 - col : col;
                    int rowInvert = yInvert ? height - 1 - row : row;

                    cogImage16Grey.SetPixel(colInvert, rowInvert, grey);
                    cogImage8Grey.SetPixel(colInvert, rowInvert, mask);
                }
            }

#endregion

            return new CogImage16Range(cogImage16Grey, cogImage8Grey, linear3Dtrans);
        }

        /// <summary>
        /// CogImage16Range数据保存
        /// 你需要先获取 VisionPro 的 License
        /// </summary>
        /// <param name="range">CogImage16Range格式的数据</param>
        /// <param name="filename">保存的文件路径</param>
        public static bool Save(this CogImage16Range range, string filename = "./VisionProPointCloud.idb")
        {
            CogImageFileTool imfiletool = new CogImageFileTool();
            imfiletool.InputImage = range;
            imfiletool.Operator.Open(filename, CogImageFileModeConstants.Write);
            imfiletool.Run();
            imfiletool.Operator.Close();
            return File.Exists(filename);
        }
    }

}
#endif
