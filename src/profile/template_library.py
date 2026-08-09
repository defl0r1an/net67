from __future__ import annotations

from core.paths import AppPaths

from .models import EngineName, Profile
from .template_catalog import load_profile_templates
from .user_profiles import load_user_profile_templates


def load_profile_template_library(paths: AppPaths, engine: EngineName | str) -> dict[str, Profile]:
    templates = dict(load_profile_templates(paths, engine))  # type: ignore[arg-type]
    templates.update(load_user_profile_templates(paths, engine))
    return templates
