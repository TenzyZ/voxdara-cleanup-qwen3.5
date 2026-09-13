"""Offline Run v1 checks. Only temporary files and mocked loopback HTTP mutate."""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("voxdara_experiment", ROOT / "tools/voxdara_experiment.py")
vx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vx)


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = vx.validate_contract()
        cls.c = cls.v["contract"]
        cls.cases = cls.v["eval"]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def assertReason(self, reason, function, *args, **kwargs):
        with self.assertRaises(vx.ExperimentError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.reason, reason)

    def test_frozen_provenance(self):
        expected = {
            "train": (500, "4FD564314574228EFC1539BA55EB5019CBDA474F192F78C4134AE3F97060CFAF"),
            "eval": (60, "116443FC3A6332DDB3D0250B60F02B524C745AE1836B4174D9E700783278814A"),
            "historical_base_results": (60, "B58598129C91449E1971495497FDE114D2CAAAC0C2B7EA6402C21F4EF32D9EFE"),
            "historical_base_summary": (None, "1D53280BA75B5AD47BF6331635010B145C838F9E541B83911F2C384AAE5A432C"),
        }
        for name, (count, digest) in expected.items():
            path = ROOT / self.c["artifacts"][name]["path"]
            self.assertEqual(vx.file_hash(path), digest)
            if count:
                self.assertEqual(len(vx.read_jsonl(path)), count)
        prompt = vx.derive_prompt(self.v["train"])
        self.assertEqual(len(prompt.encode("utf-8")), 481)
        self.assertEqual(vx.digest(prompt.encode("utf-8")),
                         "6BA7FD9E1EA544BA4E8BD3F5E5B974CE118EBA7B8925449E3B4399D6F1564D6D")
        rows = copy.deepcopy(self.v["train"])
        rows[0]["messages"][0]["content"] += "changed"
        self.assertReason("CANONICAL_PROMPT_MISMATCH", vx.derive_prompt, rows)

    def test_historical_aggregate(self):
        b = vx.read_jsonl(ROOT / self.c["artifacts"]["historical_base_results"]["path"])
        summary = vx.aggregate(self.cases, b)
        self.assertEqual(len(b), 60)
        self.assertEqual(summary["exact_matches"], 3)
        self.assertEqual(summary["legacy_constraint_passes"], 31)
        self.assertEqual(summary["constraint_passes"], 31)
        self.assertEqual(summary["api_errors"], 0)
        self.assertAlmostEqual(summary["latency"]["mean_seconds"], 1.36238, places=5)
        self.assertEqual(sum(r["cases"] for r in summary["categories"].values()), 60)
        # Recompute every legacy field, rather than trusting stored booleans.
        by_id = vx.index_results(self.cases)
        for row in b:
            checks = vx.score_case(by_id[row["id"]], row["output"], row["error"])
            for key in ["exact_match", "constraint_pass", "must_preserve_pass", "must_not_contain_pass"]:
                self.assertEqual(checks[key], row[key], (row["id"], key))

    def test_legacy_and_corrected_ceilings(self):
        for field, legacy, boundary in [("input", 38, 38), ("expected", 59, 60)]:
            outputs = [{"id": c["id"], "output": c[field]} for c in self.cases]
            summary = vx.aggregate(self.cases, outputs)
            self.assertEqual(summary["legacy_constraint_passes"], legacy)
            self.assertEqual(summary["boundary_constraint_passes"], boundary)

    def test_tech001_false_negative(self):
        case = vx.index_results(self.cases)["TECH-001"]
        score = vx.score_case(case, case["expected"])
        self.assertFalse(score["legacy_constraint_pass"])
        self.assertTrue(score["boundary_constraint_pass"])
        self.assertEqual(score["scoring_marker"], "LEGACY_FALSE_NEGATIVE")
        for phrase in ["npm install", "NPM INSTALL", "(npm install)", "run npm install."]:
            self.assertFalse(vx.score_case({**case, "must_preserve": []}, phrase)["boundary_constraint_pass"])
        for phrase in ["pnpm install", "xnpm install", "npm install2"]:
            self.assertTrue(vx.score_case({**case, "must_preserve": []}, phrase)["boundary_constraint_pass"])
        literal = {**case, "must_preserve": [], "must_not_contain": ["a.b"]}
        self.assertTrue(vx.score_case(literal, "axb")["boundary_constraint_pass"])
        self.assertFalse(vx.score_case(literal, "A.B")["boundary_constraint_pass"])

    def test_error_accounting_and_p95(self):
        results = [{"id": c["id"], "output": c["expected"], "latency_seconds": i + 1}
                   for i, c in enumerate(self.cases)]
        results[0].update(output=None, error={"reason": "HTTP_ERROR"})
        results[1]["finish_reason"] = "length"
        summary = vx.aggregate(self.cases, results)
        self.assertEqual(summary["outputs"], 59)
        self.assertEqual(summary["api_errors"], 1)
        self.assertEqual(summary["truncations"], 1)
        self.assertEqual(summary["latency"]["p95_seconds"], 57)
        self.assertReason("EVAL_IDS_MISMATCH", vx.aggregate, self.cases, results[:-1])
        self.assertReason("DUPLICATE_EVAL_ID", vx.aggregate, self.cases, results + [results[0]])

    def modified_contract(self, edit):
        contract = copy.deepcopy(self.c)
        edit(contract)
        path = self.path / "contract.json"
        path.write_text(json.dumps(contract), encoding="utf-8")
        return path

    def test_contract_hash_serialization(self):
        reverse = {key: self.c[key] for key in reversed(self.c)}
        self.assertEqual(vx.canonical_bytes(reverse), vx.canonical_bytes(self.c))
        self.assertEqual(vx.digest(vx.canonical_bytes(reverse)), vx.APPROVED_CONTRACT_SHA256)
        path = self.path / "contract.json"
        path.write_text(json.dumps(reverse, indent=4), encoding="utf-8")
        self.assertEqual(vx.validate_contract(path)["contract_sha256"], self.v["contract_sha256"])
        self.assertEqual(vx.canonical_bytes({"x": "é"}), '{"x":"é"}'.encode("utf-8"))
        self.assertReason("DUPLICATE_JSON_KEY", vx.load_json, '{"x":1,"x":2}')

    def test_invalid_contract_rejected(self):
        for reason, edit in [
            ("FROZEN_HASH_MISMATCH", lambda c: c["artifacts"]["train"].update(sha256="0" * 64)),
            ("FROZEN_COUNT_MISMATCH", lambda c: c["artifacts"]["eval"].update(rows=59)),
            ("OPTIMIZER_ARITHMETIC_MISMATCH", lambda c: c["optimizer_arithmetic"].update(total_optimizer_steps=125)),
            ("CONTRACT_DRIFT", lambda c: c["training"].update(weight_decay=0.001)),
            ("CONTRACT_DRIFT", lambda c: c["selection"].update(validation="Eval v1")),
            ("CONTRACT_DRIFT", lambda c: c["scoring"].update(expected_gold_boundary=59)),
            ("CONTRACT_DRIFT", lambda c: c["acceptance"]["PASS"].update(boundary_constraints_min=38)),
        ]:
            with self.subTest(reason=reason):
                self.assertReason(reason, vx.validate_contract, self.modified_contract(edit))

    def test_preregistered_run_policy(self):
        t, selection = self.c["training"], self.c["selection"]
        self.assertEqual(t["max_seq_length"], 256)
        self.assertEqual((t["num_epochs"], t["batch_size"], t["gradient_accumulation_steps"]), (2, 2, 4))
        self.assertEqual(self.c["optimizer_arithmetic"]["total_optimizer_steps"], 126)
        self.assertEqual(selection["candidate_step"], 126)
        self.assertEqual(selection["candidate"], "final_adapter")
        self.assertEqual(selection["diagnostic_checkpoint_step"], 63)
        self.assertFalse(selection["diagnostic_checkpoint_eval_v1_allowed"])
        self.assertTrue({"training", "validation", "checkpoint_selection", "hyperparameter_selection",
                         "epoch_selection", "learning_rate_selection", "early_stopping"}
                        <= set(selection["eval_v1_prohibited_for"]))
        self.assertTrue(t["train_on_completions"])
        self.assertFalse(t["assistant_only_loss"])
        self.assertEqual(t["effective_trainer_max_steps"], -1)
        self.assertEqual(t["weight_decay"], 0.01)
        self.assertEqual(t["report_to"], [])

    def mocked_runtime(self, free=5):
        targets = {k: self.c["lora"]["expected_" + k] for k in
                   ["modules", "trainable_parameters", "vision_matches", "mtp_matches"]}
        targets["modules_sha256"] = vx.digest(vx.canonical_bytes(sorted(
            f"model.language_model.layers.{i}.mlp.up_proj" for i in range(96))))
        live = {**targets, "foreign_modules": 0, "non_lora_trainable": 0}
        return {
            **{k: self.c["runtime"][k] for k in ["python", "cuda", "outer_versions", "effective_versions", "effective_transformers_tier"]},
            "gpu": {"available": True, "name": "NVIDIA GeForce RTX 3050 6GB Laptop GPU", "free_gib": free,
                    "total_gib": 6, "compute_capability": [8, 6], "bf16_supported": True},
            "masking": {"rows": 500, "max_rendered_tokens": 255, "mean_rendered_tokens": 137.146,
                        "mean_supervised_tokens": 17.102, "fully_masked_rows": 0, "prefix_mismatches": 0,
                        "supervision_leaks": 0, "raw_assistant_mask_nonzero_rows": 0},
            "target_resolution": {**targets, "live_peft_resolution": "VERIFIED",
                                  "live": {"regex": dict(live), "list": dict(live)}},
        }

    def report(self, free=5):
        runtime = self.mocked_runtime(free)
        return {"contract_sha256": self.v["contract_sha256"], "tool_sha256": vx.file_hash(ROOT / "tools/voxdara_experiment.py"),
                "git": {"commit": self.c["baseline_git_commit"], "dirty": True},
                "runtime": runtime, "gates": vx.launch_gates(self.c, runtime)}

    def test_failed_gate_creates_no_manifest(self):
        destination = self.path / "run"
        self.assertReason("VRAM_GATE_FAILED", vx.finish_preflight, self.report(3.5), destination, False)
        self.assertFalse(destination.exists())
        self.assertReason("VRAM_GATE_FAILED", vx.finish_preflight, self.report(3.5), destination, True)
        self.assertFalse(destination.exists())

    def test_preflight_manifest_safe_and_exclusive(self):
        destination = self.path / "run"
        report = self.report()
        report["api_key"] = "mocked-sensitive-value"
        vx.finish_preflight(report, destination, False)
        path = destination / "preflight.json"
        before = path.read_bytes()
        self.assertNotIn(b"mocked-sensitive-value", before)
        manifest = vx.read_json(path)
        self.assertEqual(manifest["contract_sha256"], self.v["contract_sha256"])
        self.assertTrue(manifest["git"]["dirty"])
        self.assertFalse(manifest["training_authorized"])
        self.assertEqual(manifest["runtime"]["masking"]["max_rendered_tokens"], 255)
        self.assertReason("OUTPUT_ALREADY_EXISTS", vx.finish_preflight, report, destination, False)
        self.assertEqual(path.read_bytes(), before)

    def test_dry_preflight_never_writes(self):
        destination = self.path / "run"
        result = vx.finish_preflight(self.report(), destination, True)
        self.assertEqual(result["status"], "PASSED")
        self.assertTrue(result["dry_run"])
        self.assertFalse(destination.exists())

    def test_runtime_launch_gate_failures(self):
        for reason, edit in [
            ("SEQUENCE_TOO_LONG", lambda r: r["masking"].update(max_rendered_tokens=257)),
            ("ZERO_COMPLETION_MASK", lambda r: r["masking"].update(fully_masked_rows=1)),
            ("SUPERVISION_LEAK", lambda r: r["masking"].update(supervision_leaks=1)),
            ("TARGET_MODULE_MISMATCH", lambda r: r["target_resolution"].update(modules=97)),
            ("RUNTIME_VERSION_MISMATCH", lambda r: r.update(python="3.14")),
        ]:
            runtime = self.mocked_runtime()
            edit(runtime)
            failures = [g["reason"] for g in vx.launch_gates(self.c, runtime) if not g["passed"]]
            self.assertIn(reason, failures)

    def test_exact_adapter_path_allowlist(self):
        for component, leaves in [("self_attn", ["q_proj", "k_proj", "v_proj", "o_proj"]),
                                  ("mlp", ["gate_proj", "up_proj", "down_proj"])]:
            for leaf in leaves:
                name = f"model.language_model.layers.0.{component}.{leaf}"
                self.assertIsNotNone(vx.ALLOWED_MODULE.fullmatch(name), name)
        for name in ["mtp.layers.0.self_attn.q_proj", "mtp.layers.0.mlp.down_proj",
                     "model.visual.blocks.0.mlp.linear_fc1",
                     "model.language_model.layers.0.self_attn.some_new_proj",
                     "model.language_model.layers.0.mlp.some_new_proj",
                     "model.language_model.layers.0.self_attn.q_proj.extra",
                     "other.model.language_model.layers.0.self_attn.q_proj"]:
            self.assertIsNone(vx.ALLOWED_MODULE.fullmatch(name), name)

    def test_live_adapter_classification_happy_path(self):
        modules = [f"model.language_model.layers.{i}.mlp.up_proj" for i in range(96)]
        total = self.c["lora"]["expected_trainable_parameters"]
        for prefix in ["", "base_model.model."]:
            names = [prefix + name for name in modules]
            trainable = {f"{name}.lora_{side}.default.weight": total // (2 * len(names))
                         for name in names for side in ["A", "B"]}
            evidence = vx.classify_adapter(names, trainable)
            self.assertEqual(evidence, {"modules": 96, "trainable_parameters": 6389760,
                                       "modules_sha256": vx.digest(vx.canonical_bytes(sorted(modules))),
                                       "mtp_matches": 0, "vision_matches": 0,
                                       "foreign_modules": 0, "non_lora_trainable": 0})
            runtime = self.mocked_runtime()
            runtime["target_resolution"]["live"] = {"regex": evidence, "list": evidence}
            result = vx.finish_preflight(
                {"gates": vx.launch_gates(self.c, runtime)}, self.path / "run", True)
            self.assertEqual(result["status"], "PASSED")
            self.assertFalse(result["training_authorized"])
            self.assertFalse((self.path / "run").exists())

    def test_allowed_identity_substitutions_fail_closed(self):
        # Shapes verified from the frozen model's layer-3 checkpoint headers.
        shapes = {"mlp.gate_proj": (3584, 1024), "mlp.up_proj": (3584, 1024),
                  "mlp.down_proj": (1024, 3584), "self_attn.q_proj": (4096, 1024),
                  "self_attn.k_proj": (512, 1024), "self_attn.v_proj": (512, 1024),
                  "self_attn.o_proj": (1024, 2048)}
        modules = {f"model.language_model.layers.{layer}.{leaf}": shape
                   for layer in range(24) for leaf, shape in shapes.items()
                   if leaf.startswith("mlp.") or layer % 4 == 3}
        def classify(replacements):
            names = [replacements.get(name, name) for name in modules]
            trainable = {
                f"base_model.model.{replacements.get(name, name)}.lora_{side}.default.weight":
                    self.c["lora"]["rank"] * dimension
                for name, shape in modules.items() for side, dimension in zip(["B", "A"], shape)
            }
            return vx.classify_adapter(["base_model.model." + name for name in names], trainable)
        expected = classify({})
        single = {"model.language_model.layers.0.mlp.up_proj":
                  "model.language_model.layers.99.mlp.up_proj"}
        renested = {f"model.language_model.layers.3.{leaf}":
                    f"model.language_model.layers.24.{leaf}" for leaf in shapes}
        for label, replacements in [("single_identity", single), ("seven_renested_mtp", renested)]:
            evidence = classify(replacements)
            self.assertEqual({k: v for k, v in evidence.items() if k != "modules_sha256"},
                             {"modules": 96, "trainable_parameters": 6389760,
                              "mtp_matches": 0, "vision_matches": 0,
                              "foreign_modules": 0, "non_lora_trainable": 0})
            self.assertNotEqual(evidence["modules_sha256"], expected["modules_sha256"])
            for resolution in ["regex", "list"]:
                with self.subTest(case=label, resolution=resolution):
                    runtime = self.mocked_runtime()
                    targets = runtime["target_resolution"]
                    targets["modules_sha256"] = expected["modules_sha256"]
                    targets["live"] = {"regex": dict(expected), "list": dict(expected)}
                    targets["live"][resolution] = evidence
                    self.assertReason("TARGET_MODULE_MISMATCH", vx.finish_preflight,
                                      {"gates": vx.launch_gates(self.c, runtime)}, self.path / "run", True)
                    targets["live"][resolution] = expected
                    result = vx.finish_preflight(
                        {"gates": vx.launch_gates(self.c, runtime)}, self.path / "run", True)
                    self.assertEqual(result["status"], "PASSED")

    def test_live_adapter_contamination_fails_closed(self):
        modules = [f"model.language_model.layers.{i}.mlp.up_proj" for i in range(103)]
        total = self.c["lora"]["expected_trainable_parameters"]
        cases = [(f"count_{count}", modules[:count], total, {}, 0, 0, 0)
                 for count in [95, 97, 103]]
        for name, mtp, vision in [
            ("mtp.layers.0.self_attn.q_proj", 1, 0),
            ("model.mtp.layers.0.mlp.down_proj", 1, 0),
            ("model.visual.blocks.0.mlp.linear_fc1", 0, 1),
            ("model.vision_tower.blocks.0.q_proj", 0, 1),
            ("model.vision_model.blocks.0.q_proj", 0, 1),
            ("model.visual_tokenizer.blocks.0.q_proj", 0, 1),
            ("model.language_model.other.q_proj", 0, 0),
            ("model.language_model.layers.0.self_attn.some_new_proj", 0, 0),
        ]:
            cases.append((name, modules[:95] + [name], total, {}, mtp, vision, 1))
        cases.extend([
            ("wrong_total", modules[:96], total + 1, {}, 0, 0, 0),
            ("non_lora", modules[:96], total,
             {"base_model.model.model.language_model.embed_tokens.weight": 16}, 0, 0, 0),
            ("misleading_lora_name", modules[:96], total,
             {"base_model.model.model.language_model.embed_tokens.lora_A.default.weight": 16},
             0, 0, 0),
        ])
        for label, names, parameter_total, extra, mtp, vision, foreign in cases:
            names = ["base_model.model." + name for name in names]
            lora_total = parameter_total - sum(extra.values())
            trainable = {f"{name}.lora_A.default.weight": lora_total // len(names) for name in names}
            trainable[f"{names[0]}.lora_A.default.weight"] += lora_total % len(names)
            evidence = vx.classify_adapter(names, {**trainable, **extra})
            self.assertEqual(evidence["modules"], len(names))
            self.assertEqual(evidence["trainable_parameters"], parameter_total)
            self.assertEqual(evidence["mtp_matches"], mtp)
            self.assertEqual(evidence["vision_matches"], vision)
            self.assertEqual(evidence["foreign_modules"], foreign)
            self.assertEqual(evidence["non_lora_trainable"], sum(extra.values()))
            for resolution in ["regex", "list"]:
                with self.subTest(case=label, resolution=resolution):
                    runtime = self.mocked_runtime()
                    runtime["target_resolution"]["live"][resolution] = evidence
                    destination = self.path / "run"
                    self.assertReason("TARGET_MODULE_MISMATCH", vx.finish_preflight,
                                      {"gates": vx.launch_gates(self.c, runtime)}, destination, True)
                    self.assertFalse(destination.exists())

    def test_missing_live_adapter_evidence_fails_closed(self):
        for missing in ["regex", "list", "live_peft_resolution", "modules_sha256",
                        "regex_digest", "list_digest", "all_digests"]:
            runtime = self.mocked_runtime()
            targets = runtime["target_resolution"]
            if missing in ["live_peft_resolution", "modules_sha256"]:
                del targets[missing]
            elif missing.endswith("_digest"):
                del targets["live"][missing.removesuffix("_digest")]["modules_sha256"]
            elif missing == "all_digests":
                del targets["modules_sha256"]
                for resolution in targets["live"].values():
                    del resolution["modules_sha256"]
            else:
                del targets["live"][missing]
            self.assertReason("TARGET_MODULE_MISMATCH", vx.finish_preflight,
                              {"gates": vx.launch_gates(self.c, runtime)}, self.path / "run", True)

    def test_cached_tensor_headers_reject_incomplete_or_wrong_precision(self):
        shard = "model.safetensors"
        name = "model.language_model.layers.0.self_attn.q_proj.weight"
        vx.write_json_new(self.path / "model.safetensors.index.json", {"weight_map": {name: shard}})
        header = {name: {"dtype": "BF16", "shape": [8, 4], "data_offsets": [0, 64]}}
        def write_header():
            raw = vx.canonical_bytes(header)
            (self.path / shard).write_bytes(struct.pack("<Q", len(raw)) + raw + bytes(64))
        write_header()
        result = vx.target_metadata(self.path, self.c["lora"])
        self.assertEqual(result["modules"], 1)
        self.assertEqual(result["trainable_parameters"], 192)
        self.assertEqual(result["modules_sha256"],
                         vx.digest(vx.canonical_bytes([name.removesuffix(".weight")])))
        complete = (self.path / shard).read_bytes()
        (self.path / shard).write_bytes(complete[:-1])
        self.assertReason("MODEL_CACHE_INCOMPLETE", vx.target_metadata, self.path, self.c["lora"])
        header[name]["dtype"] = "F16"
        write_header()
        self.assertReason("MODEL_PRECISION_MISMATCH", vx.target_metadata, self.path, self.c["lora"])

    def identity(self, role="base"):
        return {"model_repository": self.c["model"]["repository"], "model_revision": self.c["model"]["revision"],
                "model_id": "serving-" + role, "role": role, "runtime": {"name": "mocked Studio", "versions": {"transformers": "5.3.0"}},
                "adapter_sha256": "A" * 64 if role == "lora" else None,
                "candidate_step": 126 if role == "lora" else None, "experiment_id": self.c["experiment_id"]}

    def server(self, responder=None):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, body, self.headers.get("Authorization")))
                payload = (responder(body, len(requests)) if responder else
                           {"model": body["model"], "choices": [{"finish_reason": "stop",
                            "message": {"role": "assistant", "content": body["messages"][1]["content"]}}]})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(cleanup)
        return f"http://127.0.0.1:{server.server_port}/v1/chat/completions", requests

    def test_benchmark_transport_all_frozen_cases(self):
        endpoint, requests = self.server()
        destination = self.path / "base"
        with patch.dict(os.environ, {"VOXDARA_MOCK_AUTH": "mock-http-credential"}):
            summary = vx.benchmark(self.v, endpoint, "serving-base", "base", self.identity(), destination, "VOXDARA_MOCK_AUTH")
        self.assertEqual(len(requests), 60)
        self.assertEqual(summary["api_errors"], 0)
        self.assertEqual(summary["legacy_constraint_passes"], 38)
        for case, (path, body, auth) in zip(self.cases, requests):
            self.assertEqual(path, "/v1/chat/completions")
            self.assertEqual(auth, "Bearer mock-http-credential")
            self.assertEqual(body["messages"], [{"role": "system", "content": self.v["prompt"]},
                                               {"role": "user", "content": case["input"]}])
            for key, value in self.c["benchmark"]["generation"].items():
                self.assertEqual(body[key], value)
            self.assertFalse(body["enable_thinking"])
            self.assertFalse(body["stream"])
            self.assertFalse(body["enable_tools"])
            self.assertFalse(body["use_adapter"])
            self.assertEqual(body["enabled_tools"], [])
            self.assertEqual(vx.canonical_bytes(body), vx.canonical_bytes(vx.request_body(self.c, self.v["prompt"], case, "serving-base", "base")))
        for path in destination.iterdir():
            self.assertNotIn(b"mock-http-credential", path.read_bytes())
        self.assertTrue(vx.read_json(destination / "provenance.json")["credential_present"])
        self.assertReason("OUTPUT_ALREADY_EXISTS", vx.benchmark, self.v, endpoint, "serving-base", "base", self.identity(), destination)
        self.assertEqual(len(requests), 60)

    def test_api_error_and_credential_echo_are_sanitized(self):
        def respond(body, number):
            if number == 1:
                return {"error": {"message": "mock-echo-secret"}}
            return {"model": body["model"], "choices": [{"finish_reason": "length", "message": {
                "role": "assistant", "content": "mock-echo-secret"}}]}
        endpoint, requests = self.server(respond)
        subset = {**self.v, "eval": self.cases[:2]}
        destination = self.path / "echo"
        with patch.dict(os.environ, {"VOXDARA_MOCK_AUTH": "mock-echo-secret"}):
            result = vx.benchmark(subset, endpoint, "serving-base", "base", self.identity(), destination, "VOXDARA_MOCK_AUTH")
        self.assertEqual(len(requests), 2)
        rows = vx.read_jsonl(destination / "results.jsonl")
        self.assertIsNone(rows[0]["output"])
        self.assertEqual(result["api_errors"], 2)
        self.assertIsNone(rows[1]["output"])
        self.assertEqual(rows[1]["error"]["reason"], "CREDENTIAL_ECHO")
        self.assertEqual(result["truncations"], 1)
        for path in destination.iterdir():
            self.assertNotIn(b"mock-echo-secret", path.read_bytes())

    def test_remote_endpoint_and_redirect_rejected(self):
        for endpoint in ["https://example.com/v1/chat/completions", "http://192.168.1.2/v1/chat/completions",
                         "http://127.0.0.1@evil.test/v1/chat/completions", "file:///v1/chat/completions",
                         "http://127.0.0.1/v1/chat/completions?token=secret", "http://localhost.evil/v1/chat/completions"]:
            self.assertReason("REMOTE_ENDPOINT_REJECTED", vx.local_endpoint, endpoint)
        self.assertEqual(vx.local_endpoint("http://localhost:8888/v1/chat/completions"),
                         "http://127.0.0.1:8888/v1/chat/completions")
        self.assertEqual(vx.local_endpoint("http://[::1]:8888/v1/chat/completions"),
                         "http://[::1]:8888/v1/chat/completions")
        self.assertIsNone(vx.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test"))

    def result_set(self, role):
        path = self.path / role
        path.mkdir()
        identity = self.identity(role)
        tool_hash = vx.file_hash(ROOT / "tools/voxdara_experiment.py")
        provenance = {"experiment_id": self.c["experiment_id"], "contract_sha256": self.v["contract_sha256"],
                      "tool_sha256": tool_hash, "eval_sha256": self.c["artifacts"]["eval"]["sha256"],
                      "prompt_sha256": self.c["canonical_prompt"]["sha256"], "serving": identity,
                      "generation": self.c["benchmark"]["generation"], "thinking_disabled": True}
        content = "one" if role == "base" else "two"
        rows = [{"id": c["id"], "output": f"mocked content {content} {c['id']}", "error": None, "finish_reason": "stop",
                 "contract_sha256": self.v["contract_sha256"], "tool_sha256": tool_hash} for c in self.cases]
        vx.write_json_new(path / "provenance.json", provenance)
        vx.write_jsonl_new(path / "results.jsonl", rows)
        return path

    def test_blind_pair_is_deterministic_and_key_is_separate(self):
        # Outputs naturally may mention model names in dictated content. Hide
        # source metadata, never censor transcript content to manufacture blinding.
        base, lora = self.result_set("base"), self.result_set("lora")
        first, second = self.path / "pack1", self.path / "pack2"
        result = vx.blind_pack(self.v, [base, lora], first, 3407)
        vx.blind_pack(self.v, [base, lora], second, 3407)
        self.assertEqual(result["review_file"], str(first / "review/review.jsonl"))
        self.assertEqual(result["key_file"], str(first / "key/identity_key.json"))
        for destination in [first, second]:
            self.assertEqual({p.name for p in destination.iterdir()}, {"review", "key"})
            self.assertEqual({p.name for p in (destination / "review").iterdir()},
                             {"review.jsonl", "review_schema.json"})
            self.assertEqual({p.name for p in (destination / "key").iterdir()}, {"identity_key.json"})
            self.assertFalse((destination / "review/identity_key.json").exists())
        self.assertEqual((first / "review/review.jsonl").read_bytes(), (second / "review/review.jsonl").read_bytes())
        self.assertEqual(vx.read_json(first / "key/identity_key.json")["mapping"], vx.read_json(second / "key/identity_key.json")["mapping"])
        key = vx.read_json(first / "key/identity_key.json")
        reviews = vx.read_jsonl(first / "review/review.jsonl")
        sets = [vx.index_results(vx.read_jsonl(p / "results.jsonl")) for p in [base, lora]]
        for row, mapping in zip(reviews, key["mapping"]):
            self.assertEqual(row["A_output"], sets[mapping["A_source"]][row["id"]]["output"])
            self.assertEqual(row["B_output"], sets[mapping["B_source"]][row["id"]]["output"])
            self.assertEqual(set(row), {"id", "input", "expected", "notes", "category", "A_output", "B_output",
                                        "A_rating", "B_rating", "pairwise_preference", "regression_flag", "reason_code"})
            self.assertIsNone(row["A_rating"])
        for path in (first / "review").iterdir():
            for marker in [b"serving-base", b"serving-lora", b"model_repository", b"provenance",
                           b"A_source", b"B_source", b"role"]:
                self.assertNotIn(marker, path.read_bytes())
        self.assertReason("OUTPUT_ALREADY_EXISTS", vx.blind_pack, self.v, [base, lora], first, 3407)

    def test_blind_pair_rejects_mismatched_ids_and_provenance(self):
        base, lora = self.result_set("base"), self.result_set("lora")
        results = lora / "results.jsonl"
        original = results.read_bytes()
        results.write_bytes(b"\n".join(original.splitlines()[:-1]) + b"\n")
        destination = self.path / "badpack"
        self.assertReason("EVAL_IDS_MISMATCH", vx.blind_pack, self.v, [base, lora], destination, 3407)
        self.assertFalse(destination.exists())
        results.write_bytes(original)
        path = lora / "provenance.json"
        provenance = vx.read_json(path)
        provenance["serving"]["runtime"]["versions"]["transformers"] = "different"
        path.write_text(json.dumps(provenance), encoding="utf-8")
        self.assertReason("INCOMPATIBLE_PROVENANCE", vx.blind_pack, self.v, [base, lora], destination, 3407)
        self.assertFalse(destination.exists())

    def test_blind_pair_rejects_invalid_roles_and_tool_hash_mismatch(self):
        base, lora = self.result_set("base"), self.result_set("lora")
        path = lora / "provenance.json"
        original = vx.read_json(path)
        provenance = copy.deepcopy(original)
        provenance["serving"]["role"] = "base"
        path.write_text(json.dumps(provenance), encoding="utf-8")
        destination = self.path / "badroles"
        self.assertReason("INCOMPATIBLE_PROVENANCE", vx.blind_pack, self.v, [base, lora], destination, 3407)
        self.assertFalse(destination.exists())

        provenance = copy.deepcopy(original)
        provenance["tool_sha256"] = "0" * 64
        path.write_text(json.dumps(provenance), encoding="utf-8")
        results = lora / "results.jsonl"
        rows = vx.read_jsonl(results)
        for row in rows:
            row["tool_sha256"] = provenance["tool_sha256"]
        results.write_text("".join(vx.canonical_bytes(row).decode("utf-8") + "\n" for row in rows),
                           encoding="utf-8")
        destination = self.path / "badhash"
        self.assertReason("INCOMPATIBLE_PROVENANCE", vx.blind_pack, self.v, [base, lora], destination, 3407)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
