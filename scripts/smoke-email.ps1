param(
  [Parameter(Mandatory = $true)]
  [string]$To,
  [string]$Subject = "Tenacious live smoke test",
  [string]$Body = "This is a live smoke test email from conversion-engine.",
  [string]$LeadId = ""
)

$ErrorActionPreference = "Stop"

$argsList = @(
  "agent/scripts/live_smoke.py",
  "email",
  "--to", $To,
  "--subject", $Subject,
  "--body", $Body
)

if ($LeadId) {
  $argsList += @("--lead-id", $LeadId)
}

python @argsList

