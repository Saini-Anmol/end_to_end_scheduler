"""Soft-reservation table (L16) — create / consume / expire / release.

Reservation is exclusive (one consumer at a time) and invisible to other
FEFO scans while held. Expires automatically at consumer's
latest_acceptable_start. Every state transition is logged (Section 16).
"""
