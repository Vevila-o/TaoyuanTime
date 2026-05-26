from django.shortcuts import render
# Create your views here.

'''
admin_app 後台管理相關
''' 
# 登入(還沒有登入控制)
def login(request):
  return render(request, 'login.html')


# 後台管理首頁dashboard
def dashboard(request):
  return render(request, 'dashboard.html')

## 後台活動列表
def activityList(request):
  return render(request, 'activityList.html')

## 活動新增
def activityAdd(request):
  return render(request, 'activityAdd.html')

## 活動編輯
def activityEdit(request, id):
  return render(request, 'activityEdit.html')

## 推播
def pushManagement(request):
  return render(request, 'pushManagement.html')

##使用者管理
def userManagement(request):
  return render(request, 'userManagement.html')