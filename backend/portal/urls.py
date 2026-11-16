from django.urls import path
from . import views
from . import auth_views
from . import document_views
from .program_document_views import ProgramDocumentSettingsView

urlpatterns = [
    path('applications/<int:pk>/statement/', document_views.StatementView.as_view()),
    path('applications/<int:pk>/contract/', document_views.ContractDraftView.as_view()),
    path('applications/<int:pk>/contract/register/', document_views.RegisterContractView.as_view()),
    path('applications/<int:pk>/contract/download/', document_views.ContractDraftDownloadView.as_view()),
    path('contracts/', document_views.ContractsView.as_view()),
    path('contracts/<int:pk>/download/', document_views.ContractDownloadView.as_view()),
    path('contracts/<int:pk>/signed-pdf/', document_views.SignedContractDownloadView.as_view()),
    path('session/', views.SessionView.as_view()),
    path('auth/register/', views.RegisterView.as_view()),
    path('auth/login/', views.LoginView.as_view()),
    path('auth/logout/', views.LogoutView.as_view()),
    path('auth/password/change/', auth_views.PasswordChangeView.as_view()),
    path('auth/password/reset/', auth_views.PasswordResetRequestView.as_view()),
    path('auth/password/reset/confirm/', auth_views.PasswordResetConfirmView.as_view()),
    path('profile/', views.ProfileView.as_view()),
    path('profile/documents/', views.ProfileDocumentsView.as_view()),
    path('profile/documents/<int:pk>/', views.ProfileDocumentDetailView.as_view()),
    path('profile/documents/<int:pk>/preview/', views.ProfileDocumentDetailView.as_view(), {'preview': True}),
    path('profile/documents/<int:pk>/download/', views.ProfileDocumentDetailView.as_view()),
    path('dashboard/', views.DashboardView.as_view()),
    path('documents/', views.DocumentsView.as_view()),
    path('notifications/', views.NotificationsView.as_view()),
    path('notifications/<int:pk>/read/', views.NotificationReadView.as_view()),
    path('programs/', views.ProgramsView.as_view()),
    path('programs/<int:pk>/document-settings/', ProgramDocumentSettingsView.as_view()),
    path('applications/', views.ApplicationsView.as_view()),
    path('applications/<int:pk>/', views.ApplicationDetailView.as_view()),
    path('applications/<int:pk>/documents/', views.UploadView.as_view()),
    path('applications/<int:pk>/profile-document/', views.UseProfileDocumentView.as_view()),
    path('applications/<int:pk>/refresh-profile/', views.RefreshProfileView.as_view()),
    path('applications/<int:pk>/submit/', views.SubmitView.as_view()),
    path('applications/<int:pk>/decision/', views.DecisionView.as_view()),
    path('documents/<int:pk>/download/', views.DownloadView.as_view()),
    path('documents/<int:pk>/preview/', views.DownloadView.as_view(), {'preview': True}),
    path('documents/<int:pk>/', views.DocumentDeleteView.as_view()),
]
