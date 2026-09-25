from django.contrib import admin

from transactions.models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'description',
        'transaction_type',
        'amount',
        'date',
        'account',
        'category',
        'user',
    )
    list_filter = ('transaction_type', 'date')
    search_fields = ('description', 'user__email')
    date_hierarchy = 'date'
    list_select_related = ('account', 'category', 'user')
    readonly_fields = ('created_at', 'updated_at')
