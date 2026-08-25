from __future__ import annotations

from dataclasses import dataclass

from .models.connector import SECRET_CONFIG_KEYS, Connector, ConnectorType

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_CURSOR_BASE_URL = "https://api.cursor.com/v1"
DEFAULT_CURSOR_MODEL = "auto"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"

# Cursor, then DeepSeek, then OpenAI so a newly added provider is not shadowed by an existing OpenAI connector.
LLM_CONNECTOR_TYPES = (ConnectorType.CURSOR, ConnectorType.DEEPSEEK, ConnectorType.OPENAI)
LLM_LABELS = {
    ConnectorType.CURSOR: "Cursor",
    ConnectorType.DEEPSEEK: "DeepSeek",
    ConnectorType.OPENAI: "OpenAI",
}
LLM_DEFAULTS: dict[ConnectorType, tuple[str, str]] = {
    ConnectorType.CURSOR: (DEFAULT_CURSOR_BASE_URL, DEFAULT_CURSOR_MODEL),
    ConnectorType.DEEPSEEK: (DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL),
    ConnectorType.OPENAI: (DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL),
}


@dataclass(frozen=True, slots=True)
class LlmCredentials:
    api_key: str
    base_url: str
    default_model: str
    provider: str = "openai"


OpenAICredentials = LlmCredentials


def merge_connector_config(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    for key, value in incoming.items():
        if key in SECRET_CONFIG_KEYS and not str(value or "").strip():
            continue
        merged[key] = value
    return merged


def resolve_llm_credentials(connectors: list[Connector], settings) -> LlmCredentials:
    found: dict[ConnectorType, LlmCredentials] = {}
    for connector in connectors:
        if connector.connector_type not in LLM_CONNECTOR_TYPES or not connector.is_active:
            continue
        config = connector.get_config()
        key = str(config.get("api_key") or "").strip()
        if not key:
            continue
        default_url, default_model = LLM_DEFAULTS[connector.connector_type]
        url = str(config.get("base_url") or "").strip() or default_url
        model = str(config.get("default_model") or "").strip() or default_model
        found[connector.connector_type] = LlmCredentials(
            api_key=key,
            base_url=url,
            default_model=model,
            provider=connector.connector_type.value,
        )
    for connector_type in LLM_CONNECTOR_TYPES:
        if connector_type in found:
            return found[connector_type]
    for connector_type in LLM_CONNECTOR_TYPES:
        env_creds = _env_credentials(settings, connector_type)
        if env_creds.api_key:
            return env_creds
    url, model = LLM_DEFAULTS[ConnectorType.OPENAI]
    return LlmCredentials(api_key="", base_url=url, default_model=model)


def resolve_openai_credentials(connectors: list[Connector], settings) -> LlmCredentials:
    return resolve_llm_credentials(connectors, settings)


def llm_is_configured(connectors: list[Connector], settings) -> bool:
    return bool(resolve_llm_credentials(connectors, settings).api_key)


def openai_is_configured(connectors: list[Connector], settings) -> bool:
    return llm_is_configured(connectors, settings)


def _env_credentials(settings, connector_type: ConnectorType) -> LlmCredentials:
    default_url, default_model = LLM_DEFAULTS[connector_type]
    if connector_type is ConnectorType.CURSOR:
        key = str(getattr(settings, "cursor_api_key", "") or "").strip()
        url = str(getattr(settings, "cursor_base_url", "") or "").strip() or default_url
        model = str(getattr(settings, "cursor_default_model", "") or "").strip() or default_model
    elif connector_type is ConnectorType.DEEPSEEK:
        key = str(getattr(settings, "deepseek_api_key", "") or "").strip()
        url = str(getattr(settings, "deepseek_base_url", "") or "").strip() or default_url
        model = str(getattr(settings, "deepseek_default_model", "") or "").strip() or default_model
    else:
        key = str(getattr(settings, "openai_api_key", "") or "").strip()
        url = str(getattr(settings, "openai_base_url", "") or "").strip() or default_url
        model = str(getattr(settings, "default_model", "") or "").strip() or default_model
    return LlmCredentials(api_key=key, base_url=url, default_model=model, provider=connector_type.value)
