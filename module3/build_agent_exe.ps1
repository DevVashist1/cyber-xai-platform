# Build standalone executable with PyInstaller (Section 14)
.\.venv\Scripts\pyinstaller.exe --noconfirm --onefile --windowed --name CyberXAIAgent module3/agent/main.py
Write-Host "[+] Built standalone executable at dist/CyberXAIAgent.exe"
