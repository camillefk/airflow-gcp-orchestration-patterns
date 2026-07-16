# Airflow GCP Orchestration Patterns

> Production-grade Apache Airflow pipeline demonstrating **event-driven data ingestion**, **enterprise security**, and **cost optimization** on Google Cloud Platform.

## Pipeline Flow

```text
Google Cloud Storage
        │
        ▼
GCSObjectExistenceSensor
(reschedule mode)
        │
        ▼
GCSToBigQueryOperator
        │
        ▼
Google BigQuery
```

## Project Overview

This repository showcases a production-ready data ingestion pipeline that:

- ✓ Monitors Google Cloud Storage (GCS) for a daily JSON file matching the DAG execution date
- ✓ Automatically loads data into BigQuery with **zero manual intervention**
- ✓ Implements **idempotent operations** for safe reruns and historical backfills
- ✓ Optimizes infrastructure costs using smart sensor patterns
- ✓ Follows Google Cloud security best practices (Application Default Credentials and Workload Identity)

**Stack:**

- **Orchestration:** Apache Airflow 2.x (Astro Runtime 3.1)
- **Cloud Platform:** Google Cloud Platform (Cloud Storage, BigQuery, IAM)
- **Runtime:** Astro Runtime 3.1 (Docker)
- **Authentication:** Application Default Credentials (ADC)
- **Google Provider:** apache-airflow-providers-google v10.12.0

**Use this as a reference implementation for:**

- Apache Airflow on Google Cloud
- Event-driven data ingestion
- Data pipeline cost optimization
- Enterprise-grade security patterns
- Idempotent data processing

---

## Documentation

| File | Description |
|------|-------------|
| `README.md` | Project overview |
| `docs/ARCHITECTURE.md` | Architecture and design decisions |
| `docs/SETUP.md` | Local development and configuration guide |

---

## Key Features & Patterns

### 1. Cost Optimization: Reschedule vs. Poke

Traditional sensor mode (`poke`) keeps a worker slot occupied while waiting, resulting in unnecessary billing.

This project uses **`reschedule` mode**, which:

- Releases the worker slot while waiting for the file
- Checks for file existence every 5 minutes
- Frees the worker between checks
- Reduces infrastructure costs for long-running sensors

```python
#From dags/gcs_to_bq_pipeline.py
wait_for_json = GCSObjectExistenceSensor(
    mode="reschedule",
    poke_interval=300,
    timeout=60 * 60 * 2,
)
```

**Recommended when:**

- Waiting for external files
- Long-running sensors
- Production environments
- Cost optimization matters

---

### 2. Idempotency & Safe Backfills

The pipeline uses `WRITE_TRUNCATE` to guarantee safe reruns.

| Scenario | Result |
|----------|--------|
| First execution | Creates table and loads data |
| Rerun | Replaces existing data (no duplicates) |
| Historical backfill | Safe to rerun multiple dates |

```python
load_to_bq = GCSToBigQueryOperator(
    write_disposition="WRITE_TRUNCATE",
    autodetect=True,
)
```

---

### 3. Enterprise Security

The project follows Google Cloud authentication best practices.

- ✓ Uses Application Default Credentials (ADC)
- ✓ No service account JSON keys committed to Git
- ✓ Compatible with Workload Identity
- ✓ Works locally and in production

```bash
gcloud auth login
gcloud auth application-default login
```

---

## Quick Start

### Prerequisites

- Docker Desktop
- Astro CLI
- Google Cloud SDK
- Google Cloud Project
- Cloud Storage Bucket
- BigQuery Dataset

---

### Installation

```bash
git clone https://github.com/camillefk/airflow-gcp-orchestration-patterns.git

cd airflow-gcp-orchestration-patterns
```

Authenticate with Google Cloud:

```bash
gcloud auth login

gcloud auth application-default login
```

Create your `.env` file:

```bash
AIRFLOW_VAR_GCP_BUCKET_NAME=your-bucket
AIRFLOW_VAR_GCP_PROJECT_ID=your-project
AIRFLOW_VAR_BQ_DATASET_ID=your_dataset
AIRFLOW_VAR_BQ_TABLE_ID=your_table
```

Start Airflow:

```bash
astro dev start
```

Open:

```
http://localhost:8080
```

Default credentials:

```
Username: admin
Password: admin
```

> **Note**
>
> See `SETUP.md` for the complete local development setup, including ADC configuration and uploading test files to Cloud Storage.

---

## Expected Input File

The DAG waits for a JSON file inside Cloud Storage following this naming convention:

```text
raw/vendas_YYYY-MM-DD.json
```

Example:

```text
raw/vendas_2024-01-15.json
```

The filename **must match the DAG execution date**, since the sensor monitors:

```python
raw/vendas_{{ ds }}.json
```

---

## Running the Pipeline

Upload a JSON file:

```bash
gcloud storage cp vendas_2024-01-15.json \
gs://your-bucket/raw/vendas_2024-01-15.json
```

Trigger the DAG:

```bash
airflow dags trigger lab_gcs_to_bigquery_v1 \
--exec-date 2024-01-15
```

Or execute a historical backfill:

```bash
airflow backfill \
--dag-id lab_gcs_to_bigquery_v1 \
--from-date 2024-01-01 \
--to-date 2024-01-31
```

---

## Configuration

The project uses Airflow Variables.

```text
AIRFLOW_VAR_GCP_BUCKET_NAME
AIRFLOW_VAR_GCP_PROJECT_ID
AIRFLOW_VAR_BQ_DATASET_ID
AIRFLOW_VAR_BQ_TABLE_ID
```

---

## DAG Details

**DAG**

```
lab_gcs_to_bigquery_v1
```

**Schedule**

```
Every weekday at 06:00

Cron:
0 6 * * 1-5
```

### Task 1 — wait_for_json_file

**Operator**

```
GCSObjectExistenceSensor
```

Monitors:

```
raw/vendas_{{ ds }}.json
```

Example:

```
raw/vendas_2024-01-15.json
```

Configuration:

- Mode: `reschedule`
- Polling interval: 5 minutes
- Timeout: 2 hours

---

### Task 2 — gcs_to_bigquery

**Operator**

```
GCSToBigQueryOperator
```

- Reads JSON from Cloud Storage
- Auto-detects schema
- Loads into BigQuery
- Uses `WRITE_TRUNCATE`

---

### Dependency

```text
wait_for_json
        │
        ▼
gcs_to_bigquery
```

---

## Testing

Validate DAGs:

```bash
astro dev bash airflow dags list
```

Show DAG:

```bash
astro dev bash airflow dags show lab_gcs_to_bigquery_v1
```

Test only the sensor:

```bash
astro dev bash airflow tasks test \
lab_gcs_to_bigquery_v1 \
wait_for_json_file \
2024-01-15
```

---

## Monitoring

View logs:

```bash
airflow logs \
-d lab_gcs_to_bigquery_v1 \
-t wait_for_json_file \
2024-01-15
```

---

## Troubleshooting

| Problem | Solution |
|----------|----------|
| Google connection not found | Configure `google_cloud_default` |
| Sensor timeout | Check file path or increase timeout |
| Permission denied | Verify IAM permissions |
| Schema mismatch | Enable `autodetect=True` |

---

## Project Structure

```text
.
├── dags/
│   └── gcs_to_bq_pipeline.py
├── docs/
│   └── ARCHITECTURE.md
│   └── SETUP.md
├── include/
├── tests/
├── requirements.txt
├── Dockerfile
├── .env.example
├── README.md

```

---

**Built by:** @camillefk  
**Created:** April 2026  
**Last Updated:** July 15, 2026