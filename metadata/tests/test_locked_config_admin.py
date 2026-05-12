from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from integrations.models import PartnerAccount, PartnerAccountType, Tracker
from metadata.models import GlobalVariable, PublisherConfig, TargetParameter, TrackerConfig

User = get_user_model()


class PublisherConfigAdminLockTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password',
        )
        self.client = Client()
        self.client.force_login(self.superuser)

        self.publisher_type = PartnerAccountType.objects.create(name='Publisher')
        self.partner_account = PartnerAccount.objects.create(
            name='Publisher One',
            account_type=self.publisher_type,
        )
        TargetParameter.objects.create(name='Country', values=['US', 'UK'])
        self.config_payload = {
            'Country': {'exists': True, 'ttz_encoded': False},
        }
        self.publisher_config = PublisherConfig.objects.create(
            partner_account=self.partner_account,
            config=self.config_payload,
            is_locked=True,
        )
        self.publisher_config.visible_to.add(self.superuser)

        self.demo_admin = User.objects.create_user(
            username='demo_admin',
            email='demo@example.com',
            password='password',
        )

    def test_locked_save_updates_visible_to_without_clearing_config(self):
        url = reverse('admin:metadata_publisherconfig_change', args=[self.publisher_config.pk])
        response = self.client.post(
            url,
            {
                'is_locked': 'on',
                'visible_to': [str(self.demo_admin.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)

        self.publisher_config.refresh_from_db()
        self.assertEqual(self.publisher_config.partner_account_id, self.partner_account.pk)
        self.assertEqual(self.publisher_config.config, self.config_payload)
        self.assertTrue(self.publisher_config.is_locked)
        self.assertEqual(
            set(self.publisher_config.visible_to.values_list('pk', flat=True)),
            {self.demo_admin.pk},
        )

    def test_locked_change_view_renders_config_table(self):
        url = reverse('admin:metadata_publisherconfig_change', args=[self.publisher_config.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.count(b'publisher-config-widget'), 1)
        self.assertContains(response, 'config-widget-locked')
        self.assertNotContains(response, 'id="widget_config"')
        self.assertContains(response, 'Country')

    def test_unlock_save_persists_unlocked_state(self):
        url = reverse('admin:metadata_publisherconfig_change', args=[self.publisher_config.pk])
        response = self.client.post(url, {'visible_to': [str(self.superuser.pk)]})
        self.assertEqual(response.status_code, 302)

        self.publisher_config.refresh_from_db()
        self.assertFalse(self.publisher_config.is_locked)
        self.assertEqual(self.publisher_config.config, self.config_payload)


class TrackerConfigAdminLockTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password',
        )
        self.client = Client()
        self.client.force_login(self.superuser)

        self.tracker = Tracker.objects.create(name='Binom')
        GlobalVariable.objects.create(name='STD_CLICK', description='Click id')
        self.mapping_payload = {'STD_CLICK': 'click_id'}
        self.tracker_config = TrackerConfig.objects.create(
            tracker=self.tracker,
            mapping=self.mapping_payload,
            is_locked=True,
        )
        self.tracker_config.visible_to.add(self.superuser)

        self.demo_admin = User.objects.create_user(
            username='demo_admin',
            email='demo@example.com',
            password='password',
        )

    def test_locked_save_updates_visible_to_without_clearing_mapping(self):
        url = reverse('admin:metadata_trackerconfig_change', args=[self.tracker_config.pk])
        response = self.client.post(
            url,
            {
                'is_locked': 'on',
                'visible_to': [str(self.demo_admin.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)

        self.tracker_config.refresh_from_db()
        self.assertEqual(self.tracker_config.tracker_id, self.tracker.pk)
        self.assertEqual(self.tracker_config.mapping, self.mapping_payload)
        self.assertTrue(self.tracker_config.is_locked)
        self.assertEqual(
            set(self.tracker_config.visible_to.values_list('pk', flat=True)),
            {self.demo_admin.pk},
        )

    def test_locked_change_view_renders_mapping_table(self):
        url = reverse('admin:metadata_trackerconfig_change', args=[self.tracker_config.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.count(b'tracker-config-widget'), 1)
        self.assertContains(response, 'config-widget-locked')
        self.assertNotContains(response, 'class="key-input"')
        self.assertContains(response, 'mapping-value')
        self.assertNotContains(response, 'id="widget_mapping"')
        self.assertContains(response, 'STD_CLICK')

    def test_unlock_save_persists_unlocked_state(self):
        url = reverse('admin:metadata_trackerconfig_change', args=[self.tracker_config.pk])
        response = self.client.post(url, {'visible_to': [str(self.superuser.pk)]})
        self.assertEqual(response.status_code, 302)

        self.tracker_config.refresh_from_db()
        self.assertFalse(self.tracker_config.is_locked)
        self.assertEqual(self.tracker_config.mapping, self.mapping_payload)
