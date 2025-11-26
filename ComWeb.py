import dash
from dash import dcc, html, Input, Output, State
import serial
import time
import threading
import numpy as np
import redpitaya_scpi as scpi

#CONFIGURACIÓN PUERTO SERIAL
puerto = 'COM7'
baudios = 9600

                #Quitar comentarios para probar con el circuito
#try:
#    ser = serial.Serial(puerto, baudios, timeout=1)
#    time.sleep(1)
#except serial.SerialException as e:
#    print(f"Error al abrir el puerto serial: {e}")
ser = None

#CONFIGURACIÓN RED PITAYA
IP = "rp-f082af.local"
rp = None
try:
    rp = scpi.scpi(IP)
    # Configuración inicial Red Pitaya
    rp.tx_txt('GEN:RST')
    rp.tx_txt('SOUR1:FUNC SINE')
    rp.tx_txt('SOUR1:FREQ:FIX 2000')
    rp.tx_txt('SOUR1:VOLT 1')
    rp.tx_txt('OUTPUT1:STATE ON')
    rp.tx_txt('SOUR1:TRIG:INT')
    rp.tx_txt('ACQ:SOUR1:GAIN HV')
except Exception as e:
    print(f"Error al conectar Red Pitaya: {e}")
    rp = None

running = True
valor_integral = 0.0

#FUNCIONES DE COMANDOS
def enviar_comando(comando, etiqueta=None):
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

def comando_llenar():
    print("Ejecutando: LLENAR")
    enviar_comando("STATus:OPERation:LLEnar")

def comando_vaciar():
    print("Ejecutando: VACIAR")
    enviar_comando("STATus:OPERation:VACiar")

def comando_parar():
    print("Ejecutando: PARAR")
    enviar_comando("STATus:OPERation:PARar")

def comando_tarar():
    print("Ejecutando: TARAR")
    enviar_comando("STATus:OPERation:TARCAL")

#Mirar como diferenciamos tarar de calibrar
#def comando_calibrar():
#    print("Ejecutando: CALIBRAR")
#    enviar_comando("STATus:OPERation:CALibrar")

def leer_peso():
    respuesta = enviar_comando("ESTAdo:MEDicion?", etiqueta="Peso")
    return respuesta if respuesta else "N/A"

#Hilo de medición Red Pitaya (Comprobar que no bloquea)
def medir_redpitaya():
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

# Lanzar el hilo en background
thread_rp = threading.Thread(target=medir_redpitaya, daemon=True)
thread_rp.start()

# Crear la aplicación
app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Layout
app.layout = html.Div([
    html.H1("Sistema de control de volumen"),
    
    html.Div([
        dcc.Tabs(id='tabs-example-1', value='tab-1', children=[
            dcc.Tab(label='Setup', value='tab-1'),
            dcc.Tab(label='Calibracion RC', value='tab-2'),
            dcc.Tab(label='Control Automático', value='tab-3'),
        ]),
        html.Div(id='tabs-example-content-1')
    ])
])

# Funciones para cada tab
def render_tab1():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.H3('Control manual de bombas', style={'display': 'block'}),
                    html.Div([
                        html.Div([
                            html.Button('Llenar', id='button-llenar', n_clicks=0, 
                                    style={'display': 'block', 'margin': '20px auto', 'padding': '20px 50px','marginLeft': '30px'}),
                            html.Button('Vaciar', id='button-vaciar', n_clicks=0,
                                    style={'display': 'block', 'margin': '20px auto', 'padding': '20px 50px','marginLeft': '30px'}),
                        ], style={'display': 'inline-block', 'verticalAlign': 'middle'}),
                        
                        html.Div([
                            html.Button('STOP', id='button-stop', n_clicks=0,
                                    style={'margin': '10px auto', 'padding': '20px 50px'}),
                        ], style={'display': 'inline-block', 'verticalAlign': 'middle', 'marginLeft': '200px'}),
                    ])
                ], className='control-box', style={'display': 'block', 'width': '695px', 'textAlign': 'center', 'marginLeft': '50px', 'marginTop': '75px'}),

                html.Div([
                    html.Div([
                        html.H3('Tarado y Calibrado de la Bascula'),
                        html.Div([
                            html.Button('Tarar', id='button-tarar', n_clicks=0, 
                                    style={'display': 'block', 'margin': '30px auto', 'padding': '10px 20px'}),
                            html.Button('Calibrar', id='button-calibrar', n_clicks=0,
                                    style={'display': 'block', 'margin': '20px auto', 'padding': '10px 20px'}),
                        ])
                    ], className='control-box', style={'display': 'inline-block', 'width': '300px','height': '175px', 'textAlign': 'center', 'verticalAlign': 'top'}),
                    
                    html.Div([
                        html.H3('Frecuencia RC'),
                        html.H4('Introduce el valor de la frecuencia de trabajo'),
                        html.Div([
                            dcc.Input(id='InputFrecuencia', type="number", placeholder="Frecuencia...",
                                      style={'display': 'block', 'margin': '20px auto', 'padding': '5px 30px'}),
                        ])
                    ], className='control-box', style={'display': 'inline-block', 'width': '300px','height': '175px', 'textAlign': 'center', 'verticalAlign': 'top', 'marginLeft': '50px'})
                ], style={'display': 'block', 'marginLeft': '50px', 'marginTop': '40px'})
            ], style={'display': 'inline-block', 'verticalAlign': 'top'}),
            
            html.Div([
                html.H3('Monitorización del Sistema'),
                html.Div([
                    html.Div([
                        html.H4('Nivel del Depósito',className= 'h4'),
                        html.Div([
                            html.Div(id='tank-fill', style={
                                'width': '100%',
                                'height': '0%',
                                'backgroundColor': '#3498db',
                                'position': 'absolute',
                                'bottom': '0',
                                'transition': 'height 0.3s'
                            })
                        ], style={
                            'width': '150px',
                            'height': '250px',
                            'border': '3px solid #2c3e50',
                            'position': 'relative',
                            'margin': '20px auto',
                            'backgroundColor': '#ecf0f1'
                        })
                    ], style={'display': 'inline-block', 'verticalAlign': 'top', 'width': '45%', 'textAlign': 'center'}),
                    
                    html.Div([
                        html.H4('Lecturas'),
                        html.Div([
                            html.Div([
                                html.Label('Peso Báscula', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                                html.Div('N/A', id='peso-bascula', style={'padding': '10px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 'marginBottom': '15px'})
                            ]),
                            html.Div([
                                html.Label('Medida circuito RC', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                                html.Div('N/A', id='valor-condensador', style={'padding': '10px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 'marginBottom': '15px'})
                            ]),
                            html.Div([
                                html.Label('Peso circuito RC', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                                html.Div('N/A', id='peso-rc', style={'padding': '10px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px'})
                            ])
                        ], style={'textAlign': 'center', 'padding': '20px'})
                    ], style={'display': 'inline-block', 'verticalAlign': 'top', 'width': '50%','textAlign': 'center'})
                ])
            ], className='control-box', style={'display': 'inline-block', 'width': '900px','height': '450px', 'verticalAlign': 'middle', 'marginLeft': '50px', 'marginTop': '90px'})
        ], style={'display': 'block'})
    ])

def render_tab2():
    return html.Div([
        html.H3('Calibración RC')
    ])

def render_tab3():
    return html.Div([
        html.H3('Control Automático')
    ])

#CALLBACKS
@app.callback(
    Output('tabs-example-content-1', 'children'),
    Input('tabs-example-1', 'value')
)
def render_content(tab):
    if tab == 'tab-1':
        return render_tab1()
    elif tab == 'tab-2':
        return render_tab2()
    elif tab == 'tab-3':
        return render_tab3()

# Callback para botón LLENAR
@app.callback(
    Output('button-llenar', 'n_clicks'),
    Input('button-llenar', 'n_clicks'),
    prevent_initial_call=True
)
def al_hacer_clic_llenar(n_clicks):
    if n_clicks > 0:
        comando_llenar()
    return n_clicks

# Callback para botón VACIAR
@app.callback(
    Output('button-vaciar', 'n_clicks'),
    Input('button-vaciar', 'n_clicks'),
    prevent_initial_call=True
)
def al_hacer_clic_vaciar(n_clicks):
    if n_clicks > 0:
        comando_vaciar()
    return n_clicks

# Callback para botón STOP
@app.callback(
    Output('button-stop', 'n_clicks'),
    Input('button-stop', 'n_clicks'),
    prevent_initial_call=True
)
def al_hacer_clic_stop(n_clicks):
    if n_clicks > 0:
        comando_parar()
    return n_clicks

# Callback para botón TARAR
@app.callback(
    Output('button-tarar', 'n_clicks'),
    Input('button-tarar', 'n_clicks'),
    prevent_initial_call=True
)
def al_hacer_clic_tarar(n_clicks):
    if n_clicks > 0:
        comando_tarar()
    return n_clicks

if __name__ == '__main__':
    try:
        app.run(debug=True)
    except KeyboardInterrupt:
        print("Cerrando aplicación...")
        running = False
        if ser:
            ser.close()
        if rp:
            rp.close()