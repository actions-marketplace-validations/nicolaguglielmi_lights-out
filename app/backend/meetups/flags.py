"""OpenFeature client, flagd provider selected by environment (docs/adr/0007)."""

import os

from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.evaluation_context import EvaluationContext

api.set_provider_and_wait(FlagdProvider())
_client = api.get_client()
_context = EvaluationContext(
    attributes={"version": os.environ.get("APP_VERSION", "dev")}
)


def waitlist_enabled() -> bool:
    return _client.get_boolean_value("waitlist", default_value=False, evaluation_context=_context)
