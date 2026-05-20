"""Deterministic min-heap for the event-driven dispatcher (L21).

Ordering key: (event_minute, event_class_priority, lot_id).
Event-class priority: lot-completion = 0, machine-free = 1, lot-aged-in = 2.
Every heap pop is fully deterministic — no insertion-order dependence.
"""
