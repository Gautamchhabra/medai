# symptom_checker/views.py

import json
from huggingface_hub import InferenceClient
from django.shortcuts import render, redirect
from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime
# Replace the huggingface_hub import with openai
from .models import SymptomHistory, EmergencyContact, UserProfile
from .forms import LoginForm, RegisterForm, UserProfileForm, EmergencyContactForm

import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import inch, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from html.parser import HTMLParser

# ==================== PUBLIC PAGES ====================

def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'symptom_checker/home.html')

@login_required
def general_medicines(request):
    return render(request, 'symptom_checker/general_medicines.html')

@login_required
def health_tips(request):
    tips = [
        {'title': 'Stay Hydrated', 'description': 'Drink at least 8-10 glasses of water daily.', 'icon': '💧', 'category': 'daily'},
        {'title': 'Balanced Diet', 'description': 'Include fruits, vegetables, proteins in your meals.', 'icon': '🥗', 'category': 'nutrition'},
        {'title': 'Regular Exercise', 'description': '30 minutes of physical activity 5 days a week.', 'icon': '🏃', 'category': 'fitness'},
        {'title': 'Adequate Sleep', 'description': '7-9 hours of quality sleep every night.', 'icon': '😴', 'category': 'daily'},
        {'title': 'Stress Management', 'description': 'Practice meditation or deep breathing.', 'icon': '🧘', 'category': 'mental'},
        {'title': 'Hand Hygiene', 'description': 'Wash hands regularly to prevent infections.', 'icon': '🧼', 'category': 'hygiene'},
        {'title': 'Regular Checkups', 'description': 'Visit your doctor for annual checkups.', 'icon': '🩺', 'category': 'prevention'},
        {'title': 'Limit Screen Time', 'description': 'Take breaks from screens every 20 minutes.', 'icon': '📱', 'category': 'daily'},
        {'title': 'No Smoking', 'description': 'Avoid tobacco to reduce health risks.', 'icon': '🚭', 'category': 'prevention'},
    ]
    return render(request, 'symptom_checker/health_tips.html', {'tips': tips})

@login_required
def about(request):
    return render(request, 'symptom_checker/about.html')

@login_required
def symptom_checker(request):
    return render(request, 'symptom_checker/symptom_checker.html')

# ==================== AUTHENTICATION ====================

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name}!')
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    return render(request, 'symptom_checker/login.html', {'form': form})

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user)
            login(request, user)
            messages.success(request, f'Account created! Welcome, {user.first_name}!')
            return redirect('dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = RegisterForm()
    return render(request, 'symptom_checker/register.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')

# ==================== PROTECTED PAGES ====================

@login_required
def dashboard(request):
    total_checks = SymptomHistory.objects.filter(user=request.user).count()
    recent_checks = SymptomHistory.objects.filter(user=request.user)[:5]
    emergency_contacts = EmergencyContact.objects.filter(user=request.user)
    return render(request, 'symptom_checker/dashboard.html', {
        'total_checks': total_checks,
        'recent_checks': recent_checks,
        'emergency_contacts': emergency_contacts,
    })

@login_required
def history(request):
    histories = SymptomHistory.objects.filter(user=request.user)
    return render(request, 'symptom_checker/history.html', {'histories': histories})

@login_required
def emergency(request):
    if request.method == 'POST':
        form = EmergencyContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.user = request.user
            if contact.is_primary:
                EmergencyContact.objects.filter(user=request.user, is_primary=True).update(is_primary=False)
            contact.save()
            messages.success(request, 'Emergency contact added!')
            return redirect('emergency')
    else:
        form = EmergencyContactForm()
    contacts = EmergencyContact.objects.filter(user=request.user)
    return render(request, 'symptom_checker/emergency.html', {'form': form, 'contacts': contacts})

@login_required
def profile(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        profile_form = UserProfileForm(request.POST, instance=user_profile)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, 'Profile updated!')
            return redirect('profile')
    else:
        profile_form = UserProfileForm(instance=user_profile)
    return render(request, 'symptom_checker/profile.html', {'profile_form': profile_form, 'user': request.user})

# ==================== AJAX ENDPOINT ====================

@csrf_exempt
def analyze_symptoms(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method.'})
    
    try:
        data = json.loads(request.body)
        symptoms = data.get('symptoms', '').strip()
        
        if not symptoms:
            return JsonResponse({'success': False, 'error': 'Please enter some symptoms.'})
        
        if len(symptoms) < 10:
            return JsonResponse({'success': False, 'error': 'Please describe in more detail (at least 10 characters).'})
        
        analysis = get_medical_analysis(symptoms)
        
        if request.user.is_authenticated:
            SymptomHistory.objects.create(
                user=request.user,
                symptoms=symptoms,
                analysis=analysis
            )
        
        return JsonResponse({'success': True, 'analysis': analysis})
    
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request format.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def get_medical_analysis(symptoms):
    """Call Hugging Face API via OpenAI-compatible endpoint"""
    
    prompt = f"""You are a medical information assistant for educational purposes only. You are NOT a real doctor.

Symptoms: {symptoms}

Provide analysis in this exact HTML format (respond ONLY with HTML, no other text before or after):

<div class="result-section">
<h3>Possible Conditions</h3>
<ul>
<li><strong>Condition 1:</strong> Brief explanation of why this matches</li>
<li><strong>Condition 2:</strong> Brief explanation of why this matches</li>
<li><strong>Condition 3:</strong> Brief explanation of why this matches</li>
</ul>
</div>

<div class="result-section">
<h3>Precautions</h3>
<ul>
<li>Precaution 1 with details</li>
<li>Precaution 2 with details</li>
<li>Precaution 3 with details</li>
<li>Precaution 4 with details</li>
</ul>
</div>

<div class="result-section">
<h3>Possible Medications (India)</h3>
<ul>
<li><strong>Medication 1:</strong> Generic name + Indian brand, what it does</li>
<li><strong>Medication 2:</strong> Generic name + Indian brand, what it does</li>
<li><strong>Medication 3:</strong> Generic name + Indian brand, what it does</li>
</ul>
</div>

<div class="disclaimer-box">
<p><strong>DISCLAIMER:</strong> Not a real diagnosis. Educational only. Consult a doctor. Do not self-medicate.</p>
</div>"""

    try:
        # Use Hugging Face's OpenAI-compatible endpoint
        client = InferenceClient(
            base_url="https://router.huggingface.co/v1",
            api_key=settings.HF_TOKEN,
        )
        
        response = client.chat.completions.create(
            model="moonshotai/Kimi-K2-Instruct-0905",
            messages=[
                {
                    "role": "system",
                    "content": "You are a medical information assistant. Always respond with ONLY the requested HTML format, no other text."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=1000,
            temperature=0.3
        )
        
        analysis = response.choices[0].message.content.strip()
        
        # Clean up markdown code blocks if present
        if analysis.startswith("```html"):
            analysis = analysis[7:]
        if analysis.startswith("```"):
            analysis = analysis[3:]
        if analysis.endswith("```"):
            analysis = analysis[:-3]
        
        return analysis.strip()
        
    except Exception as e:
        # Fallback: Try a different model
        try:
            response = client.chat.completions.create(
                model="Qwen/Qwen2.5-7B-Instruct",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.3
            )
            analysis = response.choices[0].message.content.strip()
            return analysis
        except Exception as e2:
            return f"""<div class="error-box">
                <p><strong>API Error:</strong> {str(e2)}</p>
                <p>Please try again in a few seconds.</p>
            </div>"""
        
# ==================== PDF GENERATION ====================

class HTMLStripper(HTMLParser):
    """Strip HTML tags and get plain text"""
    def __init__(self):
        super().__init__()
        self.text = ""
        self.skip = False
    
    def handle_starttag(self, tag, attrs):
        if tag in ['br', 'li']:
            self.text += "\n• "
        elif tag in ['p', 'div', 'h3', 'h4']:
            self.text += "\n"
        elif tag in ['strong', 'b']:
            pass
    
    def handle_endtag(self, tag):
        if tag in ['p', 'div', 'h3', 'h4', 'ul']:
            self.text += "\n"
        elif tag in ['li']:
            pass
    
    def handle_data(self, data):
        self.text += data.strip() + " "


def strip_html(html_text):
    """Convert HTML to clean text"""
    stripper = HTMLStripper()
    stripper.feed(html_text)
    text = stripper.text
    # Clean up multiple spaces and newlines
    import re
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()


@login_required
def download_report(request, history_id):
    """Generate and download PDF report for a symptom check"""
    # Get the history record (ensure it belongs to current user)
    history = get_object_or_404(SymptomHistory, id=history_id, user=request.user)
    
    # Create a buffer
    buffer = io.BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm
    )
    
    # Styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=22,
        textColor=HexColor('#00695c'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=HexColor('#666666'),
        alignment=TA_CENTER,
        spaceAfter=20,
        fontName='Helvetica'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=HexColor('#00695c'),
        spaceBefore=15,
        spaceAfter=8,
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=10,
        textColor=HexColor('#333333'),
        spaceAfter=6,
        leading=16,
        fontName='Helvetica'
    )
    
    disclaimer_style = ParagraphStyle(
        'Disclaimer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=HexColor('#e65100'),
        alignment=TA_CENTER,
        fontName='Helvetica-Oblique',
        spaceBefore=10,
        spaceAfter=10
    )
    
    # Build content
    elements = []
    
    # Logo and Title
    elements.append(Paragraph("🏥 MediAI", title_style))
    elements.append(Paragraph("AI-Powered Health Analysis Report", subtitle_style))
    
    # Horizontal line
    elements.append(HRFlowable(
        width="100%",
        thickness=1,
        color=HexColor('#009688'),
        spaceAfter=15
    ))
    
    # Patient Info Section
    elements.append(Paragraph("📋 Patient Information", heading_style))
    
    patient_data = [
        ['Patient Name:', f"{request.user.first_name} {request.user.last_name}"],
        ['Email:', request.user.email or 'Not provided'],
        ['Report Date:', history.created_at.strftime('%B %d, %Y at %I:%M %p')],
        ['Report ID:', f'MED-{history.id:06d}'],
    ]
    
    patient_table = Table(patient_data, colWidths=[100, 350])
    patient_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#00695c')),
        ('TEXTCOLOR', (1, 0), (1, -1), HexColor('#333333')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(patient_table)
    elements.append(Spacer(1, 15))
    
    # Symptoms Section
    elements.append(Paragraph("📝 Reported Symptoms", heading_style))
    
    # Wrap symptoms text
    symptoms_text = history.symptoms.replace('\n', '<br/>')
    elements.append(Paragraph(symptoms_text, body_style))
    elements.append(Spacer(1, 10))
    
    # Analysis Section Header
    elements.append(HRFlowable(
        width="100%",
        thickness=0.5,
        color=HexColor('#e0e0e0'),
        spaceAfter=10
    ))
    elements.append(Paragraph("🔍 AI Analysis Results", heading_style))
    
    # Parse the HTML analysis and add to PDF
    analysis_text = strip_html(history.analysis)
    
    # Split into sections
    sections = analysis_text.split('\n\n')
    
    for section in sections:
        if section.strip():
            # Check if it's a heading
            if section.strip().startswith('•'):
                lines = section.strip().split('\n')
                for line in lines:
                    clean_line = line.replace('•', '').strip()
                    if clean_line:
                        elements.append(Paragraph(f"• {clean_line}", body_style))
            else:
                # Check for section headers
                first_line = section.strip().split('\n')[0]
                if any(keyword in first_line.lower() for keyword in ['condition', 'precaution', 'medication', 'disclaimer']):
                    elements.append(Paragraph(f"<b>{first_line}</b>", heading_style))
                    remaining = '\n'.join(section.strip().split('\n')[1:])
                    if remaining.strip():
                        for line in remaining.split('\n'):
                            clean_line = line.replace('•', '').strip()
                            if clean_line:
                                elements.append(Paragraph(f"• {clean_line}", body_style))
                else:
                    for line in section.split('\n'):
                        clean_line = line.replace('•', '').strip()
                        if clean_line:
                            elements.append(Paragraph(f"• {clean_line}", body_style))
    
    # Disclaimer
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(
        width="100%",
        thickness=1,
        color=HexColor('#ff9800'),
        spaceAfter=10
    ))
    
    disclaimer_text = """
    <b>⚠️ IMPORTANT DISCLAIMER</b><br/><br/>
    This report is generated for <b>educational purposes only</b>. 
    It is NOT a medical diagnosis. The AI-generated information may not be accurate. 
    Always consult a licensed healthcare professional for proper diagnosis and treatment. 
    Do not self-medicate based on this report. In case of emergency, call 108 (India) immediately.
    """
    elements.append(Paragraph(disclaimer_text, disclaimer_style))
    
    # Footer
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        f"© 2026 MediAI • Generated on {history.created_at.strftime('%B %d, %Y')} • Report ID: MED-{history.id:06d}",
        ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=7,
            textColor=HexColor('#999999'),
            alignment=TA_CENTER,
            fontName='Helvetica'
        )
    ))
    
    # Build PDF
    doc.build(elements)
    
    # Get the buffer content
    buffer.seek(0)
    
    # Create filename
    filename = f"MediAI_Report_{history.id:06d}_{history.created_at.strftime('%Y%m%d')}.pdf"
    
    # Return as downloadable file
    return FileResponse(
        buffer,
        as_attachment=True,
        filename=filename,
        content_type='application/pdf'
    )