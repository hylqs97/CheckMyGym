Param([string]$TaskName = "CheckMyGym")

try {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop | Out-Null
  Write-Output "Removed scheduled task '$TaskName'"
} catch {
  Write-Output "Task '$TaskName' not found or failed to remove: $_"
}

