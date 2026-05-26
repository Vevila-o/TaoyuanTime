from django.apps import AppConfig

class AdminAppConfig(AppConfig):
  # 資料庫主鍵是自動遞增
  default_auto_field = 'django.db.models.BigAutoField'
  name = 'admin_app'
  # verbose_name 是後台顯示的中文名稱
  verbose_name = '政府後台管理'