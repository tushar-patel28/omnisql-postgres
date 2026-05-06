"""
Inference Service
-----------------
Handles model inference: mock | local | sagemaker.
"""

import re
import structlog
from app.config import get_settings

log = structlog.get_logger()
settings = get_settings()


def extract_sql_from_response(response: str) -> tuple[str, str]:
    sql_pattern = r"```sql\s*(.*?)\s*```"
    match = re.search(sql_pattern, response, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip(), response[:match.start()].strip()

    sql_keywords = r"\b(SELECT|INSERT|UPDATE|DELETE|WITH|CREATE)\b"
    lines = response.split("\n")
    sql_lines = []
    in_sql = False
    for line in lines:
        if re.search(sql_keywords, line, re.IGNORECASE) and not in_sql:
            in_sql = True
        if in_sql:
            sql_lines.append(line)
    if sql_lines:
        return "\n".join(sql_lines).strip(), response
    return response.strip(), ""


def mock_inference(question: str, prompt: str) -> str:
    return "```sql\nSELECT COUNT(*) FROM users;\n```"


_local_model = None
_local_tokenizer = None


def load_local_model():
    global _local_model, _local_tokenizer
    if _local_model is not None:
        return _local_model, _local_tokenizer
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    log.info("Loading OmniSQL-7B locally", model_path=settings.model_path)
    _local_tokenizer = AutoTokenizer.from_pretrained(settings.model_path)
    _local_model = AutoModelForCausalLM.from_pretrained(
        settings.model_path, torch_dtype=torch.bfloat16, device_map="auto",
    )
    return _local_model, _local_tokenizer


def local_inference(prompt: str) -> str:
    import torch
    model, tokenizer = load_local_model()
    chat_prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        add_generation_prompt=True, tokenize=False,
    )
    inputs = tokenizer([chat_prompt], return_tensors="pt").to(model.device)
    with torch.no_grad():
        output_ids = model.generate(
            **inputs, eos_token_id=tokenizer.eos_token_id,
            max_new_tokens=1024, temperature=0.0, do_sample=False,
        )
    input_len = len(inputs.input_ids[0])
    output_ids = output_ids[0][input_len:]
    return tokenizer.batch_decode([output_ids], skip_special_tokens=True)[0]


def sagemaker_inference(prompt: str) -> str:
    import boto3, json, time, uuid

    bucket = "omnisql-dev-models-540659119855"
    region = settings.aws_region
    endpoint = settings.sagemaker_endpoint_name

    sm_runtime = boto3.client("sagemaker-runtime", region_name=region)
    s3 = boto3.client("s3", region_name=region)

    request_id = uuid.uuid4().hex[:12]
    input_key = f"inference-inputs/eval_{request_id}.json"
    input_data = json.dumps({"prompt": prompt, "max_new_tokens": 256})
    s3.put_object(Bucket=bucket, Key=input_key, Body=input_data)

    response = sm_runtime.invoke_endpoint_async(
        EndpointName=endpoint,
        ContentType="application/json",
        InputLocation=f"s3://{bucket}/{input_key}",
    )
    output_key = response["OutputLocation"].replace(f"s3://{bucket}/", "")

    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            resp = s3.get_object(Bucket=bucket, Key=output_key)
            return json.loads(resp["Body"].read())["generated_text"]
        except Exception:
            time.sleep(3)
    raise RuntimeError("SageMaker inference timed out after 5 minutes")


async def run_inference(question: str, prompt: str) -> tuple[str, str]:
    mode = settings.inference_mode
    log.info("Running inference", mode=mode, question=question[:60])
    if mode == "mock":
        raw_response = mock_inference(question, prompt)
    elif mode == "local":
        raw_response = local_inference(prompt)
    elif mode == "sagemaker":
        raw_response = sagemaker_inference(prompt)
    else:
        raise ValueError(f"Unknown INFERENCE_MODE: {mode}")
    sql, explanation = extract_sql_from_response(raw_response)
    log.info("Inference complete", sql_preview=sql[:80])
    return sql, explanation
