import requests
import pandas as pd
from pymongo import MongoClient, ASCENDING
from datetime import datetime
import logging
import os

# MongoDB Setup (localhost)
client = MongoClient("paste your mongodb connection string")
db = client['Derma']
collection = db['clinical']

# Create indexes
collection.create_index(
    [("Record_Id", ASCENDING)],
    unique=True,
    name="unique_record_id"
)

collection.create_index(
    [("Record_Id", ASCENDING), ("clinical_trials.overview.nctId", ASCENDING)],
    name="record_trial_index"
)

# Setup logging
LOG_FILE = "search_log.txt"
FAILED_FILE = "failed_searches.xlsx"
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(message)s')
failed_records = []

# Read input Excel
input_df = pd.read_excel("excel sheet path")

# Helper function to safely get nested values
def get_nested(data, keys, default=None):
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return default
    return data if data is not None else default

# Build overview
def build_overview(protocol, record_id, dr_name):
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    contacts_module = protocol.get("contactsLocationsModule", {})
    design_module = protocol.get("designModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    description = protocol.get("descriptionModule", {})
    interventions = protocol.get("armsInterventionsModule", {})

    return {
        "Record_Id": record_id,
        "doctorName": dr_name,
        "nctId": identification.get("nctId"),
        "organization": {
            "fullName": identification.get("organization", {}).get("fullName"),
            "class": identification.get("organization", {}).get("class")
        },
        "briefTitle": identification.get("briefTitle"),
        "officialTitle": identification.get("officialTitle"),
        "statusVerifiedDate": status.get("statusVerifiedDate"),
        "startDate": get_nested(status, ["startDateStruct", "date"]),
        "primaryCompletionDate": get_nested(status, ["primaryCompletionDateStruct", "date"]),
        "completionDate": get_nested(status, ["completionDateStruct", "date"]),
        "briefSummary": get_nested(description, ["briefSummary"]),
        "primaryInvestigatorName": get_nested(sponsor_module, ["responsibleParty", "investigatorFullName"]),
        "primaryInvestigatorTitle": get_nested(sponsor_module, ["responsibleParty", "investigatorTitle"]),
        "primaryInvestigatorAffiliation": get_nested(sponsor_module, ["responsibleParty", "investigatorAffiliation"]),
        "leadSponsorName": get_nested(sponsor_module, ["leadSponsor", "name"]),
        "keywords": conditions_module.get("keywords", []),
        "condition": get_nested(conditions_module, ["conditions", 0]),
        "studyType": design_module.get("studyType"),
        "phase": get_nested(design_module, ["phases", 0]),
        "interventionName": get_nested(interventions, ["armGroups", 0, "interventionNames", 0]),
        "enrollmentCount": get_nested(design_module, ["enrollmentInfo", "count"]),
        "centralContacts": contacts_module.get("centralContacts", []),
        "overallOfficials": contacts_module.get("overallOfficials", []),
        "locations": contacts_module.get("locations", [])
    }


# Scrape function
def scrap_clinical_trials(record_id, dr_name):
    url = "https://clinicaltrials.gov/api/v2/studies"
    headers = {"accept": "application/json"}
    page_token = None
    page_count = 0
    max_pages = 100
    new_trials_count = 0
    updated_trials_count = 0

    try:
        while True:
            params = {
                "format": "json",
                "markupFormat": "markdown",
                "query.term": dr_name,
                "pageSize": 100
            }
            if page_token:
                params["pageToken"] = page_token

            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                reason = f"Request failed with status {response.status_code}"
                failed_records.append({"Record_Id": record_id, "Full_Name": dr_name, "reason": reason})
                return

            data = response.json()
            studies = data.get("studies", [])
            if not studies:
                failed_records.append({"Record_Id": record_id, "Full_Name": dr_name, "reason": "No studies found"})
                return

            for study in studies:
                protocol = study.get("protocolSection", {})
                overview = build_overview(protocol, record_id, dr_name)
                nctId = overview.get("nctId")

                if not nctId:
                    continue

                # Build trial entry
                trial_entry = {
                    "overview": overview,
                    "json_raw": study
                }

                # Check if doctor exists
                doc = collection.find_one({"Record_Id": record_id})
                if doc:
                    existing_nctids = [t.get("overview", {}).get("nctId") for t in doc.get("clinical_trials", [])]
                    if nctId in existing_nctids:
                        # Update existing trial
                        collection.update_one(
                            {"Record_Id": record_id, "clinical_trials.overview.nctId": nctId},
                            {"$set": {
                                "clinical_trials.$.overview": overview,
                                "clinical_trials.$.json_raw": study
                            }}
                        )
                        updated_trials_count += 1
                    else:
                        # Add new trial
                        collection.update_one(
                            {"Record_Id": record_id},
                            {"$push": {"clinical_trials": trial_entry}}
                        )
                        new_trials_count += 1
                else:
                    # Insert new doctor with first trial
                    collection.insert_one({
                        "Record_Id": record_id,
                        "Full_Name": dr_name,
                        "clinical_trials": [trial_entry]
                    })
                    new_trials_count += 1

            # Pagination
            page_token = data.get("nextPageToken")
            page_count += 1
            if page_token is None or page_count >= max_pages:
                break

        logging.info(f"{record_id} | {dr_name} | ✅ {new_trials_count} new, {updated_trials_count} updated trials.")
    except Exception as e:
        failed_records.append({"Record_Id": record_id, "Full_Name": dr_name, "reason": str(e)})
        logging.error(f"{record_id} | {dr_name} | ❌ Error: {str(e)}")

# Run the process
for _, row in input_df.iterrows():
    scrap_clinical_trials(str(row['Record_Id']).strip(), str(row['Full_Name']).strip())

# Save failed searches
if failed_records:
    failed_df = pd.DataFrame(failed_records)
    failed_df.to_excel(FAILED_FILE, index=False)
    print(f"❌ Failed cases saved to {FAILED_FILE}")

print("🎉 All done! Logs written to 'search_log.txt'.")
