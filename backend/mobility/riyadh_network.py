"""Reference Riyadh corridor skeleton (APPROXIMATE, hand-placed waypoints).

IMPORTANT: these polylines are a schematic fallback so the prototype runs offline. They are NOT survey-grade
geometry. For authoritative geometry run `python scripts/load_riyadh_data.py --osm` (OpenStreetMap) or load an
authoritative ArcGIS feature service. All records created from this file carry data_status="reference-approximate".

Topology (intersections) is computed geometrically from crossings and endpoint snapping.
"""
from __future__ import annotations

# (lon, lat)
CORRIDORS = [
    # name, class, lanes, speed, waypoints
    ("King Fahd Road", "motorway", 4, 90, [(46.640, 24.600), (46.665, 24.640), (46.674, 24.690), (46.676, 24.745),
                                            (46.668, 24.800), (46.655, 24.850), (46.650, 24.900)]),
    ("Northern Ring Road", "motorway", 4, 100, [(46.520, 24.815), (46.580, 24.812), (46.650, 24.810),
                                                 (46.720, 24.812), (46.790, 24.815)]),
    ("Eastern Ring Road", "motorway", 4, 100, [(46.790, 24.600), (46.800, 24.660), (46.802, 24.720),
                                                (46.795, 24.770), (46.790, 24.815)]),
    ("Southern Ring Road", "motorway", 4, 100, [(46.520, 24.590), (46.600, 24.585), (46.700, 24.585),
                                                 (46.790, 24.600)]),
    ("Western Ring Road", "motorway", 4, 100, [(46.520, 24.590), (46.530, 24.660), (46.535, 24.730),
                                                (46.525, 24.780), (46.520, 24.815)]),
    ("Makkah Road", "arterial", 3, 80, [(46.540, 24.640), (46.590, 24.652), (46.640, 24.665), (46.676, 24.690),
                                        (46.710, 24.700)]),
    ("Khurais Road", "arterial", 3, 80, [(46.730, 24.690), (46.760, 24.700), (46.800, 24.715), (46.870, 24.745)]),
    ("Olaya Street", "arterial", 3, 60, [(46.690, 24.620), (46.688, 24.660), (46.684, 24.700), (46.680, 24.745),
                                         (46.676, 24.790)]),
    ("Takhassusi Street", "arterial", 3, 60, [(46.640, 24.665), (46.650, 24.700), (46.660, 24.735),
                                              (46.662, 24.775), (46.655, 24.810)]),
    ("Prince Turki bin Abdulaziz Al Awwal Road", "arterial", 3, 70,
        [(46.535, 24.745), (46.600, 24.752), (46.650, 24.758), (46.700, 24.762), (46.745, 24.765),
         (46.795, 24.770)]),
    ("Airport Road", "motorway", 3, 100, [(46.722, 24.812), (46.716, 24.860), (46.708, 24.910),
                                          (46.700, 24.955)]),
    ("Imam Saud bin Faisal Road", "arterial", 3, 70, [(46.590, 24.780), (46.640, 24.785), (46.676, 24.790),
                                                      (46.720, 24.792), (46.760, 24.790), (46.790, 24.788)]),
    ("King Salman Road", "arterial", 3, 70, [(46.730, 24.640), (46.735, 24.690), (46.738, 24.740),
                                             (46.736, 24.790), (46.725, 24.812)]),
    # Collectors/connectors: SYNTHETIC infill to provide alternative routes (no official name)
    ("Collector C1 (synthetic)", "collector", 2, 50, [(46.600, 24.600), (46.604, 24.652)]),
    ("Collector C2 (synthetic)", "collector", 2, 50, [(46.600, 24.652), (46.602, 24.752)]),
    ("Collector C3 (synthetic)", "collector", 2, 50, [(46.690, 24.585), (46.690, 24.620)]),
    ("Collector C4 (synthetic)", "collector", 2, 50, [(46.738, 24.740), (46.745, 24.765), (46.760, 24.790)]),
    ("Collector C5 (synthetic)", "collector", 2, 50, [(46.700, 24.762), (46.705, 24.812)]),
    ("Collector C6 (synthetic)", "collector", 2, 50, [(46.760, 24.700), (46.762, 24.765)]),
    ("Collector C7 (synthetic)", "collector", 2, 50, [(46.600, 24.752), (46.590, 24.780), (46.585, 24.812)]),
    ("Collector C8 (synthetic)", "collector", 2, 50, [(46.795, 24.770), (46.790, 24.790)]),
    ("Collector C9 (synthetic)", "collector", 2, 50, [(46.640, 24.665), (46.640, 24.600)]),
    ("Collector C10 (synthetic)", "collector", 2, 50, [(46.700, 24.710), (46.700, 24.762)]),
]

# Named places (approximate reference positions; verify before operational use)
LOCATIONS = {
    "KAFD": ("King Abdullah Financial District (KAFD)", 46.6420, 24.7660),
    "Olaya": ("Al Olaya", 46.6840, 24.6990),
    "Malaz": ("Al Malaz", 46.7280, 24.6700),
    "Nakheel": ("Al Nakheel", 46.6280, 24.7380),
    "Yasmin": ("Al Yasmin", 46.6560, 24.8250),
    "Narjis": ("Al Narjis", 46.6900, 24.8650),
    "Wurud": ("Al Wurud", 46.6730, 24.7180),
    "DQ": ("Diplomatic Quarter", 46.6230, 24.6840),
    "KKIA": ("King Khalid International Airport", 46.6990, 24.9570),
    "KSU": ("King Saud University", 46.6190, 24.7160),
    "KAHC": ("King Abdulaziz Historical Center", 46.7110, 24.6480),
    "RiyadhFront": ("Riyadh Front", 46.7260, 24.8090),
    "KAPark": ("King Abdullah Park", 46.7140, 24.6590),
}

# Event venues that are not demand zones: an event there is simulated at the nearest junction, and they do not take part in the trip demand or
# in hospital access, so adding one changes no other modelled number. Approximate positions, like the places above. key -> (name, lon, lat, other names)
EVENT_VENUES = {
    "KingFahdStadium": ("King Fahd International Stadium", 46.8386, 24.7892, ("King Fahd Stadium", "ملعب الملك فهد", "استاد الملك فهد")),
}

HOSPITALS = [  # name, lon, lat, beds (beds are synthetic placeholders)
    ("King Fahad Medical City", 46.6990, 24.6850, 1200),
    ("King Khalid University Hospital", 46.6180, 24.7130, 850),
    ("King Faisal Specialist Hospital", 46.6760, 24.6720, 1000),
    ("Security Forces Hospital", 46.7390, 24.7380, 600),
    ("Dr. Sulaiman Al Habib Hospital (Olaya)", 46.6850, 24.7010, 400),
    ("King Abdulaziz Medical City", 46.7240, 24.7560, 700),
    ("Imam Abdulrahman Al Faisal Hospital (East)", 46.7990, 24.7230, 350),
    ("Northern Riyadh Hospital (sample)", 46.6620, 24.8300, 300),
]

EMERGENCY = [  # name, type, lon, lat
    ("Civil Defense HQ (sample)", "civil_defense", 46.7050, 24.7150),
    ("Civil Defense Station North (sample)", "civil_defense", 46.6700, 24.8350),
    ("Civil Defense Station East (sample)", "civil_defense", 46.7800, 24.7400),
    ("Red Crescent Dispatch Centre (sample)", "ems", 46.6880, 24.7300),
    ("Red Crescent Station South (sample)", "ems", 46.6700, 24.6300),
]

METRO = [  # code, name, color, [(station, lon, lat)]  -- schematic approximations
    ("L1", "Blue Line (Olaya-Batha)", "#1e6fe0", [("Olaya Stn", 46.6860, 24.6350), ("Al Wurud", 46.6850, 24.7000),
        ("Olaya N", 46.6830, 24.7250), ("KAFD Stn", 46.6440, 24.7700), ("Airport Rd Jn", 46.7060, 24.8000)]),
    ("L2", "Red Line (King Abdullah Rd)", "#e0412e", [("SABIC", 46.6000, 24.7690), ("KAFD Stn", 46.6440, 24.7700),
        ("Al Murooj", 46.6800, 24.7600), ("Riyadh Front Stn", 46.7230, 24.8060), ("Eastern Ring Jn", 46.7900, 24.7700)]),
    ("L3", "Orange Line (Madinah Rd)", "#f08a24", [("Jeddah Rd", 46.5900, 24.6520), ("KSU Stn", 46.6190, 24.7120),
        ("Al Hamra", 46.7000, 24.7650), ("Khurais Rd", 46.7800, 24.7100)]),
    ("L4", "Yellow Line (Airport Rd)", "#e6c32a", [("KAFD Stn", 46.6440, 24.7700), ("Riyadh Front Stn", 46.7230, 24.8060),
        ("Airport T5", 46.7000, 24.9570)]),
    ("L5", "Green Line (King Abdulaziz Rd)", "#2da44e", [("Hist. Centre", 46.7120, 24.6500), ("Al Malaz", 46.7280, 24.6700),
        ("Al Hamra", 46.7000, 24.7650), ("Narjis", 46.6900, 24.8650)]),
    ("L6", "Purple Line (Abdulrahman Ibn Awf)", "#8a4fd6", [("Diplomatic Qtr", 46.6230, 24.6840), ("Al Wurud", 46.6850, 24.7000),
        ("King Fahd Rd", 46.6760, 24.7450), ("Saud Univ. East", 46.7380, 24.7390)]),
]

BUS_ROUTES = [  # sample/synthetic routes through named places
    ("B1", "Route B1 KAFD-Olaya-Malaz (sample)", 12, ["KAFD", "Wurud", "Olaya", "Malaz"]),
    ("B2", "Route B2 Airport-Riyadh Front-KAFD (sample)", 15, ["KKIA", "RiyadhFront", "KAFD"]),
    ("B3", "Route B3 KSU-Nakheel-KAFD (sample)", 10, ["KSU", "Nakheel", "KAFD"]),
    ("B4", "Route B4 Yasmin-Narjis (sample)", 20, ["Yasmin", "Narjis"]),
    ("B5", "Route B5 DQ-Olaya-KAHC (sample)", 15, ["DQ", "Olaya", "KAHC"]),
]

PROJECTS = [  # name, type, lon, lat, status, budget MUSD (all SYNTHETIC)
    ("King Salman Road Capacity Upgrade (sample)", "road_widening", 46.737, 24.715, "planned", 220),
    ("KAFD North Interchange (sample)", "interchange", 46.652, 24.795, "design", 310),
    ("Eastern Ring Road Smart Signals (sample)", "its", 46.798, 24.740, "construction", 60),
    ("Northern Link Road (proposed)", "new_road", 46.700, 24.790, "proposed", 140),
    ("Southern Metro Feeder Hub (sample)", "transit_hub", 46.690, 24.600, "planned", 95),
]
