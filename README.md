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
