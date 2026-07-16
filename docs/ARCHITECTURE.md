# Architecture Documentation

## Data Flow Diagram
```text
┌──────────────────┐
│    Daily Job     │
│   Creates File   │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│      Google Cloud Storage (GCS)          │
│                                          │
│ gs://my-bucket/raw/vendas_2024-01-15     │
└────────┬─────────────────────────────────┘
         │
         │ Airflow Sensor Monitors
         │ (reschedule mode)
         ▼
┌──────────────────────────────────────────┐
│      Apache Airflow Orchestrator         │
│      (Docker + Astro Runtime)            │
│                                          │
│ ✓ GCSObjectExistenceSensor               │
│ ✓ GCSToBigQueryOperator                  │
│ ✓ Application Default Credentials        │
└────────┬─────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│           Google BigQuery                │
│                                          │
│      project.dataset.table               │
└──────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. Data Source: Google Cloud Storage

**Bucket Structure:**

```text
gs://my-bucket/
└── raw/
    ├── vendas_2024-01-01.json
    ├── vendas_2024-01-02.json
    └── vendas_2024-01-15.json
```

**File Format:** Newline-delimited JSON (NDJSON)
```json
{"id": 1, "amount": 100.00, "timestamp": "2024-01-15T10:30:00Z"}
{"id": 2, "amount": 250.50, "timestamp": "2024-01-15T10:31:00Z"}
```

### 2. Orchestrator: Apache Airflow

**Why Airflow?**
- Declarative DAG definitions (Python code)
- Native GCP integration (apache-airflow-providers-google)
- Battle-tested in production environments
- Flexible scheduling (cron-like, event-driven)
- Rich monitoring and alerting

**Runtime Stack:**
- Base Image: `astrocrpublic.azurecr.io/runtime:3.1-14`
- Python: 3.11+ (standard with Astro 3.1)
- Airflow Version: 2.7+
- GCP Provider: v10.12.0

**Execution Flow:**
```text
1. Scheduler checks if it's 6:00 AM on a weekday
2. Creates a DAG run
3. Executes wait_for_json_file task
   ├─ Sensor enters "reschedule" mode
   ├─ Worker released; task is rescheduled
   ├─ Sensor checks for the file every 5 minutes
   └─ Once file found → Task completes
4. Executes gcs_to_bigquery task
   ├─ Reads JSON from GCS
   ├─ Truncates destination table
   ├─ Loads data with auto-schema detection
   └─ Task completes
5. DAG run marked as SUCCESS
```

### 3. Data Warehouse: Google BigQuery

**Table Design:**
- Partitioning: By execution date (YYYY-MM-DD)
- Schema: Auto-detected from JSON
- Write Disposition: WRITE_TRUNCATE (idempotent)

**Query Example:**
```sql
SELECT 
  id, 
  amount, 
  timestamp,
  _PARTITIONTIME as load_date
FROM `project.dataset.table`
WHERE _PARTITIONTIME = CURRENT_DATE()
ORDER BY timestamp DESC;
```

---

## Cost Optimization Strategy

### Problem: Traditional Sensor (Poke Mode)
```text
Time ───────────────────────────────────────────────→

Worker Slot:  [██████████████████████████████████]
              Occupied for 2 hours (billing continues)

File Check:   [✓][✗][✗][✗][✗] ... [✓]
              Polls every 30 seconds while blocking the worker
```

**Cost:** ~2 hours × worker rate × all DAGs waiting = expensive

### Solution: Reschedule Mode
```text
Time ───────────────────────────────────────────────→

Worker Slot:  [█][        free        ][█]
              Occupied only during checks

File Check:   [✓][   released   ][✗][   released   ][✓]
              Polls every 5 minutes (non-blocking)
```

**Cost:** Only ~5 minutes x check duration x worker rate = Up to 80% cost savings

---

## Security Architecture

### Authentication Flow
```text
┌──────────────────────────────────────────────┐
│        Local Development / Cloud Runtime     │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
        ┌─────────────────────────────────┐
        │ Application Default Credentials │
        │              (ADC)              │
        │                                 │
        │ - No JSON keys                  │
        │ - Workload Identity             │
        └──────────────┬──────────────────┘
                       │
                       ▼
        ┌─────────────────────────────────┐
        │        Google Cloud IAM         │
        │                                 │
        │ - Service Account               │
        │ - Workload Identity Pool        │
        │ - IAM Role Bindings             │
        └──────────────┬──────────────────┘
                       │
               ┌───────┴────────┐
               ▼                ▼
         [ GCS Access ]   [ BigQuery Access ]
```

### Why ADC?
✓ **No hardcoded credentials** in code or configs
✓ **Automatic credential refresh** (No credential expiration issues)
✓ **Workload Identity support** (GKE/Cloud Run native)
✓ **Environment-agnostic** (dev, staging, prod)

### IAM Roles Required

**For Airflow service account:**
```text
roles/storage.objectViewer        # Read from GCS
roles/bigquery.dataEditor         # Write to BigQuery
roles/bigquery.jobUser            # Run BigQuery jobs
```

---

## Idempotency Strategy

### Problem: Duplicate Data During Reruns
```text
Run 1 (2024-01-15):
  vendas_2024-01-15.json → BigQuery
  │
  └─ APPEND mode → 1000 rows

Rerun (2024-01-15, same file):
  vendas_2024-01-15.json → BigQuery
  │
  └─ APPEND mode → 2000 rows (duplicated!)
```

### Solution: WRITE_TRUNCATE
```text
Run 1 (2024-01-15):
  vendas_2024-01-15.json → BigQuery
  │
  └─ TRUNCATE + INSERT → 1000 rows

Rerun (2024-01-15):
  vendas_2024-01-15.json → BigQuery
  │
  ├─ Overwrite existing data
  └─ INSERT fresh → 1000 rows (no duplicates!)
```

---

## Scaling Considerations

### Vertical Scaling 
- Increase Airflow worker resources (CPU, memory)
- Good for: Larger JSON files, more frequent checks

### Horizontal Scaling
- Multiple Airflow workers via Kubernetes
- Good for: Multiple concurrent DAGs, high throughput

### Optimizations
- **Partitioned BigQuery tables** for faster queries
- **Compressed GCS files** (gzip) to reduce transfer time 
- **Incremental loads** instead of full table reloads (if source guarantees uniqueness)

---

## Testing Strategy

### Unit Tests (DAG Syntax)
```bash
astro dev bash airflow dags list
```

### Integration Tests (Operators)
```bash
# Test sensor with dummy file
astro dev bash airflow tasks test lab_gcs_to_bigquery_v1 wait_for_json_file 2024-01-15
```

### End-to-End Tests
```bash
# Create test data in GCS
gsutil cp test_data.json gs://my-bucket/raw/vendas_2024-01-15.json

# Trigger DAG
airflow dags trigger lab_gcs_to_bigquery_v1

# Verify BigQuery
bq query "SELECT COUNT(*) FROM dataset.table WHERE _PARTITIONTIME = CURRENT_DATE()"
```

---

## Disaster Recovery 

| Scenario | Recovery |
| ----- | ----- |
| Failed sensor |	Airflow retries after 5-minute delay; max 1 retry |
| BigQuery load fails |	Task fails; Airflow logs show error details |
| Data corrupted |	Backfill with corrected source file |
| Airflow crashes |	Cloud Run/Cloud Composer auto-restarts |

### Backfill Example:
```bash
airflow backfill \
  --dag-id lab_gcs_to_bigquery_v1 \
  --from-date 2024-01-01 \
  --to-date 2024-01-10 \
  --clear-only  # Only clear tasks, don't rerun
```

---

**Last updated: July 15, 2026**
