# Architecture Documentation

## Data Flow Diagram

```text
┌───────────────────────┐
│    External System    │
│ Creates Daily JSON    │
└───────────┬───────────┘
            │
            │ Uploads raw/vendas_YYYY-MM-DD.json
            ▼
┌──────────────────────────────────────────┐
│      Google Cloud Storage (GCS)          │
│                                          │
│ gs://my-bucket/raw/vendas_2026-07-15.json│
└───────────┬──────────────────────────────┘
            │
            │ GCSObjectExistenceSensor
            │ (reschedule mode)
            ▼
┌──────────────────────────────────────────┐
│      Apache Airflow Orchestrator         │
│      (Docker + Astro Runtime)            │
│                                          │
│ ✓ GCSObjectExistenceSensor               │
│ ✓ GCSToBigQueryOperator                  │
│ ✓ Application Default Credentials        │
└───────────┬──────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────┐
│           Google BigQuery                │
│                                          │
│      project.dataset.table               │
└──────────────────────────────────────────┘
```

The Airflow pipeline **does not generate source files**. It continuously monitors the configured Cloud Storage bucket and starts processing only after the expected daily JSON file becomes available.

---

## Component Breakdown

### 1. Data Source: Google Cloud Storage

**Bucket Structure:**

```text
gs://my-bucket/
└── raw/
    ├── vendas_2026-07-01.json
    ├── vendas_2026-07-02.json
    └── vendas_2026-07-15.json
```

One JSON file is expected for each DAG execution date.

**Naming convention**

```text
raw/vendas_YYYY-MM-DD.json
```

**Example**

```text
raw/vendas_2026-07-15.json
```

**File Format:** Newline-delimited JSON (NDJSON)

```json
{"id":1,"amount":100.00,"timestamp":"2024-01-15T10:30:00Z"}
{"id":2,"amount":250.50,"timestamp":"2024-01-15T10:31:00Z"}
```

---

### 2. Orchestrator: Apache Airflow

**Why Airflow?**
- Declarative DAG definitions (Python)
- Native Google Cloud integration
- Battle-tested in production environments
- Flexible scheduling (cron-based and event-driven)
- Rich monitoring and logging

**Runtime Stack**
- Base Image: `astrocrpublic.azurecr.io/runtime:3.1-14`
- Python: 3.11+
- Apache Airflow: 2.7+
- Google Provider: v10.12.0

**Execution Flow**
```text
1. Scheduler starts the DAG at 6:00 AM (weekdays)

2. Creates a DAG Run

3. Executes wait_for_json_file

   ├─ Sensor enters "reschedule" mode
   ├─ Worker is released while waiting
   ├─ Every 5 minutes the sensor checks whether
   │  raw/vendas_{{ ds }}.json exists
   └─ Once the object is found → Task succeeds

4. Executes gcs_to_bigquery

   ├─ Reads the JSON file from GCS
   ├─ Replaces existing table data
   ├─ Automatically detects the schema
   └─ Loads the data into BigQuery

5. DAG Run finishes successfully
```

---

### 3. Data Warehouse: Google BigQuery

**Table Design**
- Partitioning: Execution date
- Schema: Auto-detected
- Write Disposition: `WRITE_TRUNCATE`

**Query Example**
```sql
SELECT
    id,
    amount,
    timestamp,
    _PARTITIONTIME AS load_date
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

**Cost:** ~2 hours × worker rate × all DAGs waiting = expensive.

### Solution: Reschedule Mode

```text
Time ───────────────────────────────────────────────→

Worker Slot:  [█][        free        ][█]
              Occupied only during checks

File Check:   [✓][   released   ][✗][   released   ][✓]
              Polls every 5 minutes (non-blocking)
```

**Cost:** Worker resources are consumed only during sensor execution, resulting in significant cost savings for long-running waits.

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

**Why ADC?**
- ✅ No hardcoded credentials
- ✅ Automatic credential refresh
- ✅ Native Workload Identity support
- ✅ Same authentication model for local development and production

**Required IAM Roles**
```text
roles/storage.objectViewer
roles/bigquery.dataEditor
roles/bigquery.jobUser
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

This allows historical reruns and backfills without generating duplicate records.

---

## Scaling Considerations

### Vertical Scaling

* Increase CPU and memory for Airflow workers
* Suitable for larger files

### Horizontal Scaling

* Multiple Airflow workers
* Kubernetes-based deployments
* Higher DAG concurrency

### Additional Optimizations

* Partitioned BigQuery tables
* Compressed GCS files (gzip)
* Incremental loading strategies when applicable

---

## Testing Strategy

### Unit Tests

```bash
astro dev bash airflow dags list
```

---

### Integration Tests

```bash
astro dev bash airflow tasks test \
lab_gcs_to_bigquery_v1 \
wait_for_json_file \
2024-01-15
```

---

### End-to-End Test

```bash
# Create a JSON file locally

# Upload it to the expected location
gsutil cp vendas_2024-01-15.json \
gs://my-bucket/raw/vendas_2024-01-15.json

# Trigger the DAG
airflow dags trigger lab_gcs_to_bigquery_v1

# Verify the loaded data
bq query \
"SELECT COUNT(*) FROM dataset.table WHERE _PARTITIONTIME = CURRENT_DATE()"
```

The DAG starts processing only after the expected object is available inside the `raw/` directory of the configured Cloud Storage bucket.

---

## Disaster Recovery

| Scenario                     | Recovery                                                 |
| ---------------------------- | -------------------------------------------------------- |
| Sensor timeout               | Airflow retries after 5 minutes                          |
| BigQuery load failure        | Retry task after resolving the issue                     |
| Corrupted source data        | Replace the source file and rerun the DAG                |
| Airflow service interruption | Restart Airflow or rely on managed service auto-recovery |

### Example Backfill

```bash
airflow backfill \
  --dag-id lab_gcs_to_bigquery_v1 \
  --from-date 2024-01-01 \
  --to-date 2024-01-10 \
  --clear-only
```

---

**Last updated:** July 15, 2026
