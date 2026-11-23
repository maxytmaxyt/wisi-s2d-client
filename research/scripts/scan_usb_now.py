import subprocess

# Fast SetupAPI query via Get-PnpDevice
cmd = """
Get-PnpDevice -PresentOnly | Select-Object Status, Class, FriendlyName, InstanceId | Format-Table -AutoSize
"""
p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
for line in p.stdout.splitlines():
    if any(k in line.lower() for k in ['usb', 'port', 'serial', 'com', 'ali', 'crenova', 'tivicon', 'wisi', 'unknown', 'other', 'dfu', 'cdc']):
        print(line)
