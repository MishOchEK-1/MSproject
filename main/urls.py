from django.urls import path
from . import views

urlpatterns = [
    # Example path
    path('', views.index, name='index'),
]