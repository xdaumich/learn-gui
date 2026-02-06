import cv2
import depthai as dai


def test_camera_dependencies_import() -> None:
    assert cv2.__version__
    assert dai.__version__
