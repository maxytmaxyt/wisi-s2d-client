import subprocess

cmd = """
Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -in @('USB', 'Ports') } | Select-Object Name, DeviceID
"""
p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
print(p.stdout)
