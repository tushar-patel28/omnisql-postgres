import boto3
import json
from datetime import datetime

client = boto3.client("sagemaker", region_name="us-east-1")

job_name = f"omnisql-finetune-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
region = "us-east-1"

response = client.create_training_job(
    TrainingJobName=job_name,
    RoleArn="arn:aws:iam::540659119855:role/omnisql-dev-sagemaker-role",
    AlgorithmSpecification={
        "TrainingImage": f"763104351884.dkr.ecr.{region}.amazonaws.com/pytorch-training:2.1.0-gpu-py310-cu121-ubuntu20.04-sagemaker",
        "TrainingInputMode": "File",
    },
    InputDataConfig=[
        {
            "ChannelName": "train",
            "DataSource": {
                "S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri": "s3://omnisql-dev-datasets-540659119855/",
                    "S3DataDistributionType": "FullyReplicated",
                }
            },
        }
    ],
    OutputDataConfig={
        "S3OutputPath": "s3://omnisql-dev-models-540659119855/training-output/"
    },
    ResourceConfig={
        "InstanceType": "ml.g5.2xlarge",
        "InstanceCount": 1,
        "VolumeSizeInGB": 100,
    },
    StoppingCondition={"MaxRuntimeInSeconds": 36000},
    HyperParameters={
        "sagemaker_program": json.dumps("setup.sh"),
        "sagemaker_submit_directory": json.dumps("s3://omnisql-dev-datasets-540659119855/code/sourcedir.tar.gz"),
    },
    Environment={
        "HUGGINGFACE_HUB_CACHE": "/tmp/hub_cache",
    },
)

print(f"Training job launched: {job_name}")
print(f"Status: {response['ResponseMetadata']['HTTPStatusCode']}")
print(f"Monitor: https://console.aws.amazon.com/sagemaker/home#/jobs/{job_name}")