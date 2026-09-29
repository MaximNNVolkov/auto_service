from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class UserAdminTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(username="admin", password="pass12345")
        self.client.login(username="admin", password="pass12345")

    def test_change_page_shows_role_and_hides_raw_password(self):
        response = self.client.get(reverse("admin:users_user_change", args=[self.admin.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="role"')
        self.assertNotContains(response, 'name="password"')

    def test_password_change_page_is_available(self):
        response = self.client.get(reverse("admin:auth_user_password_change", args=[self.admin.pk]))
        self.assertEqual(response.status_code, 200)
