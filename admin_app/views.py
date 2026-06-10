import json
import subprocess
import sys

from django.contrib import messages
from datetime import timedelta
from io import StringIO
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management import call_command
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from events.models import (
  ActionLog,
  Activity,
  ActivityAsset,
  ActivityChangeLog,
  ActivitySearchProfile,
  ActivityTagSuggestion,
  AdminAuditLog,
  CrawlJob,
  CrawlTask,
  ImportRun,
  LineConversationState,
  OperationJob,
  PushCampaign,
  PushDeliveryLog,
  Subscription,
  Tag,
  UserProfile,
  AIProcessingLog,
)
from events.push_services import select_campaign_audience, send_campaign as send_push_campaign_now
from events.operation_jobs import create_operation_job, start_operation_job_process
from events.services import activity_business_key, backfill_activity_assets_from_images, is_seed_activity
from .diagnostics import (
  activity_exposure_diagnostic,
  apply_readiness_filter,
  exposure_summary,
  has_official_detail,
  human_action_label,
  is_expired,
  read_health_report,
  recent_recommended_activity_ids,
)


DISTRICTS = ['桃園', '中壢', '平鎮', '八德', '楊梅', '蘆竹', '大溪', '龍潭', '龜山', '大園', '觀音', '新屋', '復興']


def login(request):
  return render(request, 'login.html')


def dashboard(request):
  now = timezone.now()
  active_count = Activity.objects.filter(status='active').count()
  total_count = Activity.objects.count()
  line_ready_count = Activity.objects.filter(line_ready=True).count()
  subscription_count = Subscription.objects.count()
  user_count = UserProfile.objects.count()
  push_total = PushDeliveryLog.objects.count()
  push_sent = PushDeliveryLog.objects.filter(status='sent').count()
  push_success_rate = round((push_sent / push_total) * 100, 1) if push_total else 0
  top_activities = (ActionLog.objects
                    .filter(activity_id__isnull=False)
                    .values('activity__title')
                    .annotate(count=Count('id'))
                    .order_by('-count')[:8])
  tag_distribution = (Tag.objects
                      .annotate(activity_count=Count('activities'))
                      .filter(activity_count__gt=0)
                      .order_by('-activity_count')[:8])
  filter_summary, top_filter_reasons = exposure_summary()
  missing_search_profile_count = Activity.objects.filter(
    status='active',
    recommendation_ready=True,
  ).filter(Q(search_profile__isnull=True) | ~Q(search_profile__status='success')).count()
  dead_link_count = Activity.objects.filter(status='active', official_link_status='dead').count()
  database_status = '需處理缺口' if (
    Activity.objects.filter(status='active', end_date__lt=now).exists()
    or Activity.objects.filter(status='active', line_ready=True).filter(Q(image_url='') | Q(image_url__icontains='placehold.co')).exists()
    or missing_search_profile_count
    or dead_link_count
  ) else '正常'
  context = {
    'active_count': active_count,
    'total_count': total_count,
    'draft_count': Activity.objects.filter(status='draft').count(),
    'inactive_count': Activity.objects.filter(status='inactive').count(),
    'line_ready_count': line_ready_count,
    'serviceable_active_count': Activity.objects.filter(status='active').filter(Q(end_date__isnull=True) | Q(end_date__gte=now)).count(),
    'expired_active_count': Activity.objects.filter(status='active', end_date__lt=now).count(),
    'missing_detail_count': Activity.objects.filter(status='active', line_ready=True).filter(Q(official_detail_url__isnull=True) | Q(official_detail_url='')).count(),
    'placeholder_image_count': Activity.objects.filter(status='active', line_ready=True).filter(Q(image_url='') | Q(image_url__icontains='placehold.co')).count(),
    'test_user_count': UserProfile.objects.filter(Q(line_user_id__startswith='codex') | Q(line_user_id__startswith='line-test') | Q(line_user_id='debug-user')).count(),
    'subscription_count': subscription_count,
    'user_count': user_count,
    'push_total': push_total,
    'push_success_rate': push_success_rate,
    'recent_imports': ImportRun.objects.all()[:5],
    'recent_crawl_jobs': CrawlJob.objects.all()[:5],
    'pending_activity_changes': ActivityChangeLog.objects.filter(notify_required=True, notified_at__isnull=True).count(),
    'database_status': database_status,
    'missing_search_profile_count': missing_search_profile_count,
    'dead_link_count': dead_link_count,
    'top_activities': top_activities,
    'tag_distribution': tag_distribution,
    'filter_summary': filter_summary,
    'top_filter_reasons': top_filter_reasons,
    'health_report': read_health_report(),
  }
  return render(request, 'dashboard.html', context)


def queue_operation_job(request, job_type, title, options):
  job = create_operation_job(job_type, title=title, options=options, created_by=audit_actor(request))
  audit(request, f'queue_operation_{job_type}', None, {'job_id': job.id, 'options': options})
  try:
    start_operation_job_process(job)
    messages.success(request, f'任務 #{job.id} 已建立並啟動。')
  except Exception as exc:
    job.status = 'failed'
    job.error_summary = str(exc)[:1000]
    job.finished_at = timezone.now()
    job.progress_message = '背景程序啟動失敗。'
    job.save(update_fields=['status', 'error_summary', 'finished_at', 'progress_message', 'updated_at'])
    messages.error(request, f'任務 #{job.id} 建立成功，但啟動背景程序失敗：{str(exc)[:300]}')
  return job


def start_crawl_job_process(job):
  log_dir = Path(settings.BASE_DIR) / 'scraping' / 'data' / 'job_logs'
  log_dir.mkdir(parents=True, exist_ok=True)
  stdout_path = log_dir / f'crawl_job_{job.id}.log'
  stderr_path = log_dir / f'crawl_job_{job.id}.err.log'
  command = [
    sys.executable,
    str(Path(settings.BASE_DIR) / 'manage.py'),
    'run_queued_crawl_jobs',
    '--job-id',
    str(job.id),
  ]
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
  options = job.options or {}
  options['stdout_log'] = str(stdout_path)
  options['stderr_log'] = str(stderr_path)
  job.options = options
  job.save(update_fields=['options', 'updated_at'])


def operations(request):
  if request.method == 'POST':
    action = request.POST.get('action')
    if action == 'backfill_assets':
      result = backfill_activity_assets_from_images(dry_run=False)
      messages.success(
        request,
        f'圖片資產補齊完成：檢查 {result["checked"]} 筆，新增 {result["created"]} 筆，略過 {result["skipped"]} 筆。',
      )
      return redirect('operations')
    if action == 'ai_tag_suggestions':
      job = queue_operation_job(request, 'ai_tag', '一鍵產生 AI Tag 建議', {'limit': 20, 'mode': 'suggestions'})
      return redirect('operationJobDetail', id=job.id)
    if action == 'search_profile_only':
      job = queue_operation_job(request, 'ai_tag', '一鍵補搜尋語意', {'limit': 50, 'mode': 'search_profile_only'})
      return redirect('operationJobDetail', id=job.id)
    if action == 'ai_tag_apply':
      job = queue_operation_job(request, 'ai_tag', '一鍵直接套用 AI Tag', {'limit': 20, 'mode': 'apply'})
      return redirect('operationJobDetail', id=job.id)
    if action == 'generate_summary':
      job = queue_operation_job(request, 'summary', '一鍵產生 AI 摘要', {'limit': 100, 'force': False})
      return redirect('operationJobDetail', id=job.id)
    if action == 'process_ocr':
      job = queue_operation_job(request, 'ocr', '一鍵處理 OCR', {'limit': 20})
      return redirect('operationJobDetail', id=job.id)
    if action == 'link_check':
      job = queue_operation_job(request, 'link_check', '一鍵檢查官方連結', {'limit': 100})
      return redirect('operationJobDetail', id=job.id)

  now = timezone.now()
  active_serviceable = Activity.objects.filter(status='active').filter(Q(end_date__isnull=True) | Q(end_date__gte=now))
  summary_candidates = [
    activity for activity in active_serviceable.filter(
      is_activity=True,
    ).filter(
      Q(line_ready=True) | Q(recommendation_ready=True)
    ).exclude(
      official_detail_url=''
    ).exclude(ai_summary='')
    if not is_seed_activity(activity)
  ]
  missing_summary_candidates = [
    activity for activity in active_serviceable.filter(
      is_activity=True,
      ai_summary='',
    ).filter(
      Q(line_ready=True) | Q(recommendation_ready=True)
    ).exclude(
      official_detail_url=''
    )
    if not is_seed_activity(activity)
  ]
  ai_tag_qs = active_serviceable.filter(
    is_activity=True,
    recommendation_ready=True,
  ).exclude(official_detail_url='').order_by('start_date', 'id')
  tagged_success_ids = AIProcessingLog.objects.filter(
    task_type='tagging',
    status='success',
    activity_id__isnull=False,
  ).values_list('activity_id', flat=True)
  pending_ai_tag_qs = ai_tag_qs.exclude(id__in=tagged_success_ids)
  missing_search_profile_qs = ai_tag_qs.filter(Q(search_profile__isnull=True) | ~Q(search_profile__status='success'))
  dead_link_qs = active_serviceable.filter(official_link_status='dead')
  ocr_qs = active_serviceable.filter(
    is_activity=True,
    recommendation_ready=True,
  ).exclude(
    ocr_status__in=['success', 'skipped_no_image', 'skipped_no_local_image', 'skipped_not_front_pool']
  ).order_by('start_date', 'id')
  ocr_has_image_qs = ocr_qs.filter(
    Q(image_url__startswith='https://') |
    Q(ocr_image_url__startswith='https://') |
    Q(assets__ocr_eligible=True)
  ).distinct()
  ocr_no_image_qs = ocr_qs.exclude(id__in=ocr_has_image_qs.values_list('id', flat=True))
  recent_ai_failures = AIProcessingLog.objects.filter(status='failed').order_by('-created_at')[:8]
  context = {
    'missing_summary_count': len(missing_summary_candidates),
    'summary_existing_count': len(summary_candidates),
    'ai_tag_count': pending_ai_tag_qs.count(),
    'missing_search_profile_count': missing_search_profile_qs.count(),
    'dead_link_count': dead_link_qs.count(),
    'ocr_candidate_count': ocr_qs.count(),
    'ocr_has_image_count': ocr_has_image_qs.count(),
    'ocr_no_image_count': ocr_no_image_qs.count(),
    'activity_asset_count': ActivityAsset.objects.count(),
    'expired_active_count': Activity.objects.filter(status='active', end_date__lt=now).count(),
    'health_report': read_health_report(),
    'missing_summary_examples': missing_summary_candidates[:10],
    'ai_tag_examples': pending_ai_tag_qs[:10],
    'missing_search_profile_examples': missing_search_profile_qs[:10],
    'ocr_examples': ocr_has_image_qs[:50],
    'recent_ai_failures': recent_ai_failures,
    'recent_operation_jobs': OperationJob.objects.all()[:8],
  }
  return render(request, 'operations.html', context)


def activityList(request):
  keyword = request.GET.get('q', '').strip()
  status = request.GET.get('status', '').strip()
  district = request.GET.get('district', '').strip()
  readiness = request.GET.get('readiness', '').strip()
  qs = Activity.objects.select_related('search_profile').prefetch_related('tags').all()
  if keyword:
    qs = qs.filter(Q(title__icontains=keyword) | Q(description__icontains=keyword) | Q(location__icontains=keyword))
  if status:
    qs = qs.filter(status=status)
  if district:
    qs = qs.filter(district__icontains=district)
  if readiness == 'line_ready':
    qs = qs.filter(line_ready=True)
  elif readiness == 'needs_review':
    qs = qs.filter(Q(status='draft') | Q(line_ready=False) | Q(recommendation_ready=False))
  elif readiness == 'expired_active':
    qs = qs.filter(status='active', end_date__lt=timezone.now())
  elif readiness == 'missing_detail':
    qs = qs.filter(status='active', line_ready=True).filter(Q(official_detail_url__isnull=True) | Q(official_detail_url=''))
  elif readiness == 'fallback_image':
    qs = qs.filter(status='active', line_ready=True).filter(Q(image_url='') | Q(image_url__icontains='placehold.co'))
  elif readiness == 'seed_sample':
    qs = qs.filter(Q(source_url__contains='/sample/') | Q(official_detail_url__contains='/sample/') | Q(title__startswith='測試非活動'))
  elif readiness == 'missing_search_profile':
    qs = qs.filter(Q(search_profile__isnull=True) | ~Q(search_profile__status='success'))
  elif readiness == 'search_profile_failed':
    qs = qs.filter(search_profile__status='failed')
  elif readiness == 'link_dead':
    qs = qs.filter(official_link_status='dead')
  elif readiness in {'line_blocked', 'recommendation_blocked', 'ai_summary_blocked', 'ocr_blocked', 'quality_warning'}:
    qs = apply_readiness_filter(qs, readiness)
  activities = list(qs.order_by('-updated_at')[:200])
  for activity in activities:
    activity.exposure_diagnostic = activity_exposure_diagnostic(activity, now=timezone.now())
  context = {
    'activities': activities,
    'districts': DISTRICTS,
    'filters': {'q': keyword, 'status': status, 'district': district, 'readiness': readiness},
    'pending_tag_suggestions': ActivityTagSuggestion.objects.filter(status='pending').count(),
    'filter_summary': exposure_summary()[0],
  }
  return render(request, 'activityList.html', context)


def activityAdd(request):
  if request.method == 'POST':
    activity = Activity.objects.create(**activity_form_values(request.POST))
    apply_activity_tags(activity, request.POST.getlist('tags'))
    audit(request, 'create_activity', activity, {'title': activity.title})
    messages.success(request, '活動已新增。')
    return redirect('activityEdit', id=activity.id)
  return render(request, 'activityAdd.html', activity_form_context())


def activityEdit(request, id):
  activity = get_object_or_404(Activity, id=id)
  if request.method == 'POST':
    values = activity_form_values(request.POST, activity=activity)
    for field, value in values.items():
      setattr(activity, field, value)
    activity.save()
    apply_activity_tags(activity, request.POST.getlist('tags'))
    audit(request, 'update_activity', activity, {'title': activity.title})
    messages.success(request, '活動已更新。')
    return redirect('activityEdit', id=activity.id)
  context = activity_form_context(activity)
  context.update({
    'change_logs': activity.change_logs.all()[:20],
    'ai_logs': activity.ai_logs.all()[:20],
    'admin_logs': activity.admin_audit_logs.all()[:20],
    'exposure_diagnostic': activity_exposure_diagnostic(activity),
    'search_profile': getattr(activity, 'search_profile', None),
  })
  return render(request, 'activityEdit.html', context)


@require_POST
def activitySetStatus(request, id):
  activity = get_object_or_404(Activity, id=id)
  status = request.POST.get('status')
  if status not in {'active', 'inactive', 'draft'}:
    messages.error(request, '不支援的活動狀態。')
    return redirect('activityList')
  activity.status = status
  activity.save(update_fields=['status', 'updated_at'])
  audit(request, 'set_status', activity, {'status': status})
  messages.success(request, f'活動已更新為 {activity.get_status_display()}。')
  return redirect('activityList')


@require_POST
def activitySetReadiness(request, id):
  activity = get_object_or_404(Activity, id=id)
  target = request.POST.get('target')
  value = request.POST.get('value') == 'true'
  if target not in {'line_ready', 'recommendation_ready', 'ai_ready'}:
    messages.error(request, '不支援的 ready 欄位。')
    return redirect('activityEdit', id=id)
  if value:
    hard_errors = []
    if activity.status != 'active':
      hard_errors.append('活動尚未上架')
    if is_expired(activity):
      hard_errors.append('活動已過期')
    if not activity.is_activity:
      hard_errors.append('資料不是活動')
    if not has_official_detail(activity):
      hard_errors.append('缺官方詳細頁')
    if activity.quality_level == 'rejected':
      hard_errors.append('品質為 rejected')
    if hard_errors:
      messages.error(request, '無法標記 ready：' + '、'.join(hard_errors))
      return redirect('activityEdit', id=id)
  setattr(activity, target, value)
  activity.save(update_fields=[target, 'updated_at'])
  audit(request, 'set_readiness', activity, {'target': target, 'value': value})
  messages.success(request, f'{target} 已更新為 {"啟用" if value else "關閉"}。')
  return redirect('activityEdit', id=id)


@require_POST
def activityApplyAiTags(request, id):
  activity = get_object_or_404(Activity, id=id)
  output = StringIO()
  try:
    call_command('ai_tag_activities', activity_id=activity.id, apply=True, stdout=output)
    activity.refresh_from_db()
    audit(request, 'apply_ai_tags', activity, {'stdout': output.getvalue()[-1000:]})
    lines = output.getvalue().splitlines()
    suffix = f' {lines[-1]}' if lines else ''
    messages.success(request, f'AI Tag 已套用到這筆活動。{suffix}')
  except Exception as exc:
    messages.error(request, f'AI Tag 套用失敗：{str(exc)[:300]}')
  return redirect('activityEdit', id=id)


def tagReview(request):
  suggestions = ActivityTagSuggestion.objects.select_related('activity', 'tag').filter(status='pending')[:200]
  return render(request, 'tagReview.html', {
    'suggestions': suggestions,
    'ai_tag_target_count': apply_readiness_filter(Activity.objects.all(), 'recommendation_blocked').count(),
    'recommendation_ready_count': Activity.objects.filter(status='active', recommendation_ready=True).filter(Q(end_date__isnull=True) | Q(end_date__gte=timezone.now())).exclude(official_detail_url='').count(),
  })


@require_POST
def tagSuggestionAction(request, id):
  suggestion = get_object_or_404(ActivityTagSuggestion, id=id)
  action = request.POST.get('action')
  if action == 'approve':
    tag = suggestion.tag or Tag.objects.filter(
      name=suggestion.tag_name,
      tag_type=suggestion.tag_type,
      is_active=True,
    ).first()
    if not tag:
      messages.error(request, '找不到既有 Tag，未建立新 Tag。')
      return redirect('tagReview')
    suggestion.activity.tags.add(tag)
    suggestion.tag = tag
    suggestion.status = 'approved'
    suggestion.reviewed_at = timezone.now()
    suggestion.save(update_fields=['tag', 'status', 'reviewed_at', 'updated_at'])
    audit(request, 'tag_approve', suggestion.activity, {'tag': suggestion.tag_name})
    messages.success(request, 'Tag 建議已核准並寫入活動。')
  elif action == 'reject':
    suggestion.status = 'rejected'
    suggestion.reviewed_at = timezone.now()
    suggestion.save(update_fields=['status', 'reviewed_at', 'updated_at'])
    audit(request, 'tag_reject', suggestion.activity, {'tag': suggestion.tag_name})
    messages.success(request, 'Tag 建議已拒絕。')
  else:
    messages.error(request, '不支援的審核動作。')
  return redirect('tagReview')


def pushManagement(request):
  if request.method == 'POST':
    action = request.POST.get('action') or 'create_campaign'
    if action == 'create_campaign':
      activity = Activity.objects.filter(id=request.POST.get('activity_id')).first()
      recent_duplicate_count = 0
      if activity:
        duplicate_key = f'campaign_activity:{activity_business_key(activity)}'
        recent_duplicate_count = PushDeliveryLog.objects.filter(
          notification_type='campaign',
          status='sent',
          dedupe_key__contains=duplicate_key,
        ).count()
      campaign = PushCampaign.objects.create(
        title=request.POST.get('title', '').strip() or '手動推播',
        activity=activity,
        message=request.POST.get('message', '').strip(),
        audience_rule={'type': request.POST.get('audience', 'all_push_enabled')},
        scheduled_at=parse_datetime_field(request.POST.get('scheduled_at')),
        status='scheduled' if request.POST.get('scheduled_at') else 'draft',
      )
      audit(request, 'create_push_campaign', activity, {'campaign_id': campaign.id})
      if recent_duplicate_count:
        messages.warning(request, f'推播任務 #{campaign.id} 已建立；此活動近期已有 {recent_duplicate_count} 筆成功推播紀錄，發送前請先 dry-run。')
      else:
        messages.success(request, f'推播任務 #{campaign.id} 已建立，可在下方預覽、dry-run 或立即發送。')
      return redirect('pushManagement')

    campaign = get_object_or_404(PushCampaign.objects.select_related('activity'), id=request.POST.get('campaign_id'))
    if action == 'cancel_campaign':
      if campaign.status in {'draft', 'scheduled'}:
        campaign.status = 'cancelled'
        campaign.save(update_fields=['status', 'updated_at'])
        audit(request, 'cancel_push_campaign', campaign.activity, {'campaign_id': campaign.id})
        messages.warning(request, f'推播任務 #{campaign.id} 已取消。')
      else:
        messages.error(request, '只有草稿或預定推播可以取消。')
    elif action == 'preview_campaign':
      audience_count = select_campaign_audience(campaign).count()
      messages.info(request, f'推播任務 #{campaign.id} 目前符合受眾 {audience_count} 人。')
    elif action == 'dry_run_campaign':
      result = send_push_campaign_now(campaign, dry_run=True)
      messages.info(request, f'dry-run：任務 #{campaign.id} 受眾 {result.users} 人，不會實際推播。')
    elif action == 'send_campaign_now':
      if campaign.status == 'cancelled':
        messages.error(request, '已取消的推播不能發送。')
        return redirect('pushManagement')
      if campaign.status == 'sent':
        messages.error(request, '已送出的推播不能重複發送。')
        return redirect('pushManagement')
      job = queue_operation_job(
        request,
        'push',
        f'推播發送 #{campaign.id} {campaign.title}',
        {'campaign_id': campaign.id, 'dry_run': False},
      )
      audit(request, 'queue_push_campaign', campaign.activity, {'campaign_id': campaign.id, 'job_id': job.id})
      return redirect('operationJobDetail', id=job.id)
    else:
      messages.error(request, '不支援的推播操作。')
    return redirect('pushManagement')

  activity_q = request.GET.get('activity_q', '').strip()
  activity_qs = Activity.objects.filter(status='active').filter(Q(end_date__isnull=True) | Q(end_date__gte=timezone.now()))
  if activity_q:
    activity_qs = activity_qs.filter(Q(title__icontains=activity_q) | Q(location__icontains=activity_q) | Q(district__icontains=activity_q))
  activity_limit = 50 if activity_q else 20
  activities = list(activity_qs.order_by('start_date', 'id')[:activity_limit])
  for activity in activities:
    duplicate_key = f'campaign_activity:{activity_business_key(activity)}'
    activity.same_activity_sent_count = PushDeliveryLog.objects.filter(
      notification_type='campaign',
      status='sent',
      dedupe_key__contains=duplicate_key,
    ).count()
    activity.push_option_note = '近期已推播' if activity.same_activity_sent_count else '可推播'
  campaigns = PushCampaign.objects.select_related('activity').all()[:100]
  for campaign in campaigns:
    campaign.can_cancel = campaign.status in {'draft', 'scheduled'}
    campaign.can_send = campaign.status not in {'sent', 'cancelled', 'sending'}
    campaign.same_activity_sent_count = 0
    if campaign.activity_id:
      duplicate_key = f'campaign_activity:{activity_business_key(campaign.activity)}'
      campaign.same_activity_sent_count = PushDeliveryLog.objects.filter(
        notification_type='campaign',
        status='sent',
        dedupe_key__contains=duplicate_key,
      ).exclude(campaign=campaign).count()
  context = {
    'campaigns': campaigns,
    'activities': activities,
    'activity_q': activity_q,
    'activity_limit': activity_limit,
    'sent_count': PushDeliveryLog.objects.filter(status='sent').count(),
    'failed_count': PushDeliveryLog.objects.filter(status='failed').count(),
    'pending_count': PushCampaign.objects.filter(status__in=['draft', 'scheduled']).count(),
  }
  return render(request, 'pushManagement.html', context)


def userManagement(request):
  users = (UserProfile.objects
           .prefetch_related('preferred_tags')
           .annotate(
             subscription_count=Count('subscriptions'),
             active_subscription_count=Count('subscriptions', filter=Q(subscriptions__status='active')),
             cancelled_subscription_count=Count('subscriptions', filter=Q(subscriptions__status='cancelled')),
           )
           .order_by('-updated_at')[:200])
  return render(request, 'userManagement.html', {
    'users': users,
    'total_users': UserProfile.objects.count(),
    'push_enabled_users': UserProfile.objects.filter(push_enabled=True).count(),
    'active_users': UserProfile.objects.filter(action_logs__created_at__gte=timezone.now() - timedelta(days=30)).distinct().count(),
  })


def userDetail(request, id):
  user = get_object_or_404(UserProfile.objects.prefetch_related('preferred_tags'), id=id)
  action_logs = (ActionLog.objects
                 .select_related('activity')
                 .filter(user=user)
                 .order_by('-created_at')[:100])
  subscriptions = (Subscription.objects
                   .select_related('activity')
                   .filter(user=user)
                   .order_by('-created_at')[:50])
  push_logs = (PushDeliveryLog.objects
               .select_related('campaign', 'activity')
               .filter(user=user)
               .order_by('-created_at')[:50])
  ai_logs = (AIProcessingLog.objects
             .filter(line_user_id=user.line_user_id)
             .order_by('-created_at')[:50])
  action_counts = (ActionLog.objects
                   .filter(user=user)
                   .values('action_type')
                   .annotate(count=Count('id'))
                   .order_by('-count'))
  for item in action_counts:
    item['label'] = human_action_label(item['action_type'])
  for log in action_logs:
    log.action_label = human_action_label(log.action_type)
    log.business_key = activity_business_key(log.activity) if log.activity else ''
  for subscription in subscriptions:
    subscription.business_key = activity_business_key(subscription.activity) if subscription.activity else ''
  for log in push_logs:
    log.business_key = activity_business_key(log.activity) if log.activity else ''
  recent_ids = list(recent_recommended_activity_ids(user, limit=20))
  recent_recommended = Activity.objects.filter(id__in=recent_ids)
  recent_recommended_by_id = {activity.id: activity for activity in recent_recommended}
  ordered_recent_recommended = [recent_recommended_by_id[item_id] for item_id in recent_ids if item_id in recent_recommended_by_id]
  return render(request, 'userDetail.html', {
    'profile': user,
    'region_preferences': user.preferred_tags.filter(tag_type='region'),
    'non_region_preferences': user.preferred_tags.exclude(tag_type='region'),
    'action_logs': action_logs,
    'subscriptions': subscriptions,
    'push_logs': push_logs,
    'ai_logs': ai_logs,
    'action_counts': action_counts,
    'recent_recommended_activities': ordered_recent_recommended[:10],
  })


def operationJobs(request):
  jobs = OperationJob.objects.all()[:100]
  return render(request, 'operationJobs.html', {
    'jobs': jobs,
    'running_count': OperationJob.objects.filter(status='running').count(),
    'queued_count': OperationJob.objects.filter(status='queued').count(),
    'auto_refresh': OperationJob.objects.filter(status__in={'queued', 'running'}).exists(),
  })


def operationJobDetail(request, id):
  job = get_object_or_404(OperationJob, id=id)
  if request.method == 'POST':
    action = request.POST.get('action')
    if action == 'cancel' and job.status in {'queued', 'running'}:
      job.status = 'cancelled'
      job.progress_message = '管理員已要求取消；若背景程序正在處理單筆資料，會在下一筆前停止。'
      job.finished_at = timezone.now()
      job.save(update_fields=['status', 'progress_message', 'finished_at', 'updated_at'])
      audit(request, 'cancel_operation_job', None, {'job_id': job.id})
      messages.warning(request, f'任務 #{job.id} 已標記取消。')
    else:
      messages.error(request, '這個任務目前不能取消。')
    return redirect('operationJobDetail', id=job.id)
  recent_logs = AIProcessingLog.objects.all()[:20]
  if job.job_type in {'ai_tag', 'ocr', 'summary'}:
    task_type = {'ai_tag': 'tagging', 'ocr': 'ocr', 'summary': 'summary'}[job.job_type]
    recent_logs = AIProcessingLog.objects.filter(task_type=task_type).order_by('-created_at')[:20]
  return render(request, 'operationJobDetail.html', {
    'job': job,
    'recent_logs': recent_logs,
    'auto_refresh': job.status in {'queued', 'running'},
  })


def lineQuerySimulator(request):
  from myapp.line_services import (
    classify_line_intent,
    get_valid_conversation_state,
    handle_line_text_message,
    search_activities_for_line,
  )

  simulator_user, _ = UserProfile.objects.get_or_create(
    line_user_id='codex-admin-query-simulator',
    defaults={
      'display_name': '後台 LINE 查詢模擬器',
      'push_enabled': False,
      'recommend_push_enabled': False,
    },
  )
  result = None
  if request.method == 'POST':
    action = request.POST.get('action') or 'simulate'
    if action == 'reset_context':
      LineConversationState.objects.filter(user=simulator_user).delete()
      messages.info(request, '模擬器上下文已清除。')
      return redirect('lineQuerySimulator')

    query = request.POST.get('query', '').strip()
    if query:
      state_before = get_valid_conversation_state(simulator_user)
      intent = classify_line_intent(simulator_user, query, state=state_before)
      response = handle_line_text_message(simulator_user, query)
      line_messages = response if isinstance(response, list) else [response]
      has_flex = any(item.__class__.__name__ == 'FlexSendMessage' for item in line_messages)
      state_after = get_valid_conversation_state(simulator_user)
      activity_ids = list((state_after.last_activity_ids or []) if has_flex and state_after else [])
      conditions = (state_after.conditions or {}) if has_flex and state_after else {}
      if not activity_ids and intent == 'activity_search':
        activities, conditions = search_activities_for_line(simulator_user, query, limit=5, return_conditions=True)
        activity_ids = [activity.id for activity in activities]
      activities_by_id = {
        activity.id: activity
        for activity in Activity.objects.filter(id__in=activity_ids).select_related('search_profile').prefetch_related('tags')
      }
      ordered_activities = [activities_by_id[item_id] for item_id in activity_ids if item_id in activities_by_id]
      result = {
        'query': query,
        'intent': intent,
        'message_types': [item.__class__.__name__ for item in line_messages],
        'texts': [getattr(item, 'text', '') for item in line_messages if getattr(item, 'text', '')],
        'has_flex': has_flex,
        'conditions_json': json.dumps(conditions or {}, ensure_ascii=False, indent=2, default=str),
        'activities': ordered_activities,
      }

  return render(request, 'lineQuerySimulator.html', {
    'result': result,
    'simulator_user': simulator_user,
  })


def crawlJobs(request):
  if request.method == 'POST':
    action = request.POST.get('action') or 'create_job'
    if action == 'run_next':
      job = CrawlJob.objects.filter(status='queued').order_by('created_at').first()
      if not job:
        messages.info(request, '目前沒有等待中的爬蟲任務。')
        return redirect('crawlJobs')
      start_crawl_job_process(job)
      audit(request, 'run_next_crawl_job', None, {'job_id': job.id})
      messages.success(request, f'已啟動爬蟲任務 #{job.id}。')
      return redirect('crawlJobs')

    if action == 'clear_queued_jobs':
      now = timezone.now()
      queued_ids = list(CrawlJob.objects.filter(status='queued').values_list('id', flat=True))
      updated = CrawlJob.objects.filter(id__in=queued_ids).update(
        status='cancelled',
        finished_at=now,
        error_summary='管理員清除 queued 任務。',
        updated_at=now,
      )
      CrawlTask.objects.filter(job_id__in=queued_ids, status='queued').update(
        status='cancelled',
        finished_at=now,
        error_summary='父層 queued 任務被管理員清除。',
        updated_at=now,
      )
      audit(request, 'clear_queued_crawl_jobs', None, {'count': updated})
      messages.warning(request, f'已清除 {updated} 筆 queued 爬蟲任務。')
      return redirect('crawlJobs')

    if action == 'mark_stale_running_failed':
      now = timezone.now()
      stale_jobs = []
      for job in CrawlJob.objects.filter(status='running'):
        attach_crawl_progress(job)
        if job.maybe_stale:
          stale_jobs.append(job)
      for job in stale_jobs:
        job.status = 'failed'
        job.finished_at = now
        job.error_summary = '管理員標記：此 running 任務已超過預估時間，視為中斷。'
        job.save(update_fields=['status', 'finished_at', 'error_summary', 'updated_at'])
        job.tasks.filter(status='running').update(
          status='failed',
          finished_at=now,
          error_summary='父層爬蟲任務被管理員標記可能中斷。',
          updated_at=now,
        )
      audit(request, 'mark_stale_crawl_jobs_failed', None, {'count': len(stale_jobs)})
      messages.warning(request, f'已標記 {len(stale_jobs)} 筆可能中斷的爬蟲任務為失敗。')
      return redirect('crawlJobs')

    if action == 'mark_interrupted':
      job = get_object_or_404(CrawlJob, id=request.POST.get('job_id'), status='running')
      now = timezone.now()
      job.status = 'failed'
      job.finished_at = now
      job.error_summary = '管理員標記：爬蟲程序已中斷。若電腦關機或 Django 被停止，任務不會自動續跑。'
      job.save(update_fields=['status', 'finished_at', 'error_summary', 'updated_at'])
      job.tasks.filter(status='running').update(
        status='failed',
        finished_at=now,
        error_summary='父層爬蟲任務被管理員標記中斷。',
        updated_at=now,
      )
      audit(request, 'mark_crawl_interrupted', None, {'job_id': job.id})
      messages.warning(request, f'爬蟲任務 #{job.id} 已標記為中斷/失敗，可重新建立任務。')
      return redirect('crawlJobs')

    preset = request.POST.get('preset') or 'custom'
    primary_limit = positive_int(request.POST.get('primary_limit'), default=1)
    secondary_limit = positive_int(request.POST.get('secondary_limit'), default=primary_limit)
    options = {
      'source': request.POST.get('source', '').strip(),
      'primary_limit': primary_limit,
      'secondary_limit': secondary_limit,
      'max_runtime': int(request.POST.get('max_runtime') or 30),
      'skip_dynamic': request.POST.get('skip_dynamic') == 'on',
      'no_assets': request.POST.get('no_assets') == 'on',
      'activate': request.POST.get('activate') == 'on',
      'no_import': request.POST.get('no_import') == 'on',
      'ocr': request.POST.get('ocr') == 'on',
      'ocr_limit': int(request.POST.get('ocr_limit') or 0),
    }
    options.update(crawl_preset_options(preset, options))
    job = CrawlJob.objects.create(
      title=request.POST.get('title', '').strip() or ('一鍵完整更新' if options.get('full_pipeline') else '後台排程爬蟲'),
      source=options['source'],
      options=options,
      created_by=audit_actor(request),
    )
    audit(request, 'queue_crawl_job', None, {'job_id': job.id, 'options': options})
    if options.get('full_pipeline'):
      try:
        start_crawl_job_process(job)
        messages.success(request, f'完整更新任務 #{job.id} 已建立並開始執行。')
      except Exception as exc:
        job.status = 'failed'
        job.error_summary = f'背景程序啟動失敗：{str(exc)[:900]}'
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_summary', 'finished_at', 'updated_at'])
        messages.error(request, f'任務 #{job.id} 建立成功，但背景程序啟動失敗：{str(exc)[:300]}')
    else:
      messages.success(request, '爬蟲任務已建立，可在維護工具啟動等待中的任務。')
    return redirect('crawlJobs')
  jobs = list(CrawlJob.objects.select_related('import_run').all()[:100])
  for job in jobs:
    attach_crawl_progress(job)
  return render(request, 'crawlJobs.html', {
    'jobs': jobs,
    'queued_count': CrawlJob.objects.filter(status='queued').count(),
    'running_count': CrawlJob.objects.filter(status='running').count(),
    'source_options': crawler_source_options(),
    'auto_refresh': any(job.status in {'queued', 'running'} for job in jobs),
  })


def crawlJobDetail(request, id):
  job = get_object_or_404(CrawlJob.objects.select_related('import_run'), id=id)
  attach_crawl_progress(job)
  tasks = list(job.tasks.order_by('id'))
  for task in tasks:
    task.progress_percent = crawl_task_progress_percent(task)
    task.progress_class = crawl_progress_class(task.status)
    task.progress_note = crawl_task_progress_note(task)
  ocr_status_counts = (Activity.objects
                       .values('ocr_status')
                       .annotate(count=Count('id'))
                       .order_by('-count'))
  return render(request, 'crawlJobDetail.html', {
    'job': job,
    'tasks': tasks,
    'ocr_status_counts': ocr_status_counts,
    'auto_refresh': job.status in {'queued', 'running'},
  })


def activityChanges(request):
  changes = ActivityChangeLog.objects.select_related('activity').all()[:200]
  return render(request, 'activityChanges.html', {
    'changes': changes,
    'pending_count': ActivityChangeLog.objects.filter(notify_required=True, notified_at__isnull=True).count(),
  })


def activity_form_values(data, activity=None):
  return {
    'title': data.get('title', '').strip() or '未命名活動',
    'description': data.get('description', '').strip(),
    'location': data.get('location', '').strip(),
    'district': data.get('district', '').strip(),
    'start_date': parse_datetime_field(data.get('start_date')),
    'end_date': parse_datetime_field(data.get('end_date')),
    'status': data.get('status') if data.get('status') in {'active', 'inactive', 'draft'} else 'draft',
    'source_agency': data.get('source_agency', '').strip(),
    'source_url': data.get('source_url', '').strip(),
    'official_detail_url': data.get('official_detail_url', '').strip(),
    'image_url': data.get('image_url', '').strip(),
    'is_free': data.get('is_free') == 'on',
    'requires_registration': data.get('requires_registration') == 'on',
    'line_ready': activity.line_ready if activity else False,
    'ai_ready': activity.ai_ready if activity else False,
    'recommendation_ready': activity.recommendation_ready if activity else False,
    'is_activity': True,
    'is_public_item': True,
    'fee_type': data.get('fee_type') or 'unknown',
    'manual_verified': data.get('manual_verified') == 'on',
    'manual_overrides': parse_manual_overrides(data.get('manual_overrides', '')),
    'manual_note': data.get('manual_note', '').strip(),
    'organizer': data.get('organizer', '').strip(),
    'registration_url': data.get('registration_url', '').strip(),
  }


def activity_form_context(activity=None):
  selected_tag_ids = set(activity.tags.values_list('id', flat=True)) if activity else set()
  return {
    'activity': activity,
    'districts': DISTRICTS,
    'tags': Tag.objects.filter(is_active=True).order_by('tag_type', 'name'),
    'selected_tag_ids': selected_tag_ids,
    'status_choices': Activity.STATUS_CHOICES,
    'fee_choices': Activity.FEE_TYPE_CHOICES,
  }


def apply_activity_tags(activity, tag_ids):
  tags = Tag.objects.filter(id__in=tag_ids, is_active=True)
  activity.tags.set(tags)


def parse_datetime_field(value):
  if not value:
    return None
  parsed = parse_datetime(value)
  if parsed and timezone.is_naive(parsed):
    return timezone.make_aware(parsed, timezone.get_current_timezone())
  return parsed


def parse_manual_overrides(value):
  fields = [field.strip() for field in (value or '').split(',') if field.strip()]
  return fields or None


def positive_int(value, default=1):
  try:
    parsed = int(value)
  except (TypeError, ValueError):
    return default
  return parsed if parsed > 0 else default


def audit_actor(request):
  user = getattr(request, 'user', None)
  if user and getattr(user, 'is_authenticated', False):
    return str(user)
  return 'local_admin'


def audit(request, action, activity=None, metadata=None):
  AdminAuditLog.objects.create(
    actor=audit_actor(request),
    action=action,
    activity=activity,
    metadata=metadata or {},
  )


def crawler_source_options():
  config_path = Path(settings.BASE_DIR) / 'config' / 'sources.yaml'
  if not config_path.exists():
    return []
  data = yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}
  return data.get('sources') or []


def crawl_preset_options(preset, current_options):
  if preset == 'one_click_update':
    limit = current_options.get('primary_limit') or 1
    return {
      'primary_limit': limit,
      'secondary_limit': limit,
      'max_runtime': current_options.get('max_runtime') or 30,
      'skip_dynamic': True,
      'no_assets': False,
      'activate': True,
      'no_import': False,
      'ocr': False,
      'ocr_limit': 0,
      'full_pipeline': True,
      'post_process_limit': limit,
      'failure_cooldown_hours': 24,
      'preset': preset,
    }
  if preset == 'small_test':
    return {
      'source': current_options.get('source') or 'travel_openapi',
      'primary_limit': 1,
      'secondary_limit': 1,
      'max_runtime': 1,
      'skip_dynamic': True,
      'no_assets': True,
      'activate': False,
      'no_import': True,
      'preset': preset,
    }
  if preset == 'formal_import':
    return {
      'primary_limit': current_options.get('primary_limit') or 1,
      'secondary_limit': current_options.get('secondary_limit') or 1,
      'max_runtime': current_options.get('max_runtime') or 10,
      'skip_dynamic': True,
      'activate': True,
      'no_import': False,
      'ocr': current_options.get('ocr', False),
      'ocr_limit': current_options.get('ocr_limit', 0),
      'preset': preset,
    }
  if preset == 'formal_import_ocr':
    return {
      'primary_limit': current_options.get('primary_limit') or 1,
      'secondary_limit': current_options.get('secondary_limit') or 1,
      'max_runtime': current_options.get('max_runtime') or 10,
      'skip_dynamic': True,
      'no_assets': False,
      'activate': True,
      'no_import': False,
      'ocr': True,
      'ocr_limit': current_options.get('ocr_limit') or 20,
      'preset': preset,
    }
  if preset == 'output_only':
    return {
      'skip_dynamic': True,
      'no_assets': True,
      'activate': False,
      'no_import': True,
      'preset': preset,
    }
  current_options['preset'] = preset
  return current_options


def crawl_status_percent(status):
  return {
    'queued': 5,
    'running': 55,
    'success': 100,
    'partial': 85,
    'failed': 100,
    'cancelled': 100,
  }.get(status, 0)


def crawl_progress_class(status):
  if status == 'success':
    return 'bg-success'
  if status in {'failed', 'cancelled'}:
    return 'bg-danger'
  if status == 'partial':
    return 'bg-warning'
  if status == 'running':
    return 'progress-bar-striped progress-bar-animated bg-primary'
  return 'bg-secondary'


def crawl_status_label(status):
  return {
    'queued': '等待執行',
    'running': '執行中',
    'success': '完成',
    'partial': '部分完成',
    'failed': '失敗',
    'cancelled': '已取消',
  }.get(status, status)


def attach_crawl_progress(job):
  job.progress_percent = crawl_status_percent(job.status)
  job.progress_class = crawl_progress_class(job.status)
  job.progress_label = crawl_status_label(job.status)
  job.maybe_stale = False
  running_task = job.tasks.filter(status='running').order_by('-updated_at').first()
  if running_task:
    job.progress_percent = crawl_task_progress_percent(running_task)
    job.progress_label = f'{running_task.source_key}執行中'
    job.progress_note = crawl_task_progress_note(running_task)
  if job.status == 'running' and job.started_at:
    max_runtime = int((job.options or {}).get('max_runtime') or 10)
    stale_after = job.started_at + timedelta(minutes=max_runtime + 10)
    if timezone.now() > stale_after:
      job.maybe_stale = True
      job.progress_label = '可能中斷'
      job.progress_class = 'bg-warning progress-bar-striped'
  if job.status == 'running' and not running_task:
    job.progress_note = '已超過預估時間，若電腦曾關機或 Django 停止，請標記中斷後重跑。' if job.maybe_stale else '爬蟲正在執行，頁面會自動刷新。'
  elif job.status == 'queued':
    job.progress_note = '任務已排隊，可在維護工具啟動等待中的任務。'
  elif job.status == 'success':
    if job.import_run_id:
      job.progress_note = f'完成：新增 {job.import_run.created_count}、更新 {job.import_run.updated_count}、略過 {job.import_run.skipped_count}。'
    else:
      job.progress_note = '任務已完成，請查看輸出與匯入紀錄。'
  elif job.status == 'failed':
    job.progress_note = job.error_summary or '任務失敗，請查看錯誤。'
  else:
    job.progress_note = job.get_status_display() if hasattr(job, 'get_status_display') else job.status
  return job


def crawl_task_progress_percent(task):
  metadata = task.metadata or {}
  total = int(metadata.get('total') or 0)
  processed = int(metadata.get('processed') or 0)
  if task.status in {'success', 'failed', 'cancelled'}:
    return 100
  if total:
    return min(99, max(5, int((processed / total) * 100)))
  return crawl_status_percent(task.status)


def crawl_task_progress_note(task):
  metadata = task.metadata or {}
  message = metadata.get('message') or ''
  current = metadata.get('current_title') or ''
  if current and message:
    return f'{message}｜{current}'
  return message or task.error_summary or task.status
