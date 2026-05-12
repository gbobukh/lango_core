from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from metadata.models import CompatibilityMatrix, TargetParameter

User = get_user_model()


class CompatibilityMatrixAdminLockTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password',
        )
        self.client = Client()
        self.client.force_login(self.superuser)

        self.device_type = TargetParameter.objects.create(
            name='Device type',
            values=['TAB', 'Mobile'],
        )
        self.os = TargetParameter.objects.create(
            name='OS',
            values=['Android', 'iPAD', 'iOS'],
        )
        self.rule = CompatibilityMatrix.objects.create(
            subject_parameter=self.device_type,
            subject_value='TAB',
            target_parameter=self.os,
            allowed_values=['Android', 'iPAD'],
            is_locked=True,
        )
        self.rule.visible_to.add(self.superuser)

        self.demo_admin = User.objects.create_user(
            username='demo_admin',
            email='demo@example.com',
            password='password',
        )

    def test_locked_save_updates_visible_to_without_clearing_rule_fields(self):
        url = reverse('admin:metadata_compatibilitymatrix_change', args=[self.rule.pk])
        response = self.client.post(
            url,
            {
                'is_locked': 'on',
                'visible_to': [str(self.demo_admin.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)

        self.rule.refresh_from_db()
        self.assertEqual(self.rule.subject_parameter_id, self.device_type.pk)
        self.assertEqual(self.rule.subject_value, 'TAB')
        self.assertEqual(self.rule.target_parameter_id, self.os.pk)
        self.assertEqual(self.rule.allowed_values, ['Android', 'iPAD'])
        self.assertTrue(self.rule.is_locked)
        self.assertEqual(
            set(self.rule.visible_to.values_list('pk', flat=True)),
            {self.demo_admin.pk},
        )

    def test_unlocked_save_updates_rule_fields(self):
        url = reverse('admin:metadata_compatibilitymatrix_change', args=[self.rule.pk])
        response = self.client.post(
            url,
            {
                'subject_parameter': str(self.device_type.pk),
                'subject_value': 'Mobile',
                'target_parameter': str(self.os.pk),
                'allowed_values': ['iOS'],
                'visible_to': [str(self.superuser.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)

        self.rule.refresh_from_db()
        self.assertEqual(self.rule.subject_value, 'Mobile')
        self.assertEqual(self.rule.allowed_values, ['iOS'])
        self.assertTrue(self.rule.is_locked)
