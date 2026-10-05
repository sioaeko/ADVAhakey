cmake_minimum_required(VERSION 3.16)
project(ahakey_adv_tests LANGUAGES CXX)
enable_testing()
add_executable(protocol_test tests/protocol_test.cpp src/OriginalLights.cpp)
target_include_directories(protocol_test PRIVATE include)
target_compile_features(protocol_test PRIVATE cxx_std_17)
if(MSVC)
  target_compile_options(protocol_test PRIVATE /UNDEBUG)
else()
  target_compile_options(protocol_test PRIVATE -UNDEBUG)
endif()
add_test(NAME protocol COMMAND protocol_test)

add_executable(adpcm_encoder tests/adpcm_encoder.cpp)
target_include_directories(adpcm_encoder PRIVATE include)
target_compile_features(adpcm_encoder PRIVATE cxx_std_17)
set_target_properties(adpcm_encoder PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/dist"
  RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_SOURCE_DIR}/dist"
  RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_SOURCE_DIR}/dist")
