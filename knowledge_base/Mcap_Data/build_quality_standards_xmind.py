# -*- coding: utf-8 -*-
"""
Build XMind (Zen format) from PrismaX Mcap Data Collection Quality Standards.
Output: PrismaX_Mcap_Quality_Standards.xmind
Uses content.json format so XMind 8 / XMind Zen can open it.
"""
import json
import zipfile
import uuid

OUTPUT_PATH = "PrismaX_Mcap_Quality_Standards.xmind"

# Quality standards data: (ID, Category, Item, Definition, Minimum, Recommended)
STANDARDS = [
    ("STD-001", "Topics", "Camera Sensors", "Camera sensors used to record the demonstration. MCAP should not contain image topics; camera videos as separate MP4. One cameraInfo per camera.", "1 camera per end effector; 1 fixed camera covering all end effector trajectories.", "1 camera per end effector; 2 fixed cameras each covering all trajectories."),
    ("STD-002", "Topics", "Observed Joint States", "Minimum observed manipulator joint states in the episode.", "1 joint state topic per manipulator (including end effector).", "1 joint state topic per manipulator (including end effector)."),
    ("STD-003", "Topics", "Commanded Joint States", "Minimum commanded manipulator joint states in the episode.", "Leader/Follower: 1 commanded joint state topic per manipulator. VR: 1 commanded pose/position topic per end effector.", "Leader/Follower: 1 commanded joint state topic per manipulator. VR: 1 commanded joint state topic per manipulator."),
    ("STD-004", "Topics", "Robot Description (URDF)", "All data for reproducibility of trajectories and spatial correspondence.", "MCAP includes robot description (URDF) matching transform tree. Validate with 3D viewer (rviz, Foxglove).", "Same as minimum."),
    ("STD-005", "Topics", "Navigation", "Data for mobile robot motion and environment traversal. Only for mobile robots.", "Odometry/pose >14.5 Hz; IMU >90 Hz; odometry drift <2%; all camera frames have position/pose; nav topics reference tf tree.", "Odometry/pose >29.5 Hz; IMU >290 Hz; drift <1%; same frame/pose requirements."),
    ("STD-006", "Technical Specs", "Camera (RGB) - Min Avg Frame Rate", "Minimum camera frequency to capture robot trajectory.", "Average framerate >14.5 FPS on all cameras.", "Average framerate >29.5 FPS on all cameras."),
    ("STD-007", "Technical Specs", "Camera (RGB) - Max Gap Between Frames", "Max time between consecutive camera frames.", "All frames within 69ms of previous/next from same camera.", "All frames within 34ms of previous/next from same camera."),
    ("STD-008", "Technical Specs", "Camera (RGB) - Min Resolution", "Minimum resolution to preserve spatial detail.", "640x480", "1280x720 or higher"),
    ("STD-009", "Technical Specs", "Camera to Camera Time Sync", "Timestamp difference across cameras.", "All camera topics have timestamps; temporal misalignment <34ms.", "Hardware synchronized; no temporal misalignment."),
    ("STD-010", "Technical Specs", "Joint States to Camera Time Sync", "Temporal offset between camera and joint state timestamps.", "Temporal misalignment <34ms.", "No temporal misalignment."),
    ("STD-011", "Technical Specs", "Robot Joint States Frequency", "Minimum joint state frequency for robot movements.", "Avg joint state frequency >45 Hz on all joints; every camera frame has corresponding joint state.", "Avg >290 Hz; same correspondence."),
    ("STD-012", "Technical Specs", "Camera (Depth) - Min Avg Frame Rate", "Min depth camera frequency. Not required; if included:", "Framerate >14.5 FPS.", "Framerate >29.5 FPS."),
    ("STD-013", "Technical Specs", "Camera (Depth) - Max Gap Between Frames", "Max gap for depth frames. Not required; if included:", "Frames within 69ms.", "Frames within 34ms."),
    ("STD-014", "Technical Specs", "Camera (Depth) - Min Resolution", "Min depth resolution. Not required; if included:", "640x480", "1280x720 or higher"),
    ("STD-015", "Technical Specs", "Calibration: reprojection error", "Quality of camera intrinsic/extrinsic calibrations.", "Not required", "RMSE <0.5"),
    ("STD-016", "Technical Specs", "Calibration: eye-in-hand", "Error of extrinsic transform between end effector and its camera.", "Not required", "<5mm"),
    ("STD-017", "Technical Specs", "Calibration: eye-to-hand", "Error of extrinsic transform between end effector and static cameras.", "Not required", "<1cm"),
    ("STD-018", "Technical Specs", "Physical Vibration and Jitter", "Shakiness of robot arms and cameras.", "Free from vibrations; arm trajectory smooth, no jitters.", "Same as minimum."),
    ("STD-019", "Technical Specs", "Light Flickering in Videos", "Flickering from camera framerate vs lighting frequency.", "Videos free from flickering lights.", "Videos free from flickering lights."),
    ("STD-020", "Demonstration", "Operator Skill", "Operator ability to control robot for data collection.", "Operator sufficiently skilled to meet minimum requirements.", "Operator should pass manipulation skills assessment (see appendix)."),
    ("STD-021", "Demonstration", "Trajectory Smoothness", "How smoothly the robot arm moves.", "Trajectories continuous, fluid, no unnecessary pauses; avoid kinematic singularities.", "Same as minimum."),
    ("STD-022", "Demonstration", "Demonstration Efficiency", "Time to complete demonstration while meeting other standards.", "Efficient enough to be practical and beneficial for end user.", "Same as minimum."),
    ("STD-023", "Demonstration", "Demonstration Completeness", "Final outcome of a demonstration.", "Reach intended final state per task instructions; quick recovery from mistakes.", "Same as minimum."),
    ("STD-024", "Demonstration", "Episode Diversity", "Differences across episodes (Environment, Scene, Demonstration, Objects, Actions).", "Same values across all diversity categories repeat no more than 20 times.", "Each demonstration unique; at least one diversity category varied per demo."),
    ("STD-025", "Demonstration", "Non-Robot Actions", "Behaviors abnormal for a robot (e.g. two arms for one-arm task, singular trajectories).", "Exclude trajectories abnormal for a robot.", "Exclude trajectories abnormal for a robot."),
    ("STD-026", "Demonstration", "Field of View Compliance", "Manipulations occur within camera FOV.", "All task actions within defined FOV of recording spec.", "Same as minimum."),
    ("STD-027", "Demonstration", "Prohibited Information in View", "No personal, confidential, or proprietary information in recording.", "All demonstrations free of prohibited data.", "All demonstrations free of prohibited data."),
    ("STD-028", "Demonstration", "Language Compliance", "Text in the data, if any, should be in English.", "", ""),
]


def make_id():
    return uuid.uuid4().hex[:12]


def make_topic(title, children_list=None):
    t = {"id": make_id(), "title": title}
    if children_list:
        t["children"] = {"attached": children_list}
    return t


def build_zen_content():
    """Build XMind Zen content.json: root 下直接挂各 STD，每个 STD 下为 Definition / Minimum / Recommended，描述文字作为各自的下级节点."""
    root_attached = []
    for row in STANDARDS:
        std_id, _, item, definition, minimum, recommended = row
        sub_children = [
            make_topic("Definition", [make_topic(definition)] if definition else None),
            make_topic("Minimum", [make_topic(minimum)] if minimum else None),
            make_topic("Recommended", [make_topic(recommended)] if recommended else None),
        ]
        std_topic = make_topic(f"{std_id} {item}", children_list=sub_children)
        root_attached.append(std_topic)

    root_topic = make_topic("PrismaX Mcap Data Collection Quality Standards", children_list=root_attached)
    sheet = {
        "id": make_id(),
        "title": "PrismaX Mcap Quality Standards",
        "rootTopic": root_topic,
    }
    return [sheet]


def main():
    content = build_zen_content()
    content_bytes = json.dumps(content, ensure_ascii=False).encode("utf-8")

    # XMind Zen: zip with content.json; some apps also expect manifest.json and metadata.json
    manifest = {
        "file-entries": {
            "content.json": {},
            "metadata.json": {},
        }
    }
    metadata = {
        "creator": {"name": "PrismaX QA", "version": "1.0"},
    }

    with zipfile.ZipFile(OUTPUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", content_bytes)
        zf.writestr("metadata.json", json.dumps(metadata, indent=2).encode("utf-8"))
        zf.writestr("manifest.json", json.dumps(manifest).encode("utf-8"))

    print(f"Saved (XMind Zen format): {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
