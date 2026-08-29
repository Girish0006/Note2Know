# pyrefly: ignore [missing-import]
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("subject/<int:subject_id>/", views.subject_detail, name="subject_detail"),
    path("unit/<int:unit_id>/quiz/", views.unit_quiz, name="unit_quiz"),
    path("progress/", views.progress_dashboard, name="progress"),
    path("assistant/", views.assistant, name="assistant"),
    path("assistant/api/", views.assistant_api, name="assistant_api"),
    path("unit/<int:unit_id>/summary/", views.ai_unit_summary, name="ai_unit_summary"),
    path("unit/<int:unit_id>/generate-quiz/", views.generate_ai_quiz, name="generate_ai_quiz"),
    path("semester/<int:semester_num>/notes/", views.semester_notes, name="semester_notes"),
    path("profile/", views.profile_view, name="profile"),
    path("staff/dashboard/", views.staff_dashboard, name="staff_dashboard"),
    path("note/upload/", views.upload_note_view, name="upload_note"),
    path("note/<int:note_id>/delete/", views.delete_note_view, name="delete_note"),
]