# Metrics Report — Exfiltration Detection

> Generated automatically by `src/train/evaluate.py`

## Summary Table

| Model | Type | AUC-ROC | F1 | Precision | Recall | FPR | TP | FP | TN | FN |
|---|---|---|---|---|---|---|---|---|---|---|
| Isolation Forest | anomaly | 0.5277 | 0.0006 | 0.0003 | 0.0383 | 0.1010 | 12 | 42838 | 381460 | 301 |
| One-Class SVM | anomaly | 0.5546 | 0.0013 | 0.0007 | 0.0447 | 0.0493 | 14 | 20920 | 403378 | 299 |

## Anomaly vs Supervised Comparison

### Anomaly-Based Models (train on NORMAL only)
| Pros | Cons |
|---|---|
| No labeled exfil data needed | Lower AUC than supervised |
| Detects zero-day attacks | Higher false positive rate |
| Interpretable anomaly score | Sensitive to noise in training data |

### Supervised Models (train on labeled data)
| Pros | Cons |
|---|---|
| Higher AUC and F1 | Requires labeled exfil data |
| Lower false positive rate | Cannot detect novel attack patterns |
| More stable | Risk of overfitting to training distribution |

## burst_exfil_score Threshold Analysis

| Threshold | Alert Condition | Notes |
|---|---|---|
| 0.5 | Low suspicion | Many false positives expected |
| 0.6 | Medium suspicion | Balance between recall and precision |
| 0.7 | High suspicion (default) | Recommended threshold |
| 0.8 | Very high suspicion | Low false positives, may miss subtle exfil |

## Recommendation
