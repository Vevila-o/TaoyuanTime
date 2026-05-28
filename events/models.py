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
    tags = models.ManyToManyField(Tag, blank=True, related_name='activities')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Data quality / classification fields (新增欄位)
    ITEM_TYPE_CHOICES = [
        ('activity', 'activity'),
        ('announcement', 'announcement'),
        ('recap', 'recap'),
        ('place_or_resource', 'place_or_resource'),
    ]
    item_type = models.CharField(max_length=32, choices=ITEM_TYPE_CHOICES, default='activity')

    is_activity = models.BooleanField(default=True)
    is_public_item = models.BooleanField(default=True)
    line_ready = models.BooleanField(default=True)
    ai_ready = models.BooleanField(default=True)
    recommendation_ready = models.BooleanField(default=True)

    official_detail_url = models.URLField(max_length=1000, blank=True)
    source_key = models.CharField(max_length=100, blank=True)

    FEE_TYPE_CHOICES = [
        ('free', 'free'),
        ('paid', 'paid'),
        ('unknown', 'unknown'),
    ]
    fee_type = models.CharField(max_length=10, choices=FEE_TYPE_CHOICES, default='unknown')

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

    class Meta:
        ordering = ['-start_date', '-created_at']
        indexes = [
            models.Index(fields=['start_date']),
            models.Index(fields=['district']),
            models.Index(fields=['status']),
            models.Index(fields=['source_website']),
        ]

    def __str__(self):
        return self.title


class UserProfile(models.Model):
    line_user_id = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=200, blank=True)
    preferred_tags = models.ManyToManyField(Tag, blank=True, related_name='preferred_by')
    push_enabled = models.BooleanField(default=True)
    default_remind_before_days = models.PositiveIntegerField(default=1)
    has_citizen_card = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.display_name or self.line_user_id


class Subscription(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='subscriptions')
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='subscriptions')
    remind_before_days = models.PositiveIntegerField(default=1)
    is_notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'activity')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} -> {self.activity}"


class ActionLog(models.Model):
    ACTION_CHOICES = [
        ('view_card','view_card'),
        ('interested','interested'),
        ('not_interested','not_interested'),
        ('subscribe','subscribe'),
        ('unsubscribe','unsubscribe'),
        ('how_to_go','how_to_go'),
        ('add_calendar','add_calendar'),
        ('view_more','view_more'),
        ('citizen_card_click','citizen_card_click'),
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
