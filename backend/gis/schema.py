"""Data model: hosted-feature-layer definitions (mirrors the ArcGIS Online layers).

Every layer has a primary id field, a geometry type and a field list. The local store
validates writes against this schema so the local system of record and the hosted layers
stay consistent. Fields marked synthetic data are labelled through Data_Classification.
"""
from __future__ import annotations

from dataclasses import dataclass, field

INFRA = "Riyadh_Infrastructure_Assets"
WATER = "Riyadh_Water_Network"
SENSORS = "Riyadh_Sensor_Readings"
DETECTIONS = "Riyadh_AI_Detections"
CHANGES = "Riyadh_Change_Detection"
FEATURES = "Riyadh_Extracted_Features"
INCIDENTS = "Riyadh_Operational_Incidents"
WORK_ORDERS = "Riyadh_Work_Orders"
VERIFICATION = "Riyadh_Field_Verification"
INDICATORS = "Riyadh_Executive_Indicators"
AUDIT = "Riyadh_Agent_Audit_Log"
# supporting layers (not in the 11 required, needed for relationships / operations)
WORKERS = "Riyadh_Field_Workers"
FACILITIES = "Riyadh_Reference_Facilities"
MAINTENANCE = "Riyadh_Maintenance_History"
TELEMETRY = "Riyadh_Streetlight_Telemetry"
APPROVALS = "Riyadh_Approvals"
CONFIG = "Riyadh_Learning_Config"
BUILDINGS = "Riyadh_Reference_Buildings"
TRUTH = "Riyadh_Sim_Ground_Truth"  # simulator-only; never exposed to the agent tools
SIM_EVENTS = "Riyadh_Sim_Events"
CITIZEN = "Riyadh_Citizen_Reports"  # NCCC feed: geotagged reports from residents (SIMULATED)

NOTIFICATIONS = "Riyadh_Notifications"  # NCCC alert feed raised by the digital crew (local, not mirrored)

SYNTHETIC = "SYNTHETIC-DEMO"
SIMULATED = "SIMULATED-PROCESSING"
REFERENCE = "REFERENCE-APPROXIMATE"
OSM_REAL = "OSM-REAL (c) OpenStreetMap contributors, ODbL"
OPERATIONAL = "DEMO-OPERATIONAL"


@dataclass(frozen=True)
class LayerDef:
    name: str
    geometry: str | None  # Point | Polyline | Polygon | None (table)
    id_field: str
    fields: tuple[str, ...]
    internal: bool = False


def _l(name, geom, id_field, fields, internal=False):
    return LayerDef(name, geom, id_field, tuple([id_field] + [f for f in fields if f != id_field]), internal)


LAYERS: dict[str, LayerDef] = {
    d.name: d
    for d in [
        _l(INFRA, "Point", "Asset_ID", ["Asset_Type", "Asset_Name", "Asset_Status", "Asset_Criticality", "Installation_Date",
                                        "Location", "Area_Name", "Related_Pipeline_ID", "Corridor", "Data_Classification"]),
        _l(WATER, "Polyline", "Pipeline_ID", ["Network_Type", "Material", "Diameter", "Status", "Risk_Level", "Area_Name",
                                              "From_Node", "To_Node", "Length_M", "Data_Classification"]),
        _l(SENSORS, "Point", "Reading_ID", ["Sensor_ID", "Asset_ID", "Sensor_Type", "Timestamp", "Pressure", "Flow",
                                            "Power_Consumption", "Operating_Status", "Anomaly_Flag", "Data_Classification"]),
        _l(DETECTIONS, "Point", "Detection_ID", ["Detection_Type", "Location", "Confidence", "Severity", "Risk_Score", "Detection_Date",
                                                     "Source", "Status", "Related_Asset_ID", "Pipeline_ID", "Area_Name", "Category",
                                                     "Cluster_ID", "Evidence", "Base_Risk_Score", "Incident_ID", "Distortion_Score", "Land_Use_Category", "Data_Classification"]),
        _l(CHANGES, "Polygon", "Change_ID", ["Change_Type", "Previous_Epoch", "Current_Epoch", "Area_Sqm", "Confidence", "Detection_Date",
                                             "Status", "Area_Name", "Significant", "Mean_Magnitude", "Notes", "Data_Classification"]),
        _l(FEATURES, "Polygon", "Feature_ID", ["Feature_Type", "Extraction_Source", "Confidence", "Area_Sqm", "Detection_Date",
                                               "Related_Change_ID", "Length_M", "Data_Classification"]),
        _l(INCIDENTS, "Point", "Incident_ID", ["Incident_Type", "Priority", "Severity", "Risk_Score", "Location", "Description",
                                               "Related_Asset_ID", "Assigned_Team", "Status", "Created_Date", "Last_Updated",
                                               "Detection_IDs", "Area_Name", "Category", "Verification_Outcome", "Data_Classification"]),
        _l(WORK_ORDERS, "Point", "Work_Order_ID", ["Incident_ID", "Assigned_Team", "Assigned_Worker", "Priority", "Due_Date", "Status",
                                                   "Approval_Status", "Created_Date", "Task_Type", "Instructions", "Accepted_At", "Assigned_Worker_Name", "Assigned_To_Username", "Incident_Type", "Area_Name",
                                                   "Assigned_At", "Field_Maps_Status", "Field_Verdict", "Field_Comment", "esritask_type", "esritask_assignee", "esritask_status", "esritask_priority", "esritask_duedate",
                                                   "esritask_description", "esritask_notes", "Data_Classification"]),
        _l(VERIFICATION, "Point", "Verification_ID", ["Work_Order_ID", "Incident_ID", "Worker_ID", "Investigator_Name", "Observation", "Verification_Status",
                                                      "GPS_Location", "Photo_URL", "Timestamp", "Distance_To_Detection_M",
                                                      "Agent_Assessment", "Simulated_Worker", "Data_Classification"]),
        _l(INDICATORS, None, "Indicator_ID", ["Indicator_Name", "Indicator_Value", "Geographic_Area", "Reporting_Date", "Data_Classification"]),
        _l(AUDIT, None, "Log_ID", ["Session_ID", "Agent_Action", "Tool_Name", "Related_Incident_ID", "Input_Summary", "Output_Summary",
                                   "Approval_Status", "Timestamp", "Actor"]),
        _l(WORKERS, "Point", "Worker_ID", ["Name", "Team", "Skills", "Status", "Base_Area", "Open_Tasks", "Last_Update", "ArcGIS_Username", "Data_Classification"]),
        _l(FACILITIES, "Point", "Facility_ID", ["Name", "Facility_Type", "Area_Name", "Data_Classification"]),
        _l(BUILDINGS, "Polygon", "Building_ID", ["Name", "Building_Type", "Area_Name", "Area_Sqm", "Data_Classification"]),
        _l(MAINTENANCE, None, "Record_ID", ["Asset_ID", "Date", "Action", "Outcome", "Data_Classification"]),
        _l(TELEMETRY, None, "Asset_ID", ["Rated_Power_W", "Avg_Power_W", "Power_Trend_Pct", "Flicker_30d", "Comm_Loss_Pct",
                                             "Faults_12m", "Days_Since_Maintenance", "Age_Years", "Pole_Tilt_Deg", "Corrosion_Level", "Updated", "Data_Classification"]),
        _l(APPROVALS, None, "Approval_ID", ["Action_Type", "Status", "Summary", "Payload", "Target", "Location", "Priority", "Team",
                                            "Expected_Result", "Created", "Decided", "Decided_By", "Result", "Session_ID", "Incident_ID"]),
        _l(CONFIG, None, "Config_ID", ["Value", "Updated"]),
        _l(TRUTH, None, "Truth_ID", ["Detection_ID", "Is_True", "Notes"], internal=True),
        _l(SIM_EVENTS, None, "Event_ID", ["Timestamp", "Kind", "Message", "Ref_ID"]),
        _l(CITIZEN, "Point", "Report_ID", ["Category", "Title", "Description", "Channel", "Reported_At", "Status", "Area_Name", "Linked_Incident", "Data_Classification"], internal=True),
        _l(NOTIFICATIONS, None, "Notif_ID", ["Kind", "Severity", "Title", "Message", "Agent", "Trail", "Ref_ID", "Incident_ID", "Approval_ID", "Area_Name",
                                             "Lon", "Lat", "Status", "Created", "Updated"], internal=True),
    ]
}

CATEGORY_OF_TYPE = {"water": "Water Leak", "lighting": "Streetlight", "change": "Urban Change", "distortion": "Visual Distortion", "land_use": "Land-Use Management"}
