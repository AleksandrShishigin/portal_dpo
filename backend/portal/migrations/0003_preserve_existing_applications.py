import hashlib
import uuid
from django.db import migrations, models


FIELDS = ['last_name', 'first_name', 'patronymic', 'email', 'birth_date', 'phone', 'institution',
          'education_level', 'education_document_received', 'education_document_name',
          'education_document_series', 'education_document_number', 'education_document_date']


def preserve_existing(apps, schema_editor):
    Application = apps.get_model('portal', 'Application')
    Requirement = apps.get_model('portal', 'DocumentRequirement')
    Document = apps.get_model('portal', 'Document')
    for app in Application.objects.select_related('program').iterator():
        if not app.number:
            app.number = 'DPO-' + uuid.uuid4().hex[:20].upper()
        if app.status != 'draft' and not app.submission_snapshot:
            program = app.program
            student = {field: (getattr(app, field).isoformat() if hasattr(getattr(app, field), 'isoformat') else getattr(app, field)) for field in FIELDS}
            documents = []
            for document in Document.objects.filter(application_id=app.pk):
                try:
                    with document.file.open('rb') as file:
                        digest = hashlib.sha256()
                        for chunk in file.chunks():
                            digest.update(chunk)
                        document.size, document.sha256 = file.size, digest.hexdigest()
                        document.save(update_fields=['size', 'sha256'])
                except OSError:
                    pass
                documents.append({'id': document.pk, 'requirement': document.requirement_id,
                    'original_name': document.original_name, 'mime_type': document.mime_type,
                    'size': document.size, 'sha256': document.sha256, 'uploaded_at': document.uploaded_at.isoformat()})
            # Historical program values before this upgrade cannot be recovered.
            # Preserve existing stored personal fields and mark the reconstruction.
            app.submission_snapshot = {'legacy_reconstructed': True, 'student': student,
                'program': {'id': program.pk, 'title': program.title, 'description': program.description,
                    'starts_on': program.starts_on.isoformat(), 'ends_on': program.ends_on.isoformat(),
                    'hours': program.hours, 'lms_url': program.lms_url, 'required_fields': program.required_fields,
                    'requirements': list(Requirement.objects.filter(program_id=program.pk).values('id','title','required','only_if_graduated'))},
                'documents': documents,
                'consent': {'text': '', 'version': app.consent_version,
                    'accepted_at': app.consent_at.isoformat() if app.consent_at else None}}
        app.save(update_fields=['number', 'submission_snapshot'])
    # Existing education-document requirements should not demand a diploma from a student.
    Requirement.objects.filter(title='Документ об образовании').update(only_if_graduated=True)


class Migration(migrations.Migration):
    dependencies = [('portal', '0002_pendingfiledeletion_application_birth_date_and_more')]
    operations = [
        migrations.RunPython(preserve_existing, migrations.RunPython.noop),
        migrations.AlterField(model_name='application', name='number', field=models.CharField(max_length=32, unique=True, editable=False)),
        migrations.AddConstraint(model_name='event', constraint=models.UniqueConstraint(fields=['application'], condition=models.Q(action__in=['accepted','rejected']), name='one_final_decision_event')),
        migrations.AddConstraint(model_name='event', constraint=models.UniqueConstraint(fields=['application'], condition=models.Q(action='submitted'), name='one_submission_event')),
    ]
