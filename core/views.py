from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.models import Account
from categories.models import Category
from transactions.models import Transaction
from transactions.views import _sum_by_type

INCOME = Transaction.TransactionType.INCOME
EXPENSE = Transaction.TransactionType.EXPENSE


class HomeView(TemplateView):
    template_name = 'home.html'


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        month_start = today.replace(day=1)

        accounts = list(
            Account.objects.with_balance(user)
            .filter(is_active=True)
            .order_by('name')
        )
        total_balance = sum(
            (account.balance for account in accounts), Decimal('0.00')
        )

        user_transactions = Transaction.objects.filter(user=user)
        month_transactions = user_transactions.filter(
            date__gte=month_start, date__lte=today
        )
        totals = month_transactions.aggregate(
            month_income=_sum_by_type(INCOME),
            month_expense=_sum_by_type(EXPENSE),
        )
        month_income = totals['month_income']
        month_expense = totals['month_expense']

        expenses_by_category = [
            {
                'name': row['category__name'],
                'color': row['category__color'],
                'total': row['total'],
                'percent': (
                    round(row['total'] / month_expense * 100)
                    if month_expense else 0
                ),
            }
            for row in month_transactions.filter(transaction_type=EXPENSE)
            .values('category__name', 'category__color')
            .annotate(total=Sum('amount'))
            .order_by('-total')
        ]

        recent_transactions = user_transactions.select_related(
            'account', 'category'
        )[:5]

        has_accounts = Account.objects.filter(user=user).exists()
        has_categories = Category.objects.filter(user=user).exists()
        has_transactions = user_transactions.exists()

        context.update({
            'today': today,
            'month_start': month_start,
            'accounts': accounts,
            'total_balance': total_balance,
            'month_income': month_income,
            'month_expense': month_expense,
            'month_result': month_income - month_expense,
            'expenses_by_category': expenses_by_category,
            'recent_transactions': recent_transactions,
            'has_accounts': has_accounts,
            'has_categories': has_categories,
            'has_transactions': has_transactions,
            'onboarding_complete': (
                has_accounts and has_categories and has_transactions
            ),
        })
        return context
