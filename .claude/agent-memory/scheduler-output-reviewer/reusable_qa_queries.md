---
name: reusable-qa-queries
description: Pandas one-liners for V1 scheduler output QA — reach for these first every review
metadata:
  type: reference
---

# Reusable QA Query Snippets

## 1. Reservation log invariant
```python
import pandas as pd
df = pd.read_csv('output/.../reservation_log.csv')
created = df[df['event_type']=='created'][['consumer_lot_id','producer_lot_id']]
closed = df[df['event_type'].isin(['consumed','expired','released'])][['consumer_lot_id','producer_lot_id']]
m = created.merge(closed, on=['consumer_lot_id','producer_lot_id'], how='left', indicator=True)
print('created:', len(created), 'closed:', len(closed), 'unmatched:', (m['_merge']=='left_only').sum())
```

## 2. Machine double-booking
```python
df_s = df.sort_values(['machine_id','start_min'])
df_s['prev_end'] = df_s.groupby('machine_id')['end_min'].shift(1)
bad = df_s[df_s['start_min'] < df_s['prev_end']]
print('overlapping_lot_pairs:', len(bad))
```

## 3. Gap vs max_aging_min (CRITICAL — catches silent violations)
```python
btc = pd.read_csv('output/.../building_to_curing.csv')
print('gap > max_aging violations:', (btc['gap_min'] > btc['max_aging_min']).sum())
print('gap stats:', btc['gap_min'].describe())
```

## 4. L1 building lot count vs curing blocks
```python
build = df[df['op_seq']==70]
print('Building lots:', len(build), '| Expected: 42 (one per curing block)')
print('Serves_blocks sample:', build['serves_blocks'].head(3).tolist())
```

## 5. Building duration floor check
```python
build = df[df['op_seq']==70]
print('Building durations:', build['duration_min'].tolist())
print('Expected floor (64 tyres, 60 SEC each): >=68 min')
# Any duration < 68 min for a 64-tyre lot is a time_calculation bug
```

## 6. Capstrip leak check (L12)
```python
for item in ['CAP 66','CAP 66-MOTHERROLL','CAP 66 - CAPSTRIP','B616M','MB614']:
    n = len(df[df['item_code'].str.contains(item, na=False, regex=False)])
    if n > 0: print(f'CAPSTRIP LEAK: {item} = {n} rows')
```

## 7. L23 machine_id leading zeros
```python
mixer_ids = [m for m in df['machine_id'].unique() if str(m).startswith('0')]
print('Mixer IDs:', sorted(mixer_ids))  # Expected: ['0201','0202','0203','0204','0205','0206']
```
