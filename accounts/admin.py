from django.contrib import admin

from accounts.models import Account


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'user',
        'account_type',
        'initial_balance',
        'is_active',
        'created_at',
    )
    list_filter = ('account_type', 'is_active')
    search_fields = ('name', 'bank_name', 'user__email')
    list_select_related = ('user',)
    readonly_fields = ('created_at', 'updated_at')
