# medical_project/urls.py

from django.contrib import admin
from django.urls import path
from symptom_checker import views
# Add this import at the top
from symptom_checker.views import download_report

# Add this path in urlpatterns


urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Public pages
    path('', views.home, name='home'),
    path('general-medicines/', views.general_medicines, name='general_medicines'),
    path('symptom-checker/', views.symptom_checker, name='symptom_checker'),
    path('health-tips/', views.health_tips, name='health_tips'),
    path('about/', views.about, name='about'),
    
    # Authentication
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    
    # Protected pages (require login)
    path('dashboard/', views.dashboard, name='dashboard'),
    path('history/', views.history, name='history'),
    path('emergency/', views.emergency, name='emergency'),
    path('profile/', views.profile, name='profile'),
    path('download-report/<int:history_id>/', download_report, name='download_report'),
    # AJAX endpoints
    path('analyze/', views.analyze_symptoms, name='analyze_symptoms'),
    
]