import os

ENVIRONMENT = os.getenv("DJANGO_ENV", "dev").lower()

if ENVIRONMENT == "prod":
    from .prod import *
else:
    from .dev import *
