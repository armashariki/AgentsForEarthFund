"""Date helpers for UC-I-1 target-month discipline."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime


def parse_target_month(target_month: str) -> tuple[date, date]:
    """Return inclusive start/end dates for a YYYY-MM target month."""
    start = datetime.strptime(target_month, "%Y-%m").date()
    if start.month == 12:
        next_month = date(start.year + 1, 1, 1)
    else:
        next_month = date(start.year, start.month + 1, 1)
    return start, next_month - timedelta(days=1)


def scan_window_for_month(target_month: str, lookback_days: int = 45) -> tuple[date, date]:
    """Return the wide source-monitor window for a target month."""
    start, end = parse_target_month(target_month)
    return start - timedelta(days=lookback_days), end


def in_target_month(value: str | None, target_month: str) -> bool:
    """Return whether an ISO-ish date falls inside target month."""
    parsed = parse_date(value)
    if not parsed:
        return False
    start, end = parse_target_month(target_month)
    return start <= parsed <= end


def parse_date(value: str | None) -> date | None:
    """Parse common API/RSS date strings to a date."""
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    for candidate in (text, text[:10]):
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    try:
        return parsedate_to_datetime(text).date()
    except (TypeError, ValueError, AttributeError, IndexError, OverflowError):
        return None

