import subprocess

cmd = "Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -eq 'USB' } | Select-Object Name, DeviceID"
p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
for line in p.stdout.splitlines():
    if line.strip():
        print(line)
