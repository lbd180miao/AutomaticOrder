// Copyright (c) RVBUST, Inc - All rights reserved.
#pragma once

#include <RVC/RVC.h>

namespace RVC {
/**
 * @brief The user needs to calibrate the external camera by themselves first(The distortion parameter model
 * is [k1, k2, p1, p2, k3]).
 * Then capture the calibration board at three distances: near, middle and far, and at the same time use
 * the external camera to capture three coresponding images. Finally, call this API to get the extrinsic matrix of the
 * external camera to the RVC camera. The camera resolution does not need to be the same as the RVC camera resolution.
 * The calibration board should large enough, and the minimum recommended size is no less than 1/20 of the field of
 * view.
 * Usage example: GetExternalColorCameraPointMap.cpp / GetExternalColorCameraPointMap.py
 * The API is experimental and may change in the future.
 */

/**
 * @param internal_camera_image0: First image taken by the RVC camera in the nearest distance.
 * @param internal_camera_point_map0: First point map taken by the RVC camera under camera coordinate system.
 * @param external_camera_image_data0: First corresponding image taken by the external camera.
 * @param internal_camera_image1: Second image taken by the RVC camera in the middle distance.
 * @param internal_camera_point_map1: Second point map taken by the RVC camera under camera coordinate system.
 * @param external_camera_image_data1: Second corresponding image taken by the external camera.
 * @param internal_camera_image2: Third image taken by the RVC camera in the furthest distance.
 * @param internal_camera_point_map2: Third point map taken by the RVC camera under camera coordinate system.
 * @param external_camera_image_data2: Third corresponding image taken by the external camera.
 * @param external_camera_width: The width of the external camera image.
 * @param external_camera_height: The height of the external camera image.
 * @param external_camera_intrinsic_matrix: The 3 * 3 intrinsic matrix of the external camera.
 * @param external_camera_camera_distortion: The 5 distortion parameters of the external camera. The order is [k1, k2,
 * p1, p2, k3].
 *
 * @return
 * external_camera_extrinsic_matrix:
 * The 4 * 4 extrinsic matrix of the external camera. Note that users need to allocate memory outside the API first, and
 * then pass the pointer in.
 *
 * @return
 * error:
 * Reprojection error(unit: pixel). The smaller the value, the better the extrinsic matrix calibration result.
 *
 * @return
 * error code:
 * 0: succeeds.
 * -1: fails. Because internal_camera_image0 is not good and it fails to detect calibration board.
 * -2: fails. Because internal_camera_point_map0 is not good and it fails to extract the circle center of calibration
 * board point cloud.
 * -3: fails. Because external_camera_image0 is not good and it fails to detect calibration board.
 * -4: fails. Because internal_camera_image1 is not good and it fails to detect calibration board.
 * -5: fails. Because internal_camera_point_map1 is not good and it fails to extract the circle center of calibration
 * board point cloud.
 * -6: fails. Because external_camera_image1 is not good and it fails to detect calibration board.
 * -7: fails. Because internal_camera_image2 is not good and it fails to detect calibration board.
 * -8: fails. Because internal_camera_point_map2 is not good and it fails to extract the circle center of calibration
 * board point cloud.
 * -9: fails. Because external_camera_image2 is not good and it fails to detect calibration board.
 */
RVC_EXPORT int GetExternalCameraExtrinsicMatrix(
    const Image &internal_camera_image0, const PointMap &internal_camera_point_map0,
    const unsigned char *external_camera_image_data0, const Image &internal_camera_image1,
    const PointMap &internal_camera_point_map1, const unsigned char *external_camera_image_data1,
    const Image &internal_camera_image2, const PointMap &internal_camera_point_map2,
    const unsigned char *external_camera_image_data2, int external_camera_width, int external_camera_height,
    const float *external_camera_intrinsic_matrix,
    const float *external_camera_camera_distortion, float *external_camera_extrinsic_matrix,
    double &reprojection_error);

/**
 * @brief Use the point cloud captured by the RVC camera to get the point cloud of the external camera.
 *
 * @param internal_camera_point_map: Use GetPointMap() to get the 3D point map captured by the RVC camera. The point map
 * should be under camera coordinate system.
 * @param external_camera_width: The width of the external camera image.
 * @param external_camera_height: The height of the external camera image.
 * @param external_camera_intrinsic_matrix: The 3 * 3 intrinsic matrix of the external camera.
 * @param external_camera_camera_distortion: The 5 distortion parameters of the external camera. The order is [k1, k2,
 * p1, p2, k3].
 * @param external_camera_extrinsic_matrix: The 4 * 4 extrinsic matrix of the external camera obtained by
 * GetExternalCameraExtrinsicMatrix() above.
 *
 * @return
 * external_camera_point_map:
 * The point map of the external camera. The resolution of the external camera point map is the same as the external
 * camera image.
 */
RVC_EXPORT PointMap GetExternalCameraPointMap(const PointMap &internal_camera_point_map,
                                              const int external_camera_width, const int external_camera_height,
                                              const float *external_camera_intrinsic_matrix,
                                              const float *external_camera_camera_distortion,
                                              const float *external_camera_extrinsic_matrix);
}  // namespace RVC