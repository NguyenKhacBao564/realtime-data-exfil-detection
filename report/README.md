# Hướng Dẫn Viết Báo Cáo Đồ Án

Tài liệu này mô tả quy trình viết báo cáo theo các phase.

## Cấu trúc thư mục report/

```
report/
├── OUTLINE.md              # Dàn ý chi tiết (đã có)
├── FIGURE_PLAN.md          # Kế hoạch 30 hình ảnh (đã có)
├── TABLE_PLAN.md           # Kế hoạch 15 bảng (đã có)
├── EXPERIMENT_CHECKLIST.md # Checklist thu thập bằng chứng (đã có)
├── TODO_FILL_VALUES.md     # Danh sách giá trị cần điền thủ công (đã có)
├── README.md               # File này
├── images/                 # Thư mục chứa PNG (tự tạo)
│   ├── arch_overview.png
│   ├── docker_lab_arch.png
│   └── ...
└── bao_cao_final.docx      # File DOCX cuối cùng (sau khi build)
```

---

## Phase 1: Planning (Đã hoàn thành)
Các file planning đã được tạo:
- OUTLINE.md — cấu trúc chương, mục, trang ước tính
- FIGURE_PLAN.md — 30 hình, caption, cách chụp
- TABLE_PLAN.md — 15 bảng, cột, trạng thái giá trị
- EXPERIMENT_CHECKLIST.md — checklist từng bước thu thập evidence
- TODO_FILL_VALUES.md — tất cả placeholder cần điền

---

## Phase 2: Chương 1 — Tổng quan (~3 trang)
**Input**: topic.md, CLAUDE.md, README.md, 7–10 bài báo khoa học
**Output**: Viết nội dung Chương 1 vào REPORT_DRAFT.md (chưa tạo) hoặc trực tiếp vào DOCX

**Tasks**:
1. Tìm 7–10 bài báo trên Google Scholar:
   - "HTTP data exfiltration detection"
   - "network anomaly detection CICIDS2017"
   - "real-time network intrusion detection multi-threaded"
   - "online anomaly detection network traffic"
2. Viết 1.1–1.5 theo outline
3. Điền thông tin bìa báo cáo

---

## Phase 3: Chương 2 — Cơ sở lý thuyết & Nghiên cứu liên quan (~4 trang)
**Input**: Các bài báo từ Phase 2, tài liệu lý thuyết ML/IDS
**Output**: Viết Chương 2

**Tasks**:
1. Viết 2.1–2.12: lý thuyết Data Exfiltration, HTTP/HTTPS, IDS, Anomaly Detection, Supervised Learning, Isolation Forest, One-Class SVM, CNN1D, BiLSTM, Random Forest, Online Learning, Evaluation Metrics
2. **Bảng 1.1**: Điền 5–10 bài báo so sánh
3. Trích dẫn đúng chuẩn IEEE

---

## Phase 4: Chương 3 — Mô hình & Hệ thống đề xuất (~15–20 trang)
**Input**: Source code (src/*, lab/*, docs/*), FIGURE_PLAN.md, TABLE_PLAN.md
**Output**: Viết Chương 3 — PHẦN QUAN TRỌNG NHẤT

**Tasks**:
1. **Vẽ sơ đồ** (draw.io / Mermaid) cho Hình 1.1–1.5, 2.1–2.2, 3.23:
   - Kiến trúc tổng quan (pipeline.py)
   - Docker Lab (docker-compose.yml)
   - Pipeline 3 threads (pipeline.py)
   - Online Monitor (online_anomaly_monitor.py)
   - 3 lớp phát hiện (model_inference.py)
   - Vector đặc trưng (runtime_features.py)
   - VM Architecture (VM_DOCKER_LAB_GUIDE.md)
2. **Copy giá trị từ code** cho Bảng 2.1–2.8 (đã có sẵn trong TABLE_PLAN.md)
3. Viết công thức LaTeX:
   - upload_download_ratio, request_rate, z-score, online_score, burst_exfil_score, alert condition
4. Viết mô tả thuật toán Welford (pseudocode từ online_anomaly_monitor.py)
5. Viết 3.1–3.7 chi tiết, có figure/table cross-reference

---

## Phase 5: Chương 4 — Thực nghiệm, Đánh giá, Thảo luận (~15–20 trang)
**Input**: Kết quả chạy thực nghiệm trên VM Ubuntu, EXPERIMENT_CHECKLIST.md
**Output**: Viết Chương 4

**Tasks**:
1. **Chạy thực nghiệm trên VM** theo EXPERIMENT_CHECKLIST.md:
   - make compile, make test
   - make lab-up, lab-normal, lab-exfil, lab-slow-drip
   - live capture, PCAP capture, offline replay
   - Thu thập tất cả screenshot → copy vào report/images/
2. **Điền Bảng 3.1, 3.2, 3.3, 3.4** bằng số liệu thực
3. **Export charts** từ evaluate.py cho Hình 3.16–3.20
4. Viết 4.1–4.6 với evidence dựa trên log/screenshot thực tế
5. **KHÔNG bịa đặt số liệu** — dùng placeholder `[CẦN CHẠY THỰC NGHIỆM]` nếu chưa có

---

## Phase 6: Kết luận & Tài liệu tham khảo (~3 trang)
**Tasks**:
1. Viết 3 đoạn kết luận (đạt được, hạn chế, tương lai)
2. Compile 15–20 citations chuẩn IEEE
3. Đánh dấu `[CẦN KIỂM TRA LẠI THÔNG TIN TRÍCH DẪN]` cho citation chưa verify

---

## Phase 7: Format DOCX (Cuối cùng)
**Option A: Pandoc (khuyên dùng)**
```bash
# Cài đặt pandoc
brew install pandoc  # macOS
# hoặc
sudo apt install pandoc  # Ubuntu

# Convert Markdown → DOCX với template
pandoc REPORT_DRAFT.md \
  -o bao_cao_final.docx \
  --reference-doc=../Bao_cao_mau.docx \
  --toc --toc-depth=3 \
  --resource-path=images
```

**Option B: python-docx (nếu cần tùy chỉnh sâu)**
```bash
pip install python-docx
python build_report.py  # script tự viết
```

**Option C: Thủ công**
- Copy nội dung từ Markdown vào Word
- Áp dụng style từ Bao_cao_mau.docx
- Chèn hình/bảng thủ công

---

## Lưu ý quan trọng
1. **Không copy nội dung từ sample PDF** — chỉ dùng cho style
2. **Không bịa đặt kết quả** — dùng placeholder rõ ràng
3. **Cross-reference**: "như Hình 3.5 cho thấy", "xem Bảng 2.1"
4. **Numbering liên tục**: Hình 1.1, 1.2... 3.1, 3.2... Bảng 1.1, 2.1, 3.1...
5. **Vietnamese academic tone**: "Hệ thống đề xuất", "Thực nghiệm cho thấy", "Đề xuất cải tiến"
6. **An toàn**: Chỉ traffic tổng hợp, không data thật, lab cô lập

---

## Lệnh tiện ích
```bash
# Kiểm tra số lượng hình đã có
ls report/images/*.png | wc -l

# Kiểm tra placeholder còn lại
grep -r "CẦN" report/

# Validate markdown
python -m markdown report/REPORT_DRAFT.md > /dev/null && echo "OK"
```