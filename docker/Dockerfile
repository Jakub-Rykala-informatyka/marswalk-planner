FROM osrf/ros:humble-desktop

ARG HOST_UID=1000
ARG HOST_GID=1000

# aiohttp serves the dashboard and its WebSocket from the same process as the ROS node
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-aiohttp \
    && rm -rf /var/lib/apt/lists/*

# User with the host UID, so files written into the mounted repo are not owned by root
RUN groupadd -g ${HOST_GID} dev \
    && useradd -m -u ${HOST_UID} -g ${HOST_GID} -s /bin/bash dev \
    && echo 'source /opt/ros/humble/setup.bash' >> /home/dev/.bashrc

USER dev
WORKDIR /workspace
