"""Run v1 provenance, offline preflight, scoring, and later local benchmarks.

No training entry point. Contract v1 is pinned below: changing it requires an
explicitly reviewed update to both contract and pin. Hash serialization is
UTF-8 json.dumps(ensure_ascii=False, sort_keys=True, separators=(',', ':')).
Benchmark and blind-pack commands require separate human authorization to run.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import ipaddress
import json
import math
import os
from pathlib import Path
import random
import re
import struct
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "experiments/train-run-v1/contract.json"
APPROVED_CONTRACT_SHA256 = "1E6A4296A87541E119D6C73B2316CB6D421DFE2AFC85F88D3DF2733AE9886678"
ALLOWED_MODULE = re.compile(
    r"model\.language_model\.layers\.\d+\.(?:"
    r"self_attn\.(?:q_proj|k_proj|v_proj|o_proj)|"
    r"mlp\.(?:gate_proj|up_proj|down_proj))"
)
Json = dict[str, Any]


class ExperimentError(Exception):
    def __init__(self, reason: str, **details: Any):
        super().__init__(reason)
        self.reason = reason
        self.details = details


def require(condition: bool, reason: str, **details: Any) -> None:
    if not condition:
        raise ExperimentError(reason, **details)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def unique_object(pairs: list[tuple[str, Any]]) -> Json:
    result: Json = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY", key=key)
        result[key] = value
    return result


def load_json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=unique_object,
                      parse_constant=lambda _: require(False, "INVALID_JSON_NUMBER"))


def read_json(path: Path) -> Json:
    return load_json(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[Json]:
    return [load_json(line) for line in path.read_text(encoding="utf-8").splitlines()]


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    require(not Path(relative).is_absolute() and path.is_relative_to(root.resolve()),
            "UNSAFE_PATH")
    return path


def run_directory(root: Path, c: Json, suffix: str = "") -> Path:
    relative = f"{c['output']['runs_root']}/{c['output']['run_id']}"
    return inside(root, relative + ("/" + suffix if suffix else ""))


def resolve_destination(root: Path, c: Json, default_suffix: str, custom: Path | None = None) -> Path:
    if custom is None:
        return run_directory(root, c, default_suffix)
    path = (root / custom).resolve() if not custom.is_absolute() else custom.resolve()
    require(path.is_relative_to(root.resolve()), "UNSAFE_PATH")
    return path


def derive_prompt(rows: list[Json]) -> str:
    prompts = set()
    for row in rows:
        messages = row["messages"]
        require([m["role"] for m in messages] == ["system", "user", "assistant"],
                "TRAIN_SCHEMA_MISMATCH")
        require(all(isinstance(m["content"], str) for m in messages),
                "TRAIN_SCHEMA_MISMATCH")
        prompts.add(messages[0]["content"])
    require(len(prompts) == 1, "CANONICAL_PROMPT_MISMATCH", unique_prompts=len(prompts))
    return prompts.pop()


def index_results(rows: list[Json]) -> Json:
    indexed = {row["id"]: row for row in rows}
    require(len(indexed) == len(rows), "DUPLICATE_EVAL_ID")
    return indexed


def score_case(case: Json, output: str | None, error: Any = None) -> Json:
    text = output if isinstance(output, str) else ""
    lower = text.lower()
    preserve = {p: p.lower() in lower for p in case["must_preserve"]}
    legacy_forbidden = {p: p.lower() not in lower for p in case["must_not_contain"]}
    boundary_forbidden = {
        p: re.search(r"(?<![A-Za-z0-9])" + re.escape(p) + r"(?![A-Za-z0-9])",
                     text, re.IGNORECASE) is None for p in case["must_not_contain"]
    }
    valid = error is None and isinstance(output, str)
    legacy = valid and all(preserve.values()) and all(legacy_forbidden.values())
    boundary = valid and all(preserve.values()) and all(boundary_forbidden.values())
    return {
        "exact_match": valid and text.strip() == case["expected"].strip(),
        "must_preserve_pass": valid and all(preserve.values()),
        "must_not_contain_pass": valid and all(legacy_forbidden.values()),
        "must_preserve_checks": preserve,
        "must_not_contain_checks": legacy_forbidden,
        "boundary_must_not_contain_checks": boundary_forbidden,
        "constraint_pass": legacy,
        "legacy_constraint_pass": legacy,
        "boundary_constraint_pass": boundary,
        "scoring_marker": "LEGACY_FALSE_NEGATIVE" if boundary and not legacy else None,
    }


def aggregate(cases: list[Json], results: list[Json]) -> Json:
    indexed = index_results(results)
    require(set(indexed) == set(index_results(cases)), "EVAL_IDS_MISMATCH")
    totals: Counter = Counter()
    categories: dict[str, Counter] = defaultdict(Counter)
    latencies = []
    for case in cases:
        row = indexed[case["id"]]
        checks = score_case(case, row.get("output"), row.get("error"))
        counts = {
            "cases": 1,
            "outputs": int(isinstance(row.get("output"), str) and row.get("error") is None),
            "exact_matches": int(checks["exact_match"]),
            "legacy_constraint_passes": int(checks["legacy_constraint_pass"]),
            "boundary_constraint_passes": int(checks["boundary_constraint_pass"]),
            "api_errors": int(row.get("error") is not None or not isinstance(row.get("output"), str)),
            "truncations": int(row.get("finish_reason") == "length"),
            "legacy_false_negatives": int(checks["scoring_marker"] is not None),
        }
        totals.update(counts)
        categories[case["category"]].update(counts)
        latency = row.get("latency_seconds")
        if latency is not None:
            require(isinstance(latency, (int, float)) and math.isfinite(latency)
                    and latency >= 0, "INVALID_LATENCY")
            latencies.append(latency)
    latencies.sort()
    return {
        **dict(totals), "constraint_passes": totals["legacy_constraint_passes"],
        "categories": {k: dict(v) for k, v in sorted(categories.items())},
        "latency": {
            "observations": len(latencies),
            "mean_seconds": sum(latencies) / len(latencies) if latencies else None,
            "p95_seconds": latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
        },
        "semantic_review": "NOT_VERIFIED",
    }


def validate_contract(path: Path = DEFAULT_CONTRACT, root: Path = ROOT) -> Json:
    c = read_json(path)
    required = {"schema_version", "experiment_id", "baseline_git_commit", "model",
                "artifacts", "canonical_prompt", "training", "optimizer_arithmetic",
                "lora", "loss_masking", "selection", "benchmark", "scoring", "acceptance",
                "critical_failures", "launch_gate", "output", "runtime", "contract_serialization"}
    require(isinstance(c, dict) and required <= c.keys() and c["schema_version"] == 1,
            "CONTRACT_SCHEMA_MISMATCH")
    rows: dict[str, list[Json]] = {}
    for name, artifact in c["artifacts"].items():
        target = inside(root, artifact["path"])
        require(target.is_file(), "REQUIRED_ARTIFACT_MISSING", artifact=name)
        observed = file_hash(target)
        require(observed == artifact["sha256"], "FROZEN_HASH_MISMATCH",
                artifact=name, observed=observed, expected=artifact["sha256"])
        if "rows" in artifact:
            rows[name] = read_jsonl(target)
            require(len(rows[name]) == artifact["rows"], "FROZEN_COUNT_MISMATCH",
                    artifact=name, observed=len(rows[name]), expected=artifact["rows"])
    prompt = derive_prompt(rows["train"])
    require(len(prompt.encode("utf-8")) == c["canonical_prompt"]["utf8_bytes"]
            and digest(prompt.encode("utf-8")) == c["canonical_prompt"]["sha256"],
            "CANONICAL_PROMPT_MISMATCH")
    t = c["training"]
    require(all(type(t[k]) is int and t[k] > 0 for k in
                ["batch_size", "gradient_accumulation_steps", "num_epochs"]),
            "OPTIMIZER_ARITHMETIC_MISMATCH")
    microbatches = math.ceil(len(rows["train"]) / t["batch_size"])
    steps = math.ceil(microbatches / t["gradient_accumulation_steps"])
    arithmetic = c["optimizer_arithmetic"]
    require(arithmetic["world_size"] == 1
            and arithmetic["effective_batch"] == t["batch_size"] * t["gradient_accumulation_steps"]
            and arithmetic["microbatches_per_epoch"] == microbatches
            and arithmetic["optimizer_steps_per_epoch"] == steps
            and arithmetic["total_optimizer_steps"] == steps * t["num_epochs"]
            and c["selection"]["candidate_step"] == steps * t["num_epochs"]
            and c["selection"]["diagnostic_checkpoint_step"] == t["save_steps"] == steps,
            "OPTIMIZER_ARITHMETIC_MISMATCH")
    contract_hash = digest(canonical_bytes(c))
    # Whole-contract pin also validates nested types, exact thresholds and all
    # no-selection policies; permissive defaults would allow accidental drift.
    require(contract_hash == APPROVED_CONTRACT_SHA256, "CONTRACT_DRIFT",
            observed_contract_sha256=contract_hash)
    cases = rows["eval"]
    gold = [{"id": r["id"], "output": r["expected"]} for r in cases]
    passthrough = [{"id": r["id"], "output": r["input"]} for r in cases]
    for label, outputs in [("gold", gold), ("passthrough", passthrough)]:
        summary = aggregate(cases, outputs)
        for metric in ["legacy", "boundary"]:
            require(summary[f"{metric}_constraint_passes"] == c["scoring"][f"expected_{label}_{metric}"],
                    "SCORING_CONTRACT_MISMATCH")
    base = aggregate(cases, rows["historical_base_results"])
    b = c["benchmark"]
    require(base["exact_matches"] == b["historical_exact_matches"]
            and base["legacy_constraint_passes"] == b["historical_legacy_constraint_passes"]
            and base["api_errors"] == b["historical_api_errors"]
            and abs(base["latency"]["mean_seconds"] - b["historical_mean_latency_seconds"]) < 0.00001,
            "HISTORICAL_METRIC_MISMATCH")
    counts = Counter(case["category"] for case in cases)
    for category, denominator in c["acceptance"]["category_denominators"].items():
        observed = (sum(counts[k] for k in c["acceptance"]["language_categories"])
                    if category == "language_aggregate" else counts[category])
        require(observed == denominator, "ACCEPTANCE_CONTRACT_MISMATCH")
    return {"contract": c, "contract_sha256": contract_hash, "prompt": prompt,
            "train": rows["train"], "eval": cases, "historical_base": base}


def git_evidence(root: Path, baseline: str) -> Json:
    def run(*args: str) -> str:
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True, timeout=20).stdout.strip()
    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain=v1", "--ignore-submodules=all", "--untracked-files=all")
    run("merge-base", "--is-ancestor", baseline, "HEAD")
    return {"commit": commit, "branch": run("branch", "--show-current"),
            "dirty": bool(status), "dirty_entries": len(status.splitlines()),
            "baseline_is_ancestor": True}


def load_installed_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "RUNTIME_INSPECTION_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def target_metadata(snapshot: Path, lora: Json) -> Json:
    index = read_json(snapshot / "model.safetensors.index.json")
    selected: Json = {}
    header_hashes: Json = {}
    for shard in sorted(set(index["weight_map"].values())):
        path = inside(snapshot, shard)
        with path.open("rb") as stream:
            length = struct.unpack("<Q", stream.read(8))[0]
            require(0 < length <= 16 * 1024 * 1024, "MODEL_HEADER_INVALID")
            raw = stream.read(length)
        header_hashes[shard] = digest(raw)
        header = load_json(raw.decode("utf-8"))
        tensors = [meta for name, meta in header.items() if name != "__metadata__"]
        require(len(raw) == length and tensors
                and path.stat().st_size == 8 + length + max(m["data_offsets"][1] for m in tensors),
                "MODEL_CACHE_INCOMPLETE")
        for name, meta in header.items():
            if (name.endswith(".weight") and name.split(".")[-2] in lora["targets"]
                    and name.startswith("model.language_model.layers.")):
                require(name not in selected and len(meta["shape"]) == 2,
                        "TARGET_MODULE_MISMATCH")
                require(meta["dtype"] == "BF16", "MODEL_PRECISION_MISMATCH")
                selected[name] = meta
    return {
        "inspection": "cached tensor headers; no full model or adapter instantiated",
        "modules": len(selected),
        "modules_sha256": digest(canonical_bytes(sorted(name.removesuffix(".weight") for name in selected))),
        "trainable_parameters": sum(lora["rank"] * sum(m["shape"]) for m in selected.values()),
        "vision_matches": sum("visual" in n or "vision" in n for n in selected),
        "mtp_matches": sum("mtp" in n.lower() for n in selected),
        "header_sha256": header_hashes,
        "live_peft_resolution": "NOT_VERIFIED",
    }


def classify_adapter(modules: list[str], trainable: dict[str, int]) -> Json:
    """Measure collected LoRA layers and requires_grad parameters without Torch."""
    modules = [name.removeprefix("base_model.model.") for name in modules]
    owners = set(modules)
    non_lora = 0
    for name, count in trainable.items():
        match = re.fullmatch(r"(.+)\.lora_[AB]\.[^.]+\.weight",
                             name.removeprefix("base_model.model."))
        if match is None or match[1] not in owners:
            non_lora += count
    return {
        "modules": len(modules), "trainable_parameters": sum(trainable.values()),
        "modules_sha256": digest(canonical_bytes(sorted(modules))),
        "mtp_matches": sum(bool(re.search(r"(^|\.)mtp(\.|$)", name)) for name in modules),
        "vision_matches": sum(bool(re.search(
            r"(^|\.)(visual|vision_tower|vision_model|visual_tokenizer)(\.|$)", name))
            for name in modules),
        "foreign_modules": sum(ALLOWED_MODULE.fullmatch(name) is None for name in modules),
        "non_lora_trainable": non_lora,
    }


def live_target_resolution(snapshot: Path, lora: Json, site: Path) -> Json:
    """Construct fresh, local meta-device PEFT models; never load checkpoint shards."""
    import types
    import torch
    import transformers
    from peft import LoraConfig, get_peft_model
    from peft.tuners.lora.layer import LoraLayer

    # As with Studio masking, bypass the installed Zoo package initializer.
    package_name = "voxdara_installed_peft"
    package = types.ModuleType(package_name)
    package.__path__ = [str(site / "unsloth_zoo")]
    sys.modules[package_name] = package
    zoo = load_installed_module(package_name + ".peft_utils", site / "unsloth_zoo/peft_utils.py")
    config = transformers.AutoConfig.from_pretrained(str(snapshot), local_files_only=True,
                                                     trust_remote_code=False)
    cls = getattr(transformers, config.architectures[0])
    result = {}
    for resolution in ["regex", "list"]:
        with torch.device("meta"):
            base = cls._from_config(config)
            targets = list(lora["targets"])
            if resolution == "regex":
                targets = zoo.get_peft_regex(
                    base, finetune_vision_layers=lora["finetune_vision_layers"],
                    finetune_language_layers=True, finetune_attention_modules=True,
                    finetune_mlp_modules=True, target_modules=targets)
            model = get_peft_model(base, LoraConfig(
                r=lora["rank"], lora_alpha=lora["alpha"], lora_dropout=lora["dropout"],
                bias=lora["bias"], use_rslora=lora["use_rslora"],
                target_modules=targets, task_type="CAUSAL_LM"))
        require(all(p.device.type == "meta" for p in model.parameters()),
                "RUNTIME_INSPECTION_UNAVAILABLE")
        modules = [name for name, module in model.named_modules() if isinstance(module, LoraLayer)]
        trainable = {name: p.numel() for name, p in model.named_parameters() if p.requires_grad}
        result[resolution] = classify_adapter(modules, trainable)
        del model, base
    return result


def runtime_evidence(validated: Json, snapshot_override: Path | None = None) -> Json:
    """Inspect installed code/tokenizer and meta adapters. Never activate/repair.

    Zoo's package initializer probes cache writability, so load its installed
    dataset utility file directly. Its return_function=True path needs no
    trainer or Dataset.map and performs masking entirely in memory.
    """
    c = validated["contract"]
    outer = {p: importlib.metadata.version(p) for p in c["runtime"]["outer_versions"]}
    site = Path(sys.prefix) / ("Lib/site-packages" if os.name == "nt" else
                              f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")
    sources = c["runtime"]["installed_source_hashes"]
    observed_sources = {name: file_hash(site / name) for name in sources}
    require(observed_sources == sources, "RUNTIME_SOURCE_MISMATCH")
    model = c["model"]
    cache = Path(os.environ.get("HF_HUB_CACHE") or
                 (Path(os.environ.get("HF_HOME") or Path.home() / ".cache/huggingface") / "hub"))
    snapshot = snapshot_override or (cache / ("models--" + model["repository"].replace("/", "--"))
                                    / "snapshots" / model["revision"])
    require(snapshot.name == model["revision"] and snapshot.is_dir(), "MODEL_REVISION_MISMATCH")
    observed_files = {name: file_hash(snapshot / name) for name in model["snapshot_file_hashes"]}
    require(observed_files == model["snapshot_file_hashes"], "MODEL_REVISION_MISMATCH")
    require(read_json(snapshot / "config.json")["architectures"] == [model["architecture"]],
            "MODEL_REVISION_MISMATCH")
    # Offline flags affect this process only; no credentials are inspected.
    for name in ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE",
                 "HF_HUB_DISABLE_TELEMETRY", "PYTHONDONTWRITEBYTECODE"]:
        os.environ[name] = "1"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(site / "studio/backend"))
    from utils import transformers_version as selector
    # Pinned Qwen local config takes the explicit 530 fast path. probe=False
    # forbids sidecar subprocess probes; installer activation is never called.
    tier = selector.get_transformers_tier(str(snapshot), probe=False)
    require(tier == c["runtime"]["effective_transformers_tier"], "RUNTIME_VERSION_MISMATCH",
            effective_tier=tier)
    overlay = Path(getattr(selector, f"_VENV_T5_{tier}_DIR"))
    require(overlay.is_dir() and "transformers" not in sys.modules,
            "RUNTIME_INSPECTION_UNAVAILABLE")
    sys.path.insert(0, str(overlay))
    effective = {p: importlib.metadata.version(p) for p in c["runtime"]["effective_versions"]}
    import torch
    import transformers
    gpu: Json = {"available": torch.cuda.is_available()}
    if gpu["available"]:
        free, total = torch.cuda.mem_get_info(0)
        gpu.update(name=torch.cuda.get_device_name(0), total_gib=total / 2**30,
                   free_gib=free / 2**30, compute_capability=list(torch.cuda.get_device_capability(0)),
                   bf16_supported=torch.cuda.is_bf16_supported())
    zoo = load_installed_module("voxdara_installed_zoo_dataset_utils", site / "unsloth_zoo/dataset_utils.py")
    tok = transformers.AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True,
                                                      trust_remote_code=False)
    instruction, response = zoo.get_chat_template_parts(tok)
    # Load the shared Studio policy without importing utils.datasets' broader
    # package initializer. Its only relative import is the model marker table.
    import types
    package_name = "voxdara_installed_masking"
    package = types.ModuleType(package_name)
    package.__path__ = [str(site / "studio/backend/utils/datasets")]
    sys.modules[package_name] = package
    policy = load_installed_module(package_name + ".completion_masking",
                                  site / "studio/backend/utils/datasets/completion_masking.py")
    holder = types.SimpleNamespace(processing_class=tok)
    mask_functions = []
    def capture_mask(trainer: Any, **kwargs: Any) -> Any:
        mask_functions.append(zoo.train_on_responses_only(None, tokenizer=tok,
                                                          return_function=True, **kwargs))
        return trainer
    _, applied = policy.apply_completion_masking(holder, model["repository"], capture_mask,
                                                 detect_fn=zoo.get_chat_template_parts)
    require(applied and len(mask_functions) == 1, "ZERO_COMPLETION_MASK")
    lengths, supervised = [], []
    prefix_mismatches = leaks = raw_masks = 0
    for row in validated["train"]:
        messages = row["messages"]
        text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        prefix = tok.apply_chat_template(messages[:2], tokenize=False, add_generation_prompt=False)
        enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
        ids = enc["input_ids"]
        labels = mask_functions[0]({"input_ids": [ids]})["labels"][0]
        prefix_mismatches += not text.startswith(prefix)
        leaks += any(label != -100 and start < len(prefix)
                     for label, (start, end) in zip(labels, enc["offset_mapping"]))
        require(len(labels) == len(ids) and all(l == -100 or l == i for l, i in zip(labels, ids)),
                "COMPLETION_MASK_INVALID")
        lengths.append(len(ids))
        supervised.append(sum(l != -100 for l in labels))
        raw = tok.apply_chat_template(messages, tokenize=True, return_dict=True,
                                       return_assistant_tokens_mask=True, add_generation_prompt=False)
        require("assistant_masks" in raw and len(raw["assistant_masks"]) == len(raw["input_ids"]),
                "ASSISTANT_MASK_INSPECTION_UNAVAILABLE")
        raw_masks += any(raw["assistant_masks"])
    targets = target_metadata(snapshot, c["lora"])
    targets["live"] = live_target_resolution(snapshot, c["lora"], site)
    targets["live_peft_resolution"] = "VERIFIED"
    return {
        "python": sys.version.split()[0], "cuda": torch.version.cuda,
        "outer_versions": outer, "effective_versions": effective,
        "effective_transformers_tier": tier, "overlay_path": str(overlay),
        "effective_transformers_path": transformers.__file__, "gpu": gpu,
        "installed_source_sha256": observed_sources,
        "model": {"repository": model["repository"], "revision": snapshot.name,
                  "snapshot_path": str(snapshot), "snapshot_file_sha256": observed_files,
                  "identity_basis": "local revision cache directory plus pinned metadata hashes; tensor headers",
                  "upstream_tensor_byte_identity": "NOT_VERIFIED"},
        "tokenizer": {"class": type(tok).__name__, "template_sha256": digest(tok.chat_template.encode()),
                      "instruction_marker_sha256": digest(instruction.encode()),
                      "response_marker_sha256": digest(response.encode())},
        "masking": {"rows": len(lengths), "max_rendered_tokens": max(lengths),
                    "mean_rendered_tokens": sum(lengths) / len(lengths),
                    "mean_supervised_tokens": sum(supervised) / len(supervised),
                    "fully_masked_rows": supervised.count(0), "prefix_mismatches": prefix_mismatches,
                    "supervision_leaks": leaks, "raw_assistant_mask_nonzero_rows": raw_masks},
        "target_resolution": targets,
        "studio_fields": {**c["training"], "model_name": model["repository"],
                          "model_revision": model["revision"], "model_snapshot_path": str(snapshot),
                          "output_dir_identity": c["output"]["studio_output_identity"], "lora": c["lora"]},
        "studio_field_status": "intended; not applied to Studio installation/database",
    }


def launch_gates(c: Json, runtime: Json) -> list[Json]:
    gates = []
    def add(reason: str, passed: bool, observed: Any) -> None:
        gates.append({"reason": reason, "passed": bool(passed), "observed": observed})
    expected_runtime = c["runtime"]
    add("RUNTIME_VERSION_MISMATCH", all(runtime.get(k) == expected_runtime[k]
        for k in ["python", "cuda", "outer_versions", "effective_versions", "effective_transformers_tier"]),
        {k: runtime.get(k) for k in ["python", "cuda", "outer_versions", "effective_versions", "effective_transformers_tier"]})
    gpu = runtime.get("gpu", {})
    gate = c["launch_gate"]
    add("GPU_CONTRACT_MISMATCH", gpu.get("available") and gate["gpu_name_contains"] in gpu.get("name", "")
        and gpu.get("compute_capability") == gate["compute_capability"]
        and gpu.get("bf16_supported") is True
        and abs(gpu.get("total_gib", 0) - gate["total_vram_gib_approximately"]) < 0.1, gpu)
    add("VRAM_GATE_FAILED", gpu.get("free_gib", 0) >= gate["minimum_free_vram_gib"],
        {"free_gib": gpu.get("free_gib"), "required_gib": gate["minimum_free_vram_gib"]})
    mask = runtime.get("masking", {})
    add("SEQUENCE_TOO_LONG", 0 < mask.get("max_rendered_tokens", 0) <= c["training"]["max_seq_length"],
        mask.get("max_rendered_tokens"))
    add("ZERO_COMPLETION_MASK", mask.get("fully_masked_rows") == 0, mask.get("fully_masked_rows"))
    add("SUPERVISION_LEAK", mask.get("supervision_leaks") == 0 and mask.get("prefix_mismatches") == 0, mask)
    expected_mask = c["loss_masking"]
    add("MASKING_EVIDENCE_MISMATCH", mask.get("rows") == c["artifacts"]["train"]["rows"]
        and mask.get("max_rendered_tokens") == expected_mask["expected_max_rendered_tokens"]
        and mask.get("raw_assistant_mask_nonzero_rows") == expected_mask["expected_raw_assistant_mask_nonzero_rows"]
        and abs(mask.get("mean_rendered_tokens", 0) - expected_mask["expected_rendered_mean_tokens"]) < 1e-6
        and abs(mask.get("mean_supervised_tokens", 0) - expected_mask["expected_supervised_mean_tokens"]) < 1e-6, mask)
    targets = runtime.get("target_resolution", {})
    keys = ["modules", "trainable_parameters", "vision_matches", "mtp_matches"]
    live = [targets.get("live", {}).get(name, {}) for name in ["regex", "list"]]
    add("TARGET_MODULE_MISMATCH", all(targets.get(k) == c["lora"]["expected_" + k] for k in
        keys) and targets.get("live_peft_resolution") == "VERIFIED"
        and bool(targets.get("modules_sha256"))
        and all(all(resolution.get(k) == c["lora"]["expected_" + k] for k in keys)
                and resolution.get("modules_sha256") == targets["modules_sha256"]
                and resolution.get("foreign_modules") == 0
                and resolution.get("non_lora_trainable") == 0 for resolution in live), targets)
    return gates


def sanitized(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {k: sanitized(v, secrets) for k, v in value.items()
                if not re.search(r"(^|_)(secret|password|api_key|credential)($|_)|(^|_)(access|session|auth|hf|unsloth|provider)_token$|^token$", k, re.I)}
    if isinstance(value, list):
        return [sanitized(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


def new_directory(destination: Path) -> None:
    require(not destination.exists(), "OUTPUT_ALREADY_EXISTS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir()
    except FileExistsError:
        raise ExperimentError("OUTPUT_ALREADY_EXISTS") from None


def write_json_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")


def write_jsonl_new(path: Path, rows: list[Json]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(canonical_bytes(row).decode("utf-8") + "\n")


def finish_preflight(report: Json, destination: Path, dry_run: bool) -> Json:
    failed = [g["reason"] for g in report["gates"] if not g["passed"]]
    require(not destination.exists(), "OUTPUT_ALREADY_EXISTS")
    clean_report = sanitized({**report, "dry_run": dry_run, "status": "FAILED" if failed else "PASSED",
                              "training_authorized": False})
    if failed:
        raise ExperimentError(failed[0], preflight=clean_report, failed_gates=failed)
    if not dry_run:
        new_directory(destination)
        write_json_new(destination / "preflight.json", clean_report)
    return clean_report


def preflight(validated: Json, root: Path, dry_run: bool, snapshot: Path | None = None) -> Json:
    c = validated["contract"]
    destination = run_directory(root, c)
    require(not destination.exists(), "OUTPUT_ALREADY_EXISTS")
    git = git_evidence(root, c["baseline_git_commit"])
    runtime = runtime_evidence(validated, snapshot)
    # Re-read free VRAM after CPU tokenizer/header inspection, immediately
    # before assessing gates. A future human launch must remeasure it again.
    import torch
    if runtime["gpu"]["available"]:
        free, total = torch.cuda.mem_get_info(0)
        runtime["gpu"].update(free_gib=free / 2**30, total_gib=total / 2**30)
    report = {"schema_version": 1, "experiment_id": c["experiment_id"],
              "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "contract_sha256": validated["contract_sha256"], "tool_sha256": file_hash(Path(__file__)),
              "git": git, "runtime": runtime, "gates": launch_gates(c, runtime),
              "frozen_artifacts": c["artifacts"], "canonical_prompt": c["canonical_prompt"]}
    return finish_preflight(report, destination, dry_run)


def local_endpoint(endpoint: str) -> str:
    parsed = urllib.parse.urlsplit(endpoint)
    require(parsed.scheme in ["http", "https"] and parsed.hostname is not None
            and parsed.username is None and parsed.password is None
            and not parsed.query and not parsed.fragment
            and parsed.path == "/v1/chat/completions", "REMOTE_ENDPOINT_REJECTED")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        require(parsed.hostname.lower() == "localhost", "REMOTE_ENDPOINT_REJECTED")
        # Replace the hostname to avoid DNS rebinding and ambiguous resolution.
        address = ipaddress.ip_address("127.0.0.1")
    require(address.is_loopback, "REMOTE_ENDPOINT_REJECTED")
    host = f"[{address}]" if address.version == 6 else str(address)
    port = parsed.port
    return urllib.parse.urlunsplit((parsed.scheme, host + (f":{port}" if port else ""), parsed.path, "", ""))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def request_body(c: Json, prompt: str, case: Json, model_id: str, role: str) -> Json:
    return {"model": model_id,
            "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": case["input"]}],
            **c["benchmark"]["generation"], "enable_thinking": False, "stream": False,
            "enable_tools": False, "enabled_tools": [], "use_adapter": role == "lora"}


def serving_provenance(raw: Json, c: Json, role: str, model_id: str) -> Json:
    require(raw.get("model_repository") == c["model"]["repository"]
            and raw.get("model_revision") == c["model"]["revision"]
            and raw.get("model_id") == model_id and raw.get("role") == role,
            "MODEL_REVISION_MISMATCH")
    runtime = raw.get("runtime")
    require(isinstance(runtime, dict) and isinstance(runtime.get("name"), str)
            and isinstance(runtime.get("versions"), dict) and runtime["versions"],
            "BENCHMARK_PROVENANCE_MISSING")
    adapter_hash = raw.get("adapter_sha256")
    require((role == "base" and adapter_hash is None) or
            (role == "lora" and isinstance(adapter_hash, str)
             and re.fullmatch(r"[A-Fa-f0-9]{64}", adapter_hash) is not None
             and raw.get("candidate_step") == c["selection"]["candidate_step"]
             and raw.get("experiment_id") == c["experiment_id"]), "CANDIDATE_IDENTITY_MISMATCH")
    return {"model_repository": raw["model_repository"], "model_revision": raw["model_revision"],
            "model_id": model_id, "role": role, "runtime": runtime,
            "adapter_sha256": adapter_hash, "candidate_step": raw.get("candidate_step"),
            "identity_verification": "operator_supplied; not proof of server checkpoint bytes"}


def benchmark(validated: Json, endpoint: str, model_id: str, role: str,
              identity: Json, destination: Path, credential_env: str | None = None,
              timeout: float = 30) -> Json:
    endpoint = local_endpoint(endpoint)
    require(role in ["base", "lora"] and 0 < timeout <= 300, "BENCHMARK_CONFIG_INVALID")
    c = validated["contract"]
    serving = serving_provenance(identity, c, role, model_id)
    # Read only the named credential, never an arbitrary environment dump.
    credential = os.environ.get(credential_env, "") if credential_env else ""
    secrets = (credential,) if credential else ()
    provenance = sanitized({"schema_version": 1, "experiment_id": c["experiment_id"],
        "contract_sha256": validated["contract_sha256"], "tool_sha256": file_hash(Path(__file__)),
        "eval_sha256": c["artifacts"]["eval"]["sha256"], "prompt_sha256": c["canonical_prompt"]["sha256"],
        "endpoint": endpoint, "serving": serving, "generation": c["benchmark"]["generation"],
        "thinking_disabled": True, "authorization_basis": "explicit human launch of benchmark command",
        "credential_present": bool(credential), "timestamp_utc": datetime.now(timezone.utc).isoformat()}, secrets)
    provenance["credential_present"] = bool(credential)
    new_directory(destination)
    write_json_new(destination / "provenance.json", provenance)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    results = []
    # Exclusive streaming write preserves completed cases if execution stops.
    with (destination / "results.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for case in validated["eval"]:
            body = canonical_bytes(request_body(c, validated["prompt"], case, model_id, role))
            headers = {"Content-Type": "application/json"}
            if credential:
                headers["Authorization"] = "Bearer " + credential
            request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
            start = time.perf_counter()
            output = finish_reason = response_model = None
            error = None
            try:
                with opener.open(request, timeout=timeout) as response:
                    payload = load_json(response.read(2 * 1024 * 1024).decode("utf-8"))
                require(isinstance(payload.get("choices"), list) and len(payload["choices"]) == 1,
                        "API_RESPONSE_INVALID")
                choice = payload["choices"][0]
                response_model = payload.get("model")
                require(isinstance(response_model, str) and response_model == model_id, "API_MODEL_MISMATCH")
                finish_reason = choice.get("finish_reason")
                message = choice["message"]
                require(finish_reason in ["stop", "length"] and message.get("role") == "assistant"
                        and isinstance(message.get("content"), str) and not message.get("tool_calls"),
                        "API_RESPONSE_INVALID")
                require(not credential or credential not in message["content"], "CREDENTIAL_ECHO")
                output = message["content"]
            except urllib.error.HTTPError as exc:
                error = {"reason": "HTTP_ERROR", "status": exc.code}
                exc.close()
            except (urllib.error.URLError, TimeoutError, OSError):
                error = {"reason": "TRANSPORT_ERROR"}
            except ExperimentError as exc:
                error = {"reason": exc.reason}
            except (AttributeError, ValueError, KeyError, TypeError, IndexError):
                error = {"reason": "API_RESPONSE_INVALID"}
            row = {**case, "output": output, "error": error, "finish_reason": finish_reason,
                   "response_model": response_model, "latency_seconds": time.perf_counter() - start,
                   **score_case(case, output, error), "contract_sha256": validated["contract_sha256"],
                   "tool_sha256": provenance["tool_sha256"]}
            # Do not print HTTP bodies, exception messages, or headers: servers
            # can echo credentials. Redact any known credential in outputs too.
            row = sanitized(row, secrets)
            stream.write(canonical_bytes(row).decode("utf-8") + "\n")
            stream.flush()
            results.append(row)
    summary = aggregate(validated["eval"], results)
    write_json_new(destination / "summary.json", {**summary, "provenance": provenance})
    return summary


def compatible_results(validated: Json, directories: list[Path]) -> tuple[list[list[Json]], list[Json]]:
    sets, provenance = [], []
    for directory in directories:
        rows = read_jsonl(directory / "results.jsonl")
        p = read_json(directory / "provenance.json")
        require(set(index_results(rows)) == set(index_results(validated["eval"])), "EVAL_IDS_MISMATCH")
        require(p.get("contract_sha256") == validated["contract_sha256"]
                and p.get("eval_sha256") == validated["contract"]["artifacts"]["eval"]["sha256"]
                and p.get("prompt_sha256") == validated["contract"]["canonical_prompt"]["sha256"]
                and all(r.get("contract_sha256") == p["contract_sha256"]
                        and r.get("tool_sha256") == p.get("tool_sha256") for r in rows),
                "INCOMPATIBLE_PROVENANCE")
        require(all(r.get("error") is None and isinstance(r.get("output"), str)
                    and r.get("finish_reason") in ["stop", "length"] for r in rows),
                "REVIEW_INPUT_OPERATIONAL_FAILURE")
        sets.append(rows)
        provenance.append(p)
    a, b = provenance
    require({a["serving"]["role"], b["serving"]["role"]} == {"base", "lora"}
            and a.get("tool_sha256") == b.get("tool_sha256") and a.get("tool_sha256") is not None
            and a["serving"]["runtime"] == b["serving"]["runtime"]
            and a.get("generation") == b.get("generation") == validated["contract"]["benchmark"]["generation"]
            and a.get("thinking_disabled") is b.get("thinking_disabled") is True,
            "INCOMPATIBLE_PROVENANCE")
    for p in provenance:
        serving_provenance({**p["serving"], "experiment_id": p["experiment_id"]},
                           validated["contract"], p["serving"]["role"], p["serving"]["model_id"])
    return sets, provenance


def blind_pack(validated: Json, directories: list[Path], destination: Path, seed: int) -> Json:
    sets, provenance = compatible_results(validated, directories)
    indexed = [index_results(rows) for rows in sets]
    rng = random.Random(seed)
    reviews, mapping = [], []
    for case in sorted(validated["eval"], key=lambda row: row["id"]):
        order = [0, 1]
        rng.shuffle(order)
        reviews.append({k: case[k] for k in ["id", "input", "expected", "notes", "category"]} | {
            "A_output": indexed[order[0]][case["id"]]["output"],
            "B_output": indexed[order[1]][case["id"]]["output"],
            "A_rating": None, "B_rating": None, "pairwise_preference": None,
            "regression_flag": None, "reason_code": None,
        })
        mapping.append({"id": case["id"], "A_source": order[0], "B_source": order[1]})
    new_directory(destination)
    review_dir, key_dir = destination / "review", destination / "key"
    review_dir.mkdir()
    key_dir.mkdir()
    write_jsonl_new(review_dir / "review.jsonl", reviews)
    write_json_new(review_dir / "review_schema.json", {
        "rating_values": ["acceptable", "minor_defect", "unacceptable"],
        "pairwise_preference_values": ["A", "B", "tie"], "regression_flag_values": [True, False],
        "reason_code": "human-entered; critical failure codes from contract or concise defect code"})
    write_json_new(key_dir / "identity_key.json", {
        "seed": seed, "randomization": "Python random.Random(seed).shuffle per ID in sorted order",
        "python": sys.version.split()[0], "contract_sha256": validated["contract_sha256"],
        "sources": [{"directory": str(d), "provenance": sanitized(p),
                     "results_sha256": file_hash(d / "results.jsonl")} for d, p in zip(directories, provenance)],
        "mapping": mapping,
    })
    return {"cases": len(reviews), "review_file": str(review_dir / "review.jsonl"),
            "key_file": str(key_dir / "identity_key.json"), "semantic_review": "PENDING_HUMAN"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["validate-contract", "preflight", "score", "benchmark", "blind-pack"]:
        command = commands.add_parser(name)
        command.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
        if name == "preflight":
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--model-snapshot", type=Path)
        elif name == "score":
            command.add_argument("--results", type=Path, required=True)
        elif name == "benchmark":
            command.add_argument("--endpoint", required=True, help="loopback /v1/chat/completions URL")
            command.add_argument("--model-id", required=True)
            command.add_argument("--role", choices=["base", "lora"], required=True)
            command.add_argument("--serving-provenance", type=Path, required=True,
                                 help="operator-supplied model_repository, model_revision, model_id, role, runtime{name,versions}; LoRA adapter_sha256, candidate_step, experiment_id")
            command.add_argument("--credential-env")
            command.add_argument("--destination", type=Path,
                                 help="optional repository-contained destination directory")
        elif name == "blind-pack":
            command.add_argument("--base", type=Path, required=True)
            command.add_argument("--lora", type=Path, required=True)
            command.add_argument("--seed", type=int, default=3407)
            command.add_argument("--destination", type=Path,
                                 help="optional repository-contained destination directory")
    args = parser.parse_args(argv)
    try:
        v = validate_contract(args.contract)
        c = v["contract"]
        if args.command == "validate-contract":
            result = {"status": "PASSED", "contract_sha256": v["contract_sha256"],
                      "frozen_artifacts": c["artifacts"], "canonical_prompt": c["canonical_prompt"],
                      "total_optimizer_steps": c["optimizer_arithmetic"]["total_optimizer_steps"]}
        elif args.command == "preflight":
            result = preflight(v, ROOT, args.dry_run, args.model_snapshot)
        elif args.command == "score":
            result = aggregate(v["eval"], read_jsonl(args.results))
        elif args.command == "benchmark":
            destination = resolve_destination(ROOT, c, "benchmarks/" + args.role, args.destination)
            result = benchmark(v, args.endpoint, args.model_id, args.role,
                               read_json(args.serving_provenance), destination,
                               args.credential_env)
        else:
            destination = resolve_destination(ROOT, c, "blind-review", args.destination)
            result = blind_pack(v, [args.base, args.lora], destination, args.seed)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
        return int(args.command == "benchmark" and bool(result["api_errors"]))
    except ExperimentError as exc:
        print(json.dumps({"status": "FAILED", "reason": exc.reason, **sanitized(exc.details)}, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError, subprocess.SubprocessError):
        # Never echo exception strings: they may contain a credential or raw
        # transcript. Missing runtime/files/schema cannot yield a success file.
        print(json.dumps({"status": "FAILED", "reason": "INSPECTION_OR_SCHEMA_UNAVAILABLE"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
