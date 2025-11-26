import dash
from dash import dcc, html, Input, Output
import ComWeb as com
import serial
import time
import threading
import numpy as np
import redpitaya_scpi as scpi

#CONFIGURACIÓN PUERTO SERIAL
puerto = 'COM7'
baudios = 9600

#Quitar comentarios para probar con el circuito
try:
   ser = serial.Serial(puerto, baudios, timeout=1)
   time.sleep(1)
except serial.SerialException as e:
   print(f"Error al abrir el puerto serial: {e}")
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

#Funciones locales

def estilo_tanque(nivel_porcentaje):
    return {
        'width': '100%',
        'height': f'{nivel_porcentaje}%',
        'backgroundColor': '#3498db',
        'position': 'absolute',
        'bottom': '0',
        'transition': 'height 0.3s'
    }

# Lanzar el hilo en background
thread_rp = threading.Thread(target=com.medir_redpitaya, daemon=True)
thread_rp.start()

# Crear la aplicación
app = dash.Dash(__name__)

# Layout
app.layout = html.Div([
    html.H1("Sistema de control de volumen"),

    dcc.Interval(id='interval-peso', interval=2000, disabled=True),  # 1 segundo, desactivado inicialmente
    dcc.Store(id='store-llenando', data=False),  # Almacena el estado
    
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
        # Contenedor principal con dos columnas
        html.Div([
            # Columna izquierda - Controles
            html.Div([
                #Botones de control de bombas
                html.Div([
            html.H3('Control manual de bombas', style={'display': 'block'}),
            html.Div([
                # Columna izquierda con dos botones
                html.Div([
                    html.Button('Llenar', id='button-llenar', n_clicks=0, 
                            style={'display': 'block', 'margin': '20px auto', 'padding': '20px 50px','marginLeft': '30px'}),
                    html.Button('Vaciar', id='button-vaciar', n_clicks=0,
                            style={'display': 'block', 'margin': '20px auto', 'padding': '20px 50px','marginLeft': '30px'}),
                ], style={'display': 'inline-block', 'verticalAlign': 'middle'}),
                
                # Botón STOP a la derecha
                html.Div([
                    html.Button('STOP', id='button-stop', n_clicks=0,
                            style={'margin': '10px auto', 'padding': '20px 50px'}),
                ], style={'display': 'inline-block', 'verticalAlign': 'middle', 'marginLeft': '200px'}),
            ])
        ], className='control-box', style={'display': 'block', 'width': '695px', 'textAlign': 'center', 'marginLeft': '50px', 'marginTop': '75px'}),

        #Botones para tarar y calibrar

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
            
            # Columna derecha - Visualización
            html.Div([
                html.H3('Monitorización del Sistema'),
                html.Div([
                    # Simulador de llenado (izquierda)
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
                    
                    # Valores de lectura (derecha)
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

# Callbacks
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

# Callback que controla inicio y parada
@app.callback(
    Output('interval-peso', 'disabled'),
    [Input('button-llenar', 'n_clicks'),
     Input('button-vaciar', 'n_clicks'),
     Input('button-stop', 'n_clicks')],
    prevent_initial_call=True
)
def controlar_interval(n_llenar, n_vaciar, n_stop):
    ctx = dash.callback_context
    if not ctx.triggered:
        return True
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'button-llenar':
        com.comando_llenar(ser)  # Activa tu función de llenado
        return False  # Activa interval
    elif button_id == 'button-vaciar':
        com.comando_vaciar(ser)
        return False #Activa interval
    elif button_id == 'button-stop':
        com.comando_parar(ser)  # Activa tu función de parada
        return True   # Desactiva interval
    return True

@app.callback(
    Output('peso-bascula', 'children'),
    Output('valor-condensador','children'),
    Output('tank-fill','style'),
    Input('interval-peso', 'n_intervals'),
    prevent_initial_call=True
)
def actualizar_peso(n_intervals):
    peso = com.leer_peso(ser)  # Tu función de la librería
    valor_rc = com.medir_redpitaya(running) 
    if peso > 0 and peso <= 200:
        estilo = estilo_tanque(25)
    elif peso > 200 and peso <= 400:
        estilo = estilo_tanque(50)
    elif peso > 400 and peso < 600:
        estilo = estilo_tanque(75)
    elif peso <= 0:
        estilo = estilo_tanque(0)
    elif peso >= 600:
        estilo = estilo_tanque(100)
    return f"{peso} kg",f"{valor_rc}",estilo

#Añadir el callback para tarar, el cual llamaria a la funcion tarar de la libreria
#y la salida debe ser que sea 0 todas las medidas "peso-bascula","medida-rc" y "PesoCircuitoRC"

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
