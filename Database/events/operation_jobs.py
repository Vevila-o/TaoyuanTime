import subprocess
import sys
import requests
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from django.db.models import Q
from linebot import LineBotApi
from linebot.exceptions import LineBotApiError

from events.models import AIProcessingLog, Activity, OperationJob, PushCampaign, PushDeliveryLog
from events.push_services import build_campaign_message, campaign_dedupe_key, record_campaign_failure, select_campaign_audience
from events.services import backfill_activity_assets_from_images, get_recommendation_ready_activities, is_seed_activity
from events.search_profiles import set_link_health, update_activity_search_profile


DEFAULT_JOB_LIMIT = 20


def create_operation_job(job_type, title='', options=None, created_by='local_admin'):
    return OperationJob.objects.create(
        job_type=job_type,
        title=title or default_job_title(job_type),
        options=options or {},
        created_by=created_by or 'local_admin',
        progress_message='任務已建立，等待背景程序開始。',
    )


def default_job_title(job_type):
    return {
        'ai_tag': '一鍵 AI Tag',
        'ocr': '一鍵 OCR',
        'summary': '一鍵 AI 摘要',
        'push': '推播發送',
        'crawler': '爬蟲任務',
        'link_check': '官方連結健康檢查',
    }.get(job_type, '營運任務')


def start_operation_job_process(job):
    log_dir = Path(settings.BASE_DIR) / 'scraping' / 'data' / 'job_logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f'operation_job_{job.id}.log'
    stderr_path = log_dir / f'operation_job_{job.id}.err.log'
    command = [sys.executable, str(Path(settings.BASE_DIR) / 'manage.py'), 'run_operation_job', str(job.id)]
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    stdout = stdout_path.open('a', encoding='utf-8')
    stderr = stderr_path.open('a', encoding='utf-8')
    try:
        subprocess.Popen(
            command,
            cwd=str(settings.BASE_DIR),
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )
    finally:
        stdout.close()
        stderr.close()
    job.progress_message = f'背景程序已啟動。log={stdout_path}'
    job.save(update_fields=['progress_message', 'updated_at'])


def run_operation_job(job_id):
    job = OperationJob.objects.get(id=job_id)
    if job.status == 'cancelled':
        return job
    job.status = 'running'
    job.started_at = job.started_at or timezone.now()
    job.progress_message = '正在準備候選資料。'
    job.save(update_fields=['status', 'started_at', 'progress_message', 'updated_at'])
    try:
        if job.job_type == 'ai_tag':
            run_ai_tag_job(job)
        elif job.job_type == 'ocr':
            run_ocr_job(job)
        elif job.job_type == 'summary':
            run_summary_job(job)
        elif job.job_type == 'push':
            run_push_job(job)
        elif job.job_type == 'link_check':
            run_link_check_job(job)
        else:
            raise ValueError(f'Unsupported job_type: {job.job_type}')
        finish_job(job)
    except Exception as exc:
        job.refresh_from_db()
        if job.status != 'cancelled':
            job.status = 'failed'
            job.error_summary = str(exc)[:1000]
            job.progress_message = '任務失敗。'
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'error_summary', 'progress_message', 'finished_at', 'updated_at'])
    return job


def run_ai_tag_job(job):
    options = job.options or {}
    limit = int(options.get('limit') or DEFAULT_JOB_LIMIT)
    mode = options.get('mode') or 'suggestions'
    activities = search_profile_candidates(limit) if mode == 'search_profile_only' else ai_tag_candidates(limit)
    total_message = '搜尋語意候選已載入。' if mode == 'search_profile_only' else 'AI Tag 候選已載入。'
    set_total(job, len(activities), total_message)
    for activity in activities:
        if should_stop(job):
            return
        update_current(job, activity, '正在補搜尋語意。' if mode == 'search_profile_only' else '正在處理 AI Tag。')
        output = StringIO()
        try:
            if mode == 'search_profile_only':
                profile = update_activity_search_profile(activity, force=bool(options.get('force')))
                if profile.status == 'success':
                    increment(job, success=1, message='搜尋語意已更新。')
                else:
                    increment(job, failed=1, message=profile.error[:200] or '搜尋語意未成功。')
            else:
                kwargs = {'activity_id': activity.id, 'stdout': output}
                if mode == 'apply':
                    kwargs['apply'] = True
                else:
                    kwargs['create_suggestions'] = True
                call_command('ai_tag_activities', **kwargs)
                increment(job, success=1, message=last_output_line(output) or 'AI Tag 處理完成。')
        except Exception as exc:
            label = '搜尋語意' if mode == 'search_profile_only' else 'AI Tag'
            increment(job, failed=1, message=f'{label} 失敗：{str(exc)[:200]}')


def run_ocr_job(job):
    options = job.options or {}
    limit = int(options.get('limit') or DEFAULT_JOB_LIMIT)
    backfill_result = backfill_activity_assets_from_images(dry_run=False)
    activities = ocr_candidates(limit)
    set_total(job, len(activities), f'圖片資產補齊：新增 {backfill_result["created"]}，開始 OCR。')
    for activity in activities:
        if should_stop(job):
            return
        update_current(job, activity, '正在處理 OCR。')
        output = StringIO()
        try:
            call_command('process_activity_ocr', activity_id=activity.id, limit=1, stdout=output)
            activity.refresh_from_db()
            if activity.ocr_status == 'success':
                increment(job, success=1, message=last_output_line(output) or 'OCR 成功。')
            elif activity.ocr_status and activity.ocr_status.startswith('skipped'):
                increment(job, skipped=1, message=activity.ocr_status)
            else:
                increment(job, failed=1, message=activity.ocr_warnings[:200] or activity.ocr_status or 'OCR 未成功。')
        except Exception as exc:
            increment(job, failed=1, message=f'OCR 失敗：{str(exc)[:200]}')


def run_summary_job(job):
    options = job.options or {}
    limit = int(options.get('limit') or 100)
    force = bool(options.get('force'))
    activities = summary_candidates(limit, force=force)
    set_total(job, len(activities), 'AI 摘要候選已載入。')
    for activity in activities:
        if should_stop(job):
            return
        update_current(job, activity, '正在產生 AI 摘要。')
        output = StringIO()
        try:
            call_command('generate_activity_summaries', activity_id=activity.id, limit=1, force=force, stdout=output)
            activity.refresh_from_db()
            if activity.ai_summary:
                increment(job, success=1, message=last_output_line(output) or '摘要完成。')
            else:
                increment(job, failed=1, message='摘要仍為空。')
        except Exception as exc:
            increment(job, failed=1, message=f'摘要失敗：{str(exc)[:200]}')


def run_push_job(job):
    options = job.options or {}
    campaign = PushCampaign.objects.select_related('activity').get(id=options.get('campaign_id'))
    dry_run = bool(options.get('dry_run'))
    users = list(select_campaign_audience(campaign))
    set_total(job, len(users), '推播受眾已載入。')
    if dry_run:
        for user in users:
            if should_stop(job):
                return
            update_current(job, None, f'dry-run：{user.display_name or user.line_user_id}')
            dedupe_key = campaign_dedupe_key(campaign, user)
            if PushDeliveryLog.objects.filter(notification_type='campaign', dedupe_key=dedupe_key, status='sent').exists():
                increment(job, skipped=1, message='此使用者已收到同活動推播。')
            else:
                increment(job, success=1, message='dry-run 可發送。')
        return

    token = getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '')
    if not token:
        raise RuntimeError('LINE_CHANNEL_ACCESS_TOKEN is not configured.')
    line_bot_api = LineBotApi(token)
    campaign.status = 'sending'
    campaign.save(update_fields=['status', 'updated_at'])
    for user in users:
        if should_stop(job):
            campaign.status = 'cancelled'
            campaign.save(update_fields=['status', 'updated_at'])
            return
        update_current(job, None, f'推播給 {user.display_name or user.line_user_id}')
        dedupe_key = campaign_dedupe_key(campaign, user)
        if PushDeliveryLog.objects.filter(notification_type='campaign', dedupe_key=dedupe_key, status='sent').exists():
            increment(job, skipped=1, message='此使用者已收到同活動推播。')
            continue
        try:
            line_bot_api.push_message(user.line_user_id, build_campaign_message(campaign, user=user))
            PushDeliveryLog.objects.create(
                campaign=campaign,
                user=user,
                activity=campaign.activity,
                status='sent',
                notification_type='campaign',
                dedupe_key=dedupe_key,
                line_response='ok',
                sent_at=timezone.now(),
            )
            increment(job, success=1, message='推播成功。')
        except LineBotApiError as exc:
            record_campaign_failure(campaign, user, dedupe_key, exc)
            increment(job, failed=1, message=f'LINE 推播失敗：{str(exc)[:200]}')
        except Exception as exc:
            record_campaign_failure(campaign, user, dedupe_key, exc)
            increment(job, failed=1, message=f'推播失敗：{str(exc)[:200]}')
    job.refresh_from_db()
    campaign.status = 'sent' if job.failed_count == 0 else 'failed'
    campaign.save(update_fields=['status', 'updated_at'])


def ai_tag_candidates(limit):
    tagged_ids = AIProcessingLog.objects.filter(
        task_type='tagging',
        status='success',
        activity_id__isnull=False,
    ).values_list('activity_id', flat=True)
    qs = get_recommendation_ready_activities().filter(
        status='active',
        is_activity=True,
        recommendation_ready=True,
        quality_level='high',
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=timezone.now())
    ).exclude(
        official_detail_url=''
    ).prefetch_related('tags')
    qs = qs.exclude(id__in=tagged_ids, search_profile__status='success')
    return [activity for activity in qs.distinct().order_by('start_date', 'id')[:limit * 2] if not is_seed_activity(activity)][:limit]


def search_profile_candidates(limit):
    qs = get_recommendation_ready_activities().filter(
        status='active',
        is_activity=True,
        recommendation_ready=True,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=timezone.now())
    ).exclude(
        official_detail_url=''
    ).filter(
        Q(search_profile__isnull=True) | ~Q(search_profile__status='success')
    ).prefetch_related('tags')
    return [activity for activity in qs.distinct().order_by('start_date', 'id')[:limit * 2] if not is_seed_activity(activity)][:limit]


def run_link_check_job(job):
    options = job.options or {}
    limit = int(options.get('limit') or 100)
    activities = link_check_candidates(limit)
    set_total(job, len(activities), '官方連結候選已載入。')
    session = requests.Session()
    session.trust_env = False
    for activity in activities:
        if should_stop(job):
            return
        update_current(job, activity, '正在檢查官方連結。')
        try:
            status, error = check_activity_official_link(activity, session=session)
            set_link_health(activity, status, error)
            if status == 'ok':
                increment(job, success=1, message='官方連結正常。')
            elif status == 'dead':
                increment(job, failed=1, message=f'官方連結疑似失效：{error[:120]}')
            else:
                increment(job, skipped=1, message=f'官方連結無法確認：{error[:120]}')
        except Exception as exc:
            set_link_health(activity, 'error', str(exc))
            increment(job, failed=1, message=f'連結檢查失敗：{str(exc)[:200]}')


def link_check_candidates(limit):
    qs = Activity.objects.filter(
        status='active',
        is_activity=True,
    ).filter(
        Q(excluded_from_public=False) | Q(exclude_reason='dead_official_link') | Q(official_link_status='dead')
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=timezone.now())
    ).exclude(
        official_detail_url=''
    ).order_by('official_link_checked_at', 'start_date', 'id')
    return [activity for activity in qs[:limit * 2] if not is_seed_activity(activity)][:limit]


def check_activity_official_link(activity, session=None):
    url = (activity.official_detail_url or '').strip()
    if not url:
        return 'error', 'missing official_detail_url'
    client = session or requests.Session()
    headers = {'User-Agent': 'TaoyuanTime-LinkHealth/1.0'}
    try:
        response = client.get(url, headers=headers, timeout=8, allow_redirects=True)
    except requests.Timeout:
        return 'error', 'timeout'
    except requests.RequestException as exc:
        return 'error', str(exc)
    if response.status_code in {404, 410}:
        return 'dead', f'HTTP {response.status_code}'
    if response.status_code >= 500:
        return 'error', f'HTTP {response.status_code}'
    if response.status_code >= 400:
        return 'dead', f'HTTP {response.status_code}'
    text = (response.text or '')[:500].lower()
    if any(marker in text for marker in ('404 not found', '頁面不存在', '找不到頁面', '資料不存在')):
        return 'dead', 'page content indicates missing page'
    return 'ok', f'HTTP {response.status_code}'


def ocr_candidates(limit):
    qs = Activity.objects.filter(
        status='active',
        excluded_from_public=False,
        is_activity=True,
        recommendation_ready=True,
        quality_level='high',
    ).exclude(
        ocr_status='success'
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=timezone.now())
    ).filter(
        Q(image_url__startswith='https://')
        | Q(ocr_image_url__startswith='https://')
        | Q(ocr_image_path__gt='')
        | Q(assets__ocr_eligible=True)
    )
    return [activity for activity in qs.distinct().order_by('start_date', 'id')[:limit * 2] if not is_seed_activity(activity)][:limit]


def summary_candidates(limit, force=False):
    qs = Activity.objects.filter(
        is_activity=True,
        status='active',
        excluded_from_public=False,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=timezone.now())
    ).filter(
        Q(line_ready=True) | Q(recommendation_ready=True)
    ).exclude(
        official_detail_url=''
    )
    if not force:
        qs = qs.filter(ai_summary='')
    return [activity for activity in qs.order_by('start_date', '-updated_at', 'id')[:limit * 2] if not is_seed_activity(activity)][:limit]


def set_total(job, total, message):
    job.total_count = total
    job.progress_message = message
    if total == 0:
        job.status = 'success'
        job.finished_at = timezone.now()
        job.progress_message = '沒有待處理資料。'
    job.save(update_fields=['total_count', 'status', 'progress_message', 'finished_at', 'updated_at'])


def update_current(job, activity, message):
    job.current_label = activity.title[:300] if activity else message[:300]
    job.progress_message = message
    job.save(update_fields=['current_label', 'progress_message', 'updated_at'])


def increment(job, success=0, failed=0, skipped=0, message=''):
    job.refresh_from_db()
    job.processed_count += 1
    job.success_count += success
    job.failed_count += failed
    job.skipped_count += skipped
    if failed and message:
        job.error_summary = message[:1000]
    if message:
        job.progress_message = message
    job.save(update_fields=[
        'processed_count',
        'success_count',
        'failed_count',
        'skipped_count',
        'error_summary',
        'progress_message',
        'updated_at',
    ])


def should_stop(job):
    job.refresh_from_db()
    return job.status == 'cancelled'


def finish_job(job):
    job.refresh_from_db()
    if job.status == 'cancelled':
        job.finished_at = timezone.now()
        job.progress_message = '任務已取消。'
        job.save(update_fields=['finished_at', 'progress_message', 'updated_at'])
        return
    if job.total_count == 0:
        status = 'success'
    elif job.failed_count and job.success_count:
        status = 'partial'
    elif job.failed_count and not job.success_count:
        status = 'failed'
    else:
        status = 'success'
    job.status = status
    job.finished_at = timezone.now()
    job.result_summary = {
        'processed': job.processed_count,
        'success': job.success_count,
        'failed': job.failed_count,
        'skipped': job.skipped_count,
    }
    job.progress_message = '任務完成。' if status == 'success' else '任務完成，但有失敗或略過項目。'
    job.save(update_fields=['status', 'finished_at', 'result_summary', 'progress_message', 'updated_at'])


def last_output_line(output):
    lines = output.getvalue().splitlines()
    return lines[-1] if lines else ''
