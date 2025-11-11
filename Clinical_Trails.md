# 🧬 Clinical Trials Scraper — MongoDB Integration

This Python script automates the process of **fetching clinical trial data** from [ClinicalTrials.gov](https://clinicaltrials.gov/) using its **v2 API**, and stores the structured information in a **MongoDB collection**.  

It takes an **Excel sheet of doctor records** as input, searches for related clinical trials based on doctor names, and updates or inserts data into MongoDB.  

---

## 📘 Features

✅ Fetches data from the **ClinicalTrials.gov API (v2)**  
✅ Reads doctor details from an **Excel sheet**  
✅ Inserts or updates **clinical trial data** in MongoDB  
✅ Maintains **unique Record_Id** and **trial indexes**  
✅ Logs progress and failures for audit  
✅ Saves failed cases to an Excel file for review  

---

## ⚙️ Prerequisites

Make sure you have the following installed:

- Python 3.8+
- MongoDB Atlas or local MongoDB instance
- Required Python packages:

```bash
pip install requests pandas pymongo openpyxl

