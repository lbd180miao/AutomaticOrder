# -*- coding: utf-8 -*-
import json
import requests

BASE = "http://127.0.0.1:8001"

def show(title, resp):
    print(f"--- {title}: HTTP {resp.status_code}")
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))

show("health", requests.get(f"{BASE}/health", timeout=5))
show("status(initial)", requests.get(f"{BASE}/status", timeout=5))
show("set_mode Robust", requests.post(f"{BASE}/set_mode", json={"mode": "HighPrecision"}, timeout=5))
show("set_mode alias 抗多次反射", requests.post(f"{BASE}/set_mode", json={"mode": "AntiMultiReflex"}, timeout=5))
show("set_mode bad", requests.post(f"{BASE}/set_mode", json={"mode": "Nope"}, timeout=5))
show("set_exposure", requests.post(f"{BASE}/set_exposure", json={"exposure_2d": 9000, "exposure_3d": 25000, "projector_brightness": 200}, timeout=5))
show("status(after)", requests.get(f"{BASE}/status", timeout=5))
show("capture without camera", requests.post(f"{BASE}/capture", json={"output_dir": ""}, timeout=10))
show("find_devices", requests.get(f"{BASE}/find_devices", timeout=20))
