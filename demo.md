# Demo Guide — HTTP Data Exfiltration Detection

> Hướng dẫn chuẩn bị và thực hiện demo cho đồ án GVMH
> Thầy Đàm Minh Linh, MSc — Học viện Công nghệ Bưu Chính Viễn Thông

---

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Phương án A — Offline (PCAP)](#2-phương-án-a--offline-pcap)
3. [Phương án B — Live trên máy](#3-phương-án-b--live-trên-máy)
4. [Phương án C — Lab Network](#4-phương-án-c--lab-network)
5. [So sánh ưu nhược điểm](#5-so-sánh-ưu-nhược-điểm)
6. [Script sinh traffic](#6-script-sinh-traffic)
7. [Checklist trước demo](#7-checklist-trước-demo)
8. [Cách trình bày với giảng viên](#8-cách-trình-bày-với-giảng-viên)

---

## 1. Tổng quan

### 1.1 Điều kiện tiên quyết

Kiểm tra trên máy trước khi đi demo:

```bash
# Di chuyển vào thư mục project
cd /Users/nguyen_bao/Documents/AI_Project/Exfiltration

# 1. Kiểm tra Python environment
python -c "import scapy, pandas, numpy, sklearn, tensorflow; print('OK')"

# 2. Kiểm tra dataset tồn tại
ls data/raw/Friday-WorkingHours.pcap

# 3. Kiểm tra models đã train
ls models/

# 4. Kiểm tra pipeline chạy được
python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap
```

### 1.2 Các phương án demo

| Phương án | Tên | Yêu cầu | Thời gian chuẩn bị |
|---|---|---|---|
| A | Offline (PCAP) | Chỉ cần dataset có sẵn | ~15 phút |
| B | Live trên máy | Máy lab + HTTP server + traffic generator | ~30 phút |
| C | Lab Network | PTIT Lab + Docker/2 máy | ~60 phút |

### 1.3 Mục tiêu demo chung

```
□ Thấy được 3 threads hoạt động đồng thời
□ Thấy pipeline bắt packet → trích features → inference
□ Thấy alert màu đỏ khi phát hiện exfiltration
□ Giải thích được burst_exfil_score
□ Giải thích được kết quả AUC của từng model
□ Trả lời được câu hỏi về anomaly vs supervised
```

---

## 2. Phương án A — Offline (PCAP)

### 2.1 Mô tả

Đọc file PCAP có sẵn từ dataset CICIDS2017, chạy pipeline để phát hiện exfiltration.

```
┌──────────────────────────────────────────────────┐
│  Friday-WorkingHours.pcap                        │
│  (dataset CICIDS2017 đã có sẵn)                  │
│                                                  │
│           ↓ (Scapy đọc file)                    │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Thread 1: Packet Capture                   │  │
│  │  Thread 2: Feature Aggregation (60s window)  │  │
│  │  Thread 3: Inference (CNN1D/BiLSTM)         │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│           ↓ (Console output)                     │
│                                                  │
│  [Thread 1] Packet Q: 1234                       │
│  [Thread 2] Feature Q: 12                        │
│  🔴 ALERT: Exfiltration from 192.168.1.12        │
│     Score: 0.85 | Burst: 47 | Ratio: 3.2x       │
└──────────────────────────────────────────────────┘
```

### 2.2 Cách thực hiện

```bash
# Bước 1: Di chuyển vào project
cd /Users/nguyen_bao/Documents/AI_Project/Exfiltration

# Bước 2: Chạy pipeline (offline mode)
python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap

# Bước 3: Quan sát console
# - Thấy 3 threads khởi động
# - Thấy queue sizes tăng/giảm
# - Thấy alerts xuất hiện (màu đỏ)
# - Thấy log file được ghi

# Bước 4: Xem log file
cat exfil_detection.log
```

### 2.3 Thứ cần chuẩn bị

```
□ Máy tính (laptop) có Python + dependencies
□ Dataset Friday-WorkingHours.pcap (169MB, có sẵn)
□ Project Exfiltration (clone/pull từ GitHub)
□ Powerpoint/Keynote để trình bày (slide demo)
□ Điện thoại/tablet để ghi hình demo (backup)
```

### 2.4 Kết quả đạt được

```
✅ Thấy 3 threads hoạt động đồng thời
✅ Thấy packet capture từ PCAP
✅ Thấy feature aggregation theo 60s window
✅ Thấy model inference chạy (CNN1D AUC=0.9423)
✅ Thấy burst_exfil_score được tính
✅ Thấy alerts xuất hiện trong console
✅ Xem được log file chi tiết
✅ Trả lời được: "Pipeline đa luồng hoạt động thế nào?"
✅ Trả lời được: "burst_exfil_score là gì?"
```

---

## 3. Phương án B — Live trên máy

### 3.1 Mô tả

Sinh HTTP traffic giả lập trên máy local (localhost/loopback), bắt real-time bằng pipeline.

```
┌──────────────────────────────────────────────────────────┐
│  MÁY CỦA BẠN (PTIT Lab)                                │
│                                                          │
│  Terminal 1: HTTP Server                                 │
│  $ python -m http.server 8000                           │
│  → Nhận requests trên localhost:8000                    │
│                                                          │
│  Terminal 2: Exfiltration Pipeline                       │
│  $ python src/pipeline.py --live --iface lo             │
│  → Bắt traffic trên loopback interface                  │
│                                                          │
│  Terminal 3: Traffic Generator                           │
│  $ python scripts/generate_traffic.py                   │
│  → Sinh: Normal browsing (thưa)                         │
│  → Sinh: Exfil burst (POST 1MB × 50 lần, 50ms/request)  │
│                                                          │
│  Kết quả:                                               │
│  🔴 ALERT: Exfiltration from 127.0.0.1                   │
│     Score: 0.78 | Burst: 48 | Ratio: 8.4x               │
└──────────────────────────────────────────────────────────┘
```

### 3.2 Cách thực hiện

**Bước 1: Mở Terminal 1 — HTTP Server**

```bash
cd /Users/nguyen_bao/Documents/AI_Project/Exfiltration
python -m http.server 8000 --directory /tmp
# Output: Serving HTTP on 0.0.0.0 port 8000 ...
```

**Bước 2: Mở Terminal 2 — Chạy pipeline**

```bash
cd /Users/nguyen_bao/Documents/AI_Project/Exfiltration
python src/pipeline.py --live --iface lo
# Output:
# [Thread 1] Starting capture on lo...
# [Thread 2] Starting feature aggregation...
# [Thread 3] Starting inference...
# Packet Q: 0 | Feature Q: 0
```

**Bước 3: Mở Terminal 3 — Sinh traffic**

```bash
cd /Users/nguyen_bao/Documents/AI_Project/Exfiltration
python scripts/generate_traffic.py
# Output:
# [Generator] Normal traffic: started
# [Generator] Normal traffic: done
# [Generator] Exfil burst: started
# [Generator] Exfil burst: done
```

**Quan sát trên Terminal 2:**
- 0-10s: Normal traffic → không có alert (hoặc score thấp)
- 10-20s: Exfil burst → 🔴 **ALERT xuất hiện** (score cao)

### 3.3 Thứ cần chuẩn bị

```
□ Máy tính (laptop) có Python + dependencies
□ Quyền chạy Python scripts (không cần sudo)
□ Script sinh traffic: scripts/generate_traffic.py
□ Project Exfiltration (clone/pull từ GitHub)
□ Powerpoint/Keynote để trình bày (slide demo)
□ Điện thoại/tablet để ghi hình demo (backup)
□ Dây LAN (phòng khi WiFi lab bị captive portal)
□ Sao lưu dataset trên ổ cứng/USB (phòng mạng chậm)
```

### 3.4 Kết quả đạt được

```
✅ Tất cả kết quả của Phương án A
✅ Thấy traffic được sinh và bắt real-time
✅ Thấy pipeline phản ứng ngay khi exfil burst bắt đầu
✅ Thấy detection time: gần như tức thì (sau 1-2 windows)
✅ Thấy burst pattern được phát hiện (inter-request < 0.1s)
✅ Giải thích được: "Tại sao burst = exfil signal?"
✅ Giải thích được: "Live capture khác offline thế nào?"
```

---

## 4. Phương án C — Lab Network

### 4.1 Mô tả

Sử dụng môi trường mạng PTIT Lab thực sự, bắt traffic giữa các máy trong LAN.

```
┌──────────────────────────────────────────────────────────┐
│  PTIT LAB NETWORK                                        │
│                                                          │
│  ┌────────────┐              ┌────────────────────────┐ │
│  │ Máy 1      │◄─── LAN ───►│ Máy 2 (PTIT Lab PC)    │ │
│  │ (của bạn)  │              │                        │ │
│  │            │              │  Terminal 1: HTTP server│ │
│  │ Terminal 2:│◄─────────────│  python -m http.server│ │
│  │ Pipeline   │              │                        │ │
│  │            │◄─────────────│  Terminal 3: Generator │ │
│  │ Terminal 3:│              │  scripts/generate...    │ │
│  │ Generator  │              │                        │ │
│  └────────────┘              └────────────────────────┘ │
│                                                          │
│  Interface: eth0/wlan0 thay vì lo                       │
└──────────────────────────────────────────────────────────┘
```

### 4.2 Cách thực hiện

**Bước 1: Kiểm tra network interface**

```bash
ifconfig
# eth0: Ethernet (cắm dây LAN)
# wlan0: WiFi (nếu dùng WiFi lab)
# lo: loopback (KHÔNG dùng trong phương án này)
```

**Bước 2: Xác định IP máy**

```bash
# Nếu dùng Ethernet
ifconfig eth0 | grep "inet "
# Output: inet 10.30.x.x netmask 255.255.255.0

# Nếu dùng WiFi
ifconfig wlan0 | grep "inet "
```

**Bước 3: Mở Terminal 1 trên Máy 2 — HTTP Server**

```bash
# Lắp máy 2 vào mạng PTIT Lab
# Mở terminal, chạy:
python -m http.server 8000 --bind 0.0.0.0
```

**Bước 4: Mở Terminal 2 trên Máy 1 — Pipeline**

```bash
cd /Users/nguyen_bao/Documents/AI_Project/Exfiltration
python src/pipeline.py --live --iface eth0
# Hoặc --iface wlan0 nếu dùng WiFi
```

**Bước 5: Mở Terminal 3 trên Máy 1 — Traffic Generator**

```bash
# Cập nhật URL trong script
# Sửa: URL_NORMAL = "http://10.30.x.x:8000/upload"

python scripts/generate_traffic.py
```

### 4.3 Thứ cần chuẩn bị

```
□ 2 máy tính trong cùng mạng PTIT Lab
□ Dây mạng LAN (2 cái: 1 cắm máy 1, 1 cắm máy 2 vào switch lab)
□ Máy tính có quyền chạy Python + sudo (để bắt packet)
□ Script sinh traffic đã sửa IP
□ Phương án backup: mang dataset trên USB nếu mạng lab chậm
□ Slide demo (Powerpoint/Keynote)
□ Ghi hình trước bằng điện thoại (backup nếu demo lúc đầu lỗi)
□ XIN PHÉP giảng viên trước khi cắm dây mạng vào lab
□ Thông báo cho bộ phận IT lab nếu cần
```

### 4.4 Kết quả đạt được

```
✅ Tất cả kết quả của Phương án B
✅ Thấy traffic qua mạng LAN thật (không phải loopback)
✅ Thấy pipeline bắt được traffic từ nhiều nguồn IP
✅ Thấy detection trên traffic thật từ PTIT Lab
✅ Khẳng định: "Hệ thống hoạt động được trong môi trường thật"
```

---

## 5. So sánh ưu nhược điểm

### 5.1 Bảng so sánh

| Tiêu chí | A — Offline (PCAP) | B — Live trên máy | C — Lab Network |
|---|---|---|---|
| **Chi phí** | Miễn phí | Miễn phí | Miễn phí (cần 2 máy) |
| **Thời gian chuẩn bị** | 15 phút | 30 phút | 60 phút |
| **Độ phức tạp** | Thấp | Trung bình | Cao |
| **Cần xin phép Thầy?** | Không | Có thể | **Có** |
| **Cần 2 máy?** | Không | Không | **Có** |
| **Real-time thật?** | Không | Có | Có |
| **Qua mạng LAN thật?** | Không | Không | **Có** |
| **Rủi ro thất bại** | Thấp | Trung bình | Cao |
| **Thuyết phục với Thầy** | Trung bình | Cao | **Rất cao** |
| **Tái hiện được?** | Luôn được | Phụ thuộc máy | Khó tái hiện |
| **Backup khi lỗi** | Luôn chạy được | Có thể quay về A | Quay về A hoặc B |

### 5.2 Phân tích chi tiết

#### Phương án A — Offline (PCAP)

**Ưu điểm:**
- Không cần chuẩn bị gì ngoài dataset có sẵn
- Luôn chạy được, không phụ thuộc network
- Có thể replay nhiều lần
- Kiểm soát được kết quả (biết trước có attack)
- Thầy thấy rõ pipeline logic
- Ít rủi ro thất bại nhất

**Nhược điểm:**
- Không thật sự "real-time" (đọc file)
- Không qua mạng (chỉ đọc PCAP bằng Scapy)
- Thầy có thể hỏi: *"Đây có phải real-time không?"*
- Không cho thấy khả năng xử lý traffic thật

**→ Phù hợp khi:** Chỉ cần minh chứng pipeline hoạt động, không cần thuyết phục quá mức.

#### Phương án B — Live trên máy

**Ưu điểm:**
- Real-time thật sự (bắt packet đang sinh ra)
- Thấy pipeline phản ứng tức thì khi exfil bắt đầu
- Không cần 2 máy, không cần cắm mạng
- Dễ backup: lỗi → quay về Phương án A
- Thầy thấy rõ detection time thật
- Có thể thay đổi traffic pattern ngay lúc demo

**Nhược điểm:**
- Traffic chỉ qua loopback (localhost), không qua mạng LAN
- Cần HTTP server + traffic generator (thêm bước chuẩn bị)
- Một số lab PTIT có captive portal WiFi → khó bắt packet trên wlan0
- Rủi ro: HTTP server không start được (port 8000 bị占用)

**→ Phương án khuyên dùng.** Đủ thuyết phục, đủ đơn giản.

#### Phương án C — Lab Network

**Ưu điểm:**
- Thuyết phục nhất: traffic qua mạng LAN thật
- Thấy pipeline bắt được traffic từ nhiều IP thật
- Cho thấy hệ thống deployable trong môi trường thật
- Điểm cộng cao nhất trong mắt Thầy

**Nhược điểm:**
- Phức tạp nhất: cần 2 máy + mạng LAN + xin phép
- Rủi ro cao: switch lab có thể không cho cắm, WiFi có captive portal
- Không tái hiện được nếu demo lần đầu lỗi
- Cần chuẩn bị lâu, dễ bị trục trặc kỹ thuật
- Nếu Thầy hỏi: *"Có cần cloud/VM/EVE-NG không?"* → **Không**, nhưng cần giải thích rõ

**→ Chỉ dùng khi:** Đã test thành công Phương án B trước, và Thầy đồng ý cho dùng lab.

### 5.3 Lời khuyên

```
┌─────────────────────────────────────────────────────────────┐
│  THỨ TỰ NÊN THEO:                                           │
│                                                             │
│  1. Test Phương án A (Offline) ngay — 15 phút              │
│     → Xác nhận pipeline chạy được trên máy                  │
│                                                             │
│  2. Test Phương án B (Live) trước khi hỏi Thầy            │
│     → Biết chắc nó hoạt động                                │
│     → Khi hỏi Thầy: đã có demo video/ảnh sẵn              │
│                                                             │
│  3. Nếu Thầy đồng ý → Test Phương án C trước giờ demo    │
│     → KHÔNG test lần đầu ngay trước mặt Thầy              │
│                                                             │
│  LUÔN CÓ BACKUP:                                           │
│  Demo A sẵn sàng trong USB → Lỗi B hoặc C → Quay về A    │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Script sinh traffic

File: `scripts/generate_traffic.py`

```python
#!/usr/bin/env python3
"""
Traffic Generator cho Demo Phương án B và C
Sinh HTTP POST requests để giả lập normal browsing và exfiltration burst
"""

import requests
import time
import random
import threading
import sys
import os

# ============== CẤU HÌNH ==============
# Phương án B (localhost):
URL_NORMAL = "http://127.0.0.1:8000/upload"
URL_EXFIL  = "http://127.0.0.1:8000/data"

# Phương án C (Lab Network) — sửa IP theo máy 2 trong lab:
# URL_NORMAL = "http://10.30.x.x:8000/upload"
# URL_EXFIL  = "http://10.30.x.x:8000/data"

# Tham số traffic
NORMAL_COUNT = 20       # Số request normal
NORMAL_DELAY = (1, 3)   # Delay ngẫu nhiên 1-3 giây
NORMAL_SIZE  = (100, 2000)  # Bytes ngẫu nhiên

EXFIL_COUNT  = 50       # Số request exfil burst
EXFIL_DELAY  = 0.05     # 50ms giữa các request (burst)
EXFIL_SIZE   = 1024 * 1024  # 1MB mỗi request

WARMUP_TIME  = 5        # Đợi trước khi bắt đầu exfil
# =========================================


def generate_normal_traffic():
    """Tạo traffic bình thường: request thưa, bytes nhỏ, random"""
    print(f"[Generator] Normal traffic: started ({NORMAL_COUNT} requests)")
    print(f"[Generator] Pattern: {NORMAL_DELAY[0]}-{NORMAL_DELAY[1]}s delay, "
          f"{NORMAL_SIZE[0]}-{NORMAL_SIZE[1]} bytes")

    for i in range(NORMAL_COUNT):
        size = random.randint(*NORMAL_SIZE)
        data = os.urandom(size)
        try:
            r = requests.post(URL_NORMAL, data=data, timeout=2)
            print(f"[Generator] Normal [{i+1}/{NORMAL_COUNT}] "
                  f"{size} bytes → {r.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"[Generator] Normal [{i+1}/{NORMAL_COUNT}] "
                  f"→ Connection refused (server chưa chạy?)")
        except Exception as e:
            print(f"[Generator] Normal [{i+1}/{NORMAL_COUNT}] → Error: {e}")

        # Random delay
        delay = random.uniform(*NORMAL_DELAY)
        time.sleep(delay)

    print("[Generator] Normal traffic: done")


def generate_exfil_burst():
    """Tạo traffic exfil: POST burst, nhiều MB, tốc độ nhanh"""
    print(f"\n[Generator] Exfil burst: started ({EXFIL_COUNT} requests, "
          f"{EXFIL_DELAY*1000:.0f}ms delay, {EXFIL_SIZE/1024/1024:.1f}MB each)")
    print(f"[Generator] Expected: {EXFIL_COUNT * EXFIL_SIZE / 1024 / 1024:.0f}MB total upload")
    print(f"[Generator] Expected pattern: burst ratio cao, "
          f"inter-request < 0.1s → burst_exfil_score > 0.7")

    for i in range(EXFIL_COUNT):
        data = os.urandom(EXFIL_SIZE)
        try:
            r = requests.post(URL_EXFIL, data=data, timeout=5)
            print(f"[Generator] Exfil  [{i+1}/{EXFIL_COUNT}] "
                  f"{EXFIL_SIZE/1024/1024:.1f}MB → {r.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"[Generator] Exfil  [{i+1}/{EXFIL_COUNT}] "
                  f"→ Connection refused")
        except Exception as e:
            print(f"[Generator] Exfil  [{i+1}/{EXFIL_COUNT}] → Error: {e}")

        time.sleep(EXFIL_DELAY)

    print("[Generator] Exfil burst: done")


def main():
    print("=" * 60)
    print("  EXFILTRATION TRAFFIC GENERATOR")
    print("  Normal + Exfil Burst Simulation")
    print("=" * 60)

    # Check server availability
    print(f"\n[Setup] Checking server: {URL_NORMAL}")
    try:
        r = requests.get(URL_NORMAL.rsplit('/', 1)[0], timeout=2)
        print(f"[Setup] Server OK: {r.status_code}")
    except Exception as e:
        print(f"[Setup] ⚠ Server check failed: {e}")
        print(f"[Setup] ⚠ Make sure HTTP server is running on Terminal 1:")
        print(f"[Setup]    python -m http.server 8000 --directory /tmp")
        print(f"[Setup] ⚠ Continuing anyway (server may be starting)...\n")

    # Run normal traffic first
    print()
    normal_thread = threading.Thread(target=generate_normal_traffic)
    normal_thread.start()

    # Wait for normal to finish, then start exfil
    normal_thread.join()

    # Short pause before exfil
    print(f"\n[Generator] Waiting {WARMUP_TIME}s before exfil burst...\n")
    time.sleep(WARMUP_TIME)

    # Run exfil burst
    exfil_thread = threading.Thread(target=generate_exfil_burst)
    exfil_thread.start()
    exfil_thread.join()

    print("\n" + "=" * 60)
    print("  ALL TRAFFIC GENERATED")
    print("  Check pipeline console for alerts!")
    print("=" * 60)


if __name__ == '__main__':
    main()
```

---

## 7. Checklist trước demo

### 7.1 1 ngày trước demo

```
□ Push code lên GitHub (backup)
□ Test Phương án A — Offline — xác nhận chạy được
□ Test Phương án B — Live — xác nhận chạy được
□ Tạo Powerpoint/Keynote slide demo
□ Ghi hình demo Phương án A và B bằng điện thoại
□ In/Export bao_cao.docx ra PDF (backup)
□ Copy dataset vào USB (backup)
□ Sạc laptop đầy
□ Điện thoại sạc đầy (ghi hình backup)
```

### 7.2 Sáng ngày demo

```
□ Test nhanh Phương án A (5 phút) — confirm chạy được
□ Kiểm tra GitHub: code đã push
□ Kiểm tra USB: dataset, slides, báo cáo PDF
□ Kiểm tra WiFi PTIT: có kết nối được không?
□ Mang theo: laptop, sạc laptop, USB, điện thoại
□ Nếu dùng Phương án C: xin phép Thầy trước giờ demo
```

### 7.3 Trong lúc demo

```
□ Luôn bắt đầu bằng Phương án A (backup sẵn có)
□ Nếu Phương án B/C hoạt động → chuyển sang
□ Nếu Phương án B/C lỗi → quay về Phương án A
□ Nói trước với Thầy: "Em sẽ demo offline trước, sau đó live"
□ Chuẩn bị trả lời câu hỏi Thầy
□ Bật microphone ghi âm (backup nếu Thầy hỏi)
```

---

## 8. Cách trình bày với giảng viên

### 8.1 Kịch bản demo (3-5 phút)

```
PHÚT 1: Giới thiệu nhanh
─────────────────────────
"Em xin phép demo pipeline đa luồng phát hiện exfiltration.
Pipeline gồm 3 threads: Capture → Features → Inference.
Em sẽ demo offline trước, sau đó live trên máy."

PHÚT 2: Demo Offline (Phương án A)
───────────────────────────────────
→ Chạy: python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap
→ Chỉ vào console: "Đây là 3 threads đang chạy"
→ Chỉ vào queue sizes: "Packet Q đang tăng khi đọc PCAP"
→ Chỉ vào alert đỏ: "Đây là burst_exfil_score > 0.7 → phát hiện exfil"

PHÚT 3: Giải thích metrics
───────────────────────────
→ Mở evaluation_results.json: "CNN1D đạt AUC=0.9423, BiLSTM AUC=0.9012"
→ "Anomaly models (Isolation Forest, OCSVM) kém hơn supervised"
→ "burst_exfil_score là metric bổ sung, không thay thế model"

PHÚT 4 (nếu có thời gian): Demo Live (Phương án B)
────────────────────────────────────────────────────
→ Terminal 1: HTTP server
→ Terminal 2: Pipeline --live --iface lo
→ Terminal 3: python scripts/generate_traffic.py
→ "Thầy thấy pipeline phát hiện real-time khi exfil burst bắt đầu"
```

### 8.2 Câu hỏi Thầy có thể hỏi + cách trả lời

| Câu hỏi | Cách trả lời |
|---|---|
| *"Đây có phải real-time không?"* | "Offline mode đọc PCAP để kiểm tra logic. Live mode bắt packet thật. Thầy cho phép em demo live?" |
| *"Tại sao anomaly models kém hơn supervised?"* | "Vì Bot traffic trong CICIDS2017 giống Normal trong 67-feature space gốc. Anomaly models phù hợp cho zero-day, supervised tốt khi có label." |
| *"burst_exfil_score là gì?"* | "Là metric em đề xuất, kết hợp 4 signals: upload ratio cao + burst count > 10 + unusual endpoint + inter-request time std thấp. Score > 0.7 = exfil." |
| *"Tại sao chọn ngưỡng 0.7?"* | "Dựa trên phân tích data-driven trong 02_Feature_Engineering.ipynb. Ngưỡng này tối ưu F1, giảm false positives." |
| *"Pipeline xử lý được bao nhiêu packets/sec?"* | "Trong benchmark, pipeline đạt ~X packets/sec với speedup 2.5x so với single-thread." |
| *"Có cần cloud/VM/EVE-NG không?"* | "Không ạ. Chỉ cần máy tính + Python. Docker chỉ dùng để sinh traffic nhẹ, không bắt buộc." |

### 8.3 Email xin phép demo (mẫu)

> **Subject:** Xin phép demo đồ án — Data Exfiltration Detection
>
> Thưa Thầy Đàm Minh Linh,
>
> Em xin phép demo đồ án "Phát hiện Data Exfiltration qua HTTP bằng AI đáp ứng thời gian thực với xử lý đa luồng".
>
> **Demo plan:**
> 1. **Offline (PCAP):** Chạy pipeline trên dataset CICIDS2017 có sẵn — 3 threads + alerts 🔴
> 2. **Live (tuỳ điều kiện):** Sinh HTTP traffic giả lập trên máy lab, bắt real-time — cần xin phép Thầy
>
> **Yêu cầu nếu demo live:**
> - Chạy `python -m http.server 8000` trên máy lab (port 8000)
> - Chạy traffic generator bằng Python scripts (không cần Docker)
> - Không cần cắm thêm mạng, không ảnh hưởng mạng PTIT Lab
>
> Em đã test offline thành công. Nếu được Thầy cho phép, em sẽ demo thêm phần live.
>
> Trân trọng,
> [Họ tên — MSSV]

---

## Phụ lục: Câu lệnh nhanh

```bash
# --- Demo Offline ---
cd /Users/nguyen_bao/Documents/AI_Project/Exfiltration
python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap

# --- Demo Live ---
# Terminal 1:
python -m http.server 8000 --directory /tmp

# Terminal 2:
python src/pipeline.py --live --iface lo

# Terminal 3:
python scripts/generate_traffic.py

# --- Xem log ---
cat exfil_detection.log

# --- Xem metrics ---
cat data/processed/evaluation_results.json
```
