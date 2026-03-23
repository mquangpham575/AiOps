# 📋 KẾ HOẠCH DỰ ÁN NT531 - AGENTIC AIOPS

> **Đề tài:** Đánh giá hiệu năng hệ thống mạng tự phục hồi (Auto-remediation) sử dụng Agentic AIOps
> **Môn học:** NT531 - Đánh giá hiệu năng hệ thống mạng máy tính
> **Mục tiêu:** Áp dụng AI Agents tự trị vào IT Operations để tự động theo dõi, phát hiện và khắc phục sự cố mạng/hệ thống

---

## 🎯 MỤC TIÊU CỐT LÕI CỦA MÔN HỌC

Dựa trên các báo cáo đồ án từ các nhóm trước (MQTT, PRTG, ELK Stack, NSQ, SNMP, QUIC, Prometheus/Grafana, Kafka, v.v.), môn học này tập trung vào việc **triển khai thực tế** một giao thức/công cụ/hệ thống mạng và tiến hành **đo lường, đánh giá hiệu năng** dưới các điều kiện tải khác nhau.

### Mục tiêu đồ án:

1. **Nghiên cứu cơ sở lý thuyết**: Hiểu rõ kiến trúc, giao thức và cơ chế hoạt động của công cụ/hệ thống được chọn
2. **Triển khai hệ thống**: Xây dựng mô hình mạng thực nghiệm (Docker, AWS, EVE-NG, GNS3)
3. **Xây dựng kịch bản kiểm thử**: Thiết kế từ tải bình thường đến stress test, giả lập sự cố
4. **Đánh giá và trực quan hóa**: Thu thập metrics và biểu diễn qua Dashboard

---

## ✅ NHỮNG ĐIỀU CẦN CÓ (Must-haves)

- [x] **Sơ đồ mô hình mạng (Topology) rõ ràng**: IP, Subnet, vai trò từng Node
- [x] **Ít nhất 2-3 kịch bản thực nghiệm chi tiết**: So sánh trước/sau can thiệp
- [x] **Thu thập Metrics cụ thể**: Latency, Throughput, Packet Loss, CPU/RAM/Disk IO
- [x] **Báo cáo cấu trúc chuẩn**: Mở đầu → Lý thuyết → Thiết kế → Triển khai → Đánh giá → Kết luận
- [x] **Bảng phân công công việc**: Vai trò và đóng góp % của từng thành viên
- [x] **Tài liệu minh chứng**: Slide thuyết trình và Video Demo

## 🌟 NHỮNG ĐIỀU NÊN CÓ (Nice-to-haves)

- [x] **Tích hợp tự động hóa/Giám sát hiện đại**: Cảnh báo qua Webhook, tự động remediation
- [x] **Công cụ tạo tải chuyên nghiệp**: Stress-ng, Locust cho tải mạng/phần cứng
- [x] **Môi trường Container thực tế**: Docker Compose, Kubernetes-style deployment
- [x] **So sánh đối chiếu**: Manual Operations vs AI-Powered Automation

---

## 🏗️ KIẾN TRÚC HỆ THỐNG (TOPOLOGY)

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
│  2. Build Prompt  → Call Gemini gemma-3-1b-it             │
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
│  • check_system_load() / reduce_system_load()              │
└─────────────────────────────────────────────────────────────┘
```

**Network Configuration:**

- **Network**: aiops-net (Docker bridge)
- **Services**: 7 containers (target-app, prometheus, alertmanager, grafana, aiops-agent, node-exporter, cadvisor)
- **Exposed Ports**: 3000 (Grafana), 5000 (Target App), 8080 (Agent), 9090 (Prometheus), 9093 (AlertManager)

---

## 📅 KẾ HOẠCH TRIỂN KHAI (8 TUẦN)

### **Giai đoạn 1: Cơ sở lý thuyết (Tuần 1-2)**

- [x] **Agentic AIOps**: Khái niệm AI Agent tự suy luận và thực thi hành động
- [x] **Thành phần**: LLM (Gemini) + Monitoring Stack (Prometheus/Grafana) + Automation scripts (Python/Docker API)
- [x] **Giao thức**: Agent giao tiếp qua Webhook, REST API, Docker socket

### **Giai đoạn 2: Thiết kế hệ thống (Tuần 3)**

- [x] **Target System**: Flask Web Server với stress endpoints
- [x] **Monitoring Node**: Prometheus + Grafana + AlertManager
- [x] **Agentic AIOps Node**: Python Flask + Google Gemini API + Docker tools

### **Giai đoạn 3: Triển khai môi trường (Tuần 4-5)**

- [x] **Hạ tầng**: Docker Compose với 7 services
- [x] **Monitoring**: Prometheus scrape từ Node Exporter, cAdvisor
- [x] **Alert Rules**: 8 rules cho CPU, Memory, Request Rate, System Load
- [x] **AI Agent**: 8 tools với quyền Docker, iptables, SSH

### **Giai đoạn 4: Kịch bản thực nghiệm (Tuần 6-7)**

#### **Kịch bản 1: Baseline Overhead Assessment**

- **Mục đích**: Đánh giá tài nguyên tiêu thụ của AI Agent
- **Phương pháp**: So sánh CPU/RAM/Network khi có/không có Agent
- **Metrics**: Agent Memory < 200MB, CPU < 10%
- **Tools**: Container metrics từ cAdvisor

#### **Kịch bản 2: DDoS Response & Auto-remediation**

- **Mục đích**: Kiểm tra khả năng phản ứng với tấn công DDoS
- **Phương pháp**: Locust tạo 500 users, 50 req/s spawn rate
- **AI Response**: Detect high latency → Apply rate limiting
- **Metrics**: Request rate, latency trước/trong/sau can thiệp

#### **Kịch bản 3: CPU Stress & Process Management**

- **Mục đích**: Tự động xử lý quá tải CPU
- **Phương pháp**: stress-ng tạo CPU 100%
- **AI Response**: Detect high CPU → Kill stress processes → Restart if needed
- **Metrics**: CPU recovery time, system load normalization

### **Giai đoạn 5: Báo cáo và Demo (Tuần 8)**

- [x] **Dashboard**: Grafana với 2 dashboard (overview + agent analytics)
- [x] **Validation**: Automated test script với 25+ test cases
- [x] **Documentation**: Comprehensive guides và troubleshooting
- [x] **Video Demo**: Screen recording của tất cả 3 scenarios

---

## 🧪 CHI TIẾT KỊCH BẢN THỰC NGHIỆM

### **Kịch bản 1: Overhead Baseline**

```bash
# Tắt Agent, đo baseline
docker-compose stop agent
# Đo CPU/RAM/Network trong 2 phút

# Bật Agent, đo overhead
docker-compose start agent
# Đo lại và so sánh delta
```

**Expected Results:**

- Agent RAM usage: 60-100MB (baseline)
- Agent CPU usage: <5% (idle state)
- Network overhead: Minimal (<1MB/min)

### **Kịch bản 2: DDoS Simulation**

```bash
# Khởi động load test
locust -f loadtest/locustfile.py \
  --host=http://localhost:5000 \
  --users 500 --spawn-rate 50 \
  --run-time 3m --headless

# Alert expected: HighRequestRate, HighRequestLatency
# AI Action: apply_rate_limit(interface="eth0", rate="50/sec")
```

**Expected Results:**

- Request rate reduction từ 500+ → 50 req/s
- Latency improvement từ >2s → <1s
- MTTR (Mean Time To Recovery): <30 seconds

### **Kịch bản 3: CPU Stress**

```bash
# Tạo CPU stress
docker exec target-app stress-ng --cpu 4 --timeout 90s

# Alert expected: HighCPUUsage, ContainerHighCPU
# AI Actions: get_top_processes → kill_process("stress-ng")
```

**Expected Results:**

- CPU usage drop từ 100% → <20%
- System load normalization từ >4.0 → <2.0
- Process kill success rate: >95%

---

## 📊 METRICS VÀ KPI ĐÁNH GIÁ

| Metric                  | Description           | Target       | Tool               |
| ----------------------- | --------------------- | ------------ | ------------------ |
| **MTTR**                | Mean Time To Recovery | <30 seconds  | Manual measurement |
| **LLM Latency**         | AI decision time      | <5 seconds   | Agent logs         |
| **Decision Accuracy**   | % correct actions     | >90%         | Manual review      |
| **Agent Overhead**      | RAM/CPU consumption   | <200MB, <10% | Prometheus         |
| **False Positive Rate** | % unnecessary actions | <5%          | Manual review      |
| **System Recovery**     | Time to normal state  | <60 seconds  | Grafana charts     |

---

## 🔄 SO SÁNH: MANUAL vs AI-POWERED

| Aspect                  | Manual Operations          | AI-Powered Operations |
| ----------------------- | -------------------------- | --------------------- |
| **Response Time**       | 5-15 minutes               | <30 seconds           |
| **Availability**        | 8h/day (business hours)    | 24/7                  |
| **Cost per Incident**   | $10-50 (labor)             | $0.01-0.05 (API)      |
| **Consistency**         | Varies by person           | Consistent            |
| **Scalability**         | Limited by human resources | Unlimited             |
| **Learning Capability** | Experience-based           | Data-driven           |

---

## 🎥 DELIVERABLES

### **Báo cáo Kỹ thuật (Technical Report)**

1. **Lời mở đầu**: Bối cảnh và động lực AIOps
2. **Cơ sở lý thuyết**: Agent AI, Monitoring, Auto-remediation
3. **Thiết kế hệ thống**: Topology, Tech stack, Architecture
4. **Triển khai**: Docker setup, Configuration files
5. **Kịch bản & Kết quả**: 3 scenarios với charts từ Grafana
6. **Đánh giá**: KPIs, So sánh Manual vs AI, Ưu/Nhược điểm
7. **Kết luận**: Đóng góp, Hạn chế, Hướng phát triển

### **Video Demo (5-7 phút)**

- **Phần 1**: Giới thiệu project và kiến trúc (1 phút)
- **Phần 2**: Demo Scenario CPU Stress (2 phút)
- **Phần 3**: Demo Scenario DDoS Response (2 phút)
- **Phần 4**: Dashboard và metrics analysis (1 phút)
- **Phần 5**: Kết luận và Q&A (1 phút)

### **Slide Thuyết trình**

- 15-20 slides với focus vào results và live demo
- Screenshots từ Grafana dashboard
- Performance comparison charts
- Architecture diagrams

---

## 🔧 TECHNICAL STACK

**AI & Machine Learning:**

- Google Gemini gemma-3-1b-it (LLM for reasoning)
- Python 3.11 (Agent implementation)
- Flask (Webhook receiver)

**Monitoring & Observability:**

- Prometheus (Metrics collection)
- Grafana (Visualization & dashboards)
- AlertManager (Alert routing & webhooks)
- Node Exporter + cAdvisor (System metrics)

**Infrastructure & Automation:**

- Docker & Docker Compose (containerization)
- Python Docker SDK (Container management)
- iptables (Network rate limiting)
- Linux system tools (process management)

**Load Testing & Validation:**

- Locust (HTTP load testing)
- stress-ng (CPU/Memory stress)
- Custom validation scripts (bash + jq + curl)

---

## 🚀 INNOVATION HIGHLIGHTS

1. **Real AI Decision Making**: Sử dụng LLM thật (Gemini) thay vì rule-based systems
2. **Container-native Automation**: Integration with Docker API cho modern infrastructure
3. **Comprehensive Metrics**: Thu thập data từ system, container, và application level
4. **Production-Ready**: Resource limits, security, error handling, logging
5. **End-to-End Testing**: Automated validation với 25+ test cases
6. **Modern Tech Stack**: Containerized deployment với best practices

---

## 📈 EXPECTED OUTCOMES

**Academic Value:**

- Demonstrate practical application of AI in network operations
- Show measurable performance improvements vs manual operations
- Provide replicable framework for AIOps implementation

**Technical Value:**

- Production-ready monitoring and automation framework
- Scalable architecture for enterprise environments
- Best practices for AI agent integration with infrastructure

**Innovation Value:**

- Bridge between traditional IT operations and modern AI capabilities
- Showcase of "conversation-to-action" AI paradigm
- Foundation for future autonomous infrastructure management

---

_Tài liệu này sẽ được cập nhật theo tiến độ thực hiện project._
