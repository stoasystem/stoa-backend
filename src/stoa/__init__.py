"""Stoa backend.

Our own loggers write INFO. The Lambda Python runtime leaves the root logger
at WARNING and configures nothing else, so without this every `logger.info` in
`stoa` - the sweep's summary, the deletion cycle, the model call events - was
dropped (E29). Every deployed handler imports this package first. Only `stoa`
is raised: the SDKs' loggers stay as they were.
"""

import logging

logging.getLogger("stoa").setLevel(logging.INFO)
