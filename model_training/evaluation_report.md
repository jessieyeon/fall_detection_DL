# Fall-risk model evaluation (held-out test set)

Test set: 33 videos never seen during training (26 with a fall, 7 ADL-only).

## Operating point sweep

|   threshold |   persistence |   n_fall_videos |   n_caught |   catch_rate |   n_adl_videos |   false_events_per_adl_video |   mean_lead_time_s |   median_lead_time_s |   min_lead_time_s |
|------------:|--------------:|----------------:|-----------:|-------------:|---------------:|-----------------------------:|-------------------:|---------------------:|------------------:|
|         0.5 |             3 |              26 |         26 |     1        |              7 |                      8.85714 |            4.67371 |              2.61081 |          0.08     |
|         0.6 |             3 |              26 |         24 |     0.923077 |              7 |                      4.57143 |            3.51097 |              1.5     |          0.08     |
|         0.7 |             3 |              26 |         20 |     0.769231 |              7 |                      2.71429 |            1.45383 |              0.83666 |          0.04     |
|         0.5 |             5 |              26 |         23 |     0.884615 |              7 |                      4.85714 |            4.2805  |              2.08    |          0.041666 |

## Frame-level report (saved operating point: threshold=0.5, persistence=3)

```
              precision    recall  f1-score   support

      normal       0.96      0.87      0.91      7038
   fall_risk       0.30      0.63      0.41       633

    accuracy                           0.85      7671
   macro avg       0.63      0.75      0.66      7671
weighted avg       0.91      0.85      0.87      7671
```

## What this shows

- At threshold=0.5, persistence=3.0: caught 26/26 falls in the test set (100%), with 8.86 false alarms per ADL-only video.
- Median warning lead time for caught falls: 2.61 seconds before the person actually started falling (min observed: 0.08s).
- This is on Le2i test videos never used in training (split by video, not by frame, so there is no data leakage between train and test).
- Caveat: small test set (7 ADL videos), so the false-alarm rate has wide uncertainty. Treat this as a proof-of-concept result, not a certified accuracy figure.
