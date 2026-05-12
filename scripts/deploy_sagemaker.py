"""
scripts/deploy_sagemaker.py
-----------------------------
Deploys a fine-tuned model as a SageMaker async-inference endpoint.

Pulls training artifacts directly from S3 (no ~/omnisql-model/ cache needed),
re-packs them with inference.py + requirements.txt, and pushes a versioned
copy to s3://<model_bucket>/models/<version>/model.tar.gz.

Then creates/updates a SageMaker model, endpoint config, and endpoint.

Usage:
    # Deploy from a specific training job
    python scripts/deploy_sagemaker.py \\
        --training-job-name omnisql-finetune-20260512-101400 \\
        --version omnisql-pg-v2

    # Or use the latest training job automatically
    python scripts/deploy_sagemaker.py --version omnisql-pg-v2
"""

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

import boto3


REGION = "us-east-1"
ROLE_ARN = "arn:aws:iam::540659119855:role/omnisql-dev-sagemaker-role"
MODEL_BUCKET = "omnisql-dev-models-540659119855"
ENDPOINT_NAME = "omnisql-pg-endpoint"

INFERENCE_HANDLER = "scripts/inference/sagemaker_handler.py"
INFERENCE_REQUIREMENTS = "scripts/inference/requirements.txt"


def latest_training_job(sm_client) -> str:
    """Return the most recent omnisql-finetune-* training job name."""
    resp = sm_client.list_training_jobs(
        NameContains="omnisql-finetune-",
        StatusEquals="Completed",
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=1,
    )
    jobs = resp.get("TrainingJobSummaries", [])
    if not jobs:
        raise RuntimeError("No completed omnisql-finetune-* training jobs found.")
    return jobs[0]["TrainingJobName"]


def training_artifacts_s3_uri(sm_client, training_job_name: str) -> str:
    """Resolve the S3 URI of the model.tar.gz produced by a training job."""
    resp = sm_client.describe_training_job(TrainingJobName=training_job_name)
    if resp["TrainingJobStatus"] != "Completed":
        raise RuntimeError(
            f"Training job {training_job_name} is not Completed "
            f"(status: {resp['TrainingJobStatus']})"
        )
    return resp["ModelArtifacts"]["S3ModelArtifacts"]


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """s3://bucket/key/path → ('bucket', 'key/path')"""
    assert uri.startswith("s3://"), uri
    rest = uri[len("s3://"):]
    bucket, _, key = rest.partition("/")
    return bucket, key


def ensure_inference_requirements():
    """Write requirements.txt if missing."""
    os.makedirs("scripts/inference", exist_ok=True)
    if not os.path.exists(INFERENCE_HANDLER):
        raise RuntimeError(
            f"{INFERENCE_HANDLER} is missing! Create it before deploying."
        )
    with open(INFERENCE_REQUIREMENTS, "w") as f:
        f.write("tokenizers>=0.19.0\n")
        f.write("transformers==4.44.2\n")
        f.write("peft>=0.12.0\n")
        f.write("accelerate==0.34.2\n")


def repack_with_inference_code(
    s3_client,
    source_uri: str,
    version: str,
) -> str:
    """
    Download training artifacts from S3, add inference.py + requirements.txt,
    repack, and upload to s3://<model_bucket>/models/<version>/model.tar.gz.
    Returns the destination S3 URI.
    """
    src_bucket, src_key = parse_s3_uri(source_uri)

    workdir = Path("/tmp/model_repack")
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    # ── Download ─────────────────────────────────────────────────────────────
    src_tar = workdir / "src_model.tar.gz"
    print(f"[1/4] Downloading {source_uri}")
    s3_client.download_file(src_bucket, src_key, str(src_tar))

    # ── Extract ──────────────────────────────────────────────────────────────
    extract_dir = workdir / "extracted"
    extract_dir.mkdir()
    print(f"[2/4] Extracting to {extract_dir}")
    subprocess.check_call(["tar", "-xzf", str(src_tar), "-C", str(extract_dir)])

    # ── Inject inference code ────────────────────────────────────────────────
    print("[3/4] Adding inference.py + requirements.txt")
    shutil.copy(INFERENCE_HANDLER, extract_dir / "inference.py")
    shutil.copy(INFERENCE_REQUIREMENTS, extract_dir / "requirements.txt")

    # ── Repack and upload ────────────────────────────────────────────────────
    repacked = workdir / "model_with_code.tar.gz"
    with tarfile.open(repacked, "w:gz") as tar:
        for entry in extract_dir.iterdir():
            tar.add(str(entry), arcname=entry.name)

    dest_key = f"models/{version}/model.tar.gz"
    print(f"[4/4] Uploading to s3://{MODEL_BUCKET}/{dest_key}")
    s3_client.upload_file(str(repacked), MODEL_BUCKET, dest_key)

    return f"s3://{MODEL_BUCKET}/{dest_key}"


def deploy_endpoint(sm_client, model_data_url: str, version: str):
    """Create or update the SageMaker endpoint pointing to model_data_url."""
    image_uri = (
        f"763104351884.dkr.ecr.{REGION}.amazonaws.com/"
        f"huggingface-pytorch-inference:2.1.0-transformers4.37.0-gpu-py310-cu118-ubuntu20.04"
    )
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    model_name = f"{version}-{timestamp}"
    config_name = f"{version}-config-{timestamp}"

    print(f"Creating model: {model_name}")
    sm_client.create_model(
        ModelName=model_name,
        PrimaryContainer={
            "Image": image_uri,
            "ModelDataUrl": model_data_url,
            "Environment": {
                "SAGEMAKER_PROGRAM": "inference.py",
                "SAGEMAKER_CONTAINER_LOG_LEVEL": "20",
                "HUGGINGFACE_HUB_CACHE": "/tmp/hub_cache",
                "TS_DEFAULT_STARTUP_TIMEOUT": "600",
                "HF_TASK": "text-generation",
            },
        },
        ExecutionRoleArn=ROLE_ARN,
    )

    print(f"Creating endpoint config: {config_name}")
    sm_client.create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=[{
            "VariantName": "primary",
            "ModelName": model_name,
            "InstanceType": "ml.g5.2xlarge",
            "InitialInstanceCount": 1,
        }],
        AsyncInferenceConfig={
            "OutputConfig": {
                "S3OutputPath": f"s3://{MODEL_BUCKET}/inference-outputs/",
            },
        },
    )

    # ── Create or update endpoint ────────────────────────────────────────────
    try:
        sm_client.describe_endpoint(EndpointName=ENDPOINT_NAME)
        print(f"Endpoint {ENDPOINT_NAME} exists — updating to new config")
        sm_client.update_endpoint(
            EndpointName=ENDPOINT_NAME,
            EndpointConfigName=config_name,
        )
    except sm_client.exceptions.ClientError:
        print(f"Creating new endpoint: {ENDPOINT_NAME}")
        sm_client.create_endpoint(
            EndpointName=ENDPOINT_NAME,
            EndpointConfigName=config_name,
        )

    print()
    print("Endpoint deploying. Takes ~8-10 minutes.")
    print("Monitor with:")
    print(
        f"  aws sagemaker describe-endpoint --endpoint-name {ENDPOINT_NAME} "
        f"--region {REGION} --query 'EndpointStatus' --output text"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--training-job-name",
        help="SageMaker training job to deploy (default: latest completed job)",
    )
    parser.add_argument(
        "--version",
        default="omnisql-pg-v2",
        help="Version tag for the model (used in S3 path and SM model name)",
    )
    args = parser.parse_args()

    sm = boto3.client("sagemaker", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)

    job_name = args.training_job_name or latest_training_job(sm)
    print(f"Source training job: {job_name}")

    source_uri = training_artifacts_s3_uri(sm, job_name)
    print(f"Source artifacts:    {source_uri}")
    print(f"Target version:      {args.version}")
    print()

    ensure_inference_requirements()
    model_data_url = repack_with_inference_code(s3, source_uri, args.version)
    print()
    print(f"Deploying endpoint with model: {model_data_url}")
    print()
    deploy_endpoint(sm, model_data_url, args.version)


if __name__ == "__main__":
    main()