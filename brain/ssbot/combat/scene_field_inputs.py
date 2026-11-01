"""Startup-once loader of the portable scene-field Inputs package (Sol task 43 item 1; hand-portable).

    inputs = load_inputs("<dir>/scene_field_inputs43.json", scene_field_events.Inputs)

numpy and the standard library only: no ssbot import, no environment variable, no absolute or Opus path (the NPZ is
found next to the JSON by its recorded file name and checked by sha256).  Call once at startup, keep the object: the
three arrays come back read-only, the scalars / dicts are plain values exactly as inputs41/42 made them (so
scene_field_events' static digest and cache keys are the same).  Nothing here runs per tick, re-simulates HERO2 or
reads a report.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np

PACKAGE = "scene_field_inputs43"
VERSION = 1
ARRAY_FIELDS = ("t_centre", "t_vel", "t_ground")


def load_inputs(json_path, inputs_cls):
    """The Inputs instance described by the package JSON (raises ValueError on any mismatch)."""
    jp = Path(json_path)
    meta = json.loads(jp.read_text(encoding="utf-8"))
    if meta.get("package") != PACKAGE or meta.get("version") != VERSION:
        raise ValueError(f"not a {PACKAGE} v{VERSION} package: {jp.name}")
    name = str(meta["npz_file"])
    if Path(name).name != name:
        raise ValueError("npz_file must be a bare file name next to the JSON")
    raw = (jp.parent / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta["npz_sha256"]:
        raise ValueError(f"{name} does not match the package sha256")
    arrays = {}
    with np.load(io.BytesIO(raw), allow_pickle=False) as z:
        if sorted(z.files) != sorted(ARRAY_FIELDS):
            raise ValueError(f"unexpected arrays {sorted(z.files)}")
        for k in ARRAY_FIELDS:
            a = np.array(z[k], copy=True)
            spec = meta["arrays"][k]
            if str(a.dtype) != spec["dtype"] or list(a.shape) != list(spec["shape"]):
                raise ValueError(f"{k}: {a.dtype} {a.shape} != {spec}")
            a.setflags(write=False)
            arrays[k] = a
    fields = json.loads(json.dumps(meta["fields"]))          # a private copy of the plain values
    for k in meta["tuple_fields"]:
        fields[k] = tuple(fields[k])
    return inputs_cls(**fields, **arrays)
