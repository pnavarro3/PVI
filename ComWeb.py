import dash
from dash import dcc, html, Input, Output, State
import serial
import time
import threading
import numpy as np
import redpitaya_scpi as scpi

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

#Hilo de medición Red Pitaya (Comprobar que no bloquea)
def medir_redpitaya(running):
    global valor_integral, rp

    while running:
        try:
            if rp is None:
                time.sleep(1)
                continue
            
            # Configurar adquisición
            rp.tx_txt('ACQ:RST')
            rp.tx_txt('ACQ:DEC 16')
            rp.tx_txt('ACQ:START')
            rp.tx_txt('ACQ:TRIG NOW')

            # Esperar trigger
            while True:
                rp.tx_txt('ACQ:TRIG:STAT?')
                if rp.rx_txt() == 'TD':
                    break

            # Esperar llenado de memoria
            while True:
                rp.tx_txt('ACQ:TRIG:FILL?')
                if rp.rx_txt() == '1':
                    break

            # Dar tiempo a que el buffer realmente tenga las 100k muestras
            time.sleep(0.3)

            # Leer buffer de la Red Pitaya
            rp.tx_txt('ACQ:SOUR1:DATA:TRIG? 100000,PRE_POST_TRIG')
            buff_string = rp.rx_txt()
            buff_string = buff_string.strip('{}\n\r').replace("  ", "").split(',')
            buff = np.array(list(map(float, buff_string)))

            # Tomar rango equivalente al código original
            rango = buff[2000:9000]

            # Media del rango
            media = np.mean(rango)

            # Señal centrada solo en rango
            rango_centrado = rango - media

            # Integral absoluta
            valor_integral = np.sum(np.abs(rango_centrado))

        except Exception as e:
            pass

        time.sleep(1)
