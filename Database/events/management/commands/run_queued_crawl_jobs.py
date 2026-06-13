from pathlib import Path
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Max, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from events.ai_tagger import PROMPT_VERSION
from events.management.commands.ai_tag_activities import repair_gap_filter
from events.models import AIProcessingLog, Activity, CrawlJob, CrawlTask, ImportRun
from events.operation_jobs import check_activity_official_link, link_check_candidates
from events.search_profiles import set_link_health, update_activity_search_profile
from events.services import is_seed_activity


class Command(BaseCommand):
    help = 'Run queued CrawlJob records without blocking the admin web request.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=1)
        parser.add_argument('--job-id', type=int, help='Run one specific queued CrawlJob.')

    def handle(self, *args, **options):
        jobs = CrawlJob.objects.filter(status='queued')
        if options.get('job_id'):
            jobs = jobs.filter(id=options['job_id'])
        jobs = jobs.order_by('created_at')[:options['limit']]
        self.stdout.write(f'Queued jobs={len(jobs)}')
        for job in jobs:
            run_job(job, self)


def run_job(job, command):
    job.status = 'running'
    job.started_at = timezone.now()
    job.save(update_fields=['status', 'started_at', 'updated_at'])
    options = job.options or {}
    if options.get('full_pipeline'):
        run_full_pipeline_job(job, command)
        return

    latest_import_id = ImportRun.objects.order_by('-id').values_list('id', flat=True).first() or 0
    task = CrawlTask.objects.create(
        job=job,
        source_key=options.get('source') or 'all',
        status='running',
        started_at=timezone.now(),
    )
    try:
        call_command(
            'run_crawler_pipeline',
            mode=options.get('mode') or 'reliability_v3',
            source=options.get('source') or None,
            primary_limit=int(options.get('primary_limit') or 1),
            secondary_limit=int(options.get('secondary_limit') or 1),
            max_runtime=int(options.get('max_runtime') or 10),
            no_assets=bool(options.get('no_assets', True)),
            ocr=bool(options.get('ocr', False)),
            ocr_limit=int(options.get('ocr_limit') or 0),
            skip_dynamic=bool(options.get('skip_dynamic', True)),
            no_import=bool(options.get('no_import', False)),
            activate=bool(options.get('activate', True)),
        )
        output_path = Path(settings.BASE_DIR) / 'scraping' / 'data' / 'output' / 'activities_all.json'
        job.output_path = str(output_path)
        import_run = ImportRun.objects.filter(id__gt=latest_import_id).order_by('-id').first()
        if import_run:
            job.import_run = import_run
            task.created_count = import_run.created_count
            task.updated_count = import_run.updated_count
            task.skipped_count = import_run.skipped_count
            task.failed_count = import_run.failed_count
            task.attempted_count = (
                import_run.created_count
                + import_run.updated_count
                + import_run.skipped_count
                + import_run.failed_count
            )
            task.metadata = {
                'import_run_id': import_run.id,
                'input_path': import_run.input_path,
                'status': import_run.status,
            }
        job.status = 'success'
        task.status = 'success'
    except Exception as exc:
        job.status = 'failed'
        job.error_summary = str(exc)
        task.status = 'failed'
        task.error_summary = str(exc)
        command.stderr.write(f'CrawlJob {job.id} failed: {exc}')
    finally:
        now = timezone.now()
        job.finished_at = now
        job.save(update_fields=['status', 'output_path', 'import_run', 'error_summary', 'finished_at', 'updated_at'])
        task.finished_at = now
        task.save(update_fields=[
            'status',
            'attempted_count',
            'created_count',
            'updated_count',
            'skipped_count',
            'failed_count',
            'metadata',
            'error_summary',
            'finished_at',
            'updated_at',
        ])


def run_full_pipeline_job(job, command):
    options = job.options or {}
    latest_import_id = ImportRun.objects.order_by('-id').values_list('id', flat=True).first() or 0
    failed_stages = 0
    output_path = Path(settings.BASE_DIR) / 'scraping' / 'data' / 'output' / 'activities_all.json'

    crawl_task = start_stage(job, '爬蟲與匯入', '正在抓取活動並匯入資料庫。')
    try:
        call_command(
            'run_crawler_pipeline',
            mode=options.get('mode') or 'reliability_v3',
            source=options.get('source') or None,
            primary_limit=int(options.get('primary_limit') or 1),
            secondary_limit=int(options.get('secondary_limit') or options.get('primary_limit') or 1),
            max_runtime=int(options.get('max_runtime') or 30),
            no_assets=bool(options.get('no_assets', False)),
            ocr=False,
            ocr_limit=0,
            skip_dynamic=bool(options.get('skip_dynamic', True)),
            no_import=False,
            activate=True,
        )
        job.output_path = str(output_path)
        import_run = ImportRun.objects.filter(id__gt=latest_import_id).order_by('-id').first()
        if import_run:
            job.import_run = import_run
            crawl_task.created_count = import_run.created_count
            crawl_task.updated_count = import_run.updated_count
            crawl_task.skipped_count = import_run.skipped_count
            crawl_task.failed_count = import_run.failed_count
            crawl_task.attempted_count = (
                import_run.created_count
                + import_run.updated_count
                + import_run.skipped_count
                + import_run.failed_count
            )
        finish_stage(crawl_task, 'success', {
            'message': '爬蟲與匯入完成。',
            'output_path': str(output_path),
            'import_run_id': import_run.id if import_run else None,
        })
    except Exception as exc:
        finish_stage(crawl_task, 'failed', {'message': str(exc)[:1000]})
        job.status = 'failed'
        job.error_summary = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'output_path', 'import_run', 'error_summary', 'finished_at', 'updated_at'])
        command.stderr.write(f'CrawlJob {job.id} failed: {exc}')
        return

    expire_task = start_stage(job, '過期下架', '正在下架已過期活動。')
    expire_result = expire_active_activities()
    finish_stage(expire_task, 'success', expire_result)

    priority_ids = imported_activity_ids(output_path)
    limit = int(options.get('post_process_limit') or options.get('primary_limit') or 1)
    cooldown_hours = int(options.get('failure_cooldown_hours') or 24)
    link_check_limit = int(options.get('link_check_limit') or 100)
    for stage_key, label, runner, stage_limit in (
        ('ocr', 'OCR', run_ocr_stage, limit),
        ('tagging', 'AI Repair+Tag', run_ai_tag_stage, limit),
        ('search_profile', '搜尋語意', run_search_profile_stage, limit),
        ('summary', 'AI 摘要', run_summary_stage, limit),
        ('link_check', '官方連結檢查', run_link_check_stage, link_check_limit),
    ):
        task = start_stage(job, label, f'正在準備 {label} 候選。')
        try:
            result = runner(task, priority_ids, stage_limit, cooldown_hours)
            failed_stages += 1 if result.get('failed') else 0
            status = 'partial' if result.get('failed') and result.get('success') else ('failed' if result.get('failed') else 'success')
            finish_stage(task, status, result)
        except Exception as exc:
            failed_stages += 1
            finish_stage(task, 'failed', {'message': str(exc)[:1000]})

    now = timezone.now()
    job.refresh_from_db()
    tasks = list(job.tasks.all())
    failed_count = sum(task.failed_count for task in tasks)
    success_count = sum(task.created_count + task.updated_count for task in tasks)
    if failed_stages or failed_count:
        job.status = 'partial' if success_count else 'failed'
        job.error_summary = f'完整更新完成，但有 {failed_count} 筆階段處理失敗。'
    else:
        job.status = 'success'
        job.error_summary = ''
    job.finished_at = now
    job.save(update_fields=['status', 'output_path', 'import_run', 'error_summary', 'finished_at', 'updated_at'])


def start_stage(job, label, message):
    task = CrawlTask.objects.create(
        job=job,
        source_key=label,
        status='running',
        started_at=timezone.now(),
        metadata={
            'stage': label,
            'message': message,
            'processed': 0,
            'total': 0,
        },
    )
    job.updated_at = timezone.now()
    job.save(update_fields=['updated_at'])
    return task


def update_stage(task, processed, total, activity=None, message=''):
    metadata = task.metadata or {}
    metadata.update({
        'processed': processed,
        'total': total,
        'message': message,
    })
    if activity:
        metadata['current_activity_id'] = activity.id
        metadata['current_title'] = activity.title[:120]
    task.attempted_count = total
    task.metadata = metadata
    task.save(update_fields=['attempted_count', 'metadata', 'updated_at'])
    task.job.save(update_fields=['updated_at'])


def finish_stage(task, status, result):
    metadata = task.metadata or {}
    metadata['stage_result'] = result
    metadata['message'] = result.get('message') or metadata.get('message', '')
    task.status = status
    task.created_count = int(result.get('success') or task.created_count or 0)
    task.updated_count = int(result.get('skipped') or task.updated_count or 0)
    task.failed_count = int(result.get('failed') or task.failed_count or 0)
    task.metadata = metadata
    task.finished_at = timezone.now()
    task.save(update_fields=[
        'status',
        'created_count',
        'updated_count',
        'failed_count',
        'metadata',
        'finished_at',
        'updated_at',
    ])
    task.job.save(update_fields=['updated_at'])


def imported_activity_ids(output_path):
    if not output_path.exists():
        return []
    try:
        import json
        rows = json.loads(output_path.read_text(encoding='utf-8'))
    except Exception:
        return []
    ids = []
    for item in rows if isinstance(rows, list) else []:
        activity = find_activity_for_import_item(item)
        if activity and activity.id not in ids:
            ids.append(activity.id)
    return ids


def find_activity_for_import_item(item):
    source_key = item.get('source_key') or ''
    source_item_id = item.get('source_item_id') or item.get('id') or ''
    official_url = item.get('official_detail_url') or item.get('source_url') or ''
    source_url = item.get('source_url') or official_url
    if source_key and source_item_id:
        activity = Activity.objects.filter(source_key=source_key, source_item_id=source_item_id).first()
        if activity:
            return activity
    if official_url:
        activity = Activity.objects.filter(official_detail_url=official_url).first()
        if activity:
            return activity
    if source_url:
        return Activity.objects.filter(source_url=source_url).first()
    return None


def expire_active_activities():
    today = timezone.localdate()
    qs = Activity.objects.filter(status='active', end_date__date__lt=today)
    now = timezone.now()
    count = qs.update(status='inactive', updated_at=now)
    return {
        'message': f'已自動下架 {count} 筆過期活動。',
        'total': count,
        'success': count,
        'skipped': 0,
        'failed': 0,
    }


def run_ai_tag_stage(task, priority_ids, limit, cooldown_hours):
    activities = stage_candidates('tagging', priority_ids, limit, cooldown_hours)
    return run_activity_stage(task, activities, 'AI Tag', lambda activity: run_command_and_check_ai_log(
        activity,
        'tagging',
        'ai_tag_activities',
        apply=True,
        skip_tagged_success=True,
        repair_gaps_only=True,
    ))


def run_search_profile_stage(task, priority_ids, limit, cooldown_hours):
    activities = stage_candidates('search_profile', priority_ids, limit, cooldown_hours)

    def process(activity):
        profile = update_activity_search_profile(activity)
        if profile.status != 'success':
            raise RuntimeError(profile.error or '搜尋語意未成功。')
        return '搜尋語意已更新。'

    return run_activity_stage(task, activities, '搜尋語意', process)


def run_summary_stage(task, priority_ids, limit, cooldown_hours):
    activities = stage_candidates('summary', priority_ids, limit, cooldown_hours)
    return run_activity_stage(task, activities, 'AI 摘要', lambda activity: run_command_and_check_ai_log(
        activity,
        'summary',
        'generate_activity_summaries',
        limit=1,
    ))


def run_ocr_stage(task, priority_ids, limit, cooldown_hours):
    activities = stage_candidates('ocr', priority_ids, limit, cooldown_hours)
    return run_activity_stage(task, activities, 'OCR', lambda activity: run_command_and_check_ai_log(
        activity,
        'ocr',
        'process_activity_ocr',
        limit=1,
    ))


def run_link_check_stage(task, priority_ids, limit, cooldown_hours):
    session = None

    def process(activity):
        nonlocal session
        if session is None:
            import requests
            session = requests.Session()
            session.trust_env = False
        status, error = check_activity_official_link(activity, session=session)
        set_link_health(activity, status, error)
        if status == 'dead':
            raise RuntimeError(f'官方連結疑似失效：{error[:120]}')
        if status == 'error':
            return f'官方連結無法確認：{error[:120]}'
        return '官方連結正常。'

    return run_activity_stage(task, link_check_candidates(limit), '官方連結檢查', process)


def run_command_and_check_ai_log(activity, task_type, command_name, **kwargs):
    started_at = timezone.now()
    message = call_command_for_activity(command_name, activity.id, **kwargs)
    activity.refresh_from_db()
    if task_type == 'ocr':
        if activity.ocr_status and activity.ocr_status.startswith('skipped'):
            return activity.ocr_status
        if activity.ocr_status and activity.ocr_status != 'success':
            raise RuntimeError(activity.ocr_warnings[:200] or activity.ocr_status)
    latest = AIProcessingLog.objects.filter(
        activity=activity,
        task_type=task_type,
        created_at__gte=started_at,
    ).order_by('-created_at').first()
    if latest and latest.status == 'failed':
        raise RuntimeError(latest.error[:200] or f'{task_type} failed')
    return message


def call_command_for_activity(command_name, activity_id, **kwargs):
    output = StringIO()
    call_command(command_name, activity_id=activity_id, stdout=output, **kwargs)
    lines = output.getvalue().splitlines()
    return lines[-1] if lines else f'{command_name} 完成。'


def run_activity_stage(task, activities, label, process):
    total = len(activities)
    success = 0
    failed = 0
    skipped = 0
    failures = []
    update_stage(task, 0, total, message=f'{label} 候選 {total} 筆。')
    for index, activity in enumerate(activities, start=1):
        update_stage(task, index - 1, total, activity=activity, message=f'{label}：{activity.title}')
        try:
            message = process(activity)
            activity.refresh_from_db()
            if label == 'OCR' and activity.ocr_status and activity.ocr_status.startswith('skipped'):
                skipped += 1
            else:
                success += 1
            update_stage(task, index, total, activity=activity, message=message)
        except Exception as exc:
            failed += 1
            failures.append({'activity_id': activity.id, 'title': activity.title[:80], 'error': str(exc)[:200]})
            update_stage(task, index, total, activity=activity, message=f'{label} 失敗：{str(exc)[:160]}')
    return {
        'message': f'{label} 完成：成功 {success}、略過 {skipped}、失敗 {failed}。',
        'total': total,
        'success': success,
        'skipped': skipped,
        'failed': failed,
        'failures': failures[:20],
    }


def stage_candidates(stage, priority_ids, limit, cooldown_hours):
    selected = []
    base_qs = eligible_stage_queryset(stage, cooldown_hours)
    if priority_ids:
        priority = list(base_qs.filter(id__in=priority_ids).order_by('start_date', 'id')[:limit])
        selected.extend(priority)
    remaining = limit - len(selected)
    if remaining > 0:
        selected_ids = [activity.id for activity in selected]
        backlog = rotated_backlog_queryset(base_qs.exclude(id__in=selected_ids), stage)[:remaining]
        selected.extend(list(backlog))
    return [activity for activity in selected if not is_seed_activity(activity)]


def eligible_stage_queryset(stage, cooldown_hours):
    now = timezone.now()
    cutoff = now - timezone.timedelta(hours=cooldown_hours)
    recent_failed = AIProcessingLog.objects.filter(
        task_type=stage,
        status='failed',
        created_at__gte=cutoff,
        activity_id__isnull=False,
    ).values_list('activity_id', flat=True)
    qs = Activity.objects.filter(
        status='active',
        excluded_from_public=False,
        is_activity=True,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=now)
    ).exclude(
        id__in=recent_failed
    ).prefetch_related('tags')
    if stage == 'search_profile':
        qs = qs.filter(recommendation_ready=True, quality_level='high')
    if stage == 'tagging':
        success_ids = AIProcessingLog.objects.filter(
            task_type='tagging',
            status='success',
            prompt_version=PROMPT_VERSION,
            activity_id__isnull=False,
        ).values_list('activity_id', flat=True)
        qs = qs.exclude(id__in=success_ids)
        qs = qs.filter(repair_gap_filter())
    elif stage == 'search_profile':
        qs = qs.filter(Q(search_profile__isnull=True) | ~Q(search_profile__status='success'))
    elif stage == 'summary':
        qs = qs.filter(Q(line_ready=True) | Q(recommendation_ready=True), ai_summary='')
    elif stage == 'ocr':
        qs = qs.exclude(ocr_status='success').filter(
            Q(image_url__startswith='https://')
            | Q(ocr_image_url__startswith='https://')
            | Q(ocr_image_path__gt='')
            | Q(assets__ocr_eligible=True)
        )
    return qs.distinct()


def rotated_backlog_queryset(qs, stage):
    return qs.annotate(
        last_stage_attempt=Max('ai_logs__created_at', filter=Q(ai_logs__task_type=stage))
    ).order_by('last_stage_attempt', 'start_date', 'id')
