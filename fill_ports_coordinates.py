import pandas as pd
from geopy.geocoders import Nominatim
from tqdm import tqdm
import time

# Nom du fichier d'entrée
input_file = "DryManager_Port_Table - port sans coordonees.csv"
output_file = "ports_with_coordinates.csv"

# Lecture du CSV
df = pd.read_csv(input_file)

# Vérifie les colonnes disponibles
print("Colonnes trouvées :", df.columns.tolist())

# Nom de la colonne contenant le nom du port
port_column = "port"   # à modifier si besoin

# Géocodeur OpenStreetMap
geolocator = Nominatim(user_agent="port_locator_matthieu")

coords = []

for _, row in tqdm(df.iterrows(), total=len(df)):
    try:
        port_name = str(row[port_column]).strip()

        # Si tu as une colonne country, utilise-la
        if "country" in df.columns and pd.notna(row["country"]):
            query = f"{port_name} port, {row['country']}"
        else:
            query = f"{port_name} port"

        location = geolocator.geocode(query)

        if location:
            coords.append(f"{location.latitude:.7f},{location.longitude:.7f}")
            print(f"{query} -> {location.latitude:.7f},{location.longitude:.7f}")
        else:
            coords.append("")
            print(f"{query} -> introuvable")

    except Exception as e:
        coords.append("")
        print(f"Erreur pour {row}: {e}")

    # Pause pour éviter d'envoyer trop de requêtes
    time.sleep(1)

df["coordinates"] = coords
df.to_csv(output_file, index=False, encoding="utf-8-sig")

print(f"\nFichier généré : {output_file}")