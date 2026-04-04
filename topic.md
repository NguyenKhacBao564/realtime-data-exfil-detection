Các em Sinh viên thân mến,

Thầy gửi đề tài môn học. Nhóm đọc kỹ yêu cầu, phân công nhiệm vụ rõ ràng từng thành viên nhé.

 Phát hiện Data Exfiltration qua HTTP bằng AI đáp ứng thời gian thực với xử lý đa luồng

Mục tiêu:
Nhận biết hành vi rò rỉ dữ liệu qua HTTP/HTTPS dựa trên thống kê lưu lượng và dấu hiệu bất thường ở tầng ứng dụng.

Dataset đề xuất:
CICIDS2017, UNSW-NB15 (Exfiltration-related flows), hoặc capture lab theo kịch bản, hoặc chọn 1 dataset phù hợp khác.

https://www.unb.ca/cic/datasets/index.html

Nội dung thực hiện:

Phân tích gói tin và session HTTP: method, header length, payload size (nếu không mã hóa), request rate.
Trích xuất đặc trưng theo cửa sổ: upload/download ratio, burst pattern, unusual endpoint frequency.
Pipeline đa luồng:
Thread 1: Packet/session capture
Thread 2: Feature aggregation
Thread 3: Inference + logging
Mô hình: Isolation Forest/One-Class SVM (anomaly) và BiLSTM/CNN 1D.
Đánh giá: AUC, F1, detection time, false positive; phân tích hiệu năng theo tải.
So sánh anomaly-based và supervised trong bối cảnh exfiltration; đề xuất metric “burst-exfil score”.

Hiểu HTTP traffic; triển khai streaming window; báo cáo theo kịch bản tấn công.

Trong quá trình nghiên cứu và thực nghiệm, các em cứ mạnh dạn hỏi trực tiếp, qua email, hoặc trong giờ học.

Trân trọng.

GVMH.
--


ĐỒ ÁN MÔN HỌC


Phát hiện Data Exfiltration qua HTTP
bằng AI đáp ứng thời gian thực
với xử lý đa luồng
Hướng dẫn thực hiện chi tiết
GVHD: Thầy Đàm Minh Linh, MSc
Học viện Công nghệ Bưu Chính Viễn Thông — CS TP.HCM

PHẦN 1: TỔNG QUAN ĐỀ TÀI
1.1. Mục tiêu
Nhận biết hành vi rò rỉ dữ liệu qua HTTP/HTTPS dựa trên thống kê lưu lượng và dấu hiệu bất thường ở tầng ứng dụng.
1.2. Data Exfiltration là gì?
Data Exfiltration (rò rỉ dữ liệu) là việc chuyển dữ liệu nhạy cảm ra khỏi tổ chức một cách trái phép. Kẻ tấn công thường dùng HTTP/HTTPS vì:
- Lưu lượng HTTP/HTTPS được cho phép qua firewall (port 80/443)
- Dễ ẩn giấu trong lưu lượng web bình thường
- Có thể mã hóa payload qua HTTPS
- Upload dữ liệu lên cloud storage, paste sites, hoặc C2 server
1.3. Tại sao cần AI + Đa luồng?
- AI (Machine Learning): phát hiện pattern bất thường mà rule-based không bắt được
- Đa luồng: xử lý real-time, không bỏ sót gói tin khi lưu lượng cao
1.4. Phân công nhiệm vụ gợi ý (nhóm 3-4 người)


Thành viên
Nhiệm vụ chính
Kỹ năng cần
TV1
Thu thập data, tiền xử lý, EDA
Python, Pandas, Wireshark
TV2
Xây dựng pipeline đa luồng
Python Threading/Queue, Scapy
TV3
Huấn luyện mô hình ML/DL
Scikit-learn, TensorFlow/PyTorch
TV4 (hoặc chia)
Đánh giá, báo cáo, demo
Matplotlib, LaTeX/Word




PHẦN 2: CHUẨN BỊ DATASET
2.1. Lựa chọn Dataset
Thầy đề xuất 3 nguồn:
Dataset
Mô tả
Ưu điểm
Link
CICIDS2017
Canadian Institute for Cybersecurity, 5 ngày traffic
Có label rõ ràng, nhiều attack type
unb.ca/cic/datasets
UNSW-NB15
Univ. of New South Wales, 49 features
Feature phong phú, có exfiltration
unsw.edu.au
Tự capture
Tạo kịch bản exfil rồi capture
Sát thực tế nhất, bonus điểm
Tự tạo

⚠ Khuyến nghị: Dùng CICIDS2017 làm chính + tự capture thêm 1 kịch bản nhỏ để so sánh. Đây là cách ghi điểm cao nhất.
2.2. Tải và khám phá CICIDS2017
Tải dataset:
# Tải CICIDS2017 (khoảng 6.4GB tổng)
wget https://www.unb.ca/cic/datasets/ids-2017.html


# Hoặc dùng CICFlowMeter processed CSV files (~1GB)
# Link trực tiếp trong trang dataset
Khám phá dữ liệu (EDA):
import pandas as pd
import matplotlib.pyplot as plt


# Đọc file CSV
df = pd.read_csv('Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv')
print(f'Shape: {df.shape}')
print(f'Columns: {df.columns.tolist()}')
print(f'Labels: {df[" Label"].value_counts()}')


# Lọc HTTP traffic
http_df = df[df[' Destination Port'].isin([80, 443, 8080])]
print(f'HTTP traffic: {len(http_df)} / {len(df)} flows')
2.3. Tự capture theo kịch bản (bonus)
Nếu muốn tự capture, tạo kịch bản sau:
Kịch bản 1: Normal browsing
- Duyệt web bình thường 30 phút, capture bằng tcpdump/Wireshark
Kịch bản 2: Exfiltration simulation
# Mô phỏng exfil: upload file lớn qua HTTP POST
import requests
import os


# Tạo file giả 50MB
data = os.urandom(50 * 1024 * 1024)


# Gửi liên tục (burst pattern)
for i in range(10):
    chunk = data[i*5*1024*1024 : (i+1)*5*1024*1024]
    requests.post('http://your-server/upload',
                  data=chunk,
                  headers={'Content-Type': 'application/octet-stream'})
Capture bằng tcpdump:
# Capture HTTP traffic
sudo tcpdump -i eth0 -w capture.pcap 'port 80 or port 443'


# Convert sang CSV bằng CICFlowMeter
# Hoặc dùng tshark extract features
tshark -r capture.pcap -T fields \
  -e frame.time -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport \
  -e frame.len -e http.request.method \
  -e http.content_length > features.csv

PHẦN 3: TRÍCH XUẤT ĐẶC TRƯNG (FEATURE ENGINEERING)
Đây là phần quan trọng nhất của đồ án. Thầy yêu cầu rõ ràng các nhóm đặc trưng sau:
3.1. Đặc trưng từ gói tin và session HTTP
Feature
Mô tả
Cách tính
http_method
GET/POST/PUT/DELETE
Parse HTTP header
header_length
Kích thước HTTP header
len(headers)
payload_size
Kích thước body
Content-Length hoặc len(body)
request_rate
Số request/giây
count(requests) / time_window
is_encrypted
Có mã hóa không
1 nếu HTTPS (port 443)
content_type
Loại nội dung
Parse Content-Type header
user_agent_entropy
Độ đa dạng UA
Shannon entropy of UA string

3.2. Đặc trưng theo cửa sổ thời gian (Windowed Features)
Thầy yêu cầu rõ: “Trích xuất đặc trưng theo cửa sổ”. Cửa sổ = khoảng thời gian (ví dụ 60 giây).
Feature
Mô tả
Ý nghĩa phát hiện
upload_download_ratio
Tỷ lệ bytes gửi / bytes nhận
Exfil có ratio cao bất thường
burst_pattern
Số burst liên tục trong window
Exfil thường gửi burst
unusual_endpoint_freq
Tần suất truy cập endpoint lạ
Exfil gửi đến endpoint ít phổ biến
bytes_per_second
Throughput trung bình
Exfil có throughput ổn định cao
session_duration
Thời gian session
Exfil session thường dài
inter_request_time_std
Độ lệch chuẩn giữa các request
Exfil có pattern đều, std thấp

Code trích xuất:
import numpy as np
from collections import defaultdict


def extract_window_features(flows, window_sec=60):
    """Trích xuất features theo cửa sổ thời gian"""
    features = {}
    
    # Upload/Download ratio
    total_up = sum(f['bytes_sent'] for f in flows)
    total_down = sum(f['bytes_recv'] for f in flows)
    features['upload_download_ratio'] = (
        total_up / max(total_down, 1)
    )
    
    # Burst pattern detection
    timestamps = sorted(f['timestamp'] for f in flows)
    inter_times = np.diff(timestamps)
    burst_threshold = 0.1  # < 100ms giữa các request
    burst_count = sum(1 for t in inter_times if t < burst_threshold)
    features['burst_count'] = burst_count
    
    # Unusual endpoint frequency
    endpoints = [f['dst_ip'] + ':' + str(f['dst_port'])
                 for f in flows]
    endpoint_freq = defaultdict(int)
    for ep in endpoints:
        endpoint_freq[ep] += 1
    rare_endpoints = sum(1 for v in endpoint_freq.values()
                         if v <= 2)
    features['unusual_endpoint_freq'] = (
        rare_endpoints / max(len(endpoint_freq), 1)
    )
    
    # Inter-request time std (low = automated/exfil)
    features['inter_request_time_std'] = (
        np.std(inter_times) if len(inter_times) > 1 else 0
    )
    
    return features
3.3. Đề xuất metric: burst-exfil score
Thầy yêu cầu đề xuất metric mới. Gợi ý:
def burst_exfil_score(window_features):
    """
    Kết hợp nhiều tín hiệu thành 1 score.
    Score cao = khả năng exfiltration cao.
    """
    score = 0.0
    
    # Upload ratio bất thường (>2x download)
    if window_features['upload_download_ratio'] > 2.0:
        score += 0.3
    
    # Burst pattern (nhiều request liên tục)
    if window_features['burst_count'] > 10:
        score += 0.25
    
    # Endpoint lạ
    if window_features['unusual_endpoint_freq'] > 0.5:
        score += 0.2
    
    # Inter-request time đều (automated)
    if window_features['inter_request_time_std'] < 0.05:
        score += 0.25
    
    return min(score, 1.0)
ℹ️ Đây là điểm nhấn đồ án. Hãy giải thích rõ tại sao chọn các ngưỡng này và so sánh với baseline trong báo cáo.

PHẦN 4: PIPELINE ĐA LUỒNG (MULTI-THREADING)
Đây là yêu cầu kỹ thuật cốt lõi. Thầy yêu cầu 3 thread:
4.1. Kiến trúc tổng quát
Thread
Vai trò
Input
Output
Thread 1
Packet/Session Capture
Network interface / PCAP file
Raw packets -> Queue 1
Thread 2
Feature Aggregation
Queue 1 (raw packets)
Feature vectors -> Queue 2
Thread 3
Inference + Logging
Queue 2 (features)
Prediction + Alert log

4.2. Code Pipeline hoàn chỉnh
import threading
import queue
import time
import logging
from scapy.all import sniff, IP, TCP
from collections import defaultdict
import numpy as np
import joblib


# ===== CẤU HÌNH =====
WINDOW_SIZE = 60  # seconds
CAPTURE_IFACE = 'eth0'  # hoặc None để đọc PCAP
PCAP_FILE = 'test.pcap'  # nếu offline mode
MODEL_PATH = 'model.pkl'


# ===== QUEUES =====
packet_queue = queue.Queue(maxsize=10000)
feature_queue = queue.Queue(maxsize=1000)
stop_event = threading.Event()


# ===== LOGGING =====
logging.basicConfig(
    filename='exfil_detection.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

Thread 1: Packet Capture
def thread_capture():
    """Thread 1: Capture packets và đẩy vào queue"""
    def packet_callback(pkt):
        if stop_event.is_set():
            return
        if pkt.haslayer(IP) and pkt.haslayer(TCP):
            dst_port = pkt[TCP].dport
            if dst_port in [80, 443, 8080, 8443]:
                packet_info = {
                    'timestamp': float(pkt.time),
                    'src_ip': pkt[IP].src,
                    'dst_ip': pkt[IP].dst,
                    'src_port': pkt[TCP].sport,
                    'dst_port': dst_port,
                    'payload_len': len(pkt[TCP].payload),
                    'flags': str(pkt[TCP].flags),
                    'pkt_len': len(pkt),
                }
                try:
                    packet_queue.put(packet_info, timeout=1)
                except queue.Full:
                    logging.warning('Packet queue full!')
    
    print('[Thread 1] Starting capture...')
    if PCAP_FILE:  # Offline mode
        sniff(offline=PCAP_FILE, prn=packet_callback,
              store=False)
    else:  # Live mode
        sniff(iface=CAPTURE_IFACE, prn=packet_callback,
              store=False,
              stop_filter=lambda x: stop_event.is_set())
    print('[Thread 1] Capture stopped.')

Thread 2: Feature Aggregation
def thread_feature_aggregation():
    """Thread 2: Gom packets theo window, trích features"""
    window_buffer = defaultdict(list)  # key: src_ip
    last_flush = time.time()
    
    print('[Thread 2] Starting feature aggregation...')
    while not stop_event.is_set():
        try:
            pkt = packet_queue.get(timeout=1)
        except queue.Empty:
            continue
        
        src_ip = pkt['src_ip']
        window_buffer[src_ip].append(pkt)
        
        # Flush window mỗi WINDOW_SIZE giây
        if time.time() - last_flush >= WINDOW_SIZE:
            for ip, flows in window_buffer.items():
                if len(flows) < 3:
                    continue  # Bỏ qua IP ít traffic
                
                features = extract_all_features(flows)
                features['src_ip'] = ip
                features['window_start'] = last_flush
                
                try:
                    feature_queue.put(features, timeout=1)
                except queue.Full:
                    logging.warning('Feature queue full!')
            
            window_buffer.clear()
            last_flush = time.time()
    
    print('[Thread 2] Feature aggregation stopped.')




def extract_all_features(flows):
    """Trích xuất tất cả features từ 1 window"""
    features = {}
    
    # === Packet-level features ===
    payload_sizes = [f['payload_len'] for f in flows]
    features['mean_payload_size'] = np.mean(payload_sizes)
    features['max_payload_size'] = np.max(payload_sizes)
    features['std_payload_size'] = np.std(payload_sizes)
    features['total_bytes'] = sum(f['pkt_len'] for f in flows)
    features['request_count'] = len(flows)
    
    # === Window-level features ===
    timestamps = sorted(f['timestamp'] for f in flows)
    duration = timestamps[-1] - timestamps[0]
    features['request_rate'] = (
        len(flows) / max(duration, 0.001)
    )
    
    inter_times = np.diff(timestamps)
    features['inter_req_mean'] = (
        np.mean(inter_times) if len(inter_times) > 0 else 0
    )
    features['inter_req_std'] = (
        np.std(inter_times) if len(inter_times) > 1 else 0
    )
    
    # Upload ratio (estimate: outgoing payload)
    total_payload = sum(payload_sizes)
    features['upload_ratio'] = (
        total_payload / max(features['total_bytes'], 1)
    )
    
    # Burst detection
    burst_threshold = 0.1
    bursts = sum(1 for t in inter_times if t < burst_threshold)
    features['burst_count'] = bursts
    features['burst_ratio'] = (
        bursts / max(len(inter_times), 1)
    )
    
    # Unique destinations
    unique_dst = len(set(
        f['dst_ip'] + ':' + str(f['dst_port']) for f in flows
    ))
    features['unique_destinations'] = unique_dst
    
    return features

Thread 3: Inference + Logging
def thread_inference():
    """Thread 3: Chạy model dự đoán và log kết quả"""
    # Load trained model
    model = joblib.load(MODEL_PATH)
    feature_names = model.feature_names_in_  # sklearn
    
    print('[Thread 3] Starting inference...')
    while not stop_event.is_set():
        try:
            features = feature_queue.get(timeout=1)
        except queue.Empty:
            continue
        
        src_ip = features.pop('src_ip')
        window_start = features.pop('window_start')
        
        # Prepare feature vector
        X = np.array([[features[f] for f in feature_names]])
        
        # Predict
        prediction = model.predict(X)[0]
        
        # Tính burst_exfil_score
        exfil_score = burst_exfil_score(features)
        
        if prediction == 1 or exfil_score > 0.7:
            alert_msg = (
                f'ALERT: Potential exfiltration from {src_ip} '
                f'| Score: {exfil_score:.2f} '
                f'| Requests: {features["request_count"]} '
                f'| Burst ratio: {features["burst_ratio"]:.2f}'
            )
            logging.warning(alert_msg)
            print(f'\033[91m{alert_msg}\033[0m')
        else:
            logging.info(
                f'OK: {src_ip} | Score: {exfil_score:.2f}'
            )
    
    print('[Thread 3] Inference stopped.')

Main: Khởi chạy pipeline
def main():
    threads = [
        threading.Thread(target=thread_capture,
                         name='Capture', daemon=True),
        threading.Thread(target=thread_feature_aggregation,
                         name='FeatureAgg', daemon=True),
        threading.Thread(target=thread_inference,
                         name='Inference', daemon=True),
    ]
    
    for t in threads:
        t.start()
        print(f'Started {t.name}')
    
    try:
        while True:
            time.sleep(1)
            # Monitor queue sizes
            print(f'\rPacket Q: {packet_queue.qsize()} | '
                  f'Feature Q: {feature_queue.qsize()}',
                  end='', flush=True)
    except KeyboardInterrupt:
        print('\nStopping...')
        stop_event.set()
        for t in threads:
            t.join(timeout=5)
        print('Pipeline stopped.')


if __name__ == '__main__':
    main()

PHẦN 5: HUẤN LUYỆN MÔ HÌNH
Thầy yêu cầu 2 hướng: Anomaly-based và Supervised. Cần làm cả hai để so sánh.
5.1. Anomaly-based: Isolation Forest + One-Class SVM
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import pandas as pd


# Load processed features
df = pd.read_csv('extracted_features.csv')


# Chỉ dùng NORMAL traffic để train (anomaly detection)
normal_df = df[df['label'] == 0]
feature_cols = ['mean_payload_size', 'max_payload_size',
    'std_payload_size', 'total_bytes', 'request_count',
    'request_rate', 'inter_req_mean', 'inter_req_std',
    'upload_ratio', 'burst_count', 'burst_ratio',
    'unique_destinations']


X_normal = normal_df[feature_cols]
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_normal)


# === Isolation Forest ===
iso_forest = IsolationForest(
    contamination=0.05,  # expect 5% anomaly
    random_state=42,
    n_estimators=200
)
iso_forest.fit(X_scaled)


# === One-Class SVM ===
oc_svm = OneClassSVM(
    kernel='rbf', gamma='scale', nu=0.05
)
oc_svm.fit(X_scaled)
5.2. Supervised: BiLSTM / CNN 1D
Cần label data (normal vs exfiltration). Dùng CICIDS2017 đã có label.
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import (
    LSTM, Bidirectional, Dense, Dropout,
    Conv1D, MaxPooling1D, Flatten, BatchNormalization
)


# Load labeled data
X_train, X_test, y_train, y_test = train_test_split(
    X_all_scaled, labels, test_size=0.2, random_state=42,
    stratify=labels
)


# Reshape cho sequence model: (samples, timesteps, features)
X_train_seq = X_train.reshape(-1, 1, X_train.shape[1])
X_test_seq = X_test.reshape(-1, 1, X_test.shape[1])


# === BiLSTM Model ===
def build_bilstm(input_shape):
    model = Sequential([
        Bidirectional(
            LSTM(64, return_sequences=True),
            input_shape=input_shape
        ),
        Dropout(0.3),
        Bidirectional(LSTM(32)),
        Dropout(0.3),
        Dense(64, activation='relu'),
        BatchNormalization(),
        Dense(1, activation='sigmoid')
    ])
    model.compile(
        optimizer='adam',
        loss='binary_crossentropy',
        metrics=['accuracy', tf.keras.metrics.AUC()]
    )
    return model


bilstm = build_bilstm((1, X_train.shape[1]))
bilstm.fit(X_train_seq, y_train,
           epochs=50, batch_size=64,
           validation_split=0.15)


# === CNN 1D Model ===
def build_cnn1d(input_shape):
    model = Sequential([
        Conv1D(64, 1, activation='relu',
               input_shape=input_shape),
        BatchNormalization(),
        Conv1D(32, 1, activation='relu'),
        Flatten(),
        Dense(64, activation='relu'),
        Dropout(0.3),
        Dense(1, activation='sigmoid')
    ])
    model.compile(
        optimizer='adam',
        loss='binary_crossentropy',
        metrics=['accuracy', tf.keras.metrics.AUC()]
    )
    return model


cnn1d = build_cnn1d((1, X_train.shape[1]))
cnn1d.fit(X_train_seq, y_train,
          epochs=50, batch_size=64,
          validation_split=0.15)
✅ Với BiLSTM: nếu có nhiều window liên tiếp cho 1 IP, reshape thành sequence (timesteps > 1) sẽ hiệu quả hơn. Đây là điểm nâng cao.

PHẦN 6: ĐÁNH GIÁ KẾT QUẢ
6.1. Metrics cần báo cáo
Metric
Ý nghĩa
Quan trọng vì
AUC-ROC
Khả năng phân biệt normal vs exfil
Metric chính cho imbalanced data
F1-Score
Cân bằng precision và recall
Phát hiện đúng + ít false alarm
False Positive Rate
Tỷ lệ báo nhầm
Thực tế: FP cao = spam alert
Detection Time
Thời gian từ exfil đến alert
Real-time requirement
Throughput
Packets/sec xử lý được
Pipeline đa luồng hiệu quả?

6.2. Code đánh giá
from sklearn.metrics import (
    classification_report, roc_auc_score,
    confusion_matrix, f1_score, roc_curve
)
import matplotlib.pyplot as plt


def evaluate_model(model_name, y_true, y_pred, y_prob=None):
    print(f'\n=== {model_name} ===')
    print(classification_report(y_true, y_pred,
          target_names=['Normal', 'Exfiltration']))
    
    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel()
    fpr = fp / (fp + tn)
    print(f'False Positive Rate: {fpr:.4f}')
    
    if y_prob is not None:
        auc = roc_auc_score(y_true, y_prob)
        print(f'AUC-ROC: {auc:.4f}')
        
        # Plot ROC curve
        fpr_curve, tpr_curve, _ = roc_curve(y_true, y_prob)
        plt.plot(fpr_curve, tpr_curve,
                 label=f'{model_name} (AUC={auc:.3f})')
    
    return {'f1': f1_score(y_true, y_pred),
            'fpr': fpr,
            'auc': auc if y_prob is not None else None}
6.3. Phân tích hiệu năng đa luồng
import time


def benchmark_pipeline(pcap_file, durations):
    """So sánh single-thread vs multi-thread"""
    # Single-thread timing
    start = time.time()
    run_single_thread(pcap_file)
    single_time = time.time() - start
    
    # Multi-thread timing
    start = time.time()
    run_multi_thread(pcap_file)
    multi_time = time.time() - start
    
    speedup = single_time / multi_time
    print(f'Single-thread: {single_time:.2f}s')
    print(f'Multi-thread: {multi_time:.2f}s')
    print(f'Speedup: {speedup:.2f}x')

PHẦN 7: SO SÁNH VÀ KẾT LUẬN
7.1. Bảng so sánh anomaly vs supervised
Tiêu chí
Isolation Forest
One-Class SVM
BiLSTM
CNN 1D
Cần label?
Không
Không
Có
Có
AUC (dự kiến)
0.85-0.90
0.80-0.88
0.92-0.96
0.90-0.95
False Positive
Trung bình
Cao
Thấp
Thấp
Tốc độ inference
Nhanh
Chậm
Trung bình
Nhanh
Phát hiện zero-day
Tốt
Tốt
Kém
Kém
Phù hợp real-time
Rất phù hợp
Không phù hợp
Phù hợp
Rất phù hợp

⚠ Số liệu trên là ước tính. Kết quả thực tế phụ thuộc vào dataset và cách trích xuất features.
7.2. Kết luận gợi ý
Trong báo cáo, cần nêu rõ:
- Anomaly-based (Isolation Forest): phù hợp phát hiện zero-day exfil, không cần label, nhưng FP cao hơn
- Supervised (BiLSTM/CNN): chính xác hơn khi có label, nhưng bỏ sót attack mới
- Đề xuất: kết hợp cả hai (ensemble) + burst-exfil score làm feature bổ sung
- Pipeline đa luồng cho phép xử lý real-time, speedup 2-3x so với single-thread

PHẦN 8: CẤU TRÚC PROJECT VÀ TIMELINE
8.1. Cấu trúc thư mục
data-exfil-detection/
├── data/
│   ├── raw/              # PCAP files, CSV gốc
│   ├── processed/        # Features đã trích xuất
│   └── models/           # Trained models (.pkl, .h5)
├── src/
│   ├── capture.py        # Thread 1
│   ├── features.py       # Thread 2 + feature extraction
│   ├── inference.py      # Thread 3
│   ├── pipeline.py       # Main pipeline (khởi chạy)
│   ├── train_anomaly.py  # Huấn luyện IF + OCSVM
│   ├── train_dl.py       # Huấn luyện BiLSTM + CNN
│   └── evaluate.py       # Đánh giá + plot
├── notebooks/
│   ├── 01_EDA.ipynb
│   ├── 02_Feature_Engineering.ipynb
│   └── 03_Model_Comparison.ipynb
├── docs/
│   └── bao_cao.docx
├── requirements.txt
└── README.md
8.2. Timeline gợi ý (6-8 tuần)
Tuần
Công việc
Output
1-2
Tìm hiểu lý thuyết + tải dataset + EDA
Notebook EDA, hiểu data
3
Feature engineering + trích xuất
File extracted_features.csv
4
Xây dựng pipeline đa luồng
pipeline.py chạy được offline
5
Huấn luyện mô hình (4 models)
Model files (.pkl, .h5)
6
Đánh giá + so sánh + vẽ đồ thị
Bảng so sánh, ROC curves
7
Viết báo cáo + chỉnh sửa
bao_cao.docx hoàn chỉnh
8
Chuẩn bị demo + slide thuyết trình
Demo live + slides

8.3. Requirements.txt
# requirements.txt
scapy>=2.5.0
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
tensorflow>=2.14.0
matplotlib>=3.7.0
seaborn>=0.12.0
joblib>=1.3.0
tqdm>=4.65.0
pip install -r requirements.txt
✅ Hãy mạnh dạn hỏi thầy qua email (linhdm@ptit.edu.vn) nếu gặp khó khăn, đặc biệt về phần dataset và cách đánh giá.
