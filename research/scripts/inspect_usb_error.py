import subprocess

cmd = """
Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 } | Select-Object Name, DeviceID, ConfigManagerErrorCode | Format-List
"""
p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
print(p.stdout)
