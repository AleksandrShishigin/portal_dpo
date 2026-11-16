from datetime import date
from io import BytesIO
from unittest.mock import patch
from PIL import Image
from pypdf import PdfWriter
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Application, Document, DocumentRequirement, Event, Program, User
from django.conf import settings
from .document_test_data import PERSON, PROGRAM
CONSENT_VERSION = 'automated-test-v1'


def png(name='document.png'):
    stream = BytesIO()
    Image.new('RGB', (4, 4), 'white').save(stream, format='PNG')
    return SimpleUploadedFile(name, stream.getvalue(), content_type='image/png')


class PortalTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user('student@example.invalid', 'A7-str0ng-test-pass!', **PERSON)
        self.student.refresh_from_db()
        self.other = User.objects.create_user('other@example.invalid', 'A7-str0ng-test-pass!')
        self.operator = User.objects.create_user('operator@example.invalid', 'A7-str0ng-test-pass!', role='operator')
        self.program = Program.objects.create(title='[ТЕСТ] Программа', description='Тест', hours=72, starts_on=date(2027, 1, 1), ends_on=date(2027, 2, 1), **PROGRAM)
        self.requirement = DocumentRequirement.objects.create(program=self.program, title='Тестовый документ')
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def draft(self):
        response = self.client.post('/api/applications/', {'program': self.program.pk}, format='json')
        self.assertEqual(response.status_code, 201)
        return response.data['id']

    def upload(self, pk, file=None, requirement=None):
        return self.client.post(f'/api/applications/{pk}/documents/', {'file': file or png(), 'requirement': requirement or self.requirement.pk}, format='multipart')

    def submit(self, pk):
        return self.client.post(f'/api/applications/{pk}/submit/', {'consent': True, 'consent_version': CONSENT_VERSION}, format='json')

    def review(self):
        pk = self.draft()
        self.assertEqual(self.upload(pk).status_code, 200)
        self.assertEqual(self.submit(pk).status_code, 200)
        return pk

    def test_full_cookie_session_workflow_and_result(self):
        client = APIClient(enforce_csrf_checks=True)
        token = client.get('/api/session/').data['csrfToken']
        registration = client.post('/api/auth/register/', {
            'email': 'NewStudent@Example.invalid', 'first_name': 'Анна', 'last_name': 'Примерова',
            'password': 'X9-uncommon-long-pass!', 'password_confirm': 'X9-uncommon-long-pass!',
            'role': 'operator', 'is_staff': True, 'is_superuser': True,
        }, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(registration.status_code, 201)
        account = User.objects.get(email='newstudent@example.invalid')
        self.assertEqual(account.role, 'student')
        self.assertFalse(account.is_staff or account.is_superuser)
        self.assertTrue(client.cookies['sessionid']['httponly'])
        self.assertEqual(client.get('/api/session/').data['user']['id'], account.pk)
        token = registration.data['csrfToken']
        client.patch('/api/profile/', PERSON, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(client.post('/api/auth/logout/', {}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertIsNone(client.get('/api/session/').data['user'])
        token = client.get('/api/session/').data['csrfToken']
        login = client.post('/api/auth/login/', {'email': 'NEWSTUDENT@example.invalid', 'password': 'X9-uncommon-long-pass!'}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(login.status_code, 200)
        token = login.data['csrfToken']
        headers = {'HTTP_X_CSRFTOKEN': token}
        pk = client.post('/api/applications/', {'program': self.program.pk}, format='json', **headers).data['id']
        self.assertEqual(client.post(f'/api/applications/{pk}/documents/', {'requirement': self.requirement.pk, 'file': png()}, format='multipart', **headers).status_code, 200)
        submitted = client.post(f'/api/applications/{pk}/submit/', {'consent': True, 'consent_version': CONSENT_VERSION}, format='json', **headers)
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data['status'], 'review')
        self.assertTrue(submitted.data['consent_at'])
        operator = APIClient(enforce_csrf_checks=True)
        token_op = operator.get('/api/session/').data['csrfToken']
        login_op = operator.post('/api/auth/login/', {'email': self.operator.email, 'password': 'A7-str0ng-test-pass!'}, format='json', HTTP_X_CSRFTOKEN=token_op)
        decision = operator.post(f'/api/applications/{pk}/decision/', {'decision': 'accepted'}, format='json', HTTP_X_CSRFTOKEN=login_op.data['csrfToken'])
        self.assertEqual(decision.status_code, 200)
        result = client.get(f'/api/applications/{pk}/').data
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual([e['action'] for e in result['events']], ['created', 'submitted', 'accepted'])
        download = client.get(result['documents'][0]['download_url'])
        self.assertEqual(download.status_code, 200)
        self.assertTrue(b''.join(download.streaming_content))

    def test_csrf_required_for_login_registration_and_session_mutations(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/auth/login/', {}, format='json').status_code, 403)
        self.assertEqual(client.post('/api/auth/register/', {}, format='json').status_code, 403)
        client.force_login(self.student)
        self.assertEqual(client.post('/api/applications/', {'program': self.program.pk}, format='json').status_code, 403)
        self.assertEqual(client.post('/api/auth/logout/', {}, format='json').status_code, 403)

    def test_weak_password_and_confirmation_rejected(self):
        client = APIClient()
        data = {'email':'new@example.invalid', 'first_name':'Имя', 'last_name':'Фамилия', 'password':'12345678', 'password_confirm':'12345678'}
        response = client.post('/api/auth/register/', data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data)
        data.update(password='X9-uncommon-long-pass!')
        self.assertIn('password_confirm', client.post('/api/auth/register/', data, format='json').data)

    def test_case_insensitive_email_registration_and_database_constraint(self):
        client = APIClient()
        response = client.post('/api/auth/register/', {'email': 'STUDENT@example.invalid', 'first_name':'Имя', 'last_name':'Фамилия', 'password':'X9-uncommon-long-pass!', 'password_confirm':'X9-uncommon-long-pass!'}, format='json')
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email='STUDENT@example.invalid')])

    def test_profile_cannot_escalate_privileges(self):
        response = self.client.patch('/api/profile/', {'role':'operator', 'is_staff':True, 'is_superuser':True, 'first_name':'Новое'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, 'student')
        self.assertFalse(self.student.is_staff or self.student.is_superuser)
        self.assertEqual(self.student.first_name, 'Иван')
        self.assertEqual(self.client.patch('/api/profile/', {'email': 'OTHER@example.invalid'}, format='json').status_code, 400)

    def test_draft_prefill_and_save(self):
        pk = self.draft()
        response = self.client.get(f'/api/applications/{pk}/')
        self.assertEqual(response.data['first_name'], self.student.first_name)
        self.assertEqual(self.client.patch(f'/api/applications/{pk}/', {'first_name':'Другое'}, format='json').status_code, 200)
        self.assertEqual(Application.objects.get(pk=pk).first_name, 'Другое')

    def test_invalid_submission_stays_draft(self):
        pk = self.draft()
        self.client.patch(f'/api/applications/{pk}/', {'first_name':''}, format='json')
        response = self.client.post(f'/api/applications/{pk}/submit/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        for key in ['first_name','documents','consent','consent_version']:
            self.assertIn(key, response.data)
        app = Application.objects.get(pk=pk)
        self.assertEqual(app.status, 'draft')
        self.assertIsNone(app.consent_at)
        self.assertEqual(app.events.count(), 1)

    def test_other_student_cannot_access_application_or_document(self):
        pk = self.draft()
        self.upload(pk)
        document = Document.objects.get(application_id=pk)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/applications/').data, [])
        for url in [f'/api/applications/{pk}/', f'/api/documents/{document.pk}/download/']:
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(f'/api/applications/{pk}/', {'first_name':'Чужой'}, format='json').status_code, 404)
        self.assertEqual(self.upload(pk).status_code, 404)
        self.assertEqual(self.submit(pk).status_code, 404)

    def test_operator_cannot_access_drafts_or_their_documents(self):
        pk = self.draft()
        self.upload(pk)
        document = Document.objects.get(application_id=pk)
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.get('/api/applications/').data, [])
        self.assertEqual(self.client.get(f'/api/applications/{pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/documents/{document.pk}/download/').status_code, 404)
        self.assertEqual(self.client.post(f'/api/applications/{pk}/decision/', {'decision':'accepted'}, format='json').status_code, 404)
        self.assertEqual(self.client.post('/api/applications/', {'program':self.program.pk}, format='json').status_code, 403)

    def test_student_cannot_decide(self):
        pk = self.review()
        self.assertEqual(self.client.post(f'/api/applications/{pk}/decision/', {'decision':'accepted'}, format='json').status_code, 403)

    def test_review_cannot_edit_upload_or_resubmit(self):
        pk = self.review()
        self.assertEqual(self.client.patch(f'/api/applications/{pk}/', {'first_name':'Изменение'}, format='json').status_code, 400)
        self.assertEqual(self.upload(pk).status_code, 400)
        self.assertEqual(self.submit(pk).status_code, 400)

    def test_rejection_requires_reason_and_cannot_be_repeated(self):
        pk = self.review()
        self.client.force_authenticate(self.operator)
        url = f'/api/applications/{pk}/decision/'
        self.assertEqual(self.client.post(url, {'decision':'rejected', 'reason':'  '}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {'decision':'draft'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {'decision':'rejected', 'reason':'Нечитаемый тестовый документ'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(url, {'decision':'accepted'}, format='json').status_code, 400)
        self.client.force_authenticate(self.student)
        result = self.client.get(f'/api/applications/{pk}/').data
        self.assertEqual(result['decision_reason'], 'Нечитаемый тестовый документ')
        self.assertEqual(self.submit(pk).status_code, 400)
        self.assertEqual(self.client.patch(f'/api/applications/{pk}/', {'email':'change@example.invalid'}, format='json').status_code, 400)
        self.assertNotEqual(self.draft(), pk)

    def test_acceptance_cannot_be_repeated(self):
        pk = self.review()
        self.client.force_authenticate(self.operator)
        for expected in [200, 400]:
            self.assertEqual(self.client.post(f'/api/applications/{pk}/decision/', {'decision':'accepted'}, format='json').status_code, expected)
        self.assertEqual(Event.objects.filter(application_id=pk, action='accepted').count(), 1)

    def test_file_validation_and_private_paths(self):
        pk = self.draft()
        bad_files = [SimpleUploadedFile('fake.pdf', b'not a pdf'), SimpleUploadedFile('fake.png', b'not a png'), png('wrong.jpg'), png('blocked.exe')]
        for file in bad_files:
            with self.subTest(name=file.name):
                self.assertEqual(self.upload(pk, file).status_code, 400)
        self.assertEqual(self.upload(pk, png('../../private-name.png')).status_code, 200)
        document = Document.objects.get(application_id=pk)
        self.assertNotIn('private-name', document.file.name)
        self.assertNotIn('..', document.file.name)
        self.assertEqual(self.client.get('/private-media/' + document.file.name).status_code, 404)
        response = self.client.get(f'/api/documents/{document.pk}/download/')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertTrue(b''.join(response.streaming_content))

    def test_pdf_and_jpeg_allowed(self):
        pk = self.draft()
        output = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(output)
        self.assertEqual(self.upload(pk, SimpleUploadedFile('test.pdf', output.getvalue())).status_code, 200)
        output = BytesIO()
        Image.new('RGB', (4,4)).save(output, format='JPEG')
        self.assertEqual(self.upload(pk, SimpleUploadedFile('test.jpeg', output.getvalue())).status_code, 200)
        self.assertEqual(Document.objects.filter(application_id=pk).count(), 1)

    def test_oversize_empty_and_wrong_requirement_rejected(self):
        pk = self.draft()
        self.assertEqual(self.upload(pk, SimpleUploadedFile('large.png', b'0' * (10*1024*1024+1))).status_code, 400)
        self.assertEqual(self.upload(pk, SimpleUploadedFile('empty.pdf', b'')).status_code, 400)
        self.assertEqual(self.upload(pk, requirement=999999).status_code, 404)
        other = Program.objects.create(title='Other', hours=10, starts_on=date(2027,1,1), ends_on=date(2027,2,1))
        req = DocumentRequirement.objects.create(program=other, title='Other')
        self.assertEqual(self.upload(pk, requirement=req.pk).status_code, 404)

    def test_server_ignores_client_status_and_owner(self):
        pk = self.draft()
        response = self.client.patch(f'/api/applications/{pk}/', {'status':'accepted', 'student':self.other.pk, 'consent_at':'2026-01-01', 'consent_version':'forged'}, format='json')
        self.assertEqual(response.status_code, 200)
        app = Application.objects.get(pk=pk)
        self.assertEqual(app.status, 'draft')
        self.assertEqual(app.student_id, self.student.pk)
        self.assertEqual(app.consent_version, '')

    def test_operator_search_and_filters(self):
        pk = self.review()
        self.draft()
        self.client.force_authenticate(self.operator)
        result = self.client.get('/api/applications/', {'search':'Тестов', 'status':'review'}).data
        self.assertEqual([r['id'] for r in result], [pk])
        self.assertEqual(self.client.get('/api/applications/', {'status':'draft'}).data, [])

    def test_unauthenticated_access_denied(self):
        pk = self.review()
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/applications/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/applications/{pk}/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/documents/{Document.objects.get(application_id=pk).pk}/download/').status_code, 403)

    def test_seed_programs_idempotent(self):
        call_command('seed_programs', verbosity=0)
        count = Program.objects.count()
        call_command('seed_programs', verbosity=0)
        self.assertEqual(Program.objects.count(), count)
        self.assertEqual(Program.objects.filter(title__startswith='[ТЕСТ]').count(), 4)

    @patch('portal.management.commands.create_operator.getpass', return_value='X9-uncommon-long-pass!')
    @patch('builtins.input', side_effect=['newoperator@example.invalid','Оператор','Тестовый'])
    def test_create_operator_without_admin_privileges(self, mocked_input, mocked_password):
        call_command('create_operator')
        operator = User.objects.get(email='newoperator@example.invalid')
        self.assertEqual(operator.role, 'operator')
        self.assertFalse(operator.is_superuser or operator.is_staff)
        self.assertTrue(operator.check_password('X9-uncommon-long-pass!'))
