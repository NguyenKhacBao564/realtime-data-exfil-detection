# So sanh anomaly vs supervised — Exfiltration Detection

> Test set: 424,611 flows, 313 exfil (0.074%)

## Bang metric

| Metric | IsolationForest v2 (anomaly) | CNN1D (supervised) |
|---|---|---|
| AUC-ROC | 0.5463 | 0.9971 |
| F1 | 0.0025 | 0.0567 |
| Precision | 0.0013 | 0.0292 |
| Recall | 0.0415 | 1.0000 |
| FPR | 0.0241 | 0.0245 |
| TP / FP / TN / FN | 13 / 10211 / 414087 / 300 | 313 / 10411 / 413887 / 0 |
| Threshold | -0.179293 | 0.206957 |
| Inference (us/flow) | 6.35 | 8.95 |

## Verdict

Supervised vuot troi (delta AUC = 0.451). Phu hop khi co label tin cay; anomaly chi nen lam lop bo sung phat hien zero-day.

## Bang luan diem

| Khia canh | Anomaly | Supervised |
|---|---|---|
| Yeu cau du lieu | Chi can normal | Can label exfil |
| Phat hien zero-day | Tot | Han che (overfit pattern hoc duoc) |
| Toc do inference | Rat nhanh (decision_function) | Nhanh (CNN1D nho) |
| Do on dinh | Nhay voi noise trong train | On dinh hon |
| Cong dung trong he thong | Lop bo sung canh bao bat thuong | Detector chinh |