from django.contrib import admin
from .models import (
    AIProcessingLog,
    ActionLog,
    Activity,
    ActivityAsset,
    ActivityChangeLog,
    ActivityTagSuggestion,
    AdminAuditLog,
    CrawlJob,
    CrawlTask,
    ImportRun,
    LineConversationState,
    OperationJob,
    PushCampaign,
    PushDeliveryLog,
    SourceWebsite,
    Subscription,
    Tag,
    UserProfile,
)


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('title','source_agency','district','start_date','end_date','status','is_free', 'item_type', 'quality_level', 'line_ready', 'ai_ready', 'recommendation_ready')
    search_fields = ('title','source_agency','district','description','raw_content')
    list_filter = ('status','district','source_website','tags','is_free','requires_registration', 'item_type', 'is_activity', 'is_public_item', 'line_ready', 'ai_ready', 'recommendation_ready', 'quality_level', 'fee_type', 'source_key')
    filter_horizontal = ('tags',)
    date_hierarchy = 'start_date'
    readonly_fields = ('created_at','updated_at')


@admin.register(SourceWebsite)
class SourceWebsiteAdmin(admin.ModelAdmin):
    list_display = ('name','source_type','url','is_active')
    search_fields = ('name','url')
    list_filter = ('source_type','is_active')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name','tag_type','is_active')
    search_fields = ('name',)
    list_filter = ('tag_type','is_active')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name','line_user_id','push_enabled','has_citizen_card','default_remind_before_days')
    search_fields = ('display_name','line_user_id')
    filter_horizontal = ('preferred_tags',)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user','activity','status','remind_before_days','is_notified','last_notified_at','created_at')
    search_fields = ('user__display_name','user__line_user_id','activity__title')
    list_filter = ('status','is_notified',)


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ('user','action_type','activity','created_at')
    search_fields = ('user__display_name','user__line_user_id','activity__title')
    list_filter = ('action_type',)
    readonly_fields = ('metadata','created_at')


@admin.register(LineConversationState)
class LineConversationStateAdmin(admin.ModelAdmin):
    list_display = ('user','intent','last_query','offset','expires_at','updated_at')
    search_fields = ('user__display_name','user__line_user_id','last_query')
    list_filter = ('intent',)
    readonly_fields = ('conditions','last_activity_ids','created_at','updated_at')


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = ('run_type','source','status','created_count','updated_count','skipped_count','failed_count','started_at','finished_at')
    search_fields = ('source','input_path','error_summary')
    list_filter = ('run_type','status','source')
    readonly_fields = ('metadata','started_at','finished_at')


@admin.register(ActivityAsset)
class ActivityAssetAdmin(admin.ModelAdmin):
    list_display = ('activity','asset_type','is_primary','ocr_eligible','created_at')
    search_fields = ('activity__title','url')
    list_filter = ('asset_type','is_primary','ocr_eligible')


@admin.register(ActivityTagSuggestion)
class ActivityTagSuggestionAdmin(admin.ModelAdmin):
    list_display = ('activity','tag_name','tag_type','confidence','source','status','created_at')
    search_fields = ('activity__title','tag_name','reason')
    list_filter = ('status','tag_type','source')
    readonly_fields = ('created_at','updated_at')


@admin.register(AIProcessingLog)
class AIProcessingLogAdmin(admin.ModelAdmin):
    list_display = ('task_type','status','model','line_user_id','activity','latency_ms','created_at')
    search_fields = ('line_user_id','activity__title','input_summary','error')
    list_filter = ('task_type','status','model')
    readonly_fields = ('output_json','created_at')


@admin.register(PushCampaign)
class PushCampaignAdmin(admin.ModelAdmin):
    list_display = ('title','activity','status','scheduled_at','created_at')
    search_fields = ('title','message','activity__title')
    list_filter = ('status','scheduled_at')
    readonly_fields = ('audience_rule','created_at','updated_at')


@admin.register(PushDeliveryLog)
class PushDeliveryLogAdmin(admin.ModelAdmin):
    list_display = ('campaign','user','activity','notification_type','status','sent_at','created_at')
    search_fields = ('campaign__title','user__display_name','user__line_user_id','activity__title','error_message','dedupe_key')
    list_filter = ('notification_type','status','sent_at')


@admin.register(OperationJob)
class OperationJobAdmin(admin.ModelAdmin):
    list_display = ('id','job_type','title','status','processed_count','total_count','success_count','failed_count','skipped_count','created_at','finished_at')
    search_fields = ('title','current_label','progress_message','error_summary')
    list_filter = ('job_type','status')
    readonly_fields = ('options','result_summary','created_at','updated_at','started_at','finished_at')


@admin.register(CrawlJob)
class CrawlJobAdmin(admin.ModelAdmin):
    list_display = ('id','title','source','status','created_by','created_at','finished_at')
    search_fields = ('title','source','error_summary')
    list_filter = ('status','source')
    readonly_fields = ('options','created_at','updated_at','started_at','finished_at')


@admin.register(CrawlTask)
class CrawlTaskAdmin(admin.ModelAdmin):
    list_display = ('job','source_key','status','created_count','updated_count','failed_count','finished_at')
    search_fields = ('source_key','error_summary')
    list_filter = ('status','source_key')
    readonly_fields = ('metadata','created_at','updated_at','started_at','finished_at')


@admin.register(ActivityChangeLog)
class ActivityChangeLogAdmin(admin.ModelAdmin):
    list_display = ('activity','field_name','notify_required','notified_at','created_at')
    search_fields = ('activity__title','field_name','old_value','new_value')
    list_filter = ('field_name','notify_required','notified_at')
    readonly_fields = ('metadata','created_at')


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ('actor','action','activity','created_at')
    search_fields = ('actor','action','activity__title')
    list_filter = ('action',)
    readonly_fields = ('metadata','created_at')
