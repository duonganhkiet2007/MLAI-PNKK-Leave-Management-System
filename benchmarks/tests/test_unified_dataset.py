import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "benchmarks" / "datasets" / "unified_cases.json"


def test_unified_case_counts_and_unique_ids():
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = dataset["cases"]

    assert dataset["total_cases"] == 158
    assert dataset["source_counts"] == {
        "policy_benchmark": 120,
        "repository_case_bank": 38,
    }
    assert len({case["id"] for case in cases}) == 158


def test_every_present_proof_has_an_image_file():
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    for case in dataset["cases"]:
        evidence = case["evidence"]
        if evidence["present"]:
            assert evidence["image_path"].startswith("benchmarks/datasets/unified_proofs/")
            image_path = ROOT / evidence["image_path"]
            assert image_path.is_file(), case["id"]
        else:
            assert evidence["image_path"] is None, case["id"]