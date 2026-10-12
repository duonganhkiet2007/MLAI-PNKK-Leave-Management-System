"""Single calendar source; absence of verified configuration is never a working day."""
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from enum import Enum

class CalendarUnavailable(ValueError): pass

class DayType(str, Enum):
    WORKING_DAY = 'WORKING_DAY'
    WEEKLY_REST_DAY = 'WEEKLY_REST_DAY'
    PUBLIC_HOLIDAY = 'PUBLIC_HOLIDAY'
    COMPENSATORY_DAY_OFF = 'COMPENSATORY_DAY_OFF'

class CalendarService:
    def __init__(self, config_dir=None, working_week=None, timezone=None):
        self.config_dir = Path(config_dir or os.getenv('LEAVE_CALENDAR_DIR', Path(__file__).parent / 'calendars'))
        self.working_week = set(working_week if working_week is not None else
            [int(x) for x in os.getenv('LEAVE_WORKING_WEEK', '0,1,2,3,4').split(',')])
        if not self.working_week or not self.working_week <= set(range(7)):
            raise ValueError('working_week must contain weekdays 0..6')
        self.timezone = ZoneInfo(timezone or os.getenv('LEAVE_TIMEZONE', 'Asia/Ho_Chi_Minh'))
        self._years = {}

    def year(self, year):
        if year in self._years: return self._years[year]
        path = self.config_dir / f'holidays_{year}.json'
        if not path.exists(): raise CalendarUnavailable(f'Lịch {year} chưa được xác minh.')
        data = json.loads(path.read_text())
        if data.get('verified') is not True or data.get('year') != year:
            raise CalendarUnavailable(f'Lịch {year} chưa được xác minh.')
        holidays = {}
        for entry in data['holidays']:
            d = date.fromisoformat(entry['date'])
            if d.year != year or not entry.get('source'): raise CalendarUnavailable('Cấu hình lịch thiếu nguồn/ngày hợp lệ.')
            holidays[d] = entry
        comp = set()
        for d, entry in sorted(holidays.items()):
            if entry['holiday_type'] == 'PUBLIC_HOLIDAY' and d.weekday() not in self.working_week:
                nxt = d + timedelta(days=1)
                while nxt.weekday() not in self.working_week or nxt in holidays or nxt in comp:
                    nxt += timedelta(days=1)
                if nxt.year != year: raise CalendarUnavailable('Ngày nghỉ bù qua năm cần cấu hình đã xác minh.')
                comp.add(nxt)
        self._years[year] = holidays, comp
        return holidays, comp

    def classify(self, d):
        holidays, comp = self.year(d.year)
        if d in holidays: return DayType(holidays[d]['holiday_type'])
        if d in comp: return DayType.COMPENSATORY_DAY_OFF
        if d.weekday() not in self.working_week: return DayType.WEEKLY_REST_DAY
        return DayType.WORKING_DAY

    def days(self, start, end):
        if start > end: return []
        if (end-start).days > 3660: raise ValueError('Khoảng ngày tối đa 10 năm.')
        return [(start + timedelta(days=i), self.classify(start + timedelta(days=i)))
                for i in range((end-start).days + 1)]

    def working_dates(self, start, end):
        return [d for d, kind in self.days(start, end) if kind == DayType.WORKING_DAY]

    def notice_days(self, submitted_at, first_working_day):
        # Internal policy: count working dates [local submission date, first leave date).
        if submitted_at.tzinfo is None: submitted_at = submitted_at.replace(tzinfo=self.timezone)
        start = submitted_at.astimezone(self.timezone).date()
        return len(self.working_dates(start, first_working_day - timedelta(days=1)))


def calculate_workdays(start_date, end_date):
    return len(CalendarService().working_dates(start_date, end_date))
