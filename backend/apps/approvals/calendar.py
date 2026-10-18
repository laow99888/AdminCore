"""Frozen working calendars. Durations consume real elapsed time inside local work windows."""
from datetime import date, datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError


def _minute(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-2][0-9]:[0-5][0-9]', value):
        raise ValidationError('工作时段必须为同日有效时间且至少60分钟')
    hour, minute = map(int, value.split(':'))
    if hour > 23:
        raise ValidationError('工作时段必须为同日有效时间且至少60分钟')
    return hour * 60 + minute


def validate_calendar(value):
    if not isinstance(value, dict) or set(value) != {
            'timezone', 'weekdays', 'start', 'end', 'closed_dates', 'extra_dates'}:
        raise ValidationError('工作日历必须包含时区、工作日、时段、休息日与补班日')
    try:
        if not isinstance(value['timezone'], str) or len(value['timezone']) > 64:
            raise ValueError
        ZoneInfo(value['timezone'])
    except (ValueError, ZoneInfoNotFoundError):
        raise ValidationError('工作日历时区无效') from None
    days = value['weekdays']
    if (not isinstance(days, list) or not 1 <= len(days) <= 7
            or any(type(day) is not int or not 1 <= day <= 7 for day in days) or len(set(days)) != len(days)):
        raise ValidationError('工作日必须为不重复的1至7整数')
    if _minute(value['end']) - _minute(value['start']) < 60:
        raise ValidationError('工作时段必须为同日有效时间且至少60分钟')
    dates = []
    for key in ('closed_dates', 'extra_dates'):
        rows = value[key]
        if not isinstance(rows, list) or len(rows) > 366:
            raise ValidationError('休息日和补班日各最多366个有效日期且不能重复或重叠')
        parsed = set()
        for row in rows:
            try:
                if not isinstance(row, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', row):
                    raise ValueError
                parsed.add(date.fromisoformat(row))
            except ValueError:
                raise ValidationError('休息日和补班日各最多366个有效日期且不能重复或重叠') from None
        if len(parsed) != len(rows):
            raise ValidationError('休息日和补班日各最多366个有效日期且不能重复或重叠')
        dates.append(parsed)
    if dates[0] & dates[1]:
        raise ValidationError('休息日和补班日各最多366个有效日期且不能重复或重叠')


def _boundary(day, minute, zone, *, end=False):
    local = datetime.combine(day, time(minute // 60, minute % 60))
    # Ambiguous start opens at the first instant; ambiguous end closes at the last.
    # A nonexistent boundary advances to the first real local minute (including skipped dates).
    for _ in range(1441):
        valid = set()
        for fold in (0, 1):
            instant = local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
            if instant.astimezone(zone).replace(tzinfo=None) == local:
                valid.add(instant)
        if valid:
            return max(valid) if end else min(valid)
        local += timedelta(minutes=1)
    raise ValidationError('工作日历无法计算有效截止时间')


def deadline(now, minutes, calendar=None):
    if calendar is None:
        return now + timedelta(minutes=minutes)
    zone = ZoneInfo(calendar['timezone'])
    current = now.astimezone(timezone.utc)
    day = current.astimezone(zone).date()
    remaining = timedelta(minutes=minutes)
    start, finish = _minute(calendar['start']), _minute(calendar['end'])
    closed, extra = set(calendar['closed_dates']), set(calendar['extra_dates'])
    try:
        # At least one hour per working day and one day per week: < 63000 days
        # for the maximum duration, plus at most 366 explicit closed dates.
        for _ in range(100000):
            if day.isoformat() in extra or (day.isoweekday() in calendar['weekdays'] and day.isoformat() not in closed):
                begin = max(current, _boundary(day, start, zone))
                end = _boundary(day, finish, zone, end=True)
                if end > begin:
                    available = end - begin
                    if remaining <= available:
                        return begin + remaining
                    remaining -= available
            day += timedelta(days=1)
    except (OverflowError, ValueError):
        pass
    raise ValidationError('工作日历无法计算有效截止时间')
