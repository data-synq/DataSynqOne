"""Keep tests independent from the operator's deployment environment."""

import os

os.environ["ENVIRONMENT"] = "test"
