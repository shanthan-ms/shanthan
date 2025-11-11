# 📚 PubMed Research Profiling — Data Extraction & Analysis

This repository contains Python scripts that automate the process of **extracting, processing, and analyzing PubMed research data** for doctors or researchers.  
Both scripts are designed to work together — the first retrieves raw PubMed data, and the second processes it into structured insights stored in **MongoDB**.

---

## 🧩 Overview

| Script | Description |
|---------|--------------|
| **pubmed_scraper.py** | Fetches publication data from the NCBI PubMed API (E-Utilities). Extracts metadata like titles, journals, MeSH terms, and author details. |
| **pubmed_analyzer.py** | Processes the scraped data to derive insights like coauthor networks, publication counts, citation analytics, and stores results in MongoDB. |

Each script can be executed independently or as part of a full research profiling workflow.

---

## 📘 Features

### 🧪 PubMed Scraper
- Searches PubMed using the NCBI E-Utilities API (`esearch` + `esummary` + `efetch`)
- Extracts:
  - PMID, title, abstract, journal, keywords, publication types
  - Author details, affiliations, MeSH Major Topics
  - Journal country and year of publication
- Handles pagination and rate limiting automatically
- Stores raw publication data in MongoDB or JSON

### 📊 PubMed Analyzer
- Reads data collected by the scraper
- Computes:
  - Total and average publications per doctor
  - Earliest and latest publication years
  - Year-wise article distribution
  - Top coauthors and their affiliations
  - Top cited papers and citation averages
- Writes processed analytics back to MongoDB

---

## ⚙️ Prerequisites

Make sure you have the following installed:

- **Python 3.8+**
- **MongoDB Atlas** or local MongoDB instance
- Required Python libraries:

```bash
pip install requests pandas pymongo openpyxl
