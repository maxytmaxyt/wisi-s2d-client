import subprocess

cmd = """
Get-CimInstance Win32_PnPEntity | Where-Object { $_.DeviceID -like '*USB*' } | Select-Object Name, DeviceID, HardwareID | Format-List
"""
p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
for block in p.stdout.split("\n\n"):
    if any(k in block.lower() for k in ["crenova", "ice", "usbstor"]):
        print(block)
        print("-" * 50)
