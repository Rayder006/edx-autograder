from django.urls import path
from . import views

urlpatterns = [
    path('avaliacao/', views.lti_grade_endpoint, name='lti_grade_endpoint'),
]