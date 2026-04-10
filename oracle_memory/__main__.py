"""Allow running as ``python -m oracle_memory``."""
import sys
from .cli import main

sys.exit(main())
