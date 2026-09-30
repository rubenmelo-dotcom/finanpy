from datetime import date

from django.contrib import admin
from django.db import IntegrityError, transaction
from django.test import TestCase

from ai.constants import AI_MAX_ATTEMPTS
from ai.models import AnalysisStatus, MonthlyAnalysis
from ai.tests.utils import create_analysis
from core.test_utils import create_user


class MonthlyAnalysisConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()

    def test_one_analysis_per_user_and_month(self):
        create_analysis(self.user, date(2026, 8, 1))

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_analysis(self.user, date(2026, 8, 1))

    def test_same_month_allowed_for_other_user(self):
        other = create_user(email='outro@example.com')
        create_analysis(self.user, date(2026, 8, 1))

        create_analysis(other, date(2026, 8, 1))

        self.assertEqual(MonthlyAnalysis.objects.count(), 2)

    def test_reference_month_must_be_first_day(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MonthlyAnalysis.objects.create(
                    user=self.user,
                    reference_month=date(2026, 8, 15),
                    period_start=date(2026, 5, 1),
                    period_end=date(2026, 8, 15),
                )


class MonthlyAnalysisQuerySetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.other = create_user(email='outro@example.com')

    def test_latest_completed_ignores_other_status_and_users(self):
        create_analysis(self.user, date(2026, 6, 1))
        expected = create_analysis(self.user, date(2026, 7, 1))
        create_analysis(
            self.user, date(2026, 8, 1), status=AnalysisStatus.FAILED,
        )
        create_analysis(self.other, date(2026, 9, 1))

        self.assertEqual(
            MonthlyAnalysis.objects.latest_completed(self.user), expected
        )

    def test_latest_completed_without_analysis_is_none(self):
        create_analysis(
            self.user, date(2026, 8, 1),
            status=AnalysisStatus.INSUFFICIENT_DATA,
        )

        self.assertIsNone(
            MonthlyAnalysis.objects.latest_completed(self.user)
        )


class MonthlyAnalysisPropertyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user(email='fulano@example.com')

    def build(self, **extra):
        return MonthlyAnalysis(
            user=self.user, reference_month=date(2026, 8, 1), **extra
        )

    def test_can_retry_only_failed_below_limit(self):
        self.assertTrue(
            self.build(
                status=AnalysisStatus.FAILED, attempts=AI_MAX_ATTEMPTS - 1,
            ).can_retry
        )
        self.assertFalse(
            self.build(
                status=AnalysisStatus.FAILED, attempts=AI_MAX_ATTEMPTS,
            ).can_retry
        )
        for status in (
            AnalysisStatus.PENDING,
            AnalysisStatus.PROCESSING,
            AnalysisStatus.COMPLETED,
            AnalysisStatus.INSUFFICIENT_DATA,
        ):
            with self.subTest(status=status):
                self.assertFalse(
                    self.build(status=status, attempts=0).can_retry
                )

    def test_is_final_only_when_completed(self):
        self.assertTrue(
            self.build(status=AnalysisStatus.COMPLETED).is_final
        )
        self.assertFalse(self.build(status=AnalysisStatus.FAILED).is_final)

    def test_content_properties(self):
        analysis = self.build(content={
            'summary': 'Resumo',
            'overall_status': 'attention',
            'insights': [{'title': 'A'}],
            'tips': None,
        })

        self.assertEqual(analysis.summary, 'Resumo')
        self.assertEqual(analysis.overall_status, 'attention')
        self.assertEqual(analysis.insights, [{'title': 'A'}])
        self.assertEqual(analysis.tips, [])

    def test_content_properties_without_content(self):
        analysis = self.build(content=None)

        self.assertEqual(analysis.summary, '')
        self.assertEqual(analysis.overall_status, '')
        self.assertEqual(analysis.insights, [])
        self.assertEqual(analysis.tips, [])

    def test_str_and_defaults(self):
        analysis = create_analysis(
            self.user, date(2026, 8, 1), status=AnalysisStatus.PENDING,
        )

        self.assertEqual(str(analysis), 'fulano@example.com · 08/2026')
        self.assertEqual(analysis.attempts, 0)
        self.assertEqual(analysis.schema_version, 1)


class MonthlyAnalysisAdminTests(TestCase):
    def test_registered_read_only(self):
        self.assertTrue(admin.site.is_registered(MonthlyAnalysis))
        model_admin = admin.site._registry[MonthlyAnalysis]
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_change_permission(None))
