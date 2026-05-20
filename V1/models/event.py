"""ScheduleEvent dataclass for the event-driven dispatcher (L21).

Event-class priority at tied minute: lot-completion (0) → machine-free (1) →
lot-aged-in (2). Within a class, sort by lot_id ascending.
"""
