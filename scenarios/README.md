# Kịch bản Đánh giá Hiệu năng — NT531 AIOps PoC

## Mục tiêu chung

Tìm cấu hình phù hợp cho hệ thống AIOps thông qua đánh giá hiệu năng có phương pháp:

- Mỗi kịch bản chạy **3 lần x 5 phút** để đảm bảo tính lặp lại
- Thu thập **p50 / p95 / p99** latency cho mỗi lần chạy
- So sánh **baseline vs scenario** và **AI Agent vs Rule-Based Agent**
- Xuất kết quả CSV + bảng tổng hợp thống kê (mean, stdev)

## Cách chạy

```bash
# Chạy tất cả 3 kịch bản (mặc định 3 lần x 5 phút)
python scripts/demo_runner.py --scenario all

# Chạy 1 kịch bản cụ thể
python scripts/demo_runner.py --scenario throughput
python scripts/demo_runner.py --scenario cpu
python scripts/demo_runner.py --scenario memory

# Tùy chỉnh số lần chạy và thời gian
python scripts/demo_runner.py --scenario throughput --iterations 5 --duration 600

# Xuất kết quả ra file CSV
python scripts/demo_runner.py --scenario all --export ket_qua.csv

# So sánh AI Agent vs Rule-Based Agent (chạy 2 lần, đổi agent-url)
python scripts/demo_runner.py --scenario cpu --agent-url http://localhost:8080
python scripts/demo_runner.py --scenario cpu --agent-url http://localhost:5001
```

Ghi chú:

- Với các kịch bản MTTR (CPU/Memory), runner đọc action log từ `/logs` và cần `AGENT_API_KEY` để truy cập.
- `agent_scenario` trong [scenarios/config.yml](scenarios/config.yml) dùng để khớp với nhãn `scenario` của Prometheus alerts (vd: `cpu_stress`, `memory_stress`).

---

## Kịch bản 1: Thông lượng & Độ trễ

| Thông tin       | Chi tiết                                                          |
| --------------- | ----------------------------------------------------------------- |
| **Mục tiêu**    | Đánh giá hiệu năng hệ thống dưới tải bình thường và tấn công DDoS |
| **Phương pháp** | 3 lần chạy, mỗi lần gồm 5 phút baseline + 5 phút DDoS             |
| **So sánh**     | Baseline vs DDoS, có Agent vs không Agent                         |

### Mô tả

Kịch bản này kết hợp đánh giá baseline và DDoS vào một luồng so sánh duy nhất.
Mỗi lần chạy (iteration) gồm 2 pha:

1. **Pha Baseline**: Gửi tải ổn định (~20 users) trong 5 phút, thu thập latency nền
2. **Pha DDoS**: Tăng tải lên 500 users trong 5 phút, đo hiệu năng dưới áp lực

### Chỉ số đánh giá

| Chỉ số         | Mô tả                       | PromQL                                              |
| -------------- | --------------------------- | --------------------------------------------------- |
| Latency p50    | Độ trễ trung vị             | `histogram_quantile(0.50, rate(...[1m]))`           |
| Latency p95    | Độ trễ phần trăm 95         | `histogram_quantile(0.95, rate(...[1m]))`           |
| Latency p99    | Độ trễ phần trăm 99         | `histogram_quantile(0.99, rate(...[1m]))`           |
| Throughput     | Số request/giây             | `sum(rate(flask_http_request_total[1m]))`           |
| Error Rate     | Tỉ lệ lỗi 5xx               | `rate(5xx) / rate(total) * 100`                     |
| CPU %          | CPU container target-app    | `rate(container_cpu_usage_seconds_total[1m]) * 100` |
| Memory %       | Memory container target-app | `usage / limit * 100`                               |
| Agent Overhead | CPU & RAM của AI Agent      | Đo riêng container `aiops-agent`                    |

### Kết quả mong đợi

- Baseline: latency p99 < 200ms, throughput > 100 req/s, error rate < 1%
- DDoS: latency tăng 5-10x, error rate tăng, agent phát hiện trong < 30s
- Agent overhead: CPU < 5%, Memory < 200MB

---

## Kịch bản 2: Tự phục hồi CPU

| Thông tin       | Chi tiết                                                     |
| --------------- | ------------------------------------------------------------ |
| **Mục tiêu**    | So sánh MTTR giữa AI Agent và Rule-Based Agent cho sự cố CPU |
| **Phương pháp** | 3 lần chạy, mỗi lần inject stress-ng + đo MTTR               |
| **So sánh**     | AI Agent MTTR vs Rule-Based Agent MTTR                       |

### Mô tả

Kịch bản inject CPU stress vào container `target-app` bằng `stress-ng --cpu 4`,
sau đó đo thời gian từ lúc inject đến lúc hệ thống phục hồi.

### Timeline mỗi lần chạy

```
T0: Inject stress-ng (CPU ~100%)
T1: Prometheus phát hiện alert ContainerHighCPU (sau ~30s for:)
T2: Agent nhận alert và thực hiện hành động
T3: CPU giảm xuống < 30% (phục hồi hoàn toàn)

MTTR = T3 - T0
Detection Latency = T1 - T0
Response Latency = T2 - T1
Remediation Time = T3 - T2
```

### Chỉ số đánh giá

| Chỉ số            | Mô tả                           |
| ----------------- | ------------------------------- |
| MTTR              | Mean Time To Recovery (giây)    |
| Detection Latency | Thời gian phát hiện (giây)      |
| Response Latency  | Thời gian agent phản hồi (giây) |
| Remediation Time  | Thời gian khắc phục (giây)      |
| Peak CPU %        | CPU cao nhất trong sự cố        |
| Action            | Hành động agent đã thực hiện    |
| Confidence        | Độ tin cậy của quyết định agent |

---

## Kịch bản 3: Tự phục hồi Memory

| Thông tin       | Chi tiết                                                        |
| --------------- | --------------------------------------------------------------- |
| **Mục tiêu**    | So sánh MTTR giữa AI Agent và Rule-Based Agent cho sự cố Memory |
| **Phương pháp** | 3 lần chạy, mỗi lần inject memory pressure + đo MTTR            |
| **So sánh**     | AI Agent MTTR vs Rule-Based Agent MTTR                          |

### Mô tả

Kịch bản sử dụng Locust gửi request `/memory?mb=20` liên tục để đẩy memory
container `target-app` vượt ngưỡng 60% limit (256MB).

### Timeline mỗi lần chạy

```
T0: Bắt đầu Locust memory stress (20 users x 20MB = ~400MB)
T1: Prometheus phát hiện alert HighMemoryUsage (sau ~30s for:)
T2: Agent nhận alert và thực hiện hành động (restart service)
T3: Memory giảm xuống < 50% (phục hồi + service healthy)

MTTR = T3 - T0
```

### Chỉ số đánh giá

| Chỉ số               | Mô tả                                      |
| -------------------- | ------------------------------------------ |
| MTTR                 | Mean Time To Recovery (giây)               |
| Detection Latency    | Thời gian phát hiện (giây)                 |
| Response Latency     | Thời gian agent phản hồi (giây)            |
| Remediation Time     | Thời gian khắc phục (giây)                 |
| Peak Memory %        | Memory cao nhất trong sự cố                |
| Restart Count        | Số lần restart container                   |
| Service Availability | Thời gian service healthy / tổng thời gian |

---

## Grafana Dashboards

Mỗi kịch bản có dashboard riêng, tự động provision khi khởi động Grafana:

| Dashboard                            | Mô tả                                                       |
| ------------------------------------ | ----------------------------------------------------------- |
| **Scenario 1: Throughput & Latency** | Latency p50/p95/p99, throughput, error rate, agent overhead |
| **Scenario 2: CPU Remediation**      | CPU timeline, MTTR breakdown, AI vs Rule-Based              |
| **Scenario 3: Memory Remediation**   | Memory timeline, MTTR breakdown, restart events             |

Truy cập: `http://localhost:3000` (admin / admin123)

---

## Cấu trúc kết quả CSV

```csv
scenario,iteration,phase,latency_p50_ms,latency_p95_ms,latency_p99_ms,throughput_rps,error_rate_pct,cpu_pct,memory_pct,detection_s,response_s,remediation_s,mttr_s,action,confidence
throughput,1,baseline,12.3,45.1,120.5,150.2,0.1,15.3,42.1,,,,,,
throughput,1,ddos,89.2,350.4,1200.1,420.5,5.2,78.3,65.2,,,,,,
throughput,summary,baseline,12.1±0.5,44.8±1.2,118.3±5.1,148.5±3.2,0.12±0.02,14.8±1.1,41.5±0.8,,,,,,
throughput,summary,ddos,88.5±2.1,348.2±8.5,1190.2±30.1,418.3±5.8,5.1±0.3,77.5±2.3,64.8±1.5,,,,,,
cpu,1,remediation,,,,,,95.2,,35.2,2.1,15.3,52.6,kill_stress,0.92
cpu,summary,remediation,,,,,,94.8±1.2,,34.8±1.5,2.3±0.4,14.8±1.2,51.9±2.1,,
```
