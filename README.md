# Consejo de Investigación · UCCuyo

Sitio del Consejo. Misma planilla que Streamlit; **solo agrega filas**. El sistema de Streamlit no se toca.

## Publicar en Vercel (Hobby, sin tarjeta)

1. Entrá a [vercel.com](https://vercel.com) con GitHub o email. El plan Hobby no pide tarjeta.
2. New Project → Importá esta carpeta (`prototipo`) o el repo del sitio.
3. Framework: **FastAPI**. Deploy.

Para leer y escribir la planilla real, en Vercel → Settings → Environment Variables:

- `GOOGLE_SA_JSON` = el JSON de la cuenta de servicio (el mismo `gcp_service_account` de Streamlit Cloud), en una sola línea.

Sin esa variable el sitio igual abre y muestra los temas ya cacheados.
