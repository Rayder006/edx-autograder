from django.urls import path
from django.conf import settings
from . import views

urlpatterns = [
    path('avaliacao/', views.lti_grade_endpoint, name='lti_grade_endpoint'),
]

# O simulador local de LTI só é registrado em ambiente de desenvolvimento (DEBUG = True)
if settings.DEBUG:
    urlpatterns.append(path('test-launcher/', views.test_launcher_view, name='test_launcher_view'))