__all__ = ["TelegramProxyPage"]


def __getattr__(name: str):
    if name == "TelegramProxyPage":
        from .page import TelegramProxyPage

        return TelegramProxyPage
    raise AttributeError(name)
