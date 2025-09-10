from datetime import datetime, time, timedelta
from django.utils import timezone
from .models import Booking
from main.models import Employee

def daterange(start: datetime, end: datetime, step_min: int = 60):
    cur = start
    delta = timedelta(minutes=step_min)
    while cur < end:
        yield cur
        cur += delta

def free_slots_for_employee(day: datetime, employee: Employee, start_hour=9, end_hour=18, slot_min=60):
    """
    Повертає список вільних слотів (datetime початку) для конкретного майстра на конкретний день.
    Для zoneinfo не використовуємо .localize(), а задаємо tzinfo напряму.
    """
    tz = timezone.get_current_timezone()
    day = timezone.localtime(day, tz)

    day_start = datetime.combine(day.date(), time(hour=start_hour, minute=0), tzinfo=tz)
    day_end   = datetime.combine(day.date(), time(hour=end_hour,   minute=0), tzinfo=tz)

    bookings = Booking.objects.filter(
        master=employee,
        start_at__lt=day_end,
        end_at__gt=day_start
    ).only("start_at", "end_at")

    busy_intervals = [(b.start_at, b.end_at) for b in bookings]

    slots = []
    for s in daterange(day_start, day_end, slot_min):
        e = s + timedelta(minutes=slot_min)
        intersects = any(not (e <= b_start or s >= b_end) for b_start, b_end in busy_intervals)
        if not intersects:
            slots.append(s)
    return slots
