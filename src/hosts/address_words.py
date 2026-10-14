"""Короткое описание результата проверки адресов, без сети и записи файлов."""

def describe_address_check(report) -> str:
    """Что нашла проверка адресов — одной-двумя фразами для человека. Пусто — сказать нечего."""
    if report is None or not report.network:
        return ""
    parts: list[str] = []
    if report.added:
        parts.append("Взяты свежие адреса: " + ", ".join(_short(name) for name in report.added) + ".")
    if report.dropped:
        parts.append("Неработающие адреса убраны: " + ", ".join(_short(name) for name in report.dropped) + ".")
    if report.silent:
        parts.append(
            "Ни один адрес не ответил: " + ", ".join(_short(name) for name in report.silent) + " — оставлены прежние адреса."
        )
    return " ".join(parts)

def _short(service_name: str) -> str:
    """Название сервиса без пояснения в скобках."""
    return str(service_name).split(" (", 1)[0]
