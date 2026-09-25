from django.conf import settings
from django.db import models


class Category(models.Model):
    class CategoryType(models.TextChoices):
        INCOME = 'income', 'Entrada'
        EXPENSE = 'expense', 'Saída'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='categories',
        verbose_name='usuário',
    )
    name = models.CharField('nome', max_length=50)
    category_type = models.CharField(
        'tipo', max_length=10, choices=CategoryType.choices
    )
    color = models.CharField('cor', max_length=7, default='#8B5CF6')
    created_at = models.DateTimeField('criado em', auto_now_add=True)
    updated_at = models.DateTimeField('atualizado em', auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'categoria'
        verbose_name_plural = 'categorias'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name', 'category_type'],
                name='unique_category_per_user',
            ),
        ]

    def __str__(self):
        return self.name
