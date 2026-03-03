import os

environment = os.getenv("DJANGO_ENV", "dev").strip().lower()

if environment == "prod":
    from .prod import *  # noqa: F403
else:
    from .dev import *  # noqa: F403

