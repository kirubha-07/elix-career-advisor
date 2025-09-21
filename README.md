# Elix — Career Advisor

A personalized AI-powered career advisor prototype built for the **GenAI Hackathon 2025**.

---

## 🚀 Features
- 🔑 Login or Guest access  
- 📊 Query by Student ID, Name, or Skills  
- 🎯 Career Suggestions (Treemap visualization)  
- 🧭 Skill Fit Radar (gap analysis vs industry needs)  
- 📝 Personalized Roadmap with actionable steps  
- 📄 Downloadable PDF Career Plan  

---

## 🛠 Tech Stack
- **Backend**: FastAPI, Pandas, ReportLab  
- **Frontend**: HTML, CSS, JavaScript (Plotly.js)  
- **Deployment**: Render / Railway  

---

## ⚡ Run Locally

Clone the repo and install dependencies:

```bash
git clone https://github.com/<your-username>/elix-career-advisor.git
cd elix-career-advisor

pip install -r requirements.txt
uvicorn app:app --reload
