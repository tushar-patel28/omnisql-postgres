"""
SageMaker Inference Handler — FINE-TUNED MODE (with LoRA adapter)
------------------------------------------------------------------
Supports two decoding modes, configurable per request:

  - Beam search (default): num_beams=4, deterministic, used for primary eval.
  - Sampling: do_sample=True with temperature, used for Maj@K voting.

Request payload knobs:
  - prompt          : str (required)
  - max_new_tokens  : int (default 256)
  - num_beams       : int (default 4)
  - do_sample       : bool (default False)
  - temperature     : float (default 1.0; only used when do_sample=True)
  - top_p           : float (default 0.95; only used when do_sample=True)
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

    tmp_model_dir = "/tmp/peft_model"
    if os.path.exists(tmp_model_dir):
        shutil.rmtree(tmp_model_dir)
    shutil.copytree(model_dir, tmp_model_dir)

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
        torch_dtype=torch.bfloat16,
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
    do_sample = bool(data.get("do_sample", False))
    num_beams = int(data.get("num_beams", 4))
    temperature = float(data.get("temperature", 1.0))
    top_p = float(data.get("top_p", 0.95))

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    generation_kwargs = {
        "max_new_tokens": max_new_tokens,
        "pad_token_id": tokenizer.eos_token_id,
    }

    if do_sample:
        generation_kwargs.update({
            "do_sample": True,
            "temperature": temperature,
            "top_p": top_p,
            "num_beams": 1,
        })
    else:
        generation_kwargs.update({
            "do_sample": False,
            "num_beams": num_beams,
        })
        if num_beams > 1:
            generation_kwargs["early_stopping"] = True
            generation_kwargs["no_repeat_ngram_size"] = 0

    with torch.no_grad():
        outputs = model.generate(**inputs, **generation_kwargs)

    generated = outputs[0][inputs["input_ids"].shape[1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    print(
        f"DEBUG do_sample={do_sample}, num_beams={num_beams}, "
        f"temp={temperature}, top_p={top_p}, gen_len={len(generated)}"
    )
    print(f"DEBUG Decoded text[:200]: {repr(text[:200])}")
    return {"generated_text": text}


def input_fn(request_body, content_type="application/json"):
    return json.loads(request_body)


def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction)