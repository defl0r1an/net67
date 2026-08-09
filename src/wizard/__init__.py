"""Мастер первого запуска.

Три экрана: выбор сервисов, автоподбор настроек через blockcheck и
поведение при запуске. Результат превращается в OneClickRequest, который
исполняет оркестратор из пакета oneclick.
"""

from wizard.plans import SERVICE_CHOICES, WIZARD_STEPS

__all__ = ["SERVICE_CHOICES", "WIZARD_STEPS"]
