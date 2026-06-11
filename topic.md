# Phân tích khả thi demo trên cloud

## Tóm tắt: **Khả thi nhưng không nên** dùng làm primary demo.

Lý do không phải vì cloud chặn — mà vì rủi ro vận hành cao hơn nhiều so với lợi ích.

---

## 1. Cloud provider có chặn không? **KHÔNG.**

Bạn đang gửi `POST /upload` từ `127.0.0.1` đến `127.0.0.1:8080` (loopback). **Không gói nào rời khỏi VM**, không qua firewall provider, không qua VPC.

| Provider | Có inspect loopback intra-VM không? | Có chặn POST localhost không? |
|---|---|---|
| GCP (GCE) | Không — `lo` ở trong network namespace của VM | Không |
| AWS (EC2) | Không — security group chỉ áp dụng cho ENI ngoài | Không |
| Azure (VM) | Không — NSG chỉ filter traffic vào/ra VM | Không |

Các cloud provider **chỉ** detect/block khi:
- Volume cực lớn (DDoS thực sự — triệu req/s)
- Outbound đến target được flag (C2 server, malware IP)
- Vi phạm AUP: pentest target **bên ngoài** mà không khai báo

→ Quy mô của ta (100 req × 50KB nội bộ) là **noise**.

⚠️ Có một điểm lưu ý: AUP của AWS/GCP cấm "security testing" nhắm **vào hạ tầng của họ** hoặc target ngoài. Tự attack `localhost` trong VM mình thuê — **hoàn toàn hợp pháp**.

---

## 2. OS có chặn không? **KHÔNG, nếu là Linux + sudo.**

Hành vi cần permission ở 2 chỗ:

| Thành phần | OS-level requirement | Cloud có hạn chế thêm? |
|---|---|---|
| `Scapy sniff()` trên `lo` | `CAP_NET_RAW` → cần `sudo` | Trên IaaS (GCE/EC2): OK. Trên PaaS (Cloud Run/Lambda): **bị chặn** |
| `Scapy send()` raw socket | `CAP_NET_RAW` | (như trên) |
| HTTP POST từ [attacker.py](cci:7://file:///Users/nguyen_bao/Projects/AIproject/AI_Project/Exfiltration/demo/attacker.py:0:0-0:0) | Không cần root | Không |

Mặc định Ubuntu/Debian:
- Không có iptables rule chặn loopback.
- `ufw` (nếu enable) vẫn allow `lo` interface.
- AppArmor/SELinux không can thiệp Python script chạy bằng `sudo`.

→ **Block là ở tầng dịch vụ cloud (PaaS sandbox), không phải OS.**

---

## 3. Block thực sự là ở đâu? — Theo tier dịch vụ

| Tier | Ví dụ | Có cho `sudo` + raw socket? | Demo được? |
|---|---|---|---|
| **IaaS** (VM full) | GCE `e2-small`, EC2 `t3.micro`, Azure VM | ✅ Có | ✅ Được |
| **CaaS** | GKE node, ECS EC2 mode | ✅ (nếu `privileged: true`) | ⚠️ Phức tạp |
| **PaaS** | Cloud Run, App Engine, Lambda, ECS Fargate | ❌ Không có raw socket | ❌ **Bị chặn** |
| **Serverless** | Cloud Functions | ❌ Không có sniff() | ❌ **Bị chặn** |

→ Nếu demo cloud: **bắt buộc IaaS**.

---

## 4. Vấn đề thật sự khi demo trên cloud (không phải block)

| Vấn đề | Chi tiết | Mức độ |
|---|---|---|
| **Setup time** | Provision VM, scp ~1.5GB code+models, `pip install` (TF + Scapy), test | ~45–60 phút |
| **Display 3 pane** | Phải dùng `tmux`/`screen` qua SSH; layout dễ vỡ trên màn chiếu | Cao |
| **Telegram alert** | Bot vẫn chạy được (outbound HTTPS allowed) — OK | Thấp |
| **Latency rehearsal** | Mỗi lần chạy thử = thêm cost ($), chậm hơn local | Trung bình |
| **Network glitch demo time** | SSH disconnect trước Thầy → phá demo. Local không có rủi ro này | **Rất cao** |
| **Lý do thuyết phục** | Demo cloud không chứng minh thêm điều gì so với demo local | — |

→ Chi phí cao, lợi ích thấp.

---

## 5. Phương án đề xuất

### **Phương án A — Khuyến nghị (rủi ro thấp nhất)**

| Bước | Nội dung |
|---|---|
| 1 | **Demo chính**: Local lo0 (đã chạy thành công, có Telegram alert, không duplicate). |
| 2 | **Backup**: Quay video MP4 màn hình 3 pane đang chạy thật, để sẵn nếu mạng/máy lỗi. |
| 3 | **Slide cuối**: 1 slide giải thích "Hệ thống có thể deploy trên GCE/EC2 — kiến trúc giống hệt, chỉ thay `lo0` bằng `eth0`". Không cần demo thật. |

### **Phương án B — Nếu Thầy nhất quyết muốn cloud**

Chỉ làm trên IaaS, theo trình tự:

1. **Provision GCE `e2-small` Ubuntu 22.04** (free tier 30 ngày, ~0$/giờ trial).
2. SSH với 3 cửa sổ (hoặc 1 SSH + `tmux` 3 pane).
3. `git clone` repo, `pip install -r requirements.txt`.
4. Tạo `.env.local` với Telegram token (đã ignore khỏi git).
5. Chạy:
   - Pane 1: `python demo/upload_server.py`
   - Pane 2: `sudo -E python src/pipeline.py --live --iface lo --debug`
   - Pane 3: `python demo/attacker.py --host 127.0.0.1 --port 8080`
6. **Rehearsal ít nhất 2 lần** trước demo.
7. **Có file PCAP backup** sẵn trên VM: nếu live fail → `python src/pipeline.py --offline --pcap demo_exfil_local.pcap`.

### **Phương án C — Nếu muốn show "production-like"**

- Demo trên **2 VM** thay vì loopback:
  - VM-A (attacker, 1.2.3.4) → POST đến VM-B (server + detector, 5.6.7.8)
  - Detector chạy trên `eth0` thay vì `lo`
  - Chứng minh hệ thống bắt được traffic **thật ra ngoài VPC**
- Cần khai báo VPC firewall rule cho phép port 8080 giữa 2 VM.
- Phức tạp hơn nhưng "thực tế" hơn — phù hợp nếu Thầy đặc biệt yêu cầu.

---

## Kết luận

| Câu hỏi | Trả lời |
|---|---|
| Cloud provider có chặn không? | **Không** (intra-VM loopback) |
| OS có chặn không? | **Không** (chỉ cần `sudo` cho Scapy) |
| Block xảy ra ở đâu? | **Tầng dịch vụ PaaS/Serverless** — không cho raw socket. IaaS thì OK. |
| Có nên demo cloud không? | **Không nên** — rủi ro vận hành cao, không tăng giá trị kỹ thuật. |
| Khuyến nghị | **Phương án A**: demo local + slide nói về khả năng deploy cloud. |

Đề xuất: trong `docs/checkin_thay.docx`, **câu hỏi 3** (về demo format) nên thêm option (d): *"Hay Thầy chỉ cần slide giải thích kiến trúc cloud, không cần demo cloud thực?"* để Thầy chọn rõ.