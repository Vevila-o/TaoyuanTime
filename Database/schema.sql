-- SQLite schema for tyaihub events app (reference)
CREATE TABLE "events_sourcewebsite" (
    "id" integer PRIMARY KEY AUTOINCREMENT,
    "name" varchar(200) NOT NULL,
    "source_type" varchar(32) NOT NULL,
    "url" varchar(200) NULL,
    "is_active" bool NOT NULL,
    "note" text,
    "created_at" datetime,
    "updated_at" datetime
);

CREATE TABLE "events_tag" (
    "id" integer PRIMARY KEY AUTOINCREMENT,
    "name" varchar(100) NOT NULL UNIQUE,
    "tag_type" varchar(32) NOT NULL,
    "is_active" bool NOT NULL,
    "created_at" datetime,
    "updated_at" datetime
);

CREATE TABLE "events_activity" (
    "id" integer PRIMARY KEY AUTOINCREMENT,
    "title" varchar(200) NOT NULL,
    "description" text,
    "location" varchar(200),
    "start_date" datetime,
    "end_date" datetime,
    "status" varchar(10) NOT NULL,
    "source_agency" varchar(200),
    "source_website_id" integer,
    "source_url" varchar(1000),
    "raw_content" text,
    "district" varchar(100),
    "image_url" varchar(200),
    "is_free" bool NOT NULL,
    "requires_registration" bool NOT NULL,
    "fee_description" varchar(300),
    "registration_info" text,
    "has_citizen_card_discount" bool NOT NULL,
    "citizen_card_note" varchar(300),
    "ai_summary" text,
    "ai_confidence" real,
    "created_at" datetime,
    "updated_at" datetime
);

CREATE TABLE "events_activity_tags" (
    "id" integer PRIMARY KEY AUTOINCREMENT,
    "activity_id" integer NOT NULL,
    "tag_id" integer NOT NULL
);

CREATE TABLE "events_userprofile" (
    "id" integer PRIMARY KEY AUTOINCREMENT,
    "line_user_id" varchar(64) NOT NULL UNIQUE,
    "display_name" varchar(200),
    "push_enabled" bool NOT NULL,
    "default_remind_before_days" integer NOT NULL,
    "has_citizen_card" bool NOT NULL,
    "created_at" datetime,
    "updated_at" datetime
);

CREATE TABLE "events_userprofile_preferred_tags" (
    "id" integer PRIMARY KEY AUTOINCREMENT,
    "userprofile_id" integer NOT NULL,
    "tag_id" integer NOT NULL
);

CREATE TABLE "events_subscription" (
    "id" integer PRIMARY KEY AUTOINCREMENT,
    "user_id" integer NOT NULL,
    "activity_id" integer NOT NULL,
    "remind_before_days" integer NOT NULL,
    "is_notified" bool NOT NULL,
    "created_at" datetime
);

CREATE TABLE "events_actionlog" (
    "id" integer PRIMARY KEY AUTOINCREMENT,
    "user_id" integer NOT NULL,
    "activity_id" integer,
    "action_type" varchar(64) NOT NULL,
    "metadata" json,
    "created_at" datetime
);

-- Note: Foreign keys and indexes are created by Django migrations; use this file as a reference only.
-- SQLite schema for events app (reference for handover)

PRAGMA foreign_keys = ON;

CREATE TABLE events_sourcewebsite (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_type TEXT,
    url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    note TEXT,
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE events_tag (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    tag_type TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE events_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    location TEXT,
    start_date DATETIME,
    end_date DATETIME,
    status TEXT NOT NULL DEFAULT 'draft',
    source_agency TEXT,
    source_website_id INTEGER,
    source_url TEXT,
    raw_content TEXT,
    district TEXT,
    image_url TEXT,
    is_free INTEGER NOT NULL DEFAULT 0,
    requires_registration INTEGER NOT NULL DEFAULT 0,
    fee_description TEXT,
    registration_info TEXT,
    has_citizen_card_discount INTEGER NOT NULL DEFAULT 0,
    citizen_card_note TEXT,
    ai_summary TEXT,
    ai_confidence REAL,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY(source_website_id) REFERENCES events_sourcewebsite(id) ON DELETE SET NULL
);

-- Many-to-many: activity.tags
CREATE TABLE events_activity_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    UNIQUE(activity_id, tag_id),
    FOREIGN KEY(activity_id) REFERENCES events_activity(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES events_tag(id) ON DELETE CASCADE
);

CREATE TABLE events_userprofile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_user_id TEXT NOT NULL UNIQUE,
    display_name TEXT,
    push_enabled INTEGER NOT NULL DEFAULT 1,
    default_remind_before_days INTEGER NOT NULL DEFAULT 1,
    has_citizen_card INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME
);

-- Many-to-many: userprofile.preferred_tags
CREATE TABLE events_userprofile_preferred_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userprofile_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    UNIQUE(userprofile_id, tag_id),
    FOREIGN KEY(userprofile_id) REFERENCES events_userprofile(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES events_tag(id) ON DELETE CASCADE
);

CREATE TABLE events_subscription (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    activity_id INTEGER NOT NULL,
    remind_before_days INTEGER NOT NULL DEFAULT 1,
    is_notified INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME,
    FOREIGN KEY(user_id) REFERENCES events_userprofile(id) ON DELETE CASCADE,
    FOREIGN KEY(activity_id) REFERENCES events_activity(id) ON DELETE CASCADE,
    UNIQUE(user_id, activity_id)
);

CREATE TABLE events_actionlog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    activity_id INTEGER,
    action_type TEXT NOT NULL,
    metadata TEXT,
    created_at DATETIME,
    FOREIGN KEY(user_id) REFERENCES events_userprofile(id) ON DELETE CASCADE,
    FOREIGN KEY(activity_id) REFERENCES events_activity(id) ON DELETE SET NULL
);

-- Indexes
CREATE INDEX idx_events_activity_start_date ON events_activity(start_date);
CREATE INDEX idx_events_activity_district ON events_activity(district);
CREATE INDEX idx_events_activity_status ON events_activity(status);
CREATE INDEX idx_events_activity_source_website ON events_activity(source_website_id);
