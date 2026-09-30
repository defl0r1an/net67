"""Логика первичной настройки: что спрашивать и во что превращать ответы.

Своего окна у настройки больше нет — вопросы задаёт обучающий тур
(ui/onboarding/setup_choices.py). Здесь остались чистые решения
(plans.py) и запись ответов (apply.py).
"""

from wizard.plans import SERVICE_CHOICES, WIZARD_STEPS

__all__ = ["SERVICE_CHOICES", "WIZARD_STEPS"]
