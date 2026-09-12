import ssl
import unittest
from unittest.mock import patch
from main import tls_context, Plugin


class CertificateTests(unittest.TestCase):
    def test_loads_system_roots_when_python_defaults_are_empty(self):
        empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertFalse(empty.get_ca_certs())
        with patch('main.ssl.create_default_context', return_value=empty):
            context = tls_context()
        self.assertTrue(context.get_ca_certs())
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_missing_roots_fails_closed_with_useful_message(self):
        empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with patch('main.ssl.create_default_context', return_value=empty), patch('main.SYSTEM_CA_BUNDLES', ()):
            with self.assertRaisesRegex(RuntimeError, 'trusted system certificates'):
                tls_context()

    def test_catalogue_passes_verified_context(self):
        with patch('main.urllib.request.urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b'{"status":200,"data":[]}'
            Plugin().api('songs/new/0')
            context = urlopen.call_args.kwargs['context']
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
