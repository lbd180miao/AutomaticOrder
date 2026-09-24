cmake_minimum_required(VERSION 3.10)

project(RVC_C C CXX)

if (RVC_BUILD_SDK)
set(RVC_INCLUDE_DIRS "${CMAKE_SOURCE_DIR}/Include")
set(RVC_LIBS RVC)
else()
if(WIN32)
  set(RVC_ROOT "../../..")
  set(RVC_INCLUDE_DIRS "${RVC_ROOT}/include")
  set(RVC_LIB_DIR "${RVC_ROOT}/lib")
  file(GLOB RVC_LIBS "${RVC_LIB_DIR}/RVC.lib" ABSOLUTE)
else(WIN32)
  message(FATAL_ERROR "RVC CSharp Interface currently only support Windows platform")
endif(WIN32)
list(LENGTH RVC_LIBS RVC_LIBS_LEN)
endif()


message(STATUS "Using RVC library in ${RVC_LIBS}")
message(STATUS "Using RVC include dirs in  ${RVC_INCLUDE_DIRS}")



add_library(RVC_C SHARED 
    ${CMAKE_CURRENT_SOURCE_DIR}/RVC_C.cpp 
    ${CMAKE_CURRENT_SOURCE_DIR}/RVC_C.h
    ${CMAKE_CURRENT_SOURCE_DIR}/rvc_sdk_dll_version.rc
)

if(RVC_BUILD_SDK)
  target_link_libraries(RVC_C PRIVATE $<TARGET_LINKER_FILE:RVC>)
  add_dependencies(RVC_C RVC)
  # Copy RVC.dll to output dir so C# exe can load it at runtime
  add_custom_command(TARGET RVC_C POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      $<TARGET_FILE:RVC>
      $<TARGET_FILE_DIR:RVC_C>
    COMMENT "Copy RVC.dll to C# output directory"
    VERBATIM
  )
else()
  target_link_libraries(RVC_C PRIVATE ${RVC_LIBS})
endif()
target_include_directories(RVC_C PRIVATE ${RVC_INCLUDE_DIRS} ${CMAKE_CURRENT_SOURCE_DIR})