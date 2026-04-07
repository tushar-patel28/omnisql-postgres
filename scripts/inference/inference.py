
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
