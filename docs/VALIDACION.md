# Validación de MOLT

Instancia de desarrollo preparada el **19 de octubre de 2026 (Perú)**.

## Datos oficiales

- Acceso real verificado a `www.gob.pe/52005`, el portal y la API OECE.
- Primera consulta y repetición completa de `/api/v1/recordsAfter`: **17.231 registros, 173 páginas**, ventana **21/07/2026–19/10/2026**.
- La consulta inicial seleccionó 100 candidatos nacionales. Tras la depuración final de nombres administrativos, usos de obras civiles y vigilancia de accesos: **77 coincidencias en las zonas configuradas** por la ubicación disponible (en esta muestra, domicilio del comprador).
- Distribución de la muestra: **Lima 59, Cusco 11, Arequipa 7, Trujillo 0**. Cero coincidencias no acredita ausencia de negocios fuera de esta ventana o fuente.
- **0 vigentes confirmadas por las reglas conservadoras**, **77 históricas** en las zonas. No se presentan adjudicaciones ni fechas vencidas como ofertas abiertas.
- **42** de las coincidencias regionales tienen señales de contratos/eventos integrales; su alcance técnico debe verificarse.
- La API devuelve domicilios de entidades, montos y documentos; la ubicación de la entidad puede diferir del lugar de prestación.

## Pruebas

- **52 pruebas automatizadas** de autenticación, CSRF, filtros, clasificación, geografía, contratos integrales con pantallas en un TDR de prueba, persistencia de notas, paginación/reanudación, enlaces permitidos, Excel, programación en hora de Perú y envío simulado.
- Prueba de navegador con registros públicos reales en una **base temporal**, escritorio y móvil, sin modificar la cuenta real. Comprueba creación de acceso, búsqueda, detalle, seguimiento, Excel filtrado, preferencias, vista previa de correo y cierre de sesión.
- Comprobación real del servidor con `/health`. Instalación reproducible con `uv.lock` y scripts de instalación/arranque.
- Excel generado a partir de los registros reales de la instancia, con fuente y alcance incluidos en otra hoja.
- Lectura real de PDFs oficiales de SEACE: bases de producción de eventos, ferias y compras de pantallas. Se verificaron extracción de texto, límites y hallazgos; por ejemplo, una compra de pantalla LED también contiene micrófonos inalámbricos en sus especificaciones. Las coincidencias de plantillas legales no convierten por sí solas una compra de equipos en producción integral de eventos.

## Pendiente de configuración externa

1. **Cola de documentos:** `prod1.seace.gob.pe` fue bloqueado inicialmente; después respondió y se verificó lectura real de PDFs. Su permiso quedó guardado en el borrador del entorno. La cola restante continúa en segundo plano; los errores iniciales pueden reintentarse desde la ficha. No se ha revisado toda la cola. Escaneados y ZIP requieren revisión manual; las lecturas parciales se indican y el límite actual es 160 páginas/400.000 caracteres por PDF.
2. **Correos reales:** el destinatario indicado se guardó en configuración local privada. Falta una `RESEND_API_KEY` y `MOLT_MAIL_FROM` autorizado. No se han enviado correos reales ni se ha verificado llegada a Gmail. El resumen automático permanece desactivado hasta su configuración.
3. **Uso permanente:** requiere un servidor privado encendido con HTTPS. No se ha publicado en un dominio ni desplegado como servicio permanente. Los datos e instrucciones del entorno cloud están preparados para revisión/publicación; esa publicación no equivale a desplegar una aplicación web permanente.

No se incluyen ejemplos inventados en la base operativa. Las fixtures sintéticas solo existen en las pruebas.
