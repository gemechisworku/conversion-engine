"""Runtime entrypoint helpers for service wiring."""

from __future__ import annotations

from agent.config.settings import get_settings
from agent.services.calendar.calcom_client import CalComService
from agent.services.crm.hubspot_mcp import HubSpotMCPService
from agent.services.email.client import EmailService, ResendEmailClient
from agent.services.email.router import EmailEventRouter
from agent.services.email.webhook import ResendWebhookParser
from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.jobs_playwright import JobsPlaywrightCollector
from agent.services.enrichment.layoffs import LayoffsAdapter
from agent.services.enrichment.leadership import LeadershipChangeDetector
from agent.services.enrichment.merger import EnrichmentPipeline
from agent.services.policy.outbound_policy import OutboundPolicyService
from agent.services.sms.client import SMSService
from agent.services.sms.router import SMSRouter
from agent.services.sms.webhook import AfricasTalkingWebhookParser


def build_email_service() -> EmailService:
    settings = get_settings()
    policy_service = OutboundPolicyService(settings)
    client = ResendEmailClient(settings=settings, policy_service=policy_service)
    parser = ResendWebhookParser(settings)
    router = EmailEventRouter()
    return EmailService(client=client, parser=parser, router=router)


def build_sms_service() -> SMSService:
    settings = get_settings()
    policy_service = OutboundPolicyService(settings)
    parser = AfricasTalkingWebhookParser(settings)
    router = SMSRouter()
    return SMSService(
        settings=settings,
        policy_service=policy_service,
        parser=parser,
        router=router,
    )


def build_hubspot_service() -> HubSpotMCPService:
    settings = get_settings()
    policy_service = OutboundPolicyService(settings)
    return HubSpotMCPService(settings=settings, policy_service=policy_service)


def build_calcom_service() -> CalComService:
    settings = get_settings()
    policy_service = OutboundPolicyService(settings)
    return CalComService(settings=settings, policy_service=policy_service)


def build_enrichment_services() -> tuple[
    CrunchbaseAdapter,
    JobsPlaywrightCollector,
    LayoffsAdapter,
    LeadershipChangeDetector,
    EnrichmentPipeline,
]:
    settings = get_settings()
    return (
        CrunchbaseAdapter(settings=settings),
        JobsPlaywrightCollector(settings=settings),
        LayoffsAdapter(settings=settings),
        LeadershipChangeDetector(settings=settings),
        EnrichmentPipeline(),
    )
