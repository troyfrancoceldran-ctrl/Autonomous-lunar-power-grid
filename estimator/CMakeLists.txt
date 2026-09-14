# Native build. No board, no vendor SDK, no package manager.
#
# The filter is proven on the host first: a test here runs in milliseconds and
# a failure points at a line. An estimator that is wrong on a laptop is wrong
# on an ESP32 and far harder to see there.
#
#   cmake -S estimator -B estimator/build
#   cmake --build estimator/build
#   ./estimator/build/test_ekf
cmake_minimum_required(VERSION 3.16)
project(lunar_estimator CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)          # -std=c++17, never -std=gnu++17

# Warnings are errors here. The filter will eventually run on a microcontroller
# with no debugger attached and no way to print, so a warning caught now is
# cheaper than a silence caught never.
add_compile_options(-Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror)

add_library(ekf STATIC src/ekf.cpp)
target_include_directories(ekf PUBLIC include)

add_executable(test_ekf test/test_ekf.cpp)
target_link_libraries(test_ekf PRIVATE ekf)
target_include_directories(test_ekf PRIVATE test)

enable_testing()
add_test(NAME ekf COMMAND test_ekf)
