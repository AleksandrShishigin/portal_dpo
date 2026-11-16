"""Signature preparation only: no provider calls or real signing in these tests."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from . import test_generated_documents as document_tests
from .models import Application, Contract, Event, PendingFileDeletion
from .services import queue_file_deletion


class ContractSignatureTests(TestCase):
    setUp = document_tests.GeneratedDocumentTests.setUp
    submit = document_tests.GeneratedDocumentTests.submit
    accepted = document_tests.GeneratedDocumentTests.accepted
    draft = document_tests.GeneratedDocumentTests.draft
    register = document_tests.GeneratedDocumentTests.register
    download = document_tests.GeneratedDocumentTests.download

    def registered_contract(self):
        self.accepted(); self.draft()
        response = self.register()
        self.assertEqual(response.status_code, 201)
        return Contract.objects.get(pk=response.data['id'])

    def verified_result_fixture(self, contract):
        # Simulate data persisted AFTER a trusted verifier. This deliberately
        # synthetic fixture lives only in test storage, never in the portal DB.
        content = b'%PDF-1.4\nSYNTHETIC_VERIFIED_RESULT_FIXTURE_NOT_A_REAL_SIGNATURE\n%%EOF'
        contract.signed_pdf.save('fixture.pdf', ContentFile(content), save=False)
        contract.signature_status = Contract.SignatureStatus.SIGNED
        contract.signed_at = contract.signature_verified_at = timezone.now()
        contract.save(update_fields=['signature_status', 'signed_pdf', 'signed_at', 'signature_verified_at'])
        return content

    def test_new_registration_stays_unsigned_and_old_registry_shape_remains_available(self):
        contract = self.registered_contract()
        self.assertEqual(contract.signature_status, 'unsigned')
        self.assertFalse(contract.signed_pdf)
        self.assertIsNone(contract.signed_at); self.assertIsNone(contract.signature_verified_at)
        self.assertFalse(contract.has_confirmed_signature)
        for url, count in [('/api/contracts/', 1), ('/api/contracts/?signature=unsigned', 1), ('/api/contracts/?signature=signed', 0)]:
            self.assertEqual(self.client.get(url).data['count'], count)
        data = self.client.get('/api/contracts/?signature=unsigned').data['results'][0]
        self.assertEqual(data['signature_status_label'], 'Не подписан')
        self.assertIsNone(data['signed_pdf_download_url'])
        self.assertEqual(data['download_url'], f'/api/contracts/{contract.pk}/download/')

    def test_pending_and_failed_attempts_stay_in_unsigned_tab(self):
        contract = self.registered_contract()
        for status in ['pending', 'failed']:
            Contract.objects.filter(pk=contract.pk).update(signature_status=status)
            self.assertEqual(self.client.get('/api/contracts/?signature=signed').data['count'], 0)
            self.assertEqual(self.client.get('/api/contracts/?signature=unsigned').data['count'], 1)
            self.assertEqual(self.client.get(f'/api/contracts/{contract.pk}/signed-pdf/').status_code, 404)

    def test_database_requires_file_signing_date_and_verification_before_signed_status(self):
        contract = self.registered_contract()
        for changes in [
            {'signature_status': 'signed'},
            {'signature_status': 'signed', 'signed_pdf': 'ordinary.pdf', 'signed_at': timezone.now()},
            {'signature_status': 'signed', 'signature_verified_at': timezone.now(), 'signed_at': timezone.now()},
            {'signed_pdf': 'ordinary.pdf'}, {'signed_at': timezone.now()},
            {'signature_verified_at': timezone.now()}, {'signature_status': 'unknown'},
        ]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Contract.objects.filter(pk=contract.pk).update(**changes)
        contract.refresh_from_db(); self.assertEqual(contract.signature_status, 'unsigned')

    def test_only_confirmed_result_is_listed_in_signed_tab(self):
        contract = self.registered_contract()
        self.verified_result_fixture(contract)
        result = self.client.get('/api/contracts/?signature=signed').data
        self.assertEqual(result['count'], 1)
        self.assertEqual(self.client.get('/api/contracts/?signature=unsigned').data['count'], 0)
        row = result['results'][0]
        self.assertEqual(row['signature_status'], 'signed')
        self.assertTrue(row['signed_at'])
        self.assertEqual(row['signed_pdf_download_url'], f'/api/contracts/{contract.pk}/signed-pdf/')

    def test_signed_pdf_download_uses_saved_bytes_and_docx_is_unchanged(self):
        contract = self.registered_contract()
        docx_url = f'/api/contracts/{contract.pk}/download/'
        original = self.download(docx_url)
        content = self.verified_result_fixture(contract)
        before = Contract.objects.values().get(pk=contract.pk)
        with patch('portal.document_views.build_contract', side_effect=AssertionError('No regeneration')):
            for _ in range(2):
                response = self.client.get(f'/api/contracts/{contract.pk}/signed-pdf/')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/pdf')
                self.assertEqual(response['Cache-Control'], 'private, no-store')
                self.assertIn('-signed.pdf', response['Content-Disposition'])
                self.assertEqual(b''.join(response.streaming_content), content)
            self.assertEqual(self.download(docx_url), original)
        self.assertEqual(Contract.objects.values().get(pk=contract.pk), before)

    def test_signed_pdf_requires_same_owner_or_operator_permission_as_docx(self):
        contract = self.registered_contract()
        content = self.verified_result_fixture(contract)
        url = f'/api/contracts/{contract.pk}/signed-pdf/'
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.download(url), content)
        self.assertEqual(self.client.get('/api/contracts/?signature=signed').status_code, 403)

    def test_placeholder_has_no_write_endpoint_or_file_side_effect(self):
        contract = self.registered_contract()
        before = Contract.objects.values().get(pk=contract.pk)
        events = list(Event.objects.values())
        files = {p.relative_to(settings.MEDIA_ROOT) for p in Path(settings.MEDIA_ROOT).rglob('*') if p.is_file()}
        for _ in range(2):
            self.assertEqual(self.client.post(f'/api/contracts/{contract.pk}/sign/', {}, format='json').status_code, 404)
        self.assertEqual(self.client.post(f'/api/contracts/{contract.pk}/signed-pdf/', {}, format='json').status_code, 405)
        self.assertEqual(self.client.patch(f'/api/contracts/{contract.pk}/download/', {'signature_status': 'signed'}, format='json').status_code, 405)
        self.assertEqual(self.client.get(f'/api/contracts/{contract.pk}/signed-pdf/').status_code, 404)
        self.assertEqual(Contract.objects.values().get(pk=contract.pk), before)
        self.assertEqual(list(Event.objects.values()), events)
        self.assertEqual({p.relative_to(settings.MEDIA_ROOT) for p in Path(settings.MEDIA_ROOT).rglob('*') if p.is_file()}, files)

    def test_signature_cannot_be_injected_through_registration_or_draft(self):
        self.accepted(); self.draft()
        self.assertEqual(self.draft({'signature_status': 'signed'}).status_code, 400)
        response = self.client.post(f'/api/applications/{self.app.pk}/contract/register/',
                                    {'signature_status': 'signed', 'signed_pdf': 'ordinary.pdf'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['signature_status'], 'unsigned')
        self.assertIsNone(response.data['signed_pdf_download_url'])

    def test_search_uses_frozen_data_and_keeps_signature_filter_and_pagination(self):
        contract = self.registered_contract()
        app = Application.objects.create(student=self.student, program=self.program, status='accepted')
        second = Contract.objects.create(application=app, number='[ТЕСТ]-OTHER-123', date=contract.date,
            registered_by=self.operator, snapshot=deepcopy(contract.snapshot), template_version=contract.template_version,
            file=contract.file.name, template_file=contract.template_file.name, sha256=contract.sha256)
        self.verified_result_fixture(second)
        self.student.first_name = 'Другое имя'; self.student.save()
        for query in ['0321', 'Тестов Иван', '[ТЕСТ] Документы', self.app.number]:
            response = self.client.get('/api/contracts/', {'signature': 'unsigned', 'search': query})
            self.assertEqual(response.data['count'], 1)
            self.assertEqual(response.data['results'][0]['id'], contract.pk)
        self.assertEqual(self.client.get('/api/contracts/', {'signature': 'signed', 'search': 'OTHER'}).data['count'], 1)
        self.assertEqual(self.client.get('/api/contracts/', {'signature': 'signed', 'search': '0321'}).data['count'], 0)
        result = self.client.get('/api/contracts/', {'page_size': 1, 'page': 2}).data
        self.assertEqual(result['count'], 2); self.assertEqual(len(result['results']), 1)
        self.assertEqual(self.client.get('/api/contracts/?signature=bogus').status_code, 400)

    def test_missing_signed_file_returns_error_and_never_recreates_it(self):
        contract = self.registered_contract()
        self.verified_result_fixture(contract)
        default_storage.delete(contract.signed_pdf.name)
        before = Contract.objects.values().get(pk=contract.pk)
        with patch('portal.document_views.build_contract', side_effect=AssertionError('No regeneration')):
            self.assertEqual(self.client.get(f'/api/contracts/{contract.pk}/signed-pdf/').status_code, 404)
        self.assertEqual(Contract.objects.values().get(pk=contract.pk), before)

    def test_cleanup_preserves_signed_pdf_still_referenced_by_contract(self):
        contract = self.registered_contract()
        self.verified_result_fixture(contract)
        with self.captureOnCommitCallbacks(execute=True):
            queue_file_deletion(contract.signed_pdf.name)
        self.assertTrue(default_storage.exists(contract.signed_pdf.name))
        self.assertTrue(PendingFileDeletion.objects.filter(path=contract.signed_pdf.name).exists())
