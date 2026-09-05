Descripcion

Script en Python que extrae datos de una API de la pagina web de datos abiertos, de la cobertura móvil de tecnologia del departamento de santandery los carga en un modelo en estrella (SQL Server) compuesto por 4 dimensiones y 1 tabla de hechos.

Las cuales son las siguientes:

Dim_tecnologia
Dim_tiempo
Dim_operador
Dim_ubicacion
Fact_cobertura_movil

Clonar e instalar dependencias:
git clone https://github.com/chonto329/CoberturaMovil.git
cd tu-repo
pip install requests pyodbc


Ejecutar el proceso:
Configura el servidor y la base de datos en el archivo ingestion.py y corre:

python ingestion.py

Automatizacion y Evidencias

GitHub Actions: El workflow (.github/workflows/bigdata.yml) se ejecuta automáticamente en cada push. Levanta SQL Server, crea las tablas y ejecuta el ETL.

Verificacion: Revisa la pestaña Actions en GitHub para ver los logs de ejecución.

Descarga de Evidencias: En el detalle de la corrida completada, descarga el archivo en Artifacts (etl-execution-evidence) para obtener los logs y el archivo .csv con la validación de los datos cargados.