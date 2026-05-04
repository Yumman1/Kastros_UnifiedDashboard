# dictionaries.py
# Knowledge base: Pakistani brands, cities, and slang for normalization.
# Used by extractor.py for fuzzy matching (typos, Urdu, shorthand).

# MASTER CATEGORY MAPPING
# Keys = Official Database Category
# Values = List of keywords/brands/slang to fuzzy match against
COMMODITY_GROUPS = {
    "RICE": [
        "irri", "irri-6", "supri", "super", "kainat", "1121", "sella", "basmati",
        "c-9", "c9", "broken", "totta", "steam", "1509", "rice", "chawal"
    ],
    "WHEAT": [
        "gandum", "wheat", "atta", "flour", "maida", "suji", "bori"
    ],
    "SUGAR": [
        "sugar", "cheeni", "shakkar", "white sugar", "cane"
    ],
    "COTTON": [
        "cotton", "phutti", "kapas", "lint", "bale", "rui"
    ],
    "OIL_GHEE": [
        "oil", "ghee", "meezan", "dalda", "sufi", "kisan", "tullo",
        "palm", "olein", "canola", "soybean", "cooking oil"
    ],
    "CORN": [
        "corn", "maize", "makai", "maka"
    ]
}

# CITY NORMALIZATION
# Maps shorthand/slang to Full English Name
CITY_MAP = {
    "khi": "Karachi", "karachi": "Karachi",
    "lhr": "Lahore", "lahore": "Lahore",
    "fsd": "Faisalabad", "faisalabad": "Faisalabad",
    "mul": "Multan", "multan": "Multan",
    "hyd": "Hyderabad", "hyderabad": "Hyderabad",
    "bwk": "Bahawalpur", "suk": "Sukkur",
    "g.khan": "DG Khan", "dgk": "DG Khan", "dg khan": "DG Khan",
    "bahawalpur": "Bahawalpur", "sukkur": "Sukkur",
    "rawalpindi": "Rawalpindi", "islamabad": "Islamabad",
    "peshawar": "Peshawar", "quetta": "Quetta", "sialkot": "Sialkot",
}

# PROVINCE MAPPING
# Maps normalized city name → province for province-level analytics.
# Lookup is case-insensitive (caller should .title() or .lower() before matching).
PROVINCE_MAP = {
    # ── Punjab ──
    "Lahore": "Punjab",
    "Faisalabad": "Punjab",
    "Multan": "Punjab",
    "Bahawalpur": "Punjab",
    "DG Khan": "Punjab",
    "Rawalpindi": "Punjab",
    "Sialkot": "Punjab",
    "Khanewal": "Punjab",
    "Haroonabad": "Punjab",
    "Tounsa": "Punjab",
    "Sahiwal": "Punjab",
    "Vehari": "Punjab",
    "Lodhran": "Punjab",
    "Rahim Yar Khan": "Punjab",
    "Muzaffargarh": "Punjab",
    "Gujranwala": "Punjab",
    "Sargodha": "Punjab",
    "Jhang": "Punjab",
    "Burewala": "Punjab",
    "Mianwali": "Punjab",
    "Bahawalnagar": "Punjab",
    "Okara": "Punjab",
    "Pakpattan": "Punjab",
    "Chiniot": "Punjab",
    "Layyah": "Punjab",
    "Rajanpur": "Punjab",
    "Chichawatni": "Punjab",
    "Faqeerwali": "Punjab",
    "Fort Abbas": "Punjab",
    "Hasilpur": "Punjab",
    "Khan Pur": "Punjab",
    "Khanpur": "Punjab",
    "Mian Chanu": "Punjab",
    "Mian Channu": "Punjab",
    "Yazman": "Punjab",
    # ── Sindh ──
    "Karachi": "Sindh",
    "Hyderabad": "Sindh",
    "Hayderabad": "Sindh",
    "Sukkur": "Sindh",
    "Nawabshah": "Sindh",
    "Nawab Shah": "Sindh",
    "Mirpurkhas": "Sindh",
    "Mir Pur Khas": "Sindh",
    "MIR PUR KHAS": "Sindh",
    "Larkana": "Sindh",
    "Sanghar": "Sindh",
    "Tando Adam": "Sindh",
    "Tandoadam": "Sindh",
    "Umerkot": "Sindh",
    "Ghotki": "Sindh",
    "Hala": "Sindh",
    "Halani": "Sindh",
    "Khadro": "Sindh",
    "Khadrro": "Sindh",
    "Kotri": "Sindh",
    "Kotri Kabeer": "Sindh",
    "Mahrab Pur": "Sindh",
    "Mehrab Pur": "Sindh",
    "Rani Pur": "Sindh",
    "Sakrand": "Sindh",
    "Salah Pat": "Sindh",
    "Saleh Pat": "Sindh",
    "Shahdad Pur": "Sindh",
    "Shahdadpur": "Sindh",
    "Shadan Lund": "Sindh",
    "Shah Pur Chakar": "Sindh",
    "Shah Pur Chakkar": "Sindh",
    "Shahpur Chakar": "Sindh",
    "Dour": "Sindh",
    "Daur": "Sindh",
    "Ghupchani": "Sindh",
    "Nea Abad": "Sindh",
    "Peer Wasan": "Sindh",
    "Pir Wasan": "Sindh",
    "Sui Gas": "Sindh",
    # ── Balochistan ──
    "Quetta": "Balochistan",
    "Bella": "Balochistan",
    "Bela": "Balochistan",
    "Lasbella": "Balochistan",
    "Lasbeela": "Balochistan",
    "Windar": "Balochistan",
    "Winder": "Balochistan",
    # ── KPK ──
    "Peshawar": "KPK",
    "Mardan": "KPK",
    "Swabi": "KPK",
    "Abbottabad": "KPK",
    "Swat": "KPK",
    "Dera Ismail Khan": "KPK",
    # ── Islamabad ──
    "Islamabad": "Islamabad",
}
