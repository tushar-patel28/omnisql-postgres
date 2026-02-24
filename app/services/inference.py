"""
Inference Service
-----------------
Handles model inference with three modes:

  mock      → deterministic fake SQL for development (Phase 1)
  local     → OmniSQL-7B loaded locally via HuggingFace Transformers
  sagemaker → OmniSQL-7B deployed on AWS SageMaker (Phase 3)

Switch modes via INFERENCE_MODE env var.
"""

import re
import structlog
from app.config import get_settings

log = structlog.get_logger()
settings = get_settings()


def extract_sql_from_response(response: str) -> tuple[str, str]:
    """
    Parse OmniSQL's response to extract SQL and explanation.

    OmniSQL wraps SQL in ```sql ... ``` blocks, with chain-of-thought
    reasoning before it.

    Returns:
        (sql, explanation) tuple
    """
    # Extract SQL from code block
    sql_pattern = r"```sql\s*(.*?)\s*```"
    match = re.search(sql_pattern, response, re.DOTALL | re.IGNORECASE)

    if match:
        sql = match.group(1).strip()
        # Everything before the SQL block is the CoT explanation
        explanation = response[:match.start()].strip()
        return sql, explanation

    # Fallback: try to find any SELECT/INSERT/UPDATE/DELETE statement
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
    
    # If we can't parse it, return the whole response as SQL
    return response.strip(), ""


# ── Mock Inference (Phase 1) ─────────────────────────────────────────────────

MOCK_RESPONSES = {
    "default": """Let me analyze the schema and construct the appropriate PostgreSQL query.

The question asks for a count of records with a time-based filter. I'll use DATE_TRUNC for PostgreSQL-compatible date handling.

```sql
SELECT COUNT(*) as total_count
FROM users
WHERE created_at >= DATE_TRUNC('month', NOW() - INTERVAL '1 month')
  AND created_at < DATE_TRUNC('month', NOW());
```""",

    "list": """I need to retrieve multiple records. I'll add a reasonable LIMIT for safety.

```sql
SELECT *
FROM users
ORDER BY created_at DESC
LIMIT 100;
```""",

    "aggregate": """This requires an aggregation. I'll use GROUP BY with an appropriate aggregate function.

```sql
SELECT 
    DATE_TRUNC('day', created_at) as date,
    COUNT(*) as count
FROM orders
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY date DESC;
```""",
}


def mock_inference(question: str, prompt: str) -> str:
    """Return a contextually appropriate mock SQL response."""
    q_lower = question.lower()

    if any(w in q_lower for w in ["how many", "count", "total number"]):
        return MOCK_RESPONSES["aggregate"]
    elif any(w in q_lower for w in ["list", "show", "get all", "find all"]):
        return MOCK_RESPONSES["list"]
    else:
        return MOCK_RESPONSES["default"]


# ── Local Inference (OmniSQL-7B) ─────────────────────────────────────────────

_local_model = None
_local_tokenizer = None


def load_local_model():
    """Load OmniSQL-7B locally. Called once on first use."""
    global _local_model, _local_tokenizer

    if _local_model is not None:
        return _local_model, _local_tokenizer

    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        log.info("Loading OmniSQL-7B locally", model_path=settings.model_path)

        _local_tokenizer = AutoTokenizer.from_pretrained(settings.model_path)
        _local_model = AutoModelForCausalLM.from_pretrained(
            settings.model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",  # handles Apple Silicon MPS automatically
        )

        log.info("OmniSQL-7B loaded successfully")
        return _local_model, _local_tokenizer

    except ImportError:
        raise RuntimeError(
            "torch and transformers are required for local inference. "
            "Uncomment them in requirements.txt and reinstall."
        )


def local_inference(prompt: str) -> str:
    """Run inference with locally loaded OmniSQL-7B."""
    import torch

    model, tokenizer = load_local_model()

    chat_prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        add_generation_prompt=True,
        tokenize=False,
    )

    inputs = tokenizer([chat_prompt], return_tensors="pt")
    inputs = inputs.to(model.device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            eos_token_id=tokenizer.eos_token_id,
            max_new_tokens=1024,
            temperature=0.0,       # greedy decoding for determinism
            do_sample=False,
        )

    input_len = len(inputs.input_ids[0])
    output_ids = output_ids[0][input_len:]
    response = tokenizer.batch_decode([output_ids], skip_special_tokens=True)[0]
    return response


# ── SageMaker Inference (Phase 3) ────────────────────────────────────────────

def sagemaker_inference(prompt: str) -> str:
    """
    Call OmniSQL-7B deployed on SageMaker async inference endpoint.
    Implemented in Phase 3.
    """
    try:
        import boto3
        import json
        import uuid

        client = boto3.client("sagemaker-runtime", region_name=settings.aws_region)

        # For async inference, submit to S3 input bucket and poll output
        # Full implementation in Phase 3
        raise NotImplementedError("SageMaker inference implemented in Phase 3")

    except ImportError:
        raise RuntimeError("boto3 required for SageMaker inference. pip install boto3")


# ── Public Interface ─────────────────────────────────────────────────────────

async def run_inference(question: str, prompt: str) -> tuple[str, str]:
    """
    Run inference in the configured mode.

    Returns:
        (sql, explanation) tuple
    """
    mode = settings.inference_mode
    log.info("Running inference", mode=mode, question=question[:60])

    if mode == "mock":
        raw_response = mock_inference(question, prompt)

    elif mode == "local":
        raw_response = local_inference(prompt)

    elif mode == "sagemaker":
        raw_response = sagemaker_inference(prompt)

    else:
        raise ValueError(f"Unknown INFERENCE_MODE: {mode}. Use mock | local | sagemaker")

    sql, explanation = extract_sql_from_response(raw_response)
    log.info("Inference complete", sql_preview=sql[:80])
    return sql, explanation
