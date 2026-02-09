"""Tests for the Rerun bridge sine-wave streaming."""

from __future__ import annotations

import threading
import time
import urllib.request
from pathlib import Path

import pytest


def test_rerun_bridge_blueprint_layout(monkeypatch):
    """Ensure the default blueprint splits trajectory + 3D tabs horizontally."""
    import rerun.blueprint as rrb
    import rerun_bridge

    captured: dict[str, object] = {}

    def fake_send_blueprint(blueprint, **_kwargs):
        captured["blueprint"] = blueprint

    monkeypatch.setattr(rerun_bridge.rr, "send_blueprint", fake_send_blueprint)

    rerun_bridge._send_blueprint()

    blueprint = captured.get("blueprint")
    assert blueprint is not None
    assert isinstance(blueprint, rrb.Blueprint)
    assert blueprint.collapse_panels is True

    root = blueprint.root_container
    assert isinstance(root, rrb.Horizontal)
    assert len(root.contents) == 2
    assert isinstance(root.contents[0], rrb.TimeSeriesView)
    assert isinstance(root.contents[1], rrb.Tabs)
    assert root.contents[0].origin == "/trajectory"
    tabs = root.contents[1]
    tab_contents = list(tabs.contents)
    assert len(tab_contents) == 2

    visual_view, collision_view = tab_contents
    assert isinstance(visual_view, rrb.Spatial3DView)
    assert isinstance(collision_view, rrb.Spatial3DView)
    assert visual_view.name == "3D Visual"
    assert collision_view.name == "3D Collision"
    assert visual_view.origin == "/"
    assert collision_view.origin == "/"
    robot_root = "/vega_1p_f5d6"
    assert visual_view.contents == [
        f"{robot_root}/visual_geometries/**",
        f"{robot_root}/joint_transforms/**",
    ]
    assert collision_view.contents == [
        f"{robot_root}/collision_geometries/**",
        f"{robot_root}/joint_transforms/**",
    ]


def test_rerun_bridge_start_and_stream(monkeypatch):
    """Start the bridge, stream a few data points, and verify the web viewer is reachable."""
    import rerun_bridge

    monkeypatch.setattr(rerun_bridge, "load_vega_1p_model", lambda: None, raising=False)

    # Use non-default ports to avoid clashes with a running dev session
    grpc_port = 19876
    web_port = 19090

    url = rerun_bridge.start(grpc_port=grpc_port, web_port=web_port, open_browser=False)
    assert url == f"http://localhost:{web_port}"
    assert rerun_bridge.is_running()
    assert rerun_bridge.web_url() == url

    # Stream for a short burst in a background thread
    t = threading.Thread(
        target=rerun_bridge.stream_sine_wave,
        kwargs={"hz": 20, "duration": 1.5},
        daemon=True,
    )
    t.start()

    # Give the web viewer a moment to bind
    time.sleep(1.0)

    # Verify the HTTP web viewer responds
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        assert resp.status == 200
    except Exception as exc:
        pytest.fail(f"Web viewer not reachable at {url}: {exc}")

    t.join(timeout=5)


def test_vega_1p_urdf_path_is_repo_relative():
    import rerun_bridge

    expected = (
        Path(__file__).resolve().parents[2]
        / "external"
        / "dexmate-urdf"
        / "robots"
        / "humanoid"
        / "vega_1p"
        / "vega_1p_f5d6.urdf"
    )

    assert rerun_bridge._vega_1p_urdf_path() == expected


def test_load_vega_1p_model_logs_urdf(monkeypatch, tmp_path):
    import rerun_bridge

    fake_urdf = tmp_path / "robot.urdf"
    fake_urdf.write_text("<robot name='test'></robot>", encoding="utf-8")

    monkeypatch.setattr(rerun_bridge, "_vega_1p_urdf_path", lambda: fake_urdf)

    calls: dict[str, object] = {}

    def fake_log_file_from_path(path, *, static=False, **_kwargs):
        calls["path"] = path
        calls["static"] = static

    class FakeRecording:
        def flush(self):
            calls["flush"] = True

    monkeypatch.setattr(rerun_bridge.rr, "log_file_from_path", fake_log_file_from_path)
    monkeypatch.setattr(
        rerun_bridge.rr, "get_global_data_recording", lambda: FakeRecording()
    )
    sentinel_tree = object()

    def fake_from_file_path(path, entity_path_prefix=None):
        calls["tree_path"] = path
        calls["tree_prefix"] = entity_path_prefix
        return sentinel_tree

    monkeypatch.setattr(
        rerun_bridge.rr.urdf.UrdfTree,
        "from_file_path",
        staticmethod(fake_from_file_path),
    )

    result = rerun_bridge.load_vega_1p_model()

    assert result == fake_urdf
    assert calls["path"] == fake_urdf
    assert calls["static"] is True
    assert calls["flush"] is True
    assert calls["tree_path"] == fake_urdf
    assert calls["tree_prefix"] == f"/{fake_urdf.stem}"
    assert rerun_bridge._urdf_tree is sentinel_tree
    assert rerun_bridge._robot_root == f"/{fake_urdf.stem}"


def test_log_shoulder_transforms_logs_joint_paths(monkeypatch):
    import rerun_bridge

    logged: list[tuple[str, object]] = []

    def fake_log(path, payload, **_kwargs):
        logged.append((path, payload))

    class FakeJoint:
        def __init__(self, name: str) -> None:
            self.name = name
            self.received: tuple[float, bool] | None = None

        def compute_transform(self, value: float, clamp: bool = True) -> str:
            self.received = (value, clamp)
            return f"transform:{self.name}:{value}:{clamp}"

    class FakeTree:
        def __init__(self) -> None:
            self._joints = {
                "L_arm_j1": FakeJoint("L_arm_j1"),
                "R_arm_j1": FakeJoint("R_arm_j1"),
            }

        def get_joint_by_name(self, name: str) -> FakeJoint | None:
            return self._joints.get(name)

    tree = FakeTree()
    monkeypatch.setattr(rerun_bridge, "_urdf_tree", tree, raising=False)
    monkeypatch.setattr(rerun_bridge, "_robot_root", "/vega_1p_f5d6", raising=False)
    monkeypatch.setattr(rerun_bridge.rr, "log", fake_log)

    rerun_bridge._log_shoulder_transforms(0.25, -0.5)

    assert [entry[0] for entry in logged] == [
        "/vega_1p_f5d6/joint_transforms/L_arm_j1",
        "/vega_1p_f5d6/joint_transforms/R_arm_j1",
    ]
    assert tree._joints["L_arm_j1"].received == (0.25, True)
    assert tree._joints["R_arm_j1"].received == (-0.5, True)
