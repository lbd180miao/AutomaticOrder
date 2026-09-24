// Copyright (c) RVBUST, Inc - All rights reserved.
#pragma once

#include <RVC/RVC.h>

namespace RVC {
struct RVC_EXPORT CodedCircleMarkerType {
    int N;
    double r1_to_r0_ratio;
    double r2_to_r0_ratio;

    CodedCircleMarkerType() : N(12), r1_to_r0_ratio(2.0), r2_to_r0_ratio(3.0) {}
};

struct RVC_EXPORT CodedCircleMarker {
    double x;
    double y;
    int code;

    CodedCircleMarker() : x(0), y(0), code(0) {}
};

/**
 * @brief Use the point cloud captured by the RVC camera to get the point cloud of the external camera.
 *        To generate coded circle marker pattern, see: Examples/Python/Utils/GenerateCodedCircle.py
 *
 * @param image: Input image. The image should be neither too bright nor too dark. The radius of the circle in the middle
 * of the coding circle should be greater than 5 pixels.
 * @param type: The type of the coded circle marker. Different types of coded circle markers should have different
 * parameters.
 * @param marker_num: The number of coded circle markers detected.
 * @param markers: The coded circle markers detected. Note: maximum number of markers detected is 1000. If the number of
 * markers in the image is greater than 1000, random 1000 markers will be returned. User should allocate enough markers
 * memory and pass the markers pointer in.
 *
 * Usage example: MarkerDetectionExample.cpp / MarkerDetectionExample.py / MarkerDetection.cs
 */
RVC_EXPORT void DetectCodedCircleMarker(const RVC::Image &image, const RVC::CodedCircleMarkerType &type, int *marker_num,
                                        CodedCircleMarker markers[1000]);
}  // namespace RVC

namespace RVC {

/**
 * @brief Detect concentric circle markers from a 2D image.
 *
 * The function searches up to 1000 ring centers using the default parameters of the concentric-circle detector and
 * outputs their pixel coordinates.
 *
 * @param image Input 2D image.
 * @param marker_num Output pointer that receives the number of detected markers.
 * @param pixel_xy Output buffer with a minimum size of 2000 doubles. Each marker consumes two continuous values
 * (x, y). The caller must allocate and manage this buffer.
 *
 * @return
 *  0: Success.
 * -1: The image is invalid.
 *
 * Usage example: MarkerDetectionExample.cpp / MarkerDetectionExample.py / MarkerDetection.cs
 */
RVC_EXPORT int DetectConcentricCircleMarker2d(const RVC::Image &image, int *marker_num, double pixel_xy[2000]);

/**
 * @brief Detect concentric circle markers with 2d and 3d coordinates.
 *
 * @param image Input 2D image.
 * @param pointmap Input pointmap. It should have the same size as the input image. 
 * @param marker_num Output pointer that receives the number of detected markers.
 * @param pixel_xy Output buffer with a minimum size of 2000 doubles. Each marker consumes two continuous values
 * (x, y). The caller must allocate and manage this buffer.
 * @param point_xyz Output buffer with a minimum size of 2000 doubles. Each marker consumes two continuous values
 * (x, y, z). The caller must allocate and manage this buffer.
 *
 * @return
 *  0: Success.
 * -1: The image is invalid.
 * -2: The point map is invalid.
 * -3: Image and point map have different size.
 * -4: The point cloud is incomplete around at least one detected center.
 *
 * Usage example: MarkerDetectionExample.cpp / MarkerDetectionExample.py / MarkerDetection.cs
 */
RVC_EXPORT int DetectConcentricCircleMarker3d(const RVC::Image &image, const RVC::PointMap &pointmap, int *marker_num,
                                              double pixel_xy[2000], double point_xyz[3000]);
}

namespace RVC {
/**
 * @brief Put black background white circle asymmetric grid calibration board and test camera accuracy.
 * Test Method: Calculate the distance between the farthest pair of points along the height axis of the calibration board.
 * Compare it with the true distance to get the accuracy percentage. To ensure success and accuracy, please note:
 * 1. The calibration board must be in good condition, without bending, scratches, or damage.
 * 2. Adjust 2D and 3D exposure time ​​to make the 2D image clear and the point cloud complete and in high quality.
 * 3. The calibration board needs to be placed near the working distance.
 * 4. For accurate results, the radius of the center of the calibration board is recommended to be more than 8 pixels.
 * 5. For accurate results, the calibration board should be aligned approximately perpendicular to the camera depth axis.
 * 
 *
 * @param image 2D image
 * @param pointmap 3D point map
 * @param camera_intrinsic Pass in camera intrinsics to get more accurate result, which can be obtained from
 * GetIntrinsicParameters(). If you do not have camera intrinsics, pass in nullptr.
 * @param camera_distortion Pass in camera distortion to get more accurate result, which can be obtained from
 * GetIntrinsicParameters(). If you do not have camera intrinsics, pass in nullptr.
 * @param caliboard_pattern_size_width The width of the calibration board pattern size.
 * @param caliboard_pattern_size_height The height of the calibration board pattern size.
 * @param caliboard_circle_center_standard_3d_distance_step The standard distance step between the centers of the
 * circles on the calibration board. Unit: meter. Reference value(m): A1:0.112 A2:0.08 A3:0.056 A4:*0.04 A5:0.028
 * A6:0.02 A7:0.014 A8:0.01 A9:0.007 A10:0.0048
 *
 * @return
 * circle_center_2d: circle centers detected on 2D images. User should allocate circle num * 2 double type memory and pass
 * the pointer in.
 * circle_center_3d: circle centers detected on 3D point map. User should allocate circle num * 3 double type memory and pass
 * the pointer in.
 * measuring_distance：Distance between the farthest pair of points along the height axis of the calibration board. Unit: meter.
 * error_percentage: (measuring_distance - true_distance) / true_distance * 100
 *
 * error code return:
 * 0: success
 * -1: Image is not valid.
 * -2: Pointmap is not valid.
 * -3: Image size and pointmap size do not match.
 * -4: Caliboard_pattern_size_height is not an odd number.
 * -5: Can not find circle in 2D image. Make sure the white circle centers are not too bright nor too dark.
 * -6: There is no point cloud at the center of some circles on the calibration board. Please check every center in
 * pointmap and adjust the exposure parameters.
 *
 * Usage example: TestAccuracyExample.cpp / TestAccuracyExample.py / TestAccuracy.cs
 */
RVC_EXPORT int TestAccuracy(const RVC::Image &image, const RVC::PointMap &pointmap, const float camera_intrinsic[9],
                            const float camera_distortion[5], const int caliboard_pattern_size_width,
                            const int caliboard_pattern_size_height,
                            const float caliboard_circle_center_standard_3d_distance_step, float *circle_center_2d,
                            float *circle_center_3d, float &measuring_distance, float &error_percentage);
}  // namespace RVC