from django.contrib.auth.views import LogoutView
from django.urls import path

from users.views import SignUpView, UserLoginView

urlpatterns = [
    path('cadastro/', SignUpView.as_view(), name='signup'),
    path('entrar/', UserLoginView.as_view(), name='login'),
    path('sair/', LogoutView.as_view(), name='logout'),
]
