# Webhook Contract Alignment

This document tracks contract parity between the deployed Render webhook server and local parsing/routing code in `agent/services/*/webhook.py`.

## Status

- Current state: **pending deployed details from environment owner**
- Last updated: 2026-04-23

## Base URL

- `RENDER_WEBHOOK_BASE_URL`: `<pending>`

## Resend

- Deployed route: `<pending>`
- Method: `POST`
- Auth/signature header: `<pending>` (code currently supports configurable header via `RESEND_WEBHOOK_SIGNATURE_HEADER`)
- Retry behavior: `<pending>`
- Expected event types:
  - reply / inbound
  - bounce
  - delivery failure
- Local parser: `agent/services/email/webhook.py`

## Africa's Talking

- Deployed route: `<pending>`
- Method: `POST`
- Auth/signature header: `<pending>` (current parser assumes `x-webhook-signature` with HMAC-SHA256 when secret is configured)
- Retry behavior: `<pending>`
- Local parser: `agent/services/sms/webhook.py`

## Cal.com

- Deployed route: `<pending>`
- Method: `POST`
- Auth/signature header: `<pending>`
- Retry behavior: `<pending>`
- Local callback handling: pending implementation

## Open Questions

1. Exact route paths for each provider.
2. Header names and signature algorithm per provider.
3. Provider retries and duplicate webhook expectations.
4. Canonical payload examples from production/deployed environment.
5. Cal.com webhook event payloads used by the deployed route for booking confirmations.
