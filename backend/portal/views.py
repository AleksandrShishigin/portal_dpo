from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models import Count
from django.http import FileResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from .files import validate_document
from .models import Application, Document, ProfileDocument, DocumentRequirement, Event, Program, Notification, User
from .serializers import ApplicationEditSerializer, ApplicationSerializer, ProfileSerializer, ProfileDocumentSerializer, ProgramSerializer, RegisterSerializer, DocumentSerializer, EventSerializer, NotificationSerializer
from .fields import PERSONAL_FIELDS, missing_fields, FIELD_LABELS
from .services import (consent_settings, hash_file, snapshot, notify_submission, notify_decision,
    queue_file_deletion, populate_profile_documents, copy_profile_document, document_title_key, submission_availability)
from .generated_documents import artifact_transaction, build_statement, save_artifact
from .models import Statement

class PortalPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


def paginate(request, queryset, serializer):
    paginator = PortalPagination()
    rows = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(serializer(rows, many=True).data)


def csrf_failure(request, reason=''):
    return JsonResponse({'detail': 'Проверка CSRF не пройдена. Обновите страницу и повторите действие.'}, status=403)


def student_only(user):
    if user.role != 'student':
        raise PermissionDenied('Действие доступно только обучающемуся.')


def visible_app(user, pk, lock=False):
    qs = Application.objects.select_related('program', 'student')
    if lock:
        qs = qs.select_for_update(of=('self',))
    if user.role == 'operator':
        qs = qs.exclude(status='draft')
    else:
        qs = qs.filter(student=user)
    return get_object_or_404(qs, pk=pk)


def draft_only(app):
    if app.status != 'draft':
        raise ValidationError({'detail': 'Редактировать и отправлять можно только черновик.'})


class SessionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'apiVersion': 2, 'user': ProfileSerializer(request.user).data if request.user.is_authenticated else None,
                         'csrfToken': get_token(request), 'consent': consent_settings()})


@method_decorator(csrf_protect, name='dispatch')
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = serializer.save()
        except IntegrityError:
            raise ValidationError({'email': 'Этот email уже зарегистрирован.'})
        login(request, user)
        return Response({'user': ProfileSerializer(user).data, 'csrfToken': get_token(request)}, status=201)


@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        password = request.data.get('password', '')
        if not isinstance(password, str):
            raise ValidationError({'detail': 'Неверный email или пароль.'})
        user = authenticate(request, email=email, password=password)
        if user is None:
            raise ValidationError({'detail': 'Неверный email или пароль.'})
        login(request, user)
        return Response({'user': ProfileSerializer(user).data, 'csrfToken': get_token(request)})


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({'detail': 'Вы вышли из системы.', 'csrfToken': get_token(request)})


class ProfileView(APIView):
    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise ValidationError({'email': 'Этот email уже зарегистрирован.'})
        return Response(serializer.data)


class ProgramsView(APIView):
    def get(self, request):
        return Response(ProgramSerializer(Program.objects.filter(is_active=True).prefetch_related('requirements'), many=True, context={'user': request.user}).data)


class ProfileDocumentsView(APIView):
    def get(self, request):
        student_only(request.user)
        return Response(ProfileDocumentSerializer(request.user.profile_documents.all(), many=True).data)

    def post(self, request):
        student_only(request.user)
        from rest_framework import serializers
        title = serializers.CharField(max_length=200).run_validation(request.data.get('title'))
        file = request.FILES.get('file')
        if not file:
            raise ValidationError({'file': 'Выберите файл.'})
        mime = validate_document(file)
        stored = None
        try:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=request.user.pk)
                document = ProfileDocument(owner=request.user, title=title, original_name=file.name[:250],
                    mime_type=mime, size=file.size, sha256=hash_file(file))
                document.file.save(file.name, file, save=False)
                stored = document.file.name
                document.save()
        except Exception:
            if stored:
                queue_file_deletion(stored)
            raise
        return Response(ProfileDocumentSerializer(document).data, status=201)


class ProfileDocumentDetailView(APIView):
    def delete(self, request, pk):
        student_only(request.user)
        with transaction.atomic():
            document = get_object_or_404(ProfileDocument.objects.select_for_update(), pk=pk, owner=request.user)
            queue_file_deletion(document.file.name)
            document.delete()
        return Response({'detail': 'Документ удалён из профиля. Копии в заявках сохранены.'})

    def get(self, request, pk, preview=False):
        student_only(request.user)
        document = get_object_or_404(ProfileDocument, pk=pk, owner=request.user)
        return document_response(document, preview)


class UseProfileDocumentView(APIView):
    def post(self, request, pk):
        student_only(request.user)
        from rest_framework import serializers
        source_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('document'))
        requirement_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('requirement'))
        allocated = []
        try:
            with transaction.atomic():
                app = visible_app(request.user, pk, lock=True)
                draft_only(app)
                requirement = get_object_or_404(DocumentRequirement, pk=requirement_id, program=app.program)
                source = get_object_or_404(ProfileDocument.objects.select_for_update(), pk=source_id, owner=request.user)
                if document_title_key(source.title) != document_title_key(requirement.title):
                    raise ValidationError({'document': 'Выберите документ профиля с тем же назначением, что и требование заявки.'})
                try:
                    copy_profile_document(app, requirement, source, allocated)
                except OSError:
                    raise ValidationError({'file': 'Файл профиля недоступен. Загрузите его заново.'})
        except Exception:
            for path in allocated:
                queue_file_deletion(path)
            raise
        return Response(ApplicationSerializer(app).data)


class ApplicationsView(APIView):
    def get(self, request):
        qs = Application.objects.select_related('program').prefetch_related('program__requirements', 'documents', 'events__actor')
        if request.user.role == 'operator':
            qs = qs.exclude(status='draft')
        else:
            qs = qs.filter(student=request.user)
        state = request.query_params.get('status')
        if state:
            qs = qs.filter(status=state)
        query = request.query_params.get('search', '').strip()[:200]
        if query:
            search = Q(number__icontains=query) | Q(last_name__icontains=query) | Q(first_name__icontains=query) | Q(email__icontains=query) | Q(program__title__icontains=query) | Q(submission_snapshot__program__title__icontains=query)
            if query.isdigit():
                search |= Q(pk=int(query))
            qs = qs.filter(search)
        ordering = request.query_params.get('ordering', '-created_at')
        if ordering not in {'created_at', '-created_at', 'number', '-number', 'status', '-status', 'submitted_at', '-submitted_at'}:
            raise ValidationError({'ordering': 'Недопустимая сортировка.'})
        qs = qs.order_by(ordering, '-id')
        # Keep the original unpaginated shape for existing clients; UI requests page explicitly.
        if 'page' in request.query_params:
            return paginate(request, qs, ApplicationSerializer)
        return Response(ApplicationSerializer(qs, many=True).data)

    def post(self, request):
        student_only(request.user)
        from rest_framework import serializers
        program_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('program'))
        program = get_object_or_404(Program, pk=program_id, is_active=True)
        allocated = []
        try:
            with transaction.atomic():
                # Lock sources until their independent copies are committed.
                list(ProfileDocument.objects.select_for_update().filter(owner=request.user))
                app = Application.objects.create(student=request.user, program=program,
                    **{field: getattr(request.user, field) for field in PERSONAL_FIELDS})
                populate_profile_documents(app, allocated)
                Event.objects.create(application=app, actor=request.user, action='created')
        except Exception:
            for path in allocated:
                queue_file_deletion(path)
            raise
        return Response(ApplicationSerializer(app).data, status=201)


class ApplicationDetailView(APIView):
    def get(self, request, pk):
        return Response(ApplicationSerializer(visible_app(request.user, pk)).data)

    def patch(self, request, pk):
        student_only(request.user)
        with transaction.atomic():
            app = visible_app(request.user, pk, lock=True)
            draft_only(app)
            serializer = ApplicationEditSerializer(app, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(ApplicationSerializer(app).data)

    def delete(self, request, pk):
        student_only(request.user)
        with transaction.atomic():
            app = visible_app(request.user, pk, lock=True)
            draft_only(app)
            for path in app.documents.values_list('file', flat=True):
                queue_file_deletion(path)
            app.delete()
        return Response({'detail': 'Черновик удалён.'})


class RefreshProfileView(APIView):
    def post(self, request, pk):
        student_only(request.user)
        with transaction.atomic():
            app = visible_app(request.user, pk, lock=True)
            draft_only(app)
            for field in PERSONAL_FIELDS:
                setattr(app, field, getattr(request.user, field))
            app.save()
        return Response(ApplicationSerializer(app).data)


class UploadView(APIView):
    def post(self, request, pk):
        student_only(request.user)
        file = request.FILES.get('file')
        if not file:
            raise ValidationError({'file': 'Выберите файл.'})
        mime = validate_document(file)
        stored = None
        try:
            with transaction.atomic():
                app = visible_app(request.user, pk, lock=True)
                draft_only(app)
                from rest_framework import serializers
                requirement_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('requirement'))
                requirement = get_object_or_404(DocumentRequirement, pk=requirement_id, program=app.program)
                old = Document.objects.filter(application=app, requirement=requirement).first()
                if old:
                    queue_file_deletion(old.file.name)
                    old.delete()
                document = Document(application=app, requirement=requirement,
                                    original_name=file.name[:250], mime_type=mime, size=file.size, sha256=hash_file(file))
                document.file.save(file.name, file, save=False)
                stored = document.file.name
                document.save()
        except Exception:
            # Storage does not participate in the DB transaction. Remove only the
            # newly allocated UUID path after rollback; never remove the old file.
            if stored:
                queue_file_deletion(stored)
            raise
        return Response(ApplicationSerializer(app).data)


class DocumentDeleteView(APIView):
    def delete(self, request, pk):
        student_only(request.user)
        with transaction.atomic():
            document = get_object_or_404(Document, pk=pk)
            app = visible_app(request.user, document.application_id, lock=True)
            draft_only(app)
            # Re-read after the application lock in case another upload replaced it.
            document = get_object_or_404(Document, pk=pk, application=app)
            queue_file_deletion(document.file.name)
            document.delete()
        return Response(ApplicationSerializer(app).data)


class SubmitView(APIView):
    def post(self, request, pk):
        student_only(request.user)
        with artifact_transaction() as allocated:
            app = visible_app(request.user, pk, lock=True)
            draft_only(app)
            errors = {}
            app.program = Program.objects.select_for_update().get(pk=app.program_id)
            list(app.program.requirements.select_for_update())
            availability = submission_availability(app.program)
            if not availability['available']:
                errors['availability'] = availability['reason'] + ' ' + availability['next_step']
            for field in missing_fields(app.program, app):
                errors[field] = f'Заполните поле «{FIELD_LABELS[field]}».'
            consent = consent_settings()
            if not consent['available']:
                errors['consent'] = 'Приём заявок временно недоступен: текст согласия ещё не опубликован.'
            if request.data.get('consent') is not True:
                errors['consent'] = ('Необходимо подтвердить использование только вымышленных сведений и тестовых файлов.'
                                     if consent.get('kind') == 'demo_confirmation'
                                     else 'Необходимо согласие на обработку персональных данных.')
            if request.data.get('consent_version') != consent['version']:
                errors['consent_version'] = 'Текст согласия обновился. Обновите страницу.'
            existing = set(app.documents.values_list('requirement_id', flat=True))
            required = app.program.requirements.filter(required=True)
            if not app.education_document_received:
                required = required.filter(only_if_graduated=False)
            missing = list(required.exclude(pk__in=existing).values_list('title', flat=True))
            if missing:
                errors['documents'] = 'Добавьте документы: ' + ', '.join(missing)
            # Revalidate stored content before freezing the file manifest.
            for document in app.documents.select_related('requirement'):
                try:
                    with document.file.open('rb') as stored:
                        if validate_document(stored) != document.mime_type:
                            raise ValueError()
                        digest = hash_file(stored)
                        if document.sha256 and document.sha256 != digest:
                            raise ValueError()
                        document.sha256, document.size = digest, stored.size
                        document.save(update_fields=['sha256', 'size'])
                except (OSError, ValueError, ValidationError):
                    errors[f'document_{document.requirement_id}'] = f'Замените недоступный или некорректный файл «{document.requirement.title}».'
            if errors:
                raise ValidationError(errors)
            app.status = 'review'
            app.submitted_at = app.consent_at = timezone.now()
            app.consent_version = consent['version']
            app.submission_snapshot = snapshot(app, consent)
            data, template, content = build_statement(app)
            save_artifact(Statement(application=app), data, template, content, allocated)
            app.save()
            Event.objects.create(application=app, actor=request.user, action='submitted')
            notify_submission(app)
        return Response(ApplicationSerializer(app).data)


class DecisionView(APIView):
    def post(self, request, pk):
        if request.user.role != 'operator':
            raise PermissionDenied('Действие доступно только оператору.')
        decision = request.data.get('decision')
        reason = str(request.data.get('reason', '')).strip()
        if decision not in {'accepted', 'rejected'}:
            raise ValidationError({'decision': 'Недопустимое решение.'})
        if decision == 'rejected' and not reason:
            raise ValidationError({'reason': 'Укажите причину отклонения.'})
        if len(reason) > 4000:
            raise ValidationError({'reason': 'Не более 4000 символов.'})
        with transaction.atomic():
            app = visible_app(request.user, pk, lock=True)
            if app.status != 'review':
                raise ValidationError({'detail': 'Решение уже принято или заявка не отправлена.'})
            app.status = decision
            app.decision_reason = reason
            app.decided_by = request.user
            app.decided_at = timezone.now()
            app.save()
            Event.objects.create(application=app, actor=request.user, action=decision, reason=reason)
            notify_decision(app)
        return Response(ApplicationSerializer(app).data)


class DownloadView(APIView):
    def get(self, request, pk, preview=False):
        document = get_object_or_404(Document, pk=pk)
        visible_app(request.user, document.application_id)
        return document_response(document, preview)


def document_response(document, preview=False):
    try:
        response = FileResponse(document.file.open('rb'), as_attachment=not preview,
                                filename=document.original_name, content_type=document.mime_type)
    except OSError:
        return Response({'detail': 'Файл недоступен.'}, status=status.HTTP_404_NOT_FOUND)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    # Allow Chromium's PDF viewer, with typed private access and same-origin framing.
    response['Content-Security-Policy'] = (
        "default-src 'none'; object-src 'self'; frame-ancestors 'self'"
        if preview and document.mime_type == 'application/pdf'
        else "default-src 'none'; sandbox"
    )
    return response


class DashboardView(APIView):
    def get(self, request):
        qs = Application.objects.all()
        if request.user.role == 'operator':
            qs = qs.exclude(status='draft')
        else:
            qs = qs.filter(student=request.user)
        counters = {state: 0 for state in Application.Status.values}
        counters.update({r['status']: r['total'] for r in qs.values('status').annotate(total=Count('pk'))})
        events = Event.objects.filter(application__in=qs).select_related('actor', 'application').order_by('-created_at', '-id')[:10]
        serialized = EventSerializer(events, many=True).data
        for item, event in zip(serialized, events):
            item.update(application=event.application_id, number=event.application.number)
        return Response({'counts': counters, 'total': qs.count(), 'unread': request.user.notifications.filter(read_at=None).count(), 'events': serialized})


class DocumentsView(APIView):
    def get(self, request):
        student_only(request.user)
        applications = Application.objects.filter(student=request.user, documents__isnull=False).distinct().select_related('program').prefetch_related('documents', 'program__requirements')
        return paginate(request, applications, ApplicationSerializer)


class NotificationsView(APIView):
    def get(self, request):
        return paginate(request, request.user.notifications.all(), NotificationSerializer)


class NotificationReadView(APIView):
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        if not notification.read_at:
            notification.read_at = timezone.now()
            notification.save(update_fields=['read_at'])
        return Response(NotificationSerializer(notification).data)
