from django.shortcuts import render

# Create your views here.

def login_view(request):
	return render(request, 'login.html')

def dashboard(request):
	return render(request, 'dashboard.html')

def instances(request):
	return render(request, 'instances.html')

def hardening(request):
	return render(request, 'hardening.html')

