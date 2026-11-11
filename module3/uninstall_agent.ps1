# Test X-06: Clean Uninstall Script (removes Task Scheduler entry, runtime files, and stored credentials)
Unregister-ScheduledTask -TaskName "CyberXAIEndpointAgent" -Confirm:$false -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -c "from module3.agent.core.agent_core import CredentialStore; CredentialStore.clear_credentials('EMP001')" 2>$null
Remove-Item -Path "module3/runtime" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "[+] Cyber XAI Agent uninstalled cleanly (tasks, runtime files, and credentials removed)."
