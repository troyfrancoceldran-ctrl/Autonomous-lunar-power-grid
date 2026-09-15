# Native build of the firmware's PORTABLE half.
#
# controller.cpp has no Arduino.h and no vendor SDK, so it compiles here and
# can be held to the Python original's decisions on a laptop — where a failure
# names a line — before anything is flashed. The board-specific wrapper lives
# in src/main.cpp and is built by PlatformIO, not by this.
#
#   cmake -S firmware -B firmware/build
#   cmake --build firmware/build
#   ./firmware/build/test_controller        # run from the repository root
cmake_minimum_required(VERSION 3.16)
project(lunar_firmware CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_compile_options(-Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror)

add_library(controller STATIC src/controller.cpp)
target_include_directories(controller PUBLIC include)

add_executable(test_controller test/test_controller.cpp)
target_link_libraries(test_controller PRIVATE controller)
