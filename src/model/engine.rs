use anyhow::{bail, Result};
use candle_core::{DType, Device, Tensor};
use candle_transformers::generation::LogitsProcessor;
use candle_transformers::models::quantized_gemma3::ModelWeights;
use std::path::Path;
use tokenizers::Tokenizer;

const MAX_GENERATED_TOKENS: usize = 100;

pub struct Engine {
    model: ModelWeights,
    tokenizer: Tokenizer,
    device: Device,
}

impl Engine {
    pub fn new(model_path: &Path, tokenizer_path: &Path) -> Result<Self> {
        let device = Device::Cpu;
        let mut file = std::fs::File::open(model_path)?;
        let content = candle_core::quantized::gguf_file::Content::read(&mut file)?;
        let model = ModelWeights::from_gguf(content, &mut file, &device)?;
        let tokenizer = Tokenizer::from_file(tokenizer_path).map_err(anyhow::Error::msg)?;

        Ok(Self {
            model,
            tokenizer,
            device,
        })
    }

    pub fn infer(&mut self, prompt: &str) -> Result<String> {
        let encoding = self
            .tokenizer
            .encode(prompt, true)
            .map_err(anyhow::Error::msg)?;
        let prompt_tokens = encoding.get_ids().to_vec();

        let device = &self.device;
        let model = &mut self.model;
        let tokenizer = &self.tokenizer;

        generate_tokens(&prompt_tokens, tokenizer, &mut |tokens, pos| {
            let input = Tensor::new(tokens, device)?.unsqueeze(0)?;
            let logits = model.forward(&input, pos)?;
            Ok(logits.squeeze(0)?)
        })
    }
}

/// Generate tokens from a model with greedy decoding.
fn generate_tokens(
    prompt_tokens: &[u32],
    tokenizer: &Tokenizer,
    forward_fn: &mut dyn FnMut(&[u32], usize) -> Result<Tensor>,
) -> Result<String> {
    let mut logits_processor = LogitsProcessor::new(0, None, None);

    let logits = forward_fn(prompt_tokens, 0)?;
    let logits = logits.to_dtype(DType::F32)?;
    let mut next_logits = extract_last_logits(&logits)?;
    let mut next_token = logits_processor.sample(&next_logits)?;

    let mut generated_tokens = vec![next_token];
    let mut pos = prompt_tokens.len();

    for _ in 0..MAX_GENERATED_TOKENS {
        let logits = forward_fn(&[next_token], pos)?;
        let logits = logits.to_dtype(DType::F32)?;
        next_logits = extract_last_logits(&logits)?;
        next_token = logits_processor.sample(&next_logits)?;

        if next_token == 1 || next_token == 0 {
            break;
        }
        generated_tokens.push(next_token);
        pos += 1;
    }

    let output = tokenizer
        .decode(&generated_tokens, true)
        .map_err(anyhow::Error::msg)?
        .trim()
        .to_string();

    Ok(output)
}

/// Extract the last position's logits from a tensor of varying shape.
/// Handles [vocab], [seq_len, vocab], etc.
fn extract_last_logits(logits: &Tensor) -> Result<Tensor> {
    let dims = logits.dims();
    match dims.len() {
        1 => Ok(logits.clone()),           // [vocab] -- single position
        2 => Ok(logits.get(dims[0] - 1)?), // [seq_len, vocab] -- last position
        _ => bail!("unexpected logits shape: {:?}", dims),
    }
}
