from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "myapp"

urlpatterns = [
    # pages
    path("", views.home, name="home"),
    path("type/<slug:slug>/", views.typeface, name="typeface"),
    path("faq/", views.faq, name="faq"),
    path("errors/", views.errors, name="errors"),
    path("submit/", views.submit, name="submit"),
    path("health/", views.health, name="health"),
    path("health.json", views.health, name="health_json"),
    # accounts
    path("signup/", views.signup, name="signup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # JSON endpoints
    path("match/", views.match, name="match"),
    path("api/chat/", views.chat, name="chat"),
    path("api/chat/feedback/", views.chat_feedback, name="chat_feedback"),
    path("api/tickets/", views.ticket, name="ticket"),
    path("api/typefaces/<slug:slug>/history/", views.typeface_history, name="typeface_history"),
]
