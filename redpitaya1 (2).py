import time
import redpitaya_scpi as scpi
import matplotlib.pyplot as plot
import numpy as np

# Conectar con Red Pitaya 
IP = "rp-f082af.local"
rp = scpi.scpi(IP)

# Variable global para controlar el bucle
running = True

def tecla(esc):
    global running
    if esc.key == 'escape':  # Si se presiona ESC
        running = False

def medir():
    # Configurar adquisición
    rp.tx_txt('ACQ:RST')
    rp.tx_txt('ACQ:DEC 16')
    rp.tx_txt('ACQ:SOUR1:GAIN HV')  # Adquirir la señal con HV
    rp.tx_txt('ACQ:START')
    rp.tx_txt('ACQ:TRIG NOW')

    # Esperar trigger
    while True:
        rp.tx_txt('ACQ:TRIG:STAT?')
        if rp.rx_txt() == 'TD':
            break

    while True:
        rp.tx_txt('ACQ:TRIG:FILL?')
        if rp.rx_txt() == '1':
            break

    # Leer datos
    rp.tx_txt('ACQ:SOUR1:DATA:TRIG? 100000,PRE_POST_TRIG')
    buff_string = rp.rx_txt()
    buff_string = buff_string.strip('{}\n\r').replace("  ", "").split(',')
    buff = np.array(list(map(float, buff_string)))

    # Tomar solo el rango de muestras entre la 2000 y la 9000
    buff_rango = buff[2000:9000]

    # Calcular media del rango
    media_val = np.mean(buff_rango)
    
    # Restar la media a toda la señal
    buff = buff - media_val
    
    # Calcular integral de valores absolutos solo en el rango seleccionado
    integral_abs_rango = np.sum(np.abs(buff_rango - media_val))
    
    # Imprimir resultados
    print("Offset (media del rango 2000-9000):", media_val)
    print("Integral (valores absolutos del rango 2000-9000):", integral_abs_rango)
    
    # Graficar señal centrada
    plot.clf()  # Limpiar la figura anterior
    plot.plot(buff)
    plot.ylabel('Voltage (offset removed)')
    plot.xlabel("Puntos de muestra")
    plot.title("Señal centrada")
    plot.pause(0.001)  # Mostrar sin bloquear ejecución

# Configuración inicial del generador (solo una vez)
wave_form = 'sine'
freq = 2000
ampl = 1

rp.tx_txt('GEN:RST')
rp.tx_txt('SOUR1:FUNC ' + str(wave_form).upper())
rp.tx_txt('SOUR1:FREQ:FIX ' + str(freq))
rp.tx_txt('SOUR1:VOLT ' + str(ampl))
rp.tx_txt('OUTPUT1:STATE ON')
rp.tx_txt('SOUR1:TRIG:INT')
rp.tx_txt('ACQ:SOUR1:GAIN HV')

# Mostrar la figura de matplotlib y conectar evento de teclado
plot.ion()
fig = plot.figure()
fig.canvas.mpl_connect('key_press_event', tecla)

# Bucle principal: medir cada segundo hasta presionar ESC
while running:
    medir()
    time.sleep(1)

# Cerrar conexión al salir
rp.close()
print("Programa finalizado por el usuario")