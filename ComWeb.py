import dash
from dash import dcc, html, Input, Output, State
import serial
import time
import threading
import numpy as np
import redpitaya_scpi as scpi
import datetime
import csv

# Variables globales
valor_integral = 0.0
datos_ciclos = []

#FUNCIONES DE COMANDOS
def enviar_comando(comando,ser, etiqueta=None):
    """Envía comando al Arduino y recibe respuesta"""
    if ser is None:
        print("Conexión serial no disponible")
        return None
    
    try:
        ser.write((comando + "\n").encode('utf-8'))
        time.sleep(0.3)
        respuesta = ser.readline().decode('utf-8').strip()
        if respuesta:
            if etiqueta:
                print(f"{etiqueta}: {respuesta}")
            return respuesta
        else:
            print("No se recibió respuesta del dispositivo.")
            return None
    except Exception as e:
        print(f"Error al enviar comando: {e}")
        return None

def medirciclo(comando, ser,etiqueta=None):
    intentos = 3
    for i in range(intentos):
        ser.reset_input_buffer()  # Limpiar buffer antes de enviar
        ser.write((comando + "\n").encode('utf-8'))
        
        # Esperar más tiempo para comandos de medición (balanza necesita tiempo)
        if "MEDicion" in comando:
            time.sleep(0.8)  # La balanza toma 10 muestras
        else:
            time.sleep(0.2)
        
        respuesta = ser.readline().decode('utf-8').strip()
        
        # Si recibimos respuesta válida, devolverla
        if respuesta:
            return respuesta
        
        # Si está vacía y quedan intentos, esperar un poco más
        if i < intentos - 1:
            time.sleep(0.3)
    
    return ""  # Devolver cadena vacía si fallan todos los intentos

def guardar_csv():
    """Guarda los datos recolectados en un archivo CSV."""
    if not datos_ciclos:
        print("No hay datos para guardar.")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"datos_ciclos.csv"
    
    with open(nombre_archivo, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Peso (g)', 'Integral Red Pitaya'])
        writer.writerows(datos_ciclos)
    
    print(f"Datos guardados en: {nombre_archivo}")

def monitorear_ciclo(ser):
    """Monitorea ciclos cada 1 segundo y guarda datos."""
    global datos_ciclos
    datos_ciclos = []
    
    print("\nIniciando monitoreo de ciclos...")
    
    while True:
        # Consultar si sigue en ciclo
        respuesta = medirciclo("ESTAdo:ENCiclo?",ser)
        
        if respuesta == "0":
            print("Ciclo completado.")
            break
        
        # Obtener peso
        peso_str = medirciclo("ESTAdo:MEDicion?",ser)
        
        try:
            peso = float(peso_str)
            integral = valor_integral
            
            # Guardar datos
            datos_ciclos.append([peso, integral])
            print(f"Muestra {len(datos_ciclos)}: Peso={peso}g, Integral={integral:.2f}")
            
        except ValueError:
            print(f"Error al leer peso: '{peso_str}'")
        
        time.sleep(1)
    
    print(f"\nTotal de muestras recolectadas: {len(datos_ciclos)}")

def comando_llenar(ser):
    print("Ejecutando: LLENAR")
    enviar_comando("STATus:OPERation:LLEnar",ser)

def comando_vaciar(ser):
    print("Ejecutando: VACIAR")
    enviar_comando("STATus:OPERation:VACiar",ser)

def comando_parar(ser):
    print("Ejecutando: PARAR")
    enviar_comando("STATus:OPERation:PARar",ser)

def comando_tarar(ser):
    print("Ejecutando: TARAR")
    enviar_comando("STATus:OPERation:TARCAL",ser)

#Mirar como diferenciamos tarar de calibrar
#def comando_calibrar():
#    print("Ejecutando: CALIBRAR")
#    enviar_comando("STATus:OPERation:CALibrar")

def leer_peso(ser):
    respuesta = enviar_comando("ESTAdo:MEDicion?",ser, etiqueta="Peso")
    return respuesta if respuesta else "N/A"

def comando_ciclo(ser,num_ciclos):
    enviar_comando(f"STATus:OPERation:CIClos {num_ciclos}",ser)
    
    # Iniciar monitoreo automático
    monitorear_ciclo(ser)
    
    # Preguntar si desea guardar
    guardar = input("\n¿Deseas guardar los datos en CSV? (s/n): ")
    if guardar.lower() == 's':
        guardar_csv()
