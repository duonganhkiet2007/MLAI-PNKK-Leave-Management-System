"""Merge policy benchmark and repository case-bank fixtures."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import esprima
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "unified_cases.json"
GENERATED_PROOFS = HERE / "unified_proofs"
NON_VISUAL_PROOF_FIELDS = {"proof_verification_status", "verified_by"}


def _literal_value(node):
    if node.type == "Literal":
        return node.value
    if node.type == "ArrayExpression":
        return [_literal_value(item) for item in node.elements]
    if node.type == "ObjectExpression":
        result = {}
        for prop in node.properties:
            if prop.type != "Property" or prop.kind != "init":
                raise ValueError(f"Unsupported object property: {prop.type}")
            key = prop.key.name if prop.key.type == "Identifier" else prop.key.value
            result[key] = _literal_value(prop.value)
        return result
    if node.type == "UnaryExpression" and node.operator in ("-", "+"):
        value = _literal_value(node.argument)
        return -value if node.operator == "-" else value
    raise ValueError(f"Unsupported JavaScript literal: {node.type}")


def _read_declaration(source: str, name: str, terminator: str):
    start = source.index(f"const {name} = ")
    end = source.index(terminator, start) + len(terminator)
    declaration = esprima.parseScript(source[start:end]).body[0].declarations[0]
    return _literal_value(declaration.init)


def _font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _render_evidence(case: dict, proof: dict, path: Path):
    image = Image.new("RGB", (1100, 1450), (250, 250, 248))
    draw = ImageDraw.Draw(image)
    heading_font = _font(34)
    body_font = _font(25)
    small_font = _font(17)
    proof_type = str(proof.get("proof_type") or "OTHER")
    is_medical = "MEDICAL" in proof_type or "HOSPITAL" in proof_type
    title_map = {
        "MEDICAL_LEAVE_CERTIFICATE": "GIẤY CHỨNG NHẬN NGHỈ ỐM",
        "HOSPITAL_DISCHARGE": "GIẤY RA VIỆN",
        "MARRIAGE_CERTIFICATE": "GIẤY CHỨNG NHẬN KẾT HÔN",
        "DEATH_CERTIFICATE": "TRÍCH LỤC KHAI TỬ",
    }
    title = title_map.get(proof_type, proof_type.replace("_", " "))
    draw.rectangle((55, 50, 1045, 150), fill=(246, 248, 251))
    issuer_heading = "CƠ SỞ Y TẾ MÔ PHỎNG" if is_medical else "CƠ QUAN CẤP MÔ PHỎNG"
    draw.text((75, 76), issuer_heading, font=heading_font, fill=(30, 57, 94))
    draw.line((65, 175, 1035, 175), fill=(120, 130, 145), width=2)
    draw.text((85, 215), title, font=heading_font, fill=(155, 35, 35))

    request = case.get("request") or {}
    rows = [
        ("Loại chứng từ", proof_type),
        ("Nơi cấp", proof.get("issuer") or "Cơ sở y tế mô phỏng"),
        ("Tên trên giấy", proof.get("patient_name") or proof.get("subject_name") or request.get("employee_name") or "Không ghi"),
        ("Ngày cấp", proof.get("issue_date") or "Không ghi"),
    ]
    if is_medical:
        rows.extend([
            ("Chẩn đoán", proof.get("diagnosis") or request.get("reason") or "Không ghi"),
            ("Bác sĩ chỉ định từ ngày", proof.get("recommended_from_date") or "Không ghi"),
            ("Bác sĩ chỉ định đến ngày", proof.get("recommended_to_date") or "Không ghi"),
        ])
    else:
        rows.append(("Sự kiện / nội dung", proof.get("event_type") or request.get("reason") or "Không ghi"))
        rows.append(("Ngày sự kiện", proof.get("event_date") or proof.get("date_of_death") or "Không ghi"))
    y = 310
    for label, value in rows:
        draw.text((85, y), label + ":", font=body_font, fill=(45, 48, 53))
        value = str(value)
        draw.text((440, y), value[:52], font=body_font, fill=(30, 33, 38))
        if len(value) > 52:
            draw.text((440, y + 35), value[52:104], font=body_font, fill=(30, 33, 38))
            y += 40
        y += 92

    draw.rectangle((80, y + 5, 1020, y + 145), outline=(188, 198, 210), width=2)
    draw.text((100, y + 28), "GHI CHÚ / HƯỚNG DẪN", font=body_font, fill=(155, 35, 35))
    draw.text((100, y + 80), "Tài liệu tổng hợp phục vụ kiểm thử hệ thống.", font=small_font, fill=(55, 60, 68))

    if proof.get("signature_present") is True or proof.get("digital_signature_present") is True:
        draw.line((690, 1050, 740, 1000, 785, 1060, 835, 990, 900, 1040), fill=(25, 55, 155), width=4)
        draw.text((690, 1070), "Chữ ký minh họa", font=small_font, fill=(30, 40, 100))
    if proof.get("has_red_stamp") is True:
        draw.ellipse((790, 1120, 970, 1300), outline=(190, 25, 25), width=6)
        draw.text((814, 1175), "DẤU MÔ PHỎNG", font=small_font, fill=(180, 25, 25))
    draw.text((75, 1370), "SYNTHETIC QA FIXTURE - NOT AN OFFICIAL DOCUMENT", font=small_font, fill=(105, 110, 118))

    readability = str(proof.get("document_readability") or "").upper()
    if readability in ("UNREADABLE", "ILLEGIBLE"):
        image = image.filter(ImageFilter.GaussianBlur(8))
        image = ImageEnhance.Contrast(image).enhance(0.55)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def _evidence(case: dict, proof: dict | None, source_image: str | None = None):
    if not proof:
        return {"present": False, "image_path": None, "annotation": None, "synthetic": True}

    if source_image:
        source_path = ROOT / "frontend" / "assets" / "proofs" / source_image
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        filename = case["id"].replace(":", "-").replace("/", "-") + ".png"
        image_path = GENERATED_PROOFS / filename
        image_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, image_path)
        relative_path = image_path.relative_to(ROOT).as_posix()
    else:
        filename = case["id"].replace(":", "-").replace("/", "-") + ".png"
        image_path = GENERATED_PROOFS / filename
        _render_evidence(case, proof, image_path)
        relative_path = image_path.relative_to(ROOT).as_posix()

    annotation = {key: value for key, value in proof.items() if key not in NON_VISUAL_PROOF_FIELDS}
    trusted_metadata = {key: value for key, value in proof.items() if key in NON_VISUAL_PROOF_FIELDS}
    return {
        "present": True,
        "image_path": relative_path,
        "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "annotation": annotation,
        "trusted_metadata": trusted_metadata,
        "synthetic": True,
    }


def build():
    frontend = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    repo_cases = _read_declaration(frontend, "STAFF_TEST_CASES", "\n];")
    proof_map = _read_declaration(frontend, "TESTCASE_PROOF_MAP", "\n};")
    employee_names = _read_declaration(frontend, "EMP_NAME_MAP", "\n};")

    applications = json.loads((HERE / "applications.json").read_text(encoding="utf-8"))
    ground_truth = json.loads((HERE / "ground_truth.json").read_text(encoding="utf-8"))
    policy_cases = [case for case in applications if case.get("kind") == "policy"]
    if (len(repo_cases), len(policy_cases)) != (38, 120):
        raise ValueError(f"Expected 38 repository and 120 policy cases; got {len(repo_cases)} and {len(policy_cases)}")

    merged = []
    for source_case in policy_cases:
        case_id = source_case["id"]
        truth = ground_truth[case_id]
        record = {
            "id": f"policy:{case_id}",
            "source": "policy_benchmark",
            "source_case_id": case_id,
            "category": source_case["category"],
            "kind": "policy",
            "request": source_case["request"],
            "expected": truth["expected"],
            "ground_truth": {k: v for k, v in truth.items() if k != "expected"},
            "synthetic": True,
        }
        record["evidence"] = _evidence(record, source_case["request"].get("proof"))
        merged.append(record)

    for source_case in repo_cases:
        case_id = source_case["id"]
        request = {
            "employee_id": source_case.get("primaryEmpId"),
            "employee_name": employee_names.get(source_case.get("primaryEmpId")),
            **source_case.get("payload", {}),
        }
        record = {
            "id": f"repo:{case_id}",
            "source": "repository_case_bank",
            "source_case_id": case_id,
            "title": source_case.get("title"),
            "description": source_case.get("desc"),
            "kind": "leave_request",
            "request": request,
            "expected": source_case["expected"],
            "synthetic": True,
        }
        proof_mapping = proof_map.get(case_id) or {}
        record["evidence"] = _evidence(
            record,
            request.get("proof"),
            proof_mapping.get("file"),
        )
        merged.append(record)

    ids = [case["id"] for case in merged]
    if len(ids) != len(set(ids)):
        raise ValueError("Unified case IDs must be unique")
    cases_with_evidence = sum(case["evidence"]["present"] for case in merged)
    payload = {
        "version": 1,
        "total_cases": len(merged),
        "source_counts": {"policy_benchmark": len(policy_cases), "repository_case_bank": len(repo_cases)},
        "cases_with_evidence_images": cases_with_evidence,
        "cases_without_evidence_images": len(merged) - cases_with_evidence,
        "deduplicated": False,
        "limitations": [
            "All identities and generated evidence are synthetic QA fixtures, not official documents.",
            "Policy benchmark images are for image-input coverage; policy ground truth was authored on structured proof fields.",
            "The repository case bank's existing proof images are copied as-is into the unified evidence folder.",
        ],
        "cases": merged,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Unified cases: {len(merged)}")
    print(f"Evidence images: {cases_with_evidence}")
    print(f"Policy cases: {len(policy_cases)}; repository cases: {len(repo_cases)}")


if __name__ == "__main__":
    build()