import argparse
import time
import json
import os
import sys
import yaml
from datetime import datetime

# Import scrapers
from scrapers.tycg import TycgScraper
from scrapers.travel_taoyuan import TravelTaoyuanScraper
from scrapers.travel_openapi import TravelOpenApiFetcher
from scrapers.culture import CultureScraper
from scrapers.youth import YouthScraper
from scrapers.hakka import HakkaScraper
from scrapers.agriculture import AgricultureScraper
from scrapers.economic import EconomicScraper
from scrapers.rss_opendata import HtmlListScraper, RssOpenDataScraper

# Import pipeline
from pipeline.normalize_text import normalize_text
from pipeline.classify_content import classify_content
from pipeline.extract_dates import extract_dates
from pipeline.extract_location import extract_location
from pipeline.extract_fee import extract_fee
from pipeline.asset_extractor import extract_assets
from pipeline.asset_downloader import download_assets
from pipeline.asset_validator import validate_assets
from pipeline.line_card_readiness import check_line_card_readiness
from pipeline.ai_readiness import check_ai_readiness
from pipeline.quality_score import calculate_quality_score
from pipeline.dedupe import deduplicate
from pipeline.ocr_client import apply_ocr_to_event
from pipeline.save_json import save_to_json, save_run_summary_json, _normalize_output_contract, _sync_front_facing_flags
from pipeline.save_sqlite import save_to_sqlite, save_run_summary_db

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRAPING_ROOT = os.path.join(PROJECT_ROOT, "scraping")
if SCRAPING_ROOT not in sys.path:
    sys.path.insert(0, SCRAPING_ROOT)

SCRAPING_DATA_DIR = os.environ.get("TAOYUAN_SCRAPING_DATA_DIR", os.path.join(SCRAPING_ROOT, "data"))
SCRAPING_OUTPUT_DIR = os.path.join(SCRAPING_DATA_DIR, "output")

def load_sources_config():
    with open("config/sources.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("sources", [])

def main():
    parser = argparse.ArgumentParser(description="Public Event Crawler V3 Reliability Test")
    parser.add_argument("--mode", default="reliability_v3", choices=["probe_1hour", "reliability_v3", "custom"], help="Execution mode")
    parser.add_argument("--source", type=str, help="Run a specific source key")
    parser.add_argument("--primary-limit", type=int, default=150, help="Max items per primary source")
    parser.add_argument("--secondary-limit", type=int, default=150, help="Max items per secondary source")
    parser.add_argument("--max-runtime", type=int, default=150, help="Max runtime in minutes")
    parser.add_argument("--resume", action="store_true", help="Resume from last run")
    parser.add_argument("--no-assets", action="store_true", help="Skip asset downloading")
    parser.add_argument("--ocr", action="store_true", help="Run OCR for front-facing poster/main visual images")
    parser.add_argument("--ocr-limit", type=int, default=0, help="Max OCR calls for this run; 0 means no limit")
    parser.add_argument("--skip-dynamic", action="store_true", help="Skip DynamicFetcher sources for faster full-site runs")
    parser.add_argument("--exclude-source", action="append", default=[], help="Exclude a source key; can be used multiple times")
    
    args = parser.parse_args()
    
    start_time = time.time()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    debug_logs = {
        "date_parse_failed": [],
        "location_parse_failed": [],
        "fee_parse_failed": [],
        "asset_download_failed": [],
        "dynamic_fetch_failed": []
    }
    
    scraper_classes = {
        "tycg_news": TycgScraper,
        "tycg_events": TycgScraper,
        "travel": TravelTaoyuanScraper,
        "travel_news": TravelTaoyuanScraper,
        "travel_openapi": TravelOpenApiFetcher,
        "culture": CultureScraper,
        "youth": YouthScraper,
        "hakka": HakkaScraper,
        "agriculture": AgricultureScraper,
        "economic": EconomicScraper
    }
    scraper_classes_by_fetcher_type = {
        "RssOpenDataFetcher": RssOpenDataScraper,
        "HtmlListFetcher": HtmlListScraper,
    }
    
    sources_conf = load_sources_config()
    scrapers_to_run = []
    
    for conf in sources_conf:
        if args.source and conf["key"] != args.source:
            continue
        if conf["key"] in set(args.exclude_source):
            continue
        if args.skip_dynamic and conf.get("fetcher_type") == "DynamicFetcher":
            continue
            
        cls = scraper_classes.get(conf["key"]) or scraper_classes_by_fetcher_type.get(conf.get("fetcher_type"))
        if not cls: continue
        
        scrapers_to_run.append({
            "scraper": cls(key=conf["key"], name=conf["name"], start_url=conf.get("start_url", ""), fetcher_type=conf["fetcher_type"]),
            "priority": conf.get("source_priority", "secondary")
        })
        
    all_events = []
    source_stats = {}
    
    for item in scrapers_to_run:
        scraper = item["scraper"]
        priority = item["priority"]
        limit = args.primary_limit if priority in ("primary", "primary_candidate") else args.secondary_limit
        
        print(f"\\n[{scraper.key}] Starting scrape with {scraper.fetcher_type} (limit: {limit})...")
        
        st = {
            "source_key": scraper.key,
            "source_name": scraper.name,
            "source_priority": priority,
            "fetcher_type": scraper.fetcher_type,
            "attempted_count": 0,
            "list_items_found": 0,
            "detail_pages_attempted": 0,
            "detail_pages_success": 0,
            "detail_pages_failed": 0,
            "items_created": 0,
            "items_skipped": 0,
            "items_rejected": 0,
            
            "activity_count": 0,
            "usable_count": 0,
            "line_ready_count": 0,
            "ai_ready_count": 0,
            
            "date_success": 0,
            "location_success": 0,
            "asset_found_count": 0,
            "poster_valid_count": 0,
            "total_score": 0,
            "status": "success",
            "major_issues": []
        }
        source_stats[scraper.key] = st
        
        try:
            page = scraper.fetch_list()
            if not page:
                raise Exception("Failed to fetch list page")
                
            detail_urls = scraper.parse_list(page)
            for warning in getattr(scraper, "parse_warnings", []):
                if isinstance(warning, dict):
                    issue = warning.get("warning") or str(warning)
                    if warning.get("error"):
                        issue = f"{issue}: {warning.get('error')}"
                else:
                    issue = str(warning)
                if issue not in st["major_issues"]:
                    st["major_issues"].append(issue)
            st["list_items_found"] = len(detail_urls)
            if not detail_urls:
                st["status"] = "no_data"
                st["major_issues"].append("no_list_items_found")
            detail_urls = detail_urls[:limit]
            st["attempted_count"] = len(detail_urls)
            print(f"[{scraper.key}] Processing {st['attempted_count']} detail URLs.")
            
            for url in detail_urls:
                st["detail_pages_attempted"] += 1
                if (time.time() - start_time) > (args.max_runtime * 60):
                    print("Max runtime reached. Stopping crawl.")
                    st["major_issues"].append("Max runtime reached")
                    break
                    
                try:
                    detail_page = scraper.fetch_detail(url)
                    event_data = scraper.parse_detail(detail_page, url)
                    st["detail_pages_success"] += 1
                except Exception as e:
                    st["detail_pages_failed"] += 1
                    print(f"[{scraper.key}] Detail fetch failed for {url}: {e}")
                    continue
                
                if event_data:
                    try:
                        event_data["source_priority"] = priority
                        
                        # Run Pipeline
                        event_data = normalize_text(event_data)
                        event_data = extract_dates(event_data, debug_log=debug_logs["date_parse_failed"])
                        event_data = extract_location(event_data, debug_log=debug_logs["location_parse_failed"])
                        event_data = extract_fee(event_data, debug_log=debug_logs["fee_parse_failed"])
                        event_data = classify_content(event_data)
                        
                        if not args.no_assets:
                            event_data = extract_assets(event_data)
                            event_data = download_assets(event_data, debug_log=debug_logs["asset_download_failed"])
                            event_data = validate_assets(event_data)
                            
                        event_data = check_line_card_readiness(event_data)
                        event_data = check_ai_readiness(event_data)
                        event_data = calculate_quality_score(event_data)

                        if priority == "filtered" and not event_data.get("is_activity"):
                            st["items_skipped"] += 1
                            continue
                        
                        all_events.append(event_data)
                        st["items_created"] += 1
                    except Exception as e:
                        print(f"[{scraper.key}] Pipeline failed for {url}: {e}")
                        debug_case_dir = os.path.join(SCRAPING_DATA_DIR, "debug_cases")
                        os.makedirs(debug_case_dir, exist_ok=True)
                        debug_file = os.path.join(debug_case_dir, f"{scraper.key}_detail_parse_failed.json")
                        with open(debug_file, "a", encoding="utf-8") as f:
                            f.write(json.dumps({
                                "source_url": url, 
                                "raw_html_path": event_data.get("raw_html_path"),
                                "error": str(e)
                            }, ensure_ascii=False) + "\\n")
                        continue
                    
                    if event_data.get("content_type") == "activity":
                        st["activity_count"] += 1
                    
                    if event_data.get("quality_level") == "usable":
                        st["usable_count"] += 1
                    elif event_data.get("quality_level") == "rejected":
                        st["items_rejected"] += 1
                        
                    if event_data.get("line_card_ready"): st["line_ready_count"] += 1
                    if event_data.get("ai_ready"): st["ai_ready_count"] += 1
                    
                    if event_data.get("date_parse_status") == "success": st["date_success"] += 1
                    if event_data.get("location_parse_status") in ["success", "multi_location"]: st["location_success"] += 1
                    
                    if event_data.get("has_assets"): st["asset_found_count"] += 1
                    if event_data.get("extracted_assets"):
                        for asset in event_data["extracted_assets"]:
                            if asset.get("asset_validation_status") in ["valid_poster", "likely_poster"]:
                                st["poster_valid_count"] += 1
                                break
                        
                    st["total_score"] += event_data.get("quality_score", 0)
                    try:
                        safe_title = event_data['title'][:30].encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
                        print(f"[{scraper.key}] Parsed: {safe_title} | L:{event_data.get('line_card_ready')} | AI:{event_data.get('ai_ready')}")
                    except Exception:
                        print(f"[{scraper.key}] Parsed: (Title contains unprintable chars) | L:{event_data.get('line_card_ready')} | AI:{event_data.get('ai_ready')}")
                else:
                    st["items_skipped"] += 1
                    
        except Exception as e:
            import traceback
            print(f"[{scraper.key}] CRITICAL Error during scrape: {e}")
            traceback.print_exc()
            st["status"] = "failed"
            st["major_issues"].append(str(e))
            if scraper.fetcher_type == "DynamicFetcher":
                debug_logs["dynamic_fetch_failed"].append({"source_key": scraper.key, "reason": str(e), "fetcher_type": scraper.fetcher_type})
        finally:
            if st["status"] == "success" and st["items_created"] == 0:
                st["status"] = "no_data"
                if "no_items_created" not in st["major_issues"]:
                    st["major_issues"].append("no_items_created")
            
    # Post-processing
    deduped_events = deduplicate(all_events)
    print(f"\\nTotal raw events: {len(all_events)}, After dedupe: {len(deduped_events)}")

    if args.ocr:
        ocr_calls = 0
        for event in deduped_events:
            _normalize_output_contract(event)
            _sync_front_facing_flags(event)
            has_candidate = any(
                asset.get("ocr_candidate") and asset.get("image_role") in {"poster", "main_visual"}
                for asset in event.get("extracted_assets") or []
            )
            if not event.get("front_ready") or not has_candidate:
                apply_ocr_to_event(event)
                continue
            if args.ocr_limit and ocr_calls >= args.ocr_limit:
                event["ocr_ready"] = False
                event["ocr_status"] = "failed"
                event.setdefault("ocr_warnings", []).append("ocr_limit_reached")
                continue
            apply_ocr_to_event(event)
            ocr_calls += 1
        print(f"OCR processed candidates: {ocr_calls}")
    
    # Save Outputs
    save_to_json(deduped_events, output_dir=SCRAPING_OUTPUT_DIR)
    save_to_sqlite(deduped_events, filepath=os.path.join(SCRAPING_OUTPUT_DIR, "activities.db"))
    
    # Write Debug Cases
    for log_name, logs in debug_logs.items():
        if logs:
            debug_dir = os.path.join(SCRAPING_OUTPUT_DIR, "debug_cases")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, f"{log_name}.json"), "w", encoding="utf-8") as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
                
    # Calculate Summaries
    finished_at_time = time.time()
    runtime_seconds = int(finished_at_time - start_time)
    
    # 1. Source Quality Summary
    final_source_stats = []
    for k, v in source_stats.items():
        if v["items_created"] > 0:
            v["date_parse_success_rate"] = round(v["date_success"] / v["items_created"], 2)
            v["location_parse_success_rate"] = round(v["location_success"] / v["items_created"], 2)
            v["asset_found_rate"] = round(v["asset_found_count"] / v["items_created"], 2)
            v["poster_valid_rate"] = round(v["poster_valid_count"] / v["items_created"], 2)
            v["average_quality_score"] = round(v["total_score"] / v["items_created"], 2)
            
            line_ready_rate = v["line_ready_count"] / v["items_created"]
            date_success_rate = v["date_success"] / v["items_created"]
            location_success_rate = v["location_success"] / v["items_created"]
            activity_rate = v["activity_count"] / v["items_created"]
            v["line_ready_rate"] = round(line_ready_rate, 2)
            v["activity_rate"] = round(activity_rate, 2)
            if v["items_created"] < 10:
                v["major_issues"].append("small_sample_size")
            # V3 MVP Criteria: poster is diagnostic only, not a blocking signal.
            v["recommended_for_mvp_by_metrics"] = (
                v["activity_count"] > 0 and
                line_ready_rate >= 0.9 and
                date_success_rate >= 0.9 and
                location_success_rate >= 0.8 and
                v["average_quality_score"] >= 70
            )
            v["recommended_for_mvp_after_manual_review"] = None
        else:
            v["date_parse_success_rate"] = 0
            v["location_parse_success_rate"] = 0
            v["asset_found_rate"] = 0
            v["poster_valid_rate"] = 0
            v["average_quality_score"] = 0
            v["recommended_for_mvp_by_metrics"] = False
            v["recommended_for_mvp_after_manual_review"] = None
            
        final_source_stats.append(v)
        
    os.makedirs(SCRAPING_OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(SCRAPING_OUTPUT_DIR, "source_quality_summary.json"), "w", encoding="utf-8") as f:
        json.dump(final_source_stats, f, ensure_ascii=False, indent=2)
        
    # 2. Run Summary
    run_summary = {
        "run_id": run_id,
        "mode": args.mode,
        "started_at": datetime.fromtimestamp(start_time).isoformat(),
        "finished_at": datetime.fromtimestamp(finished_at_time).isoformat(),
        "runtime_seconds": runtime_seconds,
        "total_sources": len(scrapers_to_run),
        "success_sources": sum(1 for s in final_source_stats if s["status"] == "success"),
        "failed_sources": sum(1 for s in final_source_stats if s["status"] == "failed"),
        
        "total_items": len(deduped_events),
        "usable_items": sum(1 for e in deduped_events if e.get("quality_level") == "usable"),
        "line_card_ready_items": sum(1 for e in deduped_events if e.get("line_card_ready")),
        "search_ready_items": sum(1 for e in deduped_events if e.get("search_ready")),
        "ai_ready_items": sum(1 for e in deduped_events if e.get("ai_ready")),
        "rejected_items": sum(1 for e in deduped_events if e.get("quality_level") == "rejected"),
        "manual_review_required_count": sum(1 for e in deduped_events if e.get("manual_review_required")),
        
        "total_assets_found": 0,
        "assets_downloaded": 0,
        "assets_failed": 0,
        "assets_filtered": 0,
        
        "best_sources": [s["source_key"] for s in final_source_stats if s.get("recommended_for_mvp_by_metrics")],
        "risky_sources": [s["source_key"] for s in final_source_stats if not s.get("recommended_for_mvp_by_metrics")]
    }
    
    for e in deduped_events:
        if "extracted_assets" in e:
            for a in e["extracted_assets"]:
                run_summary["total_assets_found"] += 1
                if a.get("status") == "downloaded": run_summary["assets_downloaded"] += 1
                elif a.get("status") == "filtered": run_summary["assets_filtered"] += 1
                elif a.get("status") == "failed": run_summary["assets_failed"] += 1

    save_run_summary_json(run_summary, output_dir=SCRAPING_OUTPUT_DIR)
    save_run_summary_db(run_summary, filepath=os.path.join(SCRAPING_OUTPUT_DIR, "activities.db"))

    try:
        from scripts.build_health_report import build_report, HEALTH_REPORT_PATH
        with open(HEALTH_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(build_report(), f, ensure_ascii=False, indent=2)
            f.write("\n")
    except Exception as e:
        print(f"Health report generation failed: {e}")
    
    print("\\nRun completed successfully! Generating report...")
    
    # Generate Markdown Report
    print("\\n" + "="*50)
    print("## V3 執行結果\\n")
    print(f"- 執行時間: {run_summary['runtime_seconds']} 秒")
    print(f"- 成功來源: {run_summary['success_sources']}")
    print(f"- 失敗來源: {run_summary['failed_sources']}")
    print(f"- 總建立資料: {run_summary['total_items']}")
    print(f"- usable: {run_summary['usable_items']}")
    print(f"- line_card_ready: {run_summary['line_card_ready_items']}")
    print(f"- search_ready: {run_summary['search_ready_items']}")
    print(f"- ai_ready: {run_summary['ai_ready_items']}")
    print(f"- rejected: {run_summary['rejected_items']}")
    print(f"- 下載附件: {run_summary['assets_downloaded']}")
    print(f"- 合格海報: {sum(s['poster_valid_count'] for s in final_source_stats)}\\n")
    
    print("## 各來源品質表\\n")
    print("| source | priority | total | usable | line_ready | ai_ready | rejected | avg_score | MVP (Metrics) |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for s in final_source_stats:
        status = 'Pass' if s.get('recommended_for_mvp_by_metrics') else 'Fail'
        print(f"| {s['source_key']} | {s['source_priority']} | {s['items_created']} | {s['usable_count']} | {s['line_ready_count']} | {s['ai_ready_count']} | {s['items_rejected']} | {s['average_quality_score']} | {status} |")
    print("="*50 + "\\n")

if __name__ == "__main__":
    main()
