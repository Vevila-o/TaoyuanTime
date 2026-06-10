import os
import sqlite3

from pipeline.dedupe import apply_stable_ids

def init_db(filepath):
    dirname = os.path.dirname(filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(filepath)
    cursor = conn.cursor()
    
    # activities
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activities (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_name TEXT,
          source_key TEXT,
          source_priority TEXT,
          source_url TEXT UNIQUE,
          source_item_id TEXT,
          activity_uid TEXT,
          title TEXT,
          official_detail_url TEXT,
          status TEXT,

          content_type TEXT,
          item_type TEXT,
          is_activity INTEGER,
          is_public_item INTEGER,
          is_event_candidate INTEGER,
          event_confidence REAL,

          date_text TEXT,
          date_start TEXT,
          date_end TEXT,
          time_text TEXT,
          date_parse_status TEXT,

          location TEXT,
          district TEXT,
          location_parse_status TEXT,

          organizer TEXT,
          category TEXT,
          description TEXT,
          clean_description TEXT,

          registration_method TEXT,
          registration_url TEXT,
          registration_parse_status TEXT,
          registration_evidence_text TEXT,

          fee_text TEXT,
          fee_type TEXT,
          fee_evidence_text TEXT,
          is_free INTEGER,
          fee_parse_status TEXT,

          poster_url TEXT,
          poster_local_path TEXT,
          ocr_ready BOOLEAN,
          ocr_image_url TEXT,
          ocr_image_path TEXT,
          ocr_text TEXT,
          ocr_summary TEXT,
          ocr_confidence REAL,
          ocr_status TEXT,
          ocr_warnings TEXT,
          has_assets INTEGER,
          asset_count INTEGER,

          quality_score INTEGER,
          quality_level TEXT,

          scraped_at TEXT,
          content_hash TEXT,
          raw_html_path TEXT,
          parse_warnings TEXT,
          quality_warnings TEXT,
          
          line_ready BOOLEAN,
          line_card_ready BOOLEAN,
          search_ready BOOLEAN,
          ai_ready BOOLEAN,
          recommendation_ready BOOLEAN,
          is_searchable BOOLEAN,
          published BOOLEAN,
          has_required_date BOOLEAN,
          has_title BOOLEAN,
          has_location BOOLEAN,
          has_source_url BOOLEAN,
          missing_fields TEXT,
          status_reason TEXT,
          exclude_from_recommendation_reason TEXT,
          mvp_candidate BOOLEAN,
          manual_review_required BOOLEAN,

          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # activity_assets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_assets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          activity_id INTEGER,
          activity_hash TEXT,
          source_name TEXT,
          source_url TEXT,
          asset_url TEXT NOT NULL,
          local_path TEXT,
          asset_type TEXT,
          mime_type TEXT,
          file_ext TEXT,
          file_size INTEGER,
          content_hash TEXT,
          alt_text TEXT,
          title_text TEXT,
          link_text TEXT,
          width INTEGER,
          height INTEGER,
          is_primary_poster INTEGER DEFAULT 0,
          download_status TEXT,
          error_message TEXT,
          scraped_at TEXT,
          asset_validation_status TEXT,
          image_role TEXT,
          ocr_candidate BOOLEAN,
          line_image_candidate BOOLEAN,
          image_quality_warnings TEXT,
          line_card_candidate BOOLEAN,
          poster_score INTEGER,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # crawler_runs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crawler_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT,
          mode TEXT,
          started_at TEXT,
          finished_at TEXT,
          runtime_seconds INTEGER,
          total_sources INTEGER,
          success_sources INTEGER,
          failed_sources INTEGER,
          total_items INTEGER,
          usable_items INTEGER,
          rejected_items INTEGER,
          total_assets INTEGER,
          successful_assets INTEGER,
          failed_assets INTEGER,
          notes TEXT
        )
    ''')

    for view_name in ("public_search_items", "ai_query_items", "recommendation_items"):
        cursor.execute(f"DROP VIEW IF EXISTS {view_name}")

    cursor.execute('''
        CREATE VIEW IF NOT EXISTS public_search_items AS
        SELECT * FROM activities
        WHERE status = 'active'
          AND is_public_item = 1
          AND COALESCE(is_searchable, search_ready, 0) = 1
          AND official_detail_url IS NOT NULL
          AND official_detail_url != ''
          AND (COALESCE(date_end, date_start) IS NULL OR date(COALESCE(date_end, date_start)) >= date('now', '+8 hours'))
        ORDER BY date(date_start) ASC
    ''')
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS ai_query_items AS
        SELECT * FROM activities
        WHERE status = 'active'
          AND is_activity = 1
          AND ai_ready = 1
          AND COALESCE(is_searchable, search_ready, 0) = 1
          AND quality_level = 'usable'
          AND manual_review_required = 0
          AND date_start IS NOT NULL
          AND date_start != ''
          AND (location IS NOT NULL OR district IS NOT NULL)
          AND official_detail_url IS NOT NULL
          AND official_detail_url != ''
          AND (COALESCE(date_end, date_start) IS NULL OR date(COALESCE(date_end, date_start)) >= date('now', '+8 hours'))
        ORDER BY date(date_start) ASC
    ''')
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS recommendation_items AS
        SELECT * FROM activities
        WHERE status = 'active'
          AND is_activity = 1
          AND recommendation_ready = 1
          AND COALESCE(published, is_public_item, 0) = 1
          AND official_detail_url IS NOT NULL
          AND official_detail_url != ''
          AND (COALESCE(date_end, date_start) IS NULL OR date(COALESCE(date_end, date_start)) >= date('now', '+8 hours'))
        ORDER BY date(date_start) ASC
    ''')
    
    conn.commit()
    ensure_columns(conn)
    return conn

def ensure_columns(conn):
    cursor = conn.cursor()
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(activities)").fetchall()}
    expected = {
        "official_detail_url": "TEXT",
        "source_item_id": "TEXT",
        "activity_uid": "TEXT",
        "status": "TEXT",
        "item_type": "TEXT",
        "is_activity": "INTEGER",
        "is_public_item": "INTEGER",
        "fee_type": "TEXT",
        "fee_evidence_text": "TEXT",
        "registration_parse_status": "TEXT",
        "registration_evidence_text": "TEXT",
        "quality_warnings": "TEXT",
        "line_ready": "BOOLEAN",
        "line_card_ready": "BOOLEAN",
        "search_ready": "BOOLEAN",
        "ai_ready": "BOOLEAN",
        "recommendation_ready": "BOOLEAN",
        "is_searchable": "BOOLEAN",
        "published": "BOOLEAN",
        "has_required_date": "BOOLEAN",
        "has_title": "BOOLEAN",
        "has_location": "BOOLEAN",
        "has_source_url": "BOOLEAN",
        "missing_fields": "TEXT",
        "status_reason": "TEXT",
        "exclude_from_recommendation_reason": "TEXT",
        "ocr_ready": "BOOLEAN",
        "ocr_image_url": "TEXT",
        "ocr_image_path": "TEXT",
        "ocr_text": "TEXT",
        "ocr_summary": "TEXT",
        "ocr_confidence": "REAL",
        "ocr_status": "TEXT",
        "ocr_warnings": "TEXT",
    }
    for name, column_type in expected.items():
        if name not in columns:
            cursor.execute(f"ALTER TABLE activities ADD COLUMN {name} {column_type}")
    asset_columns = {row[1] for row in cursor.execute("PRAGMA table_info(activity_assets)").fetchall()}
    expected_asset_columns = {
        "image_role": "TEXT",
        "ocr_candidate": "BOOLEAN",
        "line_image_candidate": "BOOLEAN",
        "image_quality_warnings": "TEXT",
    }
    for name, column_type in expected_asset_columns.items():
        if name not in asset_columns:
            cursor.execute(f"ALTER TABLE activity_assets ADD COLUMN {name} {column_type}")
    conn.commit()

def save_to_sqlite(events, filepath="scraping/data/output/activities.db"):
    conn = init_db(filepath)
    cursor = conn.cursor()
    
    for evt in events:
        apply_stable_ids(evt)
        try:
            columns = [
                "source_name", "source_key", "source_priority", "source_url", "source_item_id", "activity_uid", "title", "official_detail_url", "status",
                "content_type", "item_type", "is_activity", "is_public_item", "is_event_candidate", "event_confidence",
                "date_text", "date_start", "date_end", "time_text", "date_parse_status",
                "location", "district", "location_parse_status",
                "organizer", "category", "description", "clean_description",
                "registration_method", "registration_url", "registration_parse_status", "registration_evidence_text",
                "fee_text", "fee_type", "fee_evidence_text", "is_free", "fee_parse_status",
                "poster_url", "poster_local_path",
                "ocr_ready", "ocr_image_url", "ocr_image_path", "ocr_text", "ocr_summary", "ocr_confidence", "ocr_status", "ocr_warnings",
                "has_assets", "asset_count",
                "quality_score", "quality_level",
                "scraped_at", "content_hash", "raw_html_path", "parse_warnings", "quality_warnings",
                "line_ready", "line_card_ready", "search_ready", "ai_ready", "recommendation_ready",
                "is_searchable", "published", "has_required_date", "has_title", "has_location", "has_source_url",
                "missing_fields", "status_reason",
                "exclude_from_recommendation_reason", "mvp_candidate", "manual_review_required",
            ]
            values = (
                evt.get("source_name"), evt.get("source_key"), evt.get("source_priority"), evt.get("source_url"), evt.get("source_item_id"), evt.get("activity_uid"), evt.get("title"), evt.get("official_detail_url") or evt.get("source_url"), evt.get("status", "active"),
                evt.get("content_type"), evt.get("item_type") or evt.get("content_type"), int(evt.get("is_activity", False)), int(evt.get("is_public_item", False)), int(evt.get("is_event_candidate", False)), evt.get("event_confidence"),
                evt.get("date_text"), evt.get("date_start"), evt.get("date_end"), evt.get("time_text"), evt.get("date_parse_status"),
                evt.get("location"), evt.get("district"), evt.get("location_parse_status"),
                evt.get("organizer"), evt.get("category"), evt.get("description"), evt.get("clean_description"),
                evt.get("registration_method"), evt.get("registration_url"), evt.get("registration_parse_status"), evt.get("registration_evidence_text"),
                evt.get("fee_text"), evt.get("fee_type"), evt.get("fee_evidence_text"), int(evt.get("is_free", False)) if evt.get("is_free") is not None else None, evt.get("fee_parse_status"),
                evt.get("poster_url"), evt.get("poster_local_path"),
                int(evt.get("ocr_ready", False)), evt.get("ocr_image_url"), evt.get("ocr_image_path"), evt.get("ocr_text"), evt.get("ocr_summary"), evt.get("ocr_confidence"), evt.get("ocr_status"), str(evt.get("ocr_warnings", [])),
                int(evt.get("has_assets", False)), evt.get("asset_count"),
                evt.get("quality_score"), evt.get("quality_level"),
                evt.get("scraped_at"), evt.get("content_hash"), evt.get("raw_html_path"), str(evt.get("parse_warnings", [])), str(evt.get("quality_warnings", [])),
                int(evt.get("line_ready", evt.get("line_card_ready", False))), int(evt.get("line_card_ready", False)), int(evt.get("search_ready", False)), int(evt.get("ai_ready", False)),
                int(evt.get("recommendation_ready", False)),
                int(evt.get("is_searchable", False)), int(evt.get("published", False)),
                int(evt.get("has_required_date", False)), int(evt.get("has_title", False)),
                int(evt.get("has_location", False)), int(evt.get("has_source_url", False)),
                str(evt.get("missing_fields", [])), evt.get("status_reason"),
                evt.get("exclude_from_recommendation_reason"), int(evt.get("mvp_candidate", False)), int(evt.get("manual_review_required", False))
            )
            placeholders = ", ".join("?" for _ in columns)
            cursor.execute(
                f"INSERT OR REPLACE INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            
            activity_id = cursor.lastrowid
            
            # Save assets
            if evt.get("extracted_assets"):
                for asset in evt["extracted_assets"]:
                    cursor.execute('''
                        INSERT INTO activity_assets (
                            activity_id, activity_hash, source_name, source_url, asset_url, local_path,
                            asset_type, file_ext, width, height, is_primary_poster, download_status,
                            asset_validation_status, image_role, ocr_candidate, line_image_candidate,
                            image_quality_warnings, line_card_candidate, poster_score
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        activity_id, evt.get("content_hash"), evt.get("source_name"), evt.get("source_url"), asset.get("url"), asset.get("local_path"),
                        asset.get("type"), asset.get("ext"), asset.get("width"), asset.get("height"),
                        int(asset.get("is_primary_poster", False)), asset.get("status"),
                        asset.get("asset_validation_status"), asset.get("image_role"), int(asset.get("ocr_candidate", False)),
                        int(asset.get("line_image_candidate", False)), str(asset.get("image_quality_warnings", [])),
                        int(asset.get("line_card_candidate", False)), asset.get("poster_score", 0)
                    ))
                    
        except Exception as e:
            print(f"DB Error on {evt.get('source_url')}: {e}")
            
    conn.commit()
    conn.close()

def save_run_summary_db(summary, filepath="scraping/data/output/activities.db"):
    conn = init_db(filepath)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO crawler_runs (
            run_id, mode, started_at, finished_at, runtime_seconds,
            total_sources, success_sources, failed_sources,
            total_items, usable_items, rejected_items,
            total_assets, successful_assets, failed_assets, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        summary.get("run_id"), summary.get("mode"), summary.get("started_at"), summary.get("finished_at"), summary.get("runtime_seconds"),
        summary.get("total_sources"), summary.get("success_sources"), summary.get("failed_sources"),
        summary.get("total_items"), summary.get("usable_items"), summary.get("rejected_items"),
        summary.get("total_assets_found"), summary.get("assets_downloaded"), summary.get("assets_failed"),
        str(summary.get("major_findings", []))
    ))
    conn.commit()
    conn.close()
