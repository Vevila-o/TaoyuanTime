import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.asset_downloader import read_image_dimensions
from pipeline.asset_validator import validate_assets
from pipeline.ocr_client import apply_ocr_to_event
from pipeline.save_json import save_to_json, _normalize_output_contract, _sync_front_facing_flags


def refresh_existing_image_dimensions(event):
    for asset in event.get("extracted_assets") or []:
        local_path = asset.get("local_path")
        if not local_path:
            continue
        ext = (asset.get("ext") or asset.get("file_ext") or "").lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            continue
        width, height = read_image_dimensions(local_path)
        if width and height:
            asset["width"] = width
            asset["height"] = height
            asset["status"] = asset.get("status") or "downloaded"
            asset["download_status"] = asset.get("download_status") or "downloaded"
        else:
            asset["status"] = "failed"
            asset["download_status"] = "failed"
    return event


def prepare_event(event):
    refresh_existing_image_dimensions(event)
    validate_assets(event)
    _normalize_output_contract(event)
    _sync_front_facing_flags(event)
    return event


def main():
    parser = argparse.ArgumentParser(description="Refresh front-pool image quality metadata and optionally run OCR.")
    parser.add_argument("--input", default="scraping/data/output/activities_all.json")
    parser.add_argument("--output-dir", default="scraping/data/output")
    parser.add_argument("--ocr", action="store_true", help="Call the OpenAI-compatible OCR API.")
    parser.add_argument("--limit", type=int, default=0, help="Max OCR calls; 0 means no limit.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many OCR candidates before applying --limit.")
    parser.add_argument("--skip-success", action="store_true", help="Do not call OCR again for items already marked success.")
    parser.add_argument("--skip-failed", action="store_true", help="Do not call OCR again for items already marked failed.")
    args = parser.parse_args()

    input_path = Path(args.input)
    events = json.loads(input_path.read_text(encoding="utf-8"))
    ocr_calls = 0
    ocr_success = 0
    ocr_candidates_seen = 0

    for event in events:
        prepare_event(event)
        has_candidate = any(
            asset.get("ocr_candidate") and asset.get("image_role") in {"poster", "main_visual"}
            for asset in event.get("extracted_assets") or []
        )
        if not args.ocr:
            continue
        if args.skip_success and event.get("ocr_status") == "success" and (event.get("ocr_text") or event.get("ocr_summary")):
            ocr_success += 1
            continue
        if args.skip_failed and event.get("ocr_status") == "failed":
            continue
        if not event.get("front_ready") or not has_candidate:
            apply_ocr_to_event(event)
            continue
        if args.offset and ocr_candidates_seen < args.offset:
            ocr_candidates_seen += 1
            continue
        if args.limit and ocr_calls >= args.limit:
            continue
        ocr_candidates_seen += 1
        apply_ocr_to_event(event)
        ocr_calls += 1
        if event.get("ocr_status") == "success":
            ocr_success += 1

    save_to_json(events, output_dir=args.output_dir)
    print(
        f"refreshed={len(events)} front_ready={sum(1 for item in events if item.get('front_ready'))} "
        f"ocr_calls={ocr_calls} ocr_success={ocr_success}"
    )


if __name__ == "__main__":
    main()
