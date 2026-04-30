from unittest.mock import patch

from django.test import TestCase

from integrations.models import ApiAuthID, ApiAuthType, Tracker
from integrations.utils import _mask_url_sensitive, apply_auth_to_request


class PathTemplateAuthTests(TestCase):
    def setUp(self):
        self.tracker = Tracker.objects.create(name='tg')

    def test_static_path_template_renders_credentials_without_header_or_query_duplication(self):
        auth_type = ApiAuthType.objects.create(
            name='Telegram Static Path',
            key_definitions=['token'],
            static_inject_in='PATH_TEMPLATE',
        )
        auth_id = ApiAuthID.objects.create(
            account_name='tg-static-path',
            tracker=self.tracker,
            request_url='https://api.telegram.org/bot%token%',
            auth_type=auth_type,
        )
        auth_id.set_credentials({'token': '12345:abc'})
        auth_id.save(update_fields=['credentials_encrypted'])

        url, headers = apply_auth_to_request(
            auth_id,
            'https://api.telegram.org/bot%token%/sendMessage',
            headers={},
        )

        self.assertEqual(url, 'https://api.telegram.org/bot12345:abc/sendMessage')
        self.assertEqual(headers, {})
        self.assertNotIn('token=', url)

    def test_active_path_template_replaces_token_placeholder(self):
        auth_type = ApiAuthType.objects.create(
            name='Path Active Auth',
            key_definitions=['username', 'password'],
            static_inject_in='HEADER',
            login_url='https://example.com/login',
            inject_in='PATH_TEMPLATE',
            inject_key='access_token',
        )
        auth_id = ApiAuthID.objects.create(
            account_name='active-path-auth',
            tracker=self.tracker,
            request_url='https://example.com',
            auth_type=auth_type,
        )
        auth_id.set_credentials({'username': 'u', 'password': 'p'})
        auth_id.save(update_fields=['credentials_encrypted'])

        with patch('integrations.utils.perform_auto_login', return_value=('secret-token', 'PATH_TEMPLATE', 'access_token')):
            url, headers = apply_auth_to_request(
                auth_id,
                'https://api.example.com/%access_token%/resource',
                headers={},
            )

        self.assertEqual(url, 'https://api.example.com/secret-token/resource')
        self.assertEqual(headers, {})

    def test_mask_url_sensitive_hides_query_and_path_values(self):
        masked = _mask_url_sensitive(
            'https://api.telegram.org/bot12345:abc/sendMessage?token=12345:abc&chat_id=99',
            sensitive_values=['12345:abc'],
        )
        self.assertNotIn('12345:abc', masked)
        self.assertIn('***MASKED***', masked)
