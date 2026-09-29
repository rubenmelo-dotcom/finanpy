from django.contrib import admin

from profiles.models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'phone', 'birth_date', 'ai_analysis_enabled', 'created_at'
    )
    list_filter = ('ai_analysis_enabled',)
    search_fields = ('user__email', 'user__first_name')
    list_select_related = ('user',)
    readonly_fields = ('created_at', 'updated_at')
