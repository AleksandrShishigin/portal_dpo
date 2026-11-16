import hashlib
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models, transaction
from .fields import personal_data
from .models import Document, ProfileDocument, Notification, PendingFileDeletion, User, Statement, Contract


def consent_settings():
    text, version = settings.CONSENT_TEXT.strip(), settings.CONSENT_VERSION.strip()
    return {'text': text, 'version': version, 'available': bool(text and version),
            'kind': ('prototype' if getattr(settings, 'PROTOTYPE_MODE', False) else
                     'demo_confirmation' if getattr(settings, 'DEMO_CONFIRMATION', False) else 'personal_data')}


def submission_availability(program):
    if not program.is_active:
        return {'available': False, 'code': 'program_inactive',
                'reason': 'Приём заявок на эту программу закрыт.',
                'next_step': 'Выберите другую образовательную программу или уточните сроки приёма у сотрудника ДПО.'}
    if not consent_settings()['available']:
        return {'available': False, 'code': 'consent_unpublished',
                'reason': 'Не опубликованы текст и версия согласия на обработку персональных данных.',
                'next_step': 'Сохраните черновик. Для реальной подачи сотрудник ДПО должен опубликовать утверждённое согласие; для проверки используйте отдельный локальный демопортал.'}
    return {'available': True, 'code': 'open', 'reason': '', 'next_step': ''}


def document_title_key(title):
    # Conservative matching: different document titles are never guessed equivalent.
    return ' '.join(title.split()).casefold()


def matching_profile_documents(user, requirement):
    return [d for d in user.profile_documents.all()
            if document_title_key(d.title) == document_title_key(requirement.title)]


def copy_profile_document(app, requirement, source, allocated=None):
    """Freeze independent bytes, so replacing/deleting profile files cannot alter applications."""
    from .files import validate_document
    from rest_framework.exceptions import ValidationError
    stored_path = None
    try:
        with source.file.open('rb') as file:
            mime = validate_document(file)
            digest = hash_file(file)
            if mime != source.mime_type or digest != source.sha256:
                raise ValidationError({'file': 'Файл профиля изменён. Загрузите его заново.'})
            old = Document.objects.filter(application=app, requirement=requirement).first()
            document = Document(application=app, requirement=requirement, source_profile_document=source.pk,
                original_name=source.original_name, mime_type=mime, size=file.size, sha256=digest)
            document.file.save(source.original_name, file, save=False)
            stored_path = document.file.name
            if allocated is not None:
                allocated.append(stored_path)
            if old:
                queue_file_deletion(old.file.name)
                old.delete()
            document.save()
        return document
    except Exception:
        if stored_path:
            queue_file_deletion(stored_path)
        raise


def populate_profile_documents(app, allocated):
    from rest_framework.exceptions import ValidationError
    for requirement in app.program.requirements.all():
        if requirement.only_if_graduated and not app.education_document_received:
            continue
        for source in matching_profile_documents(app.student, requirement):
            try:
                copy_profile_document(app, requirement, source, allocated)
                break
            except (OSError, ValidationError):
                # An unavailable profile file must not prevent saving an incomplete draft.
                continue


def hash_file(file):
    digest = hashlib.sha256()
    file.seek(0)
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest()


def cleanup_file(job_id):
    job = PendingFileDeletion.objects.filter(pk=job_id).first()
    if not job:
        return
    # Never delete a file still referenced by any application.
    if (Document.objects.filter(file=job.path).exists() or ProfileDocument.objects.filter(file=job.path).exists()
            or Statement.objects.filter(models.Q(file=job.path) | models.Q(template_file=job.path)).exists()
            or Contract.objects.filter(models.Q(file=job.path) | models.Q(template_file=job.path) |
                                       models.Q(signed_pdf=job.path)).exists()):
        return
    try:
        default_storage.delete(job.path)
    except OSError:
        return  # Retain the outbox record for cleanup_documents.
    job.delete()


def queue_file_deletion(path):
    job, _ = PendingFileDeletion.objects.get_or_create(path=path)
    transaction.on_commit(lambda job_id=job.pk: cleanup_file(job_id))


def program_data(program):
    return {'id': program.pk, 'title': program.title, 'description': program.description,
            'program_kind': program.program_kind, 'study_form': program.study_form,
            'starts_on': program.starts_on.isoformat(), 'ends_on': program.ends_on.isoformat(),
            'hours': program.hours, 'lms_url': program.lms_url, 'required_fields': program.required_fields,
            'submission_availability': submission_availability(program),
            'requirements': list(program.requirements.values('id', 'title', 'required', 'only_if_graduated'))}


def snapshot(app, consent):
    return {'student': personal_data(app), 'program': program_data(app.program),
            'consent': {'text': consent['text'], 'version': consent['version'], 'accepted_at': app.consent_at.isoformat()},
            'documents': [{'id': d.pk, 'requirement': d.requirement_id, 'original_name': d.original_name,
                           'mime_type': d.mime_type, 'size': d.size, 'sha256': d.sha256,
                           'uploaded_at': d.uploaded_at.isoformat()} for d in app.documents.all()]}


def notify_submission(app):
    for operator_id in User.objects.filter(role='operator', is_active=True).values_list('id', flat=True):
        Notification.objects.get_or_create(recipient_id=operator_id, application=app, kind='submitted',
            defaults={'text': f'Поступила новая заявка {app.number}.'})


def notify_decision(app):
    Notification.objects.get_or_create(recipient=app.student, application=app, kind='decision',
        defaults={'text': f'Заявка {app.number}: {app.get_status_display().lower()}.'})
