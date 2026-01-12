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
from scipy.interpolate import interp1d, UnivariateSpline
import os

#CONFIGURACIÓN PUERTO SERIAL
puerto = 'COM4'
baudios = 9600
ser = None

# Solo abrir puerto serial en el proceso principal (evitar doble apertura en debug mode)
if not os.environ.get("WERKZEUG_RUN_MAIN"):
    try:
       ser = serial.Serial(puerto, baudios, timeout=2)
       time.sleep(1)
       print(f"✓ Puerto serial {puerto} conectado correctamente")
    except serial.SerialException as e:
       print(f"✗ Error al abrir el puerto serial: {e}")
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

# Variables para calibración RC
datos_calibracion = []
ajuste_realizado = False
funcion_interpolacion = None  # Función de interpolación
tipo_interpolacion_actual = None  # Tipo de interpolación usado
valor_integral = 0.0  # Valor de la integral del circuito RC

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
    dcc.Interval(id='interval-calibracion', interval=2000, disabled=True),  # Para calibración
    dcc.Interval(id='interval-control', interval=2000, disabled=True),  # Para control automático
    dcc.Store(id='store-llenando', data=False),  # Almacena el estado
    dcc.Store(id='store-calibrando', data={'activo': False, 'num_medidas': 0, 'medida_actual': 0}),
    dcc.Store(id='store-control', data={'activo': False, 'sensor': 'bascula', 'consigna': 400}),
    dcc.Store(id='store-historial-control', data={'tiempo': [], 'nivel': [], 'consigna': [], 'error': []}),
    dcc.Store(id='store-margen', data=10),  # Margen fijo del Arduino
    dcc.Store(id='store-calibracion-tabla', data=[]),
    dcc.Store(id='store-calibracion-figura', data={'data': [], 'layout': {'title': 'Peso Báscula vs Integral RC'}}),
    dcc.Store(id='store-calibracion-estado', data='Esperando...'),
    dcc.Store(id='store-calibracion-resultado-ajuste', data=''),
    dcc.Store(id='store-control-estado', data={'estado': 'DETENIDO', 'estilo': {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold', 'color': '#e74c3c'}}),
    dcc.Store(id='store-control-nivel', data='0 g'),
    dcc.Store(id='store-control-consigna-display', data='400 g'),
    dcc.Store(id='store-control-error', data='0 g'),
    dcc.Store(id='store-control-accion', data={'texto': 'NINGUNA', 'estilo': {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold'}}),
    dcc.Store(id='store-control-figura', data={'data': [], 'layout': {'title': 'Control de Nivel en Tiempo Real'}}),
    dcc.Store(id='store-setup', data={
        'peso_bascula': 'N/A',
        'valor_condensador': 'N/A',
        'peso_rc': 'N/A',
        'tank_style': {'width': '100%', 'height': '0%', 'backgroundColor': '#3498db', 'position': 'absolute', 'bottom': '0', 'transition': 'height 0.3s'}
    }),
    dcc.Interval(id='interval-rehidratacion', interval=100, max_intervals=1, disabled=True),
    
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
                            style={'display': 'block', 'margin': '50px auto', 'padding': '10px 60px'}),
                ])
            ], className='control-box', style={'display': 'inline-block', 'width': '300px','height': '175px', 'textAlign': 'center', 'verticalAlign': 'top'}),
            
            
        ], style={'display': 'block', 'marginLeft': '250px', 'marginTop': '40px'})
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
                    html.Label('Número de medidas: (Mínimo 10)', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
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
                html.H3('Función de Interpolación'),
                html.Div([
                    html.Label('Método:', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '5px'}),
                    html.P('Interpolación Lineal (scipy.interpolate.interp1d)', 
                           style={'fontSize': '12px', 'color': '#7f8c8d', 'fontStyle': 'italic', 'marginBottom': '20px'}),
                    html.Button('Realizar Interpolación', id='button-ajuste', n_clicks=0,
                               style={'width': '100%', 'padding': '15px', 'backgroundColor': '#3498db',
                                      'color': 'white', 'border': 'none', 'borderRadius': '5px',
                                      'fontSize': '16px', 'fontWeight': 'bold'}),
                    html.Div(id='resultado-ajuste', style={'display': 'none'})
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
                    html.P('El Arduino usa un margen de ±10g para el control', 
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
    Output('interval-rehidratacion', 'disabled'),
    Output('interval-rehidratacion', 'max_intervals'),
    Input('tabs-example-1', 'value'),
    prevent_initial_call=True
)
def activar_rehidratacion(tab):
    # Activar el interval brevemente para forzar la rehidratación
    return False, 1

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
        return dash.no_update
    
    # Verificar que el trigger sea por un cambio en n_clicks, no por inicialización
    trigger_prop = ctx.triggered[0]['prop_id']
    if '.n_clicks' not in trigger_prop:
        return dash.no_update
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Verificar que realmente se hizo click (n_clicks > 0)
    if n_llenar is None and n_vaciar is None and n_stop is None:
        return dash.no_update
    
    if button_id == 'button-llenar' and n_llenar > 0:
        com.comando_llenar(ser)
        return False  # Activa interval
    elif button_id == 'button-vaciar' and n_vaciar > 0:
        com.comando_vaciar(ser)
        return False  # Activa interval
    elif button_id == 'button-stop' and n_stop > 0:
        com.comando_parar(ser)
        return True   # Desactiva interval
    
    return dash.no_update

# Rehidratar visualización de Setup al cambiar de pestaña
@app.callback(
    [Output('peso-bascula', 'children', allow_duplicate=True),
     Output('valor-condensador','children', allow_duplicate=True),
     Output('tank-fill','style', allow_duplicate=True),
     Output('peso-rc', 'children', allow_duplicate=True)],
    [Input('tabs-example-1', 'value'),
     Input('interval-rehidratacion', 'n_intervals')],
    [State('store-setup', 'data')],
    prevent_initial_call='initial_duplicate'
)
def rehidratar_setup(tab, n_intervals, setup_data):
    if tab == 'tab-1':
        if setup_data and isinstance(setup_data, dict):
            return (
                setup_data.get('peso_bascula', 'N/A'),
                setup_data.get('valor_condensador', 'N/A'),
                setup_data.get('tank_style', {'width': '100%', 'height': '0%', 'backgroundColor': '#3498db', 'position': 'absolute', 'bottom': '0', 'transition': 'height 0.3s'}),
                setup_data.get('peso_rc', 'N/A')
            )
        return ('N/A', 'N/A', {'width': '100%', 'height': '0%', 'backgroundColor': '#3498db', 'position': 'absolute', 'bottom': '0', 'transition': 'height 0.3s'}, 'N/A')
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update

# Callback para tarar la báscula
@app.callback(
    Output('peso-bascula', 'children', allow_duplicate=True),
    Output('store-setup', 'data', allow_duplicate=True),
    Input('button-tarar', 'n_clicks'),
    State('store-setup', 'data'),
    prevent_initial_call=True
)
def tarar_bascula(n_clicks, setup_data):
    if n_clicks and n_clicks > 0:
        com.comando_tarar(ser)
        time.sleep(0.5)  # Esperar a que se complete el tarado
        peso = com.leer_peso(ser)
        # Actualizar store de Setup con el nuevo peso
        nuevo_store = dict(setup_data or {})
        nuevo_store['peso_bascula'] = f"{peso} g"
        return f"{peso} g", nuevo_store
    return dash.no_update, dash.no_update
# Modificar callback de actualizar_peso para incluir peso RC si hay ajuste
@app.callback(
    Output('peso-bascula', 'children'),
    Output('valor-condensador','children'),
    Output('tank-fill','style'),
    Output('peso-rc', 'children'),
    Output('store-setup', 'data', allow_duplicate=True),
    Input('interval-peso', 'n_intervals'),
    prevent_initial_call=True
)
def actualizar_peso_completo(n_intervals):
    global ajuste_realizado, funcion_interpolacion, valor_integral
    
    peso = com.leer_peso(ser)
    try:
        valor_rc = float(valor_integral)
    except Exception:
        valor_rc = 0.0
    
    # Calcular peso RC si hay ajuste
    if ajuste_realizado and funcion_interpolacion is not None:
        peso_rc = predecir_peso_desde_integral(valor_rc)
        peso_rc_str = f"{peso_rc:.2f} g"
    else:
        peso_rc_str = "N/A"
    
    # Calcular porcentaje de llenado de forma continua
    peso_maximo = 600  # Peso máximo del tanque en gramos
    peso_num = float(peso) if peso != "N/A" else 0
    porcentaje = min(100, max(0, (peso_num / peso_maximo) * 100))
    estilo = estilo_tanque(porcentaje)
    
    store_setup = {
        'peso_bascula': f"{peso} g",
        'valor_condensador': f"{valor_rc:.2f}",
        'peso_rc': peso_rc_str,
        'tank_style': estilo
    }

    return f"{peso} g", f"{valor_rc:.2f}", estilo, peso_rc_str, store_setup

##########################################################################################

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

    if button_id == 'button-run-calibracion' and n_run and n_run > 0:
        # Iniciar: vaciar hasta 0 sin medir
        datos_calibracion = []
        com.comando_vaciar(ser)
        return False, {
            'activo': True,
            'num_medidas': int(num_medidas or 10),
            'medidas_por_ciclo': 8,          # medidas por fase (llenado o vaciado)
            'medidas_totales': 0,
            'medida_en_fase': 0,
            'modo': 'vaciando',              # primer vaciado sin medir
            'primer_vaciado': True,
            # Estado de filtro/antirruido
            'hist_pesos': [],
            'ultimo_peso_filtrado': 0.0,
            'consec_en_margen': 0,
            'ultima_medicion_ts': 0.0
        }

    if button_id == 'button-stop-calibracion' and n_stop and n_stop > 0:
        com.comando_parar(ser)
        return True, {'activo': False, 'num_medidas': 0, 'medida_actual': 0}

    return True, store_data

# Callback para proceso de calibración
# Callback para rehidratar pestaña de calibración
@app.callback(
    [Output('estado-calibracion', 'children', allow_duplicate=True),
     Output('tabla-calibracion', 'data', allow_duplicate=True),
     Output('grafica-calibracion', 'figure', allow_duplicate=True),
     Output('resultado-ajuste', 'children', allow_duplicate=True)],
    [Input('tabs-example-1', 'value'),
     Input('interval-rehidratacion', 'n_intervals')],
    [State('store-calibracion-estado', 'data'),
     State('store-calibracion-tabla', 'data'),
     State('store-calibracion-figura', 'data'),
     State('store-calibracion-resultado-ajuste', 'data')],
    prevent_initial_call='initial_duplicate'
)
def rehidratar_calibracion(tab, n_intervals, estado, tabla, figura, resultado_ajuste):
    if tab == 'tab-2':
        # Proporcionar valores por defecto si los stores están vacíos
        if estado is None or estado == '':
            estado = 'Esperando...'
        if tabla is None:
            tabla = []
        if figura is None:
            figura = {'data': [], 'layout': {'title': 'Peso Báscula vs Integral RC', 'xaxis': {'title': 'Integral RC'}, 'yaxis': {'title': 'Peso (g)'}, 'hovermode': 'closest'}}
        if resultado_ajuste is None or resultado_ajuste == '':
            resultado_ajuste = ''
        return estado, tabla, figura, resultado_ajuste
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update

@app.callback(
    [Output('estado-calibracion', 'children'),
     Output('tabla-calibracion', 'data'),
     Output('grafica-calibracion', 'figure'),
     Output('store-calibrando', 'data', allow_duplicate=True),
     Output('interval-calibracion', 'disabled', allow_duplicate=True),
     Output('store-calibracion-tabla', 'data', allow_duplicate=True),
     Output('store-calibracion-figura', 'data', allow_duplicate=True),
     Output('store-calibracion-estado', 'data', allow_duplicate=True)],
    Input('interval-calibracion', 'n_intervals'),
    [State('store-calibrando', 'data')],
    prevent_initial_call=True
)
def proceso_calibracion(n_intervals, store_data):
    global datos_calibracion, valor_integral, funcion_interpolacion, ajuste_realizado, tipo_interpolacion_actual

    if not store_data.get('activo', False):
        tabla, fig = [], {'data': [], 'layout': {'title': 'Peso Báscula vs Integral RC'}}
        return "Esperando...", tabla, fig, store_data, True, tabla, fig, "Esperando..."

    # Lectura de peso
    peso_str = com.leer_peso(ser)
    try:
        peso_actual = float(peso_str)
    except (ValueError, TypeError):
        peso_actual = 0.0

    # Parámetros
    peso_min = 0
    peso_max = 600
    margen = 20

    # Estado
    num_medidas = int(store_data['num_medidas'])
    medidas_por_fase = int(store_data['medidas_por_ciclo'])  # ahora significa por fase
    medidas_totales = int(store_data['medidas_totales'])
    medida_en_fase = int(store_data.get('medida_en_fase', 0))
    modo = store_data.get('modo', 'vaciando')
    primer_vaciado = store_data.get('primer_vaciado', False)
    # Estado de filtrado (con valores por defecto si faltan)
    hist_pesos = list(store_data.get('hist_pesos', []))
    ultimo_peso_filtrado = float(store_data.get('ultimo_peso_filtrado', 0.0))
    consec_en_margen = int(store_data.get('consec_en_margen', 0))
    ultima_medicion_ts = float(store_data.get('ultima_medicion_ts', 0.0))

    # Helpers visualización
    def tabla_y_fig():
        tabla = [
            {'medida': i+1, 'peso': f"{d[0]:.2f}", 'integral': f"{d[1]:.2f}"}
            for i, d in enumerate(datos_calibracion)
        ]
        if datos_calibracion:
            pesos = [d[0] for d in datos_calibracion]
            integrales = [d[1] for d in datos_calibracion]
            fig = {
                'data': [go.Scatter(x=integrales, y=pesos, mode='markers',
                                    marker=dict(size=10, color='blue'),
                                    name='Datos medidos')],
                'layout': {'title': 'Peso Báscula vs Integral RC',
                           'xaxis': {'title': 'Integral RC'},
                           'yaxis': {'title': 'Peso (g)'},
                           'hovermode': 'closest'}
            }
        else:
            fig = {'data': [], 'layout': {'title': 'Peso Báscula vs Integral RC'}}
        return tabla, fig

    # Fin global
    if medidas_totales >= num_medidas:
        com.comando_parar(ser)
        estado = f"Calibración completada: {len(datos_calibracion)} medidas recolectadas"
        tabla, fig = tabla_y_fig()
        return estado, tabla, fig, store_data, True, tabla, fig

    # Primer vaciado sin medir
    if primer_vaciado:
        if peso_actual > (peso_min + margen):
            com.comando_vaciar(ser)
            estado = f"Vaciando depósito... (Actual: {peso_actual:.0f}g → Objetivo: {peso_min}g)"
            tabla, fig = tabla_y_fig()
            return estado, tabla, fig, store_data, False, tabla, fig, estado
        else:
            com.comando_parar(ser)
            store_data['primer_vaciado'] = False
            store_data['modo'] = 'llenando'
            store_data['medida_en_fase'] = 0
            com.comando_llenar(ser)
            estado = "Iniciando fase de llenado (mediciones)"
            tabla, fig = tabla_y_fig()
            return estado, tabla, fig, store_data, False, tabla, fig, estado

    # Pendientes y tamaño de esta fase
    pendientes = num_medidas - medidas_totales
    M_este = max(1, min(medidas_por_fase, pendientes))

    # Objetivo de esta fase (clamp para evitar negativos o > max)
    if modo == 'llenando':
        if M_este == 1:
            objetivo = peso_max
        else:
            indice = min(max(0, medida_en_fase), M_este - 1)
            objetivo = peso_min + (peso_max - peso_min) * (indice / (M_este - 1))
    else:  # vaciando
        if M_este == 1:
            objetivo = peso_min
        else:
            indice = min(max(0, medida_en_fase), M_este - 1)
            objetivo = peso_max - (peso_max - peso_min) * (indice / (M_este - 1))
    objetivo = max(peso_min, min(peso_max, objetivo))

    # Actualizar filtro de lectura (mediana de no-cero para mitigar picos)
    # Mantener ventana corta para respuesta rápida
    ventana = 5
    if not (modo == 'vaciando' and objetivo > (peso_min + margen) and peso_actual == 0):
        # Evita añadir ceros espurios en vaciado lejos de objetivo
        hist_pesos.append(peso_actual)
        if len(hist_pesos) > ventana:
            hist_pesos = hist_pesos[-ventana:]

    # Calcular peso filtrado (mediana de valores no-cero si hay)
    no_ceros = [p for p in hist_pesos if p > 0]
    if no_ceros:
        peso_filtrado = float(np.median(no_ceros))
    else:
        peso_filtrado = peso_actual if peso_actual > 0 else ultimo_peso_filtrado

    # Decidir acción de bomba hacia el objetivo actual
    if modo == 'llenando':
        com.comando_llenar(ser)
        alcanzado_base = (peso_filtrado >= objetivo - margen)
        estado_mov = f"Llenando hacia medida {medidas_totales + 1} (Actual: {peso_filtrado:.0f}g → Objetivo: {objetivo:.0f}g)"
    else:
        com.comando_vaciar(ser)
        # En vaciado, ignora ceros espurios lejos de objetivo
        if peso_filtrado == 0 and objetivo > (peso_min + margen):
            alcanzado_base = False
        else:
            alcanzado_base = (peso_filtrado <= objetivo + margen)
        estado_mov = f"Vaciando hacia medida {medidas_totales + 1} (Actual: {peso_filtrado:.0f}g → Objetivo: {objetivo:.0f}g)"

    # Anti-rebotes: requiere lecturas consecutivas dentro de margen reducido
    margen_consec = max(5, margen // 2)
    en_margen_consec = False
    if modo == 'llenando':
        en_margen_consec = (peso_filtrado >= objetivo - margen_consec)
    else:
        en_margen_consec = (peso_filtrado <= objetivo + margen_consec) and not (peso_filtrado == 0 and objetivo > (peso_min + margen))

    consec_en_margen = (consec_en_margen + 1) if en_margen_consec else 0
    min_consec = 2  # exigir al menos 2 lecturas consecutivas en margen
    alcanzado = alcanzado_base and (consec_en_margen >= min_consec)

    # ¿Registrar medida?
    if alcanzado:
        datos_calibracion.append([peso_filtrado, valor_integral])
        medidas_totales += 1
        medida_en_fase += 1
        store_data['medidas_totales'] = medidas_totales
        store_data['medida_en_fase'] = medida_en_fase
        store_data['ultima_medicion_ts'] = time.time()
        estado = f"Medida {medidas_totales} de {num_medidas} ({modo}, paso {medida_en_fase}/{M_este})"

        # Actualizar interpolación de forma incremental si hay suficientes puntos y valores únicos
        try:
            if len(datos_calibracion) >= 3:
                pesos_inc = np.array([d[0] for d in datos_calibracion])
                integrales_inc = np.array([d[1] for d in datos_calibracion])
                if len(np.unique(integrales_inc)) >= 2:
                    idx = np.argsort(integrales_inc)
                    integrales_sorted_inc = integrales_inc[idx]
                    pesos_sorted_inc = pesos_inc[idx]
                    funcion_interpolacion = interp1d(integrales_sorted_inc, pesos_sorted_inc, kind='linear', fill_value='extrapolate')
                    ajuste_realizado = True
                    tipo_interpolacion_actual = 'linear'
        except Exception:
            pass

        # ¿Fin global?
        if medidas_totales >= num_medidas:
            # Activar interpolación automáticamente para el RC en Setup
            try:
                pesos = np.array([d[0] for d in datos_calibracion])
                integrales = np.array([d[1] for d in datos_calibracion])
                if len(pesos) >= 2 and len(np.unique(integrales)) >= 2:
                    indices = np.argsort(integrales)
                    integrales_sorted = integrales[indices]
                    pesos_sorted = pesos[indices]
                    funcion = interp1d(integrales_sorted, pesos_sorted, kind='linear', fill_value='extrapolate')
                    # Persistir globals para Setup
                    funcion_interpolacion = funcion
                    ajuste_realizado = True
                    tipo_interpolacion_actual = 'linear'
            except Exception:
                pass

            com.comando_parar(ser)
            tabla, fig = tabla_y_fig()
            estado_final = f"Calibración completada: {len(datos_calibracion)} medidas recolectadas"
            return estado_final, tabla, fig, store_data, True, tabla, fig, estado_final

        # ¿Fin de fase? Cambiar fase y reiniciar contador
        if medida_en_fase >= M_este:
            store_data['medida_en_fase'] = 0
            if modo == 'llenando':
                store_data['modo'] = 'vaciando'
                com.comando_vaciar(ser)
                estado += " → Fin de fase de llenado. Comienza vaciado (con mediciones)."
            else:
                store_data['modo'] = 'llenando'
                com.comando_llenar(ser)
                estado += " → Fin de fase de vaciado. Comienza llenado (con mediciones)."
    else:
        estado = estado_mov

    # Persistir estado de filtro
    store_data['hist_pesos'] = hist_pesos
    store_data['ultimo_peso_filtrado'] = peso_filtrado
    store_data['consec_en_margen'] = consec_en_margen

    tabla, fig = tabla_y_fig()
    return estado, tabla, fig, store_data, False, tabla, fig, estado



# Callback para realizar ajuste
@app.callback(
    [Output('resultado-ajuste', 'children'),
     Output('store-calibracion-resultado-ajuste', 'data', allow_duplicate=True)],
    Input('button-ajuste', 'n_clicks'),
    prevent_initial_call=True
)
def realizar_ajuste(n_clicks):
    global datos_calibracion, ajuste_realizado, funcion_interpolacion, tipo_interpolacion_actual
    
    if not datos_calibracion or len(datos_calibracion) < 2:
        error_msg = "Error: Se necesitan al menos 2 medidas para realizar la interpolación"
        return error_msg, error_msg
    
    # Extraer datos
    pesos = np.array([d[0] for d in datos_calibracion])
    integrales = np.array([d[1] for d in datos_calibracion])
    
    # Verificar que no haya valores duplicados en integrales (requerido para interpolación)
    if len(np.unique(integrales)) < len(integrales):
        error_msg = "Error: Hay valores de integral duplicados. Se necesitan valores únicos para interpolar."
        return error_msg, error_msg
    
    try:
        # Ordenar los datos por integral (requerido para interpolación)
        indices = np.argsort(integrales)
        integrales_sorted = integrales[indices]
        pesos_sorted = pesos[indices]
        
        # Crear interpolación lineal
        funcion_interpolacion = interp1d(integrales_sorted, pesos_sorted, kind='linear', 
                                        fill_value='extrapolate')
        nombre_metodo = "Interpolación Lineal"
        descripcion = "Conecta los puntos con líneas rectas (scipy.interpolate.interp1d)"
        
        # Calcular error de interpolación en los puntos conocidos
        pesos_interpolados = funcion_interpolacion(integrales_sorted)
        
        # Calcular R² y error
        ss_res = np.sum((pesos_sorted - pesos_interpolados) ** 2)
        ss_tot = np.sum((pesos_sorted - np.mean(pesos_sorted)) ** 2)
        r_squared = 1 - (ss_res / ss_tot)
        
        rmse = np.sqrt(np.mean((pesos_sorted - pesos_interpolados) ** 2))
        max_error = np.max(np.abs(pesos_sorted - pesos_interpolados))
        
        ajuste_realizado = True
        tipo_interpolacion_actual = 'linear'
        
        resultado = html.Div([
            html.H4('Interpolación Completada', style={'color': '#27ae60'}),
            html.P(f"Método: {nombre_metodo}", style={'fontSize': '13px', 'fontWeight': 'bold'}),
            html.P(descripcion, style={'fontSize': '11px', 'fontStyle': 'italic', 'color': '#7f8c8d'}),
            html.Div([
                html.P(f"R² = {r_squared:.6f}", style={'fontWeight': 'bold', 'display': 'inline-block', 'marginRight': '15px'}),
                html.P(f"RMSE = {rmse:.4f} g", style={'display': 'inline-block', 'marginRight': '15px'}),
                html.P(f"Error máx = {max_error:.4f} g", style={'display': 'inline-block'})
            ]),
            html.P(f"Puntos interpolados: {len(datos_calibracion)}", style={'fontSize': '11px'}),
            html.P("✓ Peso RC habilitado en Setup", style={'color': '#27ae60', 'fontWeight': 'bold'})
        ])
        
        return resultado, resultado
        
    except Exception as e:
        error_msg = f"Error al realizar interpolación: {str(e)}"
        return error_msg, error_msg

def predecir_peso_desde_integral(integral_valor):
    """Función que usa la interpolación para predecir peso desde integral."""
    global funcion_interpolacion, datos_calibracion
    
    if funcion_interpolacion is None:
        return 0
    
    try:
        # Usar directamente la función de interpolación
        integrales_conocidas = np.array([d[1] for d in datos_calibracion])
        
        # Verificar si está dentro del rango
        if integral_valor < integrales_conocidas.min() or integral_valor > integrales_conocidas.max():
            # Extrapolación (puede ser menos precisa)
            peso = float(funcion_interpolacion(integral_valor))
        else:
            # Interpolación (más precisa)
            peso = float(funcion_interpolacion(integral_valor))
        
        return peso
    except Exception as e:
        print(f"Error en predicción: {e}")
        return 0

###################################################################################################################

# Callback para iniciar/detener control automático
@app.callback(
    [Output('interval-control', 'disabled'),
     Output('store-control', 'data')],
    [Input('button-iniciar-control', 'n_clicks'),
     Input('button-detener-control', 'n_clicks')],
    [State('dropdown-sensor', 'value'),
     State('input-consigna', 'value')],
    prevent_initial_call=True
)
def controlar_sistema(n_iniciar, n_detener, sensor, consigna):
    ctx = dash.callback_context
    if not ctx.triggered:
        return True, {'activo': False, 'sensor': sensor, 'consigna': consigna}
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'button-iniciar-control' and n_iniciar > 0:
        # Iniciar control
        if sensor == 'bascula':
            # Con báscula: Arduino hace el control automático
            com.comando_consigna(consigna, ser)
            time.sleep(0.2)
        # Con RC: la web hace el control (Arduino no puede leer RC directamente)
        return False, {'activo': True, 'sensor': sensor, 'consigna': consigna, 'tiempo_inicio': time.time()}
    
    elif button_id == 'button-detener-control' and n_detener > 0:
        # Detener control (desactiva flag y para bombas)
        com.comando_parar(ser)
        return True, {'activo': False, 'sensor': sensor, 'consigna': consigna}
    
    return True, {'activo': False, 'sensor': sensor, 'consigna': consigna}

# Callback para rehidratar pestaña de control
@app.callback(
    [Output('estado-control', 'children', allow_duplicate=True),
     Output('estado-control', 'style', allow_duplicate=True),
     Output('nivel-actual', 'children', allow_duplicate=True),
     Output('consigna-actual', 'children', allow_duplicate=True),
     Output('error-control', 'children', allow_duplicate=True),
     Output('accion-control', 'children', allow_duplicate=True),
     Output('accion-control', 'style', allow_duplicate=True),
     Output('grafica-control', 'figure', allow_duplicate=True)],
    [Input('tabs-example-1', 'value'),
     Input('interval-rehidratacion', 'n_intervals')],
    [State('store-control-estado', 'data'),
     State('store-control-nivel', 'data'),
     State('store-control-consigna-display', 'data'),
     State('store-control-error', 'data'),
     State('store-control-accion', 'data'),
     State('store-control-figura', 'data')],
    prevent_initial_call='initial_duplicate'
)
def rehidratar_control(tab, n_intervals, estado_data, nivel, consigna, error, accion_data, figura):
    if tab == 'tab-3':
        # Proporcionar valores por defecto si los stores están vacíos
        if estado_data is None:
            estado_data = {'estado': 'DETENIDO', 'estilo': {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold', 'color': '#e74c3c'}}
        if nivel is None:
            nivel = '0 g'
        if consigna is None:
            consigna = '400 g'
        if error is None:
            error = '0 g'
        if accion_data is None:
            accion_data = {'texto': 'NINGUNA', 'estilo': {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold'}}
        if figura is None:
            figura = {'data': [], 'layout': {'title': 'Control de Nivel en Tiempo Real', 'xaxis': {'title': 'Tiempo (s)'}, 'yaxis': {'title': 'Peso (g)'}, 'hovermode': 'closest', 'showlegend': True}}
        return (estado_data['estado'], estado_data['estilo'],
                nivel, consigna, error,
                accion_data['texto'], accion_data['estilo'],
                figura)
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

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
     Output('store-historial-control', 'data'),
     Output('store-control-estado', 'data', allow_duplicate=True),
     Output('store-control-nivel', 'data', allow_duplicate=True),
     Output('store-control-consigna-display', 'data', allow_duplicate=True),
     Output('store-control-error', 'data', allow_duplicate=True),
     Output('store-control-accion', 'data', allow_duplicate=True),
     Output('store-control-figura', 'data', allow_duplicate=True)],
    [Input('interval-control', 'n_intervals'),
     Input('button-limpiar-grafica', 'n_clicks')],
    [State('store-control', 'data'),
     State('store-historial-control', 'data')],
    prevent_initial_call=True
)
def proceso_control_automatico(n_intervals, n_limpiar, store_control, historial):
    global valor_integral, ajuste_realizado, funcion_interpolacion
    
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Si se presiona limpiar gráfica
    if trigger_id == 'button-limpiar-grafica' and n_limpiar > 0:
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
        estado_data = {'estado': 'DETENIDO', 'estilo': {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold', 'color': '#e74c3c'}}
        accion_data = {'texto': 'NINGUNA', 'estilo': {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold'}}
        return ('DETENIDO', estado_data['estilo'],
                '0 g', '0 g', '0 g', 'NINGUNA', accion_data['estilo'],
                figura_vacia, historial_limpio,
                estado_data, '0 g', '0 g', '0 g', accion_data, figura_vacia)
    
    # Si el control no está activo
    if not store_control.get('activo', False):
        estado_data = {'estado': 'DETENIDO', 'estilo': {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold', 'color': '#e74c3c'}}
        accion_data = {'texto': 'NINGUNA', 'estilo': {'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px', 'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold'}}
        consigna_str = f"{store_control.get('consigna', 0)} g"
        figura_actual = {'data': [], 'layout': {'title': 'Control de Nivel en Tiempo Real'}}
        return ('DETENIDO', estado_data['estilo'],
                '0 g', consigna_str, '0 g', 'NINGUNA', accion_data['estilo'],
                figura_actual, historial,
                estado_data, '0 g', consigna_str, '0 g', accion_data, figura_actual)
    
    # Leer nivel según sensor seleccionado
    sensor = store_control.get('sensor', 'bascula')
    consigna = store_control.get('consigna', 400)
    margen = 10  # Margen fijo del Arduino
    
    if sensor == 'bascula':
        peso_str = com.leer_peso(ser)
        try:
            nivel_actual = float(peso_str)
        except:
            nivel_actual = 0
    else:  # sensor RC
        if ajuste_realizado and funcion_interpolacion is not None:
            nivel_actual = predecir_peso_desde_integral(valor_integral)
        else:
            nivel_actual = 0
    
    # Calcular error
    error = consigna - nivel_actual
    
    # El Arduino maneja el control automáticamente
    # Solo monitoreamos y mostramos el estado
    accion = "CONTROL ARDUINO ACTIVO"
    estilo_accion = {'padding': '15px', 'backgroundColor': '#d5f4e6', 'borderRadius': '5px', 
                     'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold', 'color': '#27ae60'}
    
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
    
    # Crear gráfica con margen fijo de ±10g del Arduino
    figura = {
        'data': [
            go.Scatter(x=historial['tiempo'], y=historial['nivel'], 
                      mode='lines', name='Nivel Actual',
                      line=dict(color='#3498db', width=2)),
            go.Scatter(x=historial['tiempo'], y=historial['consigna'],
                      mode='lines', name='Consigna',
                      line=dict(color='#27ae60', width=2, dash='dash')),
            go.Scatter(x=historial['tiempo'], y=[c + margen for c in historial['consigna']],
                      mode='lines', name='Límite Superior (+10g)',
                      line=dict(color='#95a5a6', width=1, dash='dot'),
                      showlegend=True),
            go.Scatter(x=historial['tiempo'], y=[c - margen for c in historial['consigna']],
                      mode='lines', name='Límite Inferior (-10g)',
                      line=dict(color='#95a5a6', width=1, dash='dot'),
                      fill='tonexty', fillcolor='rgba(149, 165, 166, 0.1)')
        ],
        'layout': {
            'title': 'Control de Nivel en Tiempo Real (Arduino)',
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
    
    nivel_str = f"{nivel_actual:.2f} g"
    consigna_str = f"{consigna} g"
    error_str = f"{error:.2f} g"
    
    estado_data = {'estado': estado_texto, 'estilo': estilo_estado}
    accion_data = {'texto': accion, 'estilo': estilo_accion}
    
    return (estado_texto, estilo_estado,
            nivel_str, consigna_str, error_str,
            accion, estilo_accion,
            figura, historial,
            estado_data, nivel_str, consigna_str, error_str, accion_data, figura)

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


if __name__ == '__main__':
    try:
        app.run(debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("Cerrando aplicación...")
        running = False
        if ser:
            ser.close()
        if rp:
            rp.close()
