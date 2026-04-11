from django.contrib import admin
from django.urls import path
from api.api import api  # importing api file with ninja logic 

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),   # binding ninja routes so they will be under /api/
]