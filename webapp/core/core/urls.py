from django.contrib import admin
from django.urls import path
from django.views.generic.base import RedirectView
from api.api import api  # importing api file with ninja logic
from api import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),   # binding ninja routes so they will be under /api/
	path('instances/', views.instances, name='instances'),
	path('hardening/', views.hardening, name='hardening'),
	path('login/', views.login_view, name='login'),
	path('docs/', RedirectView.as_view(url='https://github.com/mikalaytsepl/CIAHP'), name='docs'),
	path('', views.dashboard, name='dashboard'),
]