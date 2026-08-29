# pyrefly: ignore [missing-import]
from django.contrib import admin
# pyrefly: ignore [missing-import]
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
# pyrefly: ignore [missing-import]
from django.contrib.auth.models import User
from .models import Department, Note, QuizAttempt, QuizQuestion, StaffProfile, StudentProfile, Subject, Unit


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    can_delete = False
    verbose_name_plural = "Student Academic Profile"


class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    can_delete = False
    verbose_name_plural = "Staff Faculty Profile"


class UserAdmin(BaseUserAdmin):
    inlines = (StudentProfileInline, StaffProfileInline)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "icon")
    search_fields = ("name", "code")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "department", "year", "semester", "teacher")
    list_filter = ("department", "year", "semester")
    search_fields = ("name", "code")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "year", "department")
    list_filter = ("year", "department")
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "designation", "phone")
    list_filter = ("department",)
    search_fields = ("user__username", "user__first_name", "user__last_name", "designation")


admin.site.register(Unit)
admin.site.register(Note)
admin.site.register(QuizQuestion)
admin.site.register(QuizAttempt)

