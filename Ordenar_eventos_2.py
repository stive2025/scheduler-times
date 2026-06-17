import pandas as pd

def procesar_asistencias(archivo_entrada, archivo_salida):
    # 1. Leer el archivo Excel
    df = pd.read_excel(archivo_entrada)
    
    # 2. Asegurar el formato de fecha y hora
    df['Fecha'] = pd.to_datetime(df['Fecha']).dt.date
    df['Hora_str'] = df['Hora'].astype(str)
    
    # 3. Ordenar cronológicamente por empleado, fecha y hora
    df = df.sort_values(by=['Empleado', 'Fecha', 'Hora_str'])
    
    resultados = []
    
    # 4. Agrupar la data por Empleado y Día
    for (empleado, nombre, fecha), grupo in df.groupby(['Empleado', 'Nombre', 'Fecha']):
        tiempos = grupo['Hora_str'].tolist()
        
        # Diccionario para almacenar los marcajes del día
        slots = {
            'Entrada Mañana': None, 
            'Salida Mañana': None, 
            'Entrada Tarde': None, 
            'Salida Tarde': None
        }
        anotaciones = []
        
        # 5. Clasificar cada marcaje en su ventana de tiempo correspondiente
        # Eliminar dobles marcaciones muy cercanas (ej: dentro de 5 minutos)
        tiempos_limpios = []
        for hora in tiempos:
            partes = hora.split(':')
            h = int(partes[0])
            m = int(partes[1])
            s = int(partes[2]) if len(partes) > 2 else 0
            t_val = h + (m / 60.0) + (s / 3600.0)
            if not tiempos_limpios:
                tiempos_limpios.append((hora, t_val))
            else:
                last_h, last_t = tiempos_limpios[-1]
                # round to avoid floating point > issues, diff > 5 mins means diff > 5.0/60.0
                if round(t_val - last_t, 5) > round(5.0 / 60.0, 5): 
                    tiempos_limpios.append((hora, t_val))
                else:
                    anotaciones.append(f"Ignorado por cercanía: {hora}")

        if len(tiempos_limpios) == 4:
            slots['Entrada Mañana'] = tiempos_limpios[0][0]
            slots['Salida Mañana'] = tiempos_limpios[1][0]
            slots['Entrada Tarde'] = tiempos_limpios[2][0]
            slots['Salida Tarde'] = tiempos_limpios[3][0]
        elif len(tiempos_limpios) == 2:
            t0 = tiempos_limpios[0][1]
            t1 = tiempos_limpios[1][1]
            if t0 >= 12.0:
                slots['Entrada Tarde'] = tiempos_limpios[0][0]
                slots['Salida Tarde'] = tiempos_limpios[1][0]
            elif t1 <= 14.5:
                slots['Entrada Mañana'] = tiempos_limpios[0][0]
                slots['Salida Mañana'] = tiempos_limpios[1][0]
            else:
                slots['Entrada Mañana'] = tiempos_limpios[0][0]
                slots['Salida Tarde'] = tiempos_limpios[1][0]
        else:
            for hora, time_val in tiempos_limpios:
                if time_val < 11.5:
                    if not slots['Entrada Mañana']: slots['Entrada Mañana'] = hora
                    else: slots['Salida Mañana'] = hora
                elif 11.5 <= time_val < 14.0:
                    if not slots['Salida Mañana']: slots['Salida Mañana'] = hora
                    elif not slots['Entrada Tarde']: slots['Entrada Tarde'] = hora
                    else: anotaciones.append(f"Doble picada mediodía: {hora}")
                elif 14.0 <= time_val < 16.0:
                    if not slots['Entrada Tarde']: slots['Entrada Tarde'] = hora
                    elif not slots['Salida Tarde']: slots['Salida Tarde'] = hora
                    else: anotaciones.append(f"Doble picada tarde: {hora}")
                else:
                    if not slots['Salida Tarde']: slots['Salida Tarde'] = hora
                    elif not slots['Entrada Tarde']: 
                        # Si picó por primera vez pasadas las 16:00, ponerlo en entrada tarde
                        slots['Entrada Tarde'] = slots['Salida Tarde']
                        slots['Salida Tarde'] = hora
                    else: anotaciones.append(f"Doble picada tarde out: {hora}")
                    
        # 6. Lógica para detectar faltas u olvidos de marcación
        faltantes = sum([1 for v in slots.values() if v is None])
        
        if faltantes == 2:
            # Validar si es una jornada de medio tiempo (Ej: Solo tiene entrada y salida en la mañana)
            if (slots['Entrada Mañana'] and slots['Salida Mañana']) or (slots['Entrada Tarde'] and slots['Salida Tarde']):
                anotaciones.append("Medio tiempo")
            else: 
                anotaciones.append("Faltan 2 marcaciones (Olvido)")
        elif faltantes == 3: 
            anotaciones.append("Solo 1 marcación en el día (Olvido)")
        elif faltantes == 1: 
            anotaciones.append("Falta 1 marcación (Olvido)")
            
        # 7. Guardar el registro procesado del empleado en ese día
        resultados.append({
            'Empleado': empleado,
            'Nombre': nombre, 
            'Fecha': fecha,
            'Entrada Mañana': slots['Entrada Mañana'], 
            'Salida Mañana': slots['Salida Mañana'],
            'Entrada Tarde': slots['Entrada Tarde'], 
            'Salida Tarde': slots['Salida Tarde'],
            'Anotaciones': " | ".join(anotaciones) if anotaciones else "Jornada Completa"
        })
        
    # 8. Generar el Excel de salida
    df_resultado = pd.DataFrame(resultados)
    df_resultado.to_excel(archivo_salida, index=False)
    print(f"Archivo exportado con éxito a: {archivo_salida}")
    return df_resultado

# --- Ejecución ---
# Asegúrate de instalar dependencias previas si no las tienes: 
# pip install pandas openpyxl

archivo_origen = 'accesos_validos.xlsx'
archivo_destino = 'reporte_asistencias.xlsx'

df_final = procesar_asistencias(archivo_origen, archivo_destino)