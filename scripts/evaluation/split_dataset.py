"""
scripts/evaluation/split_dataset.py
--------------------------------------
Splits pg_train.jsonl into train and test sets.

- Test set: 200 pairs (10%), stratified by schema and complexity
- Train set: 1800 pairs (90%)

Stratified split ensures test set covers all schemas and complexity
levels proportionally — critical for meaningful evaluation.

Usage:
    python scripts/evaluation/split_dataset.py
"""

import json
import random
from pathlib import Path
from collections import defaultdict
import structlog

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()

INPUT_PATH = "data/synthetic/pg_train.jsonl"
TRAIN_PATH = "data/synthetic/pg_finetune.jsonl"
TEST_PATH  = "data/synthetic/pg_test.jsonl"
TEST_SIZE  = 200
SEED       = 42


def stratified_split(pairs: list[dict], test_size: int, seed: int) -> tuple[list, list]:
    """
    Stratified split by schema_name + complexity combination.
    Ensures test set covers all domains and complexity levels evenly.
    """
    random.seed(seed)

    # Group by stratum
    strata = defaultdict(list)
    for pair in pairs:
        key = f"{pair['schema_name']}_{pair['complexity']}"
        strata[key].append(pair)

    test_pairs = []
    train_pairs = []

    # Calculate how many to pull from each stratum
    total = len(pairs)
    for key, group in strata.items():
        random.shuffle(group)
        n_test = max(1, round(len(group) / total * test_size))
        test_pairs.extend(group[:n_test])
        train_pairs.extend(group[n_test:])

    # Trim to exact test_size if rounding pushed us over
    random.shuffle(test_pairs)
    if len(test_pairs) > test_size:
        train_pairs.extend(test_pairs[test_size:])
        test_pairs = test_pairs[:test_size]

    random.shuffle(train_pairs)
    return train_pairs, test_pairs


def main():
    input_file = Path(INPUT_PATH)
    if not input_file.exists():
        log.error("Input file not found", path=INPUT_PATH)
        sys.exit(1)

    pairs = [json.loads(l) for l in open(input_file) if l.strip()]
    log.info("Loaded dataset", total=len(pairs))

    train_pairs, test_pairs = stratified_split(pairs, TEST_SIZE, SEED)

    # Save splits
    with open(TRAIN_PATH, "w") as f:
        for p in train_pairs:
            f.write(json.dumps(p) + "\n")

    with open(TEST_PATH, "w") as f:
        for p in test_pairs:
            f.write(json.dumps(p) + "\n")

    # Report
    from collections import Counter
    train_schemas = Counter(p["schema_name"] for p in train_pairs)
    test_schemas  = Counter(p["schema_name"] for p in test_pairs)
    train_complex = Counter(p["complexity"] for p in train_pairs)
    test_complex  = Counter(p["complexity"] for p in test_pairs)

    log.info("Split complete")
    log.info(f"  Train: {len(train_pairs)} pairs → {TRAIN_PATH}")
    log.info(f"  Test:  {len(test_pairs)} pairs  → {TEST_PATH}")
    log.info(f"  Train schemas: {dict(train_schemas)}")
    log.info(f"  Test schemas:  {dict(test_schemas)}")
    log.info(f"  Train complexity: {dict(train_complex)}")
    log.info(f"  Test complexity:  {dict(test_complex)}")


if __name__ == "__main__":
    main()