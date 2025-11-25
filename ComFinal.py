import serial
import time
import threading
import numpy as np
import redpitaya_scpi as scpi

# CONFIGURACIÓN ARDUINO
puerto = 'COM7'
baudios = 9600

try:
    ser = serial.Serial(puerto, baudios, timeout=1)
    time.sleep(1)
except serial.SerialException as e:
    print(f"Error al abrir el puerto serial: {e}")
    exit()

def enviar_comando(comando, etiqueta=None):
    ser.write((comando + "\n").encode('utf-8'))
    time.sleep(0.3)

    respuesta = ser.readline().decode('utf-8').strip()
    if respuesta:
        if etiqueta:
            print(f"{etiqueta}: {respuesta}")
    else:
        print("No se recibió respuesta del dispositivo.")

# MENÚ PRINCIPAL
def menu():
    print("\n=== CONTROL SCPI ARDUINO ===")
    print("1. Identificar dispositivo")
    print("2. Llenar")
    print("3. Vaciar")
    print("4. Parar")
    print("5. Tara / Calibrar")
    print("6. Medir peso/volumen (incluye RedPitaya)")
    print("7. Enviar consigna")
    print("8. Ciclos de llenado/vaciado")
    print("9. Salir")
    return input("Selecciona una opción: ")

# MEDICIÓN RED PITAYA EN SEGUNDO PLANO
IP = "rp-f082af.local"
rp = scpi.scpi(IP)

# Configuración inicial Red Pitaya
rp.tx_txt('GEN:RST')
rp.tx_txt('SOUR1:FUNC SINE')
rp.tx_txt('SOUR1:FREQ:FIX 2000')
rp.tx_txt('SOUR1:VOLT 1')
rp.tx_txt('OUTPUT1:STATE ON')
rp.tx_txt('SOUR1:TRIG:INT')
rp.tx_txt('ACQ:SOUR1:GAIN HV')

running = True

# Variable donde se guardará el valor de la integral
valor_integral = 0.0


def medir_redpitaya():
    """Hilo secundario: mide cada segundo sin imprimir y sin bloquear."""
    global valor_integral

    while running:
        try:
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

        except Exception:
            pass

        time.sleep(1)


# Lanzar el hilo en background
thread_rp = threading.Thread(target=medir_redpitaya, daemon=True)
thread_rp.start()

# BUCLE PRINCIPAL (ARDUINO)
while True:
    opcion = menu()

    if opcion == "1":
        enviar_comando("SYSTem:VERSion?", etiqueta="Dispositivo")
    
    elif opcion == "2":
        enviar_comando("STATus:OPERation:LLEnar")
    
    elif opcion == "3":
        enviar_comando("STATus:OPERation:VACiar")
    
    elif opcion == "4":
        enviar_comando("STATus:OPERation:PARar")
    
    elif opcion == "5":
        enviar_comando("STATus:OPERation:TARCAL")
    
    elif opcion == "6":
        enviar_comando("ESTAdo:MEDicion?", etiqueta="Peso")

        # Mostrar también la integral de la Red Pitaya
        print(f"RedPitaya - Integral del rango 2000–9000: {valor_integral}")

    elif opcion == "7":
        valor = input("Introduce valor de consigna: ")
        enviar_comando(f"STATus:OPERation:CONsigna {valor}")
    
    elif opcion == "8":
        num_ciclos = input("Introduce número de ciclos: ")
        enviar_comando(f"STATus:OPERation:CIClos {num_ciclos}")
    
    elif opcion == "9":
        print("Cerrando conexión y terminando programa...")
        running = False
        rp.close()
        ser.close()
        break
    
    else:
        print("Opción no válida. Intenta otra vez.")
