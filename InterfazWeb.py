import dash
from dash import dcc, html, Input, Output

# Crear la aplicación
app = dash.Dash(__name__)

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

if __name__ == '__main__':
    app.run(debug=True)
