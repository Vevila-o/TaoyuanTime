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
from admin_app import views

urlpatterns = [
    path('', views.login, name = 'login'), #登入畫面(目前沒有登入控制)
    path('admin/', admin.site.urls),
    path('dashboard/', views.dashboard, name = 'dashboard'), # 首頁儀表板
    path('activityList/', views.activityList, name = 'activityList'), # 活動列表
    path('activityList/activityAdd/', views.activityAdd, name = 'activityAdd'), # 新增活動
    path('activityList/Edit/<int:id>/', views.activityEdit, name = 'activityEdit'), # 編輯活動
    path('push', views.pushManagement, name = 'pushManagement'), # 推播管理
    path('User', views.userManagement, name = 'userManagement'), # 使用者管理

]
