"""
SageMaker Inference Handler — BASELINE MODE (no LoRA adapter)
---------------------------------------------------------------
Zero-shot OmniSQL-7B inference. Used to measure the lift from
fine-tuning under matched decoding settings.

Identical to sagemaker_handler.py except this skips
PeftModel.from_pretrained() — the model is the raw base.

Decoding parameters configurable per-request:
  - num_beams (default 4): beam search width. 1 = greedy.
  - max_new_tokens (default 256): generation length cap.
"""

import os
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

model = None
tokenizer = None


def model_fn(model_dir, context=None):
    global model, tokenizer

    base_model_name = "seeklhy/OmniSQL-7B"

    # Use the base model's own tokenizer (no LoRA artifacts present)
    tokenizer = AutoTokenizer.from_pretrained(
        base_model_name,
        trust_remote_code=True,
        use_fast=False,
        cache_dir="/tmp/hub_cache",
    )
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.bfloat16,  # NOT fp16 — fixes Qwen2 numerical issues
        device_map="auto",
        trust_remote_code=True,
        cache_dir="/tmp/hub_cache",
    )
    model.eval()
    print("Loaded BASELINE OmniSQL-7B (no LoRA adapter) in bfloat16")
    return model


def predict_fn(data, model):
    prompt = data.get("prompt", "")
    max_new_tokens = data.get("max_new_tokens", 256)
    num_beams = data.get("num_beams", 4)

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    generation_kwargs = {
        "max_new_tokens": max_new_tokens,
        "pad_token_id": tokenizer.eos_token_id,
        "num_beams": num_beams,
        "do_sample": False,
    }
    if num_beams > 1:
        generation_kwargs["early_stopping"] = True
        generation_kwargs["no_repeat_ngram_size"] = 0

    with torch.no_grad():
        outputs = model.generate(**inputs, **generation_kwargs)

    generated = outputs[0][inputs["input_ids"].shape[1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    print(f"DEBUG baseline num_beams={num_beams}, generated_len={len(generated)}")
    print(f"DEBUG Decoded text[:200]: {repr(text[:200])}")
    return {"generated_text": text}


def input_fn(request_body, content_type="application/json"):
    return json.loads(request_body)


def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction)