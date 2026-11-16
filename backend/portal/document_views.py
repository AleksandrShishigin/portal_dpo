from copy import deepcopy
from io import BytesIO
from django.db import IntegrityError
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .generated_documents import (MIME, artifact_transaction, build_statement, save_artifact,
    contract_defaults, contract_preview, validate_contract, build_contract, template_bytes, historical_warning)
from .models import Contract, Event, Program
from .serializers import ApplicationEditSerializer
from .views import visible_app, paginate


def operator_only(user):
    if user.role != 'operator':
        raise PermissionDenied('Действие доступно только оператору.')


def docx_response(content, filename):
    response = FileResponse(content, as_attachment=True, filename=filename, content_type=MIME)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def stored_response(document, filename):
    try:
        return docx_response(document.file.open('rb'), filename)
    except OSError:
        return Response({'detail': 'Сохранённый файл недоступен. Обратитесь к оператору. Повторное формирование отключено для сохранения исторической версии.'}, status=404)


class StatementView(APIView):
    def get(self, request, pk):
        app = visible_app(request.user, pk)
        if hasattr(app, 'statement'):
            return stored_response(app.statement, f'statement-{app.number}.docx')
        if app.status != 'draft':
            return Response({'detail': historical_warning(app) or 'Итоговый DOCX при отправке не сохранялся. Исторический файл недоступен.'}, status=409)
        with artifact_transaction():
            _, _, content = build_statement(app)
        return docx_response(BytesIO(content), f'statement-draft-{app.number}.docx')


class ContractSerializer(serializers.ModelSerializer):
    applicant = serializers.SerializerMethodField()
    program_title = serializers.SerializerMethodField()
    application_number = serializers.CharField(source='application.number')
    download_url = serializers.SerializerMethodField()
    signature_status_label = serializers.CharField(source='get_signature_status_display', read_only=True)
    signed_pdf_download_url = serializers.SerializerMethodField()

    def get_signed_pdf_download_url(self, obj):
        return f'/api/contracts/{obj.pk}/signed-pdf/' if obj.has_confirmed_signature else None

    def get_applicant(self, obj):
        p = obj.snapshot['student']
        return ' '.join(p.get(k, '') for k in ['last_name', 'first_name', 'patronymic']).strip()

    def get_program_title(self, obj):
        return obj.snapshot['program']['title']

    def get_download_url(self, obj):
        return f'/api/contracts/{obj.pk}/download/'

    class Meta:
        model = Contract
        fields = ['id', 'application', 'application_number', 'number', 'date', 'applicant',
                  'program_title', 'download_url', 'template_version', 'sha256', 'created_at',
                  'signature_status', 'signature_status_label', 'signed_at', 'signed_pdf_download_url']
        read_only_fields = fields


def accepted_app(user, pk):
    app = visible_app(user, pk, lock=True)
    if app.status != 'accepted':
        raise ValidationError({'detail': 'Договор доступен только для принятой заявки.'})
    return app


def draft_response(app):
    if hasattr(app, 'contract'):
        return {'registered': ContractSerializer(app.contract).data}
    data = app.contract_draft or contract_defaults(app)
    template = template_bytes('contract')
    return {'data': data, 'preview_number': contract_preview(data), 'errors': validate_contract(data, template),
            'warning': historical_warning(app), 'registered': None}


class ContractDraftView(APIView):
    def get(self, request, pk):
        operator_only(request.user)
        with artifact_transaction():
            app = accepted_app(request.user, pk)
            return Response(draft_response(app))

    def patch(self, request, pk):
        operator_only(request.user)
        with artifact_transaction():
            app = accepted_app(request.user, pk)
            if hasattr(app, 'contract'):
                raise ValidationError({'detail': 'Зарегистрированный договор не изменяется.'})
            data = deepcopy(app.contract_draft or contract_defaults(app))
            allowed = {'student', 'program', 'sequence', 'number_code', 'realization_year', 'department',
                       'contract_date', 'university_representative', 'authority_basis', 'university_email'}
            if not isinstance(request.data, dict) or set(request.data) - allowed:
                raise ValidationError({'detail': 'Неизвестные поля черновика договора.'})
            for section in ['student', 'program']:
                if section in request.data:
                    if not isinstance(request.data[section], dict):
                        raise ValidationError({section: 'Ожидается объект с реквизитами.'})
                    if section == 'student':
                        validator = ApplicationEditSerializer(data=request.data[section], partial=True)
                    else:
                        class ProgramInput(serializers.ModelSerializer):
                            class Meta:
                                model = Program
                                fields = ['title', 'program_kind', 'study_form', 'hours', 'starts_on', 'ends_on']
                        validator = ProgramInput(data=request.data[section], partial=True)
                    unknown = set(request.data[section]) - set(validator.fields)
                    if unknown:
                        # API clients may send the full frozen program with read-only metadata.
                        if section != 'program' or unknown - set(data.get('program', {})):
                            raise ValidationError({section: 'Неизвестные поля реквизитов.'})
                    validator.is_valid(raise_exception=True)
                    data[section].update({key: validator.fields[key].to_representation(value)
                                          for key, value in validator.validated_data.items()})
            for key in allowed - {'student', 'program'}:
                if key in request.data:
                    value = request.data[key]
                    if not isinstance(value, (str, int)) or isinstance(value, bool) or len(str(value)) > 500:
                        raise ValidationError({key: 'Некорректное значение.'})
                    data[key] = str(value).strip() if key != 'sequence' else value
            app.contract_draft = data
            app.save(update_fields=['contract_draft', 'updated_at'])
            return Response(draft_response(app))


class RegisterContractView(APIView):
    def post(self, request, pk):
        operator_only(request.user)
        try:
            with artifact_transaction() as allocated:
                app = accepted_app(request.user, pk)
                if hasattr(app, 'contract'):
                    return Response(ContractSerializer(app.contract).data)
                data = app.contract_draft or contract_defaults(app)
                template = template_bytes('contract')
                number, content = build_contract(data, template)
                contract = Contract(application=app, number=number, date=data['contract_date'], registered_by=request.user)
                save_artifact(contract, data, template, content, allocated)
                Event.objects.create(application=app, actor=request.user, action='contract_registered')
                return Response(ContractSerializer(contract).data, status=201)
        except IntegrityError:
            existing = Contract.objects.filter(application_id=pk).first()
            if existing:
                return Response(ContractSerializer(existing).data)
            return Response({'detail': 'Этот номер договора уже зарегистрирован для другой заявки. Укажите другое порядковое число.'}, status=409)


class ContractDraftDownloadView(APIView):
    def get(self, request, pk):
        operator_only(request.user)
        with artifact_transaction():
            app = accepted_app(request.user, pk)
            if hasattr(app, 'contract'):
                return stored_response(app.contract, f'contract-{app.pk}.docx')
            _, content = build_contract(app.contract_draft or contract_defaults(app), template_bytes('contract'))
            return docx_response(BytesIO(content), f'contract-draft-{app.pk}.docx')


class ContractsView(APIView):
    def get(self, request):
        operator_only(request.user)
        qs = Contract.objects.select_related('application')
        signature = request.query_params.get('signature')
        if signature == 'signed':
            qs = qs.filter(Contract.confirmed_signature_filter())
        elif signature == 'unsigned':
            qs = qs.exclude(Contract.confirmed_signature_filter())
        elif signature is not None:
            raise ValidationError({'signature': 'Выберите подписанные или не подписанные договоры.'})
        for term in request.query_params.get('search', '').strip()[:200].split():
            qs = qs.filter(Q(number__icontains=term) | Q(application__number__icontains=term) |
                Q(snapshot__student__last_name__icontains=term) | Q(snapshot__student__first_name__icontains=term) |
                Q(snapshot__student__patronymic__icontains=term) | Q(snapshot__student__email__icontains=term) |
                Q(snapshot__program__title__icontains=term))
        return paginate(request, qs, ContractSerializer)


class ContractDownloadView(APIView):
    def get(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk)
        visible_app(request.user, contract.application_id)
        return stored_response(contract, f'contract-{contract.application_id}.docx')


class SignedContractDownloadView(APIView):
    def get(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk)
        visible_app(request.user, contract.application_id)
        if not contract.has_confirmed_signature:
            return Response({'detail': 'У договора нет подтверждённого подписанного PDF.'}, status=404)
        try:
            response = FileResponse(contract.signed_pdf.open('rb'), as_attachment=True,
                                    filename=f'contract-{contract.application_id}-signed.pdf', content_type='application/pdf')
        except OSError:
            return Response({'detail': 'Сохранённый подписанный PDF недоступен. Обратитесь к оператору.'}, status=404)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
