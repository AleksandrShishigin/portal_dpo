import uuid
from pathlib import Path
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from .fields import default_required_fields, validate_required_fields, validate_not_future, validate_phone


class EducationData(models.Model):
    passport_series = models.CharField(max_length=4, blank=True)
    passport_number = models.CharField(max_length=6, blank=True)
    passport_issued_by = models.CharField(max_length=500, blank=True)
    passport_issued_on = models.DateField(null=True, blank=True, validators=[validate_not_future])
    passport_department_code = models.CharField(max_length=7, blank=True)
    registration_address = models.CharField(max_length=1000, blank=True)
    residential_address = models.CharField(max_length=1000, blank=True)
    snils = models.CharField(max_length=14, blank=True)
    inn = models.CharField(max_length=12, blank=True)
    referral_source = models.CharField(max_length=300, blank=True)
    birth_date = models.DateField(null=True, blank=True, validators=[validate_not_future])
    phone = models.CharField(max_length=30, blank=True, validators=[validate_phone])
    institution = models.CharField(max_length=300, blank=True)
    education_level = models.CharField(max_length=30, blank=True, choices=[
        ('studying', 'Обучаюсь'), ('secondary', 'Среднее общее'), ('vocational', 'Среднее профессиональное'),
        ('bachelor', 'Бакалавриат'), ('specialist', 'Специалитет'), ('master', 'Магистратура'),
        ('postgraduate', 'Подготовка кадров высшей квалификации')])
    education_document_received = models.BooleanField(default=False)
    education_document_name = models.CharField(max_length=200, blank=True)
    education_document_series = models.CharField(max_length=50, blank=True)
    education_document_number = models.CharField(max_length=100, blank=True)
    education_document_date = models.DateField(null=True, blank=True, validators=[validate_not_future])

    class Meta:
        abstract = True


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        user = self.model(email=email.strip().lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self.create_user(email, password, **extra)


class User(AbstractUser, EducationData):
    username = None
    email = models.EmailField(unique=True)
    patronymic = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=16, choices=[('student', 'Обучающийся'), ('operator', 'Оператор')], default='student')
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        constraints = [models.UniqueConstraint(Lower('email'), name='user_email_case_insensitive')]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class Program(models.Model):
    program_kind = models.CharField(max_length=60, blank=True, choices=[
        ('повышения квалификации', 'Повышение квалификации'),
        ('профессиональной переподготовки', 'Профессиональная переподготовка')])
    study_form = models.CharField(max_length=1, blank=True, choices=[('1', 'Очная'), ('2', 'Очно-заочная'), ('3', 'Заочная')])
    title = models.CharField(max_length=250)
    description = models.TextField()
    starts_on = models.DateField()
    ends_on = models.DateField()
    hours = models.PositiveIntegerField()
    lms_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    required_fields = models.JSONField(default=default_required_fields, validators=[validate_required_fields])

    class Meta:
        ordering = ['starts_on', 'id']


class DocumentRequirement(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='requirements')
    title = models.CharField(max_length=200)
    required = models.BooleanField(default=True)
    only_if_graduated = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']
        constraints = [models.UniqueConstraint(fields=['program', 'title'], name='unique_program_requirement')]


class Application(EducationData):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        REVIEW = 'review', 'На проверке'
        ACCEPTED = 'accepted', 'Принята'
        REJECTED = 'rejected', 'Отклонена'

    student = models.ForeignKey(User, on_delete=models.PROTECT, related_name='applications')
    number = models.CharField(max_length=32, unique=True, editable=False)
    submission_snapshot = models.JSONField(default=dict, editable=False)
    contract_draft = models.JSONField(default=dict, editable=False)
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    last_name = models.CharField(max_length=150, blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    patronymic = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    consent_at = models.DateTimeField(null=True, blank=True)
    consent_version = models.CharField(max_length=50, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='decisions')
    decision_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = 'DPO-' + uuid.uuid4().hex[:20].upper()
        super().save(*args, **kwargs)


def private_path(instance, filename):
    return f'applications/{instance.application_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'


def profile_document_path(instance, filename):
    return f'profiles/{instance.owner_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'


class ProfileDocument(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='profile_documents')
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to=profile_document_path)
    original_name = models.CharField(max_length=250)
    mime_type = models.CharField(max_length=50)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at', '-id']


class Document(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='documents')
    requirement = models.ForeignKey(DocumentRequirement, on_delete=models.PROTECT)
    file = models.FileField(upload_to=private_path)
    original_name = models.CharField(max_length=250)
    mime_type = models.CharField(max_length=50)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # Historical provenance, not a live FK: removing a profile file must not
    # mutate even the attachment metadata of a submitted application.
    source_profile_document = models.PositiveBigIntegerField(null=True, blank=True, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['application', 'requirement'], name='one_document_per_requirement')]


class Event(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='events')
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    action = models.CharField(max_length=30)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.UniqueConstraint(fields=['application'], condition=models.Q(action__in=['accepted', 'rejected']), name='one_final_decision_event'),
            models.UniqueConstraint(fields=['application'], condition=models.Q(action='submitted'), name='one_submission_event'),
        ]


class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=20)
    text = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [models.UniqueConstraint(fields=['recipient', 'application', 'kind'], name='one_status_notification')]


class PendingFileDeletion(models.Model):
    """Transactional outbox: a failed disk cleanup can be retried safely."""
    path = models.CharField(max_length=500, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


def generated_path(instance, filename):
    return f'generated/{instance.application_id}/{uuid.uuid4().hex}.docx'


def signed_contract_path(instance, filename):
    return f'signed-contracts/{instance.application_id}/{uuid.uuid4().hex}.pdf'


class GeneratedDocument(models.Model):
    snapshot = models.JSONField(editable=False)
    template_version = models.CharField(max_length=80, editable=False)
    template_file = models.FileField(upload_to=generated_path, editable=False)
    file = models.FileField(upload_to=generated_path, editable=False)
    sha256 = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class Statement(GeneratedDocument):
    application = models.OneToOneField(Application, on_delete=models.PROTECT, related_name='statement')


class Contract(GeneratedDocument):
    class SignatureStatus(models.TextChoices):
        UNSIGNED = 'unsigned', 'Не подписан'
        PENDING = 'pending', 'Ожидает подписания'
        FAILED = 'failed', 'Ошибка подписания'
        SIGNED = 'signed', 'Подписан'

    application = models.OneToOneField(Application, on_delete=models.PROTECT, related_name='contract')
    number = models.CharField(max_length=100, unique=True, editable=False)
    date = models.DateField(editable=False)
    registered_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='registered_contracts')
    signature_status = models.CharField(max_length=16, choices=SignatureStatus.choices,
                                        default=SignatureStatus.UNSIGNED, editable=False, db_index=True)
    signed_pdf = models.FileField(upload_to=signed_contract_path, blank=True, editable=False)
    signed_at = models.DateTimeField(null=True, blank=True, editable=False)
    # Only a future trusted verification flow may set this confirmation marker.
    # There is deliberately no public upload, callback or status-change API yet.
    signature_verified_at = models.DateTimeField(null=True, blank=True, editable=False)

    @classmethod
    def confirmed_signature_filter(cls):
        return (models.Q(signature_status=cls.SignatureStatus.SIGNED, signed_at__isnull=False,
                         signature_verified_at__isnull=False) & ~models.Q(signed_pdf=''))

    @property
    def has_confirmed_signature(self):
        return bool(self.signature_status == self.SignatureStatus.SIGNED and self.signed_pdf
                    and self.signed_at and self.signature_verified_at)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.CheckConstraint(
            name='contract_signature_consistent',
            condition=(models.Q(signature_status='signed', signed_at__isnull=False,
                                signature_verified_at__isnull=False) & ~models.Q(signed_pdf='')) |
                      models.Q(signature_status__in=['unsigned', 'pending', 'failed'], signed_pdf='',
                               signed_at__isnull=True, signature_verified_at__isnull=True),
        )]
