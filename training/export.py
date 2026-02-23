#!/usr/bin/env python3
"""Export fine-tuned model to GGUF Q4_K_M format.

Converts a HuggingFace model checkpoint to GGUF format with Q4_K_M quantization
for efficient inference with llama.cpp.

This script uses llama-cpp-python's conversion utilities when available,
or falls back to calling the llama.cpp convert scripts directly.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def find_llama_cpp_convert_script() -> Path | None:
    """Try to find the llama.cpp convert-hf-to-gguf.py script.

    Checks common locations:
    1. In the llama-cpp-python package vendor directory
    2. In a local llama.cpp clone
    3. On PATH
    """
    # Check if llama-cpp-python has bundled scripts
    try:
        import llama_cpp

        pkg_dir = Path(llama_cpp.__file__).parent
        # Some versions bundle the conversion script
        for candidate in [
            pkg_dir / "llama_cpp" / "convert_hf_to_gguf.py",
            pkg_dir.parent / "convert_hf_to_gguf.py",
        ]:
            if candidate.exists():
                return candidate
    except ImportError:
        pass

    # Check for llama.cpp in common locations
    for candidate in [
        Path("llama.cpp/convert_hf_to_gguf.py"),
        Path("../llama.cpp/convert_hf_to_gguf.py"),
        Path.home() / "llama.cpp" / "convert_hf_to_gguf.py",
    ]:
        if candidate.exists():
            return candidate

    # Check PATH
    which = shutil.which("convert-hf-to-gguf")
    if which:
        return Path(which)

    return None


def find_quantize_binary() -> Path | None:
    """Find the llama-quantize (or llama.cpp quantize) binary."""
    # Check PATH first
    for name in ["llama-quantize", "quantize"]:
        which = shutil.which(name)
        if which:
            return Path(which)

    # Check common build locations
    for candidate in [
        Path("llama.cpp/build/bin/llama-quantize"),
        Path("../llama.cpp/build/bin/llama-quantize"),
        Path.home() / "llama.cpp" / "build" / "bin" / "llama-quantize",
    ]:
        if candidate.exists():
            return candidate

    return None


def convert_to_gguf(model_dir: Path, output_path: Path) -> bool:
    """Convert a HuggingFace model to GGUF F16 format.

    Returns True on success.
    """
    convert_script = find_llama_cpp_convert_script()
    if convert_script is None:
        print("Error: Could not find convert-hf-to-gguf.py")
        print()
        print("Please either:")
        print("  1. Clone llama.cpp: git clone https://github.com/ggml-org/llama.cpp")
        print("  2. Or install it: pip install llama-cpp-python")
        print()
        print("Then re-run this script.")
        return False

    print(f"Using conversion script: {convert_script}")

    cmd = [
        sys.executable,
        str(convert_script),
        str(model_dir),
        "--outfile",
        str(output_path),
        "--outtype",
        "f16",
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def quantize_gguf(
    input_path: Path, output_path: Path, quant_type: str = "Q4_K_M"
) -> bool:
    """Quantize a GGUF model to the specified quantization type.

    Returns True on success.
    """
    quantize_bin = find_quantize_binary()
    if quantize_bin is None:
        print("Error: Could not find llama-quantize binary")
        print()
        print("Please build llama.cpp:")
        print("  git clone https://github.com/ggml-org/llama.cpp")
        print("  cd llama.cpp && cmake -B build && cmake --build build")
        print()
        print("Then re-run this script.")
        return False

    print(f"Using quantize binary: {quantize_bin}")

    cmd = [
        str(quantize_bin),
        str(input_path),
        str(output_path),
        quant_type,
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Export fine-tuned model to GGUF Q4_K_M format"
    )
    parser.add_argument(
        "-m",
        "--model-dir",
        type=Path,
        default=Path("checkpoints/final"),
        help="Path to fine-tuned HF model directory (default: checkpoints/final)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("model/shit.gguf"),
        help="Output GGUF file path (default: model/shit.gguf)",
    )
    parser.add_argument(
        "--quant-type",
        type=str,
        default="Q4_K_M",
        help="Quantization type (default: Q4_K_M)",
    )
    parser.add_argument(
        "--keep-f16",
        action="store_true",
        help="Keep the intermediate F16 GGUF file",
    )
    args = parser.parse_args()

    if not args.model_dir.exists():
        print(f"Error: model directory {args.model_dir} not found")
        print("Run train.py first to produce a fine-tuned checkpoint.")
        raise SystemExit(1)

    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: Convert HF model to GGUF F16
    f16_path = args.output.with_suffix(".f16.gguf")
    print(f"Step 1: Converting HF model to GGUF F16...")
    print(f"  Input:  {args.model_dir}")
    print(f"  Output: {f16_path}")

    if not convert_to_gguf(args.model_dir, f16_path):
        print("\nConversion to GGUF failed.")
        raise SystemExit(1)

    f16_size = f16_path.stat().st_size / (1024 * 1024)
    print(f"\nF16 GGUF size: {f16_size:.1f} MB")

    # Step 2: Quantize to target type
    print(f"\nStep 2: Quantizing to {args.quant_type}...")
    print(f"  Input:  {f16_path}")
    print(f"  Output: {args.output}")

    if not quantize_gguf(f16_path, args.output, args.quant_type):
        print("\nQuantization failed.")
        raise SystemExit(1)

    final_size = args.output.stat().st_size / (1024 * 1024)
    print(f"\n{args.quant_type} GGUF size: {final_size:.1f} MB")
    print(f"Compression ratio: {f16_size / final_size:.1f}x")

    # Clean up F16 intermediate file
    if not args.keep_f16:
        f16_path.unlink()
        print(f"Removed intermediate F16 file: {f16_path}")

    print(f"\nExport complete: {args.output}")


if __name__ == "__main__":
    main()
