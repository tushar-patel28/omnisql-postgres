#!/bin/bash
pip install -q \
    "tokenizers>=0.19.0" \
    "transformers==4.44.2" \
    "peft==0.12.0" \
    "bitsandbytes==0.43.3" \
    "accelerate==0.34.2" \
    "datasets==2.21.0"

python train.py