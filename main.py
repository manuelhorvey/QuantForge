#!/usr/bin/env python3
"""QuantForge — thin dispatcher to the paper trading engine.

The actual entry point is paper_trading/ops/monitor.py.
This module exists as a convenience alias.
"""

import sys
from paper_trading.ops.monitor import main

if __name__ == "__main__":
    sys.exit(main())
