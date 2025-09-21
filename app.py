# app.py
"""
Elix backend (FastAPI)

Endpoints:
- POST /login          -> { username, password }  returns {status, session_id, message}
- POST /ask            -> { query, session_id }   returns insights JSON (answer + data)
- GET  /download/{id}  -> returns PDF filename for the student's career plan
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import pandas as pd
import os
import uuid
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# ---------- Configuration ----------
DATASET_FILE = "DATASET.csv"   # Put your dataset here
PORT = 8000

# ---------- FastAPI init ----------
app = FastAPI(title="Elix - Career Advisor (Enhanced)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Simple in-memory session/chat store ----------
SESSIONS = {}  # session_id -> {"history": [ {"sender":..., "msg":...} ], "user": username_or_guest}

# ---------- Demo users ----------
USERS = {"kirubha": "12345", "admin": "admin123"}

# ---------- Utility helpers ----------
def load_dataset(path=DATASET_FILE):
    if not os.path.exists(path):
        sample = pd.DataFrame({
            "Student_ID": ["1001", "1002", "1003"],
            "Name": ["Aishwarya Iyer", "Aarav Kumar", "Priya Sharma"],
            "GPA": [9.06, 8.2, 7.8],
            "10th_Marks": [95, 88, 85],
            "12th_Marks": [92, 86, 83],
            "Skills": ["Excel;Power BI;NumPy;JavaScript;SQL", "Python;Machine Learning;SQL", "Java;Networks;Security"],
            "Interested_Domain": ["Data", "AI", "Cybersecurity"],
            "Career_Suggestions": [
                "Data Analyst;Business Analyst;Data Scientist;BI Developer",
                "ML Engineer;Data Scientist;AI Researcher;MLOps Engineer",
                "Security Engineer;SOC Analyst;Penetration Tester;Security Consultant"
            ],
            "Internships": ["Analytics Intern at X;BI Intern at Y", "ML Intern at Z", "Security Intern at Q"],
            "Certifications": ["Power BI Cert;Excel Advanced", "ML Nanodegree;Python Cert", "CEH;Network+"]
        })
        sample.to_csv(path, index=False)
    df = pd.read_csv(path, dtype=str)
    for col in ["GPA","10th_Marks","12th_Marks"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

DATA = load_dataset()

DOMAIN_SKILL_MAP = {
    "AI": ["Python","Machine Learning","Deep Learning","Statistics","TensorFlow","PyTorch"],
    "Data": ["SQL","Excel","Power BI","Tableau","Pandas","NumPy","Statistics"],
    "Cybersecurity": ["Linux","Networking","Ethical Hacking","Firewalls","Cryptography"],
    "Web Development": ["HTML","CSS","JavaScript","React","Node.js"]
}

def safe_split(s):
    if s is None or pd.isna(s): return []
    if isinstance(s, float): return []
    for sep in [";", ","]:
        if sep in s:
            return [p.strip() for p in s.split(sep) if p.strip()]
    return [s.strip()]

def find_profile(query):
    q = str(query).strip().lower()
    for _, row in DATA.iterrows():
        sid = str(row.get("Student_ID","") or "").strip().lower()
        name = str(row.get("Name","") or "").strip().lower()
        domain = str(row.get("Interested_Domain","") or "").strip().lower()
        skills = ";".join(safe_split(row.get("Skills","") or "")).lower()
        if q == sid or q == name or q in name or q == domain:
            return row
        for sk in safe_split(row.get("Skills","") or ""):
            if sk.strip().lower() in q:
                return row
    return None

def performance_level(gpa, m10, m12):
    score = 0.0
    try:
        if not pd.isna(gpa):
            score += (float(gpa)/10.0) * 50.0
    except:
        pass
    try:
        if not pd.isna(m10):
            score += (float(m10)/100.0) * 25.0
    except:
        pass
    try:
        if not pd.isna(m12):
            score += (float(m12)/100.0) * 25.0
    except:
        pass
    if score >= 85:
        level = "Excellent"
    elif score >= 70:
        level = "Good"
    else:
        level = "Needs Improvement"
    return level, round(score,1)

def compute_skill_fit(skills_list, domain):
    reqs = DOMAIN_SKILL_MAP.get(domain, [])
    skills_lower = [s.lower() for s in skills_list]
    values = []
    for r in reqs:
        if r.lower() in skills_lower:
            values.append(100)
        else:
            match = any(r_part.lower() in sk for sk in skills_lower for r_part in r.split())
            values.append(60 if match else 20)
    return reqs, values

def build_career_weights(profile_row):
    careers = safe_split(str(profile_row.get("Career_Suggestions","") or ""))
    if not careers:
        return []
    even = round(100.0 / len(careers), 1)
    weights = [even] * len(careers)
    diff = round(100.0 - sum(weights), 1)
    if diff != 0:
        weights[-1] += diff
    return [{"career": c, "weight": w} for c,w in zip(careers, weights)]

# ---------- Routes ----------
@app.post("/login")
async def login(request: Request):
    try:
        data = await request.json()
    except:
        data = {}
    username = data.get("username","")
    password = data.get("password","")
    if not username or not password:
        sid = str(uuid.uuid4())
        SESSIONS[sid] = {"history": [], "user": "guest"}
        return {"status": "guest", "session_id": sid, "message": "Guest session started"}
    if username in USERS and USERS[username] == password:
        SESSIONS[username] = {"history": [], "user": username}
        return {"status": "ok", "session_id": username, "message": f"Welcome {username}"}
    return {"status": "error", "message": "Invalid credentials"}

@app.post("/ask")
async def ask(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    query = str(data.get("query","")).strip()
    session_id = data.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = {"history": [], "user": "guest"}

    SESSIONS.setdefault(session_id, {"history": [], "user": "guest"})
    SESSIONS[session_id]["history"].append({"sender":"user", "msg": query})

    if not query:
        return {"answer": "Please send a Student ID, Name, or skill."}

    profile = find_profile(query)
    if profile is None:
        message = "I couldn’t find your profile. Please tell me your Student ID, Name, or Skills."
        SESSIONS[session_id]["history"].append({"sender":"elix", "msg": message})
        return {"answer": message}

    student_id = str(profile.get("Student_ID","") or "")
    name = str(profile.get("Name","") or "")
    gpa = profile.get("GPA", None)
    try: gpa = float(gpa) if not pd.isna(gpa) else None
    except: gpa = None
    m10 = profile.get("10th_Marks", profile.get("10th Marks", None))
    m12 = profile.get("12th_Marks", profile.get("12th Marks", None))
    try: m10 = float(m10) if m10 is not None and not pd.isna(m10) else None
    except: m10 = None
    try: m12 = float(m12) if m12 is not None and not pd.isna(m12) else None
    except: m12 = None

    skills = safe_split(str(profile.get("Skills","") or ""))
    domain = str(profile.get("Interested_Domain","") or "")
    careers = build_career_weights(profile)
    internships = safe_split(str(profile.get("Internships","") or ""))
    certifications = safe_split(str(profile.get("Certifications","") or ""))

    level, perf_score = performance_level(gpa, m10, m12)
    radar_labels, radar_values = compute_skill_fit(skills, domain)

    # summary text
    top_careers = ", ".join([c["career"] for c in careers[:3]]) if careers else "some options"
    summary = f"Hi {name}. Based on your profile (G P A {gpa}), top suggested careers include: {top_careers}. Your performance level is {level}."

    # --------- Domain-specific roadmap + smarter internships/certs ---------
    roadmaps = {
        "AI": [
            {"step": "Learn Python + ML basics", "desc": "Cover Python, statistics, and ML frameworks"},
            {"step": "Deep Learning Projects", "desc": "Work on CNN, NLP projects"},
            {"step": "Internship in AI/ML", "desc": "Apply AI concepts in real-world tasks"},
            {"step": "Certifications", "desc": "TensorFlow, AWS ML Specialty"},
            {"step": "Placement Prep", "desc": "Mock interviews + case studies"}
        ],
        "Cybersecurity": [
            {"step": "Networking + OS Fundamentals", "desc": "Linux, Windows security basics"},
            {"step": "Hands-on Projects", "desc": "Firewalls, intrusion detection labs"},
            {"step": "Internship in Security", "desc": "SOC or PenTest roles"},
            {"step": "Certifications", "desc": "CEH, CompTIA Security+"},
            {"step": "Placement Prep", "desc": "CTF challenges, resume building"}
        ],
        "Data": [
            {"step": "Excel + SQL Mastery", "desc": "Learn query optimization & reporting"},
            {"step": "Visualization Projects", "desc": "Power BI / Tableau dashboards"},
            {"step": "Internship in Data Analytics", "desc": "Business Analyst or Data Analyst roles"},
            {"step": "Certifications", "desc": "Google Data Analytics, Power BI Cert"},
            {"step": "Placement Prep", "desc": "Case study solving, mock interviews"}
        ],
        "Web Development": [
            {"step": "Frontend Skills", "desc": "Master HTML, CSS, JavaScript"},
            {"step": "Backend Basics", "desc": "Learn Node.js, FastAPI, or Django"},
            {"step": "Internship in Web Dev", "desc": "Work as a frontend or full-stack intern"},
            {"step": "Certifications", "desc": "ReactJS, AWS Developer"},
            {"step": "Placement Prep", "desc": "LeetCode practice, mock interviews"}
        ]
    }
    selected_roadmap = roadmaps.get(domain, roadmaps["Data"])

    default_internships = {
        "AI": ["AI Intern at Google", "ML Intern at TCS"],
        "Cybersecurity": ["SOC Analyst Intern", "Network Security Intern"],
        "Data": ["Analytics Intern at Deloitte", "BI Developer Intern at Infosys"],
        "Web Development": ["Frontend Intern at Startup", "Full-Stack Intern at Wipro"]
    }
    default_certifications = {
        "AI": ["AWS ML Specialty", "TensorFlow Developer"],
        "Cybersecurity": ["CEH", "CompTIA Security+"],
        "Data": ["Google Data Analytics", "Power BI Certification"],
        "Web Development": ["ReactJS Certification", "AWS Developer Associate"]
    }

    internships = internships or default_internships.get(domain, [])
    certifications = certifications or default_certifications.get(domain, [])

    insights = {
        "student_id": student_id,
        "name": name,
        "gpa": gpa,
        "marks": {"10th": m10, "12th": m12},
        "skills": skills,
        "domain": domain,
        "career_suggestions": careers,
        "internships": internships,
        "certifications": certifications,
        "performance": {"level": level, "score": perf_score},
        "radar": {"labels": radar_labels, "values": radar_values},
        "summary_text": summary,
        "roadmap": selected_roadmap
    }

    SESSIONS[session_id]["history"].append({"sender":"elix", "msg": summary})
    return {"answer": summary, "insights": insights, "session_id": session_id}

@app.get("/download/{student_id}")
async def download_plan(student_id: str):
    row = None
    for _, r in DATA.iterrows():
        if str(r.get("Student_ID","") or "").strip() == student_id.strip():
            row = r
            break
    if row is None:
        raise HTTPException(status_code=404, detail="Student not found")

    name = str(row.get("Name","") or "Student")
    careers = safe_split(str(row.get("Career_Suggestions","") or ""))
    certifications = safe_split(str(row.get("Certifications","") or ""))
    internships = safe_split(str(row.get("Internships","") or ""))

    filename = f"{name.replace(' ','_')}_career_plan.pdf"
    c = canvas.Canvas(filename, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, 750, f"Career Plan — {name} (ID: {student_id})")

    c.setFont("Helvetica", 12)
    y = 720
    c.drawString(40, y, f"GPA: {row.get('GPA','N/A')}")
    y -= 20
    c.drawString(40, y, f"10th Marks: {row.get('10th_Marks','N/A')}, 12th Marks: {row.get('12th_Marks','N/A')}")
    y -= 30

    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Career Suggestions:")
    y -= 18
    c.setFont("Helvetica", 12)
    for c_item in careers:
        c.drawString(60, y, f"- {c_item}")
        y -= 16
        if y < 80:
            c.showPage()
            y = 750

    y -= 10
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Certifications:")
    y -= 18
    c.setFont("Helvetica", 12)
    for cert in certifications:
        c.drawString(60, y, f"- {cert}")
        y -= 16
        if y < 80:
            c.showPage()
            y = 750

    y -= 10
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Internships / Experience:")
    y -= 18
    c.setFont("Helvetica", 12)
    for it in internships:
        c.drawString(60, y, f"- {it}")
        y -= 16
        if y < 80:
            c.showPage()
            y = 750

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Serve static files (frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

    c.save()
    return FileResponse(filename, filename=filename, media_type="application/pdf")
