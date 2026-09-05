import os
import datetime
import requests
import pyodbc
import pandas as pd
from io import StringIO

API_URL = os.getenv("API_URL", "https://www.datos.gov.co/resource/v8qi-smj7.csv")
SERVER = os.getenv("SQL_SERVER", r"DESKTOP-26TKEMA\JUANOSPINA")
DATABASE = os.getenv("SQL_DATABASE", "db_cobertura_movil")
USER = os.getenv("SQL_USER", "")
PASSWORD = os.getenv("SQL_PASSWORD", "")
DRIVER = os.getenv("ODBC_DRIVER", "ODBC Driver 17 for SQL Server")

CONN_STR = (
    f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={DATABASE};"
    + (f"UID={USER};PWD={PASSWORD};TrustServerCertificate=yes;" if USER else "Trusted_Connection=yes;")
)

TECNOLOGIAS = [
    {"columna": "cobertura_2g", "generacion": "2G", "detalle": "Cobertura 2G"},
    {"columna": "cobertura_3g", "generacion": "3G", "detalle": "Cobertura 3G"},
    {"columna": "cobertura_hspa_hspa_dc", "generacion": "3.5G", "detalle": "HSPA / HSPA+DC"},
    {"columna": "cobertuta_4g", "generacion": "4G", "detalle": "Cobertura 4G"},
    {"columna": "cobertura_lte", "generacion": "4G", "detalle": "Cobertura LTE"},
    {"columna": "cobertura_5g", "generacion": "5G", "detalle": "Cobertura 5G"},
]

def es_valido(val):
    return val is not None and not pd.isna(val) and str(val).strip() != ""

def obtener_ubicacion(item):
    codigo = item.get("cod_centro_poblado")
    municipio = item.get("centro_poblado")
    if not es_valido(codigo) or not es_valido(municipio):
        codigo = item.get("cod_municipio")
        municipio = item.get("municipio")
    if not es_valido(codigo) or not es_valido(municipio):
        return None, None
    return str(codigo).strip(), str(municipio).strip()

def cargar_dimensiones(cursor, datos):
    # Operadores
    operadores = set(str(item["proveedor"]).strip() for item in datos if es_valido(item.get("proveedor")))
    for op in operadores:
        cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM [dim_operador] WHERE nombre_operador = ?)
                INSERT INTO [dim_operador] (nombre_operador) VALUES (?)
        """, (op, op))
    cursor.execute("SELECT nombre_operador, id_operador FROM [dim_operador]")
    map_op = {row[0]: row[1] for row in cursor.fetchall()}

    # Tecnologías
    for tech in TECNOLOGIAS:
        cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM [dim_tecnologia] WHERE generacion = ? AND tecnologia_detalle = ?)
                INSERT INTO [dim_tecnologia] (generacion, tecnologia_detalle) VALUES (?, ?)
        """, (tech["generacion"], tech["detalle"], tech["generacion"], tech["detalle"]))
    cursor.execute("SELECT generacion, tecnologia_detalle, id_tecnologia FROM [dim_tecnologia]")
    map_tech = {(row[0], row[1]): row[2] for row in cursor.fetchall()}

    # Tiempos
    tiempos = set()
    for item in datos:
        if es_valido(item.get("a_o")) and es_valido(item.get("trimestre")):
            tiempos.add((int(float(item["a_o"])), int(float(item["trimestre"]))))
    for anio, tri in tiempos:
        mes = (tri - 1) * 3 + 1
        fecha = f"{anio}-{mes:02d}-01"
        cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM [dim_tiempo] WHERE anio = ? AND trimestre = ?)
                INSERT INTO [dim_tiempo] (fecha, anio, trimestre, mes) VALUES (?, ?, ?, ?)
        """, (anio, tri, fecha, anio, tri, mes))
    cursor.execute("SELECT anio, trimestre, id_tiempo FROM [dim_tiempo]")
    map_tiem = {(row[0], row[1]): row[2] for row in cursor.fetchall()}

    # Ubicaciones
    ubicaciones = set()
    for item in datos:
        divipola, muni = obtener_ubicacion(item)
        tipo = item.get("cabecera_municipal") if es_valido(item.get("cabecera_municipal")) else "N/A"
        if divipola and muni:
            ubicaciones.add((divipola, muni, tipo))
    for divipola, muni, tipo in ubicaciones:
        cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM [dim_ubicacion] WHERE codigo_divipola = ? AND municipio = ?)
                INSERT INTO [dim_ubicacion] (codigo_divipola, municipio, tipo_centro_poblado) VALUES (?, ?, ?)
        """, (divipola, muni, divipola, muni, tipo))
    cursor.execute("SELECT codigo_divipola, municipio, id_ubicacion FROM [dim_ubicacion]")
    map_ubi = {(row[0], row[1]): row[2] for row in cursor.fetchall()}

    return map_op, map_tech, map_tiem, map_ubi

def ejecutar_pipeline():
    #os.makedirs("output", exist_ok=True)
    
    # 1. Extracción de API
    print("1. Descargando datos de la API...")
    res = requests.get(API_URL, timeout=90)
    res.raise_for_status()
    
    # dtype=str preserva ceros a la izquierda y evita casting a float de nulos
    df_raw = pd.read_csv(StringIO(res.text), dtype=str)
    datos = df_raw.to_dict(orient="records")

    # 2. Archivo de Muestra con Pandas
    archivo_muestra = "src/static/xlsx/ingestion.xlsx"
    df_raw.head(100).to_excel(archivo_muestra, index=False, engine="openpyxl")
    print(f"2. Muestra exportada exitosamente en {archivo_muestra}")

    # 3. Carga en Base de Datos
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    print("3. Actualizando tablas de dimensiones...")
    map_op, map_tech, map_tiem, map_ubi = cargar_dimensiones(cursor, datos)
    conn.commit()

    print("4. Transformando e Insertando Tabla de Hechos...")
    hechos = []
    for item in datos:
        op_nombre = str(item.get("proveedor")).strip() if es_valido(item.get("proveedor")) else None
        anio = int(float(item["a_o"])) if es_valido(item.get("a_o")) else None
        tri = int(float(item["trimestre"])) if es_valido(item.get("trimestre")) else None
        divipola, muni = obtener_ubicacion(item)

        id_op = map_op.get(op_nombre)
        id_tiem = map_tiem.get((anio, tri))
        id_ubi = map_ubi.get((divipola, muni))

        if not all([id_op, id_tiem, id_ubi]):
            continue

        for tech in TECNOLOGIAS:
            val = item.get(tech["columna"])
            if es_valido(val):
                id_tech = map_tech.get((tech["generacion"], tech["detalle"]))
                activa = 1 if str(val).strip().upper() in ['SI', '1', 'TRUE'] else 0
                hechos.append((id_ubi, id_op, id_tech, id_tiem, activa, activa))

    query_fact = """
        INSERT INTO [fact_cobertura_movil] (
            id_ubicacion, id_operador, id_tecnologia, id_tiempo,
            cobertura_activa, num_sitios_reportados
        ) VALUES (?, ?, ?, ?, ?, ?)
    """
    if hechos:
        cursor.fast_executemany = True
        cursor.executemany(query_fact, hechos)
        conn.commit()

    # 4. Generación de Archivo de Auditoría (.txt)
    cursor.execute("SELECT COUNT(*) FROM [fact_cobertura_movil]")
    total_db = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    archivo_auditoria = "src/static/auditoria/ingesta.txt"
    with open(archivo_auditoria, "w", encoding="utf-8") as f:
        f.write(f"===================================================\n")
        f.write(f"REPORTE DE AUDITORÍA Y CONCILIACIÓN ETL\n")
        f.write(f"===================================================\n")
        f.write(f"Fecha Ejecución : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Registros API   : {len(datos):,}\n")
        f.write(f"Hechos Generados: {len(hechos):,}\n")
        f.write(f"Total en BDD    : {total_db:,}\n")
        f.write(f"Estado Ingesta  : OK - PROCESO COMPLETADO\n")
        f.write(f"===================================================\n")
    print(f"5. Auditoría generada en {archivo_auditoria}")

if __name__ == "__main__":
    ejecutar_pipeline()