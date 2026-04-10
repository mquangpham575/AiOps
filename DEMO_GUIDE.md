# 🚀 Hướng Dẫn Nhanh: Chạy Demo AiOps

Làm theo các bước sau để thiết lập và chạy bản demo AiOps. Hướng dẫn này dành cho các cộng sự đã có mã nguồn, file `.env` và file chìa khóa SSH (`aiops_key`).

---

## 📋 Điều kiện tiên quyết

1.  **Docker Desktop**: Đảm bảo Docker Desktop đã được cài đặt và đang ở trạng thái **Running** (màu xanh).
2.  **Python 3.10+**: Cần có Python để chạy script demo.
3.  **Chìa khóa SSH**: Đặt file `aiops_key` vào thư mục `.ssh` của người dùng:
    -   Đường dẫn: `C:\Users\<Tên_Máy_Tính>\.ssh\aiops_key`
4.  **Biến môi trường**: Đảm bảo file `.env` đã nằm ở thư mục gốc của dự án.
5.  **Cài thư viện Python**:
    ```powershell
    pip install requests python-dotenv locust
    ```

---

## 🕹️ Khởi động hệ thống

### 1. Bật Dashboard và Agent cục bộ
Vì máy ảo Azure đã được quản trị viên bật sẵn, bạn chỉ cần khởi động tầng điều hành tại máy của mình:
```powershell
# Mở PowerShell tại thư mục dự án (DoAn)
docker compose -f docker-compose.control.yml up -d --build
```

### 2. Truy cập các Dashboard theo dõi
Mở trình duyệt và truy cập các địa chỉ sau:
-   **Grafana Dashboard**: [http://localhost:3000](http://localhost:3000) (User/Pass: `admin` / `admin123`)
-   **AI Live Action Log**: [http://localhost:8080/logs/ui](http://localhost:8080/logs/ui) (Xem AI phân tích lỗi thời gian thực)

---

## 🎮 Thực hiện các kịch bản Demo

Sử dụng script tự động để giả lập các sự cố hệ thống và xem AI Agent tự động xử lý:

| Lệnh chạy | Ý nghĩa kịch bản |
| :--- | :--- |
| `python scripts/demo_runner.py --scenario all` | **Chạy tất cả kịch bản** (DDoS, CPU, RAM) |
| `python scripts/demo_runner.py --scenario ddos` | Giả lập tấn công DDoS |
| `python scripts/demo_runner.py --scenario cpu` | Giả lập lỗi quá tải CPU |
| `python scripts/demo_runner.py --scenario memory` | Giả lập lỗi cạn kiệt bộ nhớ RAM |

---

## 📈 Những gì cần quan sát (Làm báo cáo)

1.  **Grafana**: Theo dõi các biểu đồ CPU, RAM và Latency. Demo thành công khi các biểu đồ này vọt lên cao (lúc lỗi) và tự động tụt xuống thấp (sau khi AI xử lý).
2.  **AI Reasoning**: Trên giao diện [Action Log UI](http://localhost:8080/logs/ui), đọc cột **Reasoning** để hiểu *tại sao* AI lại chọn hành động đó dựa trên các thông số hệ thống.
3.  **MTTR**: Xem chỉ số thời gian phục hồi (MTTR) trên terminal hoặc file `results.csv` để đưa vào báo cáo đồ án.

---

## 🛑 Xử lý lỗi thường gặp

-   **"SSH Permission Denied"**: Kiểm tra lại đường dẫn file `aiops_key` đã đúng chưa và file có bị đặt mật khẩu (passphrase) hay không.
-   **"Cannot connect to Docker"**: Kiểm tra Docker Desktop đã bật chưa.
-   **"Metrics are empty"**: Đợi khoảng 30-60 giây sau khi khởi động để Prometheus bắt đầu thu thập dữ liệu từ Azure.
