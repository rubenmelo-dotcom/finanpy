from django.urls import path

from profiles.views import (
    ProfileDetailView,
    ProfileUpdateView,
    UserPasswordChangeView,
)

app_name = 'profiles'

urlpatterns = [
    path('', ProfileDetailView.as_view(), name='detail'),
    path('editar/', ProfileUpdateView.as_view(), name='update'),
    path('senha/', UserPasswordChangeView.as_view(), name='password'),
]
