# PVI - Sistema de Control de Llenado con Instrumentación Virtual

Sistema de instrumentación virtual para el control automático de llenado/vaciado de depósitos, utilizando Arduino, Red Pitaya y una interfaz web.

## 🔧 Componentes del Sistema

| Componente | Descripción |
|------------|-------------|
| **Arduino** | Control de motores/bombas y lectura de balanza (HX711) vía comandos SCPI |
| **Red Pitaya** | Adquisición de señal y generación de funciones |
| **Interfaz Web** | Dashboard en Dash/Plotly para monitorización y control |

## 📁 Estructura

```
PVI/
├── InterfazWeb.py      # Interfaz web principal (Dash)
├── ComWeb.py           # Funciones de comunicación para la web
├── ComFinal.py         # Script de control por consola
├── redpitaya_scpi.py   # Librería SCPI para Red Pitaya
├── datos_ciclos.csv    # Datos de ciclos de llenado/vaciado
├── assets/styles.css   # Estilos de la interfaz
└── PruebaSCPI/
    └── PruebaSCPI.ino  # Firmware Arduino con comandos SCPI
```

## 🚀 Uso

### Requisitos
```
pip install dash plotly pyserial numpy scipy
```

### Ejecutar interfaz web
```
python InterfazWeb.py
```

### Conexiones
- **Arduino**: Puerto `COM4` a 9600 baudios
- **Red Pitaya**: IP `rp-f082af.local`

## ⚙️ Comandos SCPI (Arduino)

| Comando | Función |
|---------|---------|
| `STATus:OPERation:LLENar` | Iniciar llenado |
| `STATus:OPERation:VACiar` | Iniciar vaciado |
| `STATus:OPERation:PARar` | Detener operación |
| `STATus:OPERation:CONsigna#` | Establecer peso objetivo |
| `STATus:OPERation:CIClos#` | Configurar número de ciclos |
| `ESTAdo:MEDicion?` | Leer peso actual |
| `SYSTem:VERSion?` | Identificar dispositivo |

## 📊 Funcionalidades

- Control automático de ciclos de llenado/vaciado
- Calibración de sensor RC con interpolación
- Visualización en tiempo real de mediciones
- Exportación de datos a CSV
