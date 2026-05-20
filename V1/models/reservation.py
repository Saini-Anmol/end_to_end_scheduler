"""Soft-reservation dataclasses + reservation-log row schema (Section 16).

States: created → (consumed | expired | released). Exclusive, invisible to
other FEFO scans while held (L16).
"""
