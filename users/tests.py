from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from core.test_utils import DEFAULT_PASSWORD, create_user

User = get_user_model()


class UserManagerTests(TestCase):
    def test_create_user_normalizes_email_and_hashes_password(self):
        user = User.objects.create_user(
            email='Fulano@EXEMPLO.COM', password=DEFAULT_PASSWORD
        )

        self.assertEqual(user.email, 'Fulano@exemplo.com')
        self.assertNotEqual(user.password, DEFAULT_PASSWORD)
        self.assertTrue(user.check_password(DEFAULT_PASSWORD))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_create_user_without_email_raises_value_error(self):
        with self.assertRaisesMessage(ValueError, 'O e-mail é obrigatório.'):
            User.objects.create_user(email='', password=DEFAULT_PASSWORD)

    def test_create_superuser_sets_staff_and_superuser_flags(self):
        user = User.objects.create_superuser(
            email='admin@example.com', password=DEFAULT_PASSWORD
        )

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_create_superuser_rejects_is_staff_false(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email='admin@example.com',
                password=DEFAULT_PASSWORD,
                is_staff=False,
            )

    def test_create_superuser_rejects_is_superuser_false(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email='admin@example.com',
                password=DEFAULT_PASSWORD,
                is_superuser=False,
            )


class UserModelTests(TestCase):
    def test_str_returns_email(self):
        user = create_user(email='fulano@example.com')

        self.assertEqual(str(user), 'fulano@example.com')

    def test_email_is_username_field(self):
        self.assertEqual(User.USERNAME_FIELD, 'email')
        self.assertIsNone(getattr(User, 'username', None))

    def test_user_model_is_registered_in_admin(self):
        self.assertTrue(admin.site.is_registered(User))


class SignUpViewTests(TestCase):
    url = reverse('signup')

    def get_payload(self, **extra):
        data = {
            'first_name': 'Fulano',
            'last_name': 'de Tal',
            'email': 'fulano@example.com',
            'password1': DEFAULT_PASSWORD,
            'password2': DEFAULT_PASSWORD,
        }
        data.update(extra)
        return data

    def test_signup_page_renders(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/signup.html')

    def test_duplicate_email_is_rejected(self):
        create_user(email='fulano@example.com')

        response = self.client.post(
            self.url, self.get_payload(email='FULANO@example.com')
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'],
            'email',
            'Já existe uma conta com este e-mail.',
        )
        self.assertEqual(User.objects.count(), 1)

    def test_valid_signup_authenticates_and_redirects_to_dashboard(self):
        response = self.client.post(self.url, self.get_payload())

        self.assertRedirects(response, reverse('dashboard'))
        user = User.objects.get(email='fulano@example.com')
        self.assertEqual(
            int(self.client.session['_auth_user_id']), user.pk
        )
        self.assertTrue(user.check_password(DEFAULT_PASSWORD))
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('Bem-vindo(a) ao Finanpy!', messages)

    def test_signup_with_mismatched_passwords_does_not_create_user(self):
        response = self.client.post(
            self.url, self.get_payload(password2='OutraSenha!2026')
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors['password2'])
        self.assertFalse(User.objects.exists())

    def test_authenticated_user_is_redirected_from_signup(self):
        self.client.force_login(create_user())

        response = self.client.get(self.url)

        self.assertRedirects(response, reverse('dashboard'))


class LoginViewTests(TestCase):
    url = reverse('login')

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user(
            email='fulano@example.com', first_name='Fulano'
        )

    def test_login_page_renders(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')

    def test_valid_login_redirects_to_dashboard(self):
        response = self.client.post(
            self.url,
            {'username': 'fulano@example.com', 'password': DEFAULT_PASSWORD},
        )

        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(
            int(self.client.session['_auth_user_id']), self.user.pk
        )
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('Bem-vindo(a) de volta, Fulano!', messages)

    def test_invalid_login_shows_ptbr_error_message(self):
        response = self.client.post(
            self.url,
            {'username': 'fulano@example.com', 'password': 'errada'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'], None, 'E-mail ou senha inválidos.'
        )
        self.assertContains(response, 'E-mail ou senha inválidos.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_authenticated_user_is_redirected_from_login(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertRedirects(response, reverse('dashboard'))


class LogoutViewTests(TestCase):
    url = reverse('logout')

    def test_logout_via_post_redirects_to_home(self):
        self.client.force_login(create_user())

        response = self.client.post(self.url)

        self.assertRedirects(response, reverse('home'))
        self.assertNotIn('_auth_user_id', self.client.session)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('Você saiu da sua conta. Até logo!', messages)

    def test_logout_via_get_is_not_allowed(self):
        self.client.force_login(create_user())

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)
