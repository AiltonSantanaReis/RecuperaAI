import tempfile
import unittest

from recuperaai.bootstrap import create_engine
from recuperaai.core.exceptions import PermissionDenied, ValidationError
from recuperaai.security.permissions import can, visible_tabs_for_role


class RolePermissionTests(unittest.TestCase):
    def test_visible_tabs_by_profile(self):
        self.assertEqual(
            [tab.key for tab in visible_tabs_for_role('operator')],
            ['dashboard', 'clients', 'invoices', 'analysis'],
        )
        self.assertEqual(
            [tab.key for tab in visible_tabs_for_role('analyst')],
            ['dashboard', 'clients', 'invoices', 'analysis', 'reports'],
        )
        self.assertEqual(
            [tab.key for tab in visible_tabs_for_role('manager')],
            ['dashboard', 'clients', 'invoices', 'analysis', 'reports', 'users', 'backup'],
        )
        self.assertEqual(
            [tab.key for tab in visible_tabs_for_role('admin')],
            ['dashboard', 'clients', 'invoices', 'analysis', 'reports', 'users', 'backup', 'settings'],
        )

    def test_core_permissions_by_profile(self):
        self.assertTrue(can('operator', 'invoices_import'))
        self.assertTrue(can('operator', 'invoices_delete'))
        self.assertTrue(can('operator', 'analysis_run'))
        self.assertFalse(can('operator', 'clients_write'))
        self.assertFalse(can('operator', 'documents_delete'))
        self.assertFalse(can('operator', 'reports_export'))
        self.assertFalse(can('operator', 'users_read'))
        self.assertFalse(can('operator', 'settings_read'))

        self.assertTrue(can('manager', 'users_read'))
        self.assertFalse(can('manager', 'users_write'))
        self.assertFalse(can('manager', 'settings_write'))
        self.assertTrue(can('admin', 'settings_write'))

    def test_backend_enforces_permissions_not_only_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            admin = engine.auth.login('admin', 'Admin@12345')
            engine.tool('users').create_user(admin, 'operador', 'Operador Teste', 'operator', 'Operador@12345')
            operator = engine.auth.login('operador', 'Operador@12345')

            client = engine.tool('clients').create_client(admin, 'Cliente Restrito', '00.000.000/0001-00')
            self.assertEqual(len(engine.tool('clients').list_clients(operator)), 1)

            with self.assertRaises(PermissionDenied):
                engine.tool('clients').create_client(operator, 'Cliente Indevido')
            with self.assertRaises(PermissionDenied):
                engine.tool('reports').export_client_pdf(operator, client.id)
            with self.assertRaises(PermissionDenied):
                engine.tool('users').list_users(operator)
            with self.assertRaises(PermissionDenied):
                engine.tool('settings').get_config(operator)

    def test_manager_can_view_users_but_cannot_create_or_change_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            admin = engine.auth.login('admin', 'Admin@12345')
            engine.tool('users').create_user(admin, 'gestor', 'Gestor Teste', 'manager', 'Gestor@12345')
            manager = engine.auth.login('gestor', 'Gestor@12345')

            self.assertGreaterEqual(len(engine.tool('users').list_users(manager)), 2)
            with self.assertRaises(PermissionDenied):
                engine.tool('users').create_user(manager, 'x', 'X', 'operator', 'Operador@12345')
            with self.assertRaises(PermissionDenied):
                engine.tool('settings').update_api(manager, True, 'https://api.exemplo.local', 'token')

    def test_user_creation_validates_identity_and_duplicate_username(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            admin = engine.auth.login('admin', 'Admin@12345')

            with self.assertRaises(ValidationError):
                engine.tool('users').create_user(admin, '   ', 'Sem Login', 'operator', 'Operador@12345')
            with self.assertRaises(ValidationError):
                engine.tool('users').create_user(admin, 'usuario1', '   ', 'operator', 'Operador@12345')

            engine.tool('users').create_user(admin, 'usuario1', 'Usuário Um', 'operator', 'Operador@12345')
            session = engine.auth.login('usuario1', 'Operador@12345')
            self.assertTrue(session.user.must_change_password)
            with self.assertRaises(ValidationError):
                engine.tool('users').create_user(admin, ' USUARIO1 ', 'Usuário Duplicado', 'operator', 'Operador@12345')


if __name__ == '__main__':
    unittest.main()
