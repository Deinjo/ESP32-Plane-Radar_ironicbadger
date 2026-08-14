$ErrorActionPreference = "Stop"

python -m pip install --upgrade pyinstaller

python -m PyInstaller --noconfirm --clean --onefile `
  --name PlaneRadarSimulator `
  --add-data "tools\radar_simulator;tools\radar_simulator" `
  --add-data "include;include" `
  --add-data "src;src" `
  tools\radar_simulator\server.py

Write-Host "Created dist\PlaneRadarSimulator.exe"
