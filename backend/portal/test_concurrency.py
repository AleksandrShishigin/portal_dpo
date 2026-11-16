from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from unittest import skipUnless
from django.db import connection, close_old_connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from .models import Application, Event, Notification, Program, User, Contract
from .document_test_data import REGISTRATION
from .generated_documents import contract_defaults
from .fields import personal_data
from .services import program_data
from .document_test_data import PERSON, PROGRAM


@skipUnless(connection.vendor == 'postgresql', 'Requires the isolated PostgreSQL test cluster')
class ConcurrentTransitionTests(TransactionTestCase):
    def setUp(self):
        self.student=User.objects.create_user('concurrent@example.invalid','Unused9-only-tests!', **PERSON)
        self.first=User.objects.create_user('operator1@example.invalid','Unused9-only-tests!',role='operator')
        self.second=User.objects.create_user('operator2@example.invalid','Unused9-only-tests!',role='operator')
        self.program=Program.objects.create(title='[ТЕСТ] Конкурентность',description='Тест',hours=10,
            starts_on=date(2027,1,1),ends_on=date(2027,2,1),required_fields=[], **PROGRAM)
        self.app=Application.objects.create(student=self.student,program=self.program, email=self.student.email, **PERSON)

    def race(self, requests):
        barrier=Barrier(2)
        app_id=self.app.pk
        def request(spec):
            user_id,path,data=spec
            close_old_connections()
            try:
                client=APIClient();client.force_authenticate(User.objects.get(pk=user_id))
                barrier.wait(timeout=10)
                return client.post(f'/api/applications/{app_id}/{path}/',data,format='json').status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return sorted(pool.map(request,requests))

    def test_two_operators_produce_only_one_final_decision(self):
        self.app.status='review';self.app.save()
        statuses=self.race([(self.first.pk,'decision',{'decision':'accepted'}),
            (self.second.pk,'decision',{'decision':'rejected','reason':'Причина'})])
        self.assertEqual(statuses,[200,400])
        self.assertEqual(Event.objects.filter(application=self.app,action__in=['accepted','rejected']).count(),1)
        self.assertEqual(Notification.objects.filter(application=self.app,recipient=self.student).count(),1)

    def test_two_submissions_produce_one_snapshot_event_and_notice_per_operator(self):
        data={'consent':True,'consent_version':'automated-test-v1'}
        self.assertEqual(self.race([(self.student.pk,'submit',data),(self.student.pk,'submit',data)]),[200,400])
        self.app.refresh_from_db()
        self.assertTrue(self.app.submission_snapshot)
        self.assertEqual(Event.objects.filter(application=self.app,action='submitted').count(),1)
        self.assertEqual(Notification.objects.filter(application=self.app,kind='submitted').count(),2)

    def prepare_contract(self, app):
        app.status = 'accepted'
        app.submission_snapshot = {'student': personal_data(app), 'program': program_data(app.program)}
        app.contract_draft = {**contract_defaults(app), **REGISTRATION}
        app.save()

    def register_race(self, app_ids):
        barrier = Barrier(2)
        operator_id = self.first.pk
        def register(app_id):
            close_old_connections()
            try:
                client = APIClient(); client.force_authenticate(User.objects.get(pk=operator_id))
                barrier.wait(timeout=10)
                response = client.post(f'/api/applications/{app_id}/contract/register/', {}, format='json')
                return response.status_code, response.data
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(register, app_ids))

    def test_two_concurrent_registrations_of_one_application_return_one_contract(self):
        self.prepare_contract(self.app)
        results = self.register_race([self.app.pk, self.app.pk])
        self.assertEqual(sorted(status for status, _ in results), [200, 201])
        self.assertEqual(results[0][1]['id'], results[1][1]['id'])
        self.assertEqual(Contract.objects.count(), 1)
        self.assertEqual(Event.objects.filter(action='contract_registered').count(), 1)

    def test_two_different_applications_cannot_register_the_same_number(self):
        self.prepare_contract(self.app)
        other = Application.objects.create(student=self.student, program=self.program, email=self.student.email, **PERSON)
        self.prepare_contract(other)
        # Both independent transactions reach generation before attempting the
        # unique INSERT; this exercises PostgreSQL's uniqueness arbitration.
        from unittest.mock import patch
        from .document_views import build_contract
        generated = Barrier(2)
        def simultaneous_build(*args):
            result = build_contract(*args)
            generated.wait(timeout=10)
            return result
        with patch('portal.document_views.build_contract', side_effect=simultaneous_build):
            results = self.register_race([self.app.pk, other.pk])
        self.assertEqual(sorted(status for status, _ in results), [201, 409])
        self.assertEqual(Contract.objects.count(), 1)
        self.assertEqual(Contract.objects.get().number, '0321-2О10/1-26/28-1')
        loser = next(data for status, data in results if status == 409)
        self.assertIn('другой заявки', loser['detail'])
        self.assertEqual(Event.objects.filter(action='contract_registered').count(), 1)
