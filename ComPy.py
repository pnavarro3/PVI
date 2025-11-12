import threading
import time
import serial
import redpitaya_scpi as scpi
import matplotlib.pyplot as plot
import numpy as np

# === CONFIGURACIÓN RED PITAYA ===
IP = "rp-f082af.local"
rp = scpi.scpi(IP)
running_redpitaya = True

# === CONFIGURACIÓN ARDUINO SERIAL ===
puerto = 'COM4'
baudios = 9600
try:
    ser = serial.Serial(puerto, baudios, timeout=1)
    time.sleep(2)
except serial.SerialException as e:
    print(f"Error al abrir el puerto serial: {e}")
    exit()
running_arduino = True

# === FUNCIONES RED PITAYA ===
def tecla(event):
    global running_redpitaya
    if event.key == 'escape':
        running_redpitaya = False

def medir_redpitaya():
    while running_redpitaya:
        try:
            rp.tx_txt('ACQ:RST')
            rp.tx_txt('ACQ:DEC 16')
            rp.tx_txt('ACQ:SOUR1:GAIN HV')
            rp.tx_txt('ACQ:START')
            rp.tx_txt('ACQ:TRIG NOW')

            while True:
                rp.tx_txt('ACQ:TRIG:STAT?')
                if rp.rx_txt() == 'TD':
                    break

            while True:
                rp.tx_txt('ACQ:TRIG:FILL?')
                if rp.rx_txt() == '1':
                    break

            rp.tx_txt('ACQ:SOUR1:DATA:TRIG? 100000,PRE_POST_TRIG')
            buff_string = rp.rx_txt().strip('{}\n\r').replace("  ", "").split(',')
            buff = np.array(list(map(float, buff_string)))

            buff_rango = buff[2000:9000]
            media_val = np.mean(buff_rango)
            buff -= media_val
            integral_abs_rango = np.sum(np.abs(buff_rango - media_val))

            print("\n[Red Pitaya]")
            print("Offset:", round(media_val, 2))
            print("Integral:", round(integral_abs_rango, 2))

            plot.clf()
            plot.plot(buff)
            plot.ylabel('Voltage (offset removed)')
            plot.xlabel("Puntos de muestra")
            plot.title("Señal centrada")
            plot.pause(0.001)

            time.sleep(1)
        except Exception as e:
            print(f"[Red Pitaya] Error: {e}")
            break
    rp.close()
    print("Red Pitaya finalizado.")

# === FUNCIONES ARDUINO ===
def enviar_comando(comando, etiqueta=None):
    try:
        ser.write((comando + "\n").encode('utf-8'))
        time.sleep(2)
        respuesta = ser.readline().decode('utf-8').strip()
        if respuesta:
            if etiqueta:
                print(f"{etiqueta}: {respuesta}")
            else:
                print(f"Respuesta: {respuesta}")
        else:
            print("No se recibió respuesta del dispositivo.")
    except Exception as e:
        print(f"[Arduino] Error al enviar comando: {e}")

def menu_arduino():
    global running_arduino, running_redpitaya
    while running_arduino:
        print("\n=== CONTROL SCPI ARDUINO ===")
        print("1. Identificar dispositivo")
        print("2. Llenar")
        print("3. Vaciar")
        print("4. Parar")
        print("5. Tara / Calibrar")
        print("6. Medir peso/volumen")
        print("7. Enviar consigna")
        print("8. Ejecutar ciclos")
        print("9. Salir")
        opcion = input("Selecciona una opción: ")

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
            enviar_comando("STATus:VOLumen?", etiqueta="Peso")
        elif opcion == "7":
            valor = input("Introduce valor de consigna: ")
            enviar_comando(f"STATus:OPERation:CONsigna {valor}")
        elif opcion == "8":
            ciclos = input("Número de ciclos a ejecutar: ")
            enviar_comando(f"STATus:OPERation:CIClos {ciclos}")
        elif opcion == "9":
            print("Cerrando conexión y finalizando programa...")
            running_arduino = False
            running_redpitaya = False
            ser.close()
            break
        else:
            print("Opción no válida. Intenta otra vez.")

# === INICIO DE HILOS ===
plot.ion()
fig = plot.figure()
fig.canvas.mpl_connect('key_press_event', tecla)

hilo_redpitaya = threading.Thread(target=medir_redpitaya)
hilo_arduino = threading.Thread(target=menu_arduino)

hilo_redpitaya.start()
hilo_arduino.start()

hilo_redpitaya.join()
hilo_arduino.join()
