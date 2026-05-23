# BOE Tracker

Workflow de GitHub Actions que descarga diariamente los sumarios del BOE estatal y los boletines oficiales de las 17 CCAA españolas, filtra las disposiciones relevantes (Secciones I y III) y los sube organizados a Google Drive.

## Boletines cubiertos

| ID | Boletín | Fuente |
|----|---------|--------|
| BOE | Boletín Oficial del Estado | API JSON oficial |
| BOCM | Boletín Oficial de la Comunidad de Madrid | Scraping HTML |
| DOGC | Diari Oficial de la Generalitat de Catalunya | Scraping HTML |
| BOJA | Boletín Oficial de la Junta de Andalucía | Scraping HTML |
| DOGA | Diario Oficial de Galicia | Scraping HTML |
| BOPV | Boletín Oficial del País Vasco | Scraping HTML |
| BOC | Boletín Oficial de Canarias | Scraping HTML |
| BORM | Boletín Oficial de la Región de Murcia | Scraping HTML |
| DOCV | Diari Oficial de la Comunitat Valenciana | Scraping HTML |
| BOA | Boletín Oficial de Aragón | Scraping HTML |
| BOPA | Boletín Oficial del Principado de Asturias | Scraping HTML |
| BOIB | Butlletí Oficial de les Illes Balears | Scraping HTML |
| BOCYL | Boletín Oficial de Castilla y León | Scraping HTML |
| DOCM | Diario Oficial de Castilla-La Mancha | Scraping HTML |
| DOE | Diario Oficial de Extremadura | Scraping HTML |
| BOR | Boletín Oficial de La Rioja | Scraping HTML |
| BON | Boletín Oficial de Navarra | Scraping HTML |
| BOC-CANT | Boletín Oficial de Cantabria | Scraping HTML |

## Estructura en Google Drive

```
BOE-Tracker/          ← carpeta raíz (GOOGLE_DRIVE_FOLDER_ID)
└── 2026/
    └── 05/
        └── 23/
            ├── BOE/
            │   ├── sumario.json
            │   └── pdfs/
            │       ├── BOE-A-2026-XXXX.pdf
            │       └── ...
            ├── BOCM/
            │   ├── sumario.json
            │   └── pdfs/
            └── ...
```

## Configuración paso a paso

### 1. Crear proyecto en Google Cloud Console

1. Ve a [https://console.cloud.google.com](https://console.cloud.google.com)
2. Haz clic en el selector de proyecto (arriba a la izquierda) → **Nuevo proyecto**
3. Ponle un nombre (p. ej. `boe-tracker`) y haz clic en **Crear**
4. Asegúrate de que el proyecto nuevo está seleccionado

### 2. Activar la Google Drive API

1. En el menú lateral: **APIs y servicios → Biblioteca**
2. Busca "Google Drive API"
3. Haz clic en **Habilitar**

### 3. Crear una Service Account y descargar las credenciales

1. Ve a **APIs y servicios → Credenciales**
2. Haz clic en **Crear credenciales → Cuenta de servicio**
3. Rellena el nombre (p. ej. `boe-tracker-sa`) y haz clic en **Crear y continuar**
4. En el paso de roles, puedes omitirlo y hacer clic en **Listo**
5. En la lista de cuentas de servicio, haz clic en la que acabas de crear
6. Ve a la pestaña **Claves → Agregar clave → Crear clave nueva → JSON**
7. Se descargará un archivo `.json` — **guárdalo en lugar seguro**

### 4. Compartir la carpeta de Drive con la Service Account

1. Ve a [Google Drive](https://drive.google.com) y crea una carpeta llamada `BOE-Tracker`
2. Haz clic derecho en la carpeta → **Compartir**
3. En el campo "Agregar personas", pega el email de la Service Account  
   (tiene el formato `nombre@proyecto.iam.gserviceaccount.com`)
4. Selecciona el rol **Editor** y haz clic en **Enviar**
5. Copia el **ID de la carpeta** desde la URL:  
   `https://drive.google.com/drive/folders/`**`ESTE_ES_EL_ID`**

### 5. Añadir los secrets en GitHub

1. En tu repositorio de GitHub: **Settings → Secrets and variables → Actions**
2. Haz clic en **New repository secret** y añade los dos siguientes:

| Secret | Valor |
|--------|-------|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Contenido completo del archivo `.json` descargado en el paso 3 |
| `GOOGLE_DRIVE_FOLDER_ID` | ID de la carpeta `BOE-Tracker` de Drive (paso 4) |

### 6. Primer run manual para verificar

1. Ve a **Actions → Daily BOE Tracker** en tu repositorio
2. Haz clic en **Run workflow**
3. Opcionalmente, introduce una fecha en formato `YYYY-MM-DD` o deja vacío para usar hoy
4. Haz clic en **Run workflow** (botón verde)
5. Espera a que termine y comprueba:
   - Los logs del job para ver el resumen de actos y PDFs descargados
   - Tu carpeta de Google Drive para verificar que los archivos aparecen

## Ejecución local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Exportar credenciales
export GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
export GOOGLE_DRIVE_FOLDER_ID="tu_folder_id"

# Ejecutar para hoy
python main.py

# Ejecutar para una fecha concreta
python main.py --date 2026-05-20

# Solo algunos boletines
python main.py --bulletins BOE BOCM DOGC

# Dry-run (sin subir a Drive)
python main.py --no-upload
```

## Filtrado de secciones

Solo se descargan actos de:
- **Sección I** — Disposiciones generales
- **Sección III** — Otras disposiciones

Se excluyen: Sección II (Autoridades y personal), Sección IV (Administración de Justicia), Sección V (Anuncios), edictos y subastas.

## Límites y comportamiento de errores

- **Tamaño máximo por PDF**: 10 MB (los más grandes se descartan con un warning)
- **Delay entre descargas**: 1,5 segundos para no sobrecargar los servidores
- **Reintentos automáticos**: 3 intentos con backoff exponencial ante errores HTTP
- **Aislamiento de errores**: si un boletín falla, el job continúa con los demás
- **Re-runs**: si el workflow se vuelve a lanzar el mismo día, los archivos existentes en Drive se sobreescriben

## Formato de `sumario.json`

```json
{
  "bulletin": "BOE",
  "date": "2026-05-23",
  "acts": [
    {
      "id": "BOE-A-2026-XXXX",
      "title": "Real Decreto ...",
      "section": "I",
      "section_name": "Disposiciones generales",
      "rank": "Real Decreto",
      "organism": "Ministerio de ...",
      "pdf_url": "https://www.boe.es/boe/dias/.../BOE-A-2026-XXXX.pdf",
      "summary": "Texto del sumario...",
      "date": "2026-05-23"
    }
  ]
}
```

## Notas sobre scrapers de CCAA

Los scrapers de CCAA realizan scraping HTML de las webs oficiales de cada boletín. Las webs pueden cambiar su estructura sin previo aviso; si un scraper deja de funcionar, revisa la URL del boletín correspondiente y ajusta los selectores CSS/HTML en el archivo del scraper.

La API del BOE estatal es estable y está oficialmente documentada en [datos.boe.es](https://www.boe.es/datosabiertos/).
