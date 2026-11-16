from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from .models import Application, Document, ProfileDocument, DocumentRequirement, Event, Program, User, Notification
from .fields import PERSONAL_FIELDS, missing_fields, FIELD_LABELS
from .services import program_data, submission_availability
import re


def validate_document_person(attrs, instance=None):
    patterns = {'passport_series': r'[0-9]{4}', 'passport_number': r'[0-9]{6}',
                'passport_department_code': r'[0-9]{3}-[0-9]{3}', 'inn': r'[0-9]{12}',
                'snils': r'(?:[0-9]{11}|[0-9]{3}-[0-9]{3}-[0-9]{3} [0-9]{2})'}
    for key, pattern in patterns.items():
        if attrs.get(key) and not re.fullmatch(pattern, attrs[key]):
            raise serializers.ValidationError({key: f'Проверьте формат поля «{FIELD_LABELS[key]}».'})
    birth = attrs.get('birth_date', getattr(instance, 'birth_date', None))
    issued = attrs.get('passport_issued_on', getattr(instance, 'passport_issued_on', None))
    if birth and issued and issued < birth:
        raise serializers.ValidationError({'passport_issued_on': 'Дата выдачи паспорта раньше даты рождения.'})


class ProfileSerializer(serializers.ModelSerializer):
    employee_fields = ['id', 'role', 'last_name', 'first_name', 'patronymic', 'email', 'phone']

    def get_fields(self):
        fields = super().get_fields()
        if self.instance and self.instance.role == 'operator':
            return {key: field for key, field in fields.items() if key in self.employee_fields}
        return fields

    class Meta:
        model = User
        fields = ['id', 'role'] + PERSONAL_FIELDS
        read_only_fields = ['id', 'role', 'email']
        extra_kwargs = {'first_name': {'required': True, 'allow_blank': False}, 'last_name': {'required': True, 'allow_blank': False}}

    def validate_email(self, value):
        value = value.strip().lower()
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Этот email уже зарегистрирован.')
        return value

    def validate(self, attrs):
        validate_document_person(attrs, self.instance)
        if self.instance and self.instance.role == 'operator':
            forbidden = set(self.initial_data) - set(self.employee_fields)
            if forbidden:
                raise serializers.ValidationError({key: 'Это поле недоступно в профиле сотрудника.' for key in forbidden})
        if self.instance and 'role' in self.initial_data and self.initial_data['role'] != self.instance.role:
            raise serializers.ValidationError({'role': 'Изменение роли недоступно.'})
        if self.instance and 'email' in self.initial_data and str(self.initial_data['email']).strip().lower() != self.instance.email:
            raise serializers.ValidationError({'email': 'Email для входа пока нельзя изменить: подтверждение нового адреса не настроено.'})
        birth = attrs.get('birth_date', getattr(self.instance, 'birth_date', None))
        issued = attrs.get('education_document_date', getattr(self.instance, 'education_document_date', None))
        if birth and issued and issued < birth:
            raise serializers.ValidationError({'education_document_date': 'Дата выдачи не может быть раньше даты рождения.'})
        return attrs


class RegisterSerializer(ProfileSerializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta(ProfileSerializer.Meta):
        fields = ['id', 'last_name', 'first_name', 'patronymic', 'email', 'role', 'password', 'password_confirm']
        read_only_fields = ['id', 'role']

    def validate(self, attrs):
        confirmation = attrs.pop('password_confirm')
        if attrs['password'] != confirmation:
            raise serializers.ValidationError({'password_confirm': 'Пароли не совпадают.'})
        user = User(**{k: v for k, v in attrs.items() if k != 'password'})
        try:
            password_validation.validate_password(attrs['password'], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data, role='student', is_staff=False, is_superuser=False)


class RequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentRequirement
        fields = ['id', 'title', 'required', 'only_if_graduated']


class ProgramSerializer(serializers.ModelSerializer):
    requirements = RequirementSerializer(many=True, read_only=True)
    profile_missing_fields = serializers.SerializerMethodField()
    submission_availability = serializers.SerializerMethodField()

    def get_submission_availability(self, obj):
        return submission_availability(obj)

    def get_profile_missing_fields(self, obj):
        person = self.context.get('user')
        return [{'field': f, 'label': FIELD_LABELS[f]} for f in missing_fields(obj, person)] if person and person.role == 'student' else []

    class Meta:
        model = Program
        fields = ['id', 'title', 'description', 'starts_on', 'ends_on', 'hours', 'lms_url', 'requirements', 'required_fields', 'profile_missing_fields', 'submission_availability', 'program_kind', 'study_form']


class ProfileDocumentSerializer(serializers.ModelSerializer):
    preview_url = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    def get_preview_url(self, obj):
        return f'/api/profile/documents/{obj.pk}/preview/'

    def get_download_url(self, obj):
        return f'/api/profile/documents/{obj.pk}/download/'

    class Meta:
        model = ProfileDocument
        fields = ['id', 'title', 'original_name', 'mime_type', 'size', 'sha256', 'uploaded_at', 'preview_url', 'download_url']


class DocumentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()

    def get_preview_url(self, obj):
        return f'/api/documents/{obj.pk}/preview/'

    def get_download_url(self, obj):
        return f'/api/documents/{obj.pk}/download/'

    class Meta:
        model = Document
        fields = ['id', 'requirement', 'original_name', 'mime_type', 'size', 'sha256', 'uploaded_at', 'download_url', 'preview_url', 'source_profile_document']


class EventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    def get_actor_name(self, obj):
        return f'{obj.actor.last_name} {obj.actor.first_name}'.strip() or obj.actor.get_role_display()

    class Meta:
        model = Event
        fields = ['id', 'action', 'actor_name', 'reason', 'created_at']


class ApplicationSerializer(serializers.ModelSerializer):
    program = serializers.SerializerMethodField()
    documents = DocumentSerializer(many=True, read_only=True)
    events = EventSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    missing_fields = serializers.SerializerMethodField()
    missing_documents = serializers.SerializerMethodField()
    submission_availability = serializers.SerializerMethodField()
    statement_document = serializers.SerializerMethodField()
    contract_document = serializers.SerializerMethodField()

    def get_statement_document(self, obj):
        from .generated_documents import statement_errors, historical_warning
        if hasattr(obj, 'statement'):
            return {'saved': True, 'download_url': f'/api/applications/{obj.pk}/statement/',
                    'template_version': obj.statement.template_version, 'errors': {}, 'warning': ''}
        return {'saved': False, 'download_url': f'/api/applications/{obj.pk}/statement/',
                'errors': statement_errors(obj), 'warning': historical_warning(obj) or
                ('Итоговый DOCX при отправке не сохранялся. Исторический файл недоступен.' if obj.status != 'draft' else '')}

    def get_contract_document(self, obj):
        if hasattr(obj, 'contract'):
            return {'number': obj.contract.number, 'date': obj.contract.date.isoformat(),
                    'download_url': f'/api/contracts/{obj.contract.pk}/download/'}
        return None

    def get_submission_availability(self, obj):
        return submission_availability(obj.program)

    def get_missing_documents(self, obj):
        if obj.status != 'draft':
            return []
        existing = {d.requirement_id for d in obj.documents.all()}
        return [{'id': r.pk, 'title': r.title} for r in obj.program.requirements.all()
                if r.required and (not r.only_if_graduated or obj.education_document_received) and r.pk not in existing]

    def get_program(self, obj):
        return obj.submission_snapshot.get('program') or program_data(obj.program)

    def get_missing_fields(self, obj):
        return [{'field': f, 'label': FIELD_LABELS[f]} for f in missing_fields(obj.program, obj)] if obj.status == 'draft' else []

    class Meta:
        model = Application
        fields = ['id', 'number', 'program', 'status', 'status_label', 'consent_at', 'consent_version', 'submitted_at', 'decided_at', 'decision_reason', 'created_at', 'updated_at', 'documents', 'events', 'submission_snapshot', 'missing_fields', 'missing_documents', 'submission_availability', 'statement_document', 'contract_document'] + PERSONAL_FIELDS


class ApplicationEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = PERSONAL_FIELDS

    def validate(self, attrs):
        validate_document_person(attrs, self.instance)
        birth = attrs.get('birth_date', getattr(self.instance, 'birth_date', None))
        issued = attrs.get('education_document_date', getattr(self.instance, 'education_document_date', None))
        if birth and issued and issued < birth:
            raise serializers.ValidationError({'education_document_date': 'Дата выдачи не может быть раньше даты рождения.'})
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'application', 'kind', 'text', 'created_at', 'read_at']
