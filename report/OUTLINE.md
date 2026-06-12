# Báo cáo Đồ án: Phát hiện Data Exfiltration qua HTTP bằng AI đáp ứng thời gian thực với xử lý đa luồng

## Cấu trúc báo cáo chi tiết (theo mẫu giáo viên)

### BÌA BÁO CÁO
- Tên đề tài: Phát hiện Data Exfiltration qua HTTP bằng AI đáp ứng thời gian thực với xử lý đa luồng
- Môn học: [CẦN ĐIỀN: Tên môn học]
- Giảng viên hướng dẫn: Thầy Đàm Minh Linh, MSc
- Thực hiện bởi nhóm sinh viên: [CẦN ĐIỀN: Họ tên, MSSV, Vai trò]
- Học viện Công nghệ Bưu Chính Viễn Thông — CS TP.HCM
- TP.HCM, tháng … / 202…

---

### LỜI MỞ ĐẦU
### LỜI CẢM ƠN
### MỤC LỤC
### DANH MỤC HÌNH ẢNH
### DANH MỤC BẢNG
### TÓM TẮT (1 trang)

---

### CHƯƠNG 1. TỔNG QUAN (~3 trang)
1.1 Tổng quan đề tài
1.2 Mục tiêu nghiên cứu
1.3 Đối tượng, phạm vi và giới hạn nghiên cứu
1.4 Nhiệm vụ đồ án
1.5 Cấu trúc báo cáo

---

### CHƯƠNG 2. CƠ SỞ LÝ THUYẾT VÀ NGHIÊN CỨU LIÊN QUAN (~4 trang)
2.1 Data Exfiltration
2.2 Đặc điểm lưu lượng HTTP/HTTPS
2.3 Hệ thống phát hiện xâm nhập (IDS)
2.4 Phát hiện bất thường (Anomaly Detection)
2.5 Học có giám sát cho phát hiện tấn công mạng
2.6 Isolation Forest
2.7 One-Class SVM
2.8 CNN 1D
2.9 BiLSTM
2.10 Random Forest cho phân loại cửa sổ runtime
2.11 Học trực tuyến / giám sát baseline thích ứng
2.12 Các chỉ số đánh giá
2.13 Bảng so sánh nghiên cứu liên quan (5–10 bài báo)

---

### CHƯƠNG 3. MÔ HÌNH VÀ HỆ THỐNG ĐỀ XUẤT (~15–20 trang)
3.1 Sơ đồ mô hình hệ thống
3.2 Các thành phần của hệ thống
  3.2.1 Luồng bắt gói tin / phiên
  3.2.2 Luồng tổng hợp đặc trưng
  3.2.3 Luồng suy luận + ghi log cảnh báo
  3.2.4 Chế độ replay PCAP offline
  3.2.5 Chế độ bắt trực tiếp (live capture)
  3.2.6 Môi trường lab Docker/VM
  3.2.7 Bộ sinh traffic tổng hợp
3.3 Trích xuất đặc trưng
3.4 Mô hình phát hiện
  3.4.1 Quy tắc burst (burst rule)
  3.4.2 Các mô hình offline-trained
  3.4.3 Giám sát bất thường trực tuyến (online anomaly monitor)
3.5 Cơ chế phát hiện tấn công mới
3.6 Các cải tiến và tối ưu
3.7 Bảng tham số hệ thống

---

### CHƯƠNG 4. THỰC NGHIỆM, ĐÁNH GIÁ VÀ THẢO LUẬN (~15–20 trang)
4.1 Môi trường thực nghiệm
4.2 Kịch bản thực nghiệm
  4.2.1 Traffic bình thường (normal)
  4.2.2 Exfiltration kiểu burst
  4.2.3 Slow-drip bất thường chưa biết
  4.2.4 Bắt trực tiếp (live capture)
  4.2.5 Replay PCAP offline
4.3 Kết quả thực nghiệm
4.4 Đánh giá mô hình offline
4.5 Đánh giá thời gian thực online
4.6 Thảo luận

---

### KẾT LUẬN (~2 trang)
- Đoạn 1: Kết quả đạt được
- Đoạn 2: Hạn chế
- Đoạn 3: Phát triển tương lai

---

### TÀI LIỆU THAM KHẢO

---

## Dự toán số trang sau khi chèn hình/ảnh
| Chương | Trang ước tính |
|--------|----------------|
| Bìa + Lời mở đầu + Mục lục + Tóm tắt | 3–4 |
| Chương 1 | 3 |
| Chương 2 | 4 |
| Chương 3 | 15–20 |
| Chương 4 | 15–20 |
| Kết luận + Tài liệu tham khảo | 3–4 |
| **Tổng** | **43–55 trang** |