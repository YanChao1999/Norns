from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .models.connector import SECRET_CONFIG_KEYS, Connector, ConnectorType

logger = logging.getLogger("norns")

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_CURSOR_BASE_URL = "https://api.cursor.com/v1"
DEFAULT_CURSOR_MODEL = "auto"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"

# Prefer providers that speak OpenAI chat completions. Native Cursor API does not.
LLM_CONNECTOR_TYPES = (ConnectorType.DEEPSEEK, ConnectorType.OPENAI, ConnectorType.CURSOR)
LLM_LABELS = {
    ConnectorType.CURSOR: "Cursor",
    ConnectorType.DEEPSEEK: "DeepSeek",
    ConnectorType.OPENAI: "OpenAI",
}


def provider_label(provider: str) -> str:
    key = str(provider or "").strip().lower()
    for connector_type, label in LLM_LABELS.items():
        if connector_type.value == key:
            return label
    return key.title() or "LLM"


LLM_DEFAULTS: dict[ConnectorType, tuple[str, str]] = {
    ConnectorType.CURSOR: (DEFAULT_CURSOR_BASE_URL, DEFAULT_CURSOR_MODEL),
    ConnectorType.DEEPSEEK: (DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_DEEPSEEK_MODEL),
    ConnectorType.OPENAI: (DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL),
}
FALLBACK_MODELS: dict[ConnectorType, tuple[str, ...]] = {
    ConnectorType.OPENAI: ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o3-mini", "o4-mini"),
    # DeepSeek chat API currently advertises these ids (passing Cursor's "auto" fails with 400).
    ConnectorType.DEEPSEEK: (
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-vision-exp",
        "deepseek-chat",
        "deepseek-reasoner",
    ),
    # Curated when cursor-sdk list_models fails; keep in sync with Cursor.models.list() favorites.
    ConnectorType.CURSOR: (
        "auto",
        "auto-smart",
        "composer-2",
        "composer-2.5",
        "grok-4.6",
        "claude-sonnet-4-5",
        "claude-opus-4-6",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gemini-3-flash",
        "kimi-k2.7-code",
    ),
}

# Model ids that only make sense on Cursor Cloud Agents / Cursor Router.
CURSOR_ONLY_MODEL_IDS = frozenset({"auto", "auto-smart", "default"})

# OpenAI / DeepSeek chat ids that Cursor Cloud Agents reject (e.g. legacy board default gpt-4o).
_NON_CURSOR_CHAT_MODEL_IDS = frozenset(
    {
        *(m.lower() for m in FALLBACK_MODELS[ConnectorType.OPENAI]),
        *(m.lower() for m in FALLBACK_MODELS[ConnectorType.DEEPSEEK]),
        "gpt-4",
        "gpt-3.5-turbo",
        "chatgpt-4o-latest",
    }
)


@dataclass(frozen=True, slots=True)
class LlmCredentials:
    api_key: str
    base_url: str
    default_model: str
    provider: str = "openai"
    repo_url: str = ""


OpenAICredentials = LlmCredentials

CURSOR_CHAT_UNSUPPORTED_MESSAGE = (
    "Cursor’s api.cursor.com host is not OpenAI-compatible (no POST /v1/chat/completions). "
    "Norns runs Cursor stages through cursor-sdk Cloud Agents instead."
)


def is_native_cursor_api_host(base_url: str) -> bool:
    host = str(base_url or "").strip().lower()
    return "api.cursor.com" in host or host in {"", "https://api.cursor.com", "https://api.cursor.com/v1"}


def uses_cursor_cloud_agent(provider: str, base_url: str) -> bool:
    """True when stage runs should call Cursor Cloud Agents instead of OpenAI chat completions."""
    provider_name = str(provider or "").strip().lower()
    url = str(base_url or "").strip().lower()
    if provider_name == "cursor":
        # A custom OpenAI-compatible proxy stays on the OpenAI SDK path.
        return not url or "api.cursor.com" in url
    return "api.cursor.com" in url


def _is_foreign_to_cursor(model: str) -> bool:
    """True for OpenAI/DeepSeek chat ids that Cursor Cloud Agents reject."""
    name = str(model or "").strip().lower()
    if not name or name in CURSOR_ONLY_MODEL_IDS:
        return False
    if name.startswith("deepseek"):
        return True
    return name in _NON_CURSOR_CHAT_MODEL_IDS


def resolve_stage_model(
    *,
    provider: str,
    base_url: str,
    stage_model: str,
    default_model: str,
) -> str:
    """Pick a model id that the selected provider can actually call.

    Stages often keep Cursor's ``auto`` after switching the provider to DeepSeek/OpenAI;
    OpenAI-compatible APIs reject that id (DeepSeek 400). Conversely, board defaults like
    ``gpt-4o`` must be remapped when the stage runs on Cursor Cloud Agents.
    """
    fallback = str(default_model or "").strip()
    model = str(stage_model or "").strip() or fallback
    if uses_cursor_cloud_agent(provider, base_url):
        if not model or _is_foreign_to_cursor(model):
            cursor_default = fallback if fallback and not _is_foreign_to_cursor(fallback) else DEFAULT_CURSOR_MODEL
            return cursor_default
        return model
    if not model or model.lower() in CURSOR_ONLY_MODEL_IDS:
        return fallback or model
    return model


def supports_chat_completions(creds: LlmCredentials) -> bool:
    """Whether this connector can power a stage run (OpenAI chat or Cursor Cloud Agents)."""
    return bool(creds.api_key.strip())


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
            repo_url=str(config.get("repo_url") or "").strip(),
        )
    # Prefer a provider that can actually run chat completions.
    for connector_type in LLM_CONNECTOR_TYPES:
        creds = found.get(connector_type)
        if creds and supports_chat_completions(creds):
            return creds
    for connector_type in LLM_CONNECTOR_TYPES:
        env_creds = _env_credentials(settings, connector_type)
        if supports_chat_completions(env_creds):
            return env_creds
    # Fall back to any configured key (may be Cursor native — runner explains).
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


def llm_key_present(connectors: list[Connector], settings) -> bool:
    """True when an API key is stored — does not verify the key works."""
    return supports_chat_completions(resolve_llm_credentials(connectors, settings))


async def llm_is_configured(connectors: list[Connector], settings) -> bool:
    """True when a key is present and the provider accepts it (model list succeeds)."""
    creds = resolve_llm_credentials(connectors, settings)
    if not supports_chat_completions(creds):
        return False
    catalog = await fetch_llm_model_catalog(creds)
    return catalog_credentials_usable(catalog)


def openai_is_configured(connectors: list[Connector], settings) -> bool:
    return llm_key_present(connectors, settings)


def catalog_credentials_usable(catalog: LlmModelCatalog) -> bool:
    """Catalog entries are usable only when listing succeeded (no auth/network error)."""
    return not bool(str(catalog.error or "").strip())


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


@dataclass(frozen=True, slots=True)
class LlmModelEntry:
    id: str
    provider: str
    label: str
    usable: bool
    source: str


@dataclass(frozen=True, slots=True)
class LlmModelCatalog:
    provider: str
    default_model: str
    models: list[str]
    source: str  # "api" | "fallback" | "mixed"
    error: str = ""
    entries: list[LlmModelEntry] = field(default_factory=list)


def credentials_for_provider(
    connectors: list[Connector], settings, provider: ConnectorType | str | None = None
) -> LlmCredentials:
    if provider is None or str(provider).strip() == "":
        return resolve_llm_credentials(connectors, settings)
    try:
        connector_type = (
            provider if isinstance(provider, ConnectorType) else ConnectorType(str(provider).strip().lower())
        )
    except ValueError:
        return resolve_llm_credentials(connectors, settings)
    if connector_type not in LLM_CONNECTOR_TYPES:
        return resolve_llm_credentials(connectors, settings)
    for connector in connectors:
        if connector.connector_type != connector_type or not connector.is_active:
            continue
        config = connector.get_config()
        key = str(config.get("api_key") or "").strip()
        if not key:
            continue
        default_url, default_model = LLM_DEFAULTS[connector_type]
        url = str(config.get("base_url") or "").strip() or default_url
        model = str(config.get("default_model") or "").strip() or default_model
        return LlmCredentials(
            api_key=key,
            base_url=url,
            default_model=model,
            provider=connector_type.value,
            repo_url=str(config.get("repo_url") or "").strip(),
        )
    env_creds = _env_credentials(settings, connector_type)
    if env_creds.api_key:
        return env_creds
    url, model = LLM_DEFAULTS[connector_type]
    return LlmCredentials(api_key="", base_url=url, default_model=model, provider=connector_type.value)


def fallback_models_for(provider: str) -> list[str]:
    try:
        connector_type = ConnectorType(provider)
    except ValueError:
        connector_type = ConnectorType.OPENAI
    default_model = LLM_DEFAULTS.get(connector_type, LLM_DEFAULTS[ConnectorType.OPENAI])[1]
    models = list(FALLBACK_MODELS.get(connector_type, FALLBACK_MODELS[ConnectorType.OPENAI]))
    if default_model not in models:
        models.insert(0, default_model)
    return models


def filter_chat_model_ids(provider: str, model_ids: list[str], *, default_model: str = "") -> list[str]:
    """Keep chat-oriented ids; OpenAI /v1/models returns hundreds of embeddings/audio rows.

    When the remote list is empty (or fully filtered), pad with the curated provider fallback
    list. Previously, inserting ``default_model`` first left ``preferred`` non-empty so Cursor
    collapsed to only ``auto`` whenever list_models failed.
    """
    preferred: list[str] = []
    seen: set[str] = set()

    def add(model_id: str) -> None:
        name = model_id.strip()
        if not name or name in seen:
            return
        seen.add(name)
        preferred.append(name)

    if default_model.strip():
        add(default_model.strip())
    added_from_remote = False
    # Preserve Cursor API order (recommended catalog); sort OpenAI/DeepSeek for stability.
    remote_ids = model_ids if provider == "cursor" else sorted(model_ids)
    for model_id in remote_ids:
        if _is_chat_model_id(provider, model_id):
            add(model_id)
            added_from_remote = True
    if not added_from_remote:
        for model_id in fallback_models_for(provider):
            add(model_id)
    return preferred


def _is_chat_model_id(provider: str, model_id: str) -> bool:
    name = model_id.strip().lower()
    if not name:
        return False
    if provider == "deepseek":
        return name.startswith("deepseek")
    if provider == "cursor":
        return True
    if name.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4")):
        return True
    if any(
        token in name
        for token in (
            "instruct",
            "embedding",
            "whisper",
            "tts",
            "dall-e",
            "moderation",
            "realtime",
            "transcribe",
            "image",
        )
    ):
        return False
    return name.startswith("ft:") and "gpt" in name


def _catalog_entries(
    catalog: LlmModelCatalog,
    creds: LlmCredentials,
    *,
    display_names: dict[str, str] | None = None,
) -> list[LlmModelEntry]:
    try:
        label_prefix = LLM_LABELS[ConnectorType(catalog.provider)]
    except ValueError:
        label_prefix = catalog.provider
    # Key present is not enough: a 401/list failure must mark models unusable (#30/#34).
    usable = supports_chat_completions(creds) and catalog_credentials_usable(catalog)
    names = display_names or {}
    return [
        LlmModelEntry(
            id=model_id,
            provider=catalog.provider,
            label=f"{names.get(model_id) or model_id} · {label_prefix}",
            usable=usable,
            source=catalog.source,
        )
        for model_id in catalog.models
    ]


async def fetch_llm_model_catalog(creds: LlmCredentials) -> LlmModelCatalog:
    fallback = filter_chat_model_ids(creds.provider, [], default_model=creds.default_model)
    if not creds.api_key.strip():
        catalog = LlmModelCatalog(
            provider=creds.provider,
            default_model=creds.default_model or fallback[0],
            models=fallback,
            source="fallback",
            error="No API key configured for this provider",
        )
        return LlmModelCatalog(
            provider=catalog.provider,
            default_model=catalog.default_model,
            models=catalog.models,
            source=catalog.source,
            error=catalog.error,
            entries=_catalog_entries(catalog, creds),
        )
    try:
        if uses_cursor_cloud_agent(creds.provider, creds.base_url):
            from . import cursor_api as cursor_api_mod

            remote = await cursor_api_mod.list_cursor_model_infos(creds.api_key, base_url=creds.base_url)
            remote_ids = [item.id for item in remote]
            display_names = {item.id: item.display_name for item in remote if item.display_name}
            # Only keep the connector default when the live catalog actually includes it
            # (a stale gpt-4o default must not appear as an API-sourced Cursor model).
            configured = str(creds.default_model or "").strip()
            default_in_catalog = configured if configured in remote_ids else ""
            models = filter_chat_model_ids(creds.provider, remote_ids, default_model=default_in_catalog)
            if default_in_catalog:
                default_model = default_in_catalog
            elif DEFAULT_CURSOR_MODEL in models:
                default_model = DEFAULT_CURSOR_MODEL
            else:
                default_model = models[0] if models else fallback[0]
            catalog = LlmModelCatalog(
                provider=creds.provider,
                default_model=default_model,
                models=models or fallback,
                source="api",
            )
            logger.info(
                "Loaded %d Cursor models from API for agent selection (default=%s)",
                len(catalog.models),
                catalog.default_model,
            )
            return LlmModelCatalog(
                provider=catalog.provider,
                default_model=catalog.default_model,
                models=catalog.models,
                source=catalog.source,
                entries=_catalog_entries(catalog, creds, display_names=display_names),
            )

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=creds.api_key.strip(), base_url=creds.base_url, timeout=8.0)
        page = await client.models.list()
        remote_ids = [str(item.id) for item in page.data if getattr(item, "id", None)]
        models = filter_chat_model_ids(creds.provider, remote_ids, default_model=creds.default_model)
        catalog = LlmModelCatalog(
            provider=creds.provider,
            default_model=creds.default_model or (models[0] if models else fallback[0]),
            models=models or fallback,
            source="api",
        )
        return LlmModelCatalog(
            provider=catalog.provider,
            default_model=catalog.default_model,
            models=catalog.models,
            source=catalog.source,
            entries=_catalog_entries(catalog, creds),
        )
    except Exception as exc:  # noqa: BLE001 — any provider/network error falls back to curated list
        err = str(exc)[:240]
        logger.warning(
            "LLM model list failed for %s (%s); using curated fallback (%d models)",
            creds.provider,
            err,
            len(fallback),
        )
        catalog = LlmModelCatalog(
            provider=creds.provider,
            default_model=creds.default_model or fallback[0],
            models=fallback,
            source="fallback",
            error=err,
        )
        return LlmModelCatalog(
            provider=catalog.provider,
            default_model=catalog.default_model,
            models=catalog.models,
            source=catalog.source,
            error=catalog.error,
            entries=_catalog_entries(catalog, creds),
        )


async def fetch_all_llm_model_catalogs(connectors: list[Connector], settings) -> LlmModelCatalog:
    """Models from every configured LLM provider, labeled by API so ids like auto are unambiguous."""
    entries: list[LlmModelEntry] = []
    errors: list[str] = []
    sources: set[str] = set()
    primary = resolve_llm_credentials(connectors, settings)
    seen_keys: set[str] = set()
    for connector_type in LLM_CONNECTOR_TYPES:
        creds = credentials_for_provider(connectors, settings, connector_type)
        if not creds.api_key.strip() and connector_type.value != primary.provider:
            # Still show curated fallbacks for the form when asking a specific provider endpoint;
            # for the combined agent list, only include providers that have a key (or primary empty).
            continue
        if not creds.api_key.strip():
            continue
        catalog = await fetch_llm_model_catalog(creds)
        sources.add(catalog.source)
        if catalog.error:
            errors.append(f"{catalog.provider}: {catalog.error}")
        for entry in catalog.entries:
            key = f"{entry.provider}::{entry.id}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entries.append(entry)
    if not entries:
        # No keys — still return primary provider fallbacks labeled.
        catalog = await fetch_llm_model_catalog(primary)
        return catalog
    usable_default = next((e for e in entries if e.usable and e.provider == primary.provider), None)
    if usable_default is None:
        usable_default = next((e for e in entries if e.usable), entries[0])
    return LlmModelCatalog(
        provider=primary.provider if primary.api_key else usable_default.provider,
        default_model=primary.default_model if supports_chat_completions(primary) else usable_default.id,
        models=[
            e.id for e in entries if e.provider == (primary.provider if primary.api_key else usable_default.provider)
        ],
        source="mixed" if len(sources) > 1 else next(iter(sources), "fallback"),
        error="; ".join(errors),
        entries=entries,
    )
