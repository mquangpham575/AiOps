# Hướng Dẫn Chạy Demo AIOps 3-Node Azure

## Mục lục
1. [Điều kiện tiên quyết](#điều-kiện-tiên-quyết)
2. [Khởi động hệ thống](#khởi-động-hệ-thống)
3. [Chạy các kịch bản đánh giá](#chạy-các-kịch-bản-đánh-giá)
4. [Đầu ra và kết quả](#đầu-ra-và-kết-quả)
5. [Xử lý lỗi thường gặp](#xử-lý-lỗi-thường-gặp)

---

## Điều kiện tiên quyết

1. **Azure subscription**: Có quyền truy cập resource group `rg-aiops`
2. **SSH key**: File `.ssh/aiops3_key` trong thư mục project
3. **Azure CLI**: Đã login (`az login`)
4. **Python 3.10+**: Để chạy scripts

---

## Khởi động hệ thống

### Bước 1: Deploy infrastructure lên Azure

```powershell
# Deploy tất cả 3 nodes lên Azure
.\scripts\aiops-power.ps1 start
```

Script này sẽ:
1. Start 3 Azure VMs
2. Clone/pull repo trên mỗi VM
3. Deploy Docker containers

### Bước 2: Truy cập Dashboard (Sử dụng Public IP)

| Service | Địa chỉ Public | Purpose |
|---------|----------|---------------------|
| Grafana | http://104.215.158.157:3000 | View dashboards (Node 1) |
| AI Agent | http://104.215.158.157:8083/logs/ui | Live AI Actions (Node 1) |
| Prometheus | http://104.215.158.157:9090 | Scrape targets (Node 1) |
| Pushgateway | http://104.215.158.157:9091 | LoadGen ingress (Node 1) |
| Target App | http://4.194.57.3:80/health | Target status (Node 3) |
| cAdvisor | http://4.194.57.3:8080 | Container metrics (Node 3) |

### Kiểm tra trạng thái

```powershell
# Kiểm tra VM và service status
.\scripts\aiops-power.ps1 status
```

---

### Chạy kịch bản (Thực hiện trên Node 2)

Kịch bản phải được chạy từ **Node 2 (LoadGen)** để có thể bơm tải và thu thập metrics chính xác.

#### Cách 1: Chạy qua Azure RunCommand (Khuyên dùng)
```powershell
# Chạy Scenario Throughput (60s)
az vm run-command invoke -g rg-aiops -n aiops-loadgen-vm --command-id RunShellScript --scripts "cd /home/azureuser/AiOps" "python3 scripts/demo_runner.py --scenario throughput --iterations 1 --duration 60 --target-url http://10.0.1.6:80 --agent-url http://10.0.1.4:8083 --prometheus-url http://10.0.1.4:9090 --agent-key agent_secret_key_nt531"

# Chạy Scenario CPU MTTR
az vm run-command invoke -g rg-aiops -n aiops-loadgen-vm --command-id RunShellScript --scripts "cd /home/azureuser/AiOps" "python3 scripts/demo_runner.py --scenario cpu --iterations 1 --duration 60 --target-url http://10.0.1.6:80 --agent-url http://10.0.1.4:8083 --prometheus-url http://10.0.1.4:9090 --agent-key agent_secret_key_nt531"
```

#### Cách 2: Chạy trực tiếp qua SSH
```bash
# Login vào Node 2
ssh -i .ssh/aiops3_key_rsa azureuser@104.215.191.69

# Chạy demo (tất cả scenarios)
cd /home/azureuser/AiOps
python3 scripts/demo_runner.py --scenario all --iterations 1 --target-url http://10.0.1.6:80 --agent-url http://10.0.1.4:8083 --prometheus-url http://10.0.1.4:9090
```

### Với custom parameters

```bash
python scripts/demo_runner.py --scenario throughput --iterations 3 --duration 300 --json-output
```

---

## Đầu ra và kết quả

### Cấu trúc thư mục kết quả

```
results/
├── all_scenarios.json           # Combined JSON
├── throughput/
│   ├── runs/
│   │   ├── run_001/
│   │   │   ├── baseline_metrics.json
│   │   │   └── load_metrics.json
│   │   ├── run_002/
│   │   └── run_003/
│   ├── summary.json             # Aggregated stats (mean ± stdev)
│   ├── comparison.json          # Baseline vs Load comparison
│   └── results.csv              # CSV export
├── cpu/
│   └── ...
└── memory/
    └── ...
```

### Xem kết quả nhanh

```bash
# Xem comparison summary
cat results/throughput/comparison.json | jq

# Xem MTTR stats
cat results/cpu/summary.json | jq
```

---

## Baseline Comparison

| Scenario | Baseline | Load/Stress | Pass Criteria |
|----------|----------|-------------|---------------|
| throughput | 20 users, stable | 50→500 users, staged | Load p95 < 3x Baseline p95 |
| cpu | Normal | stress-ng injection | MTTR < threshold |
| memory | Normal | Legitimate + Attack | Success rate > threshold |

---

## Dừng hệ thống

```powershell
# Stop containers và deallocate VMs
.\scripts\aiops-power.ps1 stop
```

---

## Xử lý lỗi thường gặp

### "SSH Permission Denied"
- Kiểm tra SSH key: `.ssh/aiops3_key`
- Kiểm tra Azure VM đã running chưa

### "Metrics are empty"
- Đợi 30-60 giây sau khi khởi động để Prometheus bắt đầu scrape
- Kiểm tra Prometheus targets: http://104.215.158.157:9090/targets

### Kiểm tra containers đang chạy

```bash
# SSH vào VM và kiểm tra
ssh -i .ssh/aiops3_key_rsa azureuser@104.215.158.157 "docker ps"
```

---

## Tips cho Demo

1. **Chạy trước 1 iteration** để verify setup:
   ```bash
   python scripts/demo_runner.py --scenario throughput --iterations 1 --json-output
   ```

2. **Xem dashboard trực tiếp**:
   - Mở Grafana: http://104.215.191.69:3000
   - Import dashboard: `ops/monitoring/grafana/dashboards/aiops_perf_eval.json`

3. **Debug containers**:
   ```bash
   ssh -i .ssh/aiops3_key azureuser@10.0.1.4
   docker compose -f ops/infra/docker-compose.control.yml logs -f
   ```
