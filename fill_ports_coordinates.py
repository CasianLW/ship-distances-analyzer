import pandas as pd
from geopy.geocoders import Nominatim
from tqdm import tqdm
import time
import re
import unicodedata

# Nom du fichier d'entrée
input_file = "DryManager_Port_Table - Ports sans coordonnees.csv"
output_file = "ports_with_coordinates.csv"

# Lecture du CSV
df = pd.read_csv(input_file)

# Vérifie les colonnes disponibles
print("Colonnes trouvées :", df.columns.tolist())

# Nom de la colonne contenant le nom du port
port_column = "port"   # à modifier si besoin

# Géocodeur OpenStreetMap
geolocator = Nominatim(user_agent="port_locator_matthieu")

COUNTRY_ALIASES = {
    "U.A.E": "United Arab Emirates",
    "UAE": "United Arab Emirates",
    "UK": "United Kingdom",
    "USA": "United States",
    "U.S.A": "United States",
    "KSA": "Saudi Arabia",
}

# Alias d'états/régions pour les formats abrégés/tronqués.
REGION_ALIASES_BY_COUNTRY = {
    "AUSTRALIA": {
        "VICTO": "Victoria",
        "QUEENSL": "Queensland",
        "TASMA": "Tasmania",
        "NSW": "New South Wales",
        "N.S.W": "New South Wales",
        "WA": "Western Australia",
        "W.A": "Western Australia",
        "SA": "South Australia",
        "S.A": "South Australia",
        "NT": "Northern Territory",
        "N.T": "Northern Territory",
    }
}

IGNORED_REGION_TOKENS = {"ISLAND", "ISLANDS"}


def normalize_text(value: str) -> str:
    """Nettoie une chaîne pour améliorer les chances de géocodage."""
    text = str(value).strip()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[_.]+", " ", text)   # ex: MU.S.A -> MU S A
    text = re.sub(r"\s*\([^)]*\)", "", text)  # supprime les parenthèses
    text = re.sub(r"\s+", " ", text).strip(" ,")
    return text


def normalize_country(value):
    if pd.isna(value):
        return "", ""

    raw = str(value).strip()
    if not raw or raw.lower() == "none":
        return "", ""

    # Ex: "Australia (Island)" -> region_candidate="Island"
    parenthesized_parts = re.findall(r"\(([^)]*)\)", raw)
    without_parentheses = re.sub(r"\s*\([^)]*\)", "", raw).strip()

    country_candidate = without_parentheses
    region_candidate = ""

    # Ex: "Australia - W.A"
    if " - " in without_parentheses:
        left, right = without_parentheses.split(" - ", 1)
        country_candidate = left.strip()
        region_candidate = right.strip()
    else:
        # Ex: "Australia Queensl"
        match = re.match(r"^(Australia)\s+(.+)$", without_parentheses, flags=re.IGNORECASE)
        if match:
            country_candidate = match.group(1).strip()
            region_candidate = match.group(2).strip()

    # Si pas de région trouvée dans la forme principale, tente les parenthèses
    if not region_candidate and parenthesized_parts:
        region_candidate = parenthesized_parts[0].strip()

    country_clean = normalize_text(country_candidate)
    country_clean = COUNTRY_ALIASES.get(country_clean.upper(), country_clean)

    region_clean = normalize_text(region_candidate) if region_candidate else ""
    region_key = region_clean.upper().replace(".", "").replace(" ", "")

    country_key = country_clean.upper()
    region_aliases = REGION_ALIASES_BY_COUNTRY.get(country_key, {})
    if region_clean:
        region_clean = (
            region_aliases.get(region_clean.upper())
            or region_aliases.get(region_clean.upper().replace(".", ""))
            or region_aliases.get(region_key)
            or region_clean
        )

    if region_clean.upper() in IGNORED_REGION_TOKENS:
        region_clean = ""

    return country_clean, region_clean


def build_queries(port_name: str, country_name: str, region_name: str) -> list[str]:
    port_clean = normalize_text(port_name)
    country_clean = normalize_text(country_name) if country_name else ""
    region_clean = normalize_text(region_name) if region_name else ""

    queries = []

    if country_clean and region_clean:
        queries.extend(
            [
                f"{port_clean} port, {region_clean}, {country_clean}",
                f"{port_clean} harbor, {region_clean}, {country_clean}",
                f"{port_clean} terminal, {region_clean}, {country_clean}",
                f"{port_clean}, {region_clean}, {country_clean}",
            ]
        )

    if country_clean:
        queries.extend(
            [
                f"{port_clean} port, {country_clean}",
                f"{port_clean} harbor, {country_clean}",
                f"{port_clean} terminal, {country_clean}",
                f"{port_clean}, {country_clean}",
            ]
        )

    queries.extend(
        [
            f"{port_clean} port",
            port_clean,
        ]
    )

    # Déduplique tout en gardant l'ordre
    return list(dict.fromkeys([q for q in queries if q]))


# Détection des colonnes sans dépendre de la casse
columns_map = {c.lower(): c for c in df.columns}
country_column = columns_map.get("country")
coordinates_column = columns_map.get("coordinates")

coords = []

for _, row in tqdm(df.iterrows(), total=len(df)):
    try:
        port_name = str(row[port_column]).strip()
        existing_coords = ""
        if coordinates_column and pd.notna(row[coordinates_column]):
            existing_coords = str(row[coordinates_column]).strip()

        # Garde les coordonnées existantes
        if existing_coords:
            coords.append(existing_coords)
            print(f"{port_name} -> coordonnées déjà présentes")
            continue

        if country_column:
            country_name, region_name = normalize_country(row[country_column])
        else:
            country_name, region_name = "", ""

        queries = build_queries(port_name, country_name, region_name)

        found_coordinates = ""
        for query in queries:
            location = geolocator.geocode(query, timeout=10)
            time.sleep(0.8)  # limite de débit Nominatim
            if location:
                found_coordinates = f"{location.latitude:.7f},{location.longitude:.7f}"
                print(f"{query} -> {found_coordinates}")
                break

        if found_coordinates:
            coords.append(found_coordinates)
        else:
            coords.append("")
            print(
                f"{port_name} (country={country_name or 'N/A'}, region={region_name or 'N/A'}) -> introuvable"
            )

    except Exception as e:
        coords.append("")
        print(f"Erreur pour {port_name}: {e}")

df["coordinates"] = coords
df.to_csv(output_file, index=False, encoding="utf-8-sig")

print(f"\nFichier généré : {output_file}")