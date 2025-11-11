# updated with publication type, journal country, for_search into single script/block 


import requests
import time
import pandas as pd
from collections import Counter, defaultdict
from pymongo import MongoClient
import xml.etree.ElementTree as ET
import logging
from datetime import datetime

# ========== Logging Setup ==========
logging.basicConfig(
    filename='pubmed_profiling.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ========== MongoDB Setup ==========
mongo_client = MongoClient("mongodb+srv://userSai:snehith@privatehospitals.yi5ve.mongodb.net/")
db = mongo_client["Derma"]
collection = db["pubmed"]

# ========== Utility Functions ==========
def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

def fetch_pmids_by_name(name, retmax=5000):
    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": f"{name}[Author]",
            "retmax": retmax,
            "retmode": "json"
        }
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        raise RuntimeError(f"Failed to fetch PMIDs for {name}: {e}")
    
def fetch_pmids_by_name_and_affiliation(name, retmax=5000):
    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        # Fixed affiliation
        # affiliation = "Christian Medical College"
        # Construct query: (Author Name[Author]) AND (Affiliation[Affiliation])
        # query = f"({name}[Author]) AND ({affiliation}[Affiliation])"
        query = f"{name}[Author]"

        params = {
            "db": "pubmed",
            "term": query,
            "retmax": retmax,
            "retmode": "json"
        }

        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        raise RuntimeError(f"Failed to fetch PMIDs for {name}: {e}")


def fetch_articles(pmids):
    summaries = []
    for i in range(0, len(pmids), 200):
        chunk = pmids[i:i+200]
        try:
            url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            params = {
                "db": "pubmed",
                "id": ",".join(chunk),
                "retmode": "xml"
            }
            r = requests.get(url, params=params)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            summaries.extend(root.findall("PubmedArticle"))
        except Exception as e:
            logging.warning(f"Error fetching article chunk {chunk[0]}–{chunk[-1]}: {e}")
        time.sleep(0.34)
    return summaries

def fetch_citations(pmids, batch_size=200, delay=0.34):
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    citation_map = {}
    for chunk in chunk_list(pmids, batch_size):
        ids_str = ",".join(chunk)
        params = {
            "dbfrom": "pubmed",
            "linkname": "pubmed_pubmed_citedin",
            "id": ids_str,
            "retmode": "xml"
        }
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for linkset in root.findall("LinkSet"):
                pmid = linkset.findtext("IdList/Id")
                citations = linkset.findall("LinkSetDb/Link/Id")
                citation_map[pmid] = len(citations)
        except Exception as e:
            logging.warning(f"Error fetching citations for {chunk[0]}–{chunk[-1]}: {e}")
        time.sleep(delay)
    return citation_map

# ========== Main Extractor ==========
def extract_publication_info(articles, doctor_name, citation_counts):
    dates = []
    coauthor_counter = Counter()
    coauthor_affiliations = defaultdict(set)
    publication_types = Counter()
    journal_counter = Counter()
    articles_info = []
    own_affiliations = []

    for article in articles:
        medline = article.find("MedlineCitation")
        article_data = medline.find("Article")
        journal = article_data.find("Journal")
        journal_name = journal.findtext("Title") if journal is not None else "Unknown"

        # Publication date
        pub_date_elem = journal.find("JournalIssue/PubDate") if journal is not None else None
        pub_date = "Unknown"
        if pub_date_elem is not None:
            year = pub_date_elem.findtext("Year")
            month = pub_date_elem.findtext("Month")
            day = pub_date_elem.findtext("Day")
            pub_date = f"{year}-{month if month else '01'}-{day if day else '01'}" if year else "Unknown"
            if year and year.isdigit():
                dates.append(int(year))

        # PMID, link, title
        pmid = medline.findtext("PMID")
        article_title = article_data.findtext("ArticleTitle", default="No Title")
        link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        # Publication types
        pub_type_list = [pt.text for pt in article_data.findall("PublicationTypeList/PublicationType") if pt.text]
        for pt in pub_type_list:
            publication_types[pt] += 1

        # Journal country
        medline_info = medline.find("MedlineJournalInfo")
        journal_country = medline_info.findtext("Country") if medline_info is not None else ""

        # Citations
        citation_count = citation_counts.get(pmid, 0)

        # Authors and affiliations
        authors_aff_map = {}
        authors = article_data.findall("AuthorList/Author")
        coauthors = []
        for author in authors:
            last_name = author.findtext("LastName", "")
            fore_name = author.findtext("ForeName", "")
            fullname = f"{fore_name} {last_name}".strip()
            affs = [aff.text for aff in author.findall("AffiliationInfo/Affiliation") if aff.text]
            if fullname:
                authors_aff_map[fullname] = affs if len(affs) > 1 else affs[0] if affs else None
            if fullname.lower() != doctor_name.lower():
                coauthor_counter[fullname] += 1
                for aff in affs:
                    coauthor_affiliations[fullname].add(aff)
                coauthors.append(fullname)
            else:
                own_affiliations.extend(affs)

        # Keywords and MeSH terms
        keywords = [kw.text for kw in article_data.findall("KeywordList/Keyword") if kw.text]

        mesh_major_topics = []
        mesh_subheadings = []
        mesh_terms = []
        mesh_heading_list = medline.find("MeshHeadingList")
        if mesh_heading_list is not None:
            for mesh in mesh_heading_list.findall("MeshHeading"):
                descriptor = mesh.find("DescriptorName")
                if descriptor is not None:
                    term_text = descriptor.text
                    if descriptor.attrib.get("MajorTopicYN") == "Y":
                        mesh_major_topics.append(term_text)
                    else:
                        mesh_terms.append(term_text)
                    for qualifier in mesh.findall("QualifierName"):
                        mesh_subheadings.append(qualifier.text)

        # Supplementary Concepts
        supplementary_concepts = []
        supp_list = medline.find("SupplementaryConceptList")
        if supp_list is not None:
            for supp in supp_list.findall("SupplementaryConcept"):
                name = supp.findtext("NameOfSubstance")
                if name:
                    supplementary_concepts.append(name)

        # Append article details
        articles_info.append({
            "pmid": pmid,
            "title": article_title,
            "journal": journal_name,
            "link": link,
            "citations": citation_count,
            "publication_date": pub_date,
            "coauthors": coauthors,
            "authors_with_affiliations": authors_aff_map,
            "keywords": keywords,
            "topics": mesh_terms,
            "publication_type": pub_type_list,
            "journal_country": journal_country,
            "for_search": {
                "MeSH Major Topics": mesh_major_topics,
                "MeSH Subheadings": mesh_subheadings,
                "MeSH Terms": mesh_terms,
                "Other Terms": keywords,
                "Supplementary Concepts": supplementary_concepts
            }
        })

    # Summary calculations
    total_articles = len(articles_info)
    earliest_year = min(dates) if dates else None
    latest_year = max(dates) if dates else None
    yearwise_count = Counter(str(y) for y in dates if y)
    avg_publications = (total_articles / (latest_year - earliest_year + 1)) if earliest_year and latest_year else 0
    unique_coauthors = len(coauthor_counter)
    avg_coauthors_per_article = sum(len(a["coauthors"]) for a in articles_info) / total_articles if total_articles else 0
    top_10_coauthors = coauthor_counter.most_common(10)
    top_10_coauthors_output = [
        {"name": name, "count": count, "affiliations": list(coauthor_affiliations[name])}
        for name, count in top_10_coauthors
    ]
    unique_journal_count = len(journal_counter)
    total_citations = sum(citation_counts.get(a["pmid"], 0) for a in articles_info)
    avg_citations = total_citations / total_articles if total_articles else 0
    top_5_cited_articles_output = sorted(
        [
            {
                "pmid": a["pmid"],
                "title": a["title"],
                "journal": a["journal"],
                "link": a["link"],
                "citations": a["citations"],
                "publication_date": a["publication_date"]
            }
            for a in articles_info
        ],
        key=lambda x: x["citations"],
        reverse=True
    )[:5]

    return {
        "total_articles": total_articles,
        "earliest_publication_year": earliest_year,
        "latest_publication_year": latest_year,
        "yearwise_published_articles_count": dict(yearwise_count),
        "averge_number_of_publications_between_earliest_and_latest_years": avg_publications,
        "total_number_of_unique_coauthors_associated_with": unique_coauthors,
        "average_coauthors_per_article": avg_coauthors_per_article,
        "top_10_coauthors": top_10_coauthors_output,
        "publication_types": dict(publication_types),
        "journals": dict(journal_counter),
        "unique_journal_count": unique_journal_count,
        "total_citations": total_citations,
        "average_citations_per_article": avg_citations,
        "top_5_cited_artciles": top_5_cited_articles_output,
        "affiliations": list(set(own_affiliations)),
        "articles": articles_info
    }

# ========== Process Function ==========
failed_logs = []

def process_doctor(record_id, full_name):
    try:
        pmids = fetch_pmids_by_name_and_affiliation(full_name)
        if not pmids:
            reason = "No publications found"
            logging.warning(f"{full_name} – {reason}")
            failed_logs.append({"Record_Id": record_id, "Full_Name": full_name, "Reason": reason})
            return
        articles = fetch_articles(pmids)
        if not articles:
            reason = "No article data retrieved"
            logging.warning(f"{full_name} – {reason}")
            failed_logs.append({"Record_Id": record_id, "Full_Name": full_name, "Reason": reason})
            return
        citation_counts = fetch_citations(pmids)
        profile = extract_publication_info(articles, full_name, citation_counts)
        profile.update({"Record_Id": record_id, "Full_Name": full_name})
        collection.update_one({"Record_Id": record_id}, {"$set": profile}, upsert=True)
        logging.info(f"✅ Processed {full_name}: {len(pmids)} articles")
    except Exception as e:
        logging.error(f"❌ Error processing {full_name}: {str(e)}")
        failed_logs.append({"Record_Id": record_id, "Full_Name": full_name, "Reason": str(e)})

# ========== Execution ==========
if __name__ == "__main__":
    input_file = r"C:\Users\Shanthan\Downloads\Derma_Batch 1,2&3_Final_For_Product.xlsx"
    df = pd.read_excel(input_file)

    for _, row in df.iterrows():
        process_doctor(row["Record_Id"], row["Full_Name"])

    if failed_logs:
        pd.DataFrame(failed_logs).to_excel("failed_searches2.xlsx", index=False)
        logging.info("🚨 Logged failed/empty searches to failed_searches2.xlsx")
