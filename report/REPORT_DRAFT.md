# Báo cáo Đồ án: Phát hiện Data Exfiltration qua HTTP bằng AI đáp ứng thời gian thực với xử lý đa luồng

---

## CHƯƠNG 1. TỔNG QUAN

### 1.1 Tổng quan đề tài

Rò rỉ dữ liệu (Data Exfiltration) là một trong những mối đe dọa an ninh mạng nghiêm trọng nhất hiện nay, trong đó kẻ tấn công trích xuất trái phép dữ liệu nhạy cảm từ hệ thống mục tiêu ra bên ngoài. Theo báo cáo của Verizon Data Breach Investigations Report 2023, hơn 20% các vụ vi phạm dữ liệu liên quan đến exfiltration qua các kênh ứng dụng web, trong đó HTTP/HTTPS chiếm tỷ trọng lớn nhất do tính phổ biến và khó chặn hoàn toàn của giao thức này [CITATION-01]. Khác với các tấn công truyền thống như DoS hay mã độc, exfiltration thường diễn ra lặng lẽ, kéo dài trong thời gian dài, và sử dụng các kênh hợp pháp để lẩn tránh hệ thống giám sát.

Giao thức HTTP/HTTPS trở thành vector tấn công ưa chuộng vì nhiều lý do: (1) traffic HTTP/HTTPS được phép đi qua hầu hết firewall và proxy doanh nghiệp; (2) HTTPS mã hóa nội dung payload, khiến các giải pháp DLP (Data Loss Prevention) dựa trên kiểm tra nội dung trở nên vô hiệu; (3) các ứng dụng web hợp pháp tạo ra lượng traffic lớn, che lấp cho hành vi exfiltration; (4) attacker có thể dễ dàng mã hóa, nén, hoặc phân mảnh dữ liệu trước khi gửi qua HTTP POST/PUT requests.

Các phương pháp phát hiện truyền thống chủ yếu dựa trên signature-based detection (kiểm tra mẫu đã biết) hoặc DLP dựa trên từ khóa/regex trong payload. Tuy nhiên, những phương pháp này gặp hạn chế lớn trước exfiltration qua HTTPS do không thể giải mã payload, và trước các kỹ thuật obfuscation (mã hóa, encoding, chunking) mà attacker sử dụng. Do đó, xu hướng hiện nay chuyển sang **phân tích hành vi lưu lượng (traffic behavior analysis)** — sử dụng các đặc trưng thống kê như tỷ lệ upload/download, tần suất request, kích thước payload, pattern burst, và timing inter-request để phát hiện bất thường mà không cần xem nội dung payload [CITATION-02], [CITATION-03].

Yêu cầu **đáp ứng thời gian thực (real-time)** đặt ra thách thức thêm: hệ thống phải xử lý hàng chục ngàn gói tin mỗi giây, trích xuất đặc trưng theo cửa sổ thời gian (time window), chạy suy luận mô hình AI, và đưa ra cảnh báo trong vòng vài giây kể từ khi exfiltration bắt đầu. Kiến trúc **đa luồng (multi-threaded)** trở thành giải pháp tất yếu: tách biệt bắt gói tin, tổng hợp đặc trưng, và suy luận thành các thread độc lập liên lạc qua queue, tận dụng đa nhân CPU để đạt throughput cao và latency thấp [CITATION-04].

Trong đồ án này, chúng tôi xây dựng một hệ thống phát hiện Data Exfiltration qua HTTP/HTTPS đáp ứng các yêu cầu sau:
1. **Pipeline đa luồng real-time**: 3 thread (Packet Capture → Feature Aggregation → Inference) với queue-based IPC.
2. **Chế độ kép**: Live capture (bắt trực tiếp từ interface mạng) và Offline replay (phát lại file PCAP).
3. **Kết hợp đa lớp phát hiện**: Quy tắc burst (rule-based), Mô hình offline-trained (Isolation Forest, One-Class SVM, BiLSTM, CNN1D), và Giám sát bất thường trực tuyến (Online Anomaly Monitor) cho các pattern chưa biết.
4. **Môi trường lab an toàn, tái tạo được**: Docker Compose lab với synthetic traffic generator (normal, exfil burst, slow-drip), HTTP server log metadata only.
5. **Đánh giá định lượng**: AUC-ROC, F1, FPR, Detection Time, Throughput trên dataset CICIDS2017 và lab traffic.

Hình [Hình 1.1: Sơ đồ kiến trúc tổng quan hệ thống phát hiện Data Exfiltration] minh họa kiến trúc tổng quan của hệ thống đề xuất.

### 1.2 Mục tiêu nghiên cứu

Đồ án hướng đến các mục tiêu cụ thể sau:

**Mục tiêu chính:** Xây dựng hệ thống phát hiện Data Exfiltration qua HTTP/HTTPS hoạt động real-time với pipeline đa luồng, kết hợp phát hiện dựa trên quy tắc, học máy offline, và giám sát thích ứng online.

**Các mục tiêu cụ thể:**
1. Thiết kế và cài đặt pipeline đa luồng 3 giai đoạn: bắt gói tin/phiên (Scapy), tổng hợp đặc trưng cửa sổ 60 giây theo source IP, suy luận mô hình AI + ghi log cảnh báo.
2. Triển khai 4 mô hình offline-trained: Isolation Forest và One-Class SVM (anomaly-based, train trên traffic bình thường), BiLSTM và CNN1D (supervised, train trên dữ liệu có nhãn CICIDS2017).
3. Phát triển Online Anomaly Monitor dựa trên thuật toán Welford — duy trì baseline thống kê per-source-IP tại runtime, tính z-score deviation để phát hiện pattern exfiltration mới/không biết (zero-day, slow-drip) mà mô hình offline chưa thấy.
4. Xây dựng Docker/VM lab tái tạo được: exfil-server (HTTP metadata logger), victim-client (3-mode traffic generator: normal, exfil, slow-drip), monitor-detector (containerized pipeline), hỗ trợ tcpdump capture và PCAP replay.
5. Đánh giá hệ thống trên dataset CICIDS2017 (train/val/test split 70/10/20 hoặc 80/20) và lab traffic: AUC-ROC > 0.90 cho supervised models, FPR < 5%, Detection Time < 5s cho burst exfil, throughput > 10,000 packets/sec.
6. So sánh hiệu quả 3 lớp phát hiện: BURST_RULE (nhanh, interpretable), OFFLINE_MODEL (học pattern lịch sử), ONLINE_UNKNOWN_ANOMALY (thích ứng pattern mới).

Bảng [Bảng 1.1: So sánh nghiên cứu liên quan] sẽ được trình bày ở Chương 2 để định vị đóng góp của đồ án so với các công trình hiện có.

### 1.3 Đối tượng, phạm vi và giới hạn nghiên cứu

**Đối tượng nghiên cứu:** Lưu lượng mạng HTTP/HTTPS trong môi trường doanh nghiệp/giáo dục, tập trung vào hành vi exfiltration qua HTTP POST/PUT requests.

**Phạm vi:**
- Phân tích metadata và đặc trưng thống kê của traffic (không giải mã payload HTTPS).
- Phát hiện exfiltration dựa trên hành vi: upload ratio cao, burst pattern, unusual ports, timing regularity.
- Pipeline xử lý real-time với window size mặc định 60 giây, có thể cấu hình.
- Lab environment: Docker Compose trên Ubuntu VM, traffic tổng hợp (synthetic) an toàn cho demo học thuật.

**Giới hạn:**
1. **Không kiểm tra payload HTTPS**: Do mã hóa TLS, hệ thống chỉ dùng metadata (header, size, timing, flags). Đây là trade-off an ninh vs khả năng triển khai — giải pháp enterprise thường kết hợp TLS inspection (MITM proxy) nhưng không trong phạm vi đồ án.
2. **Dataset CICIDS2017 không có nhãn exfiltration rõ ràng**: Sử dụng Bot traffic (Friday-Morning) và Infiltration (Thursday-Afternoon) làm proxy cho exfil behavior. Cần justify rõ trong báo cáo.
3. **Lab traffic là synthetic**: Mặc dù mô phỏng thực tế (burst size, timing, payload), nhưng không thay thế hoàn toàn traffic production. Kết quả lab dùng để minh họa pipeline, không phải benchmark production.
4. **MacBook M-series limitation**: macOS không hỗ trợ promiscuous mode cho Docker network capture. Demo chính thức yêu cầu Ubuntu ARM64 VM (UTM/VMware) — xem Hình [Hình 3.21: Kiến trúc MacBook M → Ubuntu VM → Docker Lab].
5. **Model version compatibility**: Mô hình Keras/TensorFlow có thể gặp lỗi load do version mismatch (Keras 3.x vs 2.x). Code đã có fallback compile=False nhưng cần test kỹ trước demo.

### 1.4 Nhiệm vụ đồ án

Theo yêu cầu của Giảng viên hướng dẫn (Thầy Đàm Minh Linh, MSc), đồ án thực hiện các nhiệm vụ sau:

| Nhiệm vụ | Mô tả | Trạng thái |
|----------|-------|------------|
| NV1 | Tìm hiểu dataset CICIDS2017, EDA, gán nhãn exfiltration proxy | ✅ Hoàn thành (notebooks/01_EDA.ipynb) |
| NV2 | Feature engineering: trích xuất 17 runtime features, burst_exfil_score | ✅ Hoàn thành (src/features/) |
| NV3 | Xây dựng pipeline đa luồng 3 thread + queue monitoring | ✅ Hoàn thành (src/pipeline.py) |
| NV4 | Huấn luyện 4 mô hình offline: IF, OCSVM, BiLSTM, CNN1D | ✅ Hoàn thành (src/train/) |
| NV5 | Threshold tuning: giảm FPR từ ~45% → ~2.5% | ✅ Hoàn thành (src/train/train_final.py) |
| NV6 | Phát triển Online Anomaly Monitor (Welford, per-IP baseline) | ✅ Hoàn thành (src/inference/online_anomaly_monitor.py) |
| NV7 | Tích hợp online monitor vào inference pipeline | ✅ Hoàn thành (src/inference/model_inference.py) |
| NV8 | Xây dựng Docker/VM lab (3 services, synthetic traffic) | ✅ Hoàn thành (lab/, scripts/) |
| NV9 | Unit + Integration tests (37 tests passed) | ✅ Hoàn thành (tests/) |
| NV10 | Viết báo cáo, slide, demo evidence | 🔄 Đang thực hiện |

### 1.5 Cấu trúc báo cáo

Báo cáo bao gồm 4 chương chính và phần kết luận:

- **Chương 1** (Trang hiện tại): Tổng quan đề tài, mục tiêu, phạm vi, nhiệm vụ.
- **Chương 2**: Cơ sở lý thuyết (Data Exfiltration, HTTP/HTTPS, IDS, Anomaly Detection, ML models, Online learning) và Nghiên cứu liên quan (Bảng so sánh 5–10 bài báo).
- **Chương 3**: Mô hình và hệ thống đề xuất — Kiến trúc (Hình 1.1), Các thành phần (3.2), Trích xuất đặc trưng (Bảng 2.1, Hình 2.1), Mô hình phát hiện (Burst rule 3.4.1, Offline models 3.4.2, Online monitor 3.4.3), Cơ chế phát hiện mới (3.5), Cải tiến (3.6), Tham số hệ thống (Bảng 2.4).
- **Chương 4**: Thực nghiệm và đánh giá — Môi trường (4.1, Hình 3.21), Kịch bản (4.2: normal, exfil, slow-drip, live, offline), Kết quả (4.3, Hình 3.1–3.22), Đánh giá offline (4.4, Bảng 3.1, Hình 3.16–3.18), Đánh giá online (4.5, Bảng 3.2–3.4, Hình 3.19–3.20), Thảo luận (4.6).
- **Kết luận**: 3 đoạn (Kết quả đạt được, Hạn chế, Phát triển tương lai).
- **Tài liệu tham khảo**: 15–20 citations chuẩn IEEE.

---

*Lưu ý: Các placeholder [CITATION-XX], [Hình X.Y], [Bảng X.Y] sẽ được điền khi hoàn thiện các chương sau và thu thập bằng chứng thực nghiệm.*