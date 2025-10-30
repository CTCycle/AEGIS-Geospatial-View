from __future__ import annotations

import re
import unicodedata

COUNTRY_NAME_TO_ISO2 = {
    "Afghanistan": "AF",
    "Albania": "AL",
    "Algeria": "DZ",
    "American Samoa": "AS",
    "Andorra": "AD",
    "Angola": "AO",
    "Anguilla": "AI",
    "Antarctica": "AQ",
    "Antigua & Barbuda": "AG",
    "Argentina": "AR",
    "Armenia": "AM",
    "Aruba": "AW",
    "Australia": "AU",
    "Austria": "AT",
    "Azerbaijan": "AZ",
    "Bahamas": "BS",
    "Bahrain": "BH",
    "Bangladesh": "BD",
    "Barbados": "BB",
    "Belarus": "BY",
    "Belgium": "BE",
    "Belize": "BZ",
    "Benin": "BJ",
    "Bermuda": "BM",
    "Bhutan": "BT",
    "Bolivia": "BO",
    "Bosnia & Herzegovina": "BA",
    "Botswana": "BW",
    "Bouvet Island": "BV",
    "Brazil": "BR",
    "British Indian Ocean Territory": "IO",
    "British Virgin Islands": "VG",
    "Brunei": "BN",
    "Bulgaria": "BG",
    "Burkina Faso": "BF",
    "Burundi": "BI",
    "Cambodia": "KH",
    "Cameroon": "CM",
    "Canada": "CA",
    "Cape Verde": "CV",
    "Caribbean Netherlands": "BQ",
    "Cayman Islands": "KY",
    "Central African Republic": "CF",
    "Chad": "TD",
    "Chile": "CL",
    "China": "CN",
    "Christmas Island": "CX",
    "Cocos (Keeling) Islands": "CC",
    "Colombia": "CO",
    "Comoros": "KM",
    "Congo - Brazzaville": "CG",
    "Congo - Kinshasa": "CD",
    "Cook Islands": "CK",
    "Costa Rica": "CR",
    "Croatia": "HR",
    "Cuba": "CU",
    "Curaçao": "CW",
    "Cyprus": "CY",
    "Czechia": "CZ",
    "Côte d’Ivoire": "CI",
    "Denmark": "DK",
    "Djibouti": "DJ",
    "Dominica": "DM",
    "Dominican Republic": "DO",
    "Ecuador": "EC",
    "Egypt": "EG",
    "El Salvador": "SV",
    "Equatorial Guinea": "GQ",
    "Eritrea": "ER",
    "Estonia": "EE",
    "Eswatini": "SZ",
    "Ethiopia": "ET",
    "Falkland Islands": "FK",
    "Faroe Islands": "FO",
    "Fiji": "FJ",
    "Finland": "FI",
    "France": "FR",
    "French Guiana": "GF",
    "French Polynesia": "PF",
    "French Southern Territories": "TF",
    "Gabon": "GA",
    "Gambia": "GM",
    "Georgia": "GE",
    "Germany": "DE",
    "Ghana": "GH",
    "Gibraltar": "GI",
    "Greece": "GR",
    "Greenland": "GL",
    "Grenada": "GD",
    "Guadeloupe": "GP",
    "Guam": "GU",
    "Guatemala": "GT",
    "Guernsey": "GG",
    "Guinea": "GN",
    "Guinea-Bissau": "GW",
    "Guyana": "GY",
    "Haiti": "HT",
    "Heard & McDonald Islands": "HM",
    "Honduras": "HN",
    "Hong Kong SAR China": "HK",
    "Hungary": "HU",
    "Iceland": "IS",
    "India": "IN",
    "Indonesia": "ID",
    "Iran": "IR",
    "Iraq": "IQ",
    "Ireland": "IE",
    "Isle of Man": "IM",
    "Israel": "IL",
    "Italy": "IT",
    "Jamaica": "JM",
    "Japan": "JP",
    "Jersey": "JE",
    "Jordan": "JO",
    "Kazakhstan": "KZ",
    "Kenya": "KE",
    "Kiribati": "KI",
    "Kuwait": "KW",
    "Kyrgyzstan": "KG",
    "Laos": "LA",
    "Latvia": "LV",
    "Lebanon": "LB",
    "Lesotho": "LS",
    "Liberia": "LR",
    "Libya": "LY",
    "Liechtenstein": "LI",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Macao SAR China": "MO",
    "Madagascar": "MG",
    "Malawi": "MW",
    "Malaysia": "MY",
    "Maldives": "MV",
    "Mali": "ML",
    "Malta": "MT",
    "Marshall Islands": "MH",
    "Martinique": "MQ",
    "Mauritania": "MR",
    "Mauritius": "MU",
    "Mayotte": "YT",
    "Mexico": "MX",
    "Micronesia": "FM",
    "Moldova": "MD",
    "Monaco": "MC",
    "Mongolia": "MN",
    "Montenegro": "ME",
    "Montserrat": "MS",
    "Morocco": "MA",
    "Mozambique": "MZ",
    "Myanmar (Burma)": "MM",
    "Namibia": "NA",
    "Nauru": "NR",
    "Nepal": "NP",
    "Netherlands": "NL",
    "New Caledonia": "NC",
    "New Zealand": "NZ",
    "Nicaragua": "NI",
    "Niger": "NE",
    "Nigeria": "NG",
    "Niue": "NU",
    "Norfolk Island": "NF",
    "North Korea": "KP",
    "North Macedonia": "MK",
    "Northern Mariana Islands": "MP",
    "Norway": "NO",
    "Oman": "OM",
    "Pakistan": "PK",
    "Palau": "PW",
    "Palestinian Territories": "PS",
    "Panama": "PA",
    "Papua New Guinea": "PG",
    "Paraguay": "PY",
    "Peru": "PE",
    "Philippines": "PH",
    "Pitcairn Islands": "PN",
    "Poland": "PL",
    "Portugal": "PT",
    "Puerto Rico": "PR",
    "Qatar": "QA",
    "Romania": "RO",
    "Russia": "RU",
    "Rwanda": "RW",
    "Réunion": "RE",
    "Samoa": "WS",
    "San Marino": "SM",
    "Saudi Arabia": "SA",
    "Senegal": "SN",
    "Serbia": "RS",
    "Seychelles": "SC",
    "Sierra Leone": "SL",
    "Singapore": "SG",
    "Sint Maarten": "SX",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Solomon Islands": "SB",
    "Somalia": "SO",
    "South Africa": "ZA",
    "South Georgia & South Sandwich Islands": "GS",
    "South Korea": "KR",
    "South Sudan": "SS",
    "Spain": "ES",
    "Sri Lanka": "LK",
    "St. Barthélemy": "BL",
    "St. Helena": "SH",
    "St. Kitts & Nevis": "KN",
    "St. Lucia": "LC",
    "St. Martin": "MF",
    "St. Pierre & Miquelon": "PM",
    "St. Vincent & Grenadines": "VC",
    "Sudan": "SD",
    "Suriname": "SR",
    "Svalbard & Jan Mayen": "SJ",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Syria": "SY",
    "São Tomé & Príncipe": "ST",
    "Taiwan": "TW",
    "Tajikistan": "TJ",
    "Tanzania": "TZ",
    "Thailand": "TH",
    "Timor-Leste": "TL",
    "Togo": "TG",
    "Tokelau": "TK",
    "Tonga": "TO",
    "Trinidad & Tobago": "TT",
    "Tunisia": "TN",
    "Turkey": "TR",
    "Turkmenistan": "TM",
    "Turks & Caicos Islands": "TC",
    "Tuvalu": "TV",
    "U.S. Outlying Islands": "UM",
    "U.S. Virgin Islands": "VI",
    "Uganda": "UG",
    "Ukraine": "UA",
    "United Arab Emirates": "AE",
    "United Kingdom": "GB",
    "United States": "US",
    "Uruguay": "UY",
    "Uzbekistan": "UZ",
    "Vanuatu": "VU",
    "Vatican City": "VA",
    "Venezuela": "VE",
    "Vietnam": "VN",
    "Wallis & Futuna": "WF",
    "Western Sahara": "EH",
    "Yemen": "YE",
    "Zambia": "ZM",
    "Zimbabwe": "ZW",
    "Åland Islands": "AX"
}

COUNTRY_SYNONYMS = {
    "Bolivia (Plurinational State of)": "Bolivia",
    "Brunei Darussalam": "Brunei",
    "Burma": "Myanmar (Burma)",
    "Congo, Democratic Republic": "Congo - Kinshasa",
    "Congo, Republic": "Congo - Brazzaville",
    "Czech Republic": "Czechia",
    "Democratic Republic of the Congo": "Congo - Kinshasa",
    "Federated States of Micronesia": "Micronesia",
    "Great Britain": "United Kingdom",
    "Hong Kong": "Hong Kong SAR China",
    "Hong Kong SAR": "Hong Kong SAR China",
    "Iran, Islamic Republic": "Iran",
    "Ivory Coast": "Côte d’Ivoire",
    "Ivory Cost": "Côte d’Ivoire",
    "Korea (South)": "South Korea",
    "Korea, Republic of": "South Korea",
    "Korea, South": "South Korea",
    "Lao People's Democratic Republic": "Laos",
    "Macao": "Macao SAR China",
    "Macao SAR": "Macao SAR China",
    "Macau": "Macao SAR China",
    "Macedonia": "North Macedonia",
    "Micronesia (Federated States of)": "Micronesia",
    "Myanmar": "Myanmar (Burma)",
    "Palestine": "Palestinian Territories",
    "Palestinian Territory": "Palestinian Territories",
    "Republic of Korea": "South Korea",
    "Republic of Moldova": "Moldova",
    "Republic of the Congo": "Congo - Brazzaville",
    "Russian Federation": "Russia",
    "Saint Barthelemy": "St. Barthélemy",
    "Saint Kitts and Nevis": "St. Kitts & Nevis",
    "Saint Lucia": "St. Lucia",
    "Saint Martin": "St. Martin",
    "Saint Pierre and Miquelon": "St. Pierre & Miquelon",
    "Saint Vincent and the Grenadines": "St. Vincent & Grenadines",
    "Sao Tome & Principe": "São Tomé & Príncipe",
    "Sao Tome and Principe": "São Tomé & Príncipe",
    "St Barthelemy": "St. Barthélemy",
    "St Kitts and Nevis": "St. Kitts & Nevis",
    "St Lucia": "St. Lucia",
    "St Martin": "St. Martin",
    "St Pierre and Miquelon": "St. Pierre & Miquelon",
    "St Vincent and the Grenadines": "St. Vincent & Grenadines",
    "Swaziland": "Eswatini",
    "Taiwan, Province of China": "Taiwan",
    "Timor Leste": "Timor-Leste",
    "Türkiye": "Turkey",
    "U A E": "United Arab Emirates",
    "U K": "United Kingdom",
    "U S A": "United States",
    "U.A.E.": "United Arab Emirates",
    "U.K.": "United Kingdom",
    "U.S.A.": "United States",
    "UAE": "United Arab Emirates",
    "UK": "United Kingdom",
    "USA": "United States",
    "United Arab Emirates": "United Arab Emirates",
    "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
    "United States America": "United States",
    "United States of America": "United States",
    "Vatican": "Vatican City",
    "Viet Nam": "Vietnam"
}

###############################################################################
class LocationSanitizationService:
    COUNTRY_NAME_TO_ISO2 = COUNTRY_NAME_TO_ISO2
    def __init__(self) -> None:
        self.country_lookup = self.build_country_lookup()

    #-----------------------------------------------------------------------------
    def build_country_lookup(self) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for name, code in self.COUNTRY_NAME_TO_ISO2.items():
            normalized = self.normalize_country_key(name)
            if normalized:
                lookup[normalized] = code
        for alias, target in COUNTRY_SYNONYMS.items():
            normalized_alias = self.normalize_country_key(alias)
            normalized_target = self.normalize_country_key(target)
            if (
                normalized_alias
                and normalized_target
                and normalized_target in lookup
            ):
                lookup.setdefault(normalized_alias, lookup[normalized_target])
        return lookup

    #-----------------------------------------------------------------------------
    def normalize_whitespace(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return " ".join(stripped.split())

    #-----------------------------------------------------------------------------
    def normalize_country_key(self, value: str | None) -> str:
        if value is None:
            return ""
        normalized = unicodedata.normalize("NFKD", value)
        normalized = normalized.encode("ascii", "ignore").decode("ascii")
        normalized = normalized.lower()
        normalized = normalized.replace("&", "and")
        normalized = normalized.replace("'", " ")
        normalized = normalized.replace("’", " ")
        normalized = normalized.replace(".", " ")
        normalized = normalized.replace(",", " ")
        normalized = normalized.replace("-", " ")
        normalized = normalized.replace("saint", "st")
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = normalized.strip()
        if normalized.startswith("the "):
            normalized = normalized[4:]
        return normalized

    #-----------------------------------------------------------------------------
    def normalize_country(self, value: str | None) -> str | None:
        normalized = self.normalize_whitespace(value)
        if not normalized:
            return None
        if len(normalized) == 2 and normalized.isalpha():
            return normalized.upper()
        key = self.normalize_country_key(normalized)
        if not key:
            return None
        if key in self.country_lookup:
            return self.country_lookup[key]
        return None

    #-----------------------------------------------------------------------------
    def classify_query(self, value: str) -> str:
        if re.search(r"\d", value):
            return "address"
        return "place"

    #-----------------------------------------------------------------------------
    def sanitize_location_inputs(
        self,
        address: str,
        city: str | None,
        country: str | None,
    ) -> dict[str, str | None]:
        sanitized_address = self.normalize_whitespace(address) or ""
        sanitized_city = self.normalize_whitespace(city)
        sanitized_country = self.normalize_whitespace(country)
        country_code = self.normalize_country(country)
        classification = self.classify_query(sanitized_address)
        query_components: list[str] = [sanitized_address]
        if sanitized_city and sanitized_city.lower() not in sanitized_address.lower():
            query_components.append(sanitized_city)
        if not country_code and sanitized_country:
            query_components.append(sanitized_country)
        query = ", ".join(component for component in query_components if component)
        return {
            "address": sanitized_address,
            "city": sanitized_city,
            "country_code": country_code,
            "country": sanitized_country,
            "classification": classification,
            "query": query,
        }
