from datetime import date, timedelta

from django.contrib import admin
from django.contrib.auth import SESSION_KEY
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.test_utils import DEFAULT_PASSWORD, create_user
from profiles.models import Profile

NEW_PASSWORD = 'NovaSenhaForte!2026'


class ProfileSignalTests(TestCase):
    def test_signal_creates_profile_when_user_is_created(self):
        user = create_user()

        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.phone, '')
        self.assertIsNone(user.profile.birth_date)

    def test_signal_does_not_duplicate_profile_on_user_update(self):
        user = create_user()
        user.first_name = 'Fulano'
        user.save()

        self.assertEqual(Profile.objects.filter(user=user).count(), 1)


class ProfileModelTests(TestCase):
    def test_str_mentions_user_email(self):
        user = create_user(email='fulano@example.com')

        self.assertEqual(str(user.profile), 'Perfil de fulano@example.com')

    def test_profile_model_is_registered_in_admin(self):
        self.assertTrue(admin.site.is_registered(Profile))


class ProfileDetailViewTests(TestCase):
    url = reverse('profiles:detail')

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user(
            email='fulano@example.com',
            first_name='Fulano',
            last_name='de Tal',
        )

    def test_detail_shows_logged_user_data(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'profiles/profile_detail.html')
        self.assertEqual(response.context['profile'], self.user.profile)
        self.assertContains(response, 'fulano@example.com')


class ProfileUpdateViewTests(TestCase):
    url = reverse('profiles:update')

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user(
            email='fulano@example.com',
            first_name='Fulano',
            last_name='de Tal',
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_update_page_renders_both_forms(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)
        self.assertIn('user_form', response.context)

    def test_profile_update_changes_user_and_profile(self):
        response = self.client.post(self.url, {
            'first_name': 'Beltrano',
            'last_name': 'Silva',
            'phone': '(11) 98888-7777',
            'birth_date': '1990-05-20',
        })

        self.assertRedirects(response, reverse('profiles:detail'))
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Beltrano')
        self.assertEqual(self.user.last_name, 'Silva')
        self.assertEqual(self.user.profile.phone, '(11) 98888-7777')
        self.assertEqual(self.user.profile.birth_date, date(1990, 5, 20))
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('Perfil atualizado com sucesso.', messages)

    def test_future_birth_date_is_rejected(self):
        tomorrow = timezone.localdate() + timedelta(days=1)

        response = self.client.post(self.url, {
            'first_name': 'Beltrano',
            'last_name': 'Silva',
            'phone': '',
            'birth_date': tomorrow.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'],
            'birth_date',
            'A data de nascimento não pode estar no futuro.',
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Fulano')

    def test_missing_first_name_does_not_update_profile(self):
        response = self.client.post(self.url, {
            'first_name': '',
            'last_name': 'Silva',
            'phone': '(11) 98888-7777',
            'birth_date': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['user_form'].errors['first_name'])
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.phone, '')


class PasswordChangeViewTests(TestCase):
    url = reverse('profiles:password')

    def setUp(self):
        self.user = create_user()
        self.client.force_login(self.user)

    def test_password_change_works_and_keeps_session(self):
        response = self.client.post(self.url, {
            'old_password': DEFAULT_PASSWORD,
            'new_password1': NEW_PASSWORD,
            'new_password2': NEW_PASSWORD,
        })

        self.assertRedirects(response, reverse('profiles:detail'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertEqual(int(self.client.session[SESSION_KEY]), self.user.pk)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('Senha alterada com sucesso.', messages)

        response = self.client.get(reverse('profiles:detail'))
        self.assertEqual(response.status_code, 200)

    def test_wrong_old_password_shows_ptbr_error(self):
        response = self.client.post(self.url, {
            'old_password': 'errada',
            'new_password1': NEW_PASSWORD,
            'new_password2': NEW_PASSWORD,
        })

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'],
            'old_password',
            'A senha atual foi digitada incorretamente. Informe-a '
            'novamente.',
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(DEFAULT_PASSWORD))


class ProfileLoginRequiredTests(TestCase):
    def test_profile_pages_require_login(self):
        for name in ('profiles:detail', 'profiles:update',
                     'profiles:password'):
            with self.subTest(name=name):
                url = reverse(name)

                response = self.client.get(url)

                login_url = reverse('login')
                self.assertRedirects(response, f'{login_url}?next={url}')
