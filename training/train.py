#!/usr/bin/env python3
"""Fine-tune Gemma 3 270M for command correction.

Loads augmented training data and fine-tunes google/gemma-3-270m-pt using
the HuggingFace Trainer API. This is a full fine-tune (not LoRA) since the
model is small enough at 270M parameters.

Training data format (per line in JSONL):
    {"command": "...", "stderr": "...", "op": "..."}

Model input format:
    $ {command}
    > {stderr}
    OP: {op}
"""

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)


def format_example(example: dict) -> str:
    """Format a training example into the prompt format the model will learn.

    Format:
        $ {command}
        > {stderr}
        OP: REPLACE old new
    """
    parts = [f"$ {example['command']}"]
    if example.get("stderr"):
        stderr = example["stderr"]
        if len(stderr) > 512:
            stderr = stderr[:512] + "..."
        for line in stderr.splitlines():
            parts.append(f"> {line}")

    parts.append(f"OP: {example['op']}")

    return "\n".join(parts)


def load_training_data(data_path: Path) -> list[dict]:
    """Load JSONL training data."""
    examples = []
    with open(data_path) as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def tokenize_dataset(
    examples: list[dict], tokenizer, max_length: int
) -> Dataset:
    """Tokenize training examples into a HuggingFace Dataset.

    Each example is formatted into the prompt format and tokenized.
    Labels are masked (-100) for the prompt portion so the model only learns
    to predict the operation after 'OP: ', not the prompt itself.
    """
    all_input_ids = []
    all_attention_mask = []
    all_labels = []

    for ex in examples:
        # Build prompt and completion separately
        parts = [f"$ {ex['command']}"]
        if ex.get("stderr"):
            stderr = ex["stderr"]
            if len(stderr) > 512:
                stderr = stderr[:512] + "..."
            for line in stderr.splitlines():
                parts.append(f"> {line}")

        parts.append("OP: ")
        completion_text = ex["op"] + tokenizer.eos_token

        prompt_text = "\n".join(parts)

        # Tokenize prompt and completion SEPARATELY to avoid
        # tokenizer merging tokens across the boundary
        prompt_tok = tokenizer(
            prompt_text,
            truncation=True,
            max_length=max_length,
            padding=False,
            add_special_tokens=False,
        )
        completion_tok = tokenizer(
            completion_text,
            truncation=True,
            max_length=max_length - len(prompt_tok["input_ids"]),
            padding=False,
            add_special_tokens=False,
        )

        prompt_ids = prompt_tok["input_ids"]
        completion_ids = completion_tok["input_ids"]
        input_ids = prompt_ids + completion_ids
        attention_mask = [1] * len(input_ids)
        prompt_len = len(prompt_ids)

        # Labels: -100 for prompt tokens (ignored in loss), input_ids for completion
        labels = [-100] * prompt_len + completion_ids

        all_input_ids.append(input_ids)
        all_attention_mask.append(attention_mask)
        all_labels.append(labels)

    return Dataset.from_dict({
        "input_ids": all_input_ids,
        "attention_mask": all_attention_mask,
        "labels": all_labels,
    })


def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune Gemma 3 270M for command correction"
    )
    parser.add_argument(
        "-d",
        "--data",
        type=Path,
        default=Path("data/train_ops.jsonl"),
        help="Training data JSONL file (default: data/train_ops.jsonl)",
    )
    parser.add_argument(
        "--eval-data",
        type=Path,
        default=Path("data/test_ops.jsonl"),
        help="Evaluation data JSONL file (default: data/test_ops.jsonl)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("checkpoints"),
        help="Output directory for model checkpoints (default: checkpoints)",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="google/gemma-3-270m",
        help="HuggingFace model name (default: google/gemma-3-270m)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs (default: 3)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Training batch size (default: 8)",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=5e-5,
        help="Learning rate (default: 5e-5)",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=256,
        help="Max sequence length in tokens (default: 256)",
    )
    parser.add_argument(
        "--warmup-ratio",
        type=float,
        default=0.1,
        help="Warmup ratio for learning rate scheduler (default: 0.1)",
    )
    # Kept for backward compat but ignored when --eval-data is provided
    parser.add_argument(
        "--eval-split",
        type=float,
        default=0.1,
        help="(ignored when --eval-data is set) Fraction of data for eval",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--bf16",
        action="store_true",
        help="Use bfloat16 training (recommended for modern GPUs)",
    )
    parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=1,
        help="Gradient accumulation steps (default: 1)",
    )
    args = parser.parse_args()

    if not args.data.exists():
        print(f"Error: training data file {args.data} not found")
        print("Run generate_data.py and augment.py first.")
        raise SystemExit(1)

    # Load data
    print(f"Loading training data from {args.data}...")
    train_examples = load_training_data(args.data)
    print(f"Loaded {len(train_examples)} training examples")

    eval_examples = []
    if args.eval_data and args.eval_data.exists():
        print(f"Loading eval data from {args.eval_data}...")
        eval_examples = load_training_data(args.eval_data)
        print(f"Loaded {len(eval_examples)} eval examples")

    # Load tokenizer and model
    print(f"Loading model {args.model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)

    # Gemma may not have a pad token set
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        dtype=torch.bfloat16 if args.bf16 else torch.float32,
    )

    print(f"Model parameters: {model.num_parameters():,}")

    # Tokenize
    print("Tokenizing datasets...")
    train_dataset = tokenize_dataset(train_examples, tokenizer, args.max_length)
    eval_dataset = tokenize_dataset(eval_examples, tokenizer, args.max_length) if eval_examples else None
    print(f"Train: {len(train_dataset)} examples" + (f", Eval: {len(eval_dataset)} examples" if eval_dataset else ""))

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        weight_decay=0.01,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        bf16=args.bf16,
        seed=args.seed,
        report_to="none",  # Disable wandb etc. by default
        dataloader_pin_memory=True,
    )

    # Custom data collator that pads input_ids, attention_mask, and labels
    # Labels are padded with -100 (ignored in cross-entropy loss)
    def data_collator(features):
        max_len = max(len(f["input_ids"]) for f in features)
        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for f in features:
            pad_len = max_len - len(f["input_ids"])
            batch["input_ids"].append(f["input_ids"] + [tokenizer.pad_token_id] * pad_len)
            batch["attention_mask"].append(f["attention_mask"] + [0] * pad_len)
            batch["labels"].append(f["labels"] + [-100] * pad_len)
        return {k: torch.tensor(v) for k, v in batch.items()}

    # Initialize trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
    )

    # Train
    print("Starting training...")
    train_result = trainer.train()

    # Save final model
    final_dir = args.output_dir / "final"
    print(f"Saving final model to {final_dir}...")
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    # Print metrics
    metrics = train_result.metrics
    print("\nTraining complete!")
    print(f"  Train loss: {metrics.get('train_loss', 'N/A')}")
    print(f"  Train runtime: {metrics.get('train_runtime', 'N/A'):.1f}s")
    print(f"  Samples/second: {metrics.get('train_samples_per_second', 'N/A'):.1f}")
    print(f"  Model saved to: {final_dir}")

    # Run eval
    eval_metrics = trainer.evaluate()
    print(f"  Eval loss: {eval_metrics.get('eval_loss', 'N/A')}")


if __name__ == "__main__":
    main()
