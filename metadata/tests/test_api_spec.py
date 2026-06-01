import os
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from integrations.models import Tracker
from metadata.models import ApiSpec

User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ApiSpecModelTests(TestCase):
    def setUp(self):
        self.tracker = Tracker.objects.create(name='Binom')

    def test_upload_stores_file_and_source_filename(self):
        payload = b'openapi: 3.0.0\ninfo:\n  title: Test\n'
        uploaded = SimpleUploadedFile('binom-admin.yaml', payload, content_type='text/yaml')
        spec = ApiSpec.objects.create(
            tracker=self.tracker,
            name='Admin API',
            spec_file=uploaded,
        )
        spec.refresh_from_db()

        self.assertEqual(spec.source_filename, 'binom-admin.yaml')
        self.assertEqual(spec.format, 'openapi')
        self.assertTrue(spec.spec_file.name.startswith(f'api_specs/{self.tracker.pk}/'))
        self.assertTrue(os.path.exists(spec.spec_file.path))
        with open(spec.spec_file.path, 'rb') as handle:
            self.assertEqual(handle.read(), payload)

    def test_delete_removes_file_from_disk(self):
        uploaded = SimpleUploadedFile('spec.txt', b'hello', content_type='text/plain')
        spec = ApiSpec.objects.create(
            tracker=self.tracker,
            name='Plain spec',
            spec_file=uploaded,
        )
        path = spec.spec_file.path
        spec.delete()
        self.assertFalse(os.path.exists(path))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ApiSpecAdminTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='password',
        )
        self.client = Client()
        self.client.force_login(self.superuser)
        self.tracker = Tracker.objects.create(name='Keitaro')

    def test_admin_create_uploads_file(self):
        add_url = reverse('admin:metadata_apispec_add')
        payload = SimpleUploadedFile('keitaro-openapi.yml', b'paths: {}', content_type='text/yaml')
        response = self.client.post(
            add_url,
            {
                'tracker': self.tracker.pk,
                'name': 'Public API',
                'spec_file': payload,
                'format': 'unknown',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        spec = ApiSpec.objects.get(name='Public API')
        self.assertEqual(spec.source_filename, 'keitaro-openapi.yml')
        self.assertEqual(spec.format, 'openapi')
        self.assertTrue(os.path.exists(spec.spec_file.path))
