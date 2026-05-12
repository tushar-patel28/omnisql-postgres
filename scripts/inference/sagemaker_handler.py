"""
SageMaker Inference Handler — FINE-TUNED MODE (with LoRA adapter)
------------------------------------------------------------------
This file runs INSIDE the SageMaker GPU container.
Loads OmniSQL-7B base model + applies the trained LoRA adapter.

Critical fixes baked in:
  - bf16 (NOT fp16) — fixes Qwen2 numerical issues that produced
    token 0 (`!`) contamination during inference.
  - adapter_config.json patched to remove keys that older peft rejects.
  - tokenizer uses use_fast=False (container's Rust tokenizers too old).

Decoding parameters configurable per-request:
  - num_beams (default 4): beam search width. 1 = greedy.
  - max_new_tokens (default 256): generation length cap.

For SQL generation we use beam search by default (num_beams=4) since
structured outputs benefit from being able to back out of bad early
tokens. Set num_beams=1 in the request to force greedy.
"""

import os
import json
import shutil
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

model = None
tokenizer = None


def model_fn(model_dir, context=None):
    global model, tokenizer

    base_model_name = "seeklhy/OmniSQL-7B"

    # /opt/ml/model is read-only — copy to /tmp so we can patch adapter_config.json
    tmp_model_dir = "/tmp/peft_model"
    if os.path.exists(tmp_model_dir):
        shutil.rmtree(tmp_model_dir)
    shutil.copytree(model_dir, tmp_model_dir)

    # Patch adapter_config.json to remove keys that older peft doesn't accept
    config_path = os.path.join(tmp_model_dir, "adapter_config.json")
    with open(config_path) as f:
        adapter_config = json.load(f)
    for key in [
        "layer_replication",
        "use_dora",
        "use_rslora",
        "rank_pattern",
        "alpha_pattern",
    ]:
        adapter_config.pop(key, None)
    with open(config_path, "w") as f:
        json.dump(adapter_config, f)
    print("Patched adapter_config.json successfully")

    tokenizer = AutoTokenizer.from_pretrained(
        tmp_model_dir,
        trust_remote_code=True,
        use_fast=False,
    )
    tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.bfloat16,  # NOT fp16 — fixes Qwen2 numerical issues
        device_map="auto",
        trust_remote_code=True,
        cache_dir="/tmp/hub_cache",
    )

    # FINE-TUNED MODE: apply trained LoRA adapter
    model = PeftModel.from_pretrained(base_model, tmp_model_dir)
    model.eval()
    print("Loaded with LoRA adapter in bfloat16")

    return model


def predict_fn(data, model):
    prompt = data.get("prompt", "")
    max_new_tokens = data.get("max_new_tokens", 256)
    num_beams = data.get("num_beams", 4)  # beam search by default

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    generation_kwargs = {
        "max_new_tokens": max_new_tokens,
        "pad_token_id": tokenizer.eos_token_id,
        "num_beams": num_beams,
        "do_sample": False,  # deterministic
    }
    if num_beams > 1:
        # Standard beam search settings for structured output
        generation_kwargs["early_stopping"] = True
        generation_kwargs["no_repeat_ngram_size"] = 0  # SQL legitimately repeats tokens

    with torch.no_grad():
        outputs = model.generate(**inputs, **generation_kwargs)

    generated = outputs[0][inputs["input_ids"].shape[1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    print(f"DEBUG num_beams={num_beams}, generated_len={len(generated)}")
    print(f"DEBUG Decoded text[:200]: {repr(text[:200])}")
    return {"generated_text": text}


def input_fn(request_body, content_type="application/json"):
    return json.loads(request_body)


def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction)