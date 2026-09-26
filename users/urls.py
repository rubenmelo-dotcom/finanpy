from django.urls import path

from users.views import SignUpView, UserLoginView, UserLogoutView

urlpatterns = [
    path('cadastro/', SignUpView.as_view(), name='signup'),
    path('entrar/', UserLoginView.as_view(), name='login'),
    path('sair/', UserLogoutView.as_view(), name='logout'),
]
