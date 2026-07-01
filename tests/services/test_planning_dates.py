from datetime import date

from app.models.visit import Visit
from app.services.planning_dates import valid_weekdays, week_out_of_window


def test_valid_weekdays_returns_days_inside_window():
    visit = Visit(from_date=date(2025, 1, 15), to_date=date(2025, 1, 20))
    week_monday = date(2025, 1, 13)  # Mon 13 - Fri 17

    days = valid_weekdays(visit, week_monday)

    assert days == [date(2025, 1, 15), date(2025, 1, 16), date(2025, 1, 17)]


def test_valid_weekdays_falls_back_to_monday_when_no_day_fits():
    visit = Visit(from_date=date(2025, 2, 1), to_date=date(2025, 2, 28))
    week_monday = date(2025, 1, 13)  # entirely before from_date

    days = valid_weekdays(visit, week_monday)

    assert days == [week_monday]


def test_week_out_of_window_true_when_from_date_shifted_past_the_week():
    visit = Visit(from_date=date(2025, 2, 1), to_date=date(2025, 2, 28))
    week_monday = date(2025, 1, 13)

    assert week_out_of_window(visit, week_monday) is True


def test_week_out_of_window_false_when_a_day_still_fits():
    visit = Visit(from_date=date(2025, 1, 16), to_date=date(2025, 1, 30))
    week_monday = date(2025, 1, 13)  # Friday 17 still fits

    assert week_out_of_window(visit, week_monday) is False


def test_week_out_of_window_false_without_from_or_to_date():
    visit = Visit(from_date=None, to_date=None)
    week_monday = date(2025, 1, 13)

    assert week_out_of_window(visit, week_monday) is False
