# pyrefly: ignore [missing-import]
from django.contrib.auth.models import User
# pyrefly: ignore [missing-import]
from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True)
    icon = models.CharField(max_length=50, default="💻")

    def __str__(self):
        return f"{self.code} - {self.name}"


class Subject(models.Model):
    YEAR_CHOICES = [
        (1, "1st Year"),
        (2, "2nd Year"),
        (3, "3rd Year"),
        (4, "4th Year"),
    ]

    SEMESTER_CHOICES = [
        (1, "Semester 1"),
        (2, "Semester 2"),
        (3, "Semester 3"),
        (4, "Semester 4"),
        (5, "Semester 5"),
        (6, "Semester 6"),
        (7, "Semester 7"),
        (8, "Semester 8"),
    ]

    SUBJECT_TYPE_CHOICES = [
        ("theory", "Theory Subject"),
        ("lab", "Practical Lab"),
    ]

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subjects",
    )
    year = models.PositiveIntegerField(choices=YEAR_CHOICES, default=1)
    semester = models.PositiveIntegerField(choices=SEMESTER_CHOICES, default=1)
    subject_type = models.CharField(
        max_length=10,
        choices=SUBJECT_TYPE_CHOICES,
        default="theory",
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subjects_taught",
    )

    def clean(self):
        # pyrefly: ignore [missing-import]
        from django.core.exceptions import ValidationError
        super().clean()
        if self.department and self.department.code == "MBA":
            if self.year > 2:
                raise ValidationError({"year": "MBA department only has 2 academic years."})
            if self.semester > 4:
                raise ValidationError({"semester": "MBA department only has 4 semesters."})

    def __str__(self):
        dept_str = f"[{self.department.code}] " if self.department else ""
        return f"{dept_str}{self.code} - {self.name} ({self.get_year_display()}, {self.get_semester_display()})"


class Unit(models.Model):
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="units",
    )
    title = models.CharField(max_length=200)
    unit_number = models.PositiveIntegerField()

    class Meta:
        ordering = ["unit_number"]
        unique_together = ("subject", "unit_number")

    def __str__(self):
        return f"{self.subject.code} | Unit {self.unit_number}: {self.title}"


class Note(models.Model):
    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="notes",
    )
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="notes/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_notes",
    )

    def __str__(self):
        return self.title


class QuizQuestion(models.Model):
    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    question_text = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_answer = models.CharField(
        max_length=1,
        choices=[
            ("A", "Option A"),
            ("B", "Option B"),
            ("C", "Option C"),
            ("D", "Option D"),
        ],
    )

    def __str__(self):
        return self.question_text[:60]


class QuizAttempt(models.Model):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    score = models.PositiveIntegerField()
    total_questions = models.PositiveIntegerField()
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"{self.student.username} - {self.unit} - "
            f"{self.score}/{self.total_questions}"
        )


class StudentProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    year = models.PositiveIntegerField(
        choices=Subject.YEAR_CHOICES,
        default=1,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def clean(self):
        # pyrefly: ignore [missing-import]
        from django.core.exceptions import ValidationError
        super().clean()
        if self.department and self.department.code == "MBA" and self.year > 2:
            raise ValidationError({"year": "MBA department only has 2 academic years."})

    def __str__(self):
        return f"{self.user.username} - {self.get_year_display()}"


class StaffProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_members",
    )
    designation = models.CharField(max_length=100, blank=True, default="Faculty Member")
    phone = models.CharField(max_length=20, blank=True, default="")

    def __str__(self):
        dept_str = f" [{self.department.code}]" if self.department else ""
        name = self.user.get_full_name() or self.user.username
        return f"{name}{dept_str} - {self.designation}"