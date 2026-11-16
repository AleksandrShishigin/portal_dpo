from datetime import date
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PreserveLegacyDataTests(TransactionTestCase):
    def test_existing_accounts_and_submitted_application_are_preserved(self):
        executor=MigrationExecutor(connection)
        executor.migrate([('portal','0001_initial')])
        old=executor.loader.project_state([('portal','0001_initial')]).apps
        user=old.get_model('portal','User').objects.create(email='legacy@example.invalid',password='legacy-password-hash',
            first_name='Изменённый профиль',role='student')
        program=old.get_model('portal','Program').objects.create(title='[ТЕСТ] Архивная программа',description='Архив',hours=36,
            starts_on=date(2026,1,1),ends_on=date(2026,2,1))
        req=old.get_model('portal','DocumentRequirement').objects.create(program=program,title='Документ об образовании')
        app=old.get_model('portal','Application').objects.create(student=user,program=program,first_name='Имя в заявке',
            email=user.email,status='accepted',consent_version='legacy-version')
        try:
            executor=MigrationExecutor(connection)
            executor.migrate([('portal','0003_preserve_existing_applications')])
            current=executor.loader.project_state([('portal','0003_preserve_existing_applications')]).apps
            restored=current.get_model('portal','User').objects.get(pk=user.pk)
            restored_app=current.get_model('portal','Application').objects.get(pk=app.pk)
            self.assertEqual(restored.password,'legacy-password-hash')
            self.assertEqual(restored.email,user.email)
            self.assertEqual(restored.role,'student')
            self.assertEqual(restored_app.status,'accepted')
            self.assertEqual(restored_app.first_name,'Имя в заявке')
            self.assertTrue(restored_app.number)
            self.assertTrue(restored_app.submission_snapshot['legacy_reconstructed'])
            self.assertEqual(restored_app.submission_snapshot['student']['first_name'],'Имя в заявке')
            self.assertEqual(restored_app.submission_snapshot['consent']['version'],'legacy-version')
            self.assertTrue(current.get_model('portal','DocumentRequirement').objects.get(pk=req.pk).only_if_graduated)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())


class ContractSignatureMigrationTests(TransactionTestCase):
    def test_existing_registered_contracts_keep_all_original_fields_and_become_unsigned(self):
        previous = ('portal', '0007_application_contract_draft_application_inn_and_more')
        executor = MigrationExecutor(connection)
        executor.migrate([previous])
        old = executor.loader.project_state([previous]).apps
        user = old.get_model('portal', 'User').objects.create(email='signature-legacy@example.invalid', role='operator')
        program = old.get_model('portal', 'Program').objects.create(title='[ТЕСТ] Старые договоры',
            description='Тест миграции', hours=10, starts_on=date(2026, 1, 1), ends_on=date(2026, 2, 1))
        for index in range(2):
            app = old.get_model('portal', 'Application').objects.create(student_id=user.pk, program_id=program.pk,
                number=f'[ТЕСТ]-OLD-APP-{index}', status='accepted', submission_snapshot={'student': {'first_name': 'Архив'}})
            old.get_model('portal', 'Contract').objects.create(application_id=app.pk, number=f'[ТЕСТ]-OLD-CONTRACT-{index}',
                date=date(2026, 1, 2), registered_by_id=user.pk, snapshot={'student': {'first_name': 'Архив'}, 'program': {'title': 'Архив'}},
                template_version='sha256:historical-template', file=f'generated/old-{index}.docx',
                template_file=f'generated/template-{index}.docx', sha256='a' * 64)
        before = list(old.get_model('portal', 'Contract').objects.order_by('pk').values())
        original_fields = list(before[0])
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([('portal', '0008_contract_signature_metadata')])
            current = executor.loader.project_state([('portal', '0008_contract_signature_metadata')]).apps
            restored = current.get_model('portal', 'Contract').objects.order_by('pk')
            self.assertEqual(list(restored.values(*original_fields)), before)
            for contract in restored:
                self.assertEqual(contract.signature_status, 'unsigned')
                self.assertFalse(contract.signed_pdf)
                self.assertIsNone(contract.signed_at)
                self.assertIsNone(contract.signature_verified_at)
            self.assertEqual(restored.filter(signature_status='signed').count(), 0)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
