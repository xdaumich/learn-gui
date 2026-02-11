"""ZMQ port assignments, topic prefixes, and serialization helpers.

Every process imports from here to agree on the wire format.
No runner-specific logic belongs in this module.
"""

from __future__ import annotations

import msgpack
import numpy as np

ROBOT_STATE_PORT = 5555
RECORDER_STATUS_PORT = 5556
RECORDER_CONTROL_PORT = 5557

TOPIC_ROBOT_STATE = b"state"
TOPIC_RECORDER_STATUS = b"rec_status"


def pack_state(
    *,
    joint_names: list[str],
    cmd: np.ndarray,
    state: np.ndarray,
    t_ns: int,
) -> bytes:
    """Serialize a robot state snapshot for ZMQ PUB."""
    return msgpack.packb(
        {
            "joint_names": joint_names,
            "cmd": cmd.tolist(),
            "state": state.tolist(),
            "t_ns": int(t_ns),
        }
    )


def unpack_state(raw: bytes) -> dict:
    """Deserialize a robot state snapshot from ZMQ SUB."""
    data = msgpack.unpackb(raw, raw=False)
    data["cmd"] = np.array(data["cmd"], dtype=np.float32)
    data["state"] = np.array(data["state"], dtype=np.float32)
    return data


def pack_control(*, command: str, run_id: str | None = None) -> bytes:
    """Serialize a recording control command (start / stop / status)."""
    return msgpack.packb({"command": command, "run_id": run_id})


def unpack_control(raw: bytes) -> dict:
    """Deserialize a recording control command."""
    return msgpack.unpackb(raw, raw=False)


def pack_status(*, active: bool, run_id: str | None, samples: int) -> bytes:
    """Serialize a recording status update."""
    return msgpack.packb({"active": active, "run_id": run_id, "samples": int(samples)})


def unpack_status(raw: bytes) -> dict:
    """Deserialize a recording status update."""
    return msgpack.unpackb(raw, raw=False)
