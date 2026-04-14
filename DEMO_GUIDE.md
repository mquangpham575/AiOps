# 🚀 Hướng Dẫn Nhanh: Chạy Demo AiOps

Làm theo các bước sau để thiết lập và chạy bản demo AiOps. Hướng dẫn này dành cho các cộng sự đã có mã nguồn, file `.env` và file chìa khóa SSH (`aiops_key`).

---

## 📋 Điều kiện tiên quyết

1.  **Docker Desktop**: Đảm bảo Docker Desktop đã được cài đặt và đang ở trạng thái **Running** (màu xanh).
2.  **Python 3.10+**: Cần có Python để chạy script demo.
3.  **Chìa khóa SSH**: Đặt file `aiops_key` vào thư mục `.ssh` của người dùng:
    - Đường dẫn: `C:\Users\<Tên_Máy_Tính>\.ssh\aiops_key`
4.  **Biến môi trường**: Đảm bảo file `.env` đã nằm ở thư mục gốc của dự án.
5.  **Cài thư viện Python**:
    ```powershell
    pip install -r loadtest/requirements.txt
    ```

---

## 🕹️ Khởi động hệ thống

### 1. Bật hệ thống (khuyến nghị)

Khuyến nghị dùng script để:

- bật Azure VMs
- mở SSH tunnel cho Docker (`localhost:2375`)
- khởi động Control Plane cục bộ

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\aiops-power.ps1 start
```

Nếu Azure VMs đã bật sẵn và tunnel đã được mở sẵn, bạn có thể chỉ khởi động Control Plane:

```powershell
# Mở PowerShell tại thư mục dự án (DoAn)
docker compose -f ops/infra/docker-compose.control.yml up -d --build
```

### 2. Truy cập các Dashboard theo dõi

Mở trình duyệt và truy cập các địa chỉ sau:

- **Grafana Dashboard**: `http://<AZURE_LOADGEN_IP>:3000` (User/Pass: `admin` / `admin123`)
- **AI Live Action Log**: [http://localhost:8080/logs/ui](http://localhost:8080/logs/ui) (Xem AI phân tích lỗi thời gian thực)

Ghi chú:

- `AZURE_LOADGEN_IP` nằm trong file `.env`.
- Prometheus + AlertManager chạy trên PC (localhost).

---

## 🎮 Thực hiện các kịch bản Demo (Chuẩn đánh giá)

Sử dụng các runner scripts chuẩn hóa (3 lần chạy, tự động tổng hợp số liệu):

### 1. Scenario 1: Baseline vs Load Comparison
So sánh hệ thống khi rỗi (Phase A) và khi có tải (Phase B).
```bash
./scripts/run_scenario1.sh
```

### 2. Scenario 2: CPU Stress Auto-Remediation (TTR)
Đo lường giá trị của AI (MTTR) so với thao tác thủ công.
```bash
./scripts/run_scenario2.sh
```

### 3. Scenario 3: DDoS Rate Limiting Trade-off
Đánh giá hiệu quả chặn tấn công vs. ảnh hưởng người dùng thật qua 3 cấu hình.
```bash
./scripts/run_scenario3.sh
```

---

## 📊 Những gì cần quan sát (Dashboard & Phân tích)

1.  **Grafana Dashboard**: 
    - Truy cập Grafana và Import file [aiops_perf_eval.json](file:///d:/Study/3rd-y/3rdY-Sem2/NT531.Q21-DanhGiaHieuNang/DoAn/ops/monitoring/grafana/dashboards/aiops_perf_eval.json).
    - Theo dõi **Latency p95**, **RPS**, và **Error Rate**.
2.  **Kết quả tổng hợp**: 
    - Xem bảng kết quả cuối cùng trên terminal sau khi chạy mỗi script.
    - Kết quả chi tiết (CSV) được lưu tại thư mục `results/scenarioX/`.
3.  **MTTR Analysis**: 
    - Runner Sc2 sẽ tự động gọi `parse_agent_logs.py` để tính MTTR chi tiết.
    - Log thô từ docker sẽ được lưu tại `results/scenario2/agent_run.log`.

---

## 🛑 Xử lý lỗi thường gặp

- **"SSH Permission Denied"**: Kiểm tra lại đường dẫn file `aiops_key` đã đúng chưa và file có bị đặt mật khẩu (passphrase) hay không.
- **"Cannot connect to Docker"**: Kiểm tra Docker Desktop đã bật chưa.
- **"Metrics are empty"**: Đợi khoảng 30-60 giây sau khi khởi động để Prometheus bắt đầu thu thập dữ liệu từ Azure.
