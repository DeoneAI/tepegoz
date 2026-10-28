FROM ubuntu:22.04
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git cmake ninja-build g++ libopencv-dev libeigen3-dev libceres-dev \
    libboost-system-dev libboost-filesystem-dev libboost-thread-dev libboost-date-time-dev \
    && rm -rf /var/lib/apt/lists/*
ARG OPENVINS_REF=69488123ed9362dd44b6f28e7f4680abbff1442b
RUN git clone https://github.com/rpng/open_vins.git /opt/open_vins \
    && git -C /opt/open_vins checkout ${OPENVINS_REF}
RUN sed -i 's/-g3 / /g' /opt/open_vins/ov_msckf/CMakeLists.txt \
    && cmake -S /opt/open_vins/ov_msckf -B /opt/build -G Ninja -DENABLE_ROS=OFF -DENABLE_ARUCO_TAGS=OFF \
    && cmake --build /opt/build --target ov_msckf_lib -j2
COPY euroc_runner.cpp /opt/open_vins/ov_msckf/src/tepegoz_euroc.cpp
RUN printf '\nadd_executable(tepegoz_euroc src/tepegoz_euroc.cpp)\ntarget_link_libraries(tepegoz_euroc ov_msckf_lib ${thirdparty_libraries})\n' >> /opt/open_vins/ov_msckf/cmake/ROS1.cmake \
    && cmake -S /opt/open_vins/ov_msckf -B /opt/build \
    && cmake --build /opt/build --target tepegoz_euroc -j2
# Preserve upstream config and create an explicitly mono, fixed-calibration variant.
RUN cp -r /opt/open_vins/config/euroc_mav /opt/euroc_mono \
    && sed -i -e 's/use_stereo: true/use_stereo: false/' -e 's/max_cameras: 2/max_cameras: 1/' \
      -e 's/calib_cam_extrinsics: true/calib_cam_extrinsics: false/' \
      -e 's/calib_cam_intrinsics: true/calib_cam_intrinsics: false/' \
      -e 's/calib_cam_timeoffset: true/calib_cam_timeoffset: false/' /opt/euroc_mono/estimator_config.yaml
ENTRYPOINT ["/opt/build/tepegoz_euroc"]
