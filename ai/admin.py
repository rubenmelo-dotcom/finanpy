"""Read-only admin for MonthlyAnalysis (PRD 14.4)."""

from django.contrib import admin

from ai.models import MonthlyAnalysis


@admin.register(MonthlyAnalysis)
class MonthlyAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'reference_month',
        'status',
        'model_name',
        'total_tokens',
        'attempts',
        'generated_at',
    )
    list_filter = ('status', 'reference_month')
    search_fields = ('user__email',)
    list_select_related = ('user',)
    date_hierarchy = 'reference_month'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
