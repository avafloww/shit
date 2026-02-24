# Training the Model

## Prerequisites

- Python 3.10+
- PyTorch with CUDA (tested on RTX 3090, 24GB VRAM)
- ~2GB disk space for training data and checkpoints

## Pipeline

```bash
cd training

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install transformers datasets sentencepiece accelerate huggingface-hub

# Log in to HuggingFace (Gemma is a gated model)
python3 -c "from huggingface_hub import login; login()"

# 1. Generate base training examples (259 scenarios)
python3 generate_data.py --no-thefuck --stats

# 2. Augment to 60K+ examples
python3 augment.py --n-variations 100

# 3. Shuffle and split into train/test
python3 -c "
import json, random
from pathlib import Path
random.seed(42)
with open('data/augmented.jsonl') as f:
    examples = [json.loads(line) for line in f if line.strip()]
random.shuffle(examples)
split = int(len(examples) * 0.9)
for name, data in [('train', examples[:split]), ('test', examples[split:])]:
    with open(f'data/{name}.jsonl', 'w') as f:
        for ex in data:
            f.write(json.dumps(ex) + '\n')
print(f'Train: {split}, Test: {len(examples)-split}')
"

# 4. Convert to operation format
python3 -c "
import json

def command_to_op(command, correction):
    # Handle multi-alternative corrections (newline-separated)
    if '\n' in correction:
        ops = [command_to_op(command, c.strip()) for c in correction.split('\n') if c.strip()]
        return '\n'.join(ops)
    if correction == '?': return 'NONE'
    if correction.startswith('sudo ') and not command.startswith('sudo '):
        if correction[5:] == command: return 'PREPEND sudo'
    cmd_words, cor_words = command.split(), correction.split()
    if len(cmd_words) == len(cor_words):
        diffs = [(i,c,r) for i,(c,r) in enumerate(zip(cmd_words, cor_words)) if c != r]
        if len(diffs) == 1: return f'REPLACE {diffs[0][1]} {diffs[0][2]}'
        if len(diffs) == 0: return 'NONE'
    if len(cor_words) == len(cmd_words) + 1:
        for i in range(len(cor_words)):
            without = cor_words[:i] + cor_words[i+1:]
            if without == cmd_words and cor_words[i].startswith('-'):
                return f'FLAG {cor_words[i]}'
    return f'FULL {correction}'

for split in ['train', 'test']:
    examples = [json.loads(l) for l in open(f'data/{split}.jsonl')]
    converted = [dict(e, op=command_to_op(e['command'], e['correction'])) for e in examples]
    with open(f'data/{split}_ops.jsonl', 'w') as f:
        for c in converted:
            f.write(json.dumps(c) + '\n')
    print(f'{split}: {len(converted)} examples')
"

# 5. Train (5 epochs, ~45 minutes on RTX 3090)
# NOTE: If running via a script/agent with timeouts, set timeout to at least
# 60 minutes — training takes ~45 min on a 3090 and longer on slower GPUs.
python3 train.py \
  --data data/train_ops.jsonl \
  --eval-data data/test_ops.jsonl \
  --model-name google/gemma-3-270m \
  --bf16 --epochs 5 --batch-size 8 --learning-rate 1e-4 \
  --gradient-accumulation-steps 4 --warmup-ratio 0.05

# 6. Save tokenizer to checkpoint (HF Trainer doesn't do this automatically)
python3 -c "
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download
t = AutoTokenizer.from_pretrained('google/gemma-3-270m')
t.save_pretrained('checkpoints/checkpoint-XXXX')  # use best checkpoint
hf_hub_download('google/gemma-3-270m', 'tokenizer.model', local_dir='checkpoints/checkpoint-XXXX')
"
```

## Exporting to GGUF

```bash
# Clone llama.cpp for conversion tools
git clone --depth 1 https://github.com/ggml-org/llama.cpp
pip install gguf

# Convert to GGUF (use bf16, NOT f16 — Gemma weights overflow in IEEE float16)
python3 llama.cpp/convert_hf_to_gguf.py checkpoints/checkpoint-XXXX \
  --outfile model/shit.gguf --outtype bf16

cmake -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release llama.cpp
cmake --build llama.cpp/build --target llama-quantize -j$(nproc)
./llama.cpp/build/bin/llama-quantize model/shit.bf16.gguf model/shit-ops.q4.gguf Q4_K_M
```

## Key Gotchas

- **Always use `bf16` not `f16`** for GGUF export — Gemma 3 weights cause NaN in IEEE float16
- **HF Trainer doesn't save the tokenizer** to checkpoints — you must save it manually
- **Tokenize prompt and completion separately** during training — otherwise the tokenizer merges tokens across the boundary and the model learns wrong labels
- **Use the base model's tokenizer** (`google/gemma-3-270m`) when loading checkpoints, not the checkpoint's own tokenizer (which may have vocab_size=5)
