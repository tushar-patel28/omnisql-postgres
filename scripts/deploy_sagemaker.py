import boto3
import tarfile
import os
import subprocess
from datetime import datetime

region = "us-east-1"
role_arn = "arn:aws:iam::540659119855:role/omnisql-dev-sagemaker-role"
model_bucket = "omnisql-dev-models-540659119855"
endpoint_name = "omnisql-pg-endpoint"

client = boto3.client("sagemaker", region_name=region)
s3 = boto3.client("s3", region_name=region)

# ── Write inference.py ────────────────────────────────────────────────────────
os.makedirs("scripts/inference", exist_ok=True)

# inference.py is already at scripts/inference/inference.py — just verify it exists
if not os.path.exists("scripts/inference/inference.py") or os.path.getsize("scripts/inference/inference.py") == 0:
    raise RuntimeError("scripts/inference/inference.py is missing or empty! Please create it first.")

print(f"inference.py verified ({os.path.getsize('scripts/inference/inference.py')} bytes)")

# ── Write requirements.txt ────────────────────────────────────────────────────
with open("scripts/inference/requirements.txt", "w") as f:
    f.write("tokenizers>=0.19.0\n")
    f.write("transformers==4.44.2\n")
    f.write("peft>=0.12.0\n")
    f.write("accelerate==0.34.2\n")

print("requirements.txt written")

# ── Repack model.tar.gz to include inference.py + requirements.txt ────────────
print("Repacking model with inference.py and requirements.txt...")
repack_dir = "/tmp/model_repack"

# Clean and recreate repack dir
subprocess.check_call(["rm", "-rf", repack_dir])
os.makedirs(repack_dir, exist_ok=True)

# Extract existing model
subprocess.check_call([
    "tar", "-xzf",
    os.path.expanduser("~/omnisql-model/model.tar.gz"),
    "-C", repack_dir
])

# Copy inference.py and requirements.txt into model dir
subprocess.check_call(["cp", "scripts/inference/inference.py", repack_dir])
subprocess.check_call(["cp", "scripts/inference/requirements.txt", repack_dir])

# Repack
repacked_path = os.path.expanduser("~/omnisql-model/model_with_code.tar.gz")
with tarfile.open(repacked_path, "w:gz") as tar:
    for f in os.listdir(repack_dir):
        tar.add(os.path.join(repack_dir, f), arcname=f)

print(f"Repacked model: {repacked_path}")

# ── Upload repacked model to S3 ───────────────────────────────────────────────
print("Uploading repacked model to S3...")
s3.upload_file(repacked_path, model_bucket, "models/omnisql-pg-v1/model.tar.gz")
print("Model uploaded")

# ── Use HuggingFace inference container ───────────────────────────────────────
image_uri = f"763104351884.dkr.ecr.{region}.amazonaws.com/huggingface-pytorch-inference:2.1.0-transformers4.37.0-gpu-py310-cu118-ubuntu20.04"
print(f"Using image: {image_uri}")

# ── Create SageMaker model ────────────────────────────────────────────────────
model_name = f"omnisql-pg-v1-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

client.create_model(
    ModelName=model_name,
    PrimaryContainer={
        "Image": image_uri,
        "ModelDataUrl": f"s3://{model_bucket}/models/omnisql-pg-v1/model.tar.gz",
        "Environment": {
            "SAGEMAKER_PROGRAM": "inference.py",
            "SAGEMAKER_CONTAINER_LOG_LEVEL": "20",
            "HUGGINGFACE_HUB_CACHE": "/tmp/hub_cache",
            "TS_DEFAULT_STARTUP_TIMEOUT": "600",
            "HF_TASK": "text-generation",
        },
    },
    ExecutionRoleArn=role_arn,
)
print(f"Model created: {model_name}")

# ── Create endpoint config ────────────────────────────────────────────────────
config_name = f"omnisql-pg-config-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

client.create_endpoint_config(
    EndpointConfigName=config_name,
    ProductionVariants=[{
        "VariantName": "primary",
        "ModelName": model_name,
        "InstanceType": "ml.g5.2xlarge",
        "InitialInstanceCount": 1,
    }],
    AsyncInferenceConfig={
        "OutputConfig": {
            "S3OutputPath": f"s3://{model_bucket}/inference-outputs/",
        },
    },
)
print(f"Endpoint config created: {config_name}")

# ── Create endpoint ───────────────────────────────────────────────────────────
client.create_endpoint(
    EndpointName=endpoint_name,
    EndpointConfigName=config_name,
)
print(f"Endpoint deploying: {endpoint_name}")
print("This takes ~10 minutes. Monitor with:")
print(f"aws sagemaker describe-endpoint --endpoint-name {endpoint_name} --region {region} --query 'EndpointStatus'")