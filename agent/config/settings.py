"""Runtime settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Implements: FR-10, FR-15, FR-16
    # Workflow: outreach_generation_and_review.md
    # Schema: policy_decision.md
    # API: policy_api.md
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        populate_by_name=True,
        extra="ignore",
    )

    challenge_mode: bool = Field(default=True, alias="CHALLENGE_MODE")
    kill_switch_enabled: bool = Field(default=False, alias="KILL_SWITCH_ENABLED")
    sink_routing_enabled: bool = Field(default=False, alias="SINK_ROUTING_ENABLED")

    render_webhook_base_url: str = Field(default="", alias="RENDER_WEBHOOK_BASE_URL")
    webhook_route_resend: str = Field(default="/webhooks/resend", alias="WEBHOOK_ROUTE_RESEND")
    webhook_route_africastalking: str = Field(
        default="/webhooks/africastalking",
        alias="WEBHOOK_ROUTE_AFRICASTALKING",
    )
    webhook_route_calcom: str = Field(default="/webhooks/calcom", alias="WEBHOOK_ROUTE_CALCOM")

    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    resend_from_email: str = Field(default="", alias="RESEND_FROM_EMAIL")
    resend_api_url: str = Field(default="https://api.resend.com", alias="RESEND_API_URL")
    resend_webhook_secret: str = Field(default="", alias="RESEND_WEBHOOK_SECRET")
    resend_webhook_signature_header: str = Field(
        default="resend-signature",
        alias="RESEND_WEBHOOK_SIGNATURE_HEADER",
    )

    africastalking_username: str = Field(default="", alias="AFRICASTALKING_USERNAME")
    africastalking_api_key: str = Field(default="", alias="AFRICASTALKING_API_KEY")
    africastalking_shortcode: str = Field(default="", alias="AFRICASTALKING_SHORTCODE")
    africastalking_webhook_secret: str = Field(default="", alias="AFRICASTALKING_WEBHOOK_SECRET")
    africastalking_api_url: str = Field(
        default="https://api.africastalking.com/version1/messaging",
        alias="AFRICASTALKING_API_URL",
    )

    hubspot_mcp_server_url: str = Field(default="https://mcp.hubspot.com", alias="HUBSPOT_MCP_SERVER_URL")
    hubspot_mcp_access_token: str = Field(
        default="",
        alias="HUBSPOT_MCP_ACCESS_TOKEN",
        validation_alias=AliasChoices("HUBSPOT_MCP_ACCESS_TOKEN", "HUBSPOT_ACCESS_TOKEN"),
    )
    hubspot_mcp_refresh_token: str = Field(default="", alias="HUBSPOT_MCP_REFRESH_TOKEN")
    hubspot_mcp_client_id: str = Field(default="", alias="HUBSPOT_MCP_CLIENT_ID")
    hubspot_mcp_client_secret: str = Field(default="", alias="HUBSPOT_MCP_CLIENT_SECRET")
    hubspot_mcp_oauth_token_url: str = Field(
        default="https://api.hubapi.com/oauth/v1/token",
        alias="HUBSPOT_MCP_OAUTH_TOKEN_URL",
    )
    hubspot_mcp_protocol_version: str = Field(default="2025-06-18", alias="HUBSPOT_MCP_PROTOCOL_VERSION")
    hubspot_mcp_tool_upsert_lead: str = Field(default="", alias="HUBSPOT_MCP_TOOL_UPSERT_LEAD")
    hubspot_mcp_tool_append_event: str = Field(default="", alias="HUBSPOT_MCP_TOOL_APPEND_EVENT")
    hubspot_pipeline_id: str = Field(default="", alias="HUBSPOT_PIPELINE_ID")
    hubspot_company_prop_last_booking_id: str = Field(default="", alias="HUBSPOT_COMPANY_PROP_LAST_BOOKING_ID")
    hubspot_company_prop_last_booking_start_at: str = Field(
        default="",
        alias="HUBSPOT_COMPANY_PROP_LAST_BOOKING_START_AT",
    )
    hubspot_company_prop_last_booking_end_at: str = Field(
        default="",
        alias="HUBSPOT_COMPANY_PROP_LAST_BOOKING_END_AT",
    )
    hubspot_company_prop_last_booking_timezone: str = Field(
        default="",
        alias="HUBSPOT_COMPANY_PROP_LAST_BOOKING_TIMEZONE",
    )
    hubspot_company_prop_last_booking_url: str = Field(
        default="",
        alias="HUBSPOT_COMPANY_PROP_LAST_BOOKING_URL",
    )
    hubspot_company_prop_last_booking_status: str = Field(
        default="",
        alias="HUBSPOT_COMPANY_PROP_LAST_BOOKING_STATUS",
    )

    calcom_api_url: str = Field(default="https://api.cal.com/v2", alias="CALCOM_API_URL")
    calcom_api_key: str = Field(default="", alias="CALCOM_API_KEY")
    calcom_event_type_id: str = Field(default="", alias="CALCOM_EVENT_TYPE_ID")
    calcom_event_type_slug: str = Field(default="", alias="CALCOM_EVENT_TYPE_SLUG")
    calcom_username: str = Field(default="", alias="CALCOM_USERNAME")
    calcom_webhook_secret: str = Field(default="", alias="CALCOM_WEBHOOK_SECRET")

    tenacious_sales_data_path: str = Field(default="", alias="TENACIOUS_SALES_DATA_PATH")

    crunchbase_dataset_path: str = Field(default="", alias="CRUNCHBASE_DATASET_PATH")
    crunchbase_dataset_url: str = Field(default="", alias="CRUNCHBASE_DATASET_URL")
    layoffs_csv_path: str = Field(default="", alias="LAYOFFS_CSV_PATH")
    layoffs_csv_url: str = Field(default="", alias="LAYOFFS_CSV_URL")
    leadership_feed_url: str = Field(default="", alias="LEADERSHIP_FEED_URL")
    cfpb_api_url: str = Field(
        default="https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/",
        alias="CFPB_API_URL",
    )
    cfpb_result_limit: int = Field(default=100, alias="CFPB_RESULT_LIMIT")
    act2_evidence_dir: str = Field(default="outputs/evidence/act2_enrichment", alias="ACT2_EVIDENCE_DIR")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_api_url: str = Field(
        default="https://openrouter.ai/api/v1/chat/completions",
        alias="OPENROUTER_API_URL",
    )
    openrouter_model: str = Field(default="openai/gpt-4.1-mini", alias="OPENROUTER_MODEL")
    state_db_path: str = Field(default="outputs/runtime_state.db", alias="STATE_DB_PATH")
    hubspot_mcp_required_tools_csv: str = Field(default="", alias="HUBSPOT_MCP_REQUIRED_TOOLS_CSV")
    hubspot_mcp_required_tool_count: int = Field(default=9, alias="HUBSPOT_MCP_REQUIRED_TOOL_COUNT")

    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    http_timeout_seconds: float = Field(default=20.0, alias="HTTP_TIMEOUT_SECONDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    serpapi_api_key: str = Field(default="", alias="SERPAPI_API_KEY")

    def require(self, *field_names: str) -> None:
        """Raise a ValueError if required settings are not configured."""
        missing = [name for name in field_names if not getattr(self, name)]
        if missing:
            raise ValueError(f"Missing required settings: {', '.join(sorted(missing))}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
