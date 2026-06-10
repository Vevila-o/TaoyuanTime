"""
URL configuration for IMintergrateSys project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from admin_app import views
from myapp import views as line_views

urlpatterns = [
    path('', views.login, name = 'login'), #登入畫面(目前沒有登入控制)
    path('admin/', admin.site.urls),
    path('dashboard/', views.dashboard, name = 'dashboard'), # 首頁儀表板
    path('operations/', views.operations, name='operations'), # 營運工具
    path('operations/jobs/', views.operationJobs, name='operationJobs'), # 營運任務列表
    path('operations/jobs/<int:id>/', views.operationJobDetail, name='operationJobDetail'), # 營運任務詳情
    path('lineQuerySimulator/', views.lineQuerySimulator, name='lineQuerySimulator'), # LINE 查詢模擬
    path('activityList/', views.activityList, name = 'activityList'), # 活動列表
    path('activityList/activityAdd/', views.activityAdd, name = 'activityAdd'), # 新增活動
    path('activityList/Edit/<int:id>/', views.activityEdit, name = 'activityEdit'), # 編輯活動
    path('activityList/Status/<int:id>/', views.activitySetStatus, name='activitySetStatus'), # 活動上下架
    path('activityList/Readiness/<int:id>/', views.activitySetReadiness, name='activitySetReadiness'), # 活動 ready 標記
    path('activityList/ApplyAiTags/<int:id>/', views.activityApplyAiTags, name='activityApplyAiTags'), # 單筆 AI Tag 套用
    path('tagReview/', views.tagReview, name='tagReview'), # Tag 審核
    path('tagReview/<int:id>/', views.tagSuggestionAction, name='tagSuggestionAction'), # Tag 審核動作
    path('push', views.pushManagement, name = 'pushManagement'), # 推播管理
    path('User', views.userManagement, name = 'userManagement'), # 使用者管理
    path('User/<int:id>/', views.userDetail, name='userDetail'), # 使用者詳情
    path('crawlJobs/', views.crawlJobs, name='crawlJobs'), # 爬蟲任務
    path('crawlJobs/<int:id>/', views.crawlJobDetail, name='crawlJobDetail'), # 爬蟲任務詳情
    path('activityChanges/', views.activityChanges, name='activityChanges'), # 活動異動
    path('callback', line_views.callback, name='line_callback_no_slash'), # LINE webhook alias
    path('callback/', line_views.callback, name='line_callback'), # LINE webhook
    path('webhook', line_views.callback, name='line_webhook_no_slash'), # LINE webhook alias
    path('webhook/', line_views.callback, name='line_webhook'), # LINE webhook alias
    path('webhook/line/', line_views.callback, name='line_webhook_line'), # LINE webhook alias
    path('track/activity/<int:activity_id>/', line_views.track_activity, name='track_activity'), # LINE card tracking
    path('track/calendar/<int:activity_id>/', line_views.track_calendar, name='track_calendar'), # LINE calendar tracking
    path('track/maps/<int:activity_id>/', line_views.track_maps, name='track_maps'), # LINE maps tracking

]

# 配置媒體文件服務（開發環境）
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
