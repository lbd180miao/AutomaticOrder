# -*- coding: utf-8 -*-
import PyRVC as RVC

print("init:", RVC.SystemInit(), RVC.GetLastErrorMessage())
for enum_name in ("All", "GigE", "USB"):
    enum = getattr(RVC.SystemListDeviceTypeEnum, enum_name)
    count, devs = RVC.SystemListDevices(enum)
    print(f"=== {enum_name}: count={count}")
    for i, dev in enumerate(devs):
        print(f"  device[{i}] valid={dev.IsValid()}")
        try:
            info = dev.GetDeviceInfo()
            for attr in ("sn", "name", "type", "port", "support_x1", "support_x2",
                         "support_color", "support_extra", "cameraid",
                         "workingdist_near_mm", "workingdist_far_mm"):
                print(f"    info.{attr} = {getattr(info, attr, '<missing>')!r}")
        except Exception as e:
            print("    info error:", e)
        try:
            cfg = RVC.Device.GetNetworkConfig(dev)
            print("    cfg attrs:", [a for a in dir(cfg) if not a.startswith("_")])
            for a in dir(cfg):
                if a.startswith("_"):
                    continue
                try:
                    v = getattr(cfg, a)
                    if not callable(v):
                        print(f"      cfg.{a} = {v!r}")
                except Exception as e:
                    print(f"      cfg.{a} error: {e}")
        except Exception as e:
            print("    cfg error:", e)
        try:
            dev.Print()
        except Exception as e:
            print("    print error:", e)
RVC.SystemShutdown()
