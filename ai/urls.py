from django.urls import path

from ai.views import GenerateAnalysisView

app_name = 'ai'

urlpatterns = [
    path('gerar/', GenerateAnalysisView.as_view(), name='generate'),
]
