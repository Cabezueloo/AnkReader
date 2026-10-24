# AnkReader

Complemento de [Anki](https://apps.ankiweb.net/) que convierte el vocabulario
consultado en un Kindle en tarjetas de repaso. También permite añadir palabras
manualmente o enviarlas desde otro dispositivo de la red local.

## Funciones

- Sincroniza las consultas en inglés de la base `vocab.db` del Kindle.
- Organiza las tarjetas en submazos con el prefijo `Kindle::` y el título del
  libro.
- Añade traducción, definición, pronunciación, audio, sinónimos y ejemplos
  cuando están disponibles.
- Descarga imágenes de Pixabay en segundo plano si se configura una clave de
  API.
- Permite crear tarjetas manualmente desde el menú de Anki.
- Ofrece un servidor HTTP local para recibir palabras desde un dispositivo
  móvil.

## Requisitos

- Anki 2.1.50 o posterior.
- Linux para la búsqueda automática del Kindle en `/run/media`, `/media` y
  `/mnt`. Si el dispositivo está montado en otra ubicación, se puede indicar en
  la configuración.
- Conexión a Internet para consultar los servicios de diccionario, traducción,
  audio e imágenes.

El complemento usa módulos incluidos con Python y Anki; no requiere instalar
dependencias Python adicionales.

## Instalación

1. Cierra Anki.
2. Clona este repositorio dentro de la carpeta de complementos de Anki, usando
   `ankreader` como nombre de la carpeta del complemento. En Linux, normalmente:

   ```bash
   cd ~/.local/share/Anki2/addons21
   git clone <URL-DE-ESTE-REPOSITORIO> ankreader
   ```

3. Crea la configuración local a partir de la plantilla:

   ```bash
   cd ankreader
   cp config.example.json config.json
   ```

4. Si quieres usar imágenes de Pixabay o la traducción alternativa de DeepL,
   añade tus claves a `config.json`.
5. Abre Anki. En el menú **Herramientas > AnkReader**, encontrarás las opciones
   para sincronizar el Kindle y añadir una palabra manualmente.

La ubicación de la carpeta de complementos puede variar según el sistema
operativo. También puedes instalar el complemento copiando su carpeta dentro de
`addons21` y reiniciando Anki.

## Configuración

`config.example.json` contiene los valores iniciales. La copia local
`config.json` puede incluir claves de API y el estado de sincronización, por lo
que está excluida de Git.

| Opción | Descripción |
| --- | --- |
| `kindle_mount_base` | Ruta base donde buscar el Kindle; por defecto `/run/media`. |
| `vocab_db_relative_path` | Ruta de `vocab.db` dentro del Kindle. |
| `last_sync_timestamp` | Marca temporal desde la que importar consultas. |
| `target_deck_prefix` | Prefijo de los submazos creados; por defecto `Kindle::`. |
| `pixabay_api_key` | Clave opcional para añadir imágenes. |
| `deepl_api_key` | Clave opcional de respaldo para traducciones. |
| `show_mobile_notifications` | Muestra avisos cuando se reciben palabras desde el móvil. |

La clave de Pixabay es necesaria para las imágenes. DeepL solo se usa como
respaldo cuando falla la traducción de Google. No añadas claves reales a
`config.example.json` ni las subas al repositorio.

## Envío desde un dispositivo móvil

Al iniciar Anki, AnkReader abre un servidor HTTP en el puerto `8080`, escuchando
en las interfaces de red del equipo. Desde un dispositivo de la misma red se
puede enviar una palabra con una petición como:

```text
http://IP-LOCAL-DEL-ORDENADOR:8080/?word=serendipity
```

Este servidor no tiene autenticación. Úsalo únicamente en una red de confianza
y no expongas el puerto a Internet. Si no necesitas esta función, bloquea el
puerto `8080` mediante el cortafuegos del sistema.

## Desarrollo y comprobaciones

El código fuente del complemento está en la raíz del repositorio. Para comprobar
la sintaxis de los módulos Python sin iniciar Anki:

```bash
python -m compileall -q .
```

## Licencia

Este repositorio todavía no especifica una licencia. Añade una antes de
redistribuir el proyecto.
