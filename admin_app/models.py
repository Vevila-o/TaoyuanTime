from django.db import models

# 政府活動後台
class Activtiy(models.Model):
  
  # basic info
  title = models.CharField('活動名稱', max_length = 200)
  description = models.TextField('活動說明', blank = True)
  location = models.CharField('活動地點', max_length = 200, blank=True)
  start_date = models.DateTimeField('開始時間', null=True, blank=True)
  end_date = models.DateTimeField('結束時間', null=True, blank=True)
  
  # 活動狀態
  STATUS_CHOICES = [
    ('draft', '草稿'),
    ('inactive', '已下架'),
    ('active', '已上架'),
  ]
  status = models.CharField('狀態', max_length =10, choices=STATUS_CHOICES, default = 'draft')
  
  # 系統自動記錄
  created_at = models.DateTimeField('建立時間', auto_now_add = True)
  updated_at = models.DateTimeField('更新時間', auto_now = True )
  
  class Meta:
    verbose_name = '活動'
    verbose_name_plural = '活動管理'
    
  def __str__(self):
    return self.title