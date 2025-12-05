import dash
from dash import dcc, html, Input, Output, State
from dash import dash_table
import plotly.graph_objs as go
import ComWeb as com
import serial
import time
import threading
import numpy as np
import redpitaya_scpi as scpi
from scipy.optimize import curve_fit

#CONFIGURACIÓN PUERTO SERIAL
puerto = 'COM4'
baudios = 9600

#Quitar comentarios para probar con el circuito
try:
   ser = serial.Serial(puerto, baudios, timeout=1)
   time.sleep(1)
except serial.SerialException as e:
   print(f"Error al abrir el puerto serial: {e}")


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

# Variables para calibración RC
datos_calibracion = []
ajuste_realizado = False
coeficientes_ajuste = None

#Funciones locales
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
thread_rp = threading.Thread(target=medir_redpitaya, daemon=True)
thread_rp.start()

# Crear la aplicación
app = dash.Dash(__name__)

# Layout
app.layout = html.Div([
    html.H1("Sistema de control de volumen"),

    dcc.Interval(id='interval-peso', interval=2000, disabled=True),  # 1 segundo, desactivado inicialmente
    dcc.Interval(id='interval-calibracion', interval=1000, disabled=True),  # Para calibración
    dcc.Interval(id='interval-control', interval=1000, disabled=True),  # Para control automático
    dcc.Store(id='store-llenando', data=False),  # Almacena el estado
    dcc.Store(id='store-calibrando', data={'activo': False, 'num_medidas': 0, 'medida_actual': 0}),
    dcc.Store(id='store-control', data={'activo': False, 'sensor': 'bascula', 'consigna': 400, 'histeresis': 20}),
    dcc.Store(id='store-historial-control', data={'tiempo': [], 'nivel': [], 'consigna': [], 'error': []}),
    
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
        html.H2('Calibración del Circuito RC', style={'textAlign': 'center', 'marginTop': '20px'}),
        
        # Fila superior - Controles
        html.Div([
            # Panel de control
            html.Div([
                html.H3('Configuración de Medidas'),
                html.Div([
                    html.Label('Número de medidas:', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                    dcc.Input(id='input-num-medidas', type='number', value=10, min=5, max=50,
                             style={'width': '100%', 'padding': '8px', 'marginBottom': '20px'}),
                ]),
                html.Div([
                    html.Button('RUN', id='button-run-calibracion', n_clicks=0,
                               style={'width': '45%', 'padding': '15px', 'backgroundColor': '#27ae60', 
                                      'color': 'white', 'border': 'none', 'borderRadius': '5px',
                                      'marginRight': '10px', 'fontSize': '16px', 'fontWeight': 'bold'}),
                    html.Button('STOP', id='button-stop-calibracion', n_clicks=0,
                               style={'width': '45%', 'padding': '15px', 'backgroundColor': '#e74c3c',
                                      'color': 'white', 'border': 'none', 'borderRadius': '5px',
                                      'fontSize': '16px', 'fontWeight': 'bold'}),
                ]),
                html.Div([
                    html.Label('Estado:', style={'fontWeight': 'bold', 'marginTop': '20px', 'display': 'block'}),
                    html.Div('Esperando...', id='estado-calibracion',
                            style={'padding': '10px', 'backgroundColor': '#ecf0f1', 
                                   'borderRadius': '5px', 'marginTop': '10px', 'textAlign': 'center'})
                ])
            ], className='control-box', style={'display': 'inline-block', 'width': '300px', 
                                               'verticalAlign': 'top', 'marginLeft': '50px', 'padding': '20px'}),
            
            # Panel de ajuste
            html.Div([
                html.H3('Función de Ajuste'),
                html.Div([
                    html.Label('Tipo de ajuste:', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                    dcc.Dropdown(
                        id='dropdown-tipo-ajuste',
                        options=[
                            {'label': 'Lineal (y = ax + b)', 'value': 'lineal'},
                            {'label': 'Polinomial grado 2 (y = ax² + bx + c)', 'value': 'poly2'},
                            {'label': 'Polinomial grado 3', 'value': 'poly3'}
                        ],
                        value='lineal',
                        style={'marginBottom': '20px'}
                    ),
                    html.Button('Realizar Ajuste', id='button-ajuste', n_clicks=0,
                               style={'width': '100%', 'padding': '15px', 'backgroundColor': '#3498db',
                                      'color': 'white', 'border': 'none', 'borderRadius': '5px',
                                      'fontSize': '16px', 'fontWeight': 'bold'}),
                    html.Div(id='resultado-ajuste',
                            style={'marginTop': '20px', 'padding': '15px', 'backgroundColor': '#ecf0f1',
                                   'borderRadius': '5px', 'minHeight': '80px'})
                ])
            ], className='control-box', style={'display': 'inline-block', 'width': '400px',
                                               'verticalAlign': 'top', 'marginLeft': '50px', 'padding': '20px'})
        ], style={'marginBottom': '30px'}),
        
        # Fila inferior - Visualización
        html.Div([
            # Gráfica
            html.Div([
                html.H3('Gráfica de Calibración', style={'textAlign': 'center'}),
                dcc.Graph(id='grafica-calibracion',
                         figure={
                             'data': [],
                             'layout': {
                                 'title': 'Peso Báscula vs Integral RC',
                                 'xaxis': {'title': 'Integral RC'},
                                 'yaxis': {'title': 'Peso (g)'},
                                 'hovermode': 'closest'
                             }
                         })
            ], style={'display': 'inline-block', 'width': '48%', 'verticalAlign': 'top', 'marginLeft': '50px'}),
            
            # Tabla
            html.Div([
                html.H3('Datos Recolectados', style={'textAlign': 'center'}),
                dash_table.DataTable(
                    id='tabla-calibracion',
                    columns=[
                        {'name': 'Medida', 'id': 'medida'},
                        {'name': 'Peso (g)', 'id': 'peso'},
                        {'name': 'Integral RC', 'id': 'integral'}
                    ],
                    data=[],
                    style_table={'overflowY': 'auto', 'maxHeight': '400px'},
                    style_cell={'textAlign': 'center', 'padding': '10px'},
                    style_header={'backgroundColor': '#3498db', 'color': 'white', 'fontWeight': 'bold'}
                )
            ], style={'display': 'inline-block', 'width': '45%', 'verticalAlign': 'top', 'marginLeft': '30px'})
        ])
    ])

def render_tab3():
    return html.Div([
        html.H2('Control Automático de Nivel', style={'textAlign': 'center', 'marginTop': '20px'}),
        
        # Fila superior - Configuración y Control
        html.Div([
            # Panel de configuración
            html.Div([
                html.H3('Configuración del Controlador'),
                
                # Selección de sensor
                html.Div([
                    html.Label('Sensor de medida:', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                    dcc.Dropdown(
                        id='dropdown-sensor',
                        options=[
                            {'label': 'Báscula', 'value': 'bascula'},
                            {'label': 'Circuito RC', 'value': 'rc', 'disabled': not ajuste_realizado}
                        ],
                        value='bascula',
                        style={'marginBottom': '20px'}
                    ),
                    html.Div(id='info-sensor', style={'fontSize': '12px', 'color': '#e67e22', 'marginBottom': '20px'})
                ]),
                
                # Consigna
                html.Div([
                    html.Label('Consigna de peso (g):', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                    dcc.Input(id='input-consigna', type='number', value=400, min=0, max=800,
                             style={'width': '100%', 'padding': '8px', 'marginBottom': '20px'}),
                ]),
                
                # Histéresis
                html.Div([
                    html.Label('Histéresis (g):', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                    dcc.Input(id='input-histeresis', type='number', value=20, min=5, max=100, step=5,
                             style={'width': '100%', 'padding': '8px', 'marginBottom': '20px'}),
                    html.P('La histéresis evita oscilaciones del controlador', 
                           style={'fontSize': '11px', 'color': '#7f8c8d', 'fontStyle': 'italic'})
                ]),
                
                # Botones de control
                html.Div([
                    html.Button('INICIAR CONTROL', id='button-iniciar-control', n_clicks=0,
                               style={'width': '100%', 'padding': '15px', 'backgroundColor': '#27ae60', 
                                      'color': 'white', 'border': 'none', 'borderRadius': '5px',
                                      'marginBottom': '10px', 'fontSize': '16px', 'fontWeight': 'bold'}),
                    html.Button('DETENER CONTROL', id='button-detener-control', n_clicks=0,
                               style={'width': '100%', 'padding': '15px', 'backgroundColor': '#e74c3c',
                                      'color': 'white', 'border': 'none', 'borderRadius': '5px',
                                      'fontSize': '16px', 'fontWeight': 'bold'}),
                ])
            ], className='control-box', style={'display': 'inline-block', 'width': '350px', 
                                               'verticalAlign': 'top', 'marginLeft': '50px', 'padding': '20px'}),
            
            # Panel de estado y valores
            html.Div([
                html.H3('Estado del Sistema', style={'textAlign': 'center'}),
                
                html.Div([
                    html.Div([
                        html.Label('Estado del Control:', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                        html.Div('DETENIDO', id='estado-control',
                                style={'padding': '15px', 'backgroundColor': '#ecf0f1', 
                                       'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '18px',
                                       'fontWeight': 'bold', 'color': '#e74c3c', 'marginBottom': '20px'})
                    ]),
                    
                    html.Div([
                        html.Div([
                            html.Label('Nivel Actual:', style={'fontWeight': 'bold', 'fontSize': '14px'}),
                            html.Div('0 g', id='nivel-actual',
                                    style={'fontSize': '24px', 'fontWeight': 'bold', 'color': '#3498db'})
                        ], style={'display': 'inline-block', 'width': '48%', 'textAlign': 'center',
                                 'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px',
                                 'marginRight': '2%'}),
                        
                        html.Div([
                            html.Label('Consigna:', style={'fontWeight': 'bold', 'fontSize': '14px'}),
                            html.Div('400 g', id='consigna-actual',
                                    style={'fontSize': '24px', 'fontWeight': 'bold', 'color': '#27ae60'})
                        ], style={'display': 'inline-block', 'width': '48%', 'textAlign': 'center',
                                 'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px'})
                    ], style={'marginBottom': '20px'}),
                    
                    html.Div([
                        html.Label('Error de Control:', style={'fontWeight': 'bold', 'display': 'block', 
                                                               'marginBottom': '5px', 'textAlign': 'center'}),
                        html.Div('0 g', id='error-control',
                                style={'padding': '20px', 'backgroundColor': '#ecf0f1', 
                                       'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '28px',
                                       'fontWeight': 'bold', 'color': '#e67e22'})
                    ]),
                    
                    html.Div([
                        html.Label('Acción de Control:', style={'fontWeight': 'bold', 'display': 'block', 
                                                                'marginBottom': '5px', 'marginTop': '20px', 
                                                                'textAlign': 'center'}),
                        html.Div('NINGUNA', id='accion-control',
                                style={'padding': '15px', 'backgroundColor': '#ecf0f1', 
                                       'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '18px',
                                       'fontWeight': 'bold'})
                    ])
                ])
            ], className='control-box', style={'display': 'inline-block', 'width': '400px',
                                               'verticalAlign': 'top', 'marginLeft': '30px', 'padding': '20px'})
        ], style={'marginBottom': '30px'}),
        
        # Fila inferior - Gráficas
        html.Div([
            html.H3('Evolución Temporal del Sistema', style={'textAlign': 'center', 'marginLeft': '50px'}),
            
            # Gráfica de evolución
            html.Div([
                dcc.Graph(id='grafica-control',
                         figure={
                             'data': [],
                             'layout': {
                                 'title': 'Control de Nivel en Tiempo Real',
                                 'xaxis': {'title': 'Tiempo (s)'},
                                 'yaxis': {'title': 'Peso (g)'},
                                 'hovermode': 'closest',
                                 'showlegend': True
                             }
                         })
            ], style={'width': '90%', 'marginLeft': '50px'}),
            
            # Botón para limpiar gráfica
            html.Div([
                html.Button('Limpiar Gráfica', id='button-limpiar-grafica', n_clicks=0,
                           style={'padding': '10px 30px', 'backgroundColor': '#95a5a6',
                                  'color': 'white', 'border': 'none', 'borderRadius': '5px',
                                  'fontSize': '14px'})
            ], style={'textAlign': 'center', 'marginTop': '10px'})
        ])
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

#Añadir el callback para tarar, el cual llamaria a la funcion tarar de la libreria
#y la salida debe ser que sea 0 todas las medidas "peso-bascula","medida-rc" y "PesoCircuitoRC"

# Callback para iniciar/detener calibración
@app.callback(
    [Output('interval-calibracion', 'disabled'),
     Output('store-calibrando', 'data')],
    [Input('button-run-calibracion', 'n_clicks'),
     Input('button-stop-calibracion', 'n_clicks')],
    [State('input-num-medidas', 'value'),
     State('store-calibrando', 'data')],
    prevent_initial_call=True
)
def controlar_calibracion(n_run, n_stop, num_medidas, store_data):
    global datos_calibracion
    
    ctx = dash.callback_context
    if not ctx.triggered:
        return True, store_data
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'button-run-calibracion':
        # Iniciar calibración
        datos_calibracion = []
        com.comando_vaciar(ser)  # Empezar desde vacío
        time.sleep(2)
        com.comando_parar(ser)
        
        return False, {'activo': True, 'num_medidas': num_medidas, 'medida_actual': 0}
    
    elif button_id == 'button-stop-calibracion':
        # Detener calibración
        com.comando_parar(ser)
        return True, {'activo': False, 'num_medidas': 0, 'medida_actual': 0}
    
    return True, store_data

# Callback para proceso de calibración
@app.callback(
    [Output('estado-calibracion', 'children'),
     Output('tabla-calibracion', 'data'),
     Output('grafica-calibracion', 'figure'),
     Output('store-calibrando', 'data', allow_duplicate=True),
     Output('interval-calibracion', 'disabled', allow_duplicate=True)],
    Input('interval-calibracion', 'n_intervals'),
    [State('store-calibrando', 'data')],
    prevent_initial_call=True
)
def proceso_calibracion(n_intervals, store_data):
    global datos_calibracion, valor_integral
    
    if not store_data['activo']:
        return "Esperando...", [], {'data': [], 'layout': {'title': 'Peso Báscula vs Integral RC'}}, store_data, True
    
    medida_actual = store_data['medida_actual']
    num_medidas = store_data['num_medidas']
    
    # Si terminamos todas las medidas
    if medida_actual >= num_medidas:
        com.comando_parar(ser)
        estado = f"Calibración completada: {len(datos_calibracion)} medidas recolectadas"
        
        # Preparar datos para tabla
        tabla_datos = [
            {'medida': i+1, 'peso': f"{d[0]:.2f}", 'integral': f"{d[1]:.2f}"}
            for i, d in enumerate(datos_calibracion)
        ]
        
        # Preparar gráfica
        if datos_calibracion:
            pesos = [d[0] for d in datos_calibracion]
            integrales = [d[1] for d in datos_calibracion]
            
            figura = {
                'data': [
                    go.Scatter(x=integrales, y=pesos, mode='markers', 
                              marker=dict(size=10, color='blue'),
                              name='Datos medidos')
                ],
                'layout': {
                    'title': 'Peso Báscula vs Integral RC',
                    'xaxis': {'title': 'Integral RC'},
                    'yaxis': {'title': 'Peso (g)'},
                    'hovermode': 'closest'
                }
            }
        else:
            figura = {'data': [], 'layout': {'title': 'Peso Báscula vs Integral RC'}}
        
        return estado, tabla_datos, figura, {'activo': False, 'num_medidas': num_medidas, 'medida_actual': medida_actual}, True
    
    # Proceso de llenado y medición
    if medida_actual == 0:
        # Primera medida: tanque vacío
        peso_str = com.leer_peso(ser)
        try:
            peso = float(peso_str)
            integral = valor_integral
            datos_calibracion.append([peso, integral])
            
            # Iniciar llenado para siguiente medida
            com.comando_llenar(ser)
            
        except ValueError:
            pass
    else:
        # Medidas intermedias
        tiempo_llenado = 3  # segundos entre medidas
        
        # Leer valores actuales
        peso_str = com.leer_peso(ser)
        try:
            peso = float(peso_str)
            integral = valor_integral
            datos_calibracion.append([peso, integral])
            
            # Si no es la última medida, seguir llenando
            if medida_actual < num_medidas - 1:
                com.comando_llenar(ser)
            else:
                com.comando_parar(ser)
                
        except ValueError:
            pass
    
    # Actualizar estado
    store_data['medida_actual'] = medida_actual + 1
    estado = f"Recolectando medida {medida_actual + 1} de {num_medidas}..."
    
    # Preparar datos para visualización parcial
    tabla_datos = [
        {'medida': i+1, 'peso': f"{d[0]:.2f}", 'integral': f"{d[1]:.2f}"}
        for i, d in enumerate(datos_calibracion)
    ]
    
    if datos_calibracion:
        pesos = [d[0] for d in datos_calibracion]
        integrales = [d[1] for d in datos_calibracion]
        
        figura = {
            'data': [
                go.Scatter(x=integrales, y=pesos, mode='markers',
                          marker=dict(size=10, color='blue'),
                          name='Datos medidos')
            ],
            'layout': {
                'title': 'Peso Báscula vs Integral RC',
                'xaxis': {'title': 'Integral RC'},
                'yaxis': {'title': 'Peso (g)'},
                'hovermode': 'closest'
            }
        }
    else:
        figura = {'data': [], 'layout': {'title': 'Peso Báscula vs Integral RC'}}
    
    return estado, tabla_datos, figura, store_data, False

# Callback para actualizar info de sensor disponible
@app.callback(
    [Output('info-sensor', 'children'),
     Output('dropdown-sensor', 'options')],
    Input('tabs-example-1', 'value')
)
def actualizar_info_sensor(tab):
    global ajuste_realizado
    
    opciones = [
        {'label': 'Báscula', 'value': 'bascula'},
        {'label': 'Circuito RC', 'value': 'rc', 'disabled': not ajuste_realizado}
    ]
    
    if tab == 'tab-3':
        if not ajuste_realizado:
            return "⚠️ Circuito RC no disponible. Complete la calibración en la pestaña anterior.", opciones
        else:
            return "✓ Ambos sensores disponibles", opciones
    return "", opciones

# Callback para iniciar/detener control automático
@app.callback(
    [Output('interval-control', 'disabled'),
     Output('store-control', 'data')],
    [Input('button-iniciar-control', 'n_clicks'),
     Input('button-detener-control', 'n_clicks')],
    [State('dropdown-sensor', 'value'),
     State('input-consigna', 'value'),
     State('input-histeresis', 'value')],
    prevent_initial_call=True
)
def controlar_sistema(n_iniciar, n_detener, sensor, consigna, histeresis):
    ctx = dash.callback_context
    if not ctx.triggered:
        return True, {'activo': False, 'sensor': sensor, 'consigna': consigna, 'histeresis': histeresis}
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'button-iniciar-control':
        # Iniciar control
        return False, {'activo': True, 'sensor': sensor, 'consigna': consigna, 'histeresis': histeresis, 'tiempo_inicio': time.time()}
    
    elif button_id == 'button-detener-control':
        # Detener control
        com.comando_parar(ser)
        return True, {'activo': False, 'sensor': sensor, 'consigna': consigna, 'histeresis': histeresis}
    
    return True, {'activo': False, 'sensor': sensor, 'consigna': consigna, 'histeresis': histeresis}

# Callback principal del control automático
@app.callback(
    [Output('estado-control', 'children'),
     Output('estado-control', 'style'),
     Output('nivel-actual', 'children'),
     Output('consigna-actual', 'children'),
     Output('error-control', 'children'),
     Output('accion-control', 'children'),
     Output('accion-control', 'style'),
     Output('grafica-control', 'figure'),
     Output('store-historial-control', 'data')],
    [Input('interval-control', 'n_intervals'),
     Input('button-limpiar-grafica', 'n_clicks')],
    [State('store-control', 'data'),
     State('store-historial-control', 'data')],
    prevent_initial_call=True
)
def proceso_control_automatico(n_intervals, n_limpiar, store_control, historial):
    global valor_integral, ajuste_realizado, coeficientes_ajuste
    
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    #REVISAR. YA TENEMOS EL COMANDO DE CONSIGNA
    
    # Si se presiona limpiar gráfica
    if trigger_id == 'button-limpiar-grafica':
        historial_limpio = {'tiempo': [], 'nivel': [], 'consigna': [], 'error': []}
        figura_vacia = {
            'data': [],
            'layout': {
                'title': 'Control de Nivel en Tiempo Real',
                'xaxis': {'title': 'Tiempo (s)'},
                'yaxis': {'title': 'Peso (g)'},
                'hovermode': 'closest',
                'showlegend': True
            }
        }
        return ('DETENIDO', 
                {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 
                 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold', 'color': '#e74c3c'},
                '0 g', '0 g', '0 g', 'NINGUNA',
                {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 
                 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold'},
                figura_vacia, historial_limpio)
    
    # Si el control no está activo
    if not store_control.get('activo', False):
        return ('DETENIDO', 
                {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 
                 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold', 'color': '#e74c3c'},
                '0 g', f"{store_control.get('consigna', 0)} g", '0 g', 'NINGUNA',
                {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 
                 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold'},
                {'data': [], 'layout': {'title': 'Control de Nivel en Tiempo Real'}}, historial)
    
    # Leer nivel según sensor seleccionado
    sensor = store_control.get('sensor', 'bascula')
    consigna = store_control.get('consigna', 400)
    histeresis = store_control.get('histeresis', 20)
    
    if sensor == 'bascula':
        peso_str = com.leer_peso(ser)
        try:
            nivel_actual = float(peso_str)
        except:
            nivel_actual = 0
    else:  # sensor RC
        if ajuste_realizado and coeficientes_ajuste is not None:
            nivel_actual = np.polyval(coeficientes_ajuste, valor_integral)
        else:
            nivel_actual = 0
    
    # Calcular error
    error = consigna - nivel_actual
    
    # Lógica de control con histéresis
    accion = "NINGUNA"
    estilo_accion = {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 
                     'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold'}
    
    if error > histeresis:
        # Nivel muy bajo, llenar
        com.comando_llenar(ser)
        accion = "LLENANDO ↑"
        estilo_accion['color'] = '#3498db'
        estilo_accion['backgroundColor'] = '#d6eaf8'
    elif error < -histeresis:
        # Nivel muy alto, vaciar
        com.comando_vaciar(ser)
        accion = "VACIANDO ↓"
        estilo_accion['color'] = '#e67e22'
        estilo_accion['backgroundColor'] = '#fdebd0'
    else:
        # Dentro del rango de histéresis, mantener
        com.comando_parar(ser)
        accion = "MANTENIENDO ✓"
        estilo_accion['color'] = '#27ae60'
        estilo_accion['backgroundColor'] = '#d5f4e6'
    
    # Calcular tiempo transcurrido
    tiempo_actual = time.time() - store_control.get('tiempo_inicio', time.time())
    
    # Actualizar historial
    historial['tiempo'].append(tiempo_actual)
    historial['nivel'].append(nivel_actual)
    historial['consigna'].append(consigna)
    historial['error'].append(error)
    
    # Limitar historial a últimos 100 puntos
    if len(historial['tiempo']) > 100:
        historial['tiempo'] = historial['tiempo'][-100:]
        historial['nivel'] = historial['nivel'][-100:]
        historial['consigna'] = historial['consigna'][-100:]
        historial['error'] = historial['error'][-100:]
    
    # Crear gráfica
    figura = {
        'data': [
            go.Scatter(x=historial['tiempo'], y=historial['nivel'], 
                      mode='lines', name='Nivel Actual',
                      line=dict(color='#3498db', width=2)),
            go.Scatter(x=historial['tiempo'], y=historial['consigna'],
                      mode='lines', name='Consigna',
                      line=dict(color='#27ae60', width=2, dash='dash')),
            go.Scatter(x=historial['tiempo'], y=[c + histeresis for c in historial['consigna']],
                      mode='lines', name='Límite Superior',
                      line=dict(color='#95a5a6', width=1, dash='dot'),
                      showlegend=True),
            go.Scatter(x=historial['tiempo'], y=[c - histeresis for c in historial['consigna']],
                      mode='lines', name='Límite Inferior',
                      line=dict(color='#95a5a6', width=1, dash='dot'),
                      fill='tonexty', fillcolor='rgba(149, 165, 166, 0.1)')
        ],
        'layout': {
            'title': 'Control de Nivel en Tiempo Real',
            'xaxis': {'title': 'Tiempo (s)'},
            'yaxis': {'title': 'Peso (g)'},
            'hovermode': 'x unified',
            'showlegend': True,
            'legend': {'x': 0, 'y': 1}
        }
    }
    
    # Preparar outputs
    estado_texto = "ACTIVO"
    estilo_estado = {'padding': '15px', 'backgroundColor': '#d5f4e6', 'borderRadius': '5px', 
                     'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold', 'color': '#27ae60'}
    
    return (estado_texto, estilo_estado,
            f"{nivel_actual:.2f} g",
            f"{consigna} g",
            f"{error:.2f} g",
            accion, estilo_accion,
            figura, historial)

# Callback para realizar ajuste
@app.callback(
    [Output('resultado-ajuste', 'children'),
     Output('peso-rc', 'children', allow_duplicate=True)],
    Input('button-ajuste', 'n_clicks'),
    [State('dropdown-tipo-ajuste', 'value')],
    prevent_initial_call=True
)
def realizar_ajuste(n_clicks, tipo_ajuste):
    global datos_calibracion, ajuste_realizado, coeficientes_ajuste
    
    if not datos_calibracion or len(datos_calibracion) < 3:
        return "Error: Se necesitan al menos 3 medidas para realizar el ajuste", "N/A"
    
    # Extraer datos
    pesos = np.array([d[0] for d in datos_calibracion])
    integrales = np.array([d[1] for d in datos_calibracion])
    
    try:
        # Realizar ajuste según tipo seleccionado
        if tipo_ajuste == 'lineal':
            coeficientes_ajuste = np.polyfit(integrales, pesos, 1)
            ecuacion = f"y = {coeficientes_ajuste[0]:.4f}x + {coeficientes_ajuste[1]:.4f}"
            
        elif tipo_ajuste == 'poly2':
            coeficientes_ajuste = np.polyfit(integrales, pesos, 2)
            ecuacion = f"y = {coeficientes_ajuste[0]:.4e}x² + {coeficientes_ajuste[1]:.4f}x + {coeficientes_ajuste[2]:.4f}"
            
        elif tipo_ajuste == 'poly3':
            coeficientes_ajuste = np.polyfit(integrales, pesos, 3)
            ecuacion = f"y = {coeficientes_ajuste[0]:.4e}x³ + {coeficientes_ajuste[1]:.4e}x² + {coeficientes_ajuste[2]:.4f}x + {coeficientes_ajuste[3]:.4f}"
        
        # Calcular R²
        peso_pred = np.polyval(coeficientes_ajuste, integrales)
        ss_res = np.sum((pesos - peso_pred) ** 2)
        ss_tot = np.sum((pesos - np.mean(pesos)) ** 2)
        r_squared = 1 - (ss_res / ss_tot)
        
        ajuste_realizado = True
        
        # Calcular peso RC actual
        peso_rc_actual = np.polyval(coeficientes_ajuste, valor_integral)
        
        resultado = html.Div([
            html.H4('Ajuste Realizado', style={'color': '#27ae60'}),
            html.P(f"Ecuación: {ecuacion}", style={'fontSize': '12px'}),
            html.P(f"R² = {r_squared:.4f}", style={'fontWeight': 'bold'}),
            html.P("✓ Peso RC habilitado en Setup", style={'color': '#27ae60', 'fontWeight': 'bold'})
        ])
        
        return resultado, f"{peso_rc_actual:.2f} g"
        
    except Exception as e:
        return f"Error al realizar ajuste: {str(e)}", "N/A"

# Modificar callback de actualizar_peso para incluir peso RC si hay ajuste
@app.callback(
    Output('peso-bascula', 'children'),
    Output('valor-condensador','children'),
    Output('tank-fill','style'),
    Output('peso-rc', 'children'),
    Input('interval-peso', 'n_intervals'),
    prevent_initial_call=True
)
def actualizar_peso_completo(n_intervals):
    global ajuste_realizado, coeficientes_ajuste, valor_integral
    
    peso = com.leer_peso(ser)
    valor_rc = valor_integral
    
    # Calcular peso RC si hay ajuste
    if ajuste_realizado and coeficientes_ajuste is not None:
        peso_rc = np.polyval(coeficientes_ajuste, valor_rc)
        peso_rc_str = f"{peso_rc:.2f} g"
    else:
        peso_rc_str = "N/A"
    
    # Convertir peso a float para las comparaciones
    try:
        peso_num = float(peso) if peso != "N/A" else 0
    except:
        peso_num = 0
    
    if peso_num > 0 and peso_num <= 200:
        estilo = estilo_tanque(25)
    elif peso_num > 200 and peso_num <= 400:
        estilo = estilo_tanque(50)
    elif peso_num > 400 and peso_num < 600:
        estilo = estilo_tanque(75)
    elif peso_num <= 0:
        estilo = estilo_tanque(0)
    elif peso_num >= 600:
        estilo = estilo_tanque(100)
    
    return f"{peso} g", f"{valor_rc:.2f}", estilo, peso_rc_str

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
