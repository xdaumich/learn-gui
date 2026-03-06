"""Discover all connected OAK cameras and print their details."""

from __future__ import annotations

import sys

import depthai as dai


USB_SPEED_NAMES = {
    dai.UsbSpeed.UNKNOWN: "unknown",
    dai.UsbSpeed.LOW: "USB 1.0 (Low)",
    dai.UsbSpeed.FULL: "USB 1.1 (Full)",
    dai.UsbSpeed.HIGH: "USB 2.0 (High)",
    dai.UsbSpeed.SUPER: "USB 3.0 (Super)",
    dai.UsbSpeed.SUPER_PLUS: "USB 3.1 (Super+)",
}


def main() -> None:
    infos = dai.Device.getAllAvailableDevices()
    if not infos:
        print("No OAK cameras found.")
        sys.exit(1)

    print(f"Found {len(infos)} OAK camera(s):\n")

    for info in infos:
        device_id = info.getDeviceId()
        usb_path = info.name
        state = info.state.name

        model = "?"
        sensors: list[str] = []
        usb_speed = "?"

        try:
            dev = dai.Device(info)
            model = dev.getDeviceName()
            usb_speed = USB_SPEED_NAMES.get(dev.getUsbSpeed(), str(dev.getUsbSpeed()))
            for feat in dev.getConnectedCameraFeatures():
                types = "/".join(t.name for t in feat.supportedTypes)
                sensors.append(f"{feat.socket.name}: {feat.sensorName} ({types})")
            dev.close()
        except Exception as exc:
            model = f"(open failed: {exc})"

        print(f"  Device ID:  {device_id}")
        print(f"  Model:      {model}")
        print(f"  USB path:   {usb_path}")
        print(f"  USB speed:  {usb_speed}")
        print(f"  State:      {state}")
        if sensors:
            print(f"  Sensors:    {', '.join(sensors)}")
        print()


if __name__ == "__main__":
    main()
