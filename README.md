# Agentic AIOps — NT531 Đồ Án

> Đánh giá hiệu năng hệ thống mạng tự phục hồi sử dụng Agentic AIOps  
> Stack: Docker Compose · Gemini API (gemma-3-1b-it) · Prometheus · Grafana · Python Agent

---

## Yêu cầu hệ thống

- Docker Desktop (Windows) — tải tại https://docs.docker.com/desktop/install/windows-install/
- Python 3.11+ (cho Locust chạy ngoài Docker)
- Tối thiểu **8GB RAM**, khuyến nghị 16GB
- Gemini API Key — lấy miễn phí tại https://aistudio.google.com/app/apikey

---

## Cấu trúc project

```
aiops-project/
├── docker-compose.yml          ← Định nghĩa 7 service
├── .env.example                ← Template API key
├── prometheus/
│   ├── prometheus.yml          ← Scrape config
│   └── alert.rules.yml         ← 3 kịch bản alert rules
├── alertmanager/
│   └── alertmanager.yml        ← Webhook → Agent
├── grafana/
│   └── dashboards/             ← Auto-provision dashboard
├── target-app/
│   ├── app.py                  ← Flask app (target sự cố)
│   ├── Dockerfile
│   └── requirements.txt
├── agent/
│   ├── agent.py                ← Webhook receiver + Gemini + Action
│   ├── tools.py                ← SSH, iptables, Docker tools
│   ├── Dockerfile
│   └── requirements.txt
└── loadtest/
    ├── locustfile.py           ← Kịch bản 2: DDoS
    ├── stress.sh               ← Kịch bản 1 & 3
    └── requirements.txt
```

---

## Bước 1: Chuẩn bị API Key

```bash
# Sao chép file env mẫu
cp .env.example .env

# Mở .env và điền API key của bạn
# GEMINI_API_KEY=AIzaSy...
```

---

## Bước 2: Khởi động toàn bộ hệ thống

```bash
# Trong thư mục aiops-project/
docker compose up -d --build

# Kiểm tra tất cả service đang chạy
docker compose ps
```

Sau khoảng 1-2 phút, truy cập:

| Service | URL | Tài khoản |
|---|---|---|
| Target App | http://localhost:5000 | — |
| Prometheus | http://localhost:9090 | — |
| AlertManager | http://localhost:9093 | — |
| Grafana | http://localhost:3000 | admin / admin123 |
| Agent API | http://localhost:8080/health | — |
| Agent Logs | http://localhost:8080/logs | — |

---

## Bước 3: Cấu hình Grafana

1. Đăng nhập Grafana → http://localhost:3000 (admin/admin123)
2. Vào **Connections → Data Sources → Add data source**
3. Chọn **Prometheus**, URL: `http://prometheus:9090` → Save & Test
4. Import dashboard: **Dashboards → Import** → dán ID `1860` (Node Exporter Full)

**Các panel cần tạo thủ công cho báo cáo:**

```promql
-- Throughput (req/s)
rate(flask_http_requests_total{job="target-app"}[1m])

-- Latency trung bình
rate(flask_http_request_duration_seconds_sum[1m])
/ rate(flask_http_request_duration_seconds_count[1m])

-- CPU usage (%)
100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)

-- Agent RAM
container_memory_usage_bytes{name="aiops-agent"}
```

---

## Bước 4: Chạy 3 kịch bản thực nghiệm

### Kịch bản 1 — Đo Overhead AIOps

```bash
# Linux/Mac:
chmod +x loadtest/stress.sh
./loadtest/stress.sh overhead

# Windows (PowerShell):
docker compose stop agent
# Đợi 2 phút, ghi metrics Grafana
docker compose start agent
# Đợi 2 phút, ghi lại và so sánh
```

**Metrics cần ghi:** CPU delta, RAM delta, network traffic delta (agent vs không agent)

---

### Kịch bản 2 — DDoS + Auto-remediation

```bash
# Cài Locust (1 lần)
pip install -r loadtest/requirements.txt

# Chạy với UI (mở http://localhost:8089)
locust -f loadtest/locustfile.py --host=http://localhost:5000

# Hoặc headless tự động (500 users, 3 phút)
locust -f loadtest/locustfile.py \
  --host=http://localhost:5000 \
  --users 500 --spawn-rate 50 \
  --run-time 3m --headless
```

Theo dõi đồng thời:
- Grafana: Latency và Throughput
- Agent logs: http://localhost:8080/logs

**Metrics cần ghi:** Thời điểm alert, thời điểm Agent hành động, Latency trước/trong/sau

---

### Kịch bản 3 — CPU Stress + Auto-kill

```bash
# Linux/Mac:
./loadtest/stress.sh cpu

# Windows (PowerShell):
docker exec target-app stress-ng --cpu 4 --timeout 90s
```

Theo dõi:
```bash
# Xem Agent đang làm gì (real-time)
watch -n 2 "curl -s http://localhost:8080/logs | python3 -m json.tool | tail -40"
```

**Metrics cần ghi:** Biểu đồ CPU recovery, Remediation time, Thời gian downtime

---

## Bước 5: Thu thập số liệu cho báo cáo

### Lấy Action Log của Agent
```bash
curl http://localhost:8080/logs | python3 -m json.tool > agent_actions.json
```

### Tính Remediation Time
```
Remediation Time = timestamp(action) - timestamp(alert_starts_at)
```
Tìm trong `agent_actions.json`:
- `timestamp` → lúc Agent thực hiện action
- `startsAt` trong alert payload → lúc sự cố bắt đầu

### Export biểu đồ từ Grafana
1. Mở panel → biểu tượng Share → Export → PNG
2. Đặt time range: 10 phút trước và sau khi chạy kịch bản

---

## Bước 6: Test thủ công Agent (không cần AlertManager)

```bash
# Gửi webhook giả lập DDoS
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "HighRequestLatency",
        "severity": "critical",
        "scenario": "ddos"
      },
      "annotations": {
        "summary": "Latency cao bat thuong",
        "description": "Latency trung binh: 3.2s"
      },
      "startsAt": "2024-01-01T00:00:00Z"
    }]
  }'
```

```bash
# Gửi webhook giả lập CPU stress
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "HighCPUUsage",
        "severity": "critical",
        "scenario": "cpu_stress"
      },
      "annotations": {
        "summary": "CPU qua tai",
        "description": "CPU usage: 95%"
      },
      "startsAt": "2024-01-01T00:00:00Z"
    }]
  }'
```

---

## Dừng hệ thống

```bash
docker compose down          # Giữ data
docker compose down -v       # Xóa cả data (volumes)
```

---

## Ghi chú quan trọng

- **Gemini free tier**: 30 requests/phút. Agent đã có throttle 3s/call — đủ cho thực nghiệm.
- **Dry-run mode**: Nếu không điền API key, Agent vẫn chạy nhưng sẽ simulate action mà không gọi Gemini.
- **Windows**: Lệnh `iptables` trong tool `block_ip` cần container chạy với `--cap-add=NET_ADMIN`. Trên Windows Docker Desktop, một số lệnh network có thể bị giới hạn.
- **Grafana password**: Đổi password admin sau lần đầu đăng nhập nếu cần.
