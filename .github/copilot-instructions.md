# SIGREP: commit y despliegue

## Autorizacion del usuario

- Cuando el usuario solicite "commit y deploy", "commit y despliegue", "publica
  los cambios" o equivalente, ejecutar el flujo completo de la tarea actual sin
  pedir confirmaciones adicionales para pasos rutinarios autorizados.
- No hacer commit ni desplegar automaticamente por cada edicion: esperar esa
  solicitud explicita. Si pide "solo labels", no construir ni desplegar imagenes,
  ni cambiar variables de entorno o bases de datos.

## Flujo requerido

1. Revisar estado y diff; ejecutar las validaciones pertinentes. Incluir en el
   commit solo los archivos de la tarea. Preservar cambios ajenos, sin descartarlos
   ni agregarlos por conveniencia para limpiar el arbol.
2. Sincronizar la rama sin sobrescribir trabajo, crear el commit y hacer push.
   Si el script necesita un arbol limpio, usar un worktree temporal del commit
   publicado para no mezclar los cambios pendientes del usuario.
3. Revisar el flujo de CI vigente y sus resultados. El job de Dokploy del modo
   Stack puede estar omitido cuando se usa Application/Dockerfile; no interpretar
   CI exitoso o imagen publicada como despliegue completado.
4. Usar `deploy.ps1` o el procedimiento de despliegue existente autorizado. Para
   labels, usar `deploy.ps1 -SoloLabels` o `scripts/apply-traefik.sh` por SSH.
   Si falta `.deploy-secrets`, revisar tambien las variables de entorno y la
   carpeta local `CRENDENCIALES-SERVIDORES` (puede estar anidada). Identificar
   host, usuario y ruta de llave sin imprimir secretos. Usar la llave local con
   el cliente SSH, sin abrir ni transcribir su contenido. Validar la identidad
   del host; no desactivar la comprobacion SSH.
5. Descubrir el servicio SIGREP vigente por SSH antes de aplicar labels: el nombre
   puede cambiar al recrear la Application. No asumir el nombre de un despliegue
   anterior ni modificar servicios de otros proyectos.
6. Despues del despliegue, comprobar los labels Traefik, la respuesta HTTPS del
   sitio, `/api/v1/salud` y `/version.txt`. Confirmar que frontend y API ejecutan
   el commit publicado. Aplicar solo los labels necesarios si Dokploy los borro.
7. Informar commit, push y resultado real de despliegue/verificacion. Si existe
   un bloqueo de acceso, permisos, CI o configuracion, indicar el bloqueo exacto;
   no afirmar exito ni repetir operaciones que no lo pueden resolver.

## Secretos

- Nunca versionar `.env`, `.deploy-secrets`, la carpeta de credenciales, llaves
  privadas, tokens ni contrasenas. Tampoco imprimirlos en logs o en el chat.
- Las credenciales pegadas en el chat deben rotarse; preferir acceso local no
  expuesto. Pedir al usuario que complete secretos directamente en su entorno
  cuando realmente falten, nunca mediante preguntas que los envien al modelo.