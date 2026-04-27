import os
import json
import torch
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    BitsAndBytesConfig,
)
from transformers import default_data_collator
from peft import LoraConfig, get_peft_model, TaskType

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR   = os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train")
MODEL_DIR  = os.environ.get("SM_MODEL_DIR", "/opt/ml/model")
OUTPUT_DIR = os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data")

# ── Load dataset ──────────────────────────────────────────────────────────────
def load_jsonl(path):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records

data_path = os.path.join(DATA_DIR, "pg_finetune.jsonl")
records = load_jsonl(data_path)
print(f"Loaded {len(records)} training examples")

# ── Model & tokenizer ─────────────────────────────────────────────────────────
MODEL_NAME = "seeklhy/OmniSQL-7B"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
)

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
    cache_dir="/tmp/hub_cache",
    use_fast=False,
)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
    cache_dir="/tmp/hub_cache",
)
model.config.use_cache = False

# ── LoRA config ───────────────────────────────────────────────────────────────
lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    bias="none",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ── Tokenize with prompt masking ──────────────────────────────────────────────
# Only train on the SQL answer portion — mask schema+question tokens with -100
print("Tokenizing dataset with prompt masking...")
all_input_ids = []
all_attention_masks = []
all_labels = []

MAX_LENGTH = 512

for r in records:
    prompt = (
        f"### Schema:\n{r['schema_ddl']}\n\n"
        f"### Question:\n{r['question']}\n\n"
        f"### SQL:\n"
    )
    answer = r['sql']
    full_text = prompt + answer

    # Tokenize prompt and full text — both WITHOUT special tokens for accurate boundary alignment
    prompt_tokens = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    full_tokens = tokenizer(
        full_text,
        truncation=True,
        max_length=MAX_LENGTH,
        padding="max_length",
        add_special_tokens=False,   # ← FIX: prevents boundary misalignment that caused token 0 artifacts
    )

    input_ids = full_tokens["input_ids"]
    attention_mask = full_tokens["attention_mask"]

    # Build labels: -100 for prompt tokens, actual ids for answer tokens, -100 for padding
    labels = input_ids.copy()
    prompt_len = len(prompt_tokens)

    # Mask prompt portion
    for i in range(min(prompt_len, MAX_LENGTH)):
        labels[i] = -100

    # Mask padding (where attention_mask is 0)
    for i in range(MAX_LENGTH):
        if attention_mask[i] == 0:
            labels[i] = -100

    all_input_ids.append(input_ids)
    all_attention_masks.append(attention_mask)
    all_labels.append(labels)

tokenized_dataset = Dataset.from_dict({
    "input_ids": all_input_ids,
    "attention_mask": all_attention_masks,
    "labels": all_labels,
})
print(f"Tokenized dataset: {len(tokenized_dataset)} examples")

# Verify masking worked — at least some labels should be -100
sample_labels = all_labels[0]
n_masked = sum(1 for l in sample_labels if l == -100)
n_train = sum(1 for l in sample_labels if l != -100)
print(f"Sample 0: {n_masked} masked tokens, {n_train} training tokens")

# ── Training args ─────────────────────────────────────────────────────────────
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=1,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    learning_rate=1e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    max_grad_norm=1.0,
    bf16=True,
    fp16=False,
    logging_steps=10,
    save_strategy="epoch",
    report_to="none",
    dataloader_pin_memory=False,
)

# ── Trainer ───────────────────────────────────────────────────────────────────
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset,
    data_collator=default_data_collator,
)

print("Starting fine-tuning...")
trainer.train()

# ── Save model ────────────────────────────────────────────────────────────────
print(f"Saving model to {MODEL_DIR}")
trainer.save_model(MODEL_DIR)
tokenizer.save_pretrained(MODEL_DIR)
print("Training complete!")