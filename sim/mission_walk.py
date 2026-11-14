"""The astronaut's progress along a route, with stops at mission targets.

With a mission plan (from /mission/plan) every target whose stop point lies on
the route becomes a stop: the astronaut halts there for the target's work time,
scaled down for the demo. At targets the rover arm works on ("arm" executor)
the arm runs a sample sequence while the astronaut waits.
"""

import numpy as np

MATCH_M = 10.0  # a target counts as on the route when a route point is this close to its stop
ROVER_READY_M = 7.0  # the arm starts once the rover is this close behind the astronaut
# Arm sample sequence as shares of the work time: reach out, down to the ground,
# over the sample box, back to the stowed pose
ARM_SEQUENCE = ((0.15, "forward"), (0.55, "ground"), (0.8, "sample_box"), (1.01, "stow"))


class MissionWalk:
    def __init__(self, route, plan, seconds_per_minute, start_s=0.0):
        self.route = route
        self.s = start_s
        self.seconds_per_minute = seconds_per_minute
        self.stops = self._stops(plan) if plan and plan.get("ok") else []
        self.index = 0  # next stop
        self.work = None  # (stop, started at, ends at) while working; times None while waiting for the rover

    def _stops(self, plan):
        stops = []
        samples = np.arange(0.0, self.route.length, 1.0)
        points = np.array([self.route.point(s) for s in samples]) if len(samples) else np.zeros((0, 2))
        for number, target in enumerate(plan["targets"], start=1):
            if not len(points):
                break
            gaps = np.linalg.norm(points - np.array(target["stop"]), axis=1)
            i = int(np.argmin(gaps))
            if gaps[i] <= MATCH_M:
                stops.append({"number": number, "id": target["id"], "name": target["name"],
                              "executor": target["executor"], "minutes": target["minutes"],
                              "s": float(samples[i])})
        stops.sort(key=lambda stop: stop["s"])
        return stops

    def step(self, t, distance, rover_gap):
        """Walk `distance` metres unless working; returns the distance along the route.

        rover_gap: metres along the route between the rover and the astronaut.
        """
        if self.work and self.work[1] is None:
            if rover_gap > ROVER_READY_M:
                return self.s  # the arm is on the rover: wait for it
            stop = self.work[0]
            self.work = (stop, t, t + stop["minutes"] * self.seconds_per_minute)
        if self.work:
            if t < self.work[2]:
                return self.s
            self.work = None
            self.index += 1
        if self.index < len(self.stops) and self.stops[self.index]["s"] < self.s - 1.0:
            self.index += 1  # already past it (route started beyond this stop)
        target_s = self.s + distance
        if self.index < len(self.stops) and target_s >= self.stops[self.index]["s"]:
            stop = self.stops[self.index]
            self.s = stop["s"]
            if stop["executor"].startswith("arm"):
                self.work = (stop, None, None)
            else:
                self.work = (stop, t, t + stop["minutes"] * self.seconds_per_minute)
            return self.s
        self.s = min(target_s, self.route.length)
        return self.s

    def arm_pose(self, t):
        """Preset name the arm should hold now, or None when it is free for remote control."""
        if not self.work or self.work[1] is None or not self.work[0]["executor"].startswith("arm"):
            return None
        stop, start, end = self.work
        share = (t - start) / max(end - start, 1e-6)
        return next(pose for limit, pose in ARM_SEQUENCE if share < limit)

    def progress(self, t):
        message = {"stops": len(self.stops), "done": self.index, "phase": "walking"}
        if self.work and self.work[1] is None:
            stop = self.work[0]
            message.update(phase="waiting for rover", target=stop["name"], number=stop["number"],
                           executor=stop["executor"])
        elif self.work:
            stop, start, end = self.work
            message.update(phase="working", target=stop["name"], number=stop["number"], executor=stop["executor"],
                           work_left_s=round(max(end - t, 0.0)), work_minutes=stop["minutes"],
                           arm_step=self.arm_pose(t))
        elif self.index < len(self.stops):
            stop = self.stops[self.index]
            message.update(target=stop["name"], number=stop["number"], executor=stop["executor"],
                           distance_m=round(max(stop["s"] - self.s, 0.0)))
        elif self.stops:
            message["phase"] = "returning" if self.s < self.route.length - 1 else "done"
        if not self.stops:
            message["phase"] = "free walk"
        return message
