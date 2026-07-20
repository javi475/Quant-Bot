from datetime import datetime

from hermes.schedules import daily_at, every_n_minutes, hourly_at, monthly_at, weekly_at


def test_every_n_minutes_fires_when_no_last_run():
    predicate = every_n_minutes(5)
    assert predicate(datetime(2026, 1, 1, 0, 0), None)


def test_every_n_minutes_waits_for_interval():
    predicate = every_n_minutes(5)
    last = datetime(2026, 1, 1, 0, 0)
    assert not predicate(datetime(2026, 1, 1, 0, 4), last)
    assert predicate(datetime(2026, 1, 1, 0, 5), last)


def test_hourly_at_requires_correct_minute():
    predicate = hourly_at(0)
    assert not predicate(datetime(2026, 1, 1, 5, 30), None)
    assert predicate(datetime(2026, 1, 1, 5, 0), None)


def test_hourly_at_skips_if_already_run_this_hour():
    predicate = hourly_at(0)
    last = datetime(2026, 1, 1, 5, 0)
    assert not predicate(datetime(2026, 1, 1, 5, 0), last)
    assert predicate(datetime(2026, 1, 1, 6, 0), last)


def test_daily_at_requires_hour_and_minute():
    predicate = daily_at(8, 30)
    assert not predicate(datetime(2026, 1, 1, 8, 0), None)
    assert predicate(datetime(2026, 1, 1, 8, 30), None)


def test_daily_at_skips_if_already_run_today():
    predicate = daily_at(8, 0)
    last = datetime(2026, 1, 1, 8, 0)
    assert not predicate(datetime(2026, 1, 1, 8, 0), last)
    assert predicate(datetime(2026, 1, 2, 8, 0), last)


def test_weekly_at_matches_weekday_hour_minute():
    predicate = weekly_at(0, 0, 0)  # Monday=0
    assert predicate(datetime(2026, 1, 5, 0, 0), None)  # 2026-01-05 is a Monday
    assert not predicate(datetime(2026, 1, 6, 0, 0), None)  # Tuesday


def test_weekly_at_skips_if_already_run_this_week_occurrence():
    predicate = weekly_at(0, 0, 0)
    last = datetime(2026, 1, 5, 0, 0)
    assert not predicate(datetime(2026, 1, 5, 0, 0), last)
    assert predicate(datetime(2026, 1, 12, 0, 0), last)


def test_weekly_at_sunday_weekday_six():
    predicate = weekly_at(6, 0, 0)
    assert predicate(datetime(2026, 1, 11, 0, 0), None)  # 2026-01-11 is a Sunday
    assert not predicate(datetime(2026, 1, 12, 0, 0), None)


def test_monthly_at_matches_day_hour_minute():
    predicate = monthly_at(1, 6, 0)
    assert not predicate(datetime(2026, 1, 2, 6, 0), None)
    assert predicate(datetime(2026, 1, 1, 6, 0), None)


def test_monthly_at_skips_if_already_run_this_month():
    predicate = monthly_at(1, 6, 0)
    last = datetime(2026, 1, 1, 6, 0)
    assert not predicate(datetime(2026, 1, 1, 6, 0), last)
    assert predicate(datetime(2026, 2, 1, 6, 0), last)
