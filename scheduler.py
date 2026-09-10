"""
scheduler.py
Background scheduler jo saved queries ko unke schedule ke hisaab se
apne aap chalata hai — bina kisi manual click ke.

Do tarah ke schedules support karta hai:
  - "interval" -> har N minute me (jaise har 30 minute)
  - "daily"    -> roz ek fixed clock time pe (jaise roz 09:00 AM)
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()
scheduler.start()


def _job_id(query_id: str) -> str:
    return f"saved_query_{query_id}"


def schedule_query(query_id: str, schedule_type: str, run_func,
                    minutes: int = None, run_at_time: str = None):
    """
    Query ko schedule karta hai (pehle se scheduled ho to reschedule).

    schedule_type = "interval" -> minutes zaroori (e.g. 30 -> har 30 min)
    schedule_type = "daily"    -> run_at_time zaroori, format "HH:MM" (24hr), e.g. "09:00"
    """
    unschedule_query(query_id)

    if schedule_type == "daily" and run_at_time:
        try:
            hour, minute = map(int, run_at_time.split(":"))
        except ValueError:
            return  # invalid time format, schedule mat karo
        scheduler.add_job(
            run_func,
            CronTrigger(hour=hour, minute=minute),
            id=_job_id(query_id),
            args=[query_id],
            replace_existing=True,
        )
    elif schedule_type == "interval" and minutes and minutes > 0:
        scheduler.add_job(
            run_func,
            "interval",
            minutes=minutes,
            id=_job_id(query_id),
            args=[query_id],
            replace_existing=True,
        )
    # ya to schedule_type "manual" hai, ya invalid data — kuch schedule nahi hota


def unschedule_query(query_id: str):
    job_id = _job_id(query_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def is_scheduled(query_id: str) -> bool:
    return scheduler.get_job(_job_id(query_id)) is not None

