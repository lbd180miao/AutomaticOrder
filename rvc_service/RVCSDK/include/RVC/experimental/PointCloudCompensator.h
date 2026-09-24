// Copyright (c) RVBUST, Inc - All rights reserved.
#pragma once

#include <RVC/RVC.h>

namespace RVC {
/*
 * When the camera is running for a long time, the internal and external parameters of the camera may change due to
 * changes in the temperature of the camera itself or changes in ambient temperature, resulting in changes in point
 * cloud accuracy.
 *
 * If there is no condition to calibrate the camera, we can use this class to compensate the point cloud due to changes
 * of the camera parameters. This can be regarded as a simple calibration. The basic idea is to fix the marker at a
 * suitable location in the workspace or on the robot arm; let the camere at the same position capture the fixed marker
 * each time, and compare the point cloud changes of the marker to obtain the compensation model.
 *
 * There are three steps required to compensate for the point cloud:
 * 1. Initialize.
 *    Set up a reference point cloud(pm_reference). It is best to perform this step immediately after the camera
 * completes hand-eye calibration.
 *    If using calibration board, the calibration board should occupy at least 1/4 of the field of view.
 *    If using concentric circles, Use three or more concentric circles of markers, spread out in the corners of
 * the field of view to cover the most area.
 *    For correct recognition, it should be ensured that the markers in the picture are clearly visible, not too dark
 * or too bright, and that the point cloud near the center of the marker circle is complete.
 *    It is recommended to place the marker near the actual working distance. If the working range is relatively large,
 * place it in the middle of the working distance if possible.
 *    The reference point cloud should be under the camera coordinate system.
 * 2. Update.
 *    When working normally and taking n frames, we need to update the compensation model.
 *    Keep the camera in the same position as it was initialized and capture fixed markers. The compensation model will
 * be updated and be used to compensate the point cloud. The quality of image and point cloud of the fixed marker should
 * be good as mentioned in the initialization step.
 * 3. Apply.
 *    The point cloud passed in will be compensated using the compensation model obtained in the update step.
 *
 * Currently we support two types of markers. The first is 4*11 calibration board and the second is concentric circle.
 *
 * Note: If we want to compensate the point cloud in LineScan mode, we can use the point cloud captured in Ultra mode to
 * initialize and update the compensation model, and then apply to the point cloud in LineScan mode.
 *
 * Usage example: PointCloudCompensating.cpp / PointCloudCompensating.py
 * The API is experimental and may change in the future.
 */
class RVC_EXPORT Compensator_FixedMarkers {
public:
    Compensator_FixedMarkers();
    ~Compensator_FixedMarkers();

    /**
     * @brief Initialize compensation model.
     *
     * @param markerType: 0 for 4*11 calibration board, 1 for concentric circle.
     * @param pm_reference: Point cloud must be under camera coordinate system.
     * @param img_reference: The white circle of markers should be neither too bright nor too dark.
     * @param intrinsics: camera intrinsics.
     * @param distortion: camera distortion.
     *
     * @return
     * error code:
     *  0: succeeds.
     * -1: fails. Because pm is not valid.
     * -2: fails. Because image is not valid.
     * -3: fails. Because image is not good and it fails to detect markers.
     * -4: fails. Because point cloud of markers is not good.
     */
    int Initialize(const RVC::PointMap &pm_reference, const RVC::Image &img_reference, int markerType);

    /**
     * @brief update compensation model.
     *
     * @param pm: Point cloud must be under camera coordinate system.
     * @param img: The white circle in the markers should be neither too bright nor too dark.
     *
     * @return driftDistance: drift distance of current pm compared to pm_reference.
     * @return error code:
     *  0: succeeds.
     * -1: fails. Because Initialize() is not called before.
     * -2: fails. Because pm is not valid.
     * -3: fails. Because image is not valid.
     * -4: fails. Because image is not good and it fails to detect markers.
     * -5: fails. Because the relative positional relationship between the camera and fixed markers has changed compared
     *            to the initialization step.
     * -6: fails. Because point cloud of markers is not good.
     */
    int Update(const RVC::PointMap &pm, const RVC::Image &img, double &driftDistance);

    /**
     * @brief This will compensate the pm using the compensation model.
     *
     * @param pm: Point cloud must be under camera coordinate system.
     *
     * @return
     * error code:
     *  0: succeeds.
     * -1: fails. Because Update() is not called before or Update() fails.
     * -2: fails. Because pm is not valid.
     */
    int Apply(RVC::PointMap &pm);

private:
    class Impl;
    Impl *pImpl;
};
}  // namespace RVC
