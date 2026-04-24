param(
  [Parameter(Mandatory = $true)]
  [string]$ProspectEmail,

  [Parameter(Mandatory = $true)]
  [string]$SmsTo,

  [string]$ProspectName = "Live Prospect",
  [string]$Timezone = "UTC",
  [string]$CompanyName = "Tenacious Live Test",
  [string]$CompanyDomain = "tenacious-demo.com",
  [string]$CompanyId = "",
  [string]$OutDir = "",
  [int]$SmsInteractions = 1,
  [switch]$SkipUnitTests,
  [switch]$SkipHubSpotReadiness,
  [switch]$SkipSms,
  [switch]$SkipColdPolicyCheck,
  [switch]$SkipBooking
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$runId = Get-Date -Format "yyyyMMdd_HHmmss"
if (-not $CompanyId) {
  $CompanyId = "tenacious_live_$runId"
}
if (-not $OutDir) {
  $OutDir = Join-Path "outputs/evidence" "act2_live_$runId"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "== $Message =="
}

function Invoke-CheckedJsonCommand {
  param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
  )
  & $CommandArgs[0] @($CommandArgs | Select-Object -Skip 1) | Tee-Object $OutputPath
}

Write-Step "Act II live smoke setup"
Write-Host "Run ID: $runId"
Write-Host "Output directory: $OutDir"
Write-Host "Company ID: $CompanyId"

if (-not $SkipUnitTests) {
  Write-Step "Running unit tests"
  python -m pytest -q agent/tests/unit | Tee-Object (Join-Path $OutDir "00_unit_tests.txt")
}

if (-not $SkipHubSpotReadiness) {
  Write-Step "Checking HubSpot MCP readiness"
  .\scripts\smoke-hubspot-tools.ps1 -Strict | Tee-Object (Join-Path $OutDir "01_hubspot_tools.json")
}

Write-Step "Running orchestration path"
$env:ACT2_OUT = $OutDir
$env:ACT2_COMPANY_ID = $CompanyId
$env:ACT2_COMPANY_NAME = $CompanyName
$env:ACT2_COMPANY_DOMAIN = $CompanyDomain
$env:ACT2_RUN_ID = $runId
$env:ACT2_PROSPECT_EMAIL = $ProspectEmail
$env:ACT2_SMS_TO = $SmsTo
$env:ACT2_EVIDENCE_DIR = $OutDir

@'
import asyncio
import json
import os
from pathlib import Path
from time import perf_counter

from agent.main import build_orchestration_runtime, build_state_repo
from agent.services.orchestration.schemas import LeadAdvanceRequest, LeadProcessRequest, LeadReplyRequest


async def main() -> None:
    out_dir = Path(os.environ["ACT2_OUT"])
    run_id = os.environ["ACT2_RUN_ID"]
    runtime = build_orchestration_runtime()
    repo = build_state_repo()

    timings: dict[str, float] = {}

    started = perf_counter()
    process = await runtime.process_lead(
        LeadProcessRequest(
            idempotency_key=f"act2_process_{run_id}",
            company_id=os.environ["ACT2_COMPANY_ID"],
            metadata={
                "company_name": os.environ["ACT2_COMPANY_NAME"],
                "company_domain": os.environ["ACT2_COMPANY_DOMAIN"],
                "initiated_by": "human",
            },
        )
    )
    timings["process_lead_ms"] = round((perf_counter() - started) * 1000, 2)
    if process.status == "failure":
        raise SystemExit(json.dumps(process.model_dump(mode="json"), indent=2))

    lead_id = process.data["lead_id"]
    advances = []
    for index, (from_state, to_state) in enumerate(
        [
            ("brief_ready", "drafting"),
            ("drafting", "in_review"),
            ("in_review", "queued_to_send"),
            ("queued_to_send", "awaiting_reply"),
        ],
        start=1,
    ):
        started = perf_counter()
        advance = await runtime.advance_state(
            LeadAdvanceRequest(
                idempotency_key=f"act2_advance_{index}_{run_id}",
                lead_id=lead_id,
                from_state=from_state,
                to_state=to_state,
                reason="act2 live smoke",
            )
        )
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        advances.append(
            {
                "from_state": from_state,
                "to_state": to_state,
                "latency_ms": elapsed_ms,
                "response": advance.model_dump(mode="json"),
            }
        )
        if advance.status == "failure":
            raise SystemExit(json.dumps(advance.model_dump(mode="json"), indent=2))

    started = perf_counter()
    reply = await runtime.handle_reply(
        LeadReplyRequest(
            idempotency_key=f"act2_reply_{run_id}",
            lead_id=lead_id,
            channel="sms",
            message_id=f"act2_sms_reply_{run_id}",
            content="Yes, interested. Can we schedule a 15-minute call next week?",
            from_email=os.environ.get("ACT2_PROSPECT_EMAIL") or None,
            from_number=os.environ.get("ACT2_SMS_TO") or None,
            company_name=os.environ["ACT2_COMPANY_NAME"],
            company_domain=os.environ["ACT2_COMPANY_DOMAIN"],
        )
    )
    timings["handle_reply_ms"] = round((perf_counter() - started) * 1000, 2)
    if reply.status == "failure":
        raise SystemExit(json.dumps(reply.model_dump(mode="json"), indent=2))

    state = runtime.get_state(lead_id=lead_id)
    briefs = repo.get_briefs(lead_id=lead_id) or {}
    act2_briefs = repo.get_act2_briefs(lead_id=lead_id) or {}
    transcript = repo.list_messages(lead_id=lead_id, limit=50)
    artifact = {
        "lead_id": lead_id,
        "process": process.model_dump(mode="json"),
        "advances": advances,
        "reply": reply.model_dump(mode="json"),
        "state": state.model_dump(mode="json"),
        "briefs": briefs,
        "act2_briefs": act2_briefs,
        "transcript": transcript,
        "latency_ms": timings,
    }
    (out_dir / "02_orchestration_artifact.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    (out_dir / "lead_id.txt").write_text(lead_id, encoding="utf-8")
    print(json.dumps({
        "lead_id": lead_id,
        "state": state.data.get("state"),
        "next_action": reply.data.get("next_action"),
        "act2_artifact_paths": act2_briefs.get("artifact_paths", {}),
    }, indent=2))


asyncio.run(main())
'@ | python - | Tee-Object (Join-Path $OutDir "02_orchestration_stdout.json")

$LeadId = (Get-Content (Join-Path $OutDir "lead_id.txt") -Raw).Trim()
Write-Host "Lead ID: $LeadId"

if (-not $SkipSms) {
  Write-Step "Sending live SMS warm-lead probes"
  $durations = @()
  for ($i = 1; $i -le $SmsInteractions; $i++) {
    $smsOut = Join-Path $OutDir ("03_sms_run_{0}.json" -f $i)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    .\scripts\smoke-sms.ps1 -To $SmsTo -LeadId $LeadId -Message "Act II live SMS probe #$i $runId" | Tee-Object $smsOut
    $sw.Stop()
    $durations += [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
    Start-Sleep -Milliseconds 800
  }

  $sorted = @($durations | Sort-Object)
  if ($sorted.Count -gt 0) {
    if ($sorted.Count % 2 -eq 0) {
      $p50 = [math]::Round((($sorted[($sorted.Count / 2) - 1] + $sorted[$sorted.Count / 2]) / 2), 2)
    } else {
      $p50 = $sorted[[math]::Floor($sorted.Count / 2)]
    }
    $p95Index = [Math]::Max(0, [Math]::Ceiling($sorted.Count * 0.95) - 1)
    $p95 = $sorted[$p95Index]
  } else {
    $p50 = $null
    $p95 = $null
  }

  @{
    interaction_count = $sorted.Count
    p50_ms = $p50
    p95_ms = $p95
    sample_ms = $durations
  } | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutDir "04_sms_latency_report.json")

  if (-not $SkipColdPolicyCheck) {
    Write-Step "Checking cold SMS policy block"
    .\scripts\smoke-sms.ps1 -To $SmsTo -LeadId $LeadId -Message "This cold SMS should be blocked $runId" -Cold |
      Tee-Object (Join-Path $OutDir "05_cold_sms_policy_block.json")
  }
}

if (-not $SkipBooking) {
  Write-Step "Booking Cal.com slot and syncing HubSpot"
  .\scripts\smoke-booking-sync.ps1 `
    -ProspectEmail $ProspectEmail `
    -ProspectName $ProspectName `
    -Timezone $Timezone `
    -LeadId $LeadId `
    -CompanyName $CompanyName `
    -CompanyDomain $CompanyDomain |
    Tee-Object (Join-Path $OutDir "06_booking_sync.json")
}

Write-Step "Completed"
Write-Host "Evidence directory: $OutDir"
Write-Host "Lead ID: $LeadId"
Write-Host "Expected: orchestration accepted, SMS accepted unless provider rejects, cold SMS blocked, booking confirmed and CRM write successful."
