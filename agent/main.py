"""Runtime entrypoint helpers for service wiring."""

from __future__ import annotations

from agent.config.logging import configure_logging
from agent.config.settings import get_settings
from agent.services.calendar.calcom_client import CalComService
from agent.services.crm.hubspot_mcp import HubSpotMCPService
from agent.services.email.client import EmailService, ResendEmailClient
from agent.services.email.router import EmailEventRouter
from agent.services.email.webhook import ResendWebhookParser
from agent.services.enrichment.act2_pipeline import ActIIEnrichmentPipeline
from agent.services.enrichment.artifact_writer import EnrichmentArtifactWriter
from agent.services.enrichment.cfpb import CFPBComplaintAdapter
from agent.services.enrichment.crunchbase import CrunchbaseAdapter
from agent.services.enrichment.competitor_gap import CompetitorGapAnalyst
from agent.services.enrichment.jobs_playwright import JobsPlaywrightCollector
from agent.services.enrichment.layoffs import LayoffsAdapter
from agent.services.enrichment.leadership import LeadershipChangeDetector
from agent.services.enrichment.llm import OpenRouterJSONClient
from agent.services.enrichment.merger import EnrichmentPipeline
from agent.services.enrichment.news_playwright import PublicNewsPlaywrightRetriever
from agent.services.orchestration.runtime import OrchestrationRuntime
from agent.services.policy.outbound_policy import OutboundPolicyService
from agent.services.sms.client import SMSService
from agent.services.sms.router import SMSRouter
from agent.services.sms.webhook import AfricasTalkingWebhookParser
from agent.repositories.state_repo import SQLiteStateRepository


def build_email_service(state_repo: SQLiteStateRepository | None = None) -> EmailService:
    settings = get_settings()
    policy_service = OutboundPolicyService(settings)
    client = ResendEmailClient(settings=settings, policy_service=policy_service)
    parser = ResendWebhookParser(settings)
    router = EmailEventRouter()
    repo = state_repo if state_repo is not None else build_state_repo()
    return EmailService(client=client, parser=parser, router=router, state_repo=repo)


def build_sms_service() -> SMSService:
    settings = get_settings()
    policy_service = OutboundPolicyService(settings)
    parser = AfricasTalkingWebhookParser(settings)
    router = SMSRouter()
    state_repo = SQLiteStateRepository(db_path=settings.state_db_path)
    return SMSService(
        settings=settings,
        policy_service=policy_service,
        parser=parser,
        router=router,
        state_repo=state_repo,
    )


def build_state_repo() -> SQLiteStateRepository:
    settings = get_settings()
    return SQLiteStateRepository(db_path=settings.state_db_path)


def build_orchestration_runtime() -> OrchestrationRuntime:
    configure_logging()
    settings = get_settings()
    state_repo = build_state_repo()
    crunchbase, jobs, layoffs, leadership, merger, competitor_gap, llm = build_enrichment_services()
    enrichment_services = {
        "settings": settings,
        "crunchbase": crunchbase,
        "jobs": jobs,
        "layoffs": layoffs,
        "leadership": leadership,
        "merger": merger,
        "competitor_gap": competitor_gap,
        "llm": llm,
        "artifact_writer": EnrichmentArtifactWriter(settings=settings),
        "cfpb": CFPBComplaintAdapter(settings=settings),
        "news": PublicNewsPlaywrightRetriever(settings=settings),
    }
    enrichment_services["act2_pipeline"] = ActIIEnrichmentPipeline(
        settings=settings,
        crunchbase=crunchbase,
        cfpb=enrichment_services["cfpb"],
        news=enrichment_services["news"],
    )
    return OrchestrationRuntime(
        settings=settings,
        state_repo=state_repo,
        enrichment_services=enrichment_services,
        hubspot_service=build_hubspot_service(),
        calcom_service=build_calcom_service(),
        email_service=build_email_service(state_repo=state_repo),
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
    CompetitorGapAnalyst,
    OpenRouterJSONClient,
]:
    settings = get_settings()
    llm = OpenRouterJSONClient(settings=settings)
    return (
        CrunchbaseAdapter(settings=settings),
        JobsPlaywrightCollector(settings=settings),
        LayoffsAdapter(settings=settings),
        LeadershipChangeDetector(settings=settings),
        EnrichmentPipeline(),
        CompetitorGapAnalyst(settings=settings, llm=llm),
        llm,
    )
