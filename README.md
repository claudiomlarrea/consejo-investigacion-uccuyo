# Consejo de Investigación · UCCuyo

Sitio del Consejo. Misma planilla que Streamlit; **solo agrega filas**. El sistema de Streamlit no se toca.

## Publicar en Vercel (Hobby, sin tarjeta)

1. Entrá a [vercel.com](https://vercel.com) con GitHub o email. El plan Hobby no pide tarjeta.
2. New Project → Importá esta carpeta (`prototipo`) o el repo del sitio.
3. Framework: **FastAPI**. Deploy.

Para leer y escribir la planilla real, en Vercel → Settings → Environment Variables:

- `GOOGLE_SA_JSON` = el JSON de la cuenta de servicio (el mismo `gcp_service_account` de Streamlit Cloud), en una sola línea.

Sin esa variable el sitio igual abre y muestra los temas ya cacheados.

El audio del aula usa STUN público. Para redes que lo bloquean, en Vercel → Settings → Environment Variables:

- `TURN_URLS` = una o más URLs TURN separadas por coma (por ejemplo `turn:turn.ejemplo.edu:3478?transport=udp,turns:turn.ejemplo.edu:5349`).
- `TURN_USERNAME` y `TURN_CREDENTIAL` = usuario y clave de ese servidor. No van en el código.

Si `TURN_URLS` no está, el aula sigue con STUN.

## Complemento de Google Meet

El aula puede vivir adentro de Meet: el escenario principal es la mesa, y el panel lateral lleva el orden del día y la palabra. Meet sigue con el audio, la cámara, la pantalla, el chat y la grabación. Quien abre `/aula` en el navegador, fuera de Meet, sigue con el micrófono del aula.

En Vercel → Settings → Environment Variables, en el proyecto que sirve el sitio:

- `MEET_CLOUD_PROJECT_NUMBER` = el **número** del proyecto de Google Cloud (solo dígitos, no el ID con letras).

Después hay que volver a desplegar para que las páginas lo lean. Sin esa variable el sitio sigue igual y el aula suelta no se rompe.

Para registrar el complemento, en [Google Cloud Console](https://console.cloud.google.com/):

1. Creá o elegí el proyecto. En el panel principal copiá el **Project number**. Ese valor es `MEET_CLOUD_PROJECT_NUMBER`.
2. En el buscador de la consola, abrí **Google Workspace Marketplace SDK** y tocá **Enable**. Es el SDK, no la «Google Workspace Marketplace API».
3. Repetí la búsqueda y habilitá **Google Workspace add-ons API**.
4. En APIs y servicios → Pantalla de consentimiento de OAuth, configurá la pantalla. Si el Workspace es de la universidad, el tipo Internal alcanza para probarla adentro del dominio.
5. Volvé a Google Workspace Marketplace SDK → **HTTP deployments** → **Create new deployment**. El ID puede ser `aula-uccuyo`.
6. En el JSON del deployment pegá lo que responde `https://consejo-investigacion-uccuyo.vercel.app/aula/manifest.json` (el mismo host donde está publicado el sitio). Tiene que incluir `sidePanelUrl` (`/aula/panel`), `mainStageUrl` (`/aula`) y `addOnOrigins` con ese origen, sin barra al final.
7. En la configuración de la app del Marketplace SDK, activá la integración **Meet add-on** y elegí ese deployment.
8. En HTTP deployments, instalá el deployment en la cuenta con la que vas a probar.
9. Entrá a una reunión de Meet → Actividades → Aula UCCuyo. El panel abre el aula en el escenario para todos. No hace falta cambiar de pestaña.

El origen del manifest y el de Vercel tienen que ser el mismo. Un preview de Vercel tiene otro dominio y no coincide con un complemento registrado para producción.
