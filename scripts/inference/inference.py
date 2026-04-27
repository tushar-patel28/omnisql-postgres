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

    # ── Copy model dir to /tmp so we can patch adapter_config.json ────────────
    tmp_model_dir = "/tmp/peft_model"
    if os.path.exists(tmp_model_dir):
        shutil.rmtree(tmp_model_dir)
    shutil.copytree(model_dir, tmp_model_dir)

    # ── Patch adapter_config.json to remove unsupported keys ──────────────────
    config_path = os.path.join(tmp_model_dir, "adapter_config.json")
    with open(config_path) as f:
        adapter_config = json.load(f)
    for key in ["layer_replication", "use_dora", "use_rslora", "rank_pattern", "alpha_pattern"]:
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
        torch_dtype=torch.bfloat16,   # ← CHANGED from float16 — fixes Qwen2 numerical issues
        device_map="auto",
        trust_remote_code=True,
        cache_dir="/tmp/hub_cache",
    )

    model = PeftModel.from_pretrained(base_model, tmp_model_dir)
    model.eval()
    print("Loaded with LoRA adapter in bfloat16")

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
    text = tokenizer.decode(generated, skip_special_tokens=True)
    print(f"DEBUG Generated token IDs: {generated.tolist()[:30]}")
    print(f"DEBUG Decoded text: {repr(text)}")
    return {"generated_text": text}

def input_fn(request_body, content_type="application/json"):
    return json.loads(request_body)

def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction)