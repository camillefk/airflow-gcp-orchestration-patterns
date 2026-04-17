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