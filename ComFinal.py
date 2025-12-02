import serial
import time
import threading
import numpy as np
import redpitaya_scpi as scpi
import csv
from datetime import datetime
import matplotlib.pyplot as plt

# CONFIGURACIÓN ARDUINO
puerto = 'COM4'
baudios = 9600

try:
    ser = serial.Serial(puerto, baudios, timeout=2)
    time.sleep(1)
except serial.SerialException as e:
    print(f"Error al abrir el puerto serial: {e}")
    exit()

def enviar_comando(comando, etiqueta=None):
    ser.reset_input_buffer()  # Limpiar buffer antes de enviar
    ser.write((comando + "\n").encode('utf-8'))
    time.sleep(0.3)

    respuesta = ser.readline().decode('utf-8').strip()
    if respuesta:
        if etiqueta:
            print(f"{etiqueta}: {respuesta}")
    else:
        print("No se recibió respuesta del dispositivo.")

def medirciclo(comando, etiqueta=None):
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
    print("9. Visualizar datos del CSV")
    print("10. Salir")
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

# Lista para almacenar datos durante ciclos
datos_ciclos = []


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

# FUNCIONES PARA GESTIÓN DE CICLOS Y CSV
def monitorear_ciclo():
    """Monitorea ciclos cada 1 segundo y guarda datos."""
    global datos_ciclos
    datos_ciclos = []
    
    print("\nIniciando monitoreo de ciclos...")
    
    while True:
        # Consultar si sigue en ciclo
        respuesta = medirciclo("ESTAdo:ENCiclo?")
        
        if respuesta == "0":
            print("Ciclo completado.")
            break
        
        # Obtener peso
        peso_str = medirciclo("ESTAdo:MEDicion?")
        
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

def visualizar_csv():
    """Visualiza los datos del último CSV guardado en una gráfica."""
    nombre_archivo = "datos_ciclos.csv"
    
    try:
        with open(nombre_archivo, 'r') as f:
            reader = csv.reader(f)
            datos = list(reader)
            
            if len(datos) <= 1:
                print("El archivo CSV está vacío o solo contiene encabezados.")
                return
            
            # Extraer datos
            pesos = []
            integrales = []
            
            for fila in datos[1:]:  # Saltar encabezado
                if len(fila) >= 2:
                    try:
                        pesos.append(float(fila[0]))
                        integrales.append(float(fila[1]))
                    except ValueError:
                        continue
            
            if not pesos or not integrales:
                print("No hay datos válidos para graficar.")
                return
            
            # Crear gráfica de dispersión
            plt.figure(figsize=(10, 8))
            plt.scatter(pesos, integrales, c='blue', alpha=0.6, edgecolors='black', s=50)
            
            # Línea de tendencia (regresión lineal)
            z = np.polyfit(pesos, integrales, 1)
            p = np.poly1d(z)
            plt.plot(pesos, p(pesos), "r--", linewidth=2, label=f'Tendencia: y={z[0]:.4f}x+{z[1]:.4f}')
            
            plt.xlabel('Peso (g)', fontsize=14, fontweight='bold')
            plt.ylabel('Integral Red Pitaya', fontsize=14, fontweight='bold')
            plt.title('Relación entre Peso e Integral Red Pitaya', fontsize=16, fontweight='bold')
            plt.grid(True, alpha=0.3)
            plt.legend(fontsize=12)
            
            plt.tight_layout()
            plt.show()
            
            # Calcular coeficiente de correlación
            correlacion = np.corrcoef(pesos, integrales)[0, 1]
            
            # Mostrar estadísticas en consola
            print(f"\n=== ANÁLISIS DE RELACIÓN ({nombre_archivo}) ===")
            print(f"Total de muestras: {len(pesos)}")
            print(f"\nCoeficiente de correlación (R): {correlacion:.4f}")
            print(f"Ecuación de la recta: y = {z[0]:.4f}x + {z[1]:.4f}")
            
            if abs(correlacion) > 0.9:
                print("→ Relación FUERTEMENTE LINEAL")
            elif abs(correlacion) > 0.7:
                print("→ Relación MODERADAMENTE LINEAL")
            elif abs(correlacion) > 0.5:
                print("→ Relación DÉBILMENTE LINEAL")
            else:
                print("→ Relación NO LINEAL")
            
            print(f"\nPeso - Min: {np.min(pesos):.2f}g, Max: {np.max(pesos):.2f}g, Promedio: {np.mean(pesos):.2f}g")
            print(f"Integral - Min: {np.min(integrales):.2f}, Max: {np.max(integrales):.2f}, Promedio: {np.mean(integrales):.2f}")
                
    except FileNotFoundError:
        print(f"No se encontró el archivo '{nombre_archivo}'.")
        print("Ejecuta primero un ciclo y guarda los datos.")
    except Exception as e:
        print(f"Error al leer el archivo: {e}")

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
        
        # Iniciar monitoreo automático
        monitorear_ciclo()
        
        # Preguntar si desea guardar
        guardar = input("\n¿Deseas guardar los datos en CSV? (s/n): ")
        if guardar.lower() == 's':
            guardar_csv()
    
    elif opcion == "9":
        visualizar_csv()
    
    elif opcion == "10":
        print("Cerrando conexión y terminando programa...")
        running = False
        rp.close()
        ser.close()
        break
    
    else:
        print("Opción no válida. Intenta otra vez.")
