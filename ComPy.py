import serial
import time


puerto = 'COM4'
baudios = 9600

try:
  ser = serial.Serial(puerto, baudios, timeout=1) # timeout para esperar datos si es necesario
  time.sleep(2) # Espera a que la conexión se establezca
except serial.SerialException as e:
  print(f"Error al abrir el puerto serial: {e}")
  exit()

# Envía el comando SCPI al Arduino
comando = "STATus:OPERation:TARCAL\n" # El \n es importante para el salto de línea en el Arduino
ser.write(comando.encode('utf-8')) # Envía el comando como bytes

time.sleep(3)

# Opcional: Lee la respuesta del Arduino
respuesta = ser.readline().decode('utf-8').strip()
print(f"Respuesta de Arduino: {respuesta}")

time.sleep(3)

# Envía el comando SCPI al Arduino
comando = "STATus:OPERation:CONsigna -100\n" # El \n es importante para el salto de línea en el Arduino
ser.write(comando.encode('utf-8')) # Envía el comando como bytes


time.sleep(10)

comando = "STATus:VOLumen?\n" # El \n es importante para el salto de línea en el Arduino
ser.write(comando.encode('utf-8')) # Envía el comando como bytes

time.sleep(3)

respuesta = ser.readline().decode('utf-8').strip()
print(f"Respuesta de Arduino: {respuesta}")

ser.close() # Cierra la conexión