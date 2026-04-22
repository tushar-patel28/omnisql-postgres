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

# ── Tokenize upfront — no dataset.map() ───────────────────────────────────────
print("Tokenizing dataset...")
all_input_ids = []
all_attention_masks = []
all_labels = []

for r in records:
    text = (
        f"### Schema:\n{r['schema_ddl']}\n\n"
        f"### Question:\n{r['question']}\n\n"
        f"### SQL:\n{r['sql']}"
    )
    enc = tokenizer(
        text,
        truncation=True,
        max_length=512,
        padding="max_length",
    )
    all_input_ids.append(enc["input_ids"])
    all_attention_masks.append(enc["attention_mask"])
    all_labels.append(enc["input_ids"].copy())

tokenized_dataset = Dataset.from_dict({
    "input_ids": all_input_ids,
    "attention_mask": all_attention_masks,
    "labels": all_labels,
})
print(f"Tokenized dataset: {len(tokenized_dataset)} examples")

# ── Training args ─────────────────────────────────────────────────────────────
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    learning_rate=2e-4,              
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