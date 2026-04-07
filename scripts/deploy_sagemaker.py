import boto3
import json
import tarfile
import os
import sagemaker
from datetime import datetime

region = "us-east-1"
account_id = "540659119855"
role_arn = "arn:aws:iam::540659119855:role/omnisql-dev-sagemaker-role"
model_bucket = "omnisql-dev-models-540659119855"
endpoint_name = "omnisql-pg-endpoint"

client = boto3.client("sagemaker", region_name=region)

# ── Create inference script package ───────────────────────────────────────────
os.makedirs("scripts/inference", exist_ok=True)

inference_code = '''
import os
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

model = None
tokenizer = None

def model_fn(model_dir):
    global model, tokenizer

    base_model_name = "seeklhy/OmniSQL-7B"

    tokenizer = AutoTokenizer.from_pretrained(
        model_dir,
        trust_remote_code=True,
        use_fast=False,
    )
    tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
        cache_dir="/tmp/hub_cache",
    )

    model = PeftModel.from_pretrained(base_model, model_dir)
    model.eval()

    return model

def predict_fn(data, model):
    prompt = data.get("prompt", "")
    max_new_tokens = data.get("max_new_tokens", 256)

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated = outputs[0][inputs["input_ids"].shape[1]:]
    return {"generated_text": tokenizer.decode(generated, skip_special_tokens=True)}

def input_fn(request_body, content_type="application/json"):
    return json.loads(request_body)

def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction)
'''

with open("scripts/inference/inference.py", "w") as f:
    f.write(inference_code)

with open("scripts/inference/requirements.txt", "w") as f:
    f.write("peft==0.12.0\n")
    f.write("accelerate==0.34.2\n")

print("Inference scripts created")

# ── Package and upload inference code ─────────────────────────────────────────
with tarfile.open("scripts/inference/sourcedir.tar.gz", "w:gz") as tar:
    tar.add("scripts/inference/inference.py", arcname="inference.py")
    tar.add("scripts/inference/requirements.txt", arcname="requirements.txt")

s3 = boto3.client("s3", region_name=region)
s3.upload_file(
    "scripts/inference/sourcedir.tar.gz",
    model_bucket,
    "inference/sourcedir.tar.gz",
)
print("Inference code uploaded to S3")

# ── Model artifacts already in S3 ─────────────────────────────────────────────
print("Model artifacts ready at s3://omnisql-dev-models-540659119855/models/omnisql-pg-v1/model.tar.gz")

# ── Use verified correct image URI ────────────────────────────────────────────
image_uri = f"763104351884.dkr.ecr.{region}.amazonaws.com/pytorch-inference:2.1.0-gpu-py310-cu118-ubuntu20.04-sagemaker"
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
            "SAGEMAKER_SUBMIT_DIRECTORY": f"s3://{model_bucket}/inference/sourcedir.tar.gz",
            "SAGEMAKER_CONTAINER_LOG_LEVEL": "20",
            "HUGGINGFACE_HUB_CACHE": "/tmp/hub_cache",
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