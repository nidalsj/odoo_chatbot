import re
from datetime import date, datetime, time, timedelta, timezone

from zoneinfo import ZoneInfo

from .errors import QueryError

PERIOD_TOKENS = (
    'today', 'yesterday', 'this_week', 'last_week', 'this_month', 'last_month',
    'this_quarter', 'last_quarter', 'this_year', 'last_year',
    'last_7_days', 'last_30_days',
)

_YEAR = re.compile(r'^(\d{4})$')
_MONTH = re.compile(r'^(\d{4})-(\d{2})$')
_ONE_DAY = timedelta(days=1)


def _add_months(first_of_month, months):
    year, month0 = divmod(first_of_month.year * 12 + first_of_month.month - 1 + months, 12)
    return date(year, month0 + 1, 1)


def _quarter_start(day):
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def resolve_period(value, today):
    """Turn a period token into a half open date range [start, end).
    Weeks start on Monday."""
    v = str(value).strip().lower()
    if v == 'today':
        return today, today + _ONE_DAY
    if v == 'yesterday':
        return today - _ONE_DAY, today
    if v in ('this_week', 'last_week'):
        start = today - timedelta(days=today.weekday() + (7 if v == 'last_week' else 0))
        return start, start + timedelta(days=7)
    if v in ('this_month', 'last_month'):
        start = _add_months(today.replace(day=1), -1 if v == 'last_month' else 0)
        return start, _add_months(start, 1)
    if v in ('this_quarter', 'last_quarter'):
        start = _quarter_start(today)
        if v == 'last_quarter':
            start = _add_months(start, -3)
        return start, _add_months(start, 3)
    if v in ('this_year', 'last_year'):
        year = today.year - (1 if v == 'last_year' else 0)
        return date(year, 1, 1), date(year + 1, 1, 1)
    if v == 'last_7_days':
        return today - timedelta(days=6), today + _ONE_DAY
    if v == 'last_30_days':
        return today - timedelta(days=29), today + _ONE_DAY

    try:
        match = _MONTH.match(v)
        if match:
            start = date(int(match.group(1)), int(match.group(2)), 1)
            return start, _add_months(start, 1)
        match = _YEAR.match(v)
        if match:
            year = int(match.group(1))
            return date(year, 1, 1), date(year + 1, 1, 1)
        day = date.fromisoformat(v)
        return day, day + _ONE_DAY
    except ValueError:
        pass
    raise QueryError(f"I don't understand the time period '{value}'.")


def resolve_between(start_iso, end_iso):
    try:
        start, end = date.fromisoformat(str(start_iso)), date.fromisoformat(str(end_iso))
    except ValueError as exc:
        raise QueryError('Dates must look like YYYY-MM-DD.') from exc
    if end < start:
        raise QueryError('The end date is before the start date.')
    return start, end + _ONE_DAY


def user_tz(env):
    """User's timezone falling back to UTC"""
    name = env.context.get('tz') or env.user.tz or 'UTC'
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError):
        return ZoneInfo('UTC')


def to_utc_naive(day, tz):
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)