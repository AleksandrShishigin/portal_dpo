from copy import deepcopy
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from xml.dom import minidom
from zipfile import ZipFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient
from .document_test_data import PERSON, PROGRAM, REGISTRATION
from .fields import personal_data
from .generated_documents import (build_contract, contract_defaults, contract_number, render,
                                  template_bytes, values_for, build_statement)
from .models import Application, Contract, Statement, User, Program, Event
from .services import program_data


def paragraphs(content):
    with ZipFile(BytesIO(content)) as z:
        dom = minidom.parseString(z.read('word/document.xml'))
        return [''.join(t.firstChild.data if t.firstChild else '' for t in p.getElementsByTagName('w:t'))
                for p in dom.getElementsByTagName('w:p')]


class GeneratedDocumentTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user('docs@example.invalid', **PERSON)
        self.student.refresh_from_db()
        self.operator = User.objects.create_user('operator-docs@example.invalid', role='operator')
        self.other = User.objects.create_user('other-docs@example.invalid')
        self.program = Program.objects.create(title='[ТЕСТ] Документы', description='Вымышленная программа',
            hours=100, starts_on=date(2026, 9, 1), ends_on=date(2028, 9, 1), **PROGRAM)
        self.client = APIClient(); self.client.force_authenticate(self.student)
        self.app = Application.objects.create(student=self.student, program=self.program, **personal_data(self.student))

    def submit(self):
        return self.client.post(f'/api/applications/{self.app.pk}/submit/',
            {'consent': True, 'consent_version': 'automated-test-v1'}, format='json')

    def accepted(self):
        self.assertEqual(self.submit().status_code, 200)
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.post(f'/api/applications/{self.app.pk}/decision/', {'decision': 'accepted'}, format='json').status_code, 200)

    def draft(self, data=None):
        return self.client.patch(f'/api/applications/{self.app.pk}/contract/', data or REGISTRATION, format='json')

    def register(self):
        return self.client.post(f'/api/applications/{self.app.pk}/contract/register/', {}, format='json')

    def download(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        # Django's streaming test wrapper closes the response itself. A second
        # close emits request_finished again and closes a TestCase transaction.
        return b''.join(r.streaming_content)

    def test_statement_contains_profile_inn_and_all_fields_and_preserves_template_parts(self):
        data, template, content = build_statement(self.app)
        text = '\n'.join(paragraphs(content))
        for value in [PERSON['inn'], PERSON['snils'], PERSON['registration_address'], PERSON['residential_address'],
                      PERSON['passport_issued_by'], PERSON['institution'], self.program.title, self.student.email]:
            self.assertIn(value, text)
        self.assertEqual(text.count('Тестов Иван Вымышленный'), 3)
        for placeholder in ['{{', 'Фамилия Имя Отчество', 'телефон, e-mail', 'название программы', 'ФИО сотрудника или данные QR-кода']:
            self.assertNotIn(placeholder, text)
        with ZipFile(BytesIO(template)) as a, ZipFile(BytesIO(content)) as b:
            for name in a.namelist():
                if name != 'word/document.xml':
                    self.assertEqual(a.read(name), b.read(name))

    def test_statement_frozen_bytes_snapshot_and_template_survive_profile_and_template_updates(self):
        self.assertEqual(self.submit().status_code, 200)
        self.app.refresh_from_db()
        artifact = self.app.statement
        url = f'/api/applications/{self.app.pk}/statement/'
        first = self.download(url)
        self.client.patch('/api/profile/', {'first_name': 'Новое имя', 'inn': '111111111111'}, format='json')
        self.program.title = 'Новое название'; self.program.save()
        with patch('portal.generated_documents.template_bytes', side_effect=AssertionError('Must not regenerate')):
            self.assertEqual(first, self.download(url))
        self.assertEqual(artifact.snapshot['student']['inn'], PERSON['inn'])
        with artifact.template_file.open('rb') as saved:
            self.assertEqual(artifact.template_version, 'sha256:' + __import__('hashlib').sha256(saved.read()).hexdigest())
        with artifact.file.open('rb') as saved:
            self.assertEqual(saved.read(), first)

    def test_statement_requires_document_fields_but_incomplete_profile_and_draft_are_allowed(self):
        self.client.patch('/api/profile/', {'inn': '', 'passport_number': ''}, format='json')
        self.client.patch(f'/api/applications/{self.app.pk}/', {'inn': '', 'passport_number': ''}, format='json')
        self.assertEqual(self.client.get('/api/profile/').status_code, 200)
        result = self.submit()
        self.assertEqual(result.status_code, 400)
        self.assertIn('inn', result.data); self.assertIn('passport_number', result.data)
        self.app.refresh_from_db(); self.assertEqual(self.app.status, 'draft')
        self.assertFalse(Statement.objects.exists())

    def test_diploma_is_only_required_for_graduates(self):
        self.app.education_document_received = True; self.app.save()
        result = self.submit(); self.assertEqual(result.status_code, 400)
        self.assertIn('education_document_number', result.data)
        self.app.education_document_name = 'Диплом'; self.app.education_document_number = '000001'
        self.app.education_document_date = '2023-06-01'; self.app.save()
        self.assertEqual(self.submit().status_code, 200)

    def test_legacy_statement_warns_and_never_falls_back_to_profile(self):
        self.app.status = 'accepted'; self.app.submission_snapshot = {'student': {'first_name': 'Архив'}, 'legacy_reconstructed': True}; self.app.save()
        result = self.client.get(f'/api/applications/{self.app.pk}/statement/')
        self.assertEqual(result.status_code, 409); self.assertIn('профиля', str(result.data))
        self.client.force_authenticate(self.operator)
        draft = self.client.get(f'/api/applications/{self.app.pk}/contract/').data
        self.assertTrue(draft['warning']); self.assertNotIn('inn', draft['data']['student'])
        self.assertIn('passport_number', draft['errors'])

    def test_registration_and_download_are_idempotent_and_frozen(self):
        self.accepted(); draft = self.draft()
        self.assertEqual(draft.status_code, 200); self.assertEqual(draft.data['errors'], {})
        self.assertEqual(draft.data['preview_number'], '0321-2О10/1-26/28-1')
        first = self.register(); self.assertEqual(first.status_code, 201)
        second = self.register(); self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['id'], second.data['id']); self.assertEqual(Contract.objects.count(), 1)
        content = self.download(first.data['download_url'])
        self.student.first_name = 'Изменено'; self.student.save()
        self.program.title = 'Изменено'; self.program.save()
        with patch('portal.generated_documents.template_bytes', side_effect=AssertionError('Must not regenerate')):
            self.assertEqual(content, self.download(second.data['download_url']))
            self.assertEqual(self.register().status_code, 200)
        self.assertEqual(self.draft().status_code, 400)
        registry = self.client.get('/api/contracts/').data['results']
        self.assertEqual(registry[0]['program_title'], '[ТЕСТ] Документы')
        self.assertEqual(Event.objects.filter(action='contract_registered').count(), 1)

    def test_contract_number_is_in_first_paragraph_and_university_inn_untouched(self):
        self.accepted(); self.draft()
        response = self.register(); content = self.download(response.data['download_url'])
        text = paragraphs(content)
        self.assertEqual(text[0], 'ДОГОВОР № 0321-2О10/1-26/28-1')
        self.assertIn('ИНН: 7719455553', text)
        self.assertNotIn(PERSON['inn'], '\n'.join(text))
        for value in [PERSON['registration_address'], PERSON['residential_address'], PERSON['snils'], self.student.email, '21.01.2026 г.']:
            self.assertIn(value, '\n'.join(text))
        self.assertEqual('\n'.join(text).count('Тестов Иван Вымышленный'), 3)
        for placeholder in ['{{', 'Фамилия Имя Отчество', 'Ф. И. О. (полностью)', '___________ г.']:
            self.assertNotIn(placeholder, '\n'.join(text))

    def test_contract_learner_inn_only_when_template_has_explicit_token(self):
        data = {**contract_defaults(self.app), **REGISTRATION}
        template = template_bytes('contract')
        with ZipFile(BytesIO(template)) as source:
            out = BytesIO()
            with ZipFile(out, 'w') as target:
                for info in source.infolist():
                    raw = source.read(info.filename)
                    if info.filename == 'word/document.xml':
                        raw = raw.replace(b'{{email}}', 'ИНН обучающегося: {{inn}}; {{email}}'.encode())
                    target.writestr(info, raw)
        _, content = build_contract(data, out.getvalue())
        self.assertIn('ИНН обучающегося: ' + PERSON['inn'], '\n'.join(paragraphs(content)))
        self.assertIn('ИНН: 7719455553', paragraphs(content))
        del data['student']['inn']
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError) as missing:
            build_contract(data, out.getvalue())
        self.assertIn('inn', missing.exception.detail)

    def test_number_matches_html_for_all_serial_lengths_and_forms_and_rejects_latin_codes(self):
        for serial, expected in [(0, '0'), (1, '1'), (12, '12'), (321, '0321'), (1234, '1234'), (12345, '12345')]:
            for form in ['1', '2', '3']:
                data = {**REGISTRATION, 'sequence': serial, 'program': {'study_form': form}}
                self.assertEqual(contract_number(data), f'{expected}-2О10/{form}-26/28-1')
        self.accepted()
        self.assertEqual(self.draft({**REGISTRATION, 'number_code': 'O'}).data['errors']['number_code'][0].code, 'invalid_choice')
        self.assertEqual(self.register().status_code, 400)

    def test_missing_contract_details_and_bad_dates_do_not_register(self):
        self.accepted()
        self.assertEqual(self.register().status_code, 400)
        self.assertFalse(Contract.objects.exists())
        self.assertEqual(self.draft({**REGISTRATION, 'program': {'hours': 0}}).status_code, 200)
        self.assertEqual(self.register().status_code, 400)
        self.assertEqual(self.draft({'student': {'passport_issued_on': '2999-01-01'}}).status_code, 400)

    def test_permissions_for_statement_contract_draft_registry_and_download(self):
        self.accepted(); self.draft(); registered = self.register()
        statement = f'/api/applications/{self.app.pk}/statement/'
        contract = registered.data['download_url']; draft = f'/api/applications/{self.app.pk}/contract/'
        self.client.force_authenticate(self.other)
        for url in [statement, contract]: self.assertEqual(self.client.get(url).status_code, 404)
        for url in [draft, '/api/contracts/']: self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.register().status_code, 403)
        self.client.force_authenticate(self.student)
        self.download(statement); self.download(contract)
        self.assertEqual(self.client.get(draft).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(statement).status_code, 403)
        self.assertEqual(self.client.get(contract).status_code, 403)

    def test_rejected_and_unsubmitted_applications_cannot_have_contracts(self):
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.register().status_code, 404)
        for status in ['review', 'rejected']:
            self.app.status = status; self.app.save()
            self.assertEqual(self.register().status_code, 400)

    def test_failed_statement_storage_rolls_back_submission(self):
        with patch('django.core.files.storage.filesystem.FileSystemStorage._save', side_effect=OSError('Disk full')):
            self.assertEqual(self.submit().status_code, 400)
        self.app.refresh_from_db(); self.assertEqual(self.app.status, 'draft')
        self.assertFalse(Statement.objects.exists()); self.assertFalse(Event.objects.filter(action='submitted').exists())

    def test_failed_contract_render_or_file_save_does_not_register(self):
        self.accepted(); self.draft()
        for target in ['portal.generated_documents.render', 'django.core.files.storage.filesystem.FileSystemStorage._save']:
            with patch(target, side_effect=OSError('Failed')):
                self.assertEqual(self.register().status_code, 400)
            self.assertFalse(Contract.objects.exists())
            self.assertFalse(Event.objects.filter(action='contract_registered').exists())

    def test_long_addresses_are_preserved_and_rows_can_expand(self):
        address = (PERSON['registration_address'] + ', ') * 8
        self.app.registration_address = self.app.residential_address = address; self.app.save()
        _, _, statement = build_statement(self.app)
        data = {**contract_defaults(self.app), **REGISTRATION}
        _, contract = build_contract(data, template_bytes('contract'))
        for content in [statement, contract]:
            self.assertEqual('\n'.join(paragraphs(content)).count(address), 2)
            with ZipFile(BytesIO(content)) as z: self.assertNotIn(b'w:hRule="exact"', z.read('word/document.xml'))

    def test_missing_saved_file_is_not_regenerated(self):
        self.assertEqual(self.submit().status_code, 200)
        artifact = Statement.objects.get(application=self.app)
        default_storage.delete(artifact.file.name)
        self.assertEqual(self.client.get(f'/api/applications/{self.app.pk}/statement/').status_code, 404)

    def test_operator_can_configure_document_program_fields_without_changing_sent_snapshot(self):
        self.assertEqual(self.submit().status_code, 200)
        endpoint = f'/api/programs/{self.program.pk}/document-settings/'
        self.assertEqual(self.client.patch(endpoint, {'program_kind': PROGRAM['program_kind']}, format='json').status_code, 403)
        self.client.force_authenticate(self.operator)
        result = self.client.patch(endpoint, {'program_kind': 'профессиональной переподготовки', 'study_form': '3'}, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['study_form'], '3')
        self.app.refresh_from_db()
        self.assertEqual(self.app.submission_snapshot['program']['program_kind'], PROGRAM['program_kind'])
        self.assertEqual(self.client.patch(endpoint, {'study_form': '4'}, format='json').status_code, 400)

    def test_partial_storage_failure_removes_allocated_files_and_no_contract_is_registered(self):
        self.accepted(); self.draft()
        real_save = default_storage.save
        allocated = []
        def failing_save(name, value, **kwargs):
            if allocated:
                raise OSError('Disk full on second write')
            name = real_save(name, value, **kwargs); allocated.append(name); return name
        with self.captureOnCommitCallbacks(execute=True):
            with patch.object(default_storage, 'save', side_effect=failing_save):
                self.assertEqual(self.register().status_code, 400)
        self.assertFalse(Contract.objects.exists())
        self.assertFalse(default_storage.exists(allocated[0]))
