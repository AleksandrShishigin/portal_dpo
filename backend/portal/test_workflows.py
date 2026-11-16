from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
import re
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from .models import Application, Document, DocumentRequirement, Event, Notification, PendingFileDeletion, Program, User
from .services import queue_file_deletion
from .tests import PortalTests, png


class ExtendedWorkflowTests(TestCase):
    draft = PortalTests.draft
    upload = PortalTests.upload
    submit = PortalTests.submit
    review = PortalTests.review

    def setUp(self):
        cache.clear()
        PortalTests.setUp(self)

    def test_extended_profile_validation_and_immutable_login_email(self):
        values = {'birth_date':'2000-02-29','phone':'+7 (999) 123-45-67','institution':'Учебное заведение',
            'education_level':'studying','education_document_received':False}
        result = self.client.patch('/api/profile/', values, format='json')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.data['birth_date'],'2000-02-29')
        self.assertEqual(self.client.get('/api/profile/').data['phone'],values['phone'])
        for fields in [{'birth_date':'2999-01-01'},{'phone':'bad'},{'education_document_date':'1999-01-01'}, {'education_level':'invented'}]:
            self.assertEqual(self.client.patch('/api/profile/',fields,format='json').status_code,400)
        self.assertEqual(self.client.patch('/api/profile/',{'email':'new@example.invalid'},format='json').status_code,400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.email,'student@example.invalid')

    def test_short_registration_does_not_require_extended_profile(self):
        result = APIClient().post('/api/auth/register/',{'email':'short@example.invalid','last_name':'Тестов','first_name':'Имя',
            'password':'X9-very-long-pass!','password_confirm':'X9-very-long-pass!','birth_date':'invalid',
            'role':'operator','is_staff':True,'is_superuser':True},format='json')
        self.assertEqual(result.status_code,201)
        user = User.objects.get(email='short@example.invalid')
        self.assertIsNone(user.birth_date)
        self.assertEqual(user.role,'student')
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_incomplete_draft_and_explicit_profile_refresh(self):
        self.student.phone='+79991234567'
        self.student.save()
        pk=self.draft()
        self.assertEqual(self.client.get(f'/api/applications/{pk}/').data['phone'],self.student.phone)
        result=self.client.patch(f'/api/applications/{pk}/',{'first_name':'','email':'','birth_date':None,'phone':''},format='json')
        self.assertEqual(result.status_code,200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name,'Иван')
        result=self.client.post(f'/api/applications/{pk}/refresh-profile/',{},format='json')
        self.assertEqual(result.data['first_name'],'Иван')
        self.assertEqual(result.data['phone'],self.student.phone)

    def test_program_required_fields_and_no_diploma_for_current_student(self):
        self.program.required_fields=['last_name','first_name','email','birth_date','phone','institution','education_level','education_document_name','education_document_number','education_document_date']
        self.program.save()
        self.requirement.only_if_graduated=True
        self.requirement.save()
        pk=self.draft()
        self.client.patch(f'/api/applications/{pk}/', {'birth_date': None, 'phone': '', 'institution': '', 'education_level': ''}, format='json')
        response=self.submit(pk)
        self.assertEqual(response.status_code,400)
        for key in ['birth_date','phone','institution','education_level']:
            self.assertIn(key,response.data)
        self.assertNotIn('documents',response.data)
        self.assertNotIn('education_document_number',response.data)
        self.client.patch(f'/api/applications/{pk}/',{'birth_date':'2000-01-01','phone':'+79991234567','institution':'Учебное заведение','education_level':'studying'},format='json')
        self.assertEqual(self.submit(pk).status_code,200)

    def test_optional_documents_do_not_block_submission(self):
        self.requirement.required=False
        self.requirement.save()
        self.assertEqual(self.submit(self.draft()).status_code,200)

    def test_submission_requires_published_current_consent(self):
        pk=self.draft()
        self.upload(pk)
        with override_settings(CONSENT_TEXT='',CONSENT_VERSION=''):
            self.assertFalse(self.client.get('/api/session/').data['consent']['available'])
            self.assertEqual(self.submit(pk).status_code,400)
        result=self.client.post(f'/api/applications/{pk}/submit/',{'consent':True,'consent_version':'old'},format='json')
        self.assertEqual(result.status_code,400)
        self.assertEqual(Application.objects.get(pk=pk).status,'draft')

    def test_snapshot_is_immutable_after_profile_and_catalog_changes(self):
        pk=self.review()
        before=self.client.get(f'/api/applications/{pk}/').data
        self.assertEqual(before['submission_snapshot']['student']['first_name'],'Иван')
        self.assertEqual(before['submission_snapshot']['consent']['text'],settings.CONSENT_TEXT)
        self.assertEqual(len(before['submission_snapshot']['documents'][0]['sha256']),64)
        self.client.patch('/api/profile/',{'first_name':'Новое','phone':'+79991234567'},format='json')
        self.program.title='Новое название'
        self.program.hours=100
        self.program.save()
        self.requirement.title='Другое требование'
        self.requirement.save()
        DocumentRequirement.objects.create(program=self.program,title='Новое требование')
        after=self.client.get(f'/api/applications/{pk}/').data
        self.assertEqual(before['submission_snapshot'],after['submission_snapshot'])
        self.assertEqual(before['program'],after['program'])
        self.assertEqual(after['first_name'],'Иван')
        self.assertEqual(self.client.post(f'/api/applications/{pk}/refresh-profile/',{},format='json').status_code,400)

    def test_stored_file_revalidated_at_submission(self):
        pk=self.draft()
        self.upload(pk)
        document=Document.objects.get(application_id=pk)
        with default_storage.open(document.file.name,'wb') as file:
            file.write(b'not an image anymore')
        response=self.submit(pk)
        self.assertEqual(response.status_code,400)
        self.assertEqual(Application.objects.get(pk=pk).status,'draft')

    def test_number_is_unique_and_immutable_in_api(self):
        first=self.draft();second=self.draft()
        one=Application.objects.get(pk=first)
        two=Application.objects.get(pk=second)
        self.assertNotEqual(one.number,two.number)
        self.assertTrue(one.number.startswith('DPO-'))
        self.client.patch(f'/api/applications/{first}/',{'number':two.number},format='json')
        one.refresh_from_db()
        self.assertNotEqual(one.number,two.number)
        with self.assertRaises(IntegrityError),transaction.atomic():
            Application.objects.filter(pk=first).update(number=two.number)

    def test_deleting_draft_cleans_only_its_attachments_after_commit(self):
        first=self.draft();second=self.draft()
        self.upload(first);self.upload(second)
        first_file=Document.objects.get(application_id=first).file.name
        second_file=Document.objects.get(application_id=second).file.name
        with self.captureOnCommitCallbacks(execute=True):
            result=self.client.delete(f'/api/applications/{first}/')
            self.assertTrue(default_storage.exists(first_file))
        self.assertEqual(result.status_code,200)
        self.assertFalse(default_storage.exists(first_file))
        self.assertTrue(default_storage.exists(second_file))
        self.assertTrue(Application.objects.filter(pk=second).exists())

    def test_file_delete_replace_and_preview_permissions(self):
        pk=self.draft();self.upload(pk)
        old=Document.objects.get(application_id=pk)
        preview=self.client.get(f'/api/documents/{old.pk}/preview/')
        self.assertEqual(preview.status_code,200)
        self.assertIn('inline',preview['Content-Disposition'])
        self.assertTrue(b''.join(preview.streaming_content))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.upload(pk).status_code,200)
        self.assertFalse(default_storage.exists(old.file.name))
        current=Document.objects.get(application_id=pk)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.delete(f'/api/documents/{current.pk}/').status_code,404)
        self.assertEqual(self.client.delete(f'/api/applications/{pk}/').status_code,404)
        self.assertEqual(self.client.get(f'/api/documents/{current.pk}/preview/').status_code,404)
        self.client.force_authenticate(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(f'/api/documents/{current.pk}/').status_code,200)
        self.assertFalse(default_storage.exists(current.file.name))

    def test_replace_rollback_keeps_original_and_removes_new_file(self):
        pk=self.draft();self.upload(pk)
        old=Document.objects.get(application_id=pk)
        before=set(Path(settings.MEDIA_ROOT).rglob('*'))
        with self.captureOnCommitCallbacks(execute=True):
            with patch.object(Document,'save',side_effect=IntegrityError('simulated database failure')):
                with self.assertRaises(IntegrityError):
                    self.upload(pk)
        self.assertTrue(default_storage.exists(old.file.name))
        self.assertEqual(Document.objects.get(application_id=pk).pk,old.pk)
        self.assertEqual(set(Path(settings.MEDIA_ROOT).rglob('*')),before)

    def test_draft_delete_rollback_keeps_attachments(self):
        pk=self.draft();self.upload(pk)
        document=Document.objects.get(application_id=pk)
        with self.captureOnCommitCallbacks(execute=True):
            with patch.object(Application,'delete',side_effect=RuntimeError('simulated rollback')):
                with self.assertRaises(RuntimeError):
                    self.client.delete(f'/api/applications/{pk}/')
        self.assertTrue(default_storage.exists(document.file.name))
        self.assertTrue(Application.objects.filter(pk=pk).exists())

    def test_cleanup_failure_is_retryable_and_referenced_files_are_protected(self):
        pk=self.draft();self.upload(pk)
        document=Document.objects.get(application_id=pk)
        with self.captureOnCommitCallbacks(execute=True):
            queue_file_deletion(document.file.name)
        self.assertTrue(default_storage.exists(document.file.name))
        with patch('portal.services.default_storage.delete',side_effect=OSError('simulated file lock')):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.delete(f'/api/applications/{pk}/')
        self.assertTrue(PendingFileDeletion.objects.filter(path=document.file.name).exists())
        call_command('cleanup_documents',stdout=StringIO())
        self.assertFalse(default_storage.exists(document.file.name))

    def test_submitted_attachments_and_application_cannot_be_deleted(self):
        pk=self.review()
        document=Document.objects.get(application_id=pk)
        self.assertEqual(self.client.delete(f'/api/documents/{document.pk}/').status_code,400)
        self.assertEqual(self.client.delete(f'/api/applications/{pk}/').status_code,400)
        self.assertEqual(self.upload(pk).status_code,400)

    def test_notifications_and_events_are_consistent_and_private(self):
        pk=self.review()
        notice=Notification.objects.get(recipient=self.operator,application_id=pk)
        self.assertEqual(notice.kind,'submitted')
        self.assertEqual(self.submit(pk).status_code,400)
        self.assertEqual(Notification.objects.filter(application_id=pk).count(),1)
        self.assertEqual(self.client.post(f'/api/notifications/{notice.pk}/read/',{},format='json').status_code,404)
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.get('/api/notifications/').data['count'],1)
        self.assertEqual(self.client.post(f'/api/notifications/{notice.pk}/read/',{},format='json').status_code,200)
        self.client.post(f'/api/applications/{pk}/decision/',{'decision':'rejected','reason':'Причина отказа'},format='json')
        self.assertEqual(self.client.post(f'/api/applications/{pk}/decision/',{'decision':'accepted'},format='json').status_code,400)
        self.assertEqual(Event.objects.filter(application_id=pk,action__in=['accepted','rejected']).count(),1)
        self.assertEqual(Notification.objects.filter(application_id=pk,recipient=self.student).count(),1)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/notifications/').data['count'],0)
        self.assertEqual(self.client.get('/api/dashboard/').data['total'],0)
        self.assertEqual(self.client.get('/api/documents/').data['count'],0)

    def test_dashboard_counts_pagination_sorting_and_documents(self):
        first=self.draft()
        second=self.review()
        self.assertEqual(self.client.get('/api/dashboard/').data['counts']['draft'],1)
        page=self.client.get('/api/applications/',{'page':1,'page_size':1,'ordering':'created_at'}).data
        self.assertEqual(page['count'],2)
        self.assertEqual(page['results'][0]['id'],first)
        self.assertTrue(page['next'])
        result=self.client.get('/api/documents/').data
        self.assertEqual(result['results'][0]['id'],second)
        self.client.force_authenticate(self.operator)
        counts=self.client.get('/api/dashboard/').data['counts']
        self.assertEqual(counts['draft'],0)
        self.assertEqual(counts['review'],1)

    def test_password_change_checks_current_password_and_retains_current_session(self):
        client=APIClient();client.force_login(self.student)
        other_session=APIClient();other_session.force_login(self.student)
        data={'old_password':'wrong','new_password1':'New9-unique-strong-pass!','new_password2':'New9-unique-strong-pass!'}
        self.assertEqual(client.post('/api/auth/password/change/',data,format='json').status_code,400)
        data['old_password']='A7-str0ng-test-pass!'
        self.assertEqual(client.post('/api/auth/password/change/',data,format='json').status_code,200)
        self.assertIsNotNone(client.get('/api/session/').data['user'])
        self.assertIsNone(other_session.get('/api/session/').data['user'])
        self.student.refresh_from_db();self.assertTrue(self.student.check_password(data['new_password1']))

    def test_password_reset_is_generic_and_token_is_single_use(self):
        client=APIClient()
        known=client.post('/api/auth/password/reset/',{'email':self.student.email.upper()},format='json')
        unknown=client.post('/api/auth/password/reset/',{'email':'missing@example.invalid'},format='json')
        self.assertEqual(known.status_code,202);self.assertEqual(known.data,unknown.data)
        self.assertEqual(len(mail.outbox),1)
        uid,token=re.search(r'/#reset/([^/\s]+)/([^/\s]+)',mail.outbox[0].body).groups()
        self.assertNotIn(token,str(known.data))
        data={'uid':uid,'token':token,'new_password1':'Reset9-unique-strong-pass!','new_password2':'Reset9-unique-strong-pass!'}
        self.assertEqual(client.post('/api/auth/password/reset/confirm/',data,format='json').status_code,200)
        self.assertEqual(client.post('/api/auth/password/reset/confirm/',data,format='json').status_code,400)
        self.student.refresh_from_db();self.assertTrue(self.student.check_password(data['new_password1']))

    def test_reset_expiry_rate_limit_and_mail_failure(self):
        client=APIClient()
        token=default_token_generator.make_token(self.student)
        uid=urlsafe_base64_encode(force_bytes(self.student.pk))
        with override_settings(PASSWORD_RESET_TIMEOUT=1):
            with patch('django.contrib.auth.tokens.PasswordResetTokenGenerator._now',return_value=datetime.now()+timedelta(seconds=10)):
                result=client.post('/api/auth/password/reset/confirm/',{'uid':uid,'token':token,'new_password1':'Reset9-unique-strong-pass!','new_password2':'Reset9-unique-strong-pass!'},format='json')
                self.assertEqual(result.status_code,400)
        cache.clear()
        with patch('portal.auth_views.EmailMultiAlternatives.send',side_effect=OSError('mail unavailable')):
            self.assertEqual(client.post('/api/auth/password/reset/',{'email':self.student.email},format='json').status_code,202)
        cache.clear()
        for _ in range(5):
            self.assertEqual(client.post('/api/auth/password/reset/',{'email':'missing@example.invalid'},format='json').status_code,202)
        self.assertEqual(client.post('/api/auth/password/reset/',{'email':'missing@example.invalid'},format='json').status_code,429)

    def test_reset_endpoints_require_csrf(self):
        client=APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/auth/password/reset/',{'email':self.student.email},format='json').status_code,403)
        self.assertEqual(client.post('/api/auth/password/reset/confirm/',{},format='json').status_code,403)
