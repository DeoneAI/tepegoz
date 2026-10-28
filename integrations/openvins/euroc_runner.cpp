// SPDX-License-Identifier: GPL-3.0-or-later
// Local ROS-free dataset adapter for OpenVINS (GPL-3.0-or-later).
// Ground truth is deliberately absent from the estimator input interface.
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <vector>
#include "core/VioManager.h"
#include "state/State.h"
#include "utils/print.h"
#include "utils/sensor_data.h"

std::vector<std::vector<std::string>> rows(const std::string &file) {
  std::ifstream input(file);
  if (!input) throw std::runtime_error("Cannot open " + file);
  std::vector<std::vector<std::string>> result;
  std::string line, field;
  while (std::getline(input, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.empty() || line[0] == '#' || !std::isdigit(line[0])) continue;
    std::stringstream stream(line); std::vector<std::string> row;
    while (std::getline(stream, field, ',')) row.push_back(field);
    result.push_back(row);
  }
  return result;
}

int main(int argc, char **argv) {
  try {
    if (argc != 4) throw std::runtime_error("Usage: runner DATASET OUTPUT_CSV CONFIG_YAML");
    const std::string root(argv[1]), output(argv[2]);
    if (std::ifstream(output)) throw std::runtime_error("Output already exists; preserve earlier runs");
    auto cameras = rows(root + "/camera_selection.csv"), imu = rows(root + "/mav0/imu0/data.csv");
    if (cameras.empty() || imu.empty()) throw std::runtime_error("Empty camera/IMU stream");
    const auto origin = std::min(std::stoll(cameras.front()[0]), std::stoll(imu.front()[0]));
    auto seconds = [origin](const std::string &value) { return (std::stoll(value) - origin) / 1e9; };
    auto parser = std::make_shared<ov_core::YamlParser>(argv[3]);
    ov_core::Printer::setPrintLevel("WARNING");
    ov_msckf::VioManagerOptions options; options.print_and_load(parser);
    options.use_multi_threading_pubs = false; options.use_multi_threading_subs = false;
    options.num_opencv_threads = 2;
    if (!parser->successful()) throw std::runtime_error("Invalid OpenVINS config");
    ov_msckf::VioManager estimator(options);
    std::ofstream log(output);
    if (!log) throw std::runtime_error("Cannot create output CSV");
    log << "time_s,frame_index,px,py,pz,qx,qy,qz,qw,bgx,bgy,bgz,bax,bay,baz\n" << std::setprecision(17);
    size_t cursor = 0, poses = 0; double last = -1;
    for (size_t index = 0; index < cameras.size(); ++index) {
      const double time = seconds(cameras[index][0]);
      // Supply an IMU sample past the image for interpolation, as in a buffered receiver.
      while (cursor < imu.size() && seconds(imu[cursor][0]) <= time + .01) {
        const auto &row = imu[cursor++]; ov_core::ImuData sample;
        sample.timestamp = seconds(row[0]);
        for (int axis = 0; axis < 3; ++axis) { sample.wm(axis) = std::stod(row[axis + 1]); sample.am(axis) = std::stod(row[axis + 4]); }
        estimator.feed_measurement_imu(sample);
      }
      ov_core::CameraData image; image.timestamp = time; image.sensor_ids = {0};
      image.images = {cv::imread(root + "/mav0/cam0/data/" + cameras[index][1], cv::IMREAD_GRAYSCALE)};
      if (image.images[0].empty()) throw std::runtime_error("Unreadable camera image");
      image.masks = {cv::Mat::zeros(image.images[0].size(), CV_8UC1)};
      estimator.feed_measurement_camera(image);
      if (!estimator.initialized()) continue;
      auto state = estimator.get_state();
      if (state->_timestamp <= last) continue;
      last = state->_timestamp;
      Eigen::Quaterniond q(state->_imu->Rot().transpose());  // Hamilton body -> estimator world
      log << last << ',' << index;
      for (int axis = 0; axis < 3; ++axis) log << ',' << state->_imu->pos()(axis);
      log << ',' << q.x() << ',' << q.y() << ',' << q.z() << ',' << q.w();
      for (int axis = 0; axis < 3; ++axis) log << ',' << state->_imu->bias_g()(axis);
      for (int axis = 0; axis < 3; ++axis) log << ',' << state->_imu->bias_a()(axis);
      log << '\n'; ++poses;
    }
    std::cout << "origin_timestamp_ns=" << origin << " camera_frames=" << cameras.size() << " initialized_poses=" << poses << '\n';
    return poses ? 0 : 3;
  } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
