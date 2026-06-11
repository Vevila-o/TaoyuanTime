import json
import re
from pathlib import Path
from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from events.ai_providers import provider_order
from events.ai_tagger import PROMPT_VERSION, apply_accepted_tags, apply_safe_repairs, tag_activity_with_ai
from events.ai_tagger import get_active_tag_map, get_ai_tagger_config
from events.models import AIProcessingLog, Activity, ActivityTagSuggestion, Tag
from events.search_profiles import update_activity_search_profile


class Command(BaseCommand):
    help = "Use the local AI server to repair missing fields and suggest tags for active activities."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum number of recommendation-ready activities to process.",
        )
        parser.add_argument(
            "--activity-id",
            type=int,
            help="Process one activity by id instead of the recommendation-ready queryset.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not write tags. This is the default unless --apply is provided.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Add accepted whitelist tags to Activity.tags. Existing tags are preserved.",
        )
        parser.add_argument(
            "--create-suggestions",
            action="store_true",
            help="Create pending ActivityTagSuggestion rows from accepted AI whitelist tags.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print full JSON result objects.",
        )
        parser.add_argument(
            "--real-only",
            action="store_true",
            help="Exclude seeded sample rows whose source_url contains /sample/.",
        )
        parser.add_argument(
            "--input-json",
            help="Read activity objects from a crawler JSON file instead of the database.",
        )
        parser.add_argument(
            "--json-offset",
            type=int,
            default=0,
            help="Skip this many JSON rows before applying --limit.",
        )
        parser.add_argument(
            "--source-key",
            help="When using --input-json, only process rows with this source_key.",
        )
        parser.add_argument(
            "--audit-output",
            help="Write an AI tag quality audit report JSON without changing activities.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only print summary lines; useful for full-pool audit runs.",
        )
        parser.add_argument(
            "--skip-tagged-success",
            action="store_true",
            help="Skip database activities that already have a successful AI tagging log.",
        )
        parser.add_argument(
            "--repair-gaps-only",
            action="store_true",
            help="Only process active activities with missing core repair fields.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be greater than 0.")
        if options["apply"] and options["input_json"]:
            raise CommandError("--apply cannot be used with --input-json because JSON rows are not database records.")
        if options["create_suggestions"] and options["input_json"]:
            raise CommandError("--create-suggestions cannot be used with --input-json because JSON rows are not database records.")
        if options["create_suggestions"] and options["apply"]:
            raise CommandError("--create-suggestions and --apply are mutually exclusive.")

        apply_changes = bool(options["apply"])
        create_suggestions = bool(options["create_suggestions"])
        activities = self._get_activities(
            options["activity_id"],
            limit,
            options["real_only"],
            options["input_json"],
            options["json_offset"],
            options["source_key"],
            options["skip_tagged_success"],
            options["repair_gaps_only"],
        )
        if not activities:
            self.stdout.write(self.style.WARNING("No activities found."))
            return

        mode = "CREATE SUGGESTIONS" if create_suggestions else ("APPLY" if apply_changes else "DRY RUN")
        self.stdout.write(f"AI tag activities mode={mode}, count={len(activities)}")

        results = []
        suggestions_created = 0
        suggestions_skipped = 0
        for activity in activities:
            try:
                result = tag_activity_with_ai(activity)
            except Exception as exc:
                result = {
                    "activity_id": activity.id,
                    "activity_title": activity.title,
                    "activity_uid": getattr(activity, "activity_uid", "") or "",
                    "source_key": getattr(activity, "source_key", "") or "",
                    "ocr_status": getattr(activity, "ocr_status", "") or "",
                    "error": str(exc),
                    "manual_evaluation": "needs_review",
                }
                AIProcessingLog.objects.create(
                    activity=activity,
                    task_type="tagging",
                    model="/".join(provider_order())[:100],
                    prompt_version=PROMPT_VERSION,
                    input_summary=activity.title[:500],
                    output_json={"error": sanitize_ai_error(str(exc))},
                    status="failed",
                    error=sanitize_ai_error(str(exc))[:1000],
                )
                self._safe_write(self.style.ERROR(f"[{activity.id}] {activity.title} -> ERROR: {exc}"))
                results.append(result)
                continue

            applied_tags = []
            repair_outcome = apply_safe_repairs(activity, result, dry_run=not apply_changes)
            if apply_changes and repair_outcome.get("applied_repairs"):
                activity.refresh_from_db()
            if apply_changes:
                applied_tags = apply_accepted_tags(activity, result)
            if create_suggestions and not result.get("error"):
                created, skipped = create_pending_suggestions(activity, result)
                suggestions_created += created
                suggestions_skipped += skipped
            if apply_changes and not result.get("error"):
                update_activity_search_profile(activity, ai_result=result)
            result["applied_tags"] = [
                {"id": tag.id, "name": tag.name, "tag_type": tag.tag_type}
                for tag in applied_tags
            ]
            enrich_result_metadata(result, activity)
            AIProcessingLog.objects.create(
                activity=activity,
                task_type="tagging",
                model=f"{result.get('provider', 'ai')}:{result.get('model', '')}"[:100],
                prompt_version=PROMPT_VERSION,
                input_summary=activity.title[:500],
                output_json={
                    "accepted_tags": result.get("accepted_tags", []),
                    "new_tags": result.get("new_tags", []),
                    "repair_suggestions": result.get("repair_suggestions", []),
                    "applied_repairs": result.get("applied_repairs", []),
                    "rejected_repairs": result.get("rejected_repairs", []),
                    "warnings": result.get("warnings", []),
                    "search_keywords": result.get("search_keywords", []),
                    "search_topics": result.get("search_topics", []),
                    "search_synonyms": result.get("search_synonyms", []),
                    "suggestions_created": suggestions_created,
                    "suggestions_skipped": suggestions_skipped,
                    "applied_tags": result.get("applied_tags", []),
                },
                status="success",
            )
            results.append(result)
            if not options["quiet"]:
                self._print_result(result, apply_changes)

        if options["json"]:
            self._safe_write(json.dumps(results, ensure_ascii=False, indent=2))
        if options["audit_output"]:
            write_audit_report(results, options["audit_output"])
            self.stdout.write(self.style.SUCCESS(f"AI tag audit report written: {options['audit_output']}"))
        if create_suggestions:
            self.stdout.write(self.style.SUCCESS(
                f"Suggestions: created={suggestions_created}, skipped={suggestions_skipped}"
            ))

    def _get_activities(
        self,
        activity_id,
        limit,
        real_only,
        input_json,
        json_offset,
        source_key,
        skip_tagged_success,
        repair_gaps_only=False,
    ):
        if input_json:
            if activity_id:
                raise CommandError("--activity-id cannot be used with --input-json.")
            return self._get_json_activities(input_json, limit, json_offset, source_key)
        if activity_id:
            qs = Activity.objects.filter(id=activity_id, excluded_from_public=False)
        else:
            qs = Activity.objects.filter(
                status="active",
                excluded_from_public=False,
                is_activity=True,
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=timezone.now())
            )
            if repair_gaps_only:
                qs = qs.filter(repair_gap_filter())
        if real_only:
            qs = qs.exclude(source_url__contains="/sample/")
        if skip_tagged_success and not activity_id:
            tagged_ids = AIProcessingLog.objects.filter(
                task_type="tagging",
                status="success",
                prompt_version=PROMPT_VERSION,
                activity_id__isnull=False,
            ).values_list("activity_id", flat=True)
            qs = qs.exclude(id__in=tagged_ids)
        return list(qs.distinct().prefetch_related("tags").order_by("start_date", "id")[:limit])

    def _get_json_activities(self, input_json, limit, json_offset, source_key):
        path = Path(input_json)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise CommandError(f"Input JSON not found: {path}")
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc
        if not isinstance(rows, list):
            raise CommandError("--input-json must point to a JSON list of activity objects.")
        if source_key:
            rows = [row for row in rows if row.get("source_key") == source_key]
        rows = rows[json_offset:json_offset + limit]
        return [json_activity_from_item(item, index=json_offset + idx + 1) for idx, item in enumerate(rows)]

    def _print_result(self, result, apply_changes):
        accepted = _format_tags(result.get("accepted_tags", []))
        new_tags = _format_tags(result.get("new_tags", []))
        current = _format_tags(result.get("current_tags", []))
        missing = _format_tags(result.get("missing_tags", []))
        rejected = _format_tags(result.get("rejected_tags", []))
        blocking_warnings = result.get("blocking_warnings", result.get("warnings", []))
        info_warnings = result.get("info_warnings", [])
        applied = _format_tags(result.get("applied_tags", []))
        repairs = _format_repairs(result.get("repair_suggestions", []))
        applied_repairs = _format_repairs(result.get("applied_repairs", []))
        rejected_repairs = _format_repairs(result.get("rejected_repairs", []), include_reason=True)

        self._safe_write("")
        self._safe_write(f"[{result['activity_id']}] {result['activity_title']}")
        self._safe_write(f"  current_tags: {current or '-'}")
        self._safe_write(f"  ai_accepted_tags: {accepted or '-'}")
        self._safe_write(f"  new_tags_if_applied: {new_tags or '-'}")
        if missing:
            self._safe_write(f"  missing_tags_rejected: {missing}")
        if rejected:
            self._safe_write(f"  rejected_tags: {rejected}")
        if repairs:
            self._safe_write(f"  repair_suggestions: {repairs}")
        if rejected_repairs:
            self._safe_write(f"  rejected_repairs: {rejected_repairs}")
        if blocking_warnings:
            self._safe_write(f"  blocking_warnings: {' | '.join(blocking_warnings)}")
        if info_warnings:
            self._safe_write(f"  info_warnings: {' | '.join(info_warnings)}")
        self._safe_write(f"  confidence: {result.get('confidence')}")
        self._safe_write(f"  manual_evaluation: {result.get('manual_evaluation')}")
        if apply_changes:
            self._safe_write(self.style.SUCCESS(f"  applied_tags: {applied or '-'}"))
            self._safe_write(self.style.SUCCESS(f"  applied_repairs: {applied_repairs or '-'}"))
        elif applied_repairs:
            self._safe_write(f"  applied_if_apply: {applied_repairs}")

    def _safe_write(self, message):
        encoding = getattr(self.stdout, "encoding", None) or "utf-8"
        safe_message = str(message).encode(encoding, errors="replace").decode(encoding)
        self.stdout.write(safe_message)


def _format_tags(tags):
    parts = []
    for tag in tags:
        name = tag.get("name")
        tag_type = tag.get("tag_type")
        confidence = tag.get("confidence")
        label = f"{name}({tag_type})"
        if confidence is not None:
            label = f"{label}@{confidence:.2f}"
        parts.append(label)
    return ", ".join(parts)


def repair_gap_filter():
    return (
        Q(start_date__isnull=True)
        | Q(location="")
        | Q(district="")
        | Q(fee_type="unknown")
        | (Q(requires_registration=True) & (Q(registration_info="") | Q(registration_url="")))
    )


def _format_repairs(repairs, *, include_reason=False):
    parts = []
    for repair in repairs:
        field = repair.get("field")
        value = repair.get("new_value") or repair.get("normalized_value") or repair.get("value")
        confidence = repair.get("confidence")
        label = f"{field}={value}"
        if confidence is not None:
            label = f"{label}@{confidence:.2f}"
        if include_reason and repair.get("reject_reason"):
            label = f"{label}({repair['reject_reason']})"
        parts.append(label)
    return ", ".join(parts)


def sanitize_ai_error(value):
    return re.sub(r"key=[^;&\s]+", "key=***", str(value or ""))


def create_pending_suggestions(activity, result):
    created = 0
    skipped = 0
    for item in result.get("accepted_tags") or []:
        tag_name = item.get("name")
        tag_type = item.get("tag_type")
        if not tag_name or not tag_type:
            skipped += 1
            continue
        tag = Tag.objects.filter(name=tag_name, tag_type=tag_type, is_active=True).first()
        if not tag:
            skipped += 1
            continue
        if activity.tags.filter(id=tag.id).exists():
            skipped += 1
            continue
        _, was_created = ActivityTagSuggestion.objects.get_or_create(
            activity=activity,
            tag_name=tag.name,
            tag_type=tag.tag_type,
            source="ai",
            defaults={
                "tag": tag,
                "confidence": item.get("confidence"),
                "reason": item.get("reason") or "AI 判斷此活動符合既有 Tag。",
                "status": "pending",
            },
        )
        if was_created:
            created += 1
        else:
            skipped += 1
    return created, skipped


def enrich_result_metadata(result, activity):
    result["activity_uid"] = getattr(activity, "activity_uid", "") or result.get("activity_uid") or ""
    result["source_key"] = getattr(activity, "source_key", "") or result.get("source_key") or ""
    result["ocr_status"] = getattr(activity, "ocr_status", "") or result.get("ocr_status") or ""
    result["ocr_has_text"] = bool(getattr(activity, "ocr_text", "") or getattr(activity, "ocr_summary", ""))
    result["fee_type"] = getattr(activity, "fee_type", "") or ""
    result["is_free"] = getattr(activity, "is_free", None)
    result["requires_registration"] = getattr(activity, "requires_registration", None)
    return result


def write_audit_report(results, output_path):
    tag_map = get_active_tag_map()
    tag_keys = set(tag_map)
    min_confidence = get_ai_tagger_config().min_confidence
    items = [build_audit_item(result, tag_keys, min_confidence) for result in results]
    summary = build_audit_summary(items)
    path = Path(output_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"summary": summary, "items": items}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_audit_item(result, tag_keys, min_confidence):
    accepted = result.get("accepted_tags") or []
    rejected = result.get("rejected_tags") or []
    missing = result.get("missing_tags") or []
    blocking_warnings = result.get("blocking_warnings") or []
    accepted_keys = {(tag.get("tag_type"), tag.get("name")) for tag in accepted}
    non_whitelist = sorted(
        f"{tag_type}:{name}"
        for tag_type, name in accepted_keys
        if (tag_type, name) not in tag_keys
    )
    cost_values = [
        tag.get("name") for tag in accepted
        if tag.get("tag_type") == "cost" and tag.get("name") in {"免費", "付費", "金額未提供"}
    ]
    core_tags = [
        tag for tag in accepted
        if tag.get("tag_type") in {"region", "activity_type", "cost"}
        and (tag.get("confidence") is not None and tag.get("confidence") >= min_confidence)
    ]
    fail_reasons = []
    if result.get("error"):
        fail_reasons.append("tagger_error")
    if blocking_warnings:
        fail_reasons.append("blocking_warnings")
    if any(tag.get("reject_level") == "blocking" for tag in rejected):
        fail_reasons.append("blocking_rejections")
    if non_whitelist:
        fail_reasons.append("non_whitelist_accepted_tags")
    if len(cost_values) > 1:
        fail_reasons.append("mutually_exclusive_cost_tags")
    if not core_tags:
        fail_reasons.append("missing_high_confidence_core_tag")
    return {
        "activity_id": result.get("activity_id"),
        "activity_uid": result.get("activity_uid") or "",
        "title": result.get("activity_title") or "",
        "source_key": result.get("source_key") or "",
        "ocr_status": result.get("ocr_status") or "",
        "ocr_has_text": bool(result.get("ocr_has_text")),
        "accepted_tags": accepted,
        "rejected_tags": rejected,
        "missing_tags": missing,
        "warnings": result.get("warnings") or [],
        "blocking_warnings": blocking_warnings,
        "info_warnings": result.get("info_warnings") or [],
        "confidence": result.get("confidence"),
        "manual_evaluation": result.get("manual_evaluation"),
        "quality_pass": not fail_reasons,
        "fail_reasons": fail_reasons,
        "non_whitelist_accepted_tags": non_whitelist,
        "cost_value_tags": cost_values,
    }


def build_audit_summary(items):
    processed_count = len(items)
    pass_count = sum(1 for item in items if item["quality_pass"])
    mutually_exclusive_cost_errors = sum(1 for item in items if "mutually_exclusive_cost_tags" in item["fail_reasons"])
    non_whitelist_accepted_tags = sum(len(item["non_whitelist_accepted_tags"]) for item in items)
    blocking_warning_items = sum(1 for item in items if item["blocking_warnings"])
    blocking_warning_pass_items = sum(1 for item in items if item["quality_pass"] and item["blocking_warnings"])
    return {
        "processed_count": processed_count,
        "quality_pass_count": pass_count,
        "quality_pass_rate": round(pass_count / processed_count, 4) if processed_count else 0,
        "failed_count": processed_count - pass_count,
        "blocking_warning_items": blocking_warning_items,
        "blocking_warning_pass_items": blocking_warning_pass_items,
        "mutually_exclusive_cost_errors": mutually_exclusive_cost_errors,
        "non_whitelist_accepted_tags": non_whitelist_accepted_tags,
        "missing_tag_count": sum(len(item["missing_tags"]) for item in items),
        "rejected_tag_count": sum(len(item["rejected_tags"]) for item in items),
        "ocr_context_items": sum(1 for item in items if item["ocr_has_text"]),
        "ocr_success_items": sum(1 for item in items if item["ocr_status"] == "success"),
    }


def json_activity_from_item(item, index):
    fee_type = item.get("fee_type")
    is_free = item.get("is_free")
    if is_free is None:
        is_free_value = None
    else:
        is_free_value = bool(is_free)
    requires_registration = item.get("requires_registration")
    if requires_registration is None:
        text = " ".join(
            str(item.get(key) or "")
            for key in ("registration_info", "registration_method", "registration_url", "ai_input_text", "clean_description")
        )
        requires_registration = any(keyword in text for keyword in ("報名", "預約", "登記"))
    registration_parts = [
        item.get("registration_info"),
        item.get("registration_method"),
        item.get("registration_url"),
    ]
    return SimpleNamespace(
        id=item.get("id") or item.get("source_url") or index,
        activity_uid=item.get("activity_uid") or "",
        source_key=item.get("source_key") or "",
        title=item.get("title") or "活動",
        description=item.get("clean_description") or item.get("description") or item.get("ai_input_text") or "",
        district=(item.get("district") or "").replace("區", ""),
        location=item.get("location") or item.get("location_text") or item.get("address") or "",
        is_free=is_free_value,
        requires_registration=bool(requires_registration),
        fee_type=fee_type or "",
        fee_description=item.get("fee_text") or item.get("fee_raw_text") or item.get("fee_description") or fee_type or "",
        registration_info=" ".join(str(part) for part in registration_parts if part),
        ocr_text=item.get("ocr_text") or "",
        ocr_summary=item.get("ocr_summary") or "",
        ocr_status=item.get("ocr_status") or "",
        current_tags=item.get("tags") or [],
    )
