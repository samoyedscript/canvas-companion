"""NUS AY2025-2026 academic calendar data and helpers.

Dates extracted from the official NUS Registrar calendar:
https://nus.edu.sg/registrar/docs/default-source/calendar/ay2025-2026.pdf
"""

from __future__ import annotations

from datetime import date

# Each period is (label, start_date, end_date).
# For instructional weeks, the label is "Week N".
AY_2025_2026 = {
    "ay_name": "AY2025-2026",
    "semesters": [
        {
            "name": "Semester 1",
            "periods": [
                ("Orientation Week", date(2025, 8, 4), date(2025, 8, 9)),
                ("Week 1", date(2025, 8, 11), date(2025, 8, 15)),
                ("Week 2", date(2025, 8, 18), date(2025, 8, 22)),
                ("Week 3", date(2025, 8, 25), date(2025, 8, 29)),
                ("Week 4", date(2025, 9, 1), date(2025, 9, 5)),
                ("Week 5", date(2025, 9, 8), date(2025, 9, 12)),
                ("Week 6", date(2025, 9, 15), date(2025, 9, 19)),
                ("Recess Week", date(2025, 9, 20), date(2025, 9, 28)),
                ("Week 7", date(2025, 9, 29), date(2025, 10, 4)),
                ("Week 8", date(2025, 10, 6), date(2025, 10, 10)),
                ("Week 9", date(2025, 10, 13), date(2025, 10, 17)),
                ("Week 10", date(2025, 10, 20), date(2025, 10, 24)),
                ("Week 11", date(2025, 10, 27), date(2025, 10, 31)),
                ("Week 12", date(2025, 11, 3), date(2025, 11, 7)),
                ("Week 13", date(2025, 11, 10), date(2025, 11, 14)),
                ("Reading Week", date(2025, 11, 15), date(2025, 11, 21)),
                ("Examination", date(2025, 11, 22), date(2025, 12, 6)),
                ("Vacation", date(2025, 12, 7), date(2026, 1, 11)),
            ],
        },
        {
            "name": "Semester 2",
            "periods": [
                ("Week 1", date(2026, 1, 12), date(2026, 1, 16)),
                ("Week 2", date(2026, 1, 19), date(2026, 1, 23)),
                ("Week 3", date(2026, 1, 26), date(2026, 1, 30)),
                ("Week 4", date(2026, 2, 2), date(2026, 2, 6)),
                ("Week 5", date(2026, 2, 9), date(2026, 2, 13)),
                ("Week 6", date(2026, 2, 16), date(2026, 2, 20)),
                ("Recess Week", date(2026, 2, 21), date(2026, 3, 1)),
                ("Week 7", date(2026, 3, 2), date(2026, 3, 7)),
                ("Week 8", date(2026, 3, 9), date(2026, 3, 13)),
                ("Week 9", date(2026, 3, 16), date(2026, 3, 20)),
                ("Week 10", date(2026, 3, 23), date(2026, 3, 27)),
                ("Week 11", date(2026, 3, 30), date(2026, 4, 3)),
                ("Week 12", date(2026, 4, 6), date(2026, 4, 10)),
                ("Week 13", date(2026, 4, 13), date(2026, 4, 17)),
                ("Reading Week", date(2026, 4, 18), date(2026, 4, 24)),
                ("Examination", date(2026, 4, 25), date(2026, 5, 9)),
                # Vacation ends at exam close; Special Terms cover the rest of summer
                ("Vacation", date(2026, 5, 10), date(2026, 5, 10)),
            ],
        },
        {
            "name": "Special Term I",
            "periods": [
                ("Instructional Period", date(2026, 5, 11), date(2026, 6, 20)),
            ],
        },
        {
            "name": "Special Term II",
            "periods": [
                ("Instructional Period", date(2026, 6, 22), date(2026, 8, 1)),
            ],
        },
    ],
}


def get_current_period(
    today: date | None = None,
) -> tuple[str, str, int | None] | None:
    """Return (semester_name, period_label, week_number_or_none) for today.

    Returns None if today falls outside all defined periods (e.g. between AYs).
    Week number is extracted from labels like "Week 10", otherwise None.
    """
    if today is None:
        today = date.today()

    for semester in AY_2025_2026["semesters"]:
        for label, start, end in semester["periods"]:
            if start <= today <= end:
                week_num = None
                if label.startswith("Week "):
                    week_num = int(label.split(" ", 1)[1])
                return semester["name"], label, week_num
    return None


def format_start_message(today: date | None = None) -> str:
    """Return formatted HTML string for the /start home screen."""
    if today is None:
        today = date.today()

    result = get_current_period(today)
    header = f"<b>{AY_2025_2026['ay_name']}</b>"

    if result is None:
        return f"{header}\nNo active semester period"

    semester_name, period_label, week_num = result

    if week_num is not None:
        return f"{header} | {semester_name}\n<b>{period_label}</b> of 13 (Instructional)"
    return f"{header} | {semester_name}\n<b>{period_label}</b>"
