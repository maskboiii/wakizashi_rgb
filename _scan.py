import hid
devices = hid.enumerate(0, 0)
print("Total HID devices found: {}".format(len(devices)))
print()
# Show all non-standard devices (usage_page != 1)
for d in devices:
    vid = d.get("vendor_id", 0)
    pid = d.get("product_id", 0)
    up = d.get("usage_page", 0)
    ifc = d.get("interface_number", -1)
    prod = d.get("product_string", "")
    mfg = d.get("manufacturer_string", "")
    label = ""
    if mfg or prod:
        label = " [{}/{}]".format(mfg, prod)
    if up != 1 or vid not in (0x258A, 0x8087, 0x8086, 0x046D, 0x1A2C, 0x1532, 0x0B05):
        print("VID:{:04X} PID:{:04X} usage:{:04X} ifc:{} path:{} {}".format(
            vid, pid, up, ifc, d.get("path", ""), label))
