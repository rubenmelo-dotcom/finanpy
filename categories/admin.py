from django.contrib import admin

from categories.models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'category_type',
        'color',
        'user',
        'created_at',
    )
    list_filter = ('category_type',)
    search_fields = ('name', 'user__email')
    list_select_related = ('user',)
    readonly_fields = ('created_at', 'updated_at')
