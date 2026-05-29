from django.contrib import admin
from .models import SourceWebsite, Activity, Tag, UserProfile, Subscription, ActionLog

# Register your models here.
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
    list_display = ('user','activity','remind_before_days','is_notified','created_at')
    search_fields = ('user__display_name','user__line_user_id','activity__title')
    list_filter = ('is_notified',)


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ('user','action_type','activity','created_at')
    search_fields = ('user__display_name','user__line_user_id','activity__title')
    list_filter = ('action_type',)
    readonly_fields = ('metadata','created_at')
 