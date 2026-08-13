from __future__ import annotations

from importlib.metadata import version

from llama_cpp import llama_cpp


def main() -> int:
    info = llama_cpp.llama_print_system_info()
    decoded = info.decode("utf-8", errors="replace") if isinstance(info, bytes) else str(info)
    supports_offload = bool(llama_cpp.llama_supports_gpu_offload())
    targets_sm86 = "ARCHS = 860" in decoded
    avoids_avx512 = "AVX512 = 1" not in decoded
    print(f"llama-cpp-python={version('llama-cpp-python')}")
    print(f"gpu_offload={supports_offload}")
    print(f"sm86_target={targets_sm86}")
    print(f"avx512_disabled={avoids_avx512}")
    print(decoded)
    return 0 if supports_offload and targets_sm86 and avoids_avx512 else 1


if __name__ == "__main__":
    raise SystemExit(main())
