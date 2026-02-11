"""Tests for telemetry_console.viewer utility module."""


def test_joint_names_defined():
    from telemetry_console.viewer import ARM_JOINT_NAMES
    assert len(ARM_JOINT_NAMES) == 14
    assert ARM_JOINT_NAMES[0] == "L_arm_j1"
    assert ARM_JOINT_NAMES[7] == "R_arm_j1"


def test_default_ports():
    from telemetry_console.viewer import DEFAULT_GRPC_PORT, DEFAULT_WEB_PORT
    assert DEFAULT_GRPC_PORT == 9876
    assert DEFAULT_WEB_PORT == 9090


def test_is_running_initially_false(monkeypatch):
    import telemetry_console.viewer as viewer

    # Other tests may start the viewer; force baseline state for deterministic checks.
    monkeypatch.setattr(viewer, "_running", False, raising=False)
    assert viewer.is_running() is False


def test_web_url_initially_none(monkeypatch):
    import telemetry_console.viewer as viewer

    monkeypatch.setattr(viewer, "_web_url", None, raising=False)
    assert viewer.web_url() is None


def test_connect_grpc_sets_running_state(monkeypatch):
    import telemetry_console.viewer as viewer

    called: dict[str, str] = {}

    def fake_init(app_id):
        called["app_id"] = app_id

    def fake_connect(url):
        called["url"] = url

    monkeypatch.setattr(viewer.rr, "init", fake_init)
    monkeypatch.setattr(viewer.rr, "connect_grpc", fake_connect)
    monkeypatch.setattr(viewer, "_running", False, raising=False)
    monkeypatch.setattr(viewer, "_web_url", None, raising=False)
    monkeypatch.setattr(viewer, "_grpc_url", None, raising=False)

    url = viewer.connect_grpc(url="rerun+http://127.0.0.1:9876/proxy")

    assert url == "rerun+http://127.0.0.1:9876/proxy"
    assert called["app_id"] == "telemetry_console_robot"
    assert called["url"] == "rerun+http://127.0.0.1:9876/proxy"
    assert viewer.is_running() is True
    assert viewer.grpc_url() == "rerun+http://127.0.0.1:9876/proxy"
