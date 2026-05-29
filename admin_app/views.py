from django.shortcuts import render, redirect
from events.models import Activity
# Create your views here.

'''
admin_app 後台管理相關
''' 
# 登入(還沒有登入控制)
def login(request):
  if request.method == 'POST':
    # 簡單的登入邏輯（暫時不驗證，直接進入 dashboard）
    username = request.POST.get('username', '')
    password = request.POST.get('password', '')
    
    # TODO: 後續需要添加實際的身份驗證邏輯
    if username and password:  # 簡單的非空驗證
      return redirect('dashboard')
    else:
      return render(request, 'login.html', {'error': '帳號或密碼不能為空'})
  
  return render(request, 'login.html')


# 後台管理首頁dashboard
def dashboard(request):
  return render(request, 'dashboard.html')

## 後台活動列表
def activityList(request):
  activities = Activity.objects.select_related('source_website').order_by('-start_date', '-created_at')

  keyword = request.GET.get('q', '').strip()
  status = request.GET.get('status', 'all')
  district = request.GET.get('district', 'all')

  if keyword:
    activities = activities.filter(title__icontains=keyword)
  if status != 'all':
    activities = activities.filter(status=status)
  if district != 'all':
    activities = activities.filter(district=district)

  districts = (
    Activity.objects
    .exclude(district='')
    .values_list('district', flat=True)
    .distinct()
    .order_by('district')
  )

  return render(request, 'activityList.html', {
    'activities': activities[:100],
    'districts': districts,
    'selected_keyword': keyword,
    'selected_status': status,
    'selected_district': district,
  })

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
