"""
URL configuration for myproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('myapp.urls')),
]

# Custom error pages, each with an "Ask the assistant" option
handler400 = 'myapp.views.bad_request'
handler403 = 'myapp.views.permission_denied'
handler404 = 'myapp.views.page_not_found'
handler500 = 'myapp.views.server_error'
