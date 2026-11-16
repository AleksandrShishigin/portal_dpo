from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import IntegrityError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from .models import Application, Document, Event, ProfileDocument
from .tests import PortalTests, png


class ProfileDocumentTests(TestCase):
    setUp = PortalTests.setUp
    draft = PortalTests.draft
    submit = PortalTests.submit

    def test_session_exposes_current_api_contract(self):
        self.assertEqual(self.client.get('/api/session/').data['apiVersion'], 2)

    def test_prototype_submission_requires_checkbox_and_operator_can_accept_or_reject(self):
        from config.prototype_consent import PROTOTYPE_CONSENT_TEXT, PROTOTYPE_CONSENT_VERSION
        with override_settings(PROTOTYPE_MODE=True, CONSENT_TEXT=PROTOTYPE_CONSENT_TEXT,
                               CONSENT_VERSION=PROTOTYPE_CONSENT_VERSION):
            consent = self.client.get('/api/session/').data['consent']
            self.assertEqual(consent['kind'], 'prototype')
            self.assertTrue(consent['available'])
            self.profile_upload()
            first = self.draft()
            endpoint = f'/api/applications/{first}/submit/'
            self.assertEqual(self.client.post(endpoint, {'consent': False,
                'consent_version': consent['version']}, format='json').status_code, 400)
            self.assertEqual(self.client.post(endpoint, {'consent': True,
                'consent_version': 'old'}, format='json').status_code, 400)
            result = self.client.post(endpoint, {'consent': True,
                'consent_version': consent['version']}, format='json')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data['submission_snapshot']['consent']['text'], PROTOTYPE_CONSENT_TEXT)
            self.client.force_authenticate(self.operator)
            self.assertEqual(self.client.post(f'/api/applications/{first}/decision/',
                {'decision': 'rejected', 'reason': 'Отказ при проверке прототипа'}, format='json').status_code, 200)
            self.client.force_authenticate(self.student)
            second = self.draft()
            self.assertEqual(self.client.post(f'/api/applications/{second}/submit/',
                {'consent': True, 'consent_version': consent['version']}, format='json').status_code, 200)
            self.client.force_authenticate(self.operator)
            self.assertEqual(self.client.post(f'/api/applications/{second}/decision/',
                {'decision': 'accepted'}, format='json').status_code, 200)

    def profile_upload(self, name='profile.png', title=None):
        result = self.client.post('/api/profile/documents/',
            {'file': png(name), 'title': title or self.requirement.title}, format='multipart')
        self.assertEqual(result.status_code, 201)
        return result.data

    def attach(self, app, source, requirement=None):
        return self.client.post(f'/api/applications/{app}/profile-document/',
            {'document': source, 'requirement': requirement or self.requirement.pk}, format='json')

    def test_new_draft_copies_all_profile_fields_and_latest_matching_file(self):
        from .fields import PERSONAL_FIELDS
        self.student.phone = '+79991234567'
        self.student.birth_date = '2000-01-01'
        self.student.institution = 'Вымышленное учреждение'
        self.student.education_level = 'bachelor'
        self.student.education_document_received = True
        self.student.education_document_name = 'Диплом'
        self.student.education_document_number = 'ТЕСТ-001'
        self.student.education_document_series = 'ТЕСТ'
        self.student.education_document_date = '2024-01-01'
        self.student.save()
        self.student.refresh_from_db()
        self.profile_upload('old.png')
        latest = self.profile_upload('new.png', '  ' + self.requirement.title.upper() + '  ')
        self.profile_upload('unrelated.png', 'Другой документ')
        app = Application.objects.get(pk=self.draft())
        for field in PERSONAL_FIELDS:
            self.assertEqual(getattr(app, field), getattr(self.student, field))
        document = app.documents.get()
        source = ProfileDocument.objects.get(pk=latest['id'])
        self.assertEqual(document.source_profile_document, source.pk)
        self.assertNotEqual(document.file.name, source.file.name)
        self.assertEqual(document.sha256, source.sha256)
        self.assertEqual(self.client.get(f'/api/applications/{app.pk}/').data['missing_documents'], [])

    def test_opening_draft_does_not_overwrite_fields_or_file_after_profile_changes(self):
        source = self.profile_upload()
        app = self.draft()
        self.client.patch(f'/api/applications/{app}/', {'first_name': 'Другое имя', 'phone': ''}, format='json')
        before = self.client.get(f'/api/applications/{app}/').data
        self.client.patch('/api/profile/', {'first_name': 'Новое имя', 'phone': '+79991234567'}, format='json')
        self.profile_upload('new-version.png')
        after = self.client.get(f'/api/applications/{app}/').data
        # Event actor display names follow the current account; application content does not.
        for key in ('first_name', 'phone', 'documents', 'submission_snapshot', 'updated_at'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(after['documents'][0]['source_profile_document'], source['id'])

    def test_can_choose_other_profile_version_only_in_draft(self):
        first = self.profile_upload('first.png')
        self.profile_upload('second.png')
        app = self.draft()
        result = self.attach(app, first['id'])
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['documents'][0]['original_name'], 'first.png')
        self.assertEqual(self.submit(app).status_code, 200)
        self.assertEqual(self.attach(app, first['id']).status_code, 400)

    def test_profile_deletion_and_replacement_preserve_submitted_bytes_and_snapshot(self):
        source = self.profile_upload()
        source_path = ProfileDocument.objects.get(pk=source['id']).file.name
        app = self.draft()
        self.assertEqual(self.submit(app).status_code, 200)
        before = deepcopy(Application.objects.get(pk=app).submission_snapshot)
        manifest = self.client.get(f'/api/applications/{app}/').data['documents']
        document = Document.objects.get(application_id=app)
        content = document.file.read()
        document.file.close()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(f"/api/profile/documents/{source['id']}/").status_code, 200)
        self.assertFalse(default_storage.exists(source_path))
        self.profile_upload('replacement.png')
        self.client.patch('/api/profile/', {'first_name': 'Новое имя'}, format='json')
        current = Application.objects.get(pk=app)
        self.assertEqual(current.submission_snapshot, before)
        self.assertEqual(current.first_name, 'Иван')
        self.assertEqual(self.client.get(f'/api/applications/{app}/').data['documents'], manifest)
        with document.file.open('rb') as file:
            self.assertEqual(file.read(), content)

    def test_profile_files_are_private_and_operator_cannot_use_student_endpoints(self):
        source = self.profile_upload()
        app = self.draft()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/profile/documents/').data, [])
        self.assertEqual(self.client.get(source['preview_url']).status_code, 404)
        self.assertEqual(self.client.get(source['download_url']).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/profile/documents/{source['id']}/").status_code, 404)
        self.assertEqual(self.attach(app, source['id']).status_code, 404)
        other_app = self.draft()
        self.assertEqual(self.attach(other_app, source['id']).status_code, 404)
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.get('/api/profile/documents/').status_code, 403)
        self.assertEqual(self.client.post('/api/profile/documents/', {}, format='json').status_code, 403)
        self.assertEqual(self.client.get(source['preview_url']).status_code, 403)
        self.assertEqual(self.attach(app, source['id']).status_code, 403)

    def test_profile_role_shapes_and_server_side_employee_field_rejection(self):
        self.operator.institution = 'Архивные данные сохраняются'
        self.operator.save()
        self.client.force_authenticate(self.operator)
        expected = {'id', 'role', 'last_name', 'first_name', 'patronymic', 'email', 'phone'}
        self.assertEqual(set(self.client.get('/api/profile/').data), expected)
        self.assertEqual(set(self.client.get('/api/session/').data['user']), expected)
        for payload in [{'institution': 'Подмена'}, {'education_level': 'bachelor'}, {'role': 'student'}]:
            self.assertEqual(self.client.patch('/api/profile/', payload, format='json').status_code, 400)
        result = self.client.patch('/api/profile/', {'first_name': 'Сотрудник', 'phone': '+79991234567'}, format='json')
        self.assertEqual(result.status_code, 200)
        self.operator.refresh_from_db()
        self.assertEqual(self.operator.institution, 'Архивные данные сохраняются')
        self.client.force_authenticate(self.student)
        self.assertIn('education_level', self.client.get('/api/profile/').data)

    def test_mismatched_document_never_autofilled_or_explicitly_attached(self):
        source = self.profile_upload(title='Совсем другой документ')
        app = self.draft()
        result = self.client.get(f'/api/applications/{app}/').data
        self.assertEqual(result['documents'], [])
        self.assertEqual(result['missing_documents'], [{'id': self.requirement.pk, 'title': self.requirement.title}])
        self.assertEqual(self.attach(app, source['id']).status_code, 400)

    def test_missing_or_corrupted_profile_file_does_not_prevent_draft_but_cannot_submit(self):
        source = self.profile_upload()
        profile_file = ProfileDocument.objects.get(pk=source['id'])
        with profile_file.file.open('wb') as file:
            file.write(b'broken')
        app = self.draft()
        self.assertFalse(Document.objects.filter(application_id=app).exists())
        self.assertEqual(self.attach(app, source['id']).status_code, 400)
        self.assertIn('documents', self.submit(app).data)

    def test_automatic_copy_rollback_cleans_new_files_and_preserves_profile(self):
        self.profile_upload()
        before = {p for p in Path(settings.MEDIA_ROOT).rglob('*') if p.is_file()}
        with self.captureOnCommitCallbacks(execute=True):
            with patch.object(Event.objects, 'create', side_effect=IntegrityError('simulated rollback')):
                with self.assertRaises(IntegrityError):
                    self.draft()
        self.assertFalse(Application.objects.exists())
        self.assertEqual({p for p in Path(settings.MEDIA_ROOT).rglob('*') if p.is_file()}, before)

    def test_profile_document_upload_still_requires_csrf_and_file_validation(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.student)
        self.assertEqual(client.post('/api/profile/documents/', {'title': 'Файл', 'file': png()}, format='multipart').status_code, 403)
        self.assertEqual(self.client.post('/api/profile/documents/', {'title': 'Файл'}, format='multipart').status_code, 400)

    def test_availability_reports_precise_reason_and_keeps_server_consent_gate(self):
        self.profile_upload()
        app = self.draft()
        with override_settings(CONSENT_VERSION='', CONSENT_TEXT=''):
            programs = self.client.get('/api/programs/').data
            self.assertEqual(programs[0]['submission_availability']['code'], 'consent_unpublished')
            self.assertTrue(programs[0]['submission_availability']['next_step'])
            self.assertIn('availability', self.submit(app).data)
        self.program.is_active = False
        self.program.save()
        data = self.client.get(f'/api/applications/{app}/').data
        self.assertEqual(data['submission_availability']['code'], 'program_inactive')
        self.assertEqual(self.submit(app).status_code, 400)
