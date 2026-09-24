cmake_minimum_required(VERSION 3.10)
project("RVC_CSharp" CSharp)


set(RVC_VERSION_MAJOR 1)

set(RVC_VERSION_MINOR 15)
set(RVC_VERSION_PATCH 1)
set(RVC_VERSION_PATCH_0 1)


add_compile_definitions(RVC_VERSION_MAJOR=${RVC_VERSION_MAJOR})
add_compile_definitions(RVC_VERSION_MINOR=${RVC_VERSION_MINOR})
add_compile_definitions(RVC_VERSION_PATCH=${RVC_VERSION_PATCH})
add_compile_definitions(RVC_VERSION_PATCH_0=${RVC_VERSION_PATCH_0})
add_compile_definitions(RVCSDK_VERSION="${RVC_VERSION_MAJOR}.${RVC_VERSION_MINOR}.${RVC_VERSION_PATCH}")

set(MYPROJECT_VERSION "${RVC_VERSION_MAJOR}.${RVC_VERSION_MINOR}.${RVC_VERSION_PATCH_0}")
set(MYPROJECT_FILE_VERSION "${RVC_VERSION_MAJOR}.${RVC_VERSION_MINOR}.${RVC_VERSION_PATCH}")
set(MYPROJECT_PRODUCT_VERSION "${RVC_VERSION_MAJOR}.${RVC_VERSION_MINOR}.${RVC_VERSION_PATCH}")
set(MYPROJECT_COMPANY_NAME "RVBUST, Inc")
set(MYPROJECT_PRODUCT_NAME "RVBUST RVC CSharp SDK")
set(MYPROJECT_COPYRIGHT "Copyright (C) RVBUST, Inc")

configure_file(
    AssemblyInfo.cs.in
    ${CMAKE_CURRENT_BINARY_DIR}/AssemblyInfo.cs
    @ONLY
)

include(CSharpUtilities)

SET(EXECUTABLE_OUTPUT_PATH ${CMAKE_BINARY_DIR}/bin)
SET(LIBRARY_OUTPUT_PATH ${CMAKE_BINARY_DIR}/bin)

add_subdirectory(RVC_C)

add_library(RVC_CSharp SHARED
    RVC_CSharp.cs
    RVC_CSharp_Tool.cs
    ${CMAKE_CURRENT_BINARY_DIR}/AssemblyInfo.cs
)

set_target_properties(RVC_CSharp 
PROPERTIES DOTNET_ALLOW_UNSAFE_CODE   "True" 
DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
if (CMAKE_GENERATOR MATCHES "Visual Studio")
    target_compile_options(RVC_CSharp PRIVATE /unsafe)
endif()
set_property(TARGET RVC_CSharp PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")

target_link_libraries(RVC_CSharp RVC_C)

set_property(TARGET RVC_CSharp PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

option(OpenCV_Enable "whether use OpenCV  for Extension Function" OFF)
option(Halcon_Enable "whether use Halcon for Extension Function. Assuming you have obtainedt lincenses." OFF)
option(VisionPro_Enable "whether use Halcon for Extension Function. Assuming you have obtainedt lincenses." OFF)

add_library(RVC_CSharp_Extension SHARED
    Halcon_Extension.cs
    Opencv_Extension.cs
    VisionPro_Extension.cs
)

if(OpenCV_Enable AND Halcon_Enable)
    set_property(TARGET RVC_CSharp_Extension PROPERTY VS_PACKAGE_REFERENCES "OpenCvSharp4.Windows_4.1.1.20191216;HalconDotNet_19.11.0")
elseif(OpenCV_Enable)
    set_property(TARGET RVC_CSharp_Extension PROPERTY VS_PACKAGE_REFERENCES "OpenCvSharp4.Windows_4.1.1.20191216")
elseif(Halcon_Enable)
    set_property(TARGET RVC_CSharp_Extension PROPERTY VS_PACKAGE_REFERENCES "HalconDotNet_19.11.0")
endif()

if(OpenCV_Enable)
    add_compile_definitions(OpenCV_Enable)
endif()

if(Halcon_Enable)
    add_compile_definitions(Halcon_Enable)
endif()

if(VisionPro_Enable)
    add_compile_definitions(VisionPro_Enable)
endif()

set_property(TARGET RVC_CSharp_Extension PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_CSharp_Extension PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")

target_link_libraries(RVC_CSharp_Extension RVC_CSharp)

if(VisionPro_Enable)
    set_property(TARGET RVC_CSharp_Extension PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"

        "Cognex.VisionPro.Core.dll"
        "Cognex.VisionPro.CorePlus.dll"
        "Cognex.VisionPro.dll"
        "Cognex.VisionPro.ImageFile.dll"
        "Cognex.VisionPro.Interop.Core.dll"

        "Cognex.VisionPro3D.Controls.dll"
        "Cognex.VisionPro3D.Core.dll"
        "Cognex.VisionPro3D.Display.Controls.dll"
        "Cognex.VisionPro3D.dll"
        "Cognex.VisionPro3D.Graphic.dll"
    )
else()
    set_property(TARGET RVC_CSharp_Extension PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )
endif()

add_executable(RVC_Example_CameraTest
    CameraTest.cs
)

set_property(TARGET RVC_Example_CameraTest PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_CameraTest PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")

target_link_libraries(RVC_Example_CameraTest RVC_CSharp RVC_CSharp_Extension)

set_property(TARGET RVC_Example_CameraTest PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_CaptureOptions_X1
    CaptureOptions_X1.cs
)

set_property(TARGET RVC_Example_CaptureOptions_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_CaptureOptions_X1 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_CaptureOptions_X1 RVC_CSharp RVC_CSharp_Extension)

if(VisionPro_Enable)
    set_property(TARGET RVC_Example_CaptureOptions_X1 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"

        "Cognex.VisionPro.Core.dll"
        "Cognex.VisionPro.CorePlus.dll"
        "Cognex.VisionPro.dll"
        "Cognex.VisionPro.ImageFile.dll"
        "Cognex.VisionPro.Interop.Core.dll"

        "Cognex.VisionPro3D.Controls.dll"
        "Cognex.VisionPro3D.Core.dll"
        "Cognex.VisionPro3D.Display.Controls.dll"
        "Cognex.VisionPro3D.dll"
        "Cognex.VisionPro3D.Graphic.dll"
    )
else()
    set_property(TARGET RVC_Example_CaptureOptions_X1 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )
endif()

add_executable(RVC_Example_CaptureOptions_X2
    CaptureOptions_X2.cs
)

set_property(TARGET RVC_Example_CaptureOptions_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_CaptureOptions_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_CaptureOptions_X2 RVC_CSharp RVC_CSharp_Extension)
if(VisionPro_Enable)
set_property(TARGET RVC_Example_CaptureOptions_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"

    "Cognex.VisionPro.Core.dll"
    "Cognex.VisionPro.CorePlus.dll"
    "Cognex.VisionPro.dll"
    "Cognex.VisionPro.ImageFile.dll"
    "Cognex.VisionPro.Interop.Core.dll"

    "Cognex.VisionPro3D.Controls.dll"
    "Cognex.VisionPro3D.Core.dll"
    "Cognex.VisionPro3D.Display.Controls.dll"
    "Cognex.VisionPro3D.dll"
    "Cognex.VisionPro3D.Graphic.dll"
)
else()
    set_property(TARGET RVC_Example_CaptureOptions_X2 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )
endif()

add_executable(RVC_Example_MultiCamera
    MultiCamera.cs
)

set_property(TARGET RVC_Example_MultiCamera PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_MultiCamera PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_MultiCamera RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_MultiCamera PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_QuickCapture_X1
    QuickCapture_X1.cs
)

set_property(TARGET RVC_Example_QuickCapture_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_QuickCapture_X1 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_QuickCapture_X1 RVC_CSharp RVC_CSharp_Extension)
if(VisionPro_Enable)
    set_property(TARGET RVC_Example_QuickCapture_X1 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"

        "Cognex.VisionPro.Core.dll"
        "Cognex.VisionPro.CorePlus.dll"
        "Cognex.VisionPro.dll"
        "Cognex.VisionPro.ImageFile.dll"
        "Cognex.VisionPro.Interop.Core.dll"

        "Cognex.VisionPro3D.Controls.dll"
        "Cognex.VisionPro3D.Core.dll"
        "Cognex.VisionPro3D.Display.Controls.dll"
        "Cognex.VisionPro3D.dll"
        "Cognex.VisionPro3D.Graphic.dll"
    )
else()
    set_property(TARGET RVC_Example_QuickCapture_X1 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )
endif()

if(Halcon_Enable)

    add_executable(RVC_Example_Halcon_Save_Data_X1
    Halcon_Save_Data_X1.cs
    )

    set_property(TARGET RVC_Example_Halcon_Save_Data_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
    set_property(TARGET RVC_Example_Halcon_Save_Data_X1 PROPERTY WIN64_EXECUTABLE TRUE)
    set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
    target_link_libraries(RVC_Example_Halcon_Save_Data_X1 RVC_CSharp RVC_CSharp_Extension)
    set_property(TARGET RVC_Example_Halcon_Save_Data_X1 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )

endif()

if(Halcon_Enable)

    add_executable(RVC_Example_Halcon_Save_Data_X2
    Halcon_Save_Data_X2.cs
    )

    set_property(TARGET RVC_Example_Halcon_Save_Data_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
    set_property(TARGET RVC_Example_Halcon_Save_Data_X2 PROPERTY WIN64_EXECUTABLE TRUE)
    set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
    target_link_libraries(RVC_Example_Halcon_Save_Data_X2 RVC_CSharp RVC_CSharp_Extension)
    set_property(TARGET RVC_Example_Halcon_Save_Data_X2 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )
endif()

add_executable(RVC_Example_QuickCapture_X2
    QuickCapture_X2.cs
)

set_property(TARGET RVC_Example_QuickCapture_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_QuickCapture_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_QuickCapture_X2 RVC_CSharp RVC_CSharp_Extension)
if(VisionPro_Enable)
    set_property(TARGET RVC_Example_QuickCapture_X2 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"

        "Cognex.VisionPro.Core.dll"
        "Cognex.VisionPro.CorePlus.dll"
        "Cognex.VisionPro.dll"
        "Cognex.VisionPro.ImageFile.dll"
        "Cognex.VisionPro.Interop.Core.dll"

        "Cognex.VisionPro3D.Controls.dll"
        "Cognex.VisionPro3D.Core.dll"
        "Cognex.VisionPro3D.Display.Controls.dll"
        "Cognex.VisionPro3D.dll"
        "Cognex.VisionPro3D.Graphic.dll"
    )
else()
    set_property(TARGET RVC_Example_QuickCapture_X2 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )
endif()

add_executable(RVC_Example_SetSwingLineScanROI
    SetSwingLineScanROI.cs
)

set_property(TARGET RVC_Example_SetSwingLineScanROI PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_SetSwingLineScanROI PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")

target_link_libraries(RVC_Example_SetSwingLineScanROI RVC_CSharp RVC_CSharp_Extension)

set_property(TARGET RVC_Example_SetSwingLineScanROI PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_SwingLineScan
    SwingLineScan.cs
)

set_property(TARGET RVC_Example_SwingLineScan PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_SwingLineScan PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")

target_link_libraries(RVC_Example_SwingLineScan RVC_CSharp RVC_CSharp_Extension)

set_property(TARGET RVC_Example_SwingLineScan PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_FixedLineScan
    FixedLineScan.cs
)

set_property(TARGET RVC_Example_FixedLineScan PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_FixedLineScan PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_FixedLineScan RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_FixedLineScan PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_ControlProtectiveCover
    ControlProtectiveCover.cs
)
set_property(TARGET RVC_Example_ControlProtectiveCover PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_ControlProtectiveCover PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_ControlProtectiveCover RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_ControlProtectiveCover PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_CaptureCallback_X1
    CaptureCallback_X1.cs
)
set_property(TARGET RVC_Example_CaptureCallback_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_CaptureCallback_X1 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_CaptureCallback_X1 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_CaptureCallback_X1 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_CaptureCallback_X2
    CaptureCallback_X2.cs
)
set_property(TARGET RVC_Example_CaptureCallback_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_CaptureCallback_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_CaptureCallback_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_CaptureCallback_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

if(OpenCV_Enable)
    add_executable(RVC_Example_MarkerDetection
        MarkerDetection.cs
    )
    set_property(TARGET RVC_Example_MarkerDetection PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
    set_property(TARGET RVC_Example_MarkerDetection PROPERTY WIN64_EXECUTABLE TRUE)
    set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
    target_link_libraries(RVC_Example_MarkerDetection RVC_CSharp RVC_CSharp_Extension)
    set_property(TARGET RVC_Example_MarkerDetection PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )
endif()

add_executable(RVC_Example_PointCloudStitching
    PointCloudStitching.cs
)
set_property(TARGET RVC_Example_PointCloudStitching PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_PointCloudStitching PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_PointCloudStitching RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_PointCloudStitching PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_BinaryCompatibleAPIUseMethod
BinaryCompatibleAPIUseMethod.cs
)
set_property(TARGET RVC_Example_BinaryCompatibleAPIUseMethod PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_BinaryCompatibleAPIUseMethod PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_BinaryCompatibleAPIUseMethod RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_BinaryCompatibleAPIUseMethod PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_SaveEncodedImagesData
SaveEncodedImagesData.cs
)
set_property(TARGET RVC_Example_SaveEncodedImagesData PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_SaveEncodedImagesData PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_SaveEncodedImagesData RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_SaveEncodedImagesData PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_CaptureByX2
CaptureByX2.cs
)
set_property(TARGET RVC_Example_CaptureByX2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_CaptureByX2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_CaptureByX2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_CaptureByX2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_CaptureGigE
CaptureGigE.cs
)
set_property(TARGET RVC_Example_CaptureGigE PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_CaptureGigE PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_CaptureGigE RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_CaptureGigE PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_CaptureInContinueMode
CaptureInContinueMode.cs
)
set_property(TARGET RVC_Example_CaptureInContinueMode PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_CaptureInContinueMode PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_CaptureInContinueMode RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_CaptureInContinueMode PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_CaptureUSB
CaptureUSB.cs
)
set_property(TARGET RVC_Example_CaptureUSB PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_CaptureUSB PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_CaptureUSB RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_CaptureUSB PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

if(OpenCV_Enable)
    add_executable(RVC_Example_ConvertDepthMapToPointMap
    ConvertDepthMapToPointMap.cs
    )
    set_target_properties(RVC_Example_ConvertDepthMapToPointMap 
    PROPERTIES DOTNET_ALLOW_UNSAFE_CODE   "True" 
    DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
    if (CMAKE_GENERATOR MATCHES "Visual Studio")
        target_compile_options(RVC_Example_ConvertDepthMapToPointMap PRIVATE /unsafe)
    endif()
    set_property(TARGET RVC_Example_ConvertDepthMapToPointMap PROPERTY WIN64_EXECUTABLE TRUE)
    set_property(TARGET RVC_Example_ConvertDepthMapToPointMap PROPERTY VS_PACKAGE_REFERENCES "OpenCvSharp4.Windows_4.1.1.20191216")
    set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
    target_link_libraries(RVC_Example_ConvertDepthMapToPointMap RVC_CSharp RVC_CSharp_Extension)
    set_property(TARGET RVC_Example_ConvertDepthMapToPointMap PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )
endif()
add_executable(RVC_Example_GetAutoNoiseRemovalSetting
GetAutoNoiseRemovalSetting.cs
)
set_property(TARGET RVC_Example_GetAutoNoiseRemovalSetting PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetAutoNoiseRemovalSetting PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetAutoNoiseRemovalSetting RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetAutoNoiseRemovalSetting PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)
if(OpenCV_Enable)
    add_executable(RVC_Example_GetCaliBoardPose_X1
    GetCaliBoardPose_X1.cs
    )
    set_property(TARGET RVC_Example_GetCaliBoardPose_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
    set_property(TARGET RVC_Example_GetCaliBoardPose_X1 PROPERTY WIN64_EXECUTABLE TRUE)
    set_property(TARGET RVC_Example_GetCaliBoardPose_X1 PROPERTY VS_PACKAGE_REFERENCES "OpenCvSharp4.Windows_4.1.1.20191216")
    set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
    target_link_libraries(RVC_Example_GetCaliBoardPose_X1 RVC_CSharp RVC_CSharp_Extension)
    set_property(TARGET RVC_Example_GetCaliBoardPose_X1 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )
endif()

if(OpenCV_Enable)
    add_executable(RVC_Example_GetCaliBoardPose_X2
    GetCaliBoardPose_X2.cs
    )
    set_property(TARGET RVC_Example_GetCaliBoardPose_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
    set_property(TARGET RVC_Example_GetCaliBoardPose_X2 PROPERTY WIN64_EXECUTABLE TRUE)
    set_property(TARGET RVC_Example_GetCaliBoardPose_X2 PROPERTY VS_PACKAGE_REFERENCES "OpenCvSharp4.Windows_4.1.1.20191216")
    set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
    target_link_libraries(RVC_Example_GetCaliBoardPose_X2 RVC_CSharp RVC_CSharp_Extension)
    set_property(TARGET RVC_Example_GetCaliBoardPose_X2 PROPERTY VS_DOTNET_REFERENCES
        "Microsoft.CSharp"
        "System"
        "System.Linq"
        "System.Threading.Tasks"
        "System.Windows.Forms"
        "System.Runtime.InteropServices"
        "System.IO"
        "System.Drawing"
    )
endif()

add_executable(RVC_Example_GetCameraParameter
GetCameraParameter.cs
)
set_property(TARGET RVC_Example_GetCameraParameter PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetCameraParameter PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetCameraParameter RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetCameraParameter PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetConfidenceMap
GetConfidenceMap.cs
)
set_property(TARGET RVC_Example_GetConfidenceMap PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetConfidenceMap PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetConfidenceMap RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetConfidenceMap PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetCorrespondMap
GetCorrespondMap.cs
)
set_target_properties(RVC_Example_GetCorrespondMap 
PROPERTIES DOTNET_ALLOW_UNSAFE_CODE   "True" 
DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
if (CMAKE_GENERATOR MATCHES "Visual Studio")
    target_compile_options(RVC_Example_GetCorrespondMap PRIVATE /unsafe)
endif()
set_property(TARGET RVC_Example_GetCorrespondMap PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetCorrespondMap RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetCorrespondMap PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetDepthImage
GetDepthImage.cs
)
set_property(TARGET RVC_Example_GetDepthImage PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetDepthImage PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetDepthImage RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetDepthImage PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetDownsamplePointMap
GetDownsamplePointMap.cs
)
set_property(TARGET RVC_Example_GetDownsamplePointMap PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetDownsamplePointMap PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetDownsamplePointMap RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetDownsamplePointMap PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetExternalColorCameraPointMap
GetExternalColorCameraPointMap.cs
)
set_target_properties(RVC_Example_GetExternalColorCameraPointMap 
PROPERTIES DOTNET_ALLOW_UNSAFE_CODE   "True" 
DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
if (CMAKE_GENERATOR MATCHES "Visual Studio")
    target_compile_options(RVC_Example_GetExternalColorCameraPointMap PRIVATE /unsafe)
endif()
set_property(TARGET RVC_Example_GetExternalColorCameraPointMap PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetExternalColorCameraPointMap RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetExternalColorCameraPointMap PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetImageCorresponcePoint
GetImageCorresponcePoint.cs
)
set_target_properties(RVC_Example_GetImageCorresponcePoint 
PROPERTIES DOTNET_ALLOW_UNSAFE_CODE   "True" 
DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
if (CMAKE_GENERATOR MATCHES "Visual Studio")
    target_compile_options(RVC_Example_GetImageCorresponcePoint PRIVATE /unsafe)
endif()
set_property(TARGET RVC_Example_GetImageCorresponcePoint PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetImageCorresponcePoint RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetImageCorresponcePoint PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetNoiseRemovalPointMap
GetNoiseRemovalPointMap.cs
)
set_property(TARGET RVC_Example_GetNoiseRemovalPointMap PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetNoiseRemovalPointMap PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetNoiseRemovalPointMap RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetNoiseRemovalPointMap PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetNormalMap
GetNormalMap.cs
)
set_property(TARGET RVC_Example_GetNormalMap PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetNormalMap PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetNormalMap RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetNormalMap PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetPointMapSeperated
GetPointMapSeperated.cs
)
set_property(TARGET RVC_Example_GetPointMapSeperated PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetPointMapSeperated PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetPointMapSeperated RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetPointMapSeperated PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetSmoothPointMap
GetSmoothPointMap.cs
)
set_property(TARGET RVC_Example_GetSmoothPointMap PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetSmoothPointMap PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetSmoothPointMap RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetSmoothPointMap PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetValidPointMap
GetValidPointMap.cs
)
set_property(TARGET RVC_Example_GetValidPointMap PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetValidPointMap PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetValidPointMap RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetValidPointMap PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)


add_executable(RVC_Example_GetZFilteredPointMap
GetZFilteredPointMap.cs
)
set_property(TARGET RVC_Example_GetZFilteredPointMap PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetZFilteredPointMap PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetZFilteredPointMap RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetZFilteredPointMap PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_LaserCameraCapture
LaserCameraCapture.cs
)
set_property(TARGET RVC_Example_LaserCameraCapture PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_LaserCameraCapture PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_LaserCameraCapture RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_LaserCameraCapture PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_PointCloudCompensating
PointCloudCompensating.cs
)
set_property(TARGET RVC_Example_PointCloudCompensating PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_PointCloudCompensating PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_PointCloudCompensating RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_PointCloudCompensating PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_SaveColorPointMap
SaveColorPointMap.cs
)
set_property(TARGET RVC_Example_SaveColorPointMap PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_SaveColorPointMap PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_SaveColorPointMap RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_SaveColorPointMap PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_SaveLoadCameraSetting
SaveLoadCameraSetting.cs
)
set_property(TARGET RVC_Example_SaveLoadCameraSetting PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_SaveLoadCameraSetting PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_SaveLoadCameraSetting RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_SaveLoadCameraSetting PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_SaveLoadCaptureOptions
SaveLoadCaptureOptions.cs
)
set_property(TARGET RVC_Example_SaveLoadCaptureOptions PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_SaveLoadCaptureOptions PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_SaveLoadCaptureOptions RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_SaveLoadCaptureOptions PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_SetROI
SetROI.cs
)
set_property(TARGET RVC_Example_SetROI PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_SetROI PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_SetROI RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_SetROI PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_TestAccuracy
TestAccuracy.cs
)
set_property(TARGET RVC_Example_TestAccuracy PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_TestAccuracy PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_TestAccuracy RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_TestAccuracy PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_UseHelperClass
UseHelperClass.cs
)
set_property(TARGET RVC_Example_UseHelperClass PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_UseHelperClass PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_UseHelperClass RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_UseHelperClass PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_TruncatePointCloud
TruncatePointCloud.cs
)
set_property(TARGET RVC_Example_TruncatePointCloud PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_TruncatePointCloud PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_TruncatePointCloud RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_TruncatePointCloud PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_AutoHdrSetParam_X1
AutoHdrSetParam_X1.cs
)
set_property(TARGET RVC_Example_AutoHdrSetParam_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_AutoHdrSetParam_X1 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_AutoHdrSetParam_X1 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_AutoHdrSetParam_X1 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_AutoSetParam_X1
AutoSetParam_X1.cs
)
set_property(TARGET RVC_Example_AutoSetParam_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_AutoSetParam_X1 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_AutoSetParam_X1 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_AutoSetParam_X1 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_AutoSetParam_X2
AutoSetParam_X2.cs
)
set_property(TARGET RVC_Example_AutoSetParam_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_AutoSetParam_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_AutoSetParam_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_AutoSetParam_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_Capture2D_X1
Capture2D_X1.cs
)
set_property(TARGET RVC_Example_Capture2D_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_Capture2D_X1 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_Capture2D_X1 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_Capture2D_X1 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_HardWareTriggerFixedLineScanMode_X2
HardWareTriggerFixedLineScanMode_X2.cs
)
set_property(TARGET RVC_Example_HardWareTriggerFixedLineScanMode_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_HardWareTriggerFixedLineScanMode_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_HardWareTriggerFixedLineScanMode_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_HardWareTriggerFixedLineScanMode_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_HardWareTriggerFixedLineScanMode_EncoderStitching_X2
HardWareTriggerFixedLineScanMode_EncoderStitching_X2.cs
)
set_property(TARGET RVC_Example_HardWareTriggerFixedLineScanMode_EncoderStitching_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_HardWareTriggerFixedLineScanMode_EncoderStitching_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_HardWareTriggerFixedLineScanMode_EncoderStitching_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_HardWareTriggerFixedLineScanMode_EncoderStitching_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_FixedRateFixedLineScanMode_X2
FixedRateFixedLineScanMode_X2.cs
)
set_property(TARGET RVC_Example_FixedRateFixedLineScanMode_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_FixedRateFixedLineScanMode_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_FixedRateFixedLineScanMode_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_FixedRateFixedLineScanMode_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_FixedRateFixedLineScanMode_TimestampStitching_X2
FixedRateFixedLineScanMode_TimestampStitching_X2.cs
)
set_property(TARGET RVC_Example_FixedRateFixedLineScanMode_TimestampStitching_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_FixedRateFixedLineScanMode_TimestampStitching_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_FixedRateFixedLineScanMode_TimestampStitching_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_FixedRateFixedLineScanMode_TimestampStitching_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)


add_executable(RVC_Example_HDR_X1
HDR_X1.cs
)
set_property(TARGET RVC_Example_HDR_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_HDR_X1 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_HDR_X1 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_HDR_X1 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_SetTransformation_X1
SetTransformation_X1.cs
)
set_property(TARGET RVC_Example_SetTransformation_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_SetTransformation_X1 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_SetTransformation_X1 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_SetTransformation_X1 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_AutoHdrSetParam_X2
AutoHdrSetParam_X2.cs
)
set_property(TARGET RVC_Example_AutoHdrSetParam_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_AutoHdrSetParam_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_AutoHdrSetParam_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_AutoHdrSetParam_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_Auto2DExposureTime_X1
Auto2DExposureTime_X1.cs
)
set_property(TARGET RVC_Example_Auto2DExposureTime_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_Auto2DExposureTime_X1 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_Auto2DExposureTime_X1 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_Auto2DExposureTime_X1 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_Auto2DExposureTime_X2
Auto2DExposureTime_X2.cs
)
set_property(TARGET RVC_Example_Auto2DExposureTime_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_Auto2DExposureTime_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_Auto2DExposureTime_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_Auto2DExposureTime_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_Capture2D_X2
Capture2D_X2.cs
)
set_property(TARGET RVC_Example_Capture2D_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_Capture2D_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_Capture2D_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_Capture2D_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_HDR_X2
HDR_X2.cs
)
set_property(TARGET RVC_Example_HDR_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_HDR_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_HDR_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_HDR_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)


add_executable(RVC_Example_LaserCameraCapture_X2
LaserCameraCapture_X2.cs
)
set_property(TARGET RVC_Example_LaserCameraCapture_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_LaserCameraCapture_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_LaserCameraCapture_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_LaserCameraCapture_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_SetTransformation_X2
SetTransformation_X2.cs
)
set_property(TARGET RVC_Example_SetTransformation_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_SetTransformation_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_SetTransformation_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_SetTransformation_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetCameraResolution
GetCameraResolution.cs
)
set_property(TARGET RVC_Example_GetCameraResolution PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetCameraResolution PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetCameraResolution RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetCameraResolution PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_GetProjectorTemperature
GetProjectorTemperature.cs
)
set_property(TARGET RVC_Example_GetProjectorTemperature PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_GetProjectorTemperature PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_GetProjectorTemperature RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_GetProjectorTemperature PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_UserSet_X1
UserSet_X1.cs
)
set_property(TARGET RVC_Example_UserSet_X1 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_UserSet_X1 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_UserSet_X1 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_UserSet_X1 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)

add_executable(RVC_Example_UserSet_X2
UserSet_X2.cs
)
set_property(TARGET RVC_Example_UserSet_X2 PROPERTY DOTNET_TARGET_FRAMEWORK_VERSION  "v4.7.2")
set_property(TARGET RVC_Example_UserSet_X2 PROPERTY WIN64_EXECUTABLE TRUE)
set(CMAKE_CSharp_FLAGS "${CMAKE_CXX_FLAGS} /langversion:latest /platform:x64")
target_link_libraries(RVC_Example_UserSet_X2 RVC_CSharp RVC_CSharp_Extension)
set_property(TARGET RVC_Example_UserSet_X2 PROPERTY VS_DOTNET_REFERENCES
    "Microsoft.CSharp"
    "System"
    "System.Linq"
    "System.Threading.Tasks"
    "System.Windows.Forms"
    "System.Runtime.InteropServices"
    "System.IO"
    "System.Drawing"
)


