from django.contrib import admin
from .models import Activtiy
# Register your models here.

class ActivityAdmin(admin.ModelAdmin):
  # 列表顯示欄位
  list_display = ['title', 'location', 'start_date', 'end_date', 'status']
  
  # 篩選器>>狀態
  list_filter = ['status']
  
  # 搜尋欄>>活動名稱 地點
  search_fields = ['title', 'location']
  
  # 編輯頁面的欄位排列
  fields = ['title', 'description', 'location', 'start_date', 'end_date', 'status']