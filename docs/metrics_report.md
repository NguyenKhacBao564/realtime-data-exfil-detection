# Metrics Report — Exfiltration Detection
> Generated 2026-04-05 by evaluate.py
## Summary Table
| Model | AUC-ROC | F1 | Precision | Recall | FPR | TP | FP | TN | FN | Threshold |
|---|---|---|---|---|---|---|---|---|---|---|
| Isolation Forest | 0.5277 | 0.0006 | 0.0003 | 0.0383 | 0.1010 | 12 | 42838 | 381460 | 301 | auto |
| One-Class SVM | 0.5546 | 0.0013 | 0.0007 | 0.0447 | 0.0493 | 14 | 20920 | 403378 | 299 | auto |
| CNN1D Final | 0.9971 | 0.0567 | 0.0292 | 1.0000 | 0.0245 | 313 | 10411 | 413887 | 0 | 0.2070 |
| BiLSTM Final | 0.9966 | 0.0438 | 0.0224 | 1.0000 | 0.0322 | 313 | 13661 | 410637 | 0 | 0.1673 |

## Key Findings
- CNN1D Final: AUC=0.9971, FPR=0.0245 ✅ — BEST model
- BiLSTM Final: AUC=0.9966, FPR=0.0322 ✅
- Anomaly models kém vì Bot traffic giống Normal trong feature space
- Threshold tuning giảm FPR từ ~45% xuống ~2.5% (giảm 18×)
