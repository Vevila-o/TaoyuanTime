from datetime import timedelta

from django.db import models
from django.utils import timezone


class SourceWebsite(models.Model):
    SOURCE_TYPE_CHOICES = [
        ('central', '一級機關'),
        ('department', '二級機關'),
        ('district', '區公所'),
        ('other', '其他'),
    ]
    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=32, choices=SOURCE_TYPE_CHOICES, default='other')
    url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Tag(models.Model):
    TAG_TYPE_CHOICES = [
        ('region', 'region'),
        ('activity_type', 'activity_type'),
        ('audience', 'audience'),
        ('cost', 'cost'),
        ('discount', 'discount'),
        ('time', 'time'),
    ]
    name = models.CharField(max_length=100)
    tag_type = models.CharField(max_length=32, choices=TAG_TYPE_CHOICES)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['tag_type', 'name']
        constraints = [
            models.UniqueConstraint(fields=['name', 'tag_type'], name='unique_tag_name_type')
        ]

    def __str__(self):
        return f"{self.name} ({self.tag_type})"


class Activity(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)

    STATUS_CHOICES = [
        ('active', '上架中'),
        ('inactive', '已下架'),
        ('draft', '草稿'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')

    # extended fields
    source_agency = models.CharField(max_length=200, blank=True)
    source_website = models.ForeignKey(SourceWebsite, null=True, blank=True, on_delete=models.SET_NULL, related_name='activities')
    source_url = models.URLField(max_length=1000, blank=True)
    raw_content = models.TextField(blank=True)
    district = models.CharField(max_length=100, blank=True)
    image_url = models.URLField(blank=True)
    is_free = models.BooleanField(default=False)
    requires_registration = models.BooleanField(default=False)
    fee_description = models.CharField(max_length=300, blank=True)
    registration_info = models.TextField(blank=True)
    has_citizen_card_discount = models.BooleanField(default=False)
    citizen_card_note = models.CharField(max_length=300, blank=True)
    ai_summary = models.TextField(blank=True)
    ai_confidence = models.FloatField(null=True, blank=True)
    ocr_ready = models.BooleanField(default=False)
    ocr_image_url = models.URLField(max_length=1000, blank=True)
    ocr_image_path = models.CharField(max_length=1000, blank=True)
    ocr_text = models.TextField(blank=True)
    ocr_summary = models.TextField(blank=True)
    ocr_confidence = models.FloatField(null=True, blank=True)
    ocr_status = models.CharField(max_length=32, blank=True)
    ocr_warnings = models.TextField(blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='activities')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Data quality / classification fields (新增欄位)
    ITEM_TYPE_CHOICES = [
        ('activity', 'activity'),
        ('news', 'news'),
        ('announcement', 'announcement'),
        ('admin_notice', 'admin_notice'),
        ('penalty_list', 'penalty_list'),
        ('venue_notice', 'venue_notice'),
        ('policy', 'policy'),
        ('procurement', 'procurement'),
        ('recruitment', 'recruitment'),
        ('recap', 'recap'),
        ('place_or_resource', 'place_or_resource'),
        ('unknown', 'unknown'),
    ]
    item_type = models.CharField(max_length=32, choices=ITEM_TYPE_CHOICES, default='activity')

    is_activity = models.BooleanField(default=True)
    is_public_item = models.BooleanField(default=True)
    line_ready = models.BooleanField(default=True)
    ai_ready = models.BooleanField(default=True)
    recommendation_ready = models.BooleanField(default=True)
    excluded_from_public = models.BooleanField(default=False)
    exclude_reason = models.CharField(max_length=100, blank=True)

    FINAL_STATE_CHOICES = [
        ('published', '可上架'),
        ('needs_data', '待補資料'),
        ('needs_review', '待審核'),
        ('inactive', '已下架'),
        ('non_activity', '非活動'),
        ('system_excluded', '系統排除'),
        ('expired', '過期'),
    ]
    final_state = models.CharField(max_length=32, choices=FINAL_STATE_CHOICES, default='needs_review')

    official_detail_url = models.URLField(max_length=1000, blank=True)
    source_key = models.CharField(max_length=100, blank=True)
    source_item_id = models.CharField(max_length=200, blank=True)

    FEE_TYPE_CHOICES = [
        ('free', 'free'),
        ('ticket_free', 'ticket_free'),
        ('paid', 'paid'),
        ('mixed', 'mixed'),
        ('unknown', 'unknown'),
    ]
    fee_type = models.CharField(max_length=16, choices=FEE_TYPE_CHOICES, default='unknown')

    quality_score = models.FloatField(null=True, blank=True)
    QUALITY_LEVEL_CHOICES = [
        ('high', 'high'),
        ('medium', 'medium'),
        ('low', 'low'),
        ('rejected', 'rejected'),
    ]
    quality_level = models.CharField(max_length=16, choices=QUALITY_LEVEL_CHOICES, default='medium')
    quality_warnings = models.TextField(blank=True)
    exclude_from_recommendation_reason = models.TextField(blank=True)
    manual_verified = models.BooleanField(default=False)
    manual_overrides = models.JSONField(blank=True, null=True)
    manual_note = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    raw_html_path = models.CharField(max_length=1000, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    organizer = models.CharField(max_length=200, blank=True)
    registration_url = models.URLField(max_length=1000, blank=True)
    official_link_status = models.CharField(max_length=32, default='unknown', blank=True)
    official_link_checked_at = models.DateTimeField(null=True, blank=True)
    official_link_error = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date', '-created_at']
        indexes = [
            models.Index(fields=['start_date']),
            models.Index(fields=['district']),
            models.Index(fields=['status']),
            models.Index(fields=['source_website']),
            models.Index(fields=['source_key', 'source_item_id']),
        ]

    def __str__(self):
        return self.title


class UserProfile(models.Model):
    line_user_id = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=200, blank=True)
    preferred_tags = models.ManyToManyField(Tag, blank=True, related_name='preferred_by')
    push_enabled = models.BooleanField(default=True)
    recommend_push_enabled = models.BooleanField(default=True)
    recommend_push_interval_days = models.PositiveIntegerField(default=3)
    last_recommend_pushed_at = models.DateTimeField(null=True, blank=True)
    default_remind_before_days = models.PositiveIntegerField(default=1)
    has_citizen_card = models.BooleanField(default=False)
    citizen_card_number = models.CharField(max_length=50, blank=True, null=True)
    citizen_name = models.CharField(max_length=100, blank=True, null=True)
    citizen_phone = models.CharField(max_length=20, blank=True, null=True)
    citizen_birthdate = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.display_name or self.line_user_id


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'active'),
        ('cancelled', 'cancelled'),
    ]
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='subscriptions')
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='subscriptions')
    remind_before_days = models.PositiveIntegerField(default=1)
    is_notified = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='active')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'activity')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} -> {self.activity}"


class ActionLog(models.Model):
    ACTION_CHOICES = [
        ('view_card','view_card'),
        ('view_detail','view_detail'),
        ('interested','interested'),
        ('not_interested','not_interested'),
        ('subscribe','subscribe'),
        ('unsubscribe','unsubscribe'),
        ('how_to_go','how_to_go'),
        ('add_calendar','add_calendar'),
        ('view_more','view_more'),
        ('citizen_card_click','citizen_card_click'),
        ('citizen_card_bind','citizen_card_bind'),
    ]
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='action_logs')
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL, related_name='action_logs')
    action_type = models.CharField(max_length=64, choices=ACTION_CHOICES)
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} {self.action_type} {self.activity or ''}"


class LineConversationState(models.Model):
    user = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='conversation_state')
    intent = models.CharField(max_length=32, blank=True)
    last_query = models.CharField(max_length=300, blank=True)
    conditions = models.JSONField(blank=True, null=True)
    last_activity_ids = models.JSONField(blank=True, null=True)
    offset = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user_id} {self.intent or '-'}"

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())


class ImportRun(models.Model):
    RUN_TYPE_CHOICES = [
        ('crawler', 'crawler'),
        ('json_import', 'json_import'),
        ('ai_tag_audit', 'ai_tag_audit'),
        ('crawler_queue', 'crawler_queue'),
    ]
    STATUS_CHOICES = [
        ('running', 'running'),
        ('success', 'success'),
        ('partial', 'partial'),
        ('failed', 'failed'),
    ]

    run_type = models.CharField(max_length=32, choices=RUN_TYPE_CHOICES, default='crawler')
    source = models.CharField(max_length=100, blank=True)
    input_path = models.CharField(max_length=1000, blank=True)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='running')
    error_summary = models.TextField(blank=True)
    metadata = models.JSONField(blank=True, null=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.run_type} {self.status} {self.started_at:%Y-%m-%d %H:%M}"


class ActivityAsset(models.Model):
    ASSET_TYPE_CHOICES = [
        ('poster', 'poster'),
        ('main_visual', 'main_visual'),
        ('activity_photo', 'activity_photo'),
        ('other', 'other'),
    ]

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='assets')
    url = models.URLField(max_length=1000)
    asset_type = models.CharField(max_length=32, choices=ASSET_TYPE_CHOICES, default='other')
    is_primary = models.BooleanField(default=False)
    ocr_eligible = models.BooleanField(default=False)
    quality_warning = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['activity', 'url'], name='unique_activity_asset_url')
        ]

    def __str__(self):
        return f"{self.activity_id} {self.asset_type}"


class ActivityTagSuggestion(models.Model):
    STATUS_CHOICES = [
        ('pending', 'pending'),
        ('approved', 'approved'),
        ('rejected', 'rejected'),
    ]

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='tag_suggestions')
    tag = models.ForeignKey(Tag, null=True, blank=True, on_delete=models.SET_NULL, related_name='activity_suggestions')
    tag_name = models.CharField(max_length=100)
    tag_type = models.CharField(max_length=32, choices=Tag.TAG_TYPE_CHOICES)
    confidence = models.FloatField(null=True, blank=True)
    reason = models.TextField(blank=True)
    source = models.CharField(max_length=32, default='ai')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', '-confidence', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['activity', 'tag_name', 'tag_type', 'source'],
                name='unique_activity_tag_suggestion',
            )
        ]

    def __str__(self):
        return f"{self.activity_id} {self.tag_name} {self.status}"


class ActivitySearchProfile(models.Model):
    STATUS_CHOICES = [
        ('pending', 'pending'),
        ('success', 'success'),
        ('failed', 'failed'),
        ('stale', 'stale'),
    ]

    activity = models.OneToOneField(Activity, on_delete=models.CASCADE, related_name='search_profile')
    search_text = models.TextField(blank=True)
    keywords = models.JSONField(blank=True, null=True)
    topics = models.JSONField(blank=True, null=True)
    synonyms = models.JSONField(blank=True, null=True)
    source_hash = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    error = models.TextField(blank=True)
    provider_model = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['activity_id']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['source_hash']),
        ]

    def __str__(self):
        return f"{self.activity_id} {self.status}"


class AIProcessingLog(models.Model):
    TASK_TYPE_CHOICES = [
        ('condition_extract', 'condition_extract'),
        ('rerank', 'rerank'),
        ('summary', 'summary'),
        ('tagging', 'tagging'),
        ('search_profile', 'search_profile'),
        ('link_check', 'link_check'),
        ('ocr', 'ocr'),
    ]
    STATUS_CHOICES = [
        ('success', 'success'),
        ('failed', 'failed'),
    ]

    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL, related_name='ai_logs')
    line_user_id = models.CharField(max_length=64, blank=True)
    task_type = models.CharField(max_length=32, choices=TASK_TYPE_CHOICES)
    model = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=32, blank=True)
    input_summary = models.TextField(blank=True)
    output_json = models.JSONField(blank=True, null=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.task_type} {self.status} {self.created_at:%Y-%m-%d %H:%M}"


class PushCampaign(models.Model):
    STATUS_CHOICES = [
        ('draft', 'draft'),
        ('scheduled', 'scheduled'),
        ('sending', 'sending'),
        ('sent', 'sent'),
        ('failed', 'failed'),
        ('cancelled', 'cancelled'),
    ]

    title = models.CharField(max_length=200)
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL, related_name='push_campaigns')
    message = models.TextField(blank=True)
    audience_rule = models.JSONField(blank=True, null=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class PushDeliveryLog(models.Model):
    STATUS_CHOICES = [
        ('pending', 'pending'),
        ('sent', 'sent'),
        ('failed', 'failed'),
    ]
    NOTIFICATION_TYPE_CHOICES = [
        ('campaign', 'campaign'),
        ('recommendation', 'recommendation'),
        ('subscription_reminder', 'subscription_reminder'),
        ('activity_change', 'activity_change'),
    ]

    campaign = models.ForeignKey(PushCampaign, null=True, blank=True, on_delete=models.CASCADE, related_name='delivery_logs')
    user = models.ForeignKey(UserProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name='push_delivery_logs')
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL, related_name='push_delivery_logs')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    notification_type = models.CharField(max_length=32, choices=NOTIFICATION_TYPE_CHOICES, default='campaign')
    dedupe_key = models.CharField(max_length=200, blank=True)
    line_response = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['notification_type', 'dedupe_key']),
        ]

    def __str__(self):
        return f"{self.user_id or '-'} {self.status}"


class OperationJob(models.Model):
    JOB_TYPE_CHOICES = [
        ('ai_tag', 'ai_tag'),
        ('ocr', 'ocr'),
        ('summary', 'summary'),
        ('push', 'push'),
        ('crawler', 'crawler'),
        ('link_check', 'link_check'),
    ]
    STATUS_CHOICES = [
        ('queued', 'queued'),
        ('running', 'running'),
        ('success', 'success'),
        ('partial', 'partial'),
        ('failed', 'failed'),
        ('cancelled', 'cancelled'),
    ]

    job_type = models.CharField(max_length=32, choices=JOB_TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued')
    title = models.CharField(max_length=200, blank=True)
    total_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    current_label = models.CharField(max_length=300, blank=True)
    progress_message = models.TextField(blank=True)
    error_summary = models.TextField(blank=True)
    options = models.JSONField(blank=True, null=True)
    result_summary = models.JSONField(blank=True, null=True)
    created_by = models.CharField(max_length=200, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['job_type', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.title or f"{self.job_type} #{self.id}"

    @property
    def progress_percent(self):
        if self.status == 'success' and self.total_count == 0:
            return 0
        if self.status in {'success', 'failed', 'cancelled'}:
            return 100
        if self.total_count:
            return min(99, int((self.processed_count / self.total_count) * 100))
        return {'queued': 5, 'running': 15, 'partial': 85}.get(self.status, 0)

    @property
    def progress_label(self):
        if self.status == 'success' and self.total_count == 0:
            return '無待處理資料'
        return {
            'queued': '等待執行',
            'running': '執行中',
            'success': '完成',
            'partial': '部分完成',
            'failed': '失敗',
            'cancelled': '已取消',
        }.get(self.status, self.status)

    @property
    def progress_class(self):
        if self.status == 'success':
            return 'bg-success'
        if self.status in {'failed', 'cancelled'}:
            return 'bg-danger'
        if self.status == 'partial':
            return 'bg-warning'
        if self.status == 'running':
            return 'progress-bar-striped progress-bar-animated bg-primary'
        return 'bg-secondary'

    @property
    def maybe_stale(self):
        if self.status != 'running' or not self.updated_at:
            return False
        return self.updated_at <= timezone.now() - timedelta(minutes=10)

    @property
    def empty_result_message(self):
        if not (self.status == 'success' and self.total_count == 0):
            return ''
        return {
            'ocr': '目前沒有符合條件的 OCR 活動。',
            'summary': '目前沒有待產生摘要的活動。',
            'ai_tag': '目前沒有待處理的 AI Tag 或搜尋語意活動。',
            'link_check': '目前沒有待檢查的官方連結。',
            'push': '目前沒有符合條件的推播受眾。',
        }.get(self.job_type, '目前沒有待處理資料。')


class CrawlJob(models.Model):
    STATUS_CHOICES = [
        ('queued', 'queued'),
        ('running', 'running'),
        ('success', 'success'),
        ('partial', 'partial'),
        ('failed', 'failed'),
        ('cancelled', 'cancelled'),
    ]

    title = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued')
    source = models.CharField(max_length=100, blank=True)
    options = models.JSONField(blank=True, null=True)
    output_path = models.CharField(max_length=1000, blank=True)
    import_run = models.ForeignKey(ImportRun, null=True, blank=True, on_delete=models.SET_NULL, related_name='crawl_jobs')
    created_by = models.CharField(max_length=200, blank=True)
    error_summary = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title or f'CrawlJob #{self.id}'


class CrawlTask(models.Model):
    STATUS_CHOICES = CrawlJob.STATUS_CHOICES

    job = models.ForeignKey(CrawlJob, on_delete=models.CASCADE, related_name='tasks')
    source_key = models.CharField(max_length=100)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued')
    attempted_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True)
    metadata = models.JSONField(blank=True, null=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source_key']

    def __str__(self):
        return f'{self.job_id} {self.source_key} {self.status}'


class ActivityChangeLog(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='change_logs')
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    source = models.CharField(max_length=100, blank=True)
    notify_required = models.BooleanField(default=False)
    notified_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['notify_required', 'notified_at']),
        ]

    def __str__(self):
        return f'{self.activity_id} {self.field_name}'


class AdminAuditLog(models.Model):
    ACTION_CHOICES = [
        ('create_activity', 'create_activity'),
        ('update_activity', 'update_activity'),
        ('set_status', 'set_status'),
        ('tag_approve', 'tag_approve'),
        ('tag_reject', 'tag_reject'),
        ('queue_crawl_job', 'queue_crawl_job'),
    ]

    actor = models.CharField(max_length=200, default='local_admin')
    action = models.CharField(max_length=64, choices=ACTION_CHOICES)
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL, related_name='admin_audit_logs')
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.actor} {self.action}'

# 市民卡
class CitizenCardData(models.Model):
    card_number = models.CharField(max_length=14, unique=True)
    name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    birthdate = models.DateField()

    def __str__(self):
        return f"{self.name} ({self.card_number})"

# 商店
class Store(models.Model):
    name = models.CharField(max_length=100)
    district = models.CharField(max_length=20)
    address = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()
    discount_info = models.TextField()
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
