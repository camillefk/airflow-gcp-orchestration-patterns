from airflow import DAG
from airflow.providers.google.cloud.sensors.gcs import GCSObjectExistenceSensor
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator
from airflow.models import Variable
from datetime import datetime, timedelta

# Busca dinâmica, o airflow remove o prefixo 'AIRFLOW_VAR_' e busca diretamente o nome da variavel
BUCKET_NAME = Variable.get("GCP_BUCKET_NAME")
PROJECT_ID = Variable.get("GCP_PROJECT_ID")
DATASET_ID = Variable.get("BQ_DATASET_ID")
TABLE_ID = Variable.get("BQ_TABLE_ID")

default_args = {
    "owner": "Senior_Data_Engineer",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    "lab_gcs_to_bigquery_v1",
    default_args=default_args,
    description="Optimized Pipeline: GCS to BigQuery with Sensors and Idempotency",
    schedule="0 6 * * 1-5",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["portfolio", "gcp", "reschedule"],
) as dag:

    wait_for_json = GCSObjectExistenceSensor(
        task_id="wait_for_json_file",
        bucket=BUCKET_NAME,
        object="raw/vendas_{{ ds }}.json",
        google_cloud_conn_id="google_cloud_default",
        mode="reschedule",
        poke_interval=300,
        timeout=60 * 60 * 2,
    )

     load_to_bq = GCSToBigQueryOperator(
        task_id="gcs_to_bigquery",
        bucket=BUCKET_NAME,
        source_objects=["raw/vendas_{{ ds }}.json"],
        destination_project_dataset_table=f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}",
        source_format="NEWLINE_DELIMITED_JSON",
        write_disposition="WRITE_TRUNCATE",
        autodetect=True,
        gcp_conn_id="google_cloud_default",
        do_xcom_push=False,
    )

    wait_for_json >> load_to_bq
