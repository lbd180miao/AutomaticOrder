// Copyright (c) RVBUST, Inc - All rights reserved.
#pragma once

#include <RVC/RVC.h>

#include "MarkerDetection.h"

namespace RVC {
// Usage example: PointCloudStitchingExample.cpp / PointCloudStitchingExample.py
// User guild: RVCSDK/docs/PointCloudStitchingManual.pdf

/**
 * @brief Use the coded circle marker to get the transformation of point_map1 relative to point_map0 coordinate system.
 *
 * Notice:
 * 1. The image should be neither too bright nor too dark.
 * 2. The radius of the circle in the middle of the coded marker should be greater than 5 pixels (10 pixels is
 * recommended).
 * 3. The point cloud quality of the circle in the middle of the encoded marker should be good.
 * 4. There must be at least 3 circles in the shared field of view (6 or more circles is recommended), and they cannot
 * be in a line.
 *
 * @return
 * error code:
 *  0: succeeds.
 * -1: fails. Because point_map0 or point_map1 is not valid. Or the size of point_map is not equal to the size of image.
 * -2: fails. Because image0 or image1 is not valid.
 * -3: fails. Because not enough markers are detected.
 * -4: fails. Because too few circles are in the public field of view.
 * -5: fails. Because point cloud of markers is not good.
 * -6: fails. Because some markers have been moved.
 */
RVC_EXPORT int GetTwoCameraTransformByCodedCircleMarker(const RVC::PointMap &point_map0, const RVC::Image &image0,
                                                        const RVC::PointMap &point_map1, const RVC::Image &image1,
                                                        const RVC::CodedCircleMarkerType &type, double R[9],
                                                        double t[3]);

/**
 * @brief Use the coded circle marker to get the transformation of point_map1 relative to point_map0 coordinate system.
 * This variant requires captures at two working distances (near and far) for both cameras to obtain a more accurate
 * R,t.
 *
 * Notice:
 * 1. The image should be neither too bright nor too dark.
 * 2. The radius of the circle in the middle of the coded marker should be greater than 5 pixels (10 pixels is
 * recommended).
 * 3. The point cloud quality of the circle in the middle of the encoded marker should be good.
 * 4. At each distance, there must be at least 3 circles in the shared field of view (6 or more recommended).
 *
 * @param camera0_point_map0 First-distance point cloud from camera 0.
 * @param camera0_image0 First-distance 2D image from camera 0.
 * @param camera1_point_map0 First-distance point cloud from camera 1.
 * @param camera1_image0 First-distance 2D image from camera 1.
 * @param camera0_point_map1 Second-distance point cloud from camera 0.
 * @param camera0_image1 Second-distance 2D image from camera 0.
 * @param camera1_point_map1 Second-distance point cloud from camera 1.
 * @param camera1_image1 Second-distance 2D image from camera 1.
 * @param type Coded circle marker type (pattern specification).
 * @param R Output rotation matrix.
 * @param t Output translation vector.
 *
 * @return error code:
 *  0: succeeds.
 * -1: fails. Because point_map is not valid. Or the size of point_map is not equal to the size of image.
 * -2: fails. Because image is not valid.
 * -3: fails. Because not enough markers are detected.
 * -4: fails. Because too few circles are in the public field of view.
 * -5: fails. Because point cloud of markers is not good.
 * -6: fails. Because some markers have been moved.
 */
RVC_EXPORT int GetTwoCameraTransformByCodedCircleMarkerTwoDistance(
    const RVC::PointMap &camera0_point_map0, const RVC::Image &camera0_image0, const RVC::PointMap &camera1_point_map0,
    const RVC::Image &camera1_image0, const RVC::PointMap &camera0_point_map1, const RVC::Image &camera0_image1,
    const RVC::PointMap &camera1_point_map1, const RVC::Image &camera1_image1, const RVC::CodedCircleMarkerType &type,
    double R[9], double t[3]);

/**
 * @brief Transform the point cloud point_map1 to the coordinate system of point_map0.
 *        point_map1 = R * point_map1 + t
 */
RVC_EXPORT void TransformPointCloud(const double R[9], const double t[3], RVC::PointMap &point_map1);
}  // namespace RVC
