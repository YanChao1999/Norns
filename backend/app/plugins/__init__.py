from .base import Plugin, PluginContext, ToolSpec

__all__ = ["Plugin", "PluginCatalog", "PluginContext", "ToolSpec", "load_plugin_catalog"]


def __getattr__(name: str):
    if name in {"PluginCatalog", "load_plugin_catalog"}:
        from .catalog import PluginCatalog, load_plugin_catalog

        return {"PluginCatalog": PluginCatalog, "load_plugin_catalog": load_plugin_catalog}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
