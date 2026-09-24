import PyRVC as RVC

print("version:", RVC.GetVersion())
ret = RVC.SystemInit()
print("SystemInit ret:", ret, "|", RVC.GetLastErrorMessage())
print("ListDeviceType:", [m for m in dir(RVC.SystemListDeviceTypeEnum) if not m.startswith("_")])

size, devs = RVC.SystemListDevices(RVC.SystemListDeviceTypeEnum.GigE)
print("GigE device count:", size)
for d in devs:
    print("=" * 50)
    d.Print()
    print("sn:", d.sn, "| name:", d.name, "| type:", d.type,
          "| support_x1:", d.support_x1, "| support_x2:", d.support_x2,
          "| support_color:", d.support_color, "| support_extra:", d.support_extra)
    try:
        cfg = RVC.Device.GetNetworkConfig(d)
        print("net cfg attrs:", [a for a in dir(cfg) if not a.startswith("_")])
        cfg.Print()
    except Exception as e:
        print("netcfg err:", e)

RVC.SystemShutdown()
print("shutdown done")
