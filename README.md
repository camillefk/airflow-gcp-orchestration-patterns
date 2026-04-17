# Serverless Data Pipeline: GCS to BigQuery with Apache Airflow

## Project Objective
This project implements a professional, production-ready data ingestion pipeline that monitors a Google Cloud Storage (GCS) bucket for daily JSON files and loads them into Google BigQuery. 

The focus of this LAB was on **infrastructure cost optimization**, **data idempotency**, and **enterprise-grade security**.

## Architecture
1. **Orchestration:** Apache Airflow (running on Docker via Astro CLI).
2. **Data Source:** Google Cloud Storage (GCS) - Landing Zone.
3. **Data Warehouse:** Google BigQuery.
4. **Security:** Workload Identity Federation (simulated via ADC) to avoid hardcoded JSON keys.

## Key Technical Features
### 1. Cost Optimization (Poke vs. Reschedule)
Instead of the default `poke` mode, I implemented the **`reschedule`** mode in the GCS Sensor.
- **Why?** In cloud environments, a sensor in `poke` mode keeps a worker slot occupied (and billing) while waiting for a file. `reschedule` releases the worker and only checks back at defined intervals, saving significant infrastructure costs.

### 2. Idempotency & Backfill
The pipeline is designed to be **idempotent**. 
- Using `WRITE_TRUNCATE` disposition, we ensure that re-running the same day (Backfill) will not result in duplicated data. The logic clears the destination for that specific execution before re-inserting.

### 3. Enterprise Security
Aligned with Google Cloud's best practices, this project uses **Application Default Credentials (ADC)** instead of static Service Account JSON keys, preventing credential leakage in repositories.

## How to Run
1. Install [Astro CLI](https://www.astronomer.io/opensource/).
2. Authenticate with GCP: `gcloud auth application-default login`.
3. Configure your `.env` file with your Bucket and Project IDs.
4. Run `astro dev start`.
5. Trigger a backfill via terminal:
   ```bash
   airflow backfill create --dag-id lab_gcs_to_bigquery_v1 --from-date YYYY-MM-DD --to-date YYYY-MM-DD

   This file defines an **Apache Airflow DAG** that orchestrates a data pipeline from Google Cloud Storage (GCS) to BigQuery.

## 🧩 Code Explanation (DAG Deep Dive)

The pipeline (`lab_gcs_to_bigquery_v1`) waits for a JSON file to appear in GCS, then loads it into BigQuery.

## Key Components

**Configuration Variables** (lines 8–11)
- Dynamically retrieves GCP settings from Airflow variables:
  - `GCP_BUCKET_NAME`: GCS bucket to read from
  - `GCP_PROJECT_ID`: GCP project ID
  - `BQ_DATASET_ID`: BigQuery dataset
  - `BQ_TABLE_ID`: BigQuery table

**DAG Settings** (lines 13–29)
- **Owner**: Senior_Data_Engineer
- **Schedule**: Runs at 6 AM, Monday–Friday (`0 6 * * 1-5`)
- **Start Date**: January 1, 2024
- **Catchup**: Disabled (won't backfill historical runs)
- **Retries**: 1 attempt if task fails, with 5-minute delay

**Task 1: `wait_for_json`** (lines 31–39)
- Uses `GCSObjectExistenceSensor` to wait for a file at `raw/vendas_{{ ds }}.json` (where `{{ ds }}` is the execution date)
- **Mode**: `reschedule` (frees up worker slot instead of blocking)
- **Polling**: Checks every 5 minutes
- **Timeout**: 2 hours max wait

**Task 2: `load_to_bq`** (lines 41–51)
- Uses `GCSToBigQueryOperator` to load the JSON file into BigQuery
- **Format**: Newline-delimited JSON
- **Write Mode**: `WRITE_TRUNCATE` (overwrites existing table data)
- **Autodetect**: Automatically infers BigQuery schema
- **XCom Push**: Disabled (doesn't push results to other tasks)

**Dependency** (line 53)
- `wait_for_json >> load_to_bq`: The sensor must complete before the load begins

This is an efficient, production-ready pattern that minimizes resource usage with the `reschedule` mode and ensures data integrity with write disposition settings.