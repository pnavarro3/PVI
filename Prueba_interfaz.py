import serial
import time

# Configuración del puerto
puerto = 'COM4'
baudios = 9600

try:
    ser = serial.Serial(puerto, baudios, timeout=1)
    time.sleep(2)  # Tiempo para que Arduino se resetee al abrir el puerto
except serial.SerialException as e:
    print(f"Error al abrir el puerto serial: {e}")
    exit()

def enviar_comando(comando):
    ser.write((comando + "\n").encode('utf-8'))
    time.sleep(3)      #darle una vuelta para ver como optimizar
    respuesta = ser.readline().decode('utf-8').strip()
    if respuesta:
        print(f"→ Respuesta: {respuesta}")      #se puede replantear de tal manera que primero se reciba un ACK y que luego lea lo que sea necesario

def menu():
    print("\n=== CONTROL SCPI ARDUINO ===")
    print("1. Identificar dispositivo")
    print("2. Llenar")
    print("3. Vaciar")
    print("4. Parar")
    print("5. Tare / Calibrar")
    print("6. Medir peso/volumen")
    print("7. Enviar consigna")
    print("8. Salir")
    return input("Selecciona una opción: ")

while True:
    opcion = menu()

    if opcion == "1":
        enviar_comando("SYSTem:VERSion?")
    
    elif opcion == "2":
        enviar_comando("STATus:OPERation:LLEnar")
    
    elif opcion == "3":
        enviar_comando("STATus:OPERation:VACiar")
    
    elif opcion == "4":
        enviar_comando("STATus:OPERation:PARar")
    
    elif opcion == "5":
        enviar_comando("STATus:OPERation:TARCAL")
    
    elif opcion == "6":
        enviar_comando("STATus:VOLumen?")
    
    elif opcion == "7":
        valor = input("Introduce valor de consigna: ")
        enviar_comando(f"STATus:OPERation:CONsigna {valor}")
    
    elif opcion == "8":
        print("Cerrando conexión y terminando programa...")
        ser.close()
        break
    
    else:
        print("❌ Opción no válida. Intenta otra vez.")
