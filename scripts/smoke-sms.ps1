param(
  [Parameter(Mandatory = $true)]
  [string]$To,
  [string]$Message = "Tenacious live smoke test SMS.",
  [string]$LeadId = "",
  [switch]$Cold
)

$ErrorActionPreference = "Stop"

$argsList = @(
  "agent/scripts/live_smoke.py",
  "sms",
  "--to", $To,
  "--message", $Message
)

if ($LeadId) {
  $argsList += @("--lead-id", $LeadId)
}
if ($Cold) {
  $argsList += "--cold"
}

python @argsList

