from portal.models import Department
import json
import os
import re
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from openai import OpenAI
# pyrefly: ignore [missing-import]
from django.contrib import messages
# pyrefly: ignore [missing-import]
from django.contrib.auth import authenticate, login, logout
# pyrefly: ignore [missing-import]
from django.contrib.auth.decorators import login_required
# pyrefly: ignore [missing-import]
from django.db.models import Max
# pyrefly: ignore [missing-import]
from django.http import JsonResponse
# pyrefly: ignore [missing-import]
from django.shortcuts import get_object_or_404, redirect, render
# pyrefly: ignore [missing-import]
from .models import Department, Note, QuizAttempt, QuizQuestion, StaffProfile, StudentProfile, Subject, Unit


def get_student_year(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser or user.is_staff:
        return None  # Admins/Teachers have unrestricted access to all years
    profile, _ = StudentProfile.objects.get_or_create(user=user, defaults={"year": 1})
    return profile.year

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

try:
    # pyrefly: ignore [missing-import]
    from google import genai
except ImportError:
    genai = None

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

def call_ai(prompt, system_instruction="You are Note2Know AI Assistant."):
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    # 1. Try Google Gemini API (official SDK)
    if genai and gemini_key:
        models_to_try = [
            "gemini-3.6-flash",
            "gemini-flash-latest",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
        ]
        g_client = genai.Client(api_key=gemini_key)
        for model_name in models_to_try:
            try:
                response = g_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"system_instruction": system_instruction}
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                continue

    # 2. Fallback to OpenAI API
    if client:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content

    raise ValueError("No valid AI API Key configured in .env (Set GEMINI_API_KEY or OPENAI_API_KEY).")


def home(request):
    return render(request, "portal/home.html")


def login_view(request):
    if request.user.is_authenticated and request.method == "GET":
        logout(request)

    role_param = request.GET.get("role")
    selected_role = role_param if role_param in ["student", "staff"] else "student"

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        role = request.POST.get("role", "student")
        selected_role = role

        user = authenticate(request, username=username, password=password)

        if user is not None:
            is_staff_user = user.is_staff or user.is_superuser
            if role == "staff" and not is_staff_user:
                messages.error(
                    request,
                    "This account is not registered as Faculty/Staff. Please select Student login."
                )
                return render(request, "portal/login.html", {"selected_role": selected_role, "username": username})
            elif role == "student" and is_staff_user:
                messages.error(
                    request,
                    "This account is registered as Faculty/Staff. Please select Staff / Faculty login."
                )
                return render(request, "portal/login.html", {"selected_role": selected_role, "username": username})

            login(request, user)
            if is_staff_user or role == "staff":
                return redirect("staff_dashboard")
            return redirect("dashboard")

        messages.error(request, "Invalid credentials. Please check your ID and password.")
        return render(request, "portal/login.html", {"selected_role": selected_role, "username": username})

    return render(request, "portal/login.html", {"selected_role": selected_role})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect("home")


def forgot_password(request):
    # pyrefly: ignore [missing-import]
    import random
    # pyrefly: ignore [missing-import]
    from django.contrib.auth.models import User

    step = "request_otp"
    demo_otp = None

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "send_otp":
            username = request.POST.get("username", "").strip()
            user = User.objects.filter(username=username).first()

            if user:
                otp = str(random.randint(100000, 999999))
                request.session["reset_username"] = username
                request.session["reset_otp"] = otp

                step = "verify_otp"
                demo_otp = otp
                messages.info(
                    request,
                    f"OTP sent to student account '{username}'. Use the 6-digit code below to set your new password."
                )
            else:
                messages.error(request, f"No student account found with College ID '{username}'.")

        elif action == "verify_and_reset":
            submitted_otp = request.POST.get("otp", "").strip()
            new_password = request.POST.get("new_password", "")
            confirm_password = request.POST.get("confirm_password", "")

            saved_otp = request.session.get("reset_otp")
            saved_username = request.session.get("reset_username")

            if not saved_otp or not saved_username:
                messages.error(request, "Session expired. Please request a new OTP.")
                step = "request_otp"
            elif submitted_otp != saved_otp:
                messages.error(request, "Invalid OTP code. Please enter the correct 6-digit OTP.")
                step = "verify_otp"
                demo_otp = saved_otp
            elif new_password != confirm_password:
                messages.error(request, "Passwords do not match. Please re-enter your new password.")
                step = "verify_otp"
                demo_otp = saved_otp
            elif len(new_password) < 4:
                messages.error(request, "Password must be at least 4 characters long.")
                step = "verify_otp"
                demo_otp = saved_otp
            else:
                user = User.objects.filter(username=saved_username).first()
                if user:
                    user.set_password(new_password)
                    user.save()
                    request.session.pop("reset_otp", None)
                    request.session.pop("reset_username", None)
                    messages.success(request, "Password changed successfully! You can now log in.")
                    return redirect("login")
                else:
                    messages.error(request, "User not found.")
                    step = "request_otp"

    context = {
        "step": step,
        "username": request.session.get("reset_username", ""),
        "demo_otp": demo_otp,
    }
    return render(request, "portal/forgot_password.html", context)


def seed_departments_if_empty():
    defaults = [
        ("BCA", "Bachelor of Computer Applications", "fa-solid fa-laptop-code"),
        ("BBA", "Bachelor of Business Administration", "fa-solid fa-briefcase"),
        ("B.Com", "Bachelor of Commerce", "fa-solid fa-chart-pie"),
        ("MBA", "Master of Business Administration", "fa-solid fa-graduation-cap"),
    ]
    for code, name, icon in defaults:
        Department.objects.get_or_create(code=code, defaults={"name": name, "icon": icon})

    bca_dept = Department.objects.filter(code="BCA").first()
    if bca_dept:
        bca_structure = {
            1: {
                "theory": [
                    ("BCA101", "Computer Fundamentals & C Programming"),
                    ("BCA102", "Mathematics - I (Discrete Structure)"),
                    ("BCA103", "Digital Electronics & Logic Design"),
                    ("BCA104", "Communicative English & Grammar"),
                    ("BCA105", "Environmental Studies & Ecology"),
                    ("BCA106", "Office Automation & IT Tools"),
                    ("BCA107", "Problem Solving Techniques"),
                    ("BCA108", "Principles of Management"),
                ],
                "labs": [
                    ("BCALAB101", "C Programming Laboratory"),
                    ("BCALAB102", "Digital Electronics Laboratory"),
                    ("BCALAB103", "IT & Office Automation Lab"),
                ]
            },
            2: {
                "theory": [
                    ("BCA201", "Data Structures using C"),
                    ("BCA202", "Mathematics - II (Calculus & Linear Algebra)"),
                    ("BCA203", "Object Oriented Programming in C++"),
                    ("BCA204", "Operating System Concepts"),
                    ("BCA205", "Database Management Systems (DBMS)"),
                    ("BCA206", "Computer Architecture & Organization"),
                    ("BCA207", "Financial Accounting & Management"),
                    ("BCA208", "Soft Skills & Business Communication"),
                ],
                "labs": [
                    ("BCALAB201", "Data Structures Laboratory"),
                    ("BCALAB202", "Object Oriented C++ Lab"),
                    ("BCALAB203", "DBMS & SQL Practical Lab"),
                ]
            },
            3: {
                "theory": [
                    ("BCA301", "Java Programming & OOP"),
                    ("BCA302", "Computer Networks & Security"),
                    ("BCA303", "Software Engineering & Architecture"),
                    ("BCA304", "Web Technology (HTML5, CSS3, JS)"),
                    ("BCA305", "Python Programming Fundamentals"),
                    ("BCA306", "Design & Analysis of Algorithms"),
                    ("BCA307", "System Software & Compilers"),
                    ("BCA308", "Organizational Behavior"),
                ],
                "labs": [
                    ("BCALAB301", "Java Programming Laboratory"),
                    ("BCALAB302", "Web Technology Practical Lab"),
                    ("BCALAB303", "Python Programming Lab"),
                ]
            },
            4: {
                "theory": [
                    ("BCA401", "Advanced Java & Enterprise Frameworks"),
                    ("BCA402", "Relational Database System & NoSQL"),
                    ("BCA403", "PHP & MySQL Web Development"),
                    ("BCA404", "Unix / Linux Shell Programming"),
                    ("BCA405", "Software Project Management"),
                    ("BCA406", "Computer Graphics & Multimedia"),
                    ("BCA407", "Data Mining & Data Warehousing"),
                    ("BCA408", "E-Commerce & Cyber Law"),
                ],
                "labs": [
                    ("BCALAB401", "Advanced Java & Web Lab"),
                    ("BCALAB402", "PHP & MySQL Web Development Lab"),
                    ("BCALAB403", "Linux Shell Scripting Lab"),
                ]
            },
            5: {
                "theory": [
                    ("BCA501", "Artificial Intelligence & Machine Learning"),
                    ("BCA502", "Cloud Computing & Virtualization"),
                    ("BCA503", "Mobile Application Development (Android)"),
                    ("BCA504", "Cyber Security & Cryptography"),
                    ("BCA505", "Software Quality Assurance & Testing"),
                    ("BCA506", "Big Data Analytics"),
                    ("BCA507", "Internet of Things (IoT)"),
                    ("BCA508", "Management Information Systems"),
                ],
                "labs": [
                    ("BCALAB501", "AI & Machine Learning Lab"),
                    ("BCALAB502", "Android App Development Lab"),
                    ("BCALAB503", "Cloud & IoT Practical Lab"),
                ]
            },
            6: {
                "theory": [
                    ("BCA601", "Full Stack Web Development (React & Node.js)"),
                    ("BCA602", "Information & Network Security"),
                    ("BCA603", "Data Science & Business Intelligence"),
                    ("BCA604", "DevOps & Agile Methodologies"),
                    ("BCA605", "Deep Learning & Neural Networks"),
                    ("BCA606", "Mobile Computing & Wireless Tech"),
                    ("BCA607", "Entrepreneurship Development"),
                    ("BCA608", "Capstone Major Project Guidance"),
                ],
                "labs": [
                    ("BCALAB601", "Full Stack Web Application Lab"),
                    ("BCALAB602", "Data Science & Analytics Lab"),
                    ("BCALAB603", "Capstone Software Project Lab"),
                ]
            }
        }

        for sem_num, data in bca_structure.items():
            year_num = (sem_num + 1) // 2
            
            for code, name in data["theory"]:
                subj, _ = Subject.objects.get_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "department": bca_dept,
                        "year": year_num,
                        "semester": sem_num,
                        "subject_type": "theory",
                    }
                )
                if subj.department != bca_dept or subj.year != year_num or subj.semester != sem_num or subj.subject_type != "theory":
                    subj.department = bca_dept
                    subj.year = year_num
                    subj.semester = sem_num
                    subj.subject_type = "theory"
                    subj.save()

            for code, name in data["labs"]:
                subj, _ = Subject.objects.get_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "department": bca_dept,
                        "year": year_num,
                        "semester": sem_num,
                        "subject_type": "lab",
                    }
                )
                if subj.department != bca_dept or subj.year != year_num or subj.semester != sem_num or subj.subject_type != "lab":
                    subj.department = bca_dept
                    subj.year = year_num
                    subj.semester = sem_num
                    subj.subject_type = "lab"
                    subj.save()

    # Ensure every Subject (theory or lab) has 5 Units
    for subj in Subject.objects.all():
        for u_num in range(1, 6):
            if subj.subject_type == "lab":
                unit_title = f"Practical Experiment {u_num} - {subj.name} Lab Hands-on"
            else:
                unit_title = f"{subj.name} - Part {u_num} Core Concepts"
            
            Unit.objects.get_or_create(
                subject=subj,
                unit_number=u_num,
                defaults={"title": unit_title}
            )


@login_required(login_url="login")
def dashboard(request):
    seed_departments_if_empty()

    student_year = get_student_year(request.user)
    student_profile = StudentProfile.objects.filter(user=request.user).first() if request.user.is_authenticated else None
    
    default_dept = student_profile.department.code if (student_profile and student_profile.department) else "BCA"
    
    selected_dept = request.GET.get("dept", default_dept if student_year is not None else "all")
    selected_year = request.GET.get("year", str(student_year) if student_year is not None else "all")
    selected_sem = request.GET.get("sem", "all")

    is_student_restricted = False
    student_year_label = ""
    if student_year is not None:
        selected_year = str(student_year)
        is_student_restricted = True
        student_year_label = dict(Subject.YEAR_CHOICES).get(student_year, f"Year {student_year}")

    departments = Department.objects.all()

    if selected_dept == "MBA" and selected_year in ["3", "4"]:
        selected_year = "all"

    if selected_year == "1":
        available_semesters = [("1", "Sem 1"), ("2", "Sem 2")]
    elif selected_year == "2":
        available_semesters = [("3", "Sem 3"), ("4", "Sem 4")]
    elif selected_year == "3":
        available_semesters = [("5", "Sem 5"), ("6", "Sem 6")]
    elif selected_year == "4":
        available_semesters = [("7", "Sem 7"), ("8", "Sem 8")]
    else:
        if selected_dept == "MBA":
            available_semesters = [
                ("1", "Sem 1"), ("2", "Sem 2"),
                ("3", "Sem 3"), ("4", "Sem 4"),
            ]
        elif selected_dept in ["BCA", "BBA", "B.Com"]:
            available_semesters = [
                ("1", "Sem 1"), ("2", "Sem 2"),
                ("3", "Sem 3"), ("4", "Sem 4"),
                ("5", "Sem 5"), ("6", "Sem 6"),
            ]
        else:
            available_semesters = [
                ("1", "Sem 1"), ("2", "Sem 2"),
                ("3", "Sem 3"), ("4", "Sem 4"),
                ("5", "Sem 5"), ("6", "Sem 6"),
                ("7", "Sem 7"), ("8", "Sem 8"),
            ]

    valid_sem_codes = [code for code, _ in available_semesters]
    if selected_sem != "all" and selected_sem not in valid_sem_codes:
        selected_sem = "all"

    subjects_qs = Subject.objects.select_related("department").all()

    if selected_dept != "all":
        subjects_qs = subjects_qs.filter(department__code=selected_dept)

    if selected_year in ["1", "2", "3", "4"]:
        subjects_qs = subjects_qs.filter(year=int(selected_year))

    if selected_sem != "all" and selected_sem.isdigit():
        subjects_qs = subjects_qs.filter(semester=int(selected_sem))

    attempts = QuizAttempt.objects.filter(
        student=request.user
    ).order_by("-completed_at")

    total_quizzes = attempts.count()
    highest_score = max([attempt.score for attempt in attempts], default=0)
    recent_attempts = attempts[:5]

    years_list = [
        ("all", "All Years"),
        ("1", "1st Year"),
        ("2", "2nd Year"),
        ("3", "3rd Year"),
        ("4", "4th Year"),
    ]

    years_data = [
        {
            "code": "1",
            "label": "1st Year",
            "semesters": [("1", "Sem 1"), ("2", "Sem 2")],
        },
        {
            "code": "2",
            "label": "2nd Year",
            "semesters": [("3", "Sem 3"), ("4", "Sem 4")],
        },
        {
            "code": "3",
            "label": "3rd Year",
            "semesters": [("5", "Sem 5"), ("6", "Sem 6")],
        },
        {
            "code": "4",
            "label": "4th Year",
            "semesters": [("7", "Sem 7"), ("8", "Sem 8")],
        },
    ]

    subjects_by_semester = []
    sem_dict = {}
    for sub in subjects_qs:
        sem_num = sub.semester
        if sem_num not in sem_dict:
            sem_dict[sem_num] = {
                "num": sem_num,
                "label": f"Semester {sem_num}",
                "theory_subjects": [],
                "lab_subjects": [],
                "all_subjects": [],
            }
        sem_dict[sem_num]["all_subjects"].append(sub)
        if sub.subject_type == "lab":
            sem_dict[sem_num]["lab_subjects"].append(sub)
        else:
            sem_dict[sem_num]["theory_subjects"].append(sub)

    for sem_num in sorted(sem_dict.keys()):
        subjects_by_semester.append(sem_dict[sem_num])

    context = {
        "departments": departments,
        "selected_dept": selected_dept,
        "subjects": subjects_qs,
        "subjects_by_semester": subjects_by_semester,
        "total_quizzes": total_quizzes,
        "highest_score": highest_score,
        "recent_attempts": recent_attempts,
        "selected_year": selected_year,
        "years_list": years_list,
        "years_data": years_data,
        "available_semesters": available_semesters,
        "selected_sem": selected_sem,
        "is_student_restricted": is_student_restricted,
        "student_year": student_year,
        "student_year_label": student_year_label,
    }

    return render(request, "portal/dashboard.html", context)


@login_required(login_url="login")
def subject_detail(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    student_year = get_student_year(request.user)

    if student_year is not None and subject.year != student_year:
        year_label = dict(Subject.YEAR_CHOICES).get(student_year, f"Year {student_year}")
        messages.error(
            request,
            f"Access Restricted: You are enrolled in {year_label}. You can only access subjects and notes for your enrolled academic year."
        )
        return redirect("dashboard")

    return render(request, "portal/subject_detail.html", {"subject": subject})


@login_required(login_url="login")
def unit_quiz(request, unit_id):
    unit = get_object_or_404(Unit, id=unit_id)
    student_year = get_student_year(request.user)

    if student_year is not None and unit.subject.year != student_year:
        year_label = dict(Subject.YEAR_CHOICES).get(student_year, f"Year {student_year}")
        messages.error(
            request,
            f"Access Restricted: You are enrolled in {year_label} and cannot access quizzes for other academic years."
        )
        return redirect("dashboard")

    questions = QuizQuestion.objects.filter(unit=unit)

    if request.method == "POST":
        score = 0

        for question in questions:
            selected_answer = request.POST.get(f"question_{question.id}")

            if selected_answer == question.correct_answer:
                score += 1

        QuizAttempt.objects.create(
            student=request.user,
            unit=unit,
            score=score,
            total_questions=questions.count(),
        )

        return render(
            request,
            "portal/quiz.html",
            {
                "unit": unit,
                "questions": questions,
                "score": score,
                "submitted": True,
            },
        )

    return render(
        request,
        "portal/quiz.html",
        {
            "unit": unit,
            "questions": questions,
        },
    )


def get_ai_performance_insights(user):
    attempts = QuizAttempt.objects.filter(student=user).select_related("unit", "unit__subject").order_by("-completed_at")
    if not attempts.exists():
        return {
            "summary": "You haven't attempted any quizzes yet! Attempt quizzes to receive personalized AI learning recommendations.",
            "weak_topics": [],
            "recommendations": ["Attempt practice quizzes for your enrolled subjects to start tracking performance."]
        }

    unit_stats = {}
    for a in attempts:
        u_key = f"{a.unit.subject.code} Unit {a.unit.unit_number}: {a.unit.title}"
        if u_key not in unit_stats:
            unit_stats[u_key] = {"total_score": 0, "max_score": 0, "count": 0}
        unit_stats[u_key]["total_score"] += a.score
        unit_stats[u_key]["max_score"] += a.total_questions
        unit_stats[u_key]["count"] += 1

    summary_lines = []
    for u, data in unit_stats.items():
        pct = round((data["total_score"] / data["max_score"] * 100) if data["max_score"] > 0 else 0, 1)
        summary_lines.append(f"- {u}: {pct}% average score across {data['count']} attempts")

    prompt = (
        "Analyze these student quiz performance records:\n" + "\n".join(summary_lines[:8]) + "\n\n"
        "Provide a concise JSON response with keys:\n"
        '{"summary": "1-2 sentence encouraging overview", "weak_topics": ["topic 1", "topic 2"], "recommendations": ["action step 1", "action step 2"]}'
    )

    try:
        raw_text = call_ai(prompt, system_instruction="You are Note2Know AI Academic Coach. Output JSON only.")
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception:
        pass

    return {
        "summary": f"Completed {attempts.count()} quiz attempts across your subjects.",
        "weak_topics": [u for u, d in unit_stats.items() if (d["total_score"]/d["max_score"] if d["max_score"]>0 else 0) < 0.7],
        "recommendations": ["Review unit notes before retaking quizzes.", "Ask AI Assistant any questions if you get stuck."]
    }


@login_required(login_url="login")
def progress_dashboard(request):
    attempts = QuizAttempt.objects.filter(student=request.user).order_by("completed_at")

    total_quizzes = attempts.count()
    total_score = sum(attempt.score for attempt in attempts)

    highest_score = attempts.aggregate(Max("score"))["score__max"] or 0

    # Data for Chart.js
    chart_labels = [f"{attempt.unit.subject.code} U{attempt.unit.unit_number}" for attempt in attempts]
    chart_scores = [attempt.score for attempt in attempts]

    ai_insights = get_ai_performance_insights(request.user)

    context = {
        "attempts": attempts.order_by("-completed_at"),
        "total_quizzes": total_quizzes,
        "total_score": total_score,
        "highest_score": highest_score,
        "chart_labels": chart_labels,
        "chart_scores": chart_scores,
        "ai_insights": ai_insights,
    }

    return render(request, "portal/progress.html", context)


@login_required(login_url="login")
def assistant(request):
    subjects = Subject.objects.all().prefetch_related("units")
    selected_subject_id = request.GET.get("subject_id")
    selected_unit_id = request.GET.get("unit_id")
    initial_question = request.GET.get("q", "")

    context = {
        "subjects": subjects,
        "selected_subject_id": int(selected_subject_id) if selected_subject_id and selected_subject_id.isdigit() else None,
        "selected_unit_id": int(selected_unit_id) if selected_unit_id and selected_unit_id.isdigit() else None,
        "initial_question": initial_question,
    }
    return render(request, "portal/assistant.html", context)


@login_required(login_url="login")
def assistant_api(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST method required."})

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    question = data.get("question", "").strip()
    subject_id = data.get("subject_id")
    unit_id = data.get("unit_id")

    if not question:
        return JsonResponse({"status": "error", "message": "Question cannot be empty."})

    context_info = ""
    if unit_id:
        unit = Unit.objects.filter(id=unit_id).first()
        if unit:
            context_info = f"Context: Subject '{unit.subject.name}', Unit {unit.unit_number}: '{unit.title}'. "
    elif subject_id:
        subject = Subject.objects.filter(id=subject_id).first()
        if subject:
            context_info = f"Context: Subject '{subject.name}'. "

    system_prompt = (
        "You are Note2Know AI, an intelligent college study assistant. "
        "Provide accurate, concise, encouraging markdown formatted answers for college students. "
        + context_info
    )

    try:
        answer = call_ai(question, system_instruction=system_prompt)
        return JsonResponse({"status": "success", "answer": answer})
    except Exception as e:
        err_msg = str(e)
        if "insufficient_quota" in err_msg or "credit_balance_exhausted" in err_msg or "429" in err_msg:
            return JsonResponse({
                "status": "error",
                "message": "OpenAI API quota exhausted. Please add GEMINI_API_KEY in .env file for free Google Gemini AI!"
            })
        return JsonResponse({"status": "error", "message": f"Please configure GEMINI_API_KEY or OPENAI_API_KEY in .env file. Error: {err_msg}"})


@login_required(login_url="login")
def ai_unit_summary(request, unit_id):
    unit = get_object_or_404(Unit, id=unit_id)
    student_year = get_student_year(request.user)
    if student_year is not None and unit.subject.year != student_year:
        return JsonResponse({"status": "error", "message": "Access Restricted: This unit belongs to another academic year."})

    notes_titles = [n.title for n in unit.notes.all()]
    notes_str = f"Uploaded unit notes: {', '.join(notes_titles)}" if notes_titles else ""

    prompt = (
        f"Create a high-yield study guide for college students studying Subject '{unit.subject.name}', "
        f"Unit {unit.unit_number}: '{unit.title}'. {notes_str}\n\n"
        "Format clearly in markdown with headers:\n"
        "### Core Concepts Summary\n"
        "### Key Terms & Definitions\n"
        "### Formulas / Rules / Key Principles\n"
        "### Top 3 Exam Tips"
    )

    try:
        summary_text = call_ai(prompt, system_instruction="You are Note2Know AI Professor. Output clear, well-formatted markdown study guides.")
        return JsonResponse({
            "status": "success",
            "summary": summary_text,
            "unit_title": f"Unit {unit.unit_number}: {unit.title}",
            "subject_name": unit.subject.name
        })
    except Exception:
        pass

    # Fallback study guide
    summary_text = (
        f"### Core Concepts Summary\n"
        f"High-yield study notes for **{unit.subject.name} - Unit {unit.unit_number}: {unit.title}**.\n\n"
        f"### Key Terms & Definitions\n"
        f"- **{unit.title}**: Core curriculum module focusing on foundational principles and practical applications.\n\n"
        f"### Formulas / Rules / Key Principles\n"
        f"1. Understand main architectural components and workflows.\n"
        f"2. Review uploaded lecture notes and textbook chapters.\n"
        f"3. Practice sample problems to build confidence.\n\n"
        f"### Top 3 Exam Tips\n"
        f"1. Focus on key terminology and core definitions.\n"
        f"2. Take practice quizzes regularly.\n"
        f"3. Review incorrect quiz attempts before exams."
    )
    return JsonResponse({
        "status": "success",
        "summary": summary_text,
        "unit_title": f"Unit {unit.unit_number}: {unit.title}",
        "subject_name": unit.subject.name
    })


@login_required(login_url="login")
def generate_ai_quiz(request, unit_id):
    unit = get_object_or_404(Unit, id=unit_id)
    student_year = get_student_year(request.user)
    if student_year is not None and unit.subject.year != student_year:
        messages.error(request, "Access Restricted: You cannot generate quizzes for other academic years.")
        return redirect("dashboard")

    prompt = (
        f"Generate 5 multiple-choice questions for college students studying '{unit.subject.name}', "
        f"Unit {unit.unit_number}: '{unit.title}'.\n"
        "Return JSON strictly in this format:\n"
        "{\n"
        '  "questions": [\n'
        '    {\n'
        '      "question_text": "question string",\n'
        '      "option_a": "option A",\n'
        '      "option_b": "option B",\n'
        '      "option_c": "option C",\n'
        '      "option_d": "option D",\n'
        '      "correct_answer": "A"\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    q_list = []
    try:
        raw_text = call_ai(prompt, system_instruction="You are Note2Know AI Quiz Generator. Output JSON only.")
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            q_list = data.get("questions", [])
    except Exception:
        q_list = []

    if not q_list:
        q_list = [
            {
                "question_text": f"Which of the following best describes the primary focus of {unit.title} in {unit.subject.name}?",
                "option_a": f"Understanding core principles of {unit.title}",
                "option_b": "Hardware physical component design",
                "option_c": "Unrelated historical background",
                "option_d": "Manual administrative procedures",
                "correct_answer": "A"
            },
            {
                "question_text": f"What is a key requirement when implementing concepts from Unit {unit.unit_number} ({unit.title})?",
                "option_a": "Ignoring systematic protocols",
                "option_b": "Ensuring data integrity and correctness",
                "option_c": "Avoiding structural documentation",
                "option_d": "None of the above",
                "correct_answer": "B"
            },
            {
                "question_text": f"Why is {unit.title} essential for students studying {unit.subject.name}?",
                "option_a": "It provides foundational knowledge used in advanced topics",
                "option_b": "It is rarely tested in examinations",
                "option_c": "It is strictly optional context",
                "option_d": "It replaces basic arithmetic",
                "correct_answer": "A"
            }
        ]

    created_count = 0
    for q in q_list:
        c_ans = str(q.get("correct_answer", "A")).upper().strip()
        if c_ans not in ["A", "B", "C", "D"]:
            c_ans = "A"
        QuizQuestion.objects.create(
            unit=unit,
            question_text=q.get("question_text", "Question"),
            option_a=q.get("option_a", "Option A"),
            option_b=q.get("option_b", "Option B"),
            option_c=q.get("option_c", "Option C"),
            option_d=q.get("option_d", "Option D"),
            correct_answer=c_ans
        )
        created_count += 1

    messages.success(request, f"Successfully generated {created_count} AI Quiz questions for {unit.title}!")
    return redirect("unit_quiz", unit_id=unit.id)


@login_required(login_url="login")
def semester_notes(request, semester_num):
    student_year = get_student_year(request.user)
    sem_year = (semester_num + 1) // 2

    # Access control restriction for enrolled students
    if student_year is not None and sem_year != student_year:
        year_label = dict(Subject.YEAR_CHOICES).get(student_year, f"Year {student_year}")
        messages.error(
            request,
            f"Access Restricted: You are enrolled in {year_label}. You can only access notes for your enrolled academic year."
        )
        return redirect("dashboard")

    selected_dept = request.GET.get("dept", "all")
    departments = Department.objects.all()

    subjects = Subject.objects.filter(semester=semester_num).select_related("department").prefetch_related("units", "units__notes")
    if selected_dept != "all":
        subjects = subjects.filter(department__code=selected_dept)

    notes = Note.objects.filter(
        unit__subject__in=subjects
    ).select_related("unit", "unit__subject", "unit__subject__department").order_by("unit__subject", "unit__unit_number")

    sem_label = dict(Subject.SEMESTER_CHOICES).get(semester_num, f"Semester {semester_num}")
    year_label = dict(Subject.YEAR_CHOICES).get(sem_year, f"Year {sem_year}")

    all_semesters = [
        {"num": 1, "year": 1, "label": "Sem 1"},
        {"num": 2, "year": 1, "label": "Sem 2"},
        {"num": 3, "year": 2, "label": "Sem 3"},
        {"num": 4, "year": 2, "label": "Sem 4"},
        {"num": 5, "year": 3, "label": "Sem 5"},
        {"num": 6, "year": 3, "label": "Sem 6"},
        {"num": 7, "year": 4, "label": "Sem 7"},
        {"num": 8, "year": 4, "label": "Sem 8"},
    ]
    if selected_dept == "MBA":
        all_semesters = [s for s in all_semesters if s["year"] <= 2]
    elif selected_dept in ["BCA", "BBA", "B.Com"]:
        all_semesters = [s for s in all_semesters if s["year"] <= 3]

    context = {
        "semester_num": semester_num,
        "sem_label": sem_label,
        "sem_year": sem_year,
        "year_label": year_label,
        "selected_dept": selected_dept,
        "departments": departments,
        "subjects": subjects,
        "notes": notes,
        "all_semesters": all_semesters,
    }
    return render(request, "portal/semester_notes.html", context)


@login_required(login_url="login")
def profile_view(request):
    user = request.user
    is_staff = user.is_staff or user.is_superuser

    if request.method == "POST":
        action = request.POST.get("action", "update_profile")
        
        if action == "update_profile":
            user.first_name = request.POST.get("first_name", user.first_name).strip()
            user.last_name = request.POST.get("last_name", user.last_name).strip()
            user.email = request.POST.get("email", user.email).strip()
            user.save()

            if not is_staff:
                dept_id = request.POST.get("department")
                year_val = request.POST.get("year")
                profile, _ = StudentProfile.objects.get_or_create(user=user)
                if dept_id:
                    profile.department_id = dept_id
                if year_val:
                    profile.year = int(year_val)
                profile.save()

            messages.success(request, "Profile updated successfully!")
            return redirect("profile")

    departments = Department.objects.all()
    subjects = Subject.objects.select_related("department").prefetch_related("units").all()
    all_units = Unit.objects.select_related("subject", "subject__department").all()

    student_profile = None
    quiz_stats = None
    recent_attempts = []
    staff_notes = []

    if not is_staff:
        student_profile, _ = StudentProfile.objects.get_or_create(user=user)
        attempts = QuizAttempt.objects.filter(student=user).select_related("unit", "unit__subject").order_by("-completed_at")
        total_quizzes = attempts.count()
        total_score = sum(a.score for a in attempts)
        total_possible = sum(a.total_questions for a in attempts)
        avg_percentage = round((total_score / total_possible * 100), 1) if total_possible > 0 else 0
        
        quiz_stats = {
            "total_quizzes": total_quizzes,
            "avg_percentage": avg_percentage,
        }
        recent_attempts = attempts[:5]
    else:
        staff_notes = Note.objects.filter(uploaded_by=user).select_related("unit", "unit__subject", "unit__subject__department").order_by("-uploaded_at")

    context = {
        "is_staff": is_staff,
        "student_profile": student_profile,
        "quiz_stats": quiz_stats,
        "recent_attempts": recent_attempts,
        "staff_notes": staff_notes,
        "departments": departments,
        "subjects": subjects,
        "all_units": all_units,
    }
    return render(request, "portal/profile.html", context)


@login_required(login_url="login")
def upload_note_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access restricted: Only staff members can upload notes.")
        return redirect("profile")

    if request.method == "POST":
        unit_id = request.POST.get("unit")
        title = request.POST.get("title", "").strip()
        note_file = request.FILES.get("file")

        if not unit_id or not title or not note_file:
            messages.error(request, "Please select a unit, enter a title, and attach a PDF file.")
            return redirect("profile")

        unit = get_object_or_404(Unit, id=unit_id)
        Note.objects.create(
            unit=unit,
            title=title,
            file=note_file,
            uploaded_by=request.user
        )
        messages.success(request, f"Note '{title}' uploaded successfully for {unit.subject.code} - Unit {unit.unit_number}!")
    return redirect("profile")


@login_required(login_url="login")
def delete_note_view(request, note_id):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access restricted: Only staff members can delete notes.")
        return redirect("profile")

    note = get_object_or_404(Note, id=note_id)
    if note.uploaded_by == request.user or request.user.is_superuser:
        note_title = note.title
        note.delete()
        messages.success(request, f"Note '{note_title}' deleted successfully.")
    else:
        messages.error(request, "You can only delete notes uploaded by you.")
    return redirect("profile")


@login_required(login_url="login")
def staff_dashboard(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Access restricted: Staff Portal is for Faculty and Staff members only.")
        return redirect("dashboard")

    staff_profile, _ = StaffProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "update_profile":
            first_name = request.POST.get("first_name", "").strip()
            last_name = request.POST.get("last_name", "").strip()
            email = request.POST.get("email", "").strip()
            designation = request.POST.get("designation", "").strip()
            phone = request.POST.get("phone", "").strip()
            dept_id = request.POST.get("department")

            request.user.first_name = first_name
            request.user.last_name = last_name
            request.user.email = email
            request.user.save()

            if dept_id:
                staff_profile.department_id = dept_id
            else:
                staff_profile.department = None
            staff_profile.designation = designation or "Faculty Member"
            staff_profile.phone = phone
            staff_profile.save()

            messages.success(request, "Staff profile and department selection updated successfully!")
            return redirect("staff_dashboard")

        elif action == "add_handled_subject":
            subject_id = request.POST.get("existing_subject_id")
            new_subject_name = request.POST.get("subject_name", "").strip()
            new_subject_code = request.POST.get("subject_code", "").strip().upper()
            dept_id = request.POST.get("subject_department") or (staff_profile.department.id if staff_profile.department else None)
            year_val = request.POST.get("subject_year", "1")
            sem_val = request.POST.get("subject_sem", "1")
            subject_type_val = request.POST.get("subject_type", "theory")

            if subject_id and subject_id.isdigit():
                subj = get_object_or_404(Subject, id=int(subject_id))
                subj.teacher = request.user
                subj.save()
                messages.success(request, f"Assigned subject '{subj.name}' ({subj.code}) to your handled subjects!")
            elif new_subject_name and new_subject_code:
                if Subject.objects.filter(code=new_subject_code).exists():
                    messages.error(request, f"Subject code '{new_subject_code}' already exists. Please select it from existing subjects.")
                else:
                    dept = Department.objects.filter(id=dept_id).first() if dept_id else staff_profile.department
                    subj = Subject.objects.create(
                        name=new_subject_name,
                        code=new_subject_code,
                        department=dept,
                        year=int(year_val),
                        semester=int(sem_val),
                        subject_type=subject_type_val,
                        teacher=request.user
                    )
                    for u_num in range(1, 6):
                        unit_title = f"Lab Experiment {u_num} - {new_subject_name}" if subject_type_val == "lab" else f"{new_subject_name} - Part {u_num} Core Concepts"
                        Unit.objects.create(
                            subject=subj,
                            unit_number=u_num,
                            title=unit_title
                        )
                    messages.success(request, f"Created new subject '{new_subject_name}' ({new_subject_code}) and assigned to you!")
            else:
                messages.error(request, "Please select an existing subject or enter details for a new subject.")
            return redirect("staff_dashboard")

        elif action == "remove_handled_subject":
            subj_id = request.POST.get("subject_id")
            if subj_id and subj_id.isdigit():
                subj = get_object_or_404(Subject, id=int(subj_id))
                if subj.teacher == request.user or request.user.is_superuser:
                    subj.teacher = None
                    subj.save()
                    messages.success(request, f"Subject '{subj.name}' removed from your handled subjects.")
            return redirect("staff_dashboard")

        elif action == "upload_note":
            unit_id = request.POST.get("unit")
            title = request.POST.get("title", "").strip()
            note_file = request.FILES.get("file")

            if not unit_id or not title or not note_file:
                messages.error(request, "Please select a unit, enter a title, and attach a file.")
                return redirect("staff_dashboard")

            unit = get_object_or_404(Unit, id=unit_id)
            Note.objects.create(
                unit=unit,
                title=title,
                file=note_file,
                uploaded_by=request.user
            )
            messages.success(request, f"Note '{title}' uploaded successfully for {unit.subject.code} - Unit {unit.unit_number}!")
            return redirect("staff_dashboard")

        elif action == "delete_note":
            note_id = request.POST.get("note_id")
            if note_id and note_id.isdigit():
                note = get_object_or_404(Note, id=int(note_id))
                if note.uploaded_by == request.user or request.user.is_superuser:
                    n_title = note.title
                    note.delete()
                    messages.success(request, f"Note '{n_title}' deleted successfully.")
                else:
                    messages.error(request, "You can only delete notes uploaded by you.")
            return redirect("staff_dashboard")

    departments = Department.objects.all()
    handled_subjects = Subject.objects.filter(teacher=request.user).select_related("department").prefetch_related("units")
    
    if staff_profile.department:
        available_dept_subjects = Subject.objects.filter(department=staff_profile.department).exclude(teacher=request.user)
    else:
        available_dept_subjects = Subject.objects.exclude(teacher=request.user)

    handled_units = Unit.objects.filter(subject__in=handled_subjects).select_related("subject")
    uploaded_notes = Note.objects.filter(uploaded_by=request.user).select_related("unit", "unit__subject", "unit__subject__department").order_by("-uploaded_at")

    context = {
        "staff_profile": staff_profile,
        "departments": departments,
        "handled_subjects": handled_subjects,
        "available_dept_subjects": available_dept_subjects,
        "handled_units": handled_units,
        "uploaded_notes": uploaded_notes,
    }
    return render(request, "portal/staff_dashboard.html", context)


