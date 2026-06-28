"""Alerting framework — multi-channel dispatch for engine events.

Usage::

    from paper_trading.alerting.manager import global_alert_manager
    from paper_trading.alerting.channels.webhook import WebhookChannel

    mgr = global_alert_manager()
    mgr.add_channel(WebhookChannel(url="https://hooks.slack.com/...", format="slack"))

    mgr.critical("Portfolio halted", "Drawdown limit breached", details={"dd": -0.18})
"""

from paper_trading.alerting.channel import Alert, Channel, Severity
from paper_trading.alerting.manager import AlertManager, global_alert_manager

__all__ = ["Alert", "AlertManager", "Channel", "Severity", "global_alert_manager"]
