
from django.contrib import admin
from django.urls import path
# 引入剛剛寫好 LINE Bot 邏輯的 events app 視圖
from events import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # 新增 LINE Bot Webhook 的專屬路由
    # 這樣你的 LINE 接收網址就會是：你的網址/callback/
    path('callback', views.callback, name='line_callback'),
]