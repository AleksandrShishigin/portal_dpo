from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from .document_views import operator_only
from .models import Program
from .serializers import ProgramSerializer


class ProgramDocumentSettingsView(APIView):
    def patch(self, request, pk):
        operator_only(request.user)
        class DocumentSettings(serializers.ModelSerializer):
            class Meta:
                model = Program
                fields = ['program_kind', 'study_form']
        with transaction.atomic():
            program = get_object_or_404(Program.objects.select_for_update(), pk=pk)
            serializer = DocumentSettings(program, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(ProgramSerializer(program).data)
