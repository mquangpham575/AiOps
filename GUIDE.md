# 🤖 HƯỚNG DẪN SỬ DỤNG: AGENTIC AIOPS

> **Đồ án NT531 - Đánh giá hiệu năng hệ thống mạng tự phục hồi (Auto-remediation) sử dụng Agentic AIOps**

---

## 📋 MỤC LỤC

1. [Tổng quan hệ thống](#tổng-quan-hệ-thống)
2. [Kiến trúc](#kiến-trúc)
3. [Khởi động hệ thống](#khởi-động-hệ-thống)
4. [Kịch bản thực nghiệm](#kịch-bản-thực-nghiệm)
5. [Xem kết quả](#xem-kết-quả)
6. [Troubleshooting](#troubleshooting)
7. [Metrics & KPIs](#metrics--kpis)

---

## 🎯 TỔNG QUAN HỆ THỐNG

### Mục tiêu

Xây dựng hệ thống AIOps với AI Agent tự trị có khả năng:

- **Tự động giám sát** hệ thống (CPU, RAM, Traffic)
- **Phát hiện anomaly** qua Prometheus Alert Rules
- **Tự động suy luận** và quyết định hành động khắc phục (sử dụng LLM)
- **Tự động thực thi** remediation actions không cần con người

### Tech Stack

```
Monitoring:   Prometheus + Grafana + AlertManager
AI Agent:     Python Flask + Google Gemini 2.5-flash
Automation:   Docker API, iptables
Load Testing: stress-ng, Locust
```

---

## 🏗️ KIẾN TRÚC

```
┌─────────────────────────────────────────────────────────────┐
│                      MONITORING LAYER                        │
├─────────────────────────────────────────────────────────────┤
│  Prometheus (9090)  ←─ scrapes ─┬─ target-app:5000         │
│       ↓                          ├─ node-exporter:9100      │
│  Alert Rules                     ├─ cAdvisor:8080           │
│       ↓                          └─ aiops-agent:8080        │
│  AlertManager (9093)                                        │
│       ↓                                                      │
│  Webhook → http://agent:8080/webhook                        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                       AI AGENT LAYER                         │
├─────────────────────────────────────────────────────────────┤
│  1. Receive Alert → Parse context                           │
│  2. Build Prompt  → Call Gemini 2.5-flash                  │
│  3. LLM Reasoning → JSON decision {action, params}          │
│  4. Execute Tool  → Auto-remediation                        │
│  5. Log Result    → /logs API                               │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    REMEDIATION TOOLS                         │
├─────────────────────────────────────────────────────────────┤
│  • get_top_processes(container)                             │
│  • kill_process(container, process_name)                    │
│  • restart_service(container)                               │
│  • block_ip(ip)                                             │
│  • apply_rate_limit(interface, rate)                        │
│  • get_prometheus_metrics(query)                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 KHỞI ĐỘNG HỆ THỐNG

### Bước 1: Chuẩn bị môi trường

```bash
# Clone project
cd DoAn/

# Kiểm tra .env file
cat .env
# Nếu chưa có, copy từ .env.example
cp .env.example .env

# Lấy Gemini API Key (FREE) tại:
# https://aistudio.google.com/app/apikey
# Sau đó thêm vào .env:
echo "GEMINI_API_KEY=your_key_here" > .env
```

### Bước 2: Khởi động containers

```bash
# Build và start tất cả services
docker-compose up -d --build

# Kiểm tra trạng thái
docker-compose ps

# Output mong đợi (tất cả UP):
# NAME            STATUS
# target-app      Up
# prometheus      Up
# alertmanager    Up
# grafana         Up
# aiops-agent     Up
# node-exporter   Up
# cadvisor        Up
```

### Bước 3: Verify setup

```bash
# 1. Check Prometheus targets
curl http://localhost:9090/targets
# → Tất cả targets phải UP (không có DOWN)

# 2. Check AI Agent health
curl http://localhost:8080/health
# → Output: {"status":"ok","gemini_configured":true}

# 3. Check Grafana
open http://localhost:3000
# Login: admin / admin123
# → Phải thấy dashboards có sẵn
```

---

## 🧪 KỊCH BẢN THỰC NGHIỆM

### 📊 Kịch bản 1: OVERHEAD BASELINE (Đo chi phí của AI Agent)

**Mục đích:** Đánh giá tài nguyên mà chính AI Agent tiêu thụ.

**Cách chạy:**

```bash
# Hệ thống đã tự động collect metrics
# Chỉ cần vào Grafana xem dashboard
```

**Metrics cần quan sát:**

- **RAM của Agent:** `container_memory_usage_bytes{name="aiops-agent"}`
- **CPU của Agent:** `rate(container_cpu_usage_seconds_total{name="aiops-agent"}[1m])*100`
- **Network Overhead:** `rate(node_network_receive_bytes_total[1m])`

**Xem kết quả:**

```bash
# Query Prometheus
curl 'http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{name="aiops-agent"}'

# Kỳ vọng:
# - Agent RAM: ~60-80 MB (baseline)
# - Agent CPU: <5% (idle state)
```

**Dashboard:** Grafana → "Node Exporter Full" hoặc tạo panel custom.

---

### 🔥 Kịch bản 2: CPU STRESS + AUTO-KILL

**Mục đích:** AI Agent tự động phát hiện và kill process gây quá tải CPU.

#### Phase 1: Tạo CPU stress

```bash
# Chạy stress-ng trong target-app container
docker exec -d target-app stress-ng --cpu 3 --timeout 300s

# Kiểm tra process đang chạy
docker top target-app
# → Phải thấy "stress-ng-cpu [run]"
```

#### Phase 2: Đợi Alert fire

```bash
# Alert rule: HighCPUUsage (CPU > 80% for 30s)
# Đợi 40s để alert được trigger

sleep 40

# Check alert status
curl http://localhost:9090/api/v1/alerts | grep HighCPU
```

#### Phase 3: Xem AI Agent xử lý

```bash
# Xem logs real-time
docker logs aiops-agent -f

# Hoặc xem action history
curl http://localhost:8080/logs | python -m json.tool
```

#### Kết quả mong đợi:

```json
{
  "alert": "HighCPUUsage",
  "reasoning": "CPU đang quá tải 100% do stress. Cần xem các process...",
  "action": "get_top_processes",
  "params": { "container_name": "target-app" },
  "confidence": 0.95,
  "result": "Top processes: stress-ng-cpu 88% CPU",
  "llm_latency_s": 3.5
}
```

#### Manual trigger AI kill stress (nếu không tự động):

```bash
# Gửi webhook giả lập để AI kill stress-ng
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "ManualCPUKill",
        "severity": "critical",
        "scenario": "cpu_stress"
      },
      "annotations": {
        "summary": "Yêu cầu kill stress-ng",
        "description": "CPU 100% từ stress-ng, cần kill ngay"
      }
    }]
  }'
```

**AI sẽ tự động reasoning và gọi `kill_process(container_name="target-app", process_name="stress-ng")`**

#### Đo metrics:

**Trước khi AI can thiệp:**

- CPU Usage: ~90-100%
- Latency: N/A (nếu web app bị ảnh hưởng)

**Sau khi AI kill stress:**

- CPU Usage: drop xuống <20%
- MTTR (Mean Time To Repair): ~5-10 seconds

---

### 🌐 Kịch bản 3: DDoS / HIGH REQUEST RATE

**Mục đích:** AI Agent tự động detect và apply rate limiting khi bị flood traffic.

#### Cài đặt Locust (nếu chưa có):

```bash
pip install locust
```

#### Chạy load test:

```bash
cd loadtest/

# Option 1: Headless mode (tự động)
locust -f locustfile.py --host=http://localhost:5000 \
       --users 500 --spawn-rate 50 --run-time 3m --headless

# Option 2: UI mode (có dashboard)
locust -f locustfile.py --host=http://localhost:5000
# → Mở http://localhost:8089
# → Set: Users=500, Spawn rate=50, Run time=3m
```

#### Alert sẽ fire:

- `HighRequestRate`: rate(flask_http_requests_total) > 100 req/s
- `HighRequestLatency`: avg latency > 1.5s

#### AI Agent sẽ:

1. **Phân tích:** "Latency cao do DDoS, cần apply rate limit"
2. **Action:** `apply_rate_limit(interface="eth0", rate="50/sec")`
3. **Result:** Traffic throttled, latency giảm

#### Đo metrics:

```bash
# Throughput trước khi rate limit
curl 'http://localhost:9090/api/v1/query?query=rate(flask_http_requests_total[1m])'

# Latency
curl 'http://localhost:9090/api/v1/query?query=flask_http_request_duration_seconds'

# So sánh TRƯỚC và SAU khi AI can thiệp
```

---

## 📊 XEM KẾT QUẢ

### 1. AI Agent Logs

```bash
# Real-time logs
docker logs aiops-agent -f

# Action history (JSON API)
curl http://localhost:8080/logs?limit=10 | python -m json.tool
```

### 2. Prometheus Queries

```bash
# CPU usage
curl 'http://localhost:9090/api/v1/query?query=100-avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))*100'

# Memory usage
curl 'http://localhost:9090/api/v1/query?query=node_memory_MemAvailable_bytes'

# Request rate
curl 'http://localhost:9090/api/v1/query?query=rate(flask_http_requests_total[1m])'
```

### 3. Grafana Dashboards

```
URL: http://localhost:3000
Login: admin / admin123

Dashboards:
  - Node Exporter Full: System metrics
  - Custom: Tạo panel cho AI Agent metrics
```

### 4. AlertManager

```
URL: http://localhost:9093
```

Xem:

- Active alerts
- Silences
- Webhook delivery status

---

## 🐛 TROUBLESHOOTING

### Vấn đề 1: Target DOWN trong Prometheus

**Triệu chứng:**

```
Prometheus UI → Status → Targets
→ target-app: DOWN (HTTP 404)
```

**Nguyên nhân:**

- `/metrics` endpoint không tồn tại hoặc trả về wrong Content-Type

**Fix:**

```bash
# Test endpoint
curl http://localhost:5000/metrics
# → Phải trả về text/plain với Prometheus format

# Nếu 404, check target-app logs
docker logs target-app

# Rebuild target-app
docker-compose up -d --build target-app
```

---

### Vấn đề 2: AI Agent không nhận Webhook

**Triệu chứng:**

```bash
curl http://localhost:8080/logs
# → Output: []
```

**Nguyên nhân:**

1. AlertManager chưa gửi webhook (trong group_wait hoặc group_interval)
2. Webhook URL sai
3. Alert không match routing rules

**Debug:**

```bash
# 1. Check AlertManager config
cat alertmanager/alertmanager.yml | grep webhook

# 2. Check AlertManager logs
docker logs alertmanager | grep webhook

# 3. Manual test webhook
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"alerts":[{"status":"firing","labels":{"alertname":"Test","severity":"critical","scenario":"test"},"annotations":{"summary":"Test"}}]}'

# 4. Xem AI Agent response
docker logs aiops-agent --tail 20
```

---

### Vấn đề 3: Gemini API Error

**Triệu chứng:**

```json
{
  "reasoning": "API error: 404 model not found",
  "action": null
}
```

**Nguyên nhân:**

- Model name sai
- API key expired
- Rate limit exceeded

**Fix:**

```bash
# 1. Check API key
docker exec aiops-agent env | grep GEMINI

# 2. Test API key
curl -H "Content-Type: application/json" \
     -d '{"contents":[{"parts":[{"text":"test"}]}]}' \
     "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=YOUR_KEY"

# 3. Change model in agent.py
# Line 55: model = genai.GenerativeModel("gemini-2.5-flash")
```

---

### Vấn đề 4: Alert không fire

**Triệu chứng:**
Stress test đang chạy nhưng không có alert

**Debug:**

```bash
# 1. Check alert rules loaded
curl http://localhost:9090/api/v1/rules | grep HighCPU

# 2. Check rule expression manually
curl 'http://localhost:9090/api/v1/query?query=100-avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))*100'
# → Phải > 80 thì alert mới fire

# 3. Check alert "for" duration
# alert.rules.yml: for: 30s
# → Phải maintain condition trong 30s liên tục
```

---

## 📈 METRICS & KPIs

### Đánh giá hiệu năng AI Agent

| Metric                         | Mô tả                        | Query                        | Target      |
| ------------------------------ | ---------------------------- | ---------------------------- | ----------- |
| **MTTR** (Mean Time To Repair) | Thời gian từ alert → fix     | Manual measure từ logs       | <10 seconds |
| **LLM Latency**                | Thời gian gọi Gemini API     | `llm_latency_s` trong logs   | <5 seconds  |
| **Decision Accuracy**          | % quyết định đúng            | Manual review actions        | >90%        |
| **Agent Overhead**             | RAM/CPU của agent            | `container_memory/cpu_usage` | <100MB, <5% |
| **False Positive Rate**        | % action sai/không cần thiết | Manual review                | <5%         |

### So sánh: Manual vs AI Agent

|                       | Manual (Con người)      | AI Agent                      |
| --------------------- | ----------------------- | ----------------------------- |
| **MTTR**              | 5-15 phút               | <10 giây                      |
| **Availability**      | 8h/day (business hours) | 24/7                          |
| **Cost per Incident** | $10-50 (labor)          | $0.01-0.05 (API)              |
| **Consistency**       | Varies by person        | Consistent                    |
| **Flexibility**       | High (intuition)        | Medium (rule-based reasoning) |

---

## 📝 TẠO BÁO CÁO

### Cấu trúc báo cáo gợi ý:

```
1. LỜI MỞ ĐẦU
   - Bối cảnh và động lực
   - Mục tiêu đề tài

2. CƠ SỞ LÝ THUYẾT
   - AIOps là gì?
   - Agentic AI vs Traditional Automation
   - LLM trong IT Operations
   - Kiến trúc Prometheus/Grafana/AlertManager

3. THIẾT KẾ HỆ THỐNG
   - Topology diagram
   - Tech stack chi tiết
   - Alert rules & thresholds
   - AI Agent architecture
   - Tools & capabilities

4. TRIỂN KHAI
   - Docker compose setup
   - Configuration files
   - Gemini API integration

5. KỊCH BẢN THỰC NGHIỆM & KẾT QUẢ
   ├─ Kịch bản 1: Overhead Baseline
   │  ├─ Mục đích
   │  ├─ Cách thực hiện
   │  ├─ Kết quả (charts từ Grafana)
   │  └─ Phân tích
   ├─ Kịch bản 2: CPU Stress
   │  ├─ Mục đích
   │  ├─ Cách thực hiện
   │  ├─ Kết quả (before/after charts)
   │  └─ MTTR measurement
   └─ Kịch bản 3: DDoS
      ├─ Mục đích
      ├─ Cách thực hiện
      ├─ Kết quả (latency/throughput)
      └─ Effectiveness của rate limiting

6. ĐÁNH GIÁ
   - KPIs summary
   - So sánh Manual vs AI Agent
   - Ưu điểm & Nhược điểm
   - Security concerns
   - Future improvements

7. KẾT LUẬN
   - Tổng kết đạt được
   - Đóng góp của đề tài
   - Hướng phát triển

8. TÀI LIỆU THAM KHẢO
9. PHỤ LỤC
   - Code snippets
   - Config files
   - Screenshots
```

### Export charts từ Grafana:

1. Vào Grafana dashboard
2. Click panel → Share → Export → Save as PNG
3. Thêm vào báo cáo với caption mô tả

### Metrics screenshots quan trọng:

- **Agent Overhead**: RAM/CPU usage graph
- **CPU Stress**: Before/After AI intervention
- **DDoS**: Request rate & latency comparison
- **MTTR Timeline**: Alert fire → AI action → System recovery

---

## 🎥 VIDEO DEMO

### Script gợi ý (5-7 phút):

**Phần 1: Giới thiệu (30s)**

- Tên đề tài, thành viên nhóm
- Mục tiêu: AIOps với AI Agent tự động khắc phục sự cố

**Phần 2: Kiến trúc (1 phút)**

- Diagram: Prometheus → AlertManager → AI Agent
- Tech stack: Gemini 2.5-flash, Docker, Python

**Phần 3: Demo Kịch bản CPU Stress (2 phút)**

1. Chạy `docker exec stress-ng`
2. Grafana: CPU spike trên dashboard
3. Prometheus: Alert "HighCPUUsage" firing
4. AI Agent logs: Nhận webhook → Reasoning → Action
5. Kết quả: stress-ng bị killed, CPU trả về bình thường

**Phần 4: Demo Kịch bản DDoS (2 phút)**

1. Chạy Locust load test
2. Grafana: Request rate & latency spike
3. AI Agent: Detect anomaly → Apply rate limit
4. Kết quả: Latency giảm, throughput stable

**Phần 5: Đánh giá & Kết luận (1 phút)**

- Metrics: MTTR <10s, Overhead <100MB
- So sánh: AI vs Manual
- Ưu điểm: 24/7, fast response, consistent
- Kết luận: AIOps khả thi, cải thiện Ops efficiency

---

## 🔗 THAM KHẢO

### Documentation:

- Prometheus: https://prometheus.io/docs/
- Grafana: https://grafana.com/docs/
- Google Gemini: https://ai.google.dev/docs
- Docker: https://docs.docker.com/

### Papers & Blogs:

- "AIOps: Real-World Challenges and Research Innovations" (Dang et al., 2019)
- "Autonomous Incident Management" (Microsoft, 2023)
- LangChain Agents: https://python.langchain.com/docs/modules/agents/

---

## 📞 LIÊN HỆ & HỖ TRỢ

Nếu gặp vấn đề không thể tự debug:

1. **Check logs:**

   ```bash
   docker-compose logs --tail=100
   ```

2. **Restart hệ thống:**

   ```bash
   docker-compose down
   docker-compose up -d --build
   ```

3. **Verify config:**

   ```bash
   # Prometheus
   docker exec prometheus promtool check config /etc/prometheus/prometheus.yml

   # AlertManager
   docker exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
   ```

---

**Good luck với đồ án! 🚀**

_Đừng quên tạo backup trước khi chạy các test phá hoại (stress, DDoS)._
