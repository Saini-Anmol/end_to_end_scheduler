"""LSF dispatch tiebreak chain (L15).

Exhaustive 4-step ordering at a tied event minute:
(1) Least Slack First — smallest latest_acceptable_start - current_sim_time;
(2) earliest curing-block deadline served;
(3) longest downstream path remaining (sum of MIN_aging + proc minutes);
(4) item_code ascending alphabetical.
"""
